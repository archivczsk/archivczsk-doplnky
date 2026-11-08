# -*- coding: utf-8 -*-
#
# Canal+ (SK/CZ) - zive kanaly, archiv, userbouquet a XML EPG.
# Prihlasenie kodom cez connect.canalplus.com (vid canalplus_api.py).

import sys
import base64
from hashlib import md5
from time import time, strftime, localtime

from tools_archivczsk.contentprovider.extended import (ModuleContentProvider, CPModuleLiveTV,
                                                       CPModuleArchive, CPModuleTemplate)
from tools_archivczsk.string_utils import _I, _C
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.generator.lamedb import channel_name_normalise

from .canalplus_api import (CanalplusApi, CanalplusSessionError, USER_AGENT, error_text,
                            event_details, new_user_key_id, ADDON_VERSION, ADDON_BUILD)
from .bouquet import CanalplusBouquetXmlEpgGenerator

# zoznam kanalov tahame najviac raz za tento cas
CHANNELS_CACHE_SECONDS = 600

# dokedy siaha DVR okno (catch-up) a aky dlhy je blok v nahradnom vypise archivu
ARCHIVE_HOURS = 168         # 7 dni
# PlayReady CDM v tools_cenc potrebuje Python 3; na Python 2.7 ide prehravanie cez Widevine (Solocoo)
is_py2 = sys.version_info[0] == 2
ARCHIVE_BLOCK_SECONDS = 30 * 60

# rozmer picon/loga (LogoUrl ma zastupny {resolutionXY})
LOGO_SIZE = '220x220'


# ##################################################################################################################

def _flag(value):
	"""Priznak z API, ktore ho posiela ako retazec 'true' alebo ako bool."""
	return value in (True, 'true', 'True', 1, '1')


def logo_url(url):
	if not url:
		return None
	return url.replace('{resolutionXY}', LOGO_SIZE)


class CanalplusChannel(object):
	__slots__ = ('key', 'id', 'name', 'picon', 'lcn', 'dvr', 'no_access', 'epg_id',
	             'epg_name', 'epg_desc', 'epg_img', 'epg_start', 'epg_stop')

	def __init__(self, key, cid, name, picon=None, lcn=None, dvr=False, no_access=False):
		self.key = key          # EpgId ako retazec
		self.id = cid           # ciselne id pre bouquet
		self.name = name
		self.picon = picon
		self.lcn = lcn
		self.dvr = dvr
		self.no_access = no_access
		self.epg_id = key
		self.epg_name = None
		self.epg_desc = None
		self.epg_img = None
		self.epg_start = None
		self.epg_stop = None


# ##################################################################################################################

class CanalplusModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=False)

	def get_live_tv_channels(self, cat_id=None):
		try:
			self.cp.load_channel_list()
			self.cp.load_epg(self.cp.channels)
		except CanalplusSessionError:
			self.cp.session_expired()
			return

		enable_download = self.cp.get_setting('download_live')

		for channel in self.cp.channels:
			title = channel.name
			if channel.lcn:
				title = '%d. %s' % (channel.lcn, title)
			if channel.no_access:
				title = _C('grey', title)

			if channel.epg_name:
				epg_str = '  ' + _I(channel.epg_name)
				plot = '%s - %s' % (self.cp.timestamp_to_str(channel.epg_start),
				                    self.cp.timestamp_to_str(channel.epg_stop))
				if channel.epg_desc:
					plot += '\n' + channel.epg_desc
				info_labels = {'title': channel.epg_name, 'plot': plot}
				if channel.epg_start and channel.epg_stop:
					info_labels['duration'] = channel.epg_stop - channel.epg_start
			else:
				epg_str = ''
				info_labels = {'title': channel.name}

			menu = self.cp.create_ctx_menu()
			if channel.dvr and self.cp.archive_module:
				menu.add_menu_item(self.cp._("Archive"),
				                   cmd=self.cp.archive_module.get_archive_days_for_channels,
				                   channel_id=channel.key, archive_hours=ARCHIVE_HOURS)

			img = channel.epg_img or channel.picon

			self.cp.add_video(title + epg_str, img, info_labels, menu=menu, download=enable_download,
			                  cmd=self.cp.get_live_stream,
			                  channel_key=channel.key, channel_name=channel.name)


# ##################################################################################################################

class CanalplusModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	def get_archive_channels(self):
		try:
			self.cp.load_channel_list()
		except CanalplusSessionError:
			self.cp.session_expired()
			return

		for channel in self.cp.channels:
			if channel.dvr and not channel.no_access:
				self.add_archive_channel(channel.name, channel.key, ARCHIVE_HOURS, img=channel.picon)

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		channel = self.cp.channels_by_key.get(channel_id)
		channel_name = channel.name if channel else ''

		try:
			events = self.cp.api.get_epg_range(channel_id, ts_from, ts_to)
		except Exception as e:
			self.cp.show_error(self.cp._("Failed to load the TV guide: %s") % error_text(e))
			return

		now = int(time())
		oldest = now - ARCHIVE_HOURS * 3600

		# pri otvoreni dna sa zo Solocoo dotiahne program aj s plnymi popismi relacii
		if self.cp.api.solocoo.is_paired():
			try:
				if self.cp.api.fetch_solocoo_channel(channel_id, ts_from - 3600, ts_to + 3600):
					events = self.cp.api.get_epg_range(channel_id, ts_from, ts_to)
			except Exception as e:
				self.cp.log_error('Solocoo schedule failed: %s' % error_text(e))

		if not events:
			# pre dni, z ktorych este nie je ulozeny program, ponukneme casove bloky
			self.archive_time_blocks(channel_id, channel_name, ts_from, ts_to, now)
			return

		for ev in events:
			start = ev['start']
			stop = ev['end'] or start
			name = ev['title'] or ''
			if ev.get('subtitle'):
				name = '%s - %s' % (name, ev['subtitle'])

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start),
			                          self.cp.timestamp_to_str(stop), _I(name))

			info_labels = {'title': ev['title'] or name, 'plot': event_details(ev)}
			if start and stop:
				info_labels['duration'] = stop - start
			if start > now or stop <= oldest:
				# este sa nevysielalo alebo uz je mimo archivu
				self.cp.add_video(_C('grey', title), ev.get('image'), info_labels, download=False, cmd=self.cp.noop)
				continue

			self.cp.add_video(title, ev.get('image'), info_labels, cmd=self.get_archive_stream,
			                  channel_id=channel_id, start=start, stop=stop,
			                  archive_title='%s - %s' % (channel_name, name))

	def archive_time_blocks(self, channel_id, channel_name, ts_from, ts_to, now,
	                        block=ARCHIVE_BLOCK_SECONDS):
		"""Nahradny vypis archivu po casovych blokoch, ked pre dany den nemame program.

		Zobrazi len bloky, ktore uz prebehli a este su v DVR okne (ARCHIVE_HOURS)."""
		oldest = now - ARCHIVE_HOURS * 3600
		start = (int(ts_from) // block) * block
		count = 0

		while start < ts_to:
			stop = start + block
			if stop > now:
				break
			if stop > oldest:
				title = '%s - %s' % (self.cp.timestamp_to_str(start),
				                     self.cp.timestamp_to_str(stop))
				info_labels = {'title': '%s %s' % (channel_name, title), 'duration': block}
				self.cp.add_video(title, None, info_labels, cmd=self.get_archive_stream,
				                  channel_id=channel_id, start=start, stop=stop,
				                  archive_title='%s %s' % (channel_name, title))
				count += 1
			start = stop

		if not count:
			self.cp.show_info(self.cp._("No TV guide for this day yet. The addon collects "
			                            "the guide daily, so previous days will appear soon."))

	def get_archive_stream(self, channel_id, start, archive_title, stop=None):
		return self.cp.play_asset(channel_id, archive_title, live=False, begin=start, end=stop)

	# --- skratka do archivu z EPG prijimaca / z userbouquetu ---------------------------------------

	def _archive_channel(self, channel_key):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None
		channel = self.cp.channels_by_key.get(channel_key)
		return channel if channel and channel.dvr and not channel.no_access else None

	def get_archive_hours(self, channel_id):
		return ARCHIVE_HOURS if self._archive_channel(channel_id) else None

	def get_channel_id_from_path(self, path):
		if not path.startswith(('playlive/', 'playlivets/')):
			return None
		path = path.split('/', 1)[1]
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index'):
			path = path[:-6]
		try:
			channel_key = base64.b64decode(path.encode('utf-8')).decode('utf-8')
		except Exception:
			return None
		return channel_key if self._archive_channel(channel_key) else None

	def get_channel_id_from_sref(self, sref):
		try:
			self.cp.load_channel_list()
		except Exception:
			return None
		name = channel_name_normalise(sref.getServiceName())
		for channel in self.cp.channels:
			if channel.dvr and not channel.no_access and channel_name_normalise(channel.name) == name:
				return channel.key
		return None

	def get_archive_event(self, channel_id, event_start, event_end=None):
		channel = self._archive_channel(channel_id)
		if not channel:
			return
		title = channel.name
		try:
			for ev in self.cp.api.get_epg_range(channel_id, event_start, event_start + 1):
				if ev['start'] <= event_start < (ev['end'] or event_start + 1):
					title = '%s - %s' % (channel.name, ev['title'] or '')
					event_end = event_end or ev['end'] or None
					break
		except Exception:
			pass
		return self.cp.play_asset(channel_id, title, live=False, begin=event_start, end=event_end)


# ##################################################################################################################

class CanalplusModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Information and settings"))

	def root(self, section=None):
		self.cp.add_dir(self._('Account'), cmd=self.list_account)
		self.cp.add_video(self._("Sign out (pair again)"), cmd=self.sign_out)
		self.cp.add_video(self._("Check playback"), cmd=self.check_playback)

	def sign_out(self):
		self.cp.sign_out()
		self.cp.show_info(self._("Signed out. Please exit the addon and open it again to pair."))

	def list_account(self):
		try:
			self.cp.load_channel_list()
		except Exception as e:
			self.cp.show_error(self._("Failed to load account: %s") % error_text(e))
			return

		info = self.cp.api.account_summary()
		if info.get('zone'):
			self.cp.add_video(self._("Zone: %s") % info['zone'], None, {}, download=False, cmd=self.cp.noop)
		self.cp.add_video(self._("Number of channels: %d") % len(self.cp.channels),
		                  None, {}, download=False, cmd=self.cp.noop)
		if self.cp.widevine_wanted():
			drm = self._("Widevine, SD (this receiver has Python 2.7)")
		else:
			drm = self._("PlayReady, Full HD")
		self.cp.add_video(self._("Playback: %s") % drm, None, {}, download=False, cmd=self.cp.noop)

	def check_playback(self):
		try:
			self.cp.load_channel_list()
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		channel = None
		for ch in self.cp.channels:
			if not ch.no_access:
				channel = ch
				break
		if not channel:
			self.cp.show_error(self._("No playable channel found."))
			return

		try:
			stream = self.cp.get_stream_info(channel.key)
		except Exception as e:
			self.cp.show_error(self._("Playback failed: %s") % error_text(e))
			return

		# kontrola nic neprehrava - Broadpeak relaciu hned zatvorime
		self.cp.api.teardown(stream.get('teardown'))
		self.cp.play_session = {}

		if stream.get('url') and (stream.get('license_url') or self.cp.api.live_token):
			self.cp.show_info(self._("No error occured during playback check. Playback should work."))
		else:
			self.cp.show_error(self._("The server did not return a stream or a license token."))


# ##################################################################################################################

class CanalplusContentProvider(ModuleContentProvider):

	def __init__(self):
		ModuleContentProvider.__init__(self)

		self.log_info('Canal+ %s (build %d)' % (ADDON_VERSION, ADDON_BUILD))

		# prihlasenie je ulozene v data_dir (Solocoo), nie v nastaveniach
		self.login_settings_names = ()
		self.login_optional_settings_names = ('brand',)

		self.needs_pairing = False
		self.api = CanalplusApi(self)
		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None

		# callbacky prave prehravanej Broadpeak relacie (keepalive/teardown)
		self.play_session = {}

		self.bxeg = CanalplusBouquetXmlEpgGenerator(self)

		self.archive_module = CanalplusModuleArchive(self)

		self.modules = [
			CanalplusModuleLiveTV(self),
			self.archive_module,
			CanalplusModuleExtra(self),
		]

		# po zmene filtra predplatneho sa zoznam kanalov nacita znova hned, nie az po vyprsani pamate
		self.add_setting_change_notifier(['only_subscribed'], self.subscription_filter_changed)

	# ##############################################################################################################

	def subscription_filter_changed(self, name, value):
		self.channels_next_load_time = 0

		# katalog ma len okno okolo aktualneho casu - program si priebezne ukladame,
		# aby mal archiv nazvy relacii aj pre minule dni
		try:
			self.bgservice.run_in_loop('loop(epg)', (int(time()) % 1800) + 5400, self.collect_epg)
		except Exception:
			pass

	# ##############################################################################################################
	# prihlasenie

	def login(self, silent):
		brand = self.get_setting('brand') or 'cpsvk'
		user_key_id = (self.get_setting('user_key_id') or '').strip()
		if not user_key_id:
			user_key_id = new_user_key_id()
			self.set_setting('user_key_id', user_key_id)

		self.api.setup(brand, user_key_id)

		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None

		# bez sparovania sa v menu ponukne prihlasenie kodom
		if not self.api.solocoo.is_paired():
			self.needs_pairing = True
			return True

		self.needs_pairing = False
		try:
			self.api.ensure_pass_token(force=True)
		except CanalplusSessionError as e:
			self.log_info('Saved sign-in is no longer valid: %s' % error_text(e))
			self.needs_pairing = True
			return True
		except Exception as e:
			self.log_error('Login error: %s' % error_text(e))
			self.login_error(self._("Sign-in failed: %s") % error_text(e))
			return False

		return True

	def root(self):
		if self.needs_pairing:
			self.add_video(self._("Sign in with a code (pairing)"), cmd=self.start_pairing)
			return
		for module in self.modules:
			module.add()

	def start_pairing(self):
		"""Prihlasenie kodom cez connect.canalplus.com - plati pre program aj prehravanie."""
		try:
			code, url = self.api.solocoo.request_pairing()
		except Exception as e:
			self.log_error('Pairing error: %s' % error_text(e))
			self.show_error(self._("Could not get a pairing code: %s") % error_text(e))
			return

		sso = None
		msg = self._("Sign in with a code:\n\n"
		             "1) On your phone/PC open %s\n"
		             "2) Sign in and enter this code:\n\n        %s\n\n"
		             "Waiting for confirmation... (press Back to cancel)") % (url, code)
		interval = max(3, self.api.solocoo.pairing_interval())
		for i in range(80):
			if self.show_info(msg, noexit=True, timeout=interval) == False:
				self.log_info('Pairing canceled by user')
				return
			try:
				sso = self.api.solocoo.poll_pairing_once(code)
			except Exception as e:
				self.log_debug('Pairing check failed: %s' % error_text(e))
				sso = None
			if sso:
				break

		if sso:
			self.needs_pairing = False
			try:
				self.api.ensure_pass_token(force=True)
			except Exception as e:
				self.log_error('Sign-in after pairing failed: %s' % error_text(e))
			self.show_info(self._("Paired. Please exit the addon and open it again."))
		else:
			self.show_error(self._("Pairing was not confirmed in time. Please try again."))

	def forget_session(self):
		self.api.pass_token = None
		self.api.pass_token_time = 0

	def sign_out(self):
		self.forget_session()
		try:
			self.api.solocoo.logout()
		except Exception:
			pass
		self.needs_pairing = True

	def session_expired(self):
		self.forget_session()
		self.login_error(self._("Your sign-in has expired."))

	def noop(self):
		return

	def logged_in(self):
		return self.api.logged_in()

	# ##############################################################################################################
	# kanaly

	def timestamp_to_str(self, timestamp, format_str='%H:%M'):
		if not timestamp:
			return ''
		return strftime(format_str, localtime(timestamp))

	def load_channel_list(self, force=False):
		if not force and self.channels and int(time()) < self.channels_next_load_time:
			return

		raw = self.api.channels()
		only_subscribed = bool(self.get_setting('only_subscribed'))

		channels = []
		by_key = {}
		used_ids = set()
		skipped = 0

		for item in raw:
			key = item.get('EpgId')
			name = item.get('Name')
			if not key or not name:
				continue

			# kanal mimo predplatneho (server ho posiela, ale prehrat sa neda) - podla nastavenia vynechat
			if only_subscribed and _flag((item.get('AccessRights') or {}).get('NoAccess')):
				skipped += 1
				continue

			try:
				lcn = int(item.get('Nb') or item.get('NumZap') or 0)
			except Exception:
				lcn = 0

			cid = lcn if lcn and lcn not in used_ids else None
			if cid is None:
				cid = 10000 + len(channels)
			used_ids.add(cid)

			no_access = _flag((item.get('AccessRights') or {}).get('NoAccess'))

			channel = CanalplusChannel(
				key=str(key), cid=cid, name=name,
				picon=logo_url(item.get('LogoUrl')),
				lcn=lcn or None,
				dvr=_flag(item.get('DVR')),
				no_access=no_access,
			)
			channels.append(channel)
			by_key[channel.key] = channel

		channels.sort(key=lambda c: (c.lcn or 99999, c.name))
		self.log_debug('Channels: %d from server, %d usable, %d outside subscription' % (len(raw), len(channels), skipped))

		self.channels = channels
		self.channels_by_key = by_key
		self.channels_next_load_time = int(time()) + CHANNELS_CACHE_SECONDS

		# kontrolny sucet ponuky pre export bouquetu
		self.checksum = md5(('%s|' % ADDON_BUILD + '|'.join(c.key for c in channels)).encode('utf-8')).hexdigest()

	def load_epg(self, channels):
		"""Doplni ku kanalom prave beziaci program (nazov, cas, popis, nahlad)."""
		now = int(time())
		todo = [ch for ch in channels
		        if not ch.epg_name or not ch.epg_stop or ch.epg_stop < now]
		if not todo:
			return

		try:
			epg = self.api.get_epg_now_many([ch.epg_id for ch in todo], now)
		except Exception as e:
			self.log_error('Failed to load the EPG: %s' % error_text(e))
			return

		# popisy prave beziacich relacii zo Solocoo
		now_desc = {}   # epg_id -> popis
		if self.api.solocoo.is_paired():
			try:
				cc_to_epg = {}
				for ch in todo:
					cc_to_epg[self.api.solocoo_cc_id(ch.epg_id)] = str(ch.epg_id)
				now_map = self.api.solocoo.get_schedule_now(list(cc_to_epg.keys()))
				id_by_epg = {}
				for cc, e in now_map.items():
					eid = cc_to_epg.get(cc)
					if eid and e.get('id'):
						id_by_epg[eid] = e['id']
				desc_map = self.api.solocoo.get_descriptions(list(id_by_epg.values()), time_limit=15)
				for eid, aid in id_by_epg.items():
					d = desc_map.get(aid)
					if d:
						now_desc[eid] = d
			except Exception as e:
				self.log_error('Solocoo descriptions failed: %s' % error_text(e))

		for channel in todo:
			ev = epg.get(str(channel.epg_id))
			if not ev:
				continue
			channel.epg_name = ev.get('title') or None
			channel.epg_start = ev.get('start')
			channel.epg_stop = ev.get('end')
			channel.epg_img = ev.get('image')
			d = now_desc.get(str(channel.epg_id))
			if d and not ev.get('desc'):
				ev['desc'] = d
			channel.epg_desc = event_details(ev) or None

	def get_channel_epg(self, channel_key, time_from, time_to):
		"""Program kanala pre bouquet a XML EPG."""
		return self.api.get_epg_range(channel_key, time_from, time_to)

	def collect_epg(self):
		"""Na pozadi stiahne a ulozi program vsetkych kanalov (Solocoo historia + spyro)."""
		try:
			if not self.logged_in():
				return
			self.load_channel_list()
			ids = [ch.epg_id for ch in self.channels if ch.epg_id]
			if not ids:
				return
			try:
				self.api.fetch_solocoo_epg(self.channels)
			except Exception as e:
				self.log_error('Solocoo schedule failed: %s' % error_text(e))
			self.api.get_epg_now_many(ids)
			self.log_debug('EPG collected for %d channels' % len(ids))
		except Exception as e:
			self.log_error('EPG collection failed: %s' % error_text(e))

	# ##############################################################################################################
	# prehravanie

	def stream_headers(self):
		return {
			'User-Agent': USER_AGENT,
			'Origin': 'https://www.canalplus.com',
			'Referer': 'https://www.canalplus.com/',
		}

	def get_dash_info(self, stream_key):
		"""Udaje pre DashHTTPRequestHandler - manifest a licencna konfiguracia."""
		headers = self.stream_headers()
		license_headers = dict(headers)
		license_headers['Content-Type'] = 'application/json'

		if stream_key.get('wv'):
			# zalozna cesta cez Solocoo Widevine (Python 2.7)
			wv_headers = self.api.solocoo.stream_headers()
			wv_license_headers = dict(wv_headers)
			wv_license_headers['Content-Type'] = 'application/octet-stream'
			return {
				'url': stream_key['url'],
				'bandwidth': stream_key.get('bandwidth'),
				'headers': wv_headers,
				'drm': {
					'wv': {
						'license_url': stream_key['wv'],
						'headers': wv_license_headers,
					}
				}
			}

		ctx = stream_key.get('license') or {}

		return {
			'url': stream_key['url'],
			'bandwidth': stream_key.get('bandwidth'),
			'headers': headers,
			'drm': {
				'pr': {
					'license_url': ctx.get('url', ''),
					'headers': license_headers,
					'canalplus': ctx,
				}
			}
		}

	def widevine_wanted(self):
		"""Python 3 = PlayReady (Full HD), Python 2.7 = Widevine cez Solocoo (SD) - rozhoduje sa samo."""
		return is_py2

	def solocoo_asset_for(self, channel_key, begin=None, end=None):
		"""Solocoo id na prehratie: zivy kanal = cc<EpgId>, archiv = id relacie z programu."""
		if begin is None:
			return self.api.solocoo_cc_id(channel_key)
		t_from = int(begin)
		t_to = int(end) if end else t_from + 1
		events = self.api.get_epg_range(channel_key, t_from, t_to) or []
		best = None
		for ev in events:
			if not ev.get('id'):
				continue
			if best is None or abs(int(ev['start']) - t_from) < abs(int(best['start']) - t_from):
				best = ev
		if best is None:
			# program este nie je stiahnuty - skus ho dotiahnut a hladaj znova
			try:
				self.api.fetch_solocoo_channel(channel_key, t_from - 3600, t_to + 3600, with_desc=False)
			except Exception:
				self.log_exception()
			for ev in self.api.get_epg_range(channel_key, t_from, t_to) or []:
				if ev.get('id') and (best is None or abs(int(ev['start']) - t_from) < abs(int(best['start']) - t_from)):
					best = ev
		return best['id'] if best else None

	def get_stream_info_wv(self, channel_key, begin=None, end=None):
		"""Manifest a Widevine licencia zo Solocoo (bez keepalive relacie)."""
		if not self.api.solocoo.is_paired():
			raise CanalplusSessionError('Not paired')
		asset_id = self.solocoo_asset_for(channel_key, begin, end)
		if not asset_id:
			raise Exception('No programme found for this time in the archive')
		stream = self.api.solocoo.get_stream(asset_id)
		if stream.get('url'):
			self.log_info('Widevine stream from: %s' % (stream['url'].split('/')[2] if stream['url'].count('/') >= 2 else '?'))
		self.play_session = {}
		return stream

	def get_stream_info(self, channel_key, begin=None, end=None):
		"""Vrati adresu manifestu a licencny kontext - pouziva aj HTTP handler pre bouquet."""
		channel = self.channels_by_key.get(channel_key)
		if not channel:
			self.load_channel_list()
			channel = self.channels_by_key.get(channel_key)
		if not channel:
			raise Exception('Unknown channel')

		if self.widevine_wanted():
			return self.get_stream_info_wv(channel_key, begin=begin, end=end)

		raw = None
		for item in self.api.channels():
			if str(item.get('EpgId')) == channel_key:
				raw = item
				break
		if not raw:
			raise Exception('Channel not in current list')

		stream = self.api.get_stream(raw, live=(begin is None), begin=begin, end=end)

		mpd_url = stream.get('url') or ''
		if mpd_url:
			self.log_info('Stream from: %s' % (mpd_url.split('/')[2] if mpd_url.count('/') >= 2 else '?'))

		# zapamataj si callbacky relacie - stats() ich pouzije na keepalive a teardown
		self.play_session = {
			'keepalive': stream.get('keepalive'),
			'teardown': stream.get('teardown'),
		}

		return stream

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""Udrziava Broadpeak reláciu nažive a po skončení ju korektne zatvorí.

		Bez keepalive CDN reláciu po čase ukončí (stream spadne), bez teardown
		ostávajú relácie otvorené a pri prepínaní kanálov sa hromadia."""
		try:
			session = self.play_session or {}
			if action in ('play', 'watching', 'unpause', 'seek'):
				self.api.keepalive(session.get('keepalive'))
			elif action == 'end':
				self.api.teardown(session.get('teardown'))
				self.play_session = {}
		except Exception:
			self.log_exception()

	def get_live_stream(self, channel_key, channel_name=''):
		return self.play_asset(channel_key, channel_name, live=True)

	def play_asset(self, channel_key, stream_title='', live=True, begin=None, end=None):
		if not channel_key:
			self.show_error(self._("Missing item identifier."))
			return

		try:
			stream = self.get_stream_info(channel_key, begin=begin, end=end)
		except CanalplusSessionError:
			self.session_expired()
			return
		except Exception as e:
			msg = error_text(e)
			self.log_error('Stream error: %s' % msg)
			low = msg.lower()
			if 'noaccess' in low or 'subscri' in low or 'entitle' in low:
				self.show_error(self._("This channel is not part of your subscription."))
			elif 'geo' in low:
				self.show_error(self._("The broadcast is not available from this network (geoblocking)."))
			else:
				self.show_error(self._("Playback failed: %s") % msg)
			return

		mpd_url = stream.get('url') or ''
		if not mpd_url:
			self.show_error(self._("No stream URL received from server."))
			return

		if stream.get('license_url'):
			# Widevine cesta (Solocoo)
			if not self.resolve_dash_streams_wv(stream, stream_title or stream.get('title') or '', live):
				self.show_error(self._("Failed to load the DASH stream."))
			return

		if not self.api.live_token:
			self.show_error(self._("No license token received. The stream cannot be played."))
			return

		if not self.resolve_dash_streams(stream, stream_title or stream.get('title') or '', live):
			self.show_error(self._("Failed to load the DASH stream."))

	def player_settings(self):
		"""DASH s DRM vie prehrat len exteplayer3 - vynutime ho bez ohladu na predvoleny prehravac
		v archivCZSK (gstplayer da len cierny obraz)."""
		return {'stype': 5002}

	def limit_streams(self, streams):
		try:
			max_height = int(self.get_setting('max_resolution') or 0)
		except Exception:
			max_height = 0
		if not max_height or not streams:
			return streams
		allowed = [s for s in streams if s.get('height') and int(s['height']) <= max_height]
		if not allowed:
			allowed = [min(streams, key=lambda x: int(x.get('height') or 0) or 99999)]
		return allowed

	def resolve_streams_for_channel(self, manifest_url):
		streams = self.get_dash_streams(manifest_url, headers=self.stream_headers(),
		                                max_bitrate=self.get_setting('max_bitrate'))
		return self.limit_streams(streams)

	def resolve_dash_streams_wv(self, stream, title, live):
		"""Widevine (Solocoo): s klucmi L3 dava Canal+ realne SD bez ohladu na stopu v manifeste,
		preto sa ponukne jedna polozka (najvyssia povolena stopa) oznacena ako SD."""
		streams = self.get_dash_streams(stream['url'], headers=self.api.solocoo.stream_headers(),
		                                max_bitrate=self.get_setting('max_bitrate'))
		streams = self.limit_streams(streams)
		if not streams:
			return False
		s = max(streams, key=lambda x: int(x.get('bandwidth') or 0))
		stream_key = {
			'url': s['playlist_url'],
			'bandwidth': s['bandwidth'],
			'wv': stream.get('license_url') or '',
		}
		url = stream_key_to_dash_url(self.http_endpoint, stream_key)
		info_labels = {
			'bandwidth': int(s['bandwidth']),
			'quality': 'SD (Widevine)',
		}
		self.add_play(title, url, info_labels=info_labels, settings=self.player_settings(), live=live)
		return True

	def resolve_dash_streams(self, stream, title, live):
		streams = self.resolve_streams_for_channel(stream['url'])
		if not streams:
			return False

		web = self.api.web_url()
		license_ctx = stream.get('license') or {}

		for s in streams:
			stream_key = {
				'url': s['playlist_url'],
				'bandwidth': s['bandwidth'],
				'license': license_ctx,
				'web': web,
			}
			url = stream_key_to_dash_url(self.http_endpoint, stream_key)

			info_labels = {
				'bandwidth': int(s['bandwidth']),
				'quality': s['height'] + 'p' if s.get('height') else 'max',
			}
			self.add_play(title, url, info_labels=info_labels, settings=self.player_settings(), live=live)

		return True
