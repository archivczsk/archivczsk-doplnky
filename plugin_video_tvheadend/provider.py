# -*- coding: utf-8 -*-
"""
TvheadendContentProvider – hlavný provider pre ArchivCZSK.

Kompatibilita: Python 2.7 + Python 3.x
Primárne testované na OpenATV / Python 3.

Implementuje:
  - login() metódu (nie login v root/konstruktore)
  - login_settings_names / login_optional_settings_names
  - _maybe_cleanup_poster_cache() volaná len z login() (nie z __init__)
  - export bouquet/EPG cez BouquetXmlEpgGenerator s TTL stampom
  - Python 2 kompatibilný fallback s užívateľsky zrozumiteľnou chybou
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import sys
import time
import base64
import unicodedata
from datetime import datetime

from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException

# Prenositeľné formátovanie textu (_I, _B, _C) – povinné pre "oficiálne" doplnky
try:
	from tools_archivczsk.string_utils import _I, _C, _B
except Exception:
	def _I(s):
		return str(s) if s is not None else ''
	def _B(s):
		return str(s) if s is not None else ''
	def _C(color, s):
		return str(s) if s is not None else ''

from .tvheadend import Tvheadend

try:
	from .bouquet import TvheadendBouquetXmlEpgGenerator
except Exception:
	TvheadendBouquetXmlEpgGenerator = None


# --------------------------------------------------------------------------
# Konštanty
# --------------------------------------------------------------------------
_POSTER_CACHE_DIR   = "/tmp/archivczsk_poster"
_POSTER_CLEAN_STAMP = "/tmp/archivczsk_tvheadend_poster_clean.stamp"
_POSTER_TTL_DAYS    = 7

# Export bouquet/EPG sa nespúšťa pri každom silent login-e (napr. z HTTP handlera)
_EXPORT_TRIGGER_STAMP   = "/tmp/archivczsk_tvheadend_exports_trigger.stamp"
_EXPORT_TRIGGER_TTL_SEC = 1800  # 30 min

# DVR entries cache – používame tools_archivczsk ExpiringLRUCache
try:
	from tools_archivczsk.cache import ExpiringLRUCache as _ExpiringLRUCache
	_DVR_CACHE = _ExpiringLRUCache(1, default_timeout=60)
except Exception:
	_DVR_CACHE = None
_DVR_CACHE_TS = 0
_DVR_CACHE_TTL = 60

# Bouquet auto-refresh stamp
_BOUQUET_REFRESH_STAMP = "/tmp/archivczsk_tvheadend_bouquet_refresh.stamp"


# --------------------------------------------------------------------------
# Pomocné funkcie
# --------------------------------------------------------------------------

def _maybe_cleanup_poster_cache():
	"""Čistí starý poster cache – max raz za _POSTER_TTL_DAYS dní."""
	try:
		if not os.path.isdir(_POSTER_CACHE_DIR):
			return
		now = int(time.time())
		ttl = int(_POSTER_TTL_DAYS) * 24 * 3600
		last = 0
		try:
			last = int(os.path.getmtime(_POSTER_CLEAN_STAMP))
		except Exception:
			pass
		if last and (now - last) < ttl:
			return
		for fn in os.listdir(_POSTER_CACHE_DIR):
			fp = os.path.join(_POSTER_CACHE_DIR, fn)
			try:
				if os.path.isfile(fp) and (now - int(os.path.getmtime(fp))) >= ttl:
					os.remove(fp)
			except Exception:
				pass
		try:
			with open(_POSTER_CLEAN_STAMP, 'w') as f:
				f.write(str(now))
		except Exception:
			pass
	except Exception:
		pass


def _get_dvr_finished_cached(tvh):
	"""Vráti DVR nahrávky z cache (max 60 sekúnd staré)."""
	if _DVR_CACHE is not None:
		cached = _DVR_CACHE.get('dvr')
		if cached is not None:
			return cached
	result = tvh.get_dvr_finished()
	if _DVR_CACHE is not None:
		_DVR_CACHE.put('dvr', result)
	return result


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


# --------------------------------------------------------------------------
# Provider
# --------------------------------------------------------------------------

class TvheadendContentProvider(CommonContentProvider):

	# Tieto atribúty zabezpečia automatické volanie login() pri zmene nastavení
	login_settings_names = (
		'host', 'port', 'use_https',
		'username', 'password',
		'http_auth_mode', 'use_ticket_url',
		'profile', 'loading_timeout',
	)
	login_optional_settings_names = tuple()

	def __init__(self, *args, **kwargs):
		CommonContentProvider.__init__(self, *args, **kwargs)
		self.tvh = Tvheadend(self)
		self._bouquet_gen = None

	# ------------------------------------------------------------------
	# login() – volá sa automaticky pri štarte aj po zmene nastavení
	# ------------------------------------------------------------------

	def login(self, silent=False):
		# Python 2 – upozorní užívateľa zmysluplnou správou namiesto pádu
		if sys.version_info[0] < 3:
			msg = (
				"Tvheadend addon vyžaduje Python 3.x.\n"
				"Tvoje image používa Python 2.7 – doplnok nemôže bežať."
			)
			if silent:
				return False
			raise AddonErrorException(msg)

		# Vyčistenie poster cache (max raz za týždeň) – tu, nie v __init__
		_maybe_cleanup_poster_cache()

		if not self.tvh.is_configured():
			if silent:
				return False
			raise AddonErrorException(
				self._('Please fill in the addon settings first: host, username and password.')
			)

		try:
			self.tvh.check_login()
		except Exception:
			if silent:
				return False
			raise AddonErrorException(
				self._('Tvheadend login failed. Check username/password and account permissions.')
			)

		# Lazy inicializácia generátora bouquetu
		if self._bouquet_gen is None and TvheadendBouquetXmlEpgGenerator is not None:
			try:
				self._bouquet_gen = TvheadendBouquetXmlEpgGenerator(self)
			except Exception:
				self._bouquet_gen = None

		# Spustiť picon download na pozadí (non-blocking)
		try:
			self.tvh.init_picons_async()
		except Exception:
			pass

		# Export bouquet/EPG na pozadí s TTL ochranou
		if self._bouquet_gen is not None:
			self._maybe_trigger_exports(silent=bool(silent))

		# Auto-refresh bouquetu podľa nastaveného intervalu
		self._maybe_auto_refresh_bouquet()

		return True

	def _check_login_silent(self):
		try:
			return bool(self.login(silent=True))
		except Exception:
			return False

	def _maybe_auto_refresh_bouquet(self):
		"""Automaticky refreshne bouquet ak uplynul nastavený interval."""
		if self._bouquet_gen is None:
			return
		try:
			interval = int(self.get_setting('bouquet_refresh_interval') or 0)
			if interval <= 0:
				return
			now = int(time.time())
			last = 0
			try:
				last = int(os.path.getmtime(_BOUQUET_REFRESH_STAMP))
			except Exception:
				pass
			if last and (now - last) < interval:
				return
			# Zapisat stamp pred refreshom
			try:
				with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
					f.write(str(now))
			except Exception:
				return
			self._bouquet_gen.refresh_userbouquet_start()
		except Exception:
			pass

	def _maybe_trigger_exports(self, silent=False):
		"""
		Spustí refresh bouquet + EPG na pozadí.
		Pri silent login-e (HTTP handler) sa spustí max raz za _EXPORT_TRIGGER_TTL_SEC.
		"""
		if self._bouquet_gen is None:
			return

		if silent:
			try:
				now  = int(time.time())
				last = 0
				try:
					last = int(os.path.getmtime(_EXPORT_TRIGGER_STAMP))
				except Exception:
					pass
				if last and (now - last) < int(_EXPORT_TRIGGER_TTL_SEC):
					return
				# Zapíš stamp pred štartom – ochrana proti burst requestom
				try:
					with open(_EXPORT_TRIGGER_STAMP, 'w') as f:
						f.write(str(now))
				except Exception:
					return
			except Exception:
				return

		# *_start() len naplánujú tasky – neblokujú GUI
		try:
			self._bouquet_gen.refresh_userbouquet_start()
		except Exception:
			pass
		try:
			self._bouquet_gen.refresh_xmlepg_start()
		except Exception:
			pass

	# ------------------------------------------------------------------
	# Pomocné
	# ------------------------------------------------------------------

	def _player_settings(self):
		return {
			'user-agent': 'VLC/3.0.20 LibVLC/3.0.20',
			'extra-headers': {}
		}

	# ------------------------------------------------------------------
	# root() – hlavná ponuka
	# ------------------------------------------------------------------

	def root(self):
		self.add_dir(self._("Live TV"),  cmd=self.live_root,        info_labels={'title': self._("Live TV")})
		self.add_dir(self._("Archive"),  cmd=self.archive_channels, info_labels={'title': self._("Archive")})

	# ------------------------------------------------------------------
	# LIVE
	# ------------------------------------------------------------------

	def _live_info_labels(self, channel_title, event):
		info = {'title': channel_title}
		if not event:
			return info
		epgt = event.get('title') or ''
		sub  = event.get('subtitle') or event.get('summary') or ''
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
			pass

		for ch in channels:
			ch_uuid      = ch.get('uuid') or ''
			channel_name = ch.get('name') or ch_uuid
			if not ch_uuid:
				continue

			service_uuid = ''
			try:
				services = ch.get('services') or []
				if services:
					service_uuid = services[0]
			except Exception:
				pass

			icon  = self.tvh.make_icon_url(ch.get('icon_public_url') or None)
			event = epgnow.get(ch_uuid) if isinstance(epgnow, dict) else None
			info  = self._live_info_labels(channel_name, event)

			# EPG titul vedľa názvu kanála (štýl iVysilani)
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
		if not channel_title and service_uuid:
			try:
				ch_name = self.tvh.get_channel_name_by_service_uuid(service_uuid)
				if ch_name:
					play_title = ch_name
			except Exception:
				pass

		self.add_play(
			play_title, url,
			info_labels={'title': play_title},
			settings=self._player_settings(),
			live=True,
			download=False
		)

	# ------------------------------------------------------------------
	# ARCHÍV (DVR)
	# ------------------------------------------------------------------

	def _dvr_info_labels(self, label_title, entry):
		info = {'title': label_title}
		if not isinstance(entry, dict):
			return info

		def _pick(v):
			if not v:
				return ''
			if isinstance(v, dict):
				for k in ('slk', 'slo', 'cze', 'ces', 'eng'):
					if k in v and v[k]:
						return str(v[k]).strip()
				for _val in v.values():
					if _val:
						return str(_val).strip()
				return ''
			return str(v).strip()

		main = _pick(entry.get('disp_title') or entry.get('title'))
		sub  = _pick(entry.get('disp_subtitle') or entry.get('disp_summary') or entry.get('subtitle') or entry.get('summary'))
		desc = _pick(entry.get('disp_description') or entry.get('description'))

		plot_parts = [p for p in (main, sub, desc) if p]
		if plot_parts:
			info['plot'] = "\n".join(plot_parts)

		try:
			dur = entry.get('duration')
			if dur:
				info['duration'] = int(dur)
			else:
				start = int(entry.get('start_real') or entry.get('start') or 0)
				stop  = int(entry.get('stop_real')  or entry.get('stop')  or 0)
				if start and stop and stop > start:
					info['duration'] = stop - start
		except Exception:
			pass

		return info

	def archive_channels(self):
		if not self._check_login_silent():
			return

		try:
			entries  = _get_dvr_finished_cached(self.tvh)
			channels = self.tvh.get_channels()
		except Exception:
			return

		ch_info = {}
		for ch in channels:
			cid = ch.get('uuid') or ''
			if not cid:
				continue
			ch_info[cid] = {
				'name':   ch.get('name') or cid,
				'number': int(ch.get('number') or 0),
				'icon':   self.tvh.make_icon_url(ch.get('icon_public_url') or None)
			}

		# Aplikuj limity z nastavení
		try:
			days_limit = int(self.get_setting('archive_days_limit') or 0)
			if days_limit > 0:
				cutoff = time.time() - days_limit * 86400
				entries = [e for e in entries if _ts(e) >= cutoff]
		except Exception:
			pass
		try:
			dvr_limit = int(self.get_setting('dvr_limit') or 0)
			if dvr_limit > 0:
				entries = entries[:dvr_limit]
		except Exception:
			pass

		counts = {}
		days   = {}
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
			info    = ch_info.get(cid) or {}
			name    = info.get('name') or cid
			num     = info.get('number', 0)
			icon    = info.get('icon')
			day_cnt = len(days.get(cid) or set())
			items.append((num, _norm_name(name), cid, name, icon, cnt, day_cnt))

		items.sort(key=lambda x: (x[0] if x[0] > 0 else 999999, x[1]))

		for num, _, cid, name, icon, cnt, day_cnt in items:
			label = '%s (%d)' % (name, num) if num > 0 else name
			if day_cnt > 0:
				label = '%s - %d %s' % (label, day_cnt, self._('days'))
			self.add_dir(
				label, img=icon, info_labels={'title': label},
				cmd=self.archive_dates, channel_id=cid, channel_name=name
			)

	def archive_dates(self, channel_id, channel_name=None):
		if not self._check_login_silent():
			return

		try:
			entries = _get_dvr_finished_cached(self.tvh)
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
			cnt   = len(by_date[d])
			label = '%s (%d)' % (d, cnt)
			self.add_dir(label, info_labels={'title': label}, cmd=self.archive_day, channel_id=channel_id, date=d)

	def archive_day(self, channel_id, date):
		if not self._check_login_silent():
			return

		try:
			entries = _get_dvr_finished_cached(self.tvh)
		except Exception:
			return

		entries = [e for e in entries if (e.get('channel') or '') == channel_id]
		day = [e for e in entries if _ts(e) > 0 and _date_key_from_ts(_ts(e)) == date]
		day.sort(key=_ts, reverse=True)

		for e in day:
			title = e.get('disp_title') or e.get('title') or self._("Recording")
			ts    = _ts(e)
			tstr  = datetime.fromtimestamp(ts).strftime('%H:%M') if ts > 0 else ''
			label = '%s %s' % (tstr, title) if tstr else title
			icon  = self.tvh.make_icon_url(e.get('channel_icon') or None)
			self.add_video(
				label, img=icon, info_labels=self._dvr_info_labels(label, e),
				cmd=self.play_dvr, entry=e, download=False
			)

	def play_dvr(self, entry):
		if not self._check_login_silent():
			return

		url   = self.tvh.make_dvr_url(entry.get('url') or '')
		title = entry.get('disp_title') or entry.get('channelname') or self._("DVR")
		self.add_play(title, url, info_labels={'title': title}, settings=self._player_settings(), live=False, download=True)

	# ------------------------------------------------------------------
	# get_url_by_channel_key – volané z HTTP handlera a bouquet generátora
	# ------------------------------------------------------------------

	def get_url_by_channel_key(self, key):
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
			for ch in self.tvh.get_channels():
				if (ch.get('uuid') or '') == channel_uuid:
					services = ch.get('services') or []
					if services:
						service_uuid = services[0]
					break
		except Exception:
			pass

		return self.tvh.make_live_stream_url(
			channel_uuid=channel_uuid,
			service_uuid=service_uuid,
			channel_title=None
		)
