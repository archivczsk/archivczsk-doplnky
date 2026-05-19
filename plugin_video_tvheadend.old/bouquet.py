# -*- coding: utf-8 -*-

import hashlib
import os
import re
import time

# -------------------------------------------------
# Python 2/3 compatibility
# -------------------------------------------------
# FIX 0.57.0 (skyjet PR #22 review): threading je vždy dostupný v
# Py2.7+ aj Py3 (stdlib module); fallback try/except odstránený.
import threading

# io.open() je dostupné v Py2 aj Py3 a podporuje encoding=
import io as _io

def _open_utf8(path, mode='r'):
	"""Otvorí súbor s UTF-8 kódovaním kompatibilne s Py2 aj Py3."""
	return _io.open(path, mode, encoding='utf-8', errors='ignore')

# FIX 0.57.0 (skyjet PR #22 review): basestring (Py2 builtin) nahradený
# tools_archivczsk.six.string_types — vracia (str,) v Py3, (str, bytes) v Py2.
from tools_archivczsk.six import string_types as basestring

# FIX 0.57.0 (skyjet PR #22 review): urllib Py2/Py3 fallback nahradený
# centrálnym tools_archivczsk.compat helper-om. Predtým bol 8-riadkový
# try/except nested fallback (urllib.parse → urlparse → no-op lambda)
# vrátane mŕtveho `urllib_parse = None` ošetrenia. Compat helper rieši
# Py2/Py3 import path interne, módy a knižnice sú guaranteed dostupné.
from tools_archivczsk.compat import urlparse as _url_urlparse

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, BouquetGenerator
# FIX 0.57.0: framework volá download_picons cez parent triedu
# (BouquetGeneratorTemplate.download_picons), nie cez child (BouquetGenerator).
# Pre monkey-patch loggingu musíme patch-núť parent.
from tools_archivczsk.generator.bouquet import BouquetGeneratorTemplate

# FIX 0.57.0 (skyjet PR #22 review): tools.archivczsk je guaranteed dependency
# (addon.xml require version 3.4+) — žiadny fallback netreba.
from tools_archivczsk.string_utils import strip_accents

try:
	from .tvheadend import _picon_ready_event as _tvh_picon_ready
except Exception:
	_tvh_picon_ready = None

# FIX 0.48j: import persistent data path helper
from ._paths import data_path


# FIX 0.48j: _PICON_LOG odstránené — logy idú cez print() do archivCZSK.log
# (sledovať cez `grep '\[plugin.tvheadend' /tmp/archivCZSK.log`)

# FIX 0.58.2 (skyjet PR #22 review #11 follow-up): `_EPG_INJECT_STAMP`
# odstránený spolu s celou custom inject_tvh_epg_into_enigma() cestou.
# Framework `BouquetXmlEpgGenerator` trigger-uje EPG inject automaticky.

# FIX 0.48b: module-level debounce stamp pre download_picons_from_bouquets.
# Framework BouquetXmlEpgGenerator volá _post() pri každom channel_type
# (tv + radio = 2×). Bez debouncu sa logika kopírovania a fallback
# downloadov spúšťa 2× po sebe → log spam + zbytočná záťaž.
# FIX 0.50beta: locky inicializované eagerly pri importe modulu namiesto
# lazy v rámci funkcie. Lazy init `if X is None: X = Lock()` mal race
# condition keď 2 thready prešli kontrolou predtým ako jeden vytvoril
# inštanciu — druhý prepísal lock cudzou inštanciou a debouncing stratil
# atomicitu. Eager init je O(1) pri starte a deterministické.
_DOWNLOAD_PICONS_LOCK = threading.Lock()

# FIX 0.48c: debounce pre celý refresh_userbouquet_start._post() callback.
# Predtým debouncoval len picon copy step (#FIX 0.48b), ale celý _post()
# obsahuje aj _fix_radio_bouquet_filenames() + eDVBDB.reloadBouquets() +
# OpenWebif HTTP request — tie bežali 2× za sebou (raz pre TV, raz pre Radio
# channel_type). Aplikujeme rovnakú debounce logiku ako pri picon copy,
# 30 sekundové okno je dostatočné na pokrytie tv+radio framework cyklu.
# FIX 0.50beta: eager init (rovnaký dôvod ako _DOWNLOAD_PICONS_LOCK).
_POST_CALLBACK_LOCK = threading.Lock()
_LAST_POST_CALLBACK_TS = [0]
_POST_CALLBACK_DEBOUNCE_SEC = 30


# FIX 0.57.0: framework BouquetGeneratorTemplate.download_picons() volá
# s.get(url) s URL formátu http://user:pass@host/path — Python requests
# IGNORUJE inline credentials a nepošle HTTP Basic Auth header (security
# policy z CVE-2023-32681). Výsledok: TVH vracia HTTP 401 pre VŠETKY
# requests a framework len silently skip-ne file. Tento monkey-patch
# nahradí framework download_picons vlastnou implementáciou ktorá
# explicitne aplikuje auth (Basic alebo Digest auto-detect cez probe).
#
# Patch je idempotent (sentinel flag na triede) a aplikuje sa raz pri
# prvom _TvhBouquetGenerator init-e per session.
def _install_picon_download_patch(cp):
	"""Monkey-patch framework BouquetGeneratorTemplate.download_picons.

	Args:
	    cp: TvheadendContentProvider instance (pre logging cez cp.log_info/log_debug).
	"""
	BGT = BouquetGeneratorTemplate
	if getattr(BGT, '_tvh_dp_patched', False):
		return

	_original_dp = BGT.download_picons
	_cp_ref = cp

	def _patched_dp(picons):
		try:
			cnt = len(picons) if picons else 0
			_cp_ref.log_debug('[Tvheadend.debug] download_picons thread started: '
				'%d picons' % cnt)
		except Exception:
			pass

		picon_dir = '/usr/share/enigma2/picon'
		try:
			if not os.path.exists(picon_dir):
				os.mkdir(picon_dir)
		except Exception as _e:
			_cp_ref.log_error('[Tvheadend.picons] mkdir %s failed: %s' % (picon_dir, _e))
			return

		try:
			import requests as _req
			from requests.auth import HTTPDigestAuth as _DigestAuth
		except ImportError as _ie:
			_cp_ref.log_error('[Tvheadend.picons] requests library missing: %s' % _ie)
			return

		# Extract credentials z URL netloc + clean URLs (bez user:pass)
		user = None
		pwd = None
		cleaned = {}
		for _ref, _url in picons.items():
			if not _url:
				continue
			try:
				_p = _url_urlparse(_url)
				if _p.username:
					user = _p.username
					pwd = _p.password or ''
					_netloc = _p.hostname
					if _p.port:
						_netloc += ':' + str(_p.port)
					from tools_archivczsk.compat import urlunparse as _urlunparse_compat
					_clean_url = _urlunparse_compat((
						_p.scheme, _netloc, _p.path,
						_p.params, _p.query, _p.fragment))
					cleaned[_ref] = _clean_url
				else:
					cleaned[_ref] = _url
			except Exception:
				cleaned[_ref] = _url

		# Auto-detect Basic vs Digest auth cez probe na prvý URL
		sess = _req.Session()
		auth_mode = 'none'
		if user is not None and cleaned:
			_probe_url = next(iter(cleaned.values()))
			try:
				_pr = sess.get(_probe_url, auth=(user, pwd), timeout=8)
				if _pr.status_code == 200:
					sess.auth = (user, pwd)
					auth_mode = 'basic'
				elif _pr.status_code == 401:
					_pr2 = sess.get(_probe_url, auth=_DigestAuth(user, pwd), timeout=8)
					if _pr2.status_code == 200:
						sess.auth = _DigestAuth(user, pwd)
						auth_mode = 'digest'
					else:
						auth_mode = 'failed_both_basic_and_digest'
				else:
					auth_mode = 'failed_status_%d' % _pr.status_code
			except Exception as _pe:
				auth_mode = 'probe_error_%s' % _pe

		_cp_ref.log_info('[Tvheadend.picons] auth probe: %s' % auth_mode)

		# Skutočný download loop
		written = 0
		errs_404 = 0
		errs_other = 0
		exceptions = 0
		skipped_exists = 0
		try:
			for _ref, _url in cleaned.items():
				if not _url:
					continue
				_fileout = picon_dir + '/' + _ref + '.png'
				if os.path.exists(_fileout):
					skipped_exists += 1
					continue
				try:
					_r = sess.get(_url, timeout=10)
					if _r.status_code == 200 and _r.content:
						_ct = _r.headers.get('content-type', '').lower()
						if _ct.startswith('image/') or len(_r.content) > 100:
							with open(_fileout, 'wb') as _f:
								_f.write(_r.content)
							written += 1
						else:
							errs_other += 1
					elif _r.status_code == 404:
						errs_404 += 1
					else:
						errs_other += 1
				except Exception:
					exceptions += 1
		except Exception as _le:
			_cp_ref.log_error('[Tvheadend.picons] download loop crashed: %s' % _le)

		_cp_ref.log_info('[Tvheadend.picons] download done: '
			'written=%d, skipped_exists=%d, errs_404=%d, '
			'errs_other=%d, exceptions=%d' %
			(written, skipped_exists, errs_404, errs_other, exceptions))

	BGT.download_picons = staticmethod(_patched_dp)
	BGT._tvh_dp_patched = True


class _TvhBouquetGenerator(BouquetGenerator):
	"""
	Tenký override framework BouquetGenerator — aplikuje user-overridden
	bouquet display name z plugin settings (userbouquet_custom_name_tv /
	userbouquet_custom_name_radio). Všetka common init logika (prefix,
	profile suffix, namespace, TID, ONID, atď.) dedeí z framework parent.

	FIX 0.57.0 (skyjet PR #22 review #3): predtým bola tu plne vlastná
	CustomBouquetGenerator(BouquetGeneratorTemplate) trieda (~65 LoC)
	ktorá duplikovala celý parent init. Skyjet's feedback: "stačí self.name =
	... v BouquetXmlEpgGenerator triede". Zachytené ako 20-LoC minimal
	subclass-with-override.
	"""

	def __init__(self, bxeg, channel_type=None):
		# Framework parent vytvorí prefix, default name, namespace, TID, atď.
		BouquetGenerator.__init__(self, bxeg, channel_type)

		# FIX 0.58.0: Safeguard pre legacy player_name="3" (DMM) a "4" (DVB
		# OE>=2.5) z predchádzajúcich verzií. Settings.xml v 0.58.0 zobrazuje
		# len Default/gstplayer/exteplayer3:
		#   - DVB chain (stype=1) nefunguje cez TVH plugin proxy URL — native
		#     eDVBService expect MPEG-TS s validnými DVB tabuľkami, ale proxy
		#     stream re-buffers a mení timing → playback zlyhá s "no PIDs".
		#   - DMM player (stype=8193) je špecifický pre Dreambox boxy a nie je
		#     bežný v cieľovej user base TVH plugin-u (väčšina má Vu+/Octagon/
		#     Zgemma s OpenATV/OpenPLi a štandardný GST stack).
		#
		# Stored value mohla zostať z minulosti — force-reset na "0" (Default).
		if str(self.player_name) in ('3', '4'):
			try:
				bxeg.cp.log_info('[Tvheadend.bouquet] player_name="%s" nie je '
				                 'podporovaný v 0.58.0+ — force-reset na '
				                 'Default (4097)' % self.player_name)
			except Exception:
				pass
			self.player_name = '0'

		# FIX 0.57.0: install picon download patch (idempotent, runs once)
		try:
			_install_picon_download_patch(bxeg.cp)
		except Exception as _e:
			try:
				bxeg.cp.log_error('[Tvheadend.picons] patch install failed: %s' % _e)
			except Exception:
				pass

		# Custom name override z user settings — nahradí framework default
		# "bxeg.name + ' ' + channel_type" ak je nastavený.
		try:
			if channel_type == 'radio':
				custom = (bxeg.get_setting('userbouquet_custom_name_radio') or '').strip()
			else:
				custom = (bxeg.get_setting('userbouquet_custom_name_tv') or '').strip()
		except Exception:
			custom = ''

		if custom:
			# Zachovať profile suffix ktorý framework appendol cez
			# bxeg.get_profile_info() — pre multi-profile setups.
			profile_info = None
			try:
				profile_info = bxeg.get_profile_info()
			except Exception:
				pass
			if profile_info is not None:
				self.name = custom + ' - ' + profile_info[1]
			else:
				self.name = custom


class TvheadendBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	"""
	Tvheadend -> ArchivCZSK bouquet + xmlepg + enigmaepg generator
	"""

	def __init__(self, content_provider):
		self.cp = content_provider

		# POZOR: enable_userbouquet_cam u teba neexistuje -> spôsobovalo AttributeError
		self.bouquet_settings_names = (
			'enable_userbouquet',
			'enable_userbouquet_radio',
			# 'enable_userbouquet_cam',   # ❌ removed due to AttributeError
			'userbouquet_categories',

			# ✅ NEW settings (custom bouquet display names)
			'userbouquet_custom_name_tv',
			'userbouquet_custom_name_radio',

			# FIX 0.58.2 (skyjet PR #22 review #11 follow-up):
			# `tvh_epg_inject_interval` + `enigmaepg_days` nahradené
			# framework default setting names `enable_xmlepg` + `xmlepg_days`.
			# Custom direct-injection cesta odstránená — framework
			# `EnigmaEpgGenerator` to robí natívne cez `get_xmlepg_channels()`
			# + `get_epg()` (existujú v tomto súbore).
			'enable_xmlepg',
			'xmlepg_days',

			'enable_picons',
			'player_name',
			'bouquet_refresh_interval',
		)

		# ✅ support TV + RADIO
		BouquetXmlEpgGenerator.__init__(self, content_provider, channel_types=('tv', 'radio'))

		# ✅ override bouquet generator — minimal subclass over framework
		# default (viď _TvhBouquetGenerator), aplikuje len custom display name
		self.bouquet_generator = _TvhBouquetGenerator

		self._channels = []
		self._key_to_url = {}
		self._epg_cache = None
		self._epg_cache_ts = 0  # FIX 0.48c: TTL stamp pre _epg_cache
		self._tagmap = None

		# ✅ TAG ORDER CACHE (sorting categories according to TVH "index")
		self._taguuid_to_order = None        # uuid -> index
		self._tagnorm_to_order = None        # normalized-name -> index

	# -------------------------------------------------
	# logging helper
	# -------------------------------------------------

	def _log(self, msg):
		"""FIX 0.57.0: log cez framework cp.log_info() ktorý ide priamo
		do /tmp/archivCZSK.log. Predtým bol print() a potom
		logging.getLogger() — ani jeden nešiel do archivCZSK.log
		(archivCZSK framework zachytí len vlastný logger).
		Sleduj cez: `grep '\\[Tvheadend' /tmp/archivCZSK.log`
		"""
		try:
			self.cp.log_info('[Tvheadend.bouquet] ' + str(msg))
		except Exception:
			pass

	# -------------------------------------------------
	# Settings helpers
	# -------------------------------------------------

	def _to_bool(self, v, default=False):
		if isinstance(v, bool):
			return v
		if v is None:
			return default
		try:
			s = str(v).strip().lower()
		except Exception:
			return default
		if s in ("1", "true", "yes", "on", "enabled"):
			return True
		if s in ("0", "false", "no", "off", "disabled"):
			return False
		return default

	def _to_int(self, v, default=0):
		try:
			return int(v)
		except Exception:
			return default

	def get_setting(self, name):
		# FIX 0.48e: XML EPG cesta bola odstránená — pre staré inštalácie
		# kde užívateľ má enable_xmlepg=true vrátime False, aby framework
		# neprodukoval XML súbory.
		if name == 'enable_xmlepg':
			return False
		if name == 'xmlepg_dir':
			return ''
		if name == 'xmlepg_days':
			return 0

		# FIX 0.57.0 (skyjet PR #22 review): odstránený priame čítanie
		# /etc/enigma2/settings cez vlastný parser — framework
		# self.cp.get_setting() vracia už sparsovanú a type-correct hodnotu
		# (bool/int/str podľa addon.xml settings.xml type=). Wrappujeme len
		# kvôli legacy bool/int coerce-ovaniu nad str výsledkom z framework-u
		# pre starý formát settingov.
		try:
			val = self.cp.get_setting(name)
		except Exception:
			val = None

		if name in (
			"enable_userbouquet", "enable_userbouquet_radio",
			"userbouquet_categories",
			"enable_picons",
			# FIX 0.58.2: enable_xmlepg bool toggle (framework default name)
			"enable_xmlepg",
		):
			return self._to_bool(val, default=False)

		# FIX 0.58.2: framework default name `xmlepg_days` (predtým `enigmaepg_days`)
		if name == "xmlepg_days":
			return self._to_int(val, default=7)

		# text settings
		if name in ("xmlepg_dir", "player_name",
		            "userbouquet_custom_name_tv", "userbouquet_custom_name_radio"):
			return val if val is not None and val != "" else ""

		return val

	# -------------------------------------------------

	def logged_in(self):
		return True

	def translate(self, txt):
		try:
			return self.cp._(txt)
		except Exception:
			return txt

	# -------------------------------------------------
	# ✅ TVH TAGS -> RADIO DETECT (+ categories)
	# -------------------------------------------------

	def _normalize_tag_name(self, s):
		s = (s or "").strip().lower()
		s = strip_accents(s) if s else ''   # rádio -> radio
		s = re.sub(r"\s+", " ", s)
		return s

	def _safe_int(self, v, default=10**6):
		try:
			return int(v)
		except Exception:
			return default

	def _get_tag_uuid_to_name(self):
		# ✅ if cache ready, return
		if self._tagmap is not None and self._taguuid_to_order is not None and self._tagnorm_to_order is not None:
			return self._tagmap

		self._tagmap = {}
		self._taguuid_to_order = {}
		self._tagnorm_to_order = {}

		try:
			tags = self.cp.tvh.get_tags() or []
		except Exception:
			tags = []

		# TVH returns "index" (important for ordering)
		for t in tags:
			u = (t.get('uuid') or '').strip()
			n = (t.get('name') or t.get('val') or '').strip()
			if not u or not n:
				continue

			self._tagmap[u] = n

			idx = self._safe_int(t.get('index', None), default=10**6)
			if idx == 10**6:
				idx = self._safe_int(t.get('order', None), default=10**6)

			if (u not in self._taguuid_to_order) or (idx < self._taguuid_to_order.get(u, 10**6)):
				self._taguuid_to_order[u] = idx

			nn = self._normalize_tag_name(n)
			if nn:
				if (nn not in self._tagnorm_to_order) or (idx < self._tagnorm_to_order.get(nn, 10**6)):
					self._tagnorm_to_order[nn] = idx

		return self._tagmap

	def _is_radio_by_tags(self, tag_uuids):
		radio_tokens = (
			"radio", "radia", "radia fm", "radio fm",
			"radiostanice", "radiostanica",
			"rádio", "rádia", "rádiá",
		)

		tagmap = self._get_tag_uuid_to_name()
		for tu in (tag_uuids or []):
			n = self._normalize_tag_name(tagmap.get(tu) or "")
			if not n:
				continue

			for tok in radio_tokens:
				tokn = self._normalize_tag_name(tok)
				if n == tokn or tokn in n:
					return True

		return False

	def _get_channel_categories(self, ch):
		out = []
		tagmap = self._get_tag_uuid_to_name()
		for tu in (ch.get("tags") or []):
			n = (tagmap.get(tu) or "").strip()
			if n:
				out.append(n)
		return out

	def _category_order(self, cat_name):
		"""
		Category order:
		- based on TVH "index" (api/channeltag/grid)
		- "Ostatné" always last
		- fallback: big number
		"""
		if not cat_name:
			return 10**6

		nn = self._normalize_tag_name(cat_name)
		if nn in ("ostatne", "ostatné"):
			return 10**9

		self._get_tag_uuid_to_name()
		if self._tagnorm_to_order and nn in self._tagnorm_to_order:
			return self._safe_int(self._tagnorm_to_order.get(nn), default=10**6)

		return 10**6

	# -------------------------------------------------
	# CHANNELS
	# -------------------------------------------------

	def get_channels_checksum(self, channel_type):
		if channel_type not in ('tv', 'radio'):
			return '0'

		if not self._channels:
			self.load_channel_list()

		want_radio = (channel_type == 'radio')

		h = hashlib.md5()
		for ch in self._channels:
			if bool(ch.get('is_radio')) != want_radio:
				continue
			s = "%s|%s|%s|%s|%s" % (
				ch.get('uuid', ''),
				ch.get('name', ''),
				ch.get('id', 0),
				ch.get('icon_public_url') or '',
				'R' if ch.get('is_radio') else 'T'
			)
			h.update(s.encode('utf-8', errors='ignore'))
		return h.hexdigest()

	def load_channel_list(self):
		self._channels = []
		self._key_to_url = {}
		self._epg_cache = None
		self._epg_cache_ts = 0   # FIX 0.48c: reset TTL stamp pri reload kanálov
		self._tagmap = None

		# reset tag-order cache
		self._taguuid_to_order = None
		self._tagnorm_to_order = None

		try:
			channels = self.cp.tvh.get_channels() or []
		except Exception:
			channels = []

		channels = [c for c in channels if c.get('enabled', True)]

		def _num(x):
			try:
				return int(x.get('number') or 0)
			except Exception:
				return 0

		channels = sorted(channels, key=_num)

		fallback_id = 10000
		for ch in channels:
			uuid = ch.get('uuid') or ''
			if not uuid:
				continue

			name = ch.get('name') or uuid
			number = _num(ch)

			service_uuid = ''
			try:
				services = ch.get('services') or []
				if services:
					service_uuid = services[0]
			except Exception:
				service_uuid = ''

			try:
				url = self.cp.tvh.make_live_stream_url(
					channel_uuid=uuid,
					service_uuid=(service_uuid or None)
				)
			except Exception:
				continue

			icon_public_url = (ch.get('icon_public_url') or '').strip()

			try:
				is_radio = self._is_radio_by_tags(ch.get('tags') or [])
			except Exception:
				is_radio = False

			ch_id = number if number > 0 else fallback_id
			if number <= 0:
				fallback_id += 1

			item = {
				'uuid': uuid,
				'name': name,
				'id': int(ch_id),
				'key': uuid,
				'adult': False,
				# FIX 0.57.0 (skyjet PR #22 review #11-#14): picon: URL
				# namiesto None. Framework BouquetGeneratorTemplate.download_picons()
				# si stiahne picons priamo z TVH HTTP API endpoint-u, sám
				# vyrieši SRP-based naming, PNG conversion (vrátane SVG/JPEG),
				# dedup, skip-existing. Custom plugin picon flow odstránený
				# (~700 LoC). Pre channels bez icon_public_url vráti
				# make_icon_http_url None — framework skip-uje.
				'picon': self.cp.tvh.make_icon_http_url(icon_public_url),
				'icon_public_url': icon_public_url,
				'is_radio': bool(is_radio),
				'tags': ch.get('tags') or [],
			}

			self._channels.append(item)
			self._key_to_url[uuid] = url

		# FIX 0.57.0 debug: koľko channels skončilo s picon URL nastavenou
		try:
			with_picon = sum(1 for c in self._channels if c.get('picon'))
			without_picon = len(self._channels) - with_picon
			sample = next((c['picon'] for c in self._channels if c.get('picon')), None)
			self._log("load_channel_list: %d channels total, %d with picon URL, %d without. "
			          "Sample picon URL: %r" % (len(self._channels), with_picon,
			                                     without_picon, sample))
		except Exception:
			pass

		return True

	def get_url_by_channel_key(self, channel_key):
		return self._key_to_url.get(channel_key, '')

	def get_bouquet_channels(self, channel_type=None):
		if not self._channels:
			self.load_channel_list()

		want_radio = (channel_type == 'radio')
		use_categories = self.get_setting("userbouquet_categories")

		# FIX: if separate radio bouquet is enabled, TV bouquet must not contain radio channels
		separate_radio = self.get_setting("enable_userbouquet_radio")

		if not use_categories:
			for ch in self._channels:
				if (channel_type == 'tv') and separate_radio and bool(ch.get('is_radio')):
					continue

				if bool(ch.get('is_radio')) != want_radio:
					continue
				yield {
					'name': ch['name'],
					'id': ch['id'],
					'key': ch['key'],
					'adult': False,
					'picon': ch.get('picon'),
					'is_separator': False,
				}
			return

		categories = {}
		for ch in self._channels:
			if (channel_type == 'tv') and separate_radio and bool(ch.get('is_radio')):
				continue

			if bool(ch.get('is_radio')) != want_radio:
				continue

			cats = self._get_channel_categories(ch)
			if not cats:
				cats = ["Ostatné"]

			for c in cats:
				categories.setdefault(c, []).append(ch)

		for cat in sorted(
			categories.keys(),
			key=lambda x: (
				self._category_order(x),
				strip_accents(x).lower() if x else ''
			)
		):
			yield {
				'name': "--- %s ---" % cat,
				'is_separator': True,
			}
			for ch in categories[cat]:
				yield {
					'name': ch['name'],
					'id': ch['id'],
					'key': ch['key'],
					'adult': False,
					'picon': ch.get('picon'),
					'is_separator': False,
				}

	def get_xmlepg_channels(self):
		if not self._channels:
			self.load_channel_list()

		for ch in self._channels:
			id_content = (ch['uuid'] or '').replace('-', '_')
			yield {
				'name': ch['name'],
				'id': ch['id'],
				'id_content': id_content,
				'key': ch['uuid'],
			}



	# FIX 0.58.2: 6 EPG-injection helpers odstránených spolu s custom
	# inject_tvh_epg_into_enigma() path:
	# - _find_bouquet_files
	# - _is_tvheadend_bouquet_file
	# - _looks_like_uuid
	# - _b64_to_text
	# - _extract_url_from_service_ref
	# - _extract_channel_uuid
	# Framework EnigmaEpgGenerator extrahuje service ref priamo z
	# channel['id'] cez build_service_ref formulu — žiadne parsing
	# bouquet súborov.

	def _read_lines(self, path):
		try:
			if not os.path.isfile(path):
				return []
			with _open_utf8(path, "r") as f:
				return f.read().splitlines()
		except Exception:
			return []

	def _write_lines(self, path, lines):
		try:
			with _open_utf8(path, "w") as f:
				f.write("\n".join(lines) + "\n")
			return True
		except Exception:
			return False

	def _ensure_bouquets_radio_has(self, bouquet_filename):
		base = "/etc/enigma2"
		br = os.path.join(base, "bouquets.radio")

		line_need = '#SERVICE 1:7:2:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % bouquet_filename

		lines = self._read_lines(br)
		if not lines:
			lines = [
				'#NAME Bouquets (Radio)',
				line_need,
			]
			if self._write_lines(br, lines):
				self._log("Created bouquets.radio + added %s" % bouquet_filename)
			return

		for ln in lines:
			if bouquet_filename in ln and "FROM BOUQUET" in ln:
				return

		out = []
		inserted = False
		for ln in lines:
			out.append(ln)
			if (not inserted) and ln.startswith("#NAME"):
				out.append(line_need)
				inserted = True
		if not inserted:
			out.append(line_need)

		if self._write_lines(br, out):
			self._log("Patched bouquets.radio: added %s" % bouquet_filename)

	def _remove_from_bouquets_tv(self, bouquet_filenames):
		base = "/etc/enigma2"
		bt = os.path.join(base, "bouquets.tv")

		lines = self._read_lines(bt)
		if not lines:
			return

		def _hit(line):
			for b in bouquet_filenames:
				if ('FROM BOUQUET "%s"' % b) in line:
					return True
			return False

		new_lines = [ln for ln in lines if not _hit(ln)]
		if new_lines != lines:
			if self._write_lines(bt, new_lines):
				self._log("Removed radio bouquet(s) from bouquets.tv: %s" % (", ".join(bouquet_filenames)))

	def _fix_radio_bouquet_filenames(self):
		if not self.get_setting("enable_userbouquet_radio"):
			return

		base = "/etc/enigma2"
		try:
			files = os.listdir(base)
		except Exception:
			return

		remove_from_tv = []

		renamed_to = []
		for fn in files:
			lfn = fn.lower()
			if not fn.startswith("userbouquet."):
				continue
			if not fn.endswith(".tv"):
				continue
			if not (("radio" in lfn) or ("radia" in lfn) or ("rádio" in lfn) or ("rádia" in lfn)):
				continue

			src = os.path.join(base, fn)

			dst_fn = fn[:-3] + ".radio"
			dst = os.path.join(base, dst_fn)

			remove_from_tv.append(fn)

			try:
				if os.path.isfile(dst):
					try:
						os.remove(src)
					except Exception:
						pass
					renamed_to.append(dst_fn)
					continue

				os.rename(src, dst)
				renamed_to.append(dst_fn)
				self._log("Radio bouquet rename: %s -> %s" % (fn, dst_fn))
			except Exception:
				continue

		br = os.path.join(base, "bouquets.radio")
		lines = self._read_lines(br)
		if lines:
			new_lines = []
			changed = False
			for line in lines:
				m = re.search(r'FROM BOUQUET \"(userbouquet\.[^\"]+)\.tv\"', line)
				if m:
					base_name = m.group(1)
					new_line = line.replace(base_name + ".tv", base_name + ".radio")
					if new_line != line:
						changed = True
						line = new_line
				new_lines.append(line)
			if changed and self._write_lines(br, new_lines):
				self._log("Patched bouquets.radio references (.tv -> .radio)")

		for fn in list(remove_from_tv):
			remove_from_tv.append(fn[:-3] + ".radio")
		self._remove_from_bouquets_tv(sorted(set(remove_from_tv)))

		target = "userbouquet.tvheadend_radio.radio"
		if os.path.isfile(os.path.join(base, target)):
			self._ensure_bouquets_radio_has(target)
			return

		try:
			for fn in os.listdir(base):
				lfn = fn.lower()
				if not fn.startswith("userbouquet.") or not fn.endswith(".radio"):
					continue
				if "tvheadend" in lfn and ("radio" in lfn or "radia" in lfn or "rádio" in lfn or "rádia" in lfn):
					self._ensure_bouquets_radio_has(fn)
					return
		except Exception:
			pass

		if renamed_to:
			self._ensure_bouquets_radio_has(renamed_to[0])

	# -------------------------------------------------
	# FIX 0.58.2 (skyjet PR #22 review #11 follow-up):
	# Custom EPG injection cesta (~175 LoC) odstránená — framework
	# `BouquetXmlEpgGenerator.refresh_xmlepg()` automaticky volá
	# `EnigmaEpgGenerator.run()` → iteruje cez `get_xmlepg_channels()`
	# + `get_epg()` → `eEPGCache.importEvent(serviceref, epg_data)`.
	#
	# Predtým existovali paralelne 2 EPG injection cesty:
	# 1. Framework (auto-triggered cez refresh_xmlepg) — VŽDY fungovala
	#    keď `enable_xmlepg=True` a plugin má `get_xmlepg_channels()`
	#    + `get_epg()` (existujú v tomto súbore)
	# 2. Custom `inject_tvh_epg_into_enigma()` — bulk XMLTV download +
	#    parse + custom service ref extraction z userbouquet súborov
	#
	# Cesta 2 bola **redundantná** a navyše broken (po skyjet review
	# #11 rename `m3u_epg_injector.py` → `epg_injector.py` zlyhával
	# pri upgrade users s legacy filename). Plus celý code path:
	# - `inject_tvh_epg_into_enigma()` method
	# - `_build_uuid_to_short_sref_from_bouquets()` + helpers
	#   (`_extract_channel_uuid`, `_b64_to_text`, `_looks_like_uuid`,
	#   `_extract_url_from_service_ref`)
	# - `epg_injector.py` modul (separate file)
	# - `provider.py:_maybe_auto_inject_epg()` + `_EPG_INJECT_STAMP`
	# - `provider.py:action_tvh_inject_epg()` menu item
	# - Setting `tvh_epg_inject_interval` (nahradené `enable_xmlepg`)
	#
	# Existujúce framework-aligned methods `get_xmlepg_channels()`
	# a `get_epg(channel, fromts, tots)` ostávajú a sú teraz hlavnou
	# cestou. -------------------------------------------------


	def refresh_userbouquet_start(self, *args, **kwargs):
		try:
			ret = BouquetXmlEpgGenerator.refresh_userbouquet_start(self, *args, **kwargs)
		except Exception:
			ret = None

		def _post():
			# FIX 0.48c: debounce celého _post() callbacku.
			# Framework volá refresh_userbouquet_start raz pre channel_type='tv'
			# a raz pre 'radio', takže _post() je v rade 2× ~1s od seba.
			# Bez debouncu by sa _fix_radio_bouquet_filenames(),
			# download_picons() (interne má svoj vlastný debounce) a 2×
			# eDVBDB.reloadBouquets() + OpenWebif request spustili dvojnásobne.
			# FIX 0.50beta: lock je teraz module-level eager init, nie lazy
			now_ts = int(time.time())
			if _POST_CALLBACK_LOCK is not None:
				with _POST_CALLBACK_LOCK:
					since = now_ts - _LAST_POST_CALLBACK_TS[0]
					if since < _POST_CALLBACK_DEBOUNCE_SEC:
						self._log("refresh_userbouquet_start._post called %ds "
						          "after last run (debounce %ds) — skipping "
						          "duplicate" % (since, _POST_CALLBACK_DEBOUNCE_SEC))
						return
					_LAST_POST_CALLBACK_TS[0] = now_ts

			try:
				self._fix_radio_bouquet_filenames()
			except Exception:
				pass
			# Počkaj kým picon worker dobeží (max 120 sekúnd)
			# Používame threading.Event namiesto sleep slučky – efektívnejšie
			# FIX 0.48c: event sa teraz správne čistí na začiatku worker-a
			# (predtým bol set forever a wait() sa vracal okamžite).
			try:
				if _tvh_picon_ready is not None:
					_tvh_picon_ready.wait(timeout=120)
				else:
					# fallback na stamp kontrolu
					# FIX 0.48j: persistent data dir (rovnaký path ako tvheadend._PICON_STAMP)
					_picon_stamp_path = data_path("tvh_picon.stamp")
					for _ in range(120):
						if os.path.isfile(_picon_stamp_path):
							break
						time.sleep(1)
			except Exception:
				pass
			# FIX 0.57.0 (skyjet PR #22 review #14): explicit self.download_picons()
			# call removed — BouquetGeneratorTemplate.run() automaticky volá
			# download_picons() v background thread keď enable_picons=True.

			# FIX 0.48: po dokončení refresh-u prinúť Enigma2 znovu načítať
			# bouquet súbory z disku — bez tohto user musel reštartovať Enigma2
			# aby uvidel nové kanály v live TV. M3UBouquetWriter to už robí
			# (eDVBDB + OpenWebif), pridávame ekvivalent aj sem.
			try:
				from enigma import eDVBDB
				db = eDVBDB.getInstance()
				db.reloadBouquets()
				self._log("eDVBDB.reloadBouquets() OK after TVH bouquet refresh")
				try:
					db.reloadServicelist()
				except Exception:
					pass
			except ImportError:
				# bežíme mimo Enigma2 (testy) — preskoč
				pass
			except Exception as e:
				self._log("eDVBDB.reloadBouquets() failed: %s" % e)

			# OpenWebif fallback — funguje aj keď enigma cache caching skin
			try:
				try:
					from urllib.request import urlopen as _urlopen
				except ImportError:
					from urllib2 import urlopen as _urlopen
				resp = _urlopen('http://127.0.0.1/web/servicelistreload?mode=2',
				                timeout=5)
				try:
					resp.read()
				finally:
					try:
						resp.close()
					except Exception:
						pass
				self._log("OpenWebif servicelistreload OK")
			except Exception:
				# OpenWebif nemusí byť spustený — to je v poriadku
				pass

			# FIX 0.58.2 (skyjet PR #22 review #11 follow-up): custom EPG
			# injection v _post() callback-u odstránená. Framework
			# `BouquetXmlEpgGenerator.bouquet_settings_changed` po
			# `refresh_bouquet` automaticky volá `refresh_xmlepg` ktorá
			# spustí `EnigmaEpgGenerator.run()` → iteruje cez
			# `get_xmlepg_channels()` + `get_epg()` → priame importEvent()
			# volania. Tým sa odstránila duplicita.

		try:
			t = threading.Timer(1.0, _post)
			t.daemon = True
			t.start()
		except Exception:
			pass

		return ret

	# -------------------------------------------------
	# FAST EPG
	# -------------------------------------------------

	def _pick(self, val):
		if not val:
			return ""
		if isinstance(val, basestring):
			return val
		if isinstance(val, dict):
			for k in ('slk', 'slo', 'ces', 'cze', 'eng'):
				if k in val and val[k]:
					return val[k]
			for v in val.values():
				if v:
					return v
		return ""

	# FIX 0.48c: TTL pre EPG cache.
	# Predtým: _epg_cache sa naplnil pri prvom volaní get_epg() a držal sa
	# navždy. Pri preload="yes" plugine s 24/7 boxom to znamenalo že po
	# týždni mal generátor stále EPG zo dňa štartu E2. Teraz: 30 min TTL,
	# po expirácii sa nasledujúce volanie naparuje fresh data.
	_EPG_CACHE_TTL_SEC = 1800  # 30 min

	def get_epg(self, channel, fromts, tots):
		ch_uuid = channel.get('key') or ''
		if not ch_uuid:
			return

		fromts_i = int(fromts)
		tots_i = int(tots)

		# FIX 0.48c: TTL check pre _epg_cache
		now_ts = int(time.time())
		cache_ts = getattr(self, '_epg_cache_ts', 0)
		if (self._epg_cache is not None and cache_ts > 0
		        and (now_ts - cache_ts) >= self._EPG_CACHE_TTL_SEC):
			self._epg_cache = None
			try:
				self._log("EPG cache expired (age %ds > TTL %ds), reloading" %
				          (now_ts - cache_ts, self._EPG_CACHE_TTL_SEC))
			except Exception:
				pass

		if self._epg_cache is None:
			self._epg_cache = {}
			self._epg_cache_ts = now_ts
			try:
				data = self.cp.tvh.api_get(
					"api/epg/events/grid",
					{"limit": 999999, "sort": "start", "dir": "ASC"}
				) or {}
				entries = data.get("entries") or []
			except Exception:
				entries = []

			for ev in entries:
				try:
					cuuid = ev.get("channelUuid")
					if not cuuid:
						continue
					start = int(ev.get("start") or 0)
					stop = int(ev.get("stop") or 0)
					if not start or not stop:
						continue
					if stop <= fromts_i or start >= tots_i:
						continue
					self._epg_cache.setdefault(cuuid, []).append(ev)
				except Exception:
					continue

		for ev in self._epg_cache.get(ch_uuid, []):
			try:
				start = int(ev.get("start") or 0)
				stop = int(ev.get("stop") or 0)

				title = (self._pick(ev.get("title")) or '').strip()
				desc = (self._pick(ev.get("description")) or self._pick(ev.get("summary")) or '').strip()

				if not title:
					continue

				yield {"start": start, "end": stop, "title": title, "desc": desc}
			except Exception:
				continue
