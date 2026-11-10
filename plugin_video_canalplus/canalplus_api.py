# -*- coding: utf-8 -*-
#
# Canal+ (SK/CZ) - the Canal+ platform on top of the Solocoo / Broadpeak CDN.
#
# The addon is hybrid:
#   - sign-in by code via connect.canalplus.com and the schedule (EPG) with history go through
#     Solocoo (solocoo_api.py); the Solocoo session also returns the Canal+ passToken,
#   - playback (live and archive) goes natively through Canal+, where the box gets HD via PlayReady:
#       1. InitLiveTV(passToken)                   -> channels, LiveToken, RMUToken
#       2. WSXUrl(RMUToken) -> routemeup           -> MPD URL
#       3. GetLicence(LiveToken, EpgId, challenge) -> PlayReady license
#
# The schedule is stored on disk (Solocoo history + public spyro catalogue for the current time)
# and the channel list, archive and XML EPG all read from the stored schedule.

import calendar
import json
import os
import random
import re
import threading
import uuid
from bisect import bisect_left
from time import time, strftime, strptime, gmtime

from tools_archivczsk.contentprovider.exception import AddonErrorException

from .solocoo_api import SolocooEpg, SolocooAuthError

LTV_BASE = 'https://ltv.services.canalplustech.pro/api/V4'
SPYRO_BASE = 'https://spyro.prod.catalog.canal.canalplustech.pro/spyro/metadata'
WEB_HOST = 'https://www.canalplus.com'

ADDON_BUILD = 28

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')

DEVICE_INIT = '3'
DEVICE_LICENCE = '30'
APP_ID = '1'
LICENCE_PROVIDER = 'PlayReady'
LICENCE_MODE = 'MKPL'

BRANDS = {
	'cpsvk': {'zone': 'cpsvk', 'loc': 'sk'},
	'cpscz': {'zone': 'cpcze', 'loc': 'cz'},   # setting value kept, the service zone is cpcze
}

PASS_TOKEN_TTL = 1800       # passToken is refreshed after this time
INIT_TTL = 3 * 3600         # InitLiveTV (RMUToken/LiveToken) is refreshed after this time
EPG_TTL = 600               # channel schedule is kept in memory for this time
EPG_HISTORY_DAYS = 8        # how many days of schedule are kept on disk
EPG_WORKERS = 10            # how many channels are loaded in parallel
TIMEOUT = 20


# ##################################################################################################################

def iso_to_ts(value):
	"""2026-11-05T06:00:05.050Z -> unix timestamp (UTC)"""
	if not value:
		return 0
	try:
		return calendar.timegm(strptime(value[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S'))
	except Exception:
		return 0


def spyro_image(url, size='320x180'):
	if not url:
		return None
	return url.replace('{resolutionXY}', size)


def error_text(e):
	"""Exception text safe for both Python 2 and 3."""
	msg = None
	try:
		if getattr(e, 'args', None):
			msg = e.args[0]
	except Exception:
		msg = None
	if msg is None:
		try:
			msg = str(e)
		except Exception:
			msg = e.__class__.__name__
	if not isinstance(msg, str):
		try:
			msg = msg.decode('utf-8') if isinstance(msg, bytes) else ('%s' % (msg,))
		except Exception:
			msg = e.__class__.__name__
	return msg


def event_details(ev):
	"""Programme description - full description from Solocoo, otherwise at least the subtitle (episode)."""
	if not isinstance(ev, dict):
		return ''
	desc = ev.get('desc') or ''
	sub = ev.get('subtitle') or ''
	if desc and sub and sub not in desc:
		return '%s\n%s' % (sub, desc)
	return desc or sub


def new_user_key_id():
	return str(uuid.uuid4())


def _new_device_key_id():
	"""DeviceKeyId for GetLicence in the <ms>-<12hex> format (like the web client)."""
	return '%d-%012x' % (int(time() * 1000), random.getrandbits(48))


def _bpk_time(ts):
	"""unix timestamp -> YYYYMMDDTHHMMSS (UTC) for broadpeak begin/end"""
	return strftime('%Y%m%dT%H%M%S', gmtime(int(ts)))


def _strip_bpk_placeholders(src):
	"""Removes the Broadpeak SmartLib placeholder parameters (bkm-query, begin, end) from the URL."""
	if not src or '?' not in src:
		return src
	base, query = src.split('?', 1)
	params = [p for p in query.split('&') if p and p != 'bkm-query'
	          and not re.match(r'^(begin|end)=', p)]
	return base + ('?' + '&'.join(params) if params else '')


class CanalplusSessionError(Exception):
	"""Invalid or expired passId/token."""
	pass


# ##################################################################################################################

class CanalplusApi(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()

		self.brand = 'cpsvk'
		self.user_key_id = None

		self.pass_token = None
		self.pass_token_time = 0

		self.live_token = None
		self.rmu_token = None
		self.channels_raw = []
		self.init_time = 0

		self.data_dir = getattr(self.cp, 'data_dir', None)
		self._epg_cache = {}
		self._epg_saved_sig = {}
		self._epg_lock = threading.Lock()
		self._epg_file_lock = threading.Lock()   # load + merge + save of a channel schedule
		self._lock = threading.RLock()

		# Solocoo - sign-in and schedule with history
		self.solocoo = SolocooEpg(self)
		self._solocoo_fetch_time = 0

	# ##############################################################################################################

	def _brand(self):
		return BRANDS.get(self.brand) or BRANDS['cpsvk']

	def logged_in(self):
		return bool(self.pass_token) or self.solocoo.is_paired()

	def setup(self, brand, user_key_id):
		if brand in BRANDS:
			self.brand = brand
		self.user_key_id = user_key_id or new_user_key_id()
		self.pass_token = None
		self.pass_token_time = 0
		self.live_token = None
		self.rmu_token = None
		self.channels_raw = []
		self.init_time = 0
		with self._epg_lock:
			self._epg_cache = {}

	def request_timeout(self):
		try:
			value = int(self.cp.get_setting('loading_timeout'))
		except Exception:
			value = 0
		return value if value > 0 else TIMEOUT

	def ensure_pass_token(self, force=False):
		"""Canal+ passToken for native playback - provided by the Solocoo session."""
		with self._lock:
			if not force and self.pass_token and (time() - self.pass_token_time) < PASS_TOKEN_TTL:
				return

			try:
				self.solocoo.ensure_session(force=force)
			except SolocooAuthError as e:
				raise CanalplusSessionError(error_text(e))

			if not self.solocoo.pass_token:
				raise Exception('Solocoo session returned no passToken')

			self.pass_token = self.solocoo.pass_token
			self.pass_token_time = time()

	# ##############################################################################################################
	# channels

	def _ltv_url(self, device, job, provider=None):
		b = self._brand()
		if provider:
			return '%s/zones/%s/devices/%s/apps/%s/providers/%s/jobs/%s' % (
				LTV_BASE, b['zone'], device, APP_ID, provider, job)
		return '%s/zones/%s/devices/%s/apps/%s/jobs/%s' % (LTV_BASE, b['zone'], device, APP_ID, job)

	def _ltv_headers(self):
		return {
			'User-Agent': USER_AGENT,
			'Content-Type': 'application/json',
			'Origin': WEB_HOST,
			'Referer': WEB_HOST + '/',
		}

	def ensure_channels(self, force=False):
		with self._lock:
			if not force and self.channels_raw and (time() - self.init_time) < INIT_TTL:
				return

			self.ensure_pass_token()

			body = {'ServiceRequest': {'InData': {
				'UseRmuTokenPlaceHolder': True,
				'PassData': {'Id': 0, 'Token': self.pass_token},
				'UserKeyId': self.user_key_id,
				'DeviceKeyId': str(uuid.uuid4()),
				# same channel groups as the official app requests
				'PDSData': {'GroupTypes': '1;4'},
				'DeviceSpecificities': {'BpkCompatibility': True},
			}}}

			response = self.req_session.post(self._ltv_url(DEVICE_INIT, 'InitLiveTV'), json=body,
			                                 headers=self._ltv_headers(), timeout=max(30, self.request_timeout()))

			if response.status_code in (401, 403):
				if not force:
					self.ensure_pass_token(force=True)
					return self.ensure_channels(force=True)
				raise CanalplusSessionError('InitLiveTV HTTP %d' % response.status_code)

			try:
				sr = (response.json() or {}).get('ServiceResponse') or {}
			except Exception:
				raise Exception('InitLiveTV: invalid response (HTTP %d)' % response.status_code)

			if sr.get('Status') not in ('0', 0):
				# the error details are needed to diagnose accounts the addon wasn't tested with (e.g. CZ)
				details = dict((k, v) for k, v in sr.items() if k != 'OutData')
				self.cp.log_error('InitLiveTV failed: %s' % json.dumps(details, ensure_ascii=False)[:600])
				raise Exception('InitLiveTV status %s%s' % (sr.get('Status'), (' - %s' % sr.get('Message')) if sr.get('Message') else ''))

			out = sr.get('OutData') or {}
			self.live_token = out.get('LiveToken')
			self.rmu_token = out.get('RMUToken')

			channels = []
			seen = set()
			try:
				groups = out['PDS']['ChannelsGroups']['ChannelsGroup']
			except Exception:
				groups = []
			for group in groups:
				group_channels = group.get('Channels') or []
				self.cp.log_debug('InitLiveTV: group %s - %d channels' % (group.get('GroupType'), len(group_channels)))
				for ch in group_channels:
					epg_id = ch.get('EpgId')
					if epg_id in seen:
						continue
					seen.add(epg_id)
					channels.append(ch)

			if not channels:
				pds = out.get('PDS')
				self.cp.log_error('InitLiveTV returned no channels, PDS: %s' % json.dumps(pds, ensure_ascii=False)[:600])
				raise AddonErrorException(self.cp._('Your Canal+ account has no live TV channels available. Check that your subscription includes TV channels.'))

			self.channels_raw = channels
			self.init_time = time()
			self.cp.log_debug('InitLiveTV: %d channels' % len(channels))

	def channels(self):
		self.ensure_channels()
		return self.channels_raw

	# ##############################################################################################################
	# playback

	def _resolve_routemeup(self, wsx_url):
		url = (wsx_url or '').replace('{RMUToken}', self.rmu_token or '')
		response = self.req_session.get(url, headers={'User-Agent': USER_AGENT},
		                                timeout=self.request_timeout(), allow_redirects=True)
		if response.status_code in (401, 403):
			raise CanalplusSessionError('routemeup HTTP %d' % response.status_code)
		response.raise_for_status()
		return response.json()

	def _routemeup(self, channel, dvr):
		"""routemeup for a channel; on an expired RMUToken refreshes InitLiveTV once."""
		def wsx():
			url = channel.get('WSXUrl') or ''
			# the archive has its own dvr-dash path with the same RMUToken
			return url.replace('/dash/', '/dvr-dash/').replace('.json?', '?') if dvr else url

		try:
			return self._resolve_routemeup(wsx())
		except CanalplusSessionError:
			self.ensure_channels(force=True)

		try:
			return self._resolve_routemeup(wsx())
		except CanalplusSessionError as e:
			if not dvr:
				raise
			# archive refused even with a new token - this is not an expired sign-in
			raise Exception('Archive is not available (%s)' % error_text(e))

	def get_stream(self, channel, live=True, begin=None, end=None):
		"""Manifest URL and license context for a channel (InitLiveTV record).
		begin/end (unix timestamp) = archive playback."""
		self.ensure_channels()

		if not channel.get('WSXUrl'):
			raise Exception('Channel has no stream address')

		if begin:
			routemeup = self._routemeup(channel, True)
			node = routemeup.get('dvr') or routemeup.get('primary') or routemeup.get('nodvr') or {}
			base = _strip_bpk_placeholders(node.get('src') or '')
			if base:
				q = 'begin=%s' % _bpk_time(begin)
				if end:
					q += '&end=%s' % _bpk_time(end)
				src = base + ('&' if '?' in base else '?') + q
			else:
				src = ''
		else:
			routemeup = self._routemeup(channel, False)
			node = routemeup.get('nodvr') or routemeup.get('primary') or {}
			src = _strip_bpk_placeholders(node.get('src') or '')

		if not src:
			raise Exception('routemeup returned no stream URL')

		callbacks = routemeup.get('callbacks') or {}

		return {
			'url': src,
			'title': channel.get('Name') or '',
			'keepalive': (callbacks.get('keepalive') or {}).get('url'),
			'teardown': (callbacks.get('teardown') or {}).get('url'),
			# LiveToken and UserKeyId are not put into the URL (they are long), they are read from memory at license time
			'license': {
				'url': self._ltv_url(DEVICE_LICENCE, 'GetLicence', LICENCE_PROVIDER),
				'epg_id': channel.get('EpgId'),
			},
		}

	def get_license(self, ctx, challenge):
		"""Wraps the PlayReady challenge into GetLicence and returns the license (bytes).
		If the server refuses the LiveToken, refreshes InitLiveTV once and retries."""
		self.ensure_channels()

		if isinstance(challenge, bytes):
			try:
				challenge = challenge.decode('utf-8')
			except Exception:
				challenge = challenge.decode('latin-1')

		# ChallengeInfo is embedded into a larger XML, the <?xml ...?> declaration must not be there
		challenge = challenge.lstrip()
		if challenge.startswith('<?xml'):
			pos = challenge.find('?>')
			if pos != -1:
				challenge = challenge[pos + 2:].lstrip()

		body = {'ServiceRequest': {'InData': {
			'EpgId': ctx.get('epg_id'),
			'LiveToken': self.live_token,
			'UserKeyId': self.user_key_id,
			'DeviceKeyId': _new_device_key_id(),
			'ChallengeInfo': challenge,
			'Mode': LICENCE_MODE,
			'PersistentLicense': 'false',
		}}}

		url = ctx.get('url') or self._ltv_url(DEVICE_LICENCE, 'GetLicence', LICENCE_PROVIDER)

		for attempt in (1, 2):
			body['ServiceRequest']['InData']['LiveToken'] = self.live_token
			response = self.req_session.post(url, json=body, headers=self._ltv_headers(),
			                                 timeout=self.request_timeout())
			try:
				data = response.json() or {}
			except Exception:
				data = {}

			sr = data.get('ServiceResponse') or {}
			licence = (sr.get('OutData') or {}).get('LicenseInfo')
			if licence or attempt == 2:
				break
			# the token may have expired before INIT_TTL - refresh and try once more
			self.cp.log_debug('GetLicence failed (HTTP %d), refreshing InitLiveTV' % response.status_code)
			try:
				self.ensure_channels(force=True)
			except Exception as e:
				self.cp.log_error('InitLiveTV refresh failed: %s' % error_text(e))
				break

		if not licence:
			status = sr.get('Status')
			self.cp.log_error('GetLicence failed: HTTP %d, response: %s'
			                  % (response.status_code, json.dumps(sr, ensure_ascii=False)[:600]))
			raise Exception('GetLicence failed (HTTP %d, status %s)' % (response.status_code, status))

		return licence.encode('utf-8')

	def _session_callback(self, url, what):
		"""Broadpeak keepalive/teardown - never raises."""
		if not url:
			return
		try:
			self.req_session.get(url, headers={'User-Agent': USER_AGENT}, timeout=self.request_timeout())
		except Exception as e:
			self.cp.log_debug('Broadpeak %s failed: %s' % (what, error_text(e)))

	def keepalive(self, url):
		self._session_callback(url, 'keepalive')

	def teardown(self, url):
		self._session_callback(url, 'teardown')

	# ##############################################################################################################
	# schedule (EPG)

	def _epg_store_path(self, epg_id):
		if not self.data_dir:
			return None
		return os.path.join(self.data_dir, 'epg', '%s.json' % epg_id)

	def _epg_load_stored(self, epg_id):
		"""File format: [[start, end, title, subtitle, image], ...]"""
		path = self._epg_store_path(epg_id)
		if not path:
			return []
		try:
			with open(path, 'r') as f:
				raw = json.load(f) or []
		except Exception:
			return []
		out = []
		for e in raw:
			try:
				out.append({'start': int(e[0]), 'end': int(e[1]) or 0,
				            'title': e[2] or '', 'subtitle': e[3] or '', 'image': e[4] or None,
				            'desc': (e[5] if len(e) > 5 else '') or '',
				            'id': (e[6] if len(e) > 6 else '') or ''})
			except Exception:
				continue
		return out

	def _epg_save(self, epg_id, events):
		path = self._epg_store_path(epg_id)
		if not path:
			return
		try:
			folder = os.path.dirname(path)
			if not os.path.isdir(folder):
				os.makedirs(folder)
			data = [[e['start'], e.get('end') or 0, e.get('title') or '', e.get('subtitle') or '',
			         e.get('image') or '', e.get('desc') or '', e.get('id') or ''] for e in events]
			tmp = path + '.tmp'
			with open(tmp, 'w') as f:
				json.dump(data, f)
			os.rename(tmp, path)
		except Exception as e:
			self.cp.log_error('Failed to save EPG for %s: %s' % (epg_id, error_text(e)))

	def _spyro_url(self, epg_id):
		b = self._brand()
		return '%s/%s/%s/canal-3.0/chid%s.json' % (SPYRO_BASE, b['zone'], b['loc'], epg_id)

	def _fetch_epg(self, epg_id):
		"""Channel schedule from the public catalogue. Returns None if it couldn't be loaded."""
		try:
			response = self.req_session.get(self._spyro_url(epg_id),
			                                headers={'User-Agent': USER_AGENT, 'Origin': WEB_HOST},
			                                timeout=self.request_timeout())
			if response.status_code != 200:
				self.cp.log_debug('EPG for %s: HTTP %d' % (epg_id, response.status_code))
				return None
			data = response.json() or {}
		except Exception as e:
			self.cp.log_debug('EPG for %s failed: %s' % (epg_id, error_text(e)))
			return None

		events = []
		for ch in (data.get('channels') or []):
			for ev in (ch.get('events') or []):
				start = iso_to_ts(ev.get('startDate'))
				if not start:
					continue
				events.append({
					'start': start,
					'end': iso_to_ts(ev.get('endDate')),
					'title': ev.get('title') or '',
					'subtitle': ev.get('subTitle') or '',
					'image': spyro_image(ev.get('picture')),
				})
		events.sort(key=lambda e: e['start'])
		return events

	def get_epg(self, epg_id):
		"""Channel schedule (downloaded + stored history) as [{start, end, title, subtitle, image}]."""
		epg_id = str(epg_id)
		now = time()
		with self._epg_lock:
			hit = self._epg_cache.get(epg_id)
			if hit and (now - hit[0]) < EPG_TTL:
				return hit[1]

		fetched = self._fetch_epg(epg_id)

		with self._epg_file_lock:
			merged = {}
			self._merge_window(merged, self._epg_load_stored(epg_id), fetched or [])

			cutoff = int(now) - EPG_HISTORY_DAYS * 86400
			events = sorted((ev for s, ev in merged.items() if s >= cutoff), key=lambda ev: ev['start'])

			if fetched:
				# write only when changed
				sig = (len(events), events[0]['start'] if events else 0, events[-1]['start'] if events else 0)
				if self._epg_saved_sig.get(epg_id) != sig:
					self._epg_save(epg_id, events)
					self._epg_saved_sig[epg_id] = sig

		with self._epg_lock:
			if len(self._epg_cache) > 300:
				self._epg_cache = {}
			self._epg_cache[epg_id] = (now, events)
		return events

	@staticmethod
	def _merge_window(merged, stored, fresh):
		"""Merges the stored schedule with a freshly downloaded one.

		A stored programme overlapping in time with a fresh one is dropped (otherwise both the old
		and the new one would remain when the schedule shifts). If a fresh programme with the same
		start and title lacks a description, image, subtitle or id, they are taken from the stored one.
		Where the fresh schedule is missing (e.g. one request failed), the stored one stays."""
		fresh = sorted(fresh, key=lambda e: e['start'])
		starts = [ev['start'] for ev in fresh]
		replaced = {}
		for ev in stored:
			s = ev['start']
			e = ev['end'] or (s + 1)
			i = bisect_left(starts, e) - 1     # last fresh programme starting before the end
			if i >= 0 and (fresh[i]['end'] or (fresh[i]['start'] + 1)) > s:
				replaced[s] = ev
				continue
			merged[s] = ev
		for ev in fresh:
			old = replaced.get(ev['start'])
			if old and old.get('title') == ev.get('title'):
				for f in ('desc', 'image', 'subtitle', 'id'):
					if not ev.get(f) and old.get(f):
						ev[f] = old[f]
			merged[ev['start']] = ev

	def get_epg_now_many(self, epg_ids, when=None):
		"""Loads the schedule in parallel and returns {epg_id: currently running event or None}."""
		when = when or int(time())
		result = {}
		todo = [str(e) for e in epg_ids if e]
		if not todo:
			return result

		lock = threading.Lock()
		index = {'i': 0}

		def worker():
			while True:
				with lock:
					i = index['i']
					if i >= len(todo):
						return
					index['i'] = i + 1
				epg_id = todo[i]
				now_ev = None
				for ev in self.get_epg(epg_id):
					if ev['start'] <= when < (ev['end'] or (ev['start'] + 1)):
						now_ev = ev
						break
				with lock:
					result[epg_id] = now_ev

		threads = [threading.Thread(target=worker) for _ in range(min(EPG_WORKERS, len(todo)))]
		for t in threads:
			t.daemon = True
			t.start()
		for t in threads:
			t.join(timeout=max(30, self.request_timeout() * 2))
		return result

	def get_epg_range(self, epg_id, time_from, time_to):
		"""Channel events overlapping the range."""
		return [ev for ev in self.get_epg(epg_id)
		        if (ev['end'] or (ev['start'] + 1)) > time_from and ev['start'] < time_to]

	# ##############################################################################################################
	# Solocoo schedule (EPG with history) - written into the same storage as spyro,
	# so the channel list, archive and XML EPG all use it.
	# Solocoo channel id = 'cc' + native EpgId.

	@staticmethod
	def solocoo_cc_id(epg_id):
		eid = str(epg_id or '')
		return eid if eid.startswith('cc') else ('cc' + eid)

	def _merge_solocoo(self, epg_id, events):
		"""Merges Solocoo events with the stored channel schedule and saves it."""
		if not events:
			return 0
		epg_id = str(epg_id)
		with self._epg_file_lock:
			merged = {}
			self._merge_window(merged, self._epg_load_stored(epg_id), events)
			cutoff = int(time()) - EPG_HISTORY_DAYS * 86400
			out = sorted((ev for s, ev in merged.items() if s >= cutoff), key=lambda e: e['start'])
			self._epg_save(epg_id, out)
		with self._epg_lock:
			self._epg_saved_sig[epg_id] = None   # the next merge with spyro will be saved
			self._epg_cache.pop(epg_id, None)
		return len(events)

	def fetch_solocoo_channel(self, epg_id, time_from, time_to, with_desc=True):
		"""Fetches the Solocoo schedule of one channel for the given range on demand,
		including full programme descriptions (synopsis). Called when an archive day is opened."""
		if not self.solocoo.is_paired():
			return False
		cc = self.solocoo_cc_id(epg_id)
		try:
			sched = self.solocoo.get_schedule([cc], time_from, time_to)
		except Exception as e:
			self.cp.log_error('Solocoo schedule for %s failed: %s' % (epg_id, error_text(e)))
			return False
		evs = sched.get(cc) or []
		if not evs:
			return False
		if with_desc:
			try:
				ids = [e['id'] for e in evs if e.get('id')]
				desc_map = self.solocoo.get_descriptions(ids)
				for e in evs:
					d = desc_map.get(e.get('id'))
					if d:
						e['desc'] = d
			except Exception as e2:
				self.cp.log_error('Solocoo descriptions for %s failed: %s' % (epg_id, error_text(e2)))
		self._merge_solocoo(epg_id, evs)
		return True

	def fetch_solocoo_epg(self, channels, force=False):
		"""Bulk-fetches the Solocoo schedule (history + a few days ahead) for all channels.
		Called in the background. Returns the number of channels that got something written."""
		if not self.solocoo.is_paired() or not channels:
			return 0
		now = int(time())
		if not force and (now - self._solocoo_fetch_time) < 1800:
			return 0

		cc_map = {}
		for ch in channels:
			eid = str(getattr(ch, 'epg_id', None) or getattr(ch, 'key', '') or '')
			if eid:
				cc_map[self.solocoo_cc_id(eid)] = eid

		if not cc_map:
			return 0

		t_from = now - EPG_HISTORY_DAYS * 86400
		t_to = now + 2 * 86400
		try:
			sched = self.solocoo.get_schedule(list(cc_map.keys()), t_from, t_to)
		except Exception as e:
			self.cp.log_error('Solocoo schedule failed: %s' % error_text(e))
			return 0

		count = 0
		for cc, evs in sched.items():
			eid = cc_map.get(cc)
			if eid and evs:
				self._merge_solocoo(eid, evs)
				count += 1
		self._solocoo_fetch_time = now
		self.cp.log_debug('Solocoo schedule stored for %d channels' % count)
		return count
