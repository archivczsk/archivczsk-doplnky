# provider.py
# -*- coding: utf-8 -*-
from datetime import datetime
import unicodedata
import os
import time
import base64
import sys

from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException

# --- ako iVysilani: prenositeľné formátovanie textu ---
try:
	from tools_archivczsk.string_utils import _I, _C, _B
except Exception:
	# fallback aby to nikdy nespadlo (len čistý text)
	def _I(s): return str(s) if s is not None else ''
	def _B(s): return str(s) if s is not None else ''
	def _C(color, s): return str(s) if s is not None else ''

from .tvheadend import Tvheadend

_PY2_ONLY_MSG = "Tvheadend addon requires Python 3.x (your image uses Python 2.7)."

try:
	from .bouquet import TvheadendBouquetXmlEpgGenerator
except Exception:
	TvheadendBouquetXmlEpgGenerator = None


_POSTER_CACHE_DIR = "/tmp/archivczsk_poster"
_POSTER_CLEAN_STAMP = "/tmp/archivczsk_tvheadend_poster_clean.stamp"
_POSTER_TTL_DAYS = 7

# zabrániť spúšťaniu exportov pri každom silent login-e (napr. z http handlera)
_EXPORT_TRIGGER_STAMP = "/tmp/archivczsk_tvheadend_exports_trigger.stamp"
_EXPORT_TRIGGER_TTL_SEC = 1800  # 30 min


def _maybe_cleanup_poster_cache():
	try:
		if not os.path.isdir(_POSTER_CACHE_DIR):
			return

		now = int(time.time())
		ttl = int(_POSTER_TTL_DAYS) * 24 * 3600

		last = 0
		try:
			last = int(os.path.getmtime(_POSTER_CLEAN_STAMP))
		except Exception:
			last = 0

		if last and (now - last) < ttl:
			return

		for fn in os.listdir(_POSTER_CACHE_DIR):
			fp = os.path.join(_POSTER_CACHE_DIR, fn)
			try:
				if not os.path.isfile(fp):
					continue
				age = now - int(os.path.getmtime(fp))
				if age >= ttl:
					os.remove(fp)
			except Exception:
				continue

		try:
			with open(_POSTER_CLEAN_STAMP, "w") as f:
				f.write(str(now))
		except Exception:
			pass
	except Exception:
		pass


def _norm_name(s):
	if not s:
		return ''
	try:
		s = unicodedata.normalize('NFKD', s)
		s = ''.join(c for c in s if not unicodedata.combining(c))
	except Exception:
		pass
	return s.lower()


def _ts(e):
	try:
		return int(e.get('start_real') or e.get('start') or 0)
	except Exception:
		return 0


def _date_key_from_ts(ts):
	return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d')


def _tag_sort_key(tag):
	for k in ('index', 'sort_index', 'sortIndex', 'order', 'num'):
		v = tag.get(k)
		if v is None:
			continue
		try:
			return int(v)
		except Exception:
			pass
	return 999999


class TvheadendContentProvider(CommonContentProvider):

	login_settings_names = (
		'host', 'port', 'use_https',
		'username', 'password',
		'http_auth_mode', 'use_ticket_url',
		'profile', 'loading_timeout',
	)
	login_optional_settings_names = tuple()

	def __init__(self, *args, **kwargs):
		# Python 2.7 compatibility note: this addon is Python3-only
		try:
			if sys.version_info[0] < 3:
				raise AddonErrorException(_PY2_ONLY_MSG)
		except Exception:
			# if sys not available for some reason, ignore
			pass
		CommonContentProvider.__init__(self, *args, **kwargs)
		self.tvh = Tvheadend(self)
		self._bouquet_gen = None

	def login(self, silent=False):
		_maybe_cleanup_poster_cache()

		if not self.tvh.is_configured():
			if silent:
				return False
			raise AddonErrorException(self._('Please fill in the addon settings first: host, username and password.'))

		try:
			self.tvh.check_login()
		except Exception:
			if silent:
				return False
			raise AddonErrorException(self._('Tvheadend login failed. Check username/password and account permissions.'))

		if self._bouquet_gen is None and TvheadendBouquetXmlEpgGenerator is not None:
			try:
				self._bouquet_gen = TvheadendBouquetXmlEpgGenerator(self)
			except Exception:
				self._bouquet_gen = None

		if self._bouquet_gen is not None:
			self._maybe_trigger_exports(silent=bool(silent))

		return True

	def _player_settings(self):
		return {
			'user-agent': 'VLC/3.0.20 LibVLC/3.0.20',
			'extra-headers': {}
		}

	def _check_login_silent(self):
		try:
			return bool(self.login(silent=True))
		except Exception:
			return False

	
	def _maybe_trigger_exports(self, silent=False):
		"""Spustí background refresh bouquet/EPG, ale nie pri každom silent login-e.

		silent login môže byť volaný často (napr. cez http handler), preto použijeme TTL stamp.
		"""
		if self._bouquet_gen is None:
			return

		if silent:
			try:
				now = int(time.time())
				last = 0
				try:
					last = int(os.path.getmtime(_EXPORT_TRIGGER_STAMP))
				except Exception:
					last = 0

				if last and (now - last) < int(_EXPORT_TRIGGER_TTL_SEC):
					return

				# zapíš stamp ešte pred štartom, aby sa to pri burst requestoch nespúšťalo opakovane
				try:
					with open(_EXPORT_TRIGGER_STAMP, "w") as f:
						f.write(str(now))
				except Exception:
					# ak stamp zlyhá, radšej nespúšťať opakovane
					return
			except Exception:
				return

		# samotné *start() len plánujú tasky (neblokujú GUI)
		try:
			self._bouquet_gen.refresh_userbouquet_start()
		except Exception:
			pass
		try:
			self._bouquet_gen.refresh_xmlepg_start()
		except Exception:
			pass

	def root(self):
		# ZLOŽKY NEMENÍME (presne ako si chcel)
		self.add_dir(self._("Live TV"), cmd=self.live_root, info_labels={'title': self._("Live TV")})
		self.add_dir(self._("Archive"), cmd=self.archive_channels, info_labels={'title': self._("Archive")})

	# ---------------- LIVE ----------------

	def _live_info_labels(self, channel_title, event):
		info = {'title': channel_title}
		if not event:
			return info

		epgt = event.get('title') or ''
		sub = event.get('subtitle') or event.get('summary') or ''
		desc = event.get('description') or ''
		plot_parts = [p for p in (epgt, sub, desc) if p]
		if plot_parts:
			info['plot'] = "\n".join(plot_parts)
		try:
			info['duration'] = int(event.get('stop', 0)) - int(event.get('start', 0))
		except Exception:
			pass
		return info

	def live_root(self):
		if not self._check_login_silent():
			return

		self.add_dir(self._("All"), cmd=self.live_channels, cat_id='')

		try:
			tags = self.tvh.get_tags()
		except Exception:
			return

		tags = sorted(tags, key=lambda t: (_tag_sort_key(t), _norm_name(t.get('name') or '')))

		for t in tags:
			name = t.get('name') or ''
			uuid = t.get('uuid') or ''
			if not uuid:
				continue
			self.add_dir(name, cmd=self.live_channels, cat_id=uuid)

	def live_channels(self, cat_id=''):
		if not self._check_login_silent():
			return

		try:
			channels = self.tvh.get_channels_by_tag(cat_id) if cat_id else self.tvh.get_channels()
		except Exception:
			return

		def _num(x):
			try:
				return int(x.get('number') or 0)
			except Exception:
				return 0

		channels = sorted(channels, key=_num)

		epgnow = None
		try:
			epgnow = self.tvh.get_epg_now(limit=5000)
		except Exception:
			epgnow = None

		for ch in channels:
			ch_uuid = ch.get('uuid') or ''
			channel_name = ch.get('name') or ch_uuid
			if not ch_uuid:
				continue

			service_uuid = ''
			try:
				services = ch.get('services') or []
				if services:
					service_uuid = services[0]
			except Exception:
				service_uuid = ''

			icon = self.tvh.make_icon_url(ch.get('icon_public_url') or None)

			event = epgnow.get(ch_uuid) if isinstance(epgnow, dict) else None
			info = self._live_info_labels(channel_name, event)

			# iVysilani štýl EPG
			display_title = channel_name
			try:
				epg_title = (event.get('title') if isinstance(event, dict) else None) or ''
				if isinstance(epg_title, dict):
					epg_title = next(iter(epg_title.values()), '') if epg_title else ''
				epg_title = str(epg_title).strip()
				if epg_title:
					display_title += _I('  (' + epg_title + ')')
			except Exception:
				pass

			self.add_video(
				display_title,
				img=icon,
				info_labels=info,
				cmd=self.play_live,
				channel_uuid=ch_uuid,
				service_uuid=service_uuid,
				channel_title=channel_name,
				download=False
			)

	def play_live(self, channel_uuid, service_uuid='', channel_title=None):
		if not self._check_login_silent():
			return

		url = self.tvh.make_live_stream_url(
			channel_uuid=channel_uuid,
			service_uuid=(service_uuid or None),
			channel_title=(channel_title or '')
		)

		play_title = channel_title or self._("Live stream")
		try:
			if service_uuid and (not channel_title):
				ch_name = self.tvh.get_channel_name_by_service_uuid(service_uuid)
				if ch_name:
					play_title = ch_name
		except Exception:
			pass

		self.add_play(
			play_title,
			url,
			info_labels={'title': play_title},
			settings=self._player_settings(),
			live=True,
			download=False
		)

	def play_live(self, channel_uuid, service_uuid='', channel_title=None):
		if not self._check_login_silent():
			return

		url = self.tvh.make_live_stream_url(
			channel_uuid=channel_uuid,
			service_uuid=(service_uuid or None),
			channel_title=(channel_title or '')
		)

		play_title = channel_title or self._("Live stream")
		try:
			if service_uuid and (not channel_title):
				ch_name = self.tvh.get_channel_name_by_service_uuid(service_uuid)
				if ch_name:
					play_title = ch_name
		except Exception:
			pass

		self.add_play(
			play_title,
			url,
			info_labels={'title': play_title},
			settings=self._player_settings(),
			live=True,
			download=False
		)

	# ---------------- ARCHIVE ----------------

	def _dvr_info_labels(self, label_title, entry):
		info = {'title': label_title}
		if not isinstance(entry, dict):
			return info

		def _pick_text(v):
			if not v:
				return ''
			if isinstance(v, dict):
				for k in ('slk', 'slo', 'cze', 'ces', 'eng'):
					if k in v and v[k]:
						return str(v[k]).strip()
				for _k, _val in v.items():
					if _val:
						return str(_val).strip()
				return ''
			return str(v).strip()

		main = _pick_text(entry.get('disp_title') or entry.get('title'))
		sub = _pick_text(entry.get('disp_subtitle') or entry.get('disp_summary') or entry.get('subtitle') or entry.get('summary'))
		desc = _pick_text(entry.get('disp_description') or entry.get('description'))

		plot_parts = [p for p in (main, sub, desc) if p]
		if plot_parts:
			info['plot'] = "\n".join(plot_parts)

		try:
			dur = entry.get('duration')
			if dur:
				info['duration'] = int(dur)
			else:
				start = int(entry.get('start_real') or entry.get('start') or 0)
				stop = int(entry.get('stop_real') or entry.get('stop') or 0)
				if start and stop and stop > start:
					info['duration'] = stop - start
		except Exception:
			pass

		return info

	def archive_channels(self):
		if not self._check_login_silent():
			return

		try:
			entries = self.tvh.get_dvr_finished()
			channels = self.tvh.get_channels()
		except Exception:
			return

		ch_info = {}
		for ch in channels:
			cid = ch.get('uuid') or ''
			if not cid:
				continue
			ch_info[cid] = {
				'name': ch.get('name') or cid,
				'number': int(ch.get('number') or 0),
				'icon': self.tvh.make_icon_url(ch.get('icon_public_url') or None)
			}

		counts = {}
		days = {}
		for e in entries:
			cid = e.get('channel') or ''
			if not cid:
				continue
			counts[cid] = counts.get(cid, 0) + 1
			ts = _ts(e)
			if ts > 0:
				days.setdefault(cid, set()).add(_date_key_from_ts(ts))

		items = []
		for cid, cnt in counts.items():
			info = ch_info.get(cid) or {}
			name = info.get('name') or cid
			num = info.get('number', 0)
			icon = info.get('icon')
			day_cnt = len(days.get(cid) or set())
			items.append((num, _norm_name(name), cid, name, icon, cnt, day_cnt))

		items.sort(key=lambda x: (x[0] if x[0] > 0 else 999999, x[1]))

		for num, _, cid, name, icon, cnt, day_cnt in items:
			label = '%s (%d)' % (name, num) if num > 0 else name
			if day_cnt > 0:
				label = '%s - %d %s' % (label, day_cnt, self._('days'))
			self.add_dir(label, img=icon, info_labels={'title': label}, cmd=self.archive_dates, channel_id=cid, channel_name=name)

	def archive_dates(self, channel_id, channel_name=None):
		if not self._check_login_silent():
			return

		try:
			entries = self.tvh.get_dvr_finished()
		except Exception:
			return

		entries = [e for e in entries if (e.get('channel') or '') == channel_id]

		by_date = {}
		for e in entries:
			ts = _ts(e)
			if ts <= 0:
				continue
			d = _date_key_from_ts(ts)
			by_date.setdefault(d, []).append(e)

		for d in sorted(by_date.keys(), reverse=True):
			cnt = len(by_date[d])
			label = '%s (%d)' % (d, cnt)
			self.add_dir(label, info_labels={'title': label}, cmd=self.archive_day, channel_id=channel_id, date=d)

	def archive_day(self, channel_id, date):
		if not self._check_login_silent():
			return

		try:
			entries = self.tvh.get_dvr_finished()
		except Exception:
			return

		entries = [e for e in entries if (e.get('channel') or '') == channel_id]

		day = []
		for e in entries:
			ts = _ts(e)
			if ts <= 0:
				continue
			if _date_key_from_ts(ts) == date:
				day.append(e)

		day.sort(key=lambda e: _ts(e), reverse=True)

		for e in day:
			title = e.get('disp_title') or e.get('title') or self._("Recording")

			ts = _ts(e)
			tstr = datetime.fromtimestamp(ts).strftime('%H:%M') if ts > 0 else ''
			label = '%s %s' % (tstr, title) if tstr else title

			icon = self.tvh.make_icon_url(e.get('channel_icon') or None)

			self.add_video(label, img=icon, info_labels=self._dvr_info_labels(label, e), cmd=self.play_dvr, entry=e, download=False)

	def play_dvr(self, entry):
		if not self._check_login_silent():
			return

		entry_url = entry.get('url') or ''
		url = self.tvh.make_dvr_url(entry_url)

		title = entry.get('disp_title') or entry.get('channelname') or self._("DVR")

		self.add_play(title, url, info_labels={'title': title}, settings=self._player_settings(), live=False, download=True)

	# ---------------- USERBOUQUET RESOLVE ----------------

	def get_url_by_channel_key(self, key):
		_maybe_cleanup_poster_cache()
		self.login(silent=True)

		if not key:
			raise AddonErrorException('Missing key')

		try:
			pad = '=' * (-len(key) % 4)
			channel_uuid = base64.b64decode((key + pad).encode('utf-8')).decode('utf-8').strip()
		except Exception as e:
			raise AddonErrorException('Invalid key: %s' % e)

		if not channel_uuid:
			raise AddonErrorException('Invalid key (empty channel uuid)')

		service_uuid = None
		try:
			channels = self.tvh.get_channels()
			for ch in channels:
				if (ch.get('uuid') or '') == channel_uuid:
					services = ch.get('services') or []
					if services:
						service_uuid = services[0]
					break
		except Exception:
			service_uuid = None

		return self.tvh.make_live_stream_url(channel_uuid=channel_uuid, service_uuid=service_uuid, channel_title=None)
