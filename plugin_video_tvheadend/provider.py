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
import io
import json
import time
import gzip
import base64
import unicodedata
from datetime import datetime

try:
	import lzma  # Py3
except ImportError:
	try:
		from backports import lzma
	except ImportError:
		lzma = None

# urllib for Py2/Py3
try:
	from urllib.request import Request, urlopen
except ImportError:
	from urllib2 import Request, urlopen

# XMLTV iterparse (cElementTree faster on Py2)
try:
	from xml.etree.cElementTree import iterparse as _et_iterparse
	from xml.etree.cElementTree import parse as _et_parse
except ImportError:
	from xml.etree.ElementTree import iterparse as _et_iterparse
	from xml.etree.ElementTree import parse as _et_parse

from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException

# FIX 0.57.0 (skyjet PR #22 review): _I/_C/_B sú vždy dostupné v
# tools_archivczsk.string_utils (guaranteed dependency); fallback dead code
# odstránený.
from tools_archivczsk.string_utils import _I, _C, _B

# FIX 0.57.0 (skyjet PR #22 review): tools.archivczsk je explicit dependency
# v addon.xml (version 3.4+) — strip_accents je vždy dostupný, žiadny fallback
# netreba. Predtým bola tu duplicitná implementácia cez unicodedata.normalize
# pre prípad chýbajúceho framework helpera, čo nikdy nemôže nastať.
from tools_archivczsk.string_utils import strip_accents

from .tvheadend import Tvheadend

try:
	from .bouquet import TvheadendBouquetXmlEpgGenerator
except Exception:
	TvheadendBouquetXmlEpgGenerator = None

# FIX 0.57.0 (skyjet PR #22 review #10/#11): M3U fíčúra extrahovaná
# do samostatného doplnku plugin.video.e2m3u2bouquet.


# --------------------------------------------------------------------------
# Konštanty
# --------------------------------------------------------------------------
# FIX 0.48j: stamp súbory sa ukladajú do persistent data dir-u namiesto /tmp,
# aby prežili reboot E2 (predtým sa všetky TTL gates pri reboot-e zresetli).
# Cache picons ostáva v /tmp lebo je regenerovateľná a tmpfs je rýchle.
from ._paths import data_path, get_data_dir

# FIX 0.48: predtým ukazoval na /tmp/archivczsk_poster (cache iného doplnku);
# plugin reálne píše svoje obrázky do /tmp/archivczsk_tvheadend_img, takže
# cleanup roky nič nemazal a /tmp na boxoch s nonstop behom donekonečna rástol.
# FIX 0.48j: cache obrázkov ostáva v /tmp (regenerovateľné dáta).
_POSTER_CACHE_DIR   = "/tmp/archivczsk_tvheadend_img"
_POSTER_CLEAN_STAMP = data_path("tvh_poster_clean.stamp")
_POSTER_TTL_DAYS    = 7

# Export bouquet/EPG sa nespúšťa pri každom silent login-e (napr. z HTTP handlera)
_EXPORT_TRIGGER_STAMP   = data_path("tvh_exports_trigger.stamp")
_EXPORT_TRIGGER_TTL_SEC = 1800  # 30 min

# DVR entries cache – používame tools_archivczsk ExpiringLRUCache.
# FIX 0.57.0 (skyjet PR #22 review): tools.archivczsk je guaranteed dependency
# (addon.xml require version 3.4+), žiadny fallback netreba.
from tools_archivczsk.cache import ExpiringLRUCache as _ExpiringLRUCache
_DVR_CACHE = _ExpiringLRUCache(1, default_timeout=60)

# Bouquet auto-refresh stamp
_BOUQUET_REFRESH_STAMP = data_path("tvh_bouquet_refresh.stamp")

# FIX 0.58.2: `_EPG_INJECT_STAMP` constant odstránený — framework
# trigger-uje EPG inject automaticky cez bgservice loop.


# FIX 0.52beta: persistent JSON storage pre "posledné sledované" history.
# FIX 0.55beta: rozšírené o resume position + duration tracking (sosáč-style).
# Plugin sleduje ktoré DVR entries užívateľ otvoril, kedy, a kde skončil
# v prehrávaní — aby mohol pokračovať od poslednej pozície a zobraziť
# hviezdičkový marker pri už pozretých nahrávkach v archive listing-u.
#
# Štruktúra (0.55beta forward-compatible upgrade z 0.52beta):
#   {'<entry_uuid>': {
#       'ts':          <epoch>,    # kedy bola entry naposledy otvorená
#       'title':       '...',
#       'subtitle':    '...',
#       'channelname': '...',
#       'start_real':  <epoch>,
#       'position':    <int seconds>,  # 0.55beta: kde sa playback zastavil
#       'duration':    <int seconds>,  # 0.55beta: celková dĺžka
#     }, ...}
#
# Pre entries z 0.52-0.54beta (bez position/duration) sa polia doplnia
# pri prvom save a chýbajúce keys vrátia None — žiadne dáta sa nezahodia,
# žiadny migration step required.
#
# Limit: 50 najnovších entries (FIFO discard). Pri reštarte E2 stav prežíva.
_WATCHED_HISTORY_PATH = data_path("watched_history.json")
_WATCHED_HISTORY_MAX = 50

# 0.55beta thresholds (sosáč-style):
#   _WATCHED_MARK_PCT — pri ≥80 % pozretia zobraz hviezdičku v listingu
#   _WATCHED_AUTO_CLEAR_DEFAULT_PCT — pri ≥95 % auto-clear position (film
#     dohraný, pri ďalšom play sa pustí od začiatku, ale marker zostane)
_WATCHED_MARK_PCT = 80
_WATCHED_AUTO_CLEAR_DEFAULT_PCT = 95

def _load_watched_history():
	"""Načítaj JSON s watched history. Pri chybe vráti prázdny dict."""
	try:
		import json
		if not os.path.isfile(_WATCHED_HISTORY_PATH):
			return {}
		with open(_WATCHED_HISTORY_PATH, 'r') as f:
			data = json.load(f)
		if not isinstance(data, dict):
			return {}
		return data
	except Exception:
		return {}


def _save_watched_history(history):
	"""Atomic write JSON s watched history. Silent fail (TVH plugin nemá
	hlásiť chyby pri tracking-u — to je nepriamy feature)."""
	try:
		import json
		tmp = _WATCHED_HISTORY_PATH + '.tmp'
		with open(tmp, 'w') as f:
			json.dump(history, f, ensure_ascii=False)
		if hasattr(os, 'replace'):
			os.replace(tmp, _WATCHED_HISTORY_PATH)
		else:
			if os.path.exists(_WATCHED_HISTORY_PATH):
				os.remove(_WATCHED_HISTORY_PATH)
			os.rename(tmp, _WATCHED_HISTORY_PATH)
	except Exception:
		pass


def _track_watched(entry):
	"""FIX 0.52beta: zapíš DVR entry do watched history. Volaná z
	play_dvr() pri každom otvorení nahrávky.

	Idempotent — ak entry už v history, len aktualizuje timestamp (a
	zachová existujúce position/duration ak boli zaznamenané pri
	predošlom skončení playback-u). Limit 50 najnovších; staršie sa
	odstránia pri save keď dict prekročí limit.
	"""
	uuid = entry.get('uuid')
	if not uuid:
		return
	try:
		history = _load_watched_history()
		# Forward-compatible: zachovaj existujúce position/duration ak sú
		existing = history.get(uuid, {}) if isinstance(history.get(uuid), dict) else {}
		history[uuid] = {
			'ts': int(time.time()),
			'title': entry.get('disp_title') or '',
			'subtitle': entry.get('disp_subtitle') or '',
			'channelname': entry.get('channelname') or '',
			'start_real': entry.get('start_real') or 0,
			# 0.55beta — zachovaj predošlú resume pozíciu, ak nie je
			# žiadna tak None
			'position': existing.get('position'),
			'duration': existing.get('duration'),
		}
		# Trim na _WATCHED_HISTORY_MAX najnovších
		if len(history) > _WATCHED_HISTORY_MAX:
			sorted_items = sorted(history.items(),
			                      key=lambda kv: kv[1].get('ts', 0),
			                      reverse=True)
			history = dict(sorted_items[:_WATCHED_HISTORY_MAX])
		_save_watched_history(history)
	except Exception:
		pass


def _get_watched_position(uuid):
	"""FIX 0.55beta: vráti (position, duration) pre entry, alebo
	(None, None) ak entry nie je v history alebo nemá zaznamenanú
	pozíciu. Position a duration sú v sekundách (int) alebo None.
	"""
	if not uuid:
		return (None, None)
	try:
		history = _load_watched_history()
		rec = history.get(uuid)
		if not isinstance(rec, dict):
			return (None, None)
		return (rec.get('position'), rec.get('duration'))
	except Exception:
		return (None, None)


def _set_watched_position(entry, position, duration):
	"""FIX 0.55beta: zapíš resume position pre entry. Volaná z stats()
	handler-a pri end/next playback eventu.

	Auto-clear semantika: ak position prekročí _WATCHED_AUTO_CLEAR_DEFAULT_PCT
	z duration, position sa vynuluje (film dohraný, nemá zmysel resume-ovať
	posledné 5 % titulkov/credits). Marker v listingu zostane lebo ide nad
	_WATCHED_MARK_PCT threshold.

	Position-only persist (žiadny title/subtitle update) — to robí
	_track_watched pri play_dvr() otvorení.
	"""
	uuid = entry.get('uuid') if isinstance(entry, dict) else None
	if not uuid:
		return
	try:
		pos = int(position) if position else 0
		dur = int(duration) if duration else 0
	except (TypeError, ValueError):
		return
	try:
		history = _load_watched_history()
		rec = history.get(uuid)
		if not isinstance(rec, dict):
			# Entry nebola v history — vytvor minimálny záznam aby sa pri
			# ďalšom play vedelo, že existuje resume pozícia.
			rec = {
				'ts': int(time.time()),
				'title': entry.get('disp_title') or '',
				'subtitle': entry.get('disp_subtitle') or '',
				'channelname': entry.get('channelname') or '',
				'start_real': entry.get('start_real') or 0,
			}
			history[uuid] = rec
		# Auto-clear ak >= 95 % (film dohraný) — pozícia 0, ale duration
		# si zachováme aby _is_fully_watched mohla vrátiť True a marker
		# v listingu sa zobrazil.
		if dur > 0 and pos >= (dur * _WATCHED_AUTO_CLEAR_DEFAULT_PCT) // 100:
			rec['position'] = 0
		else:
			rec['position'] = pos
		rec['duration'] = dur if dur > 0 else rec.get('duration')
		# Aktualizuj timestamp aby entry vyplávala v recently_watched
		rec['ts'] = int(time.time())
		_save_watched_history(history)
	except Exception:
		pass


def _is_fully_watched(uuid):
	"""FIX 0.55beta: vráti True ak entry má position alebo duration
	naznačujúcu že bola pozretá nad _WATCHED_MARK_PCT (default 80 %)
	hranicu — používa sa pre hviezdičkový marker v listingu.

	Špeciál: ak position == 0 ale duration > 0 (auto-cleared after 95 %),
	entry je tiež považovaná za pozretú (marker sa zobrazí).
	"""
	if not uuid:
		return False
	try:
		history = _load_watched_history()
		rec = history.get(uuid)
		if not isinstance(rec, dict):
			return False
		pos = rec.get('position')
		dur = rec.get('duration')
		if not dur or dur <= 0:
			return False
		# Auto-cleared (95 %+) → marker show
		if pos == 0 and rec.get('ts'):
			# Heuristika: position==0 a record existuje s duration → bola
			# auto-cleared (a teda dosiahla 95 %+). True positive.
			# (Pred 0.55beta entries nemajú duration, dostane sa sem
			# len keď bol playback zaznamenaný v 0.55beta+ formáte.)
			return True
		if pos is None:
			return False
		return pos >= (dur * _WATCHED_MARK_PCT) // 100
	except Exception:
		return False



# FIX 0.48: TTL cache pre _check_tvh_silent() — zabraňuje N×/sec HTTP requestom
# na /api/serverinfo počas navigácie v menu.
# FIX 0.48h: asymetrické TTL — pozitívny check 30s (znižuje GUI lag),
# negatívny len 5s (rýchla recovery po TVH transient failure). Predtým
# spoločné 30s znamenalo že keď TVH zlyhal na 1 request, ďalších 30s
# plugin tvrdil že je offline aj keď sa medzitým obnovil. To je presne
# čo užívatelia zažili v logu — TVH bol späť za pár sekúnd, ale plugin
# 30s ďalej hlásil "not configured".
# 'reason' tracking: rozlíšenie 'not_configured' (chýbajú credentials)
# vs 'unreachable' (sú vyplnené ale API call zlyhal) → root() ukáže
# odlišnú chybovú hlášku.
_TVH_LOGIN_CACHE_TTL_OK   = 30
_TVH_LOGIN_CACHE_TTL_FAIL = 5
_TVH_LOGIN_CACHE = {'ts': 0, 'ok': False, 'reason': None, 'last_error': ''}

# FIX 0.48: globálny stav watchdog timera — drží referenciu, aby ho GC nezahodil
_WATCHDOG_STATE = {'timer': None, 'last_state': None, 'started': False}
_WATCHDOG_INTERVAL_MS = 5 * 60 * 1000  # 5 minút

# FIX 0.48i: fast-recovery poll state. Keď _check_tvh_silent detekuje
# zlyhanie, spustí sa background thread ktorý každých 10 sekúnd skúša
# TVH check (max 30 pokusov = 5 minút). Keď TVH naskočí, cache sa
# silently obnoví na ok=True — ďalšia užívateľská navigácia uvidí
# fungujúci plugin bez ručného retry.
# FIX 0.50beta: pridaný _FAST_RECOVERY_LOCK na ochranu pred race
# condition keď 2+ threads (napr. watchdog tick + user navigation)
# zavolajú _maybe_start_fast_recovery_poll súčasne — predtým mohli
# obaja prejsť `if not running` checkom a spustiť 2 paralelné poll
# loops. V praxi vzácne (5min watchdog vs user interakcia), ale
# stand-alone test scenárov to vyrobí.
import threading as _threading_for_state
_FAST_RECOVERY_STATE = {'running': False, 'thread': None}
_FAST_RECOVERY_LOCK = _threading_for_state.Lock()
_FAST_RECOVERY_INTERVAL_SEC = 10
_FAST_RECOVERY_MAX_ATTEMPTS = 30   # 30 × 10s = 5 minút


# --------------------------------------------------------------------------
# Pomocné funkcie
# --------------------------------------------------------------------------

def _maybe_cleanup_poster_cache():
	"""Čistí starý poster cache – max raz za _POSTER_TTL_DAYS dní.

	FIX 0.48: prísnejšia logika
	  - maže LEN súbory s prefixom 'imagecache_' (plugin-ove ikony),
	    nie iné súbory ktoré tam môžu byť (.stamp, .lock atď.)
	  - vynechá súbory čerstvejšie ako TTL (predtým mazalo všetko)
	  - vynechá '.tmp' rozpracované downloads, aby sa nepokazil prebiehajúci picon worker
	"""
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
		removed = 0
		for fn in os.listdir(_POSTER_CACHE_DIR):
			# Bezpečnostné filtre: maž len skutočne svoje cached ikony
			if not fn.startswith('imagecache_'):
				continue
			if fn.endswith('.tmp'):
				continue  # rozpracovaný download
			fp = os.path.join(_POSTER_CACHE_DIR, fn)
			try:
				if os.path.isfile(fp) and (now - int(os.path.getmtime(fp))) >= ttl:
					os.remove(fp)
					removed += 1
			except Exception:
				pass
		try:
			with open(_POSTER_CLEAN_STAMP, 'w') as f:
				f.write(str(now))
		except Exception:
			pass
		if removed:
			try:
				self.log_info('[plugin.tvheadend]poster cache cleanup: removed %d stale files' % removed)
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


# ============================================================================
# FIX 0.49 (+revízia 0.49b): DVR klasifikácia s podžánrami a viacúrovňovou
# heuristikou.
# ============================================================================
# Cieľ: namiesto vŕtania sa cez kanál → dátum → záznam ponúknuť žánrovú
# navigáciu. Klasifikácia sa robí na klientovi z polí ktoré TVH posiela
# v DVR entries.
#
# Aplikované signály (v poradí priority):
#   1) Channel-based hint   — názov kanála (CT :D = deti, Sport = šport, ...)
#                              prevažuje nad content_type lebo kanálové
#                              značky sú spoľahlivejšie ako EIT meta.
#   2) Series detection     — "X/Y" v subtitle (25/31), "(N)" sufix v title
#                              kde N nie je rok (Otec Brown IV (1)), alebo
#                              keyword "seriál"/"díl"/"epizoda" v popise.
#   3) Content_type fixed   — DVB EIT main category (top nibble genre byte):
#                              ct=2→News, ct=4→Sport, ct=5→Deti, atď.
#   4) Keyword fallback     — pre ct=0/11 (undefined) prejde popis + title
#                              cez Czech/Slovak žánrové keywords.
#
# Sub-žánre (len pre Filmy + Seriály):
#   - DVB genre low nibble (keď je dostupný) — primary signal
#   - Keyword scan v description + title       — secondary signal
#   - 'Iné' ak žiadny nezmatchol               — fallback
#
# Cache: rovnaké 60s TTL ako DVR cache.

# FIX 0.57.0 (skyjet PR #22 review #4): celá klasifikačná logika
# (~1390 LoC: kategórie, sub-kategórie, regex patterns, channel hints,
# keyword fallback, IMDb integration) presunutá do samostatného modulu
# classifier.py. Provider.py teraz importuje public API namiesto in-line
# definícií.
from .classifier import (
	# Kategórie
	_CAT_FILM, _CAT_SERIAL, _CAT_SPORT,
	_CAT_LABELS_ORDER,
	# Display labels pre sub-kategórie (Filmy podžánre)
	_MOVIE_SUBCAT_LABELS,
	# Sub-cat registry pre generic dispatch (Šport, Spravodajstvo, Šou, Detské, ...)
	_SUBCAT_REGISTRY,
	# Regex patterns (používané v provider menu rendering pre series detection)
	_SUBTITLE_SERIES_PATTERN,
	_TITLE_EPISODE_PATTERN,
	# Helpers
	_strip_accents_lower,
	_strip_tech_markers,
	# Klasifikačné funkcie
	_movie_subgenre,
	_get_classified_dvr,
	_invalidate_classify_cache,
)



def _norm_name(s):
	# FIX 0.57.0 (skyjet PR #22 review #13): používa tools_archivczsk
	# `strip_accents` priamo, namiesto custom fallback wrapper-u.
	if not s:
		return ''
	return strip_accents(s).lower()


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

	# Disneyplus-style: nepoužívame login_settings_names (blokuje root()
	# pri prázdnych values). Namiesto toho v login() ručne kontrolujeme
	# required settings a voláme show_info() ako disneyplus.
	#
	# login_optional_settings_names = framework zavolá login_data_changed()
	# keď user zmení niektoré z týchto settings (re-login auto trigger).
	login_settings_names = tuple()
	login_optional_settings_names = (
		'host', 'port', 'use_https',
		'username', 'password',
		'http_auth_mode', 'use_ticket_url',
		'profile', 'loading_timeout',
	)

	def __init__(self, *args, **kwargs):
		CommonContentProvider.__init__(self, *args, **kwargs)
		self.tvh = Tvheadend(self)
		self._bouquet_gen = None
		# FIX 0.57.0: zaregistrovať log callbacky v sub-moduloch aby ich
		# diagnostiky šli do archivCZSK.log. Python logging.getLogger v
		# plugine NEJDE do archivCZSK.log — framework zachytí len
		# cp.log_info() / cp.log_debug() calls.
		try:
			from . import imdb_lookup as _imdb_mod
			if hasattr(_imdb_mod, 'set_log_callback'):
				_imdb_mod.set_log_callback(self.log_info)
			if hasattr(_imdb_mod, 'set_log_debug_callback'):
				_imdb_mod.set_log_debug_callback(self.log_debug)
		except Exception:
			pass
		try:
			from . import classifier as _cls_mod
			if hasattr(_cls_mod, 'set_log_callback'):
				_cls_mod.set_log_callback(self.log_info)
		except Exception:
			pass

	# ------------------------------------------------------------------
	# login() – volá sa automaticky pri štarte aj po zmene nastavení
	# ------------------------------------------------------------------

	def login(self, silent=False):
		# Disneyplus-style: required settings check + info dialog
		if not (self.get_setting('host') or '').strip() \
		   or not (self.get_setting('username') or '').strip() \
		   or not (self.get_setting('password') or '').strip():
			if not silent:
				self.show_info(self._(
				    "To display content, you must enter TVH server "
				    "(host, username, password) in the addon settings"),
				    noexit=True)
			return False

		# Python 2 – best-effort beh, len jednorazové upozornenie do logu
		if sys.version_info[0] < 3:
			if not getattr(self, '_py2_warned', False):
				try:
					self.log_info("[Tvheadend] WARNING: running on "
					              "Python 2.x — best-effort mode")
				except Exception:
					pass
				self._py2_warned = True

		# Vyčistenie poster cache (max raz za týždeň) – tu, nie v __init__
		try:
			_maybe_cleanup_poster_cache()
		except Exception:
			pass

		# FIX 0.54beta: sync IMDb lookup feature flag s aktuálnym
		# setting. Volá sa pri každom login() — toggle v Settings sa
		# prejaví bez reštartu (framework volá login() po zmene
		# settingov cez login_data_changed).
		# FIX 0.57.0: cp.log_info() (framework logger) ide do archivCZSK.log.
		# Predtým bol logging.getLogger() ktorý šiel do stdlib logger ktorý
		# E2 nezachytí.
		try:
			from . import imdb_lookup as _imdb
			raw = self.get_setting('online_metadata_lookup')
			# ArchivCZSK vracia bool pre type="bool" settings, ale pre
			# istotu akceptujeme aj "true"/"1"/True/1.
			if isinstance(raw, bool):
				enabled = raw
			else:
				enabled = str(raw).strip().lower() in ('true', '1', 'yes')
			_imdb.set_enabled(enabled)
			self.log_info('IMDb lookup setting raw=%r resolved=%s' %
			              (raw, 'ON' if enabled else 'OFF'))
		except Exception as _e:
			try:
				self.log_info('IMDb lookup setup failed: %s' % _e)
			except Exception:
				pass

		# FIX 0.48: invalid-uj login cache pri každom login() volaní cez
		# settings change. (Framework volá login_data_changed → login(silent=True)
		# po zmene credentials.)
		self._invalidate_tvh_login_cache()
		try:
			self.tvh.invalidate_auth_cache()
		except Exception:
			pass

		# Test TVH connectivity (without raising — neúspech nezablokuje plugin,
		# Settings menu ostane prístupný aj keď TVH dočasne nedostupný)
		tvh_ok = False
		if self.tvh.is_configured():
			try:
				self.tvh.check_login()
				tvh_ok = True
			except Exception:
				tvh_ok = False
		# Aktualizuj cache aby _check_tvh_silent() nešiel hneď znova na server
		_TVH_LOGIN_CACHE['ts'] = int(time.time())
		_TVH_LOGIN_CACHE['ok'] = tvh_ok

		# TVH-related background work len pri funkčnom spojení
		if tvh_ok:
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
				try:
					self._maybe_trigger_exports(silent=bool(silent))
				except Exception:
					pass

			# Auto-refresh bouquetu podľa nastaveného intervalu
			try:
				self._maybe_auto_refresh_bouquet()
			except Exception:
				pass

			# FIX 0.58.2 (skyjet PR #22 review #11 follow-up): nezávislý EPG
			# auto-inject odstránený — framework `BouquetXmlEpgGenerator`
			# automaticky volá `refresh_xmlepg()` každé 4 hodiny + pri
			# settings change keď je `enable_xmlepg=True`. Plus podľa
			# `bouquet_refresh_interval` sa znova aj triggeruje cez
			# `_maybe_auto_refresh_bouquet()` ktoré sa volá vyššie.

		# FIX 0.57.0 (skyjet PR #22 review #10/#11): M3U manager init
		# odstránený — extrahovaný do plugin.video.e2m3u2bouquet.

		# FIX 0.48: watchdog timer — spustí sa raz pri prvom login()
		# (preload="yes" v addon.xml znamená že login beží pri boot-e E2).
		# Pravidelne (5 min) volá _check_tvh_silent(force=True), a keď
		# detekuje OFFLINE → ONLINE prechod, automaticky spustí bouquet
		# refresh + picon download. Tým sa odstráni potreba manuálne
		# otvoriť plugin po reštarte TVH servera.
		try:
			self._maybe_start_watchdog()
		except Exception:
			pass

		# Pozn.: Dialóg "Plugin nie je nakonfigurovaný" sa zobrazí z root()
		# vyhodením AddonErrorException — framework ho v run() zachytí cez
		# `except AddonErrorException: client.showError(str(e))`. Tu v login()
		# nezobrazujeme nič (vždy vrátime True), aby framework dostal kontrolu
		# nad volaním root().

		# Vždy vracia True aby framework načítal root() - bez ohľadu na TVH stav.
		# Jednotlivé root() / live_root() / archive_channels() si overia
		# TVH login podľa potreby cez _check_tvh_silent().
		return True

	def _quick_login_for_http_handler(self):
		"""FIX 0.48: light-weight login pre HTTP handler.

		Predtým HTTP handler `get_url_by_channel_key()` volal plný `login(silent=True)`,
		ktorý pri každom playback-u kanála spravil:
		  - _maybe_cleanup_poster_cache (rýchle, ale beží)
		  - lazy init bouquet generator
		  - init_picons_async (spawn threadu zakaždým — _picon_worker_lock
		    zabráni paralelnému downloadu, ale stále zbytočný thread overhead)
		  - _maybe_trigger_exports + _maybe_auto_refresh_bouquet

		Pre HTTP handler stačí overiť TVH konektivitu cez cache.
		Bouquet refresh / picon download spustí watchdog alebo plný login().
		"""
		if not self.tvh.is_configured():
			return False
		try:
			# Použi cache (default 30s) — pri streamovaní mnoho channels
			# za sekundu by sme inak hammerovali TVH /api/serverinfo.
			return self._check_tvh_silent()
		except Exception:
			return False

	def _maybe_start_watchdog(self):
		"""Spustí periodický watchdog timer ktorý detekuje návrat TVH online.

		FIX 0.48: bez tohto musel užívateľ po reštarte TVH servera buď
		otvoriť plugin v GUI alebo počkať na ďalší pokus o stream.
		Watchdog beží na pozadí (eTimer + fallback threading) a:
		  - každých 5 minút volá _check_tvh_silent(force=True)
		  - ak detekuje OFFLINE→ONLINE prechod, spustí na pozadí:
		      a) bouquet refresh (cez existujúci _bouquet_gen)
		      b) picon download (cez init_picons_async)
		  - ak je ONLINE, ešte navyše kontroluje či nezbehol auto-refresh
		    bouquet interval (užitočné keď používateľ ROZHODNE neotvára
		    plugin v GUI a HTTP handler sa tiež nepoužíva)
		"""
		if _WATCHDOG_STATE['started']:
			return

		def _tick():
			try:
				prev = _WATCHDOG_STATE.get('last_state')
				now_ok = self._check_tvh_silent(force=True)
				_WATCHDOG_STATE['last_state'] = now_ok

				if now_ok and prev is False:
					# OFFLINE → ONLINE prechod
					try:
						self.log_info('[Tvheadend] watchdog: TVH back online — '
						      'triggering bouquet + picon refresh')
					except Exception:
						pass
					# Lazy-init bouquet gen ak ešte nie je
					if self._bouquet_gen is None and TvheadendBouquetXmlEpgGenerator is not None:
						try:
							self._bouquet_gen = TvheadendBouquetXmlEpgGenerator(self)
						except Exception:
							pass
					# Background refresh (non-blocking)
					if self._bouquet_gen is not None:
						try:
							self._bouquet_gen.refresh_userbouquet_start()
							with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
								f.write(str(int(time.time())))
						except Exception:
							pass
					try:
						self.tvh.init_picons_async()
					except Exception:
						pass

				# Pravidelná kontrola auto-refresh aj keď user neotvoril plugin
				if now_ok and self._bouquet_gen is not None:
					try:
						self._maybe_auto_refresh_bouquet()
					except Exception:
						pass
					# FIX 0.58.2: EPG auto-inject odstránený z watchdog —
					# framework sám trigger-uje refresh_xmlepg po
					# refresh_bouquet keď je enable_xmlepg=True.
			except Exception as e:
				try:
					self.log_info('[plugin.tvheadend]watchdog error: %s' % e)
				except Exception:
					pass

		# Skús enigma eTimer, fallback threading
		try:
			from enigma import eTimer
			t = eTimer()
			try:
				del t.callback[:]
			except Exception:
				pass
			t.callback.append(_tick)
			# False = opakovaný timer (nie singleshot)
			t.start(_WATCHDOG_INTERVAL_MS, False)
			_WATCHDOG_STATE['timer'] = t
			_WATCHDOG_STATE['started'] = True
			try:
				self.log_info('[Tvheadend] watchdog started '
				      '(eTimer, interval=%d min)' % (_WATCHDOG_INTERVAL_MS // 60000))
			except Exception:
				pass
		except ImportError:
			# Fallback: daemon thread + Event.wait
			import threading as _th
			ev = _th.Event()
			_WATCHDOG_STATE['stop_event'] = ev
			interval_sec = _WATCHDOG_INTERVAL_MS // 1000

			def _loop():
				while not ev.wait(interval_sec):
					_tick()

			th = _th.Thread(target=_loop, name='TVHWatchdog')
			th.daemon = True
			th.start()
			_WATCHDOG_STATE['timer'] = th
			_WATCHDOG_STATE['started'] = True

	def _check_tvh_silent(self, force=False):
		"""Vráti True ak TVH server je nakonfigurovaný a prihlásenie funguje.

		FIX 0.48: TTL cache.
		FIX 0.48h: asymetrické TTL (30s pri úspechu, 5s pri zlyhaní) — keď
		TVH transient failne, ďalší pokus zbehne čoskoro. + 'reason' tracking
		('not_configured' / 'unreachable' / 'ok') pre rozlíšenie chybových
		stavov v root().
		FIX 0.48i:
		  - pri prvom zlyhaní okamžitý retry s force_reauth=True (handluje
		    digest auth nonce expiry — TVH server občas odhodí nonce po
		    niekoľkých minútach idle, requests knižnica si občas nestihne
		    obnoviť stav medzi thread-mi)
		  - keď check stále zlyhá, spustí sa background fast-recovery poll
		    cez _maybe_start_fast_recovery_poll() — užívateľ nebude musieť
		    tlačiť retry manuálne; po naskočení TVH sa cache aktualizuje
		    ticho a ďalšia navigácia zafunguje

		Volajúci môže zistiť dôvod cez get_tvh_state() metódu nižšie.

		FIX 0.50beta: zdieľaný core (_do_tvh_login_check) s
		_check_tvh_silent_no_recurse_for_poll — eliminuje DRY violation
		ktorá vyžadovala udržiavať dve takmer identické kópie tej istej
		logiky (oba volajú check_login + force_reauth retry + cache
		update). Verzia bez recurse je iba flag `start_recovery_on_fail`.
		"""
		now = int(time.time())
		c = _TVH_LOGIN_CACHE
		if not force:
			ttl = _TVH_LOGIN_CACHE_TTL_OK if c['ok'] else _TVH_LOGIN_CACHE_TTL_FAIL
			if (now - c['ts']) < ttl:
				return c['ok']
		return self._do_tvh_login_check(start_recovery_on_fail=True)

	def _do_tvh_login_check(self, start_recovery_on_fail):
		"""FIX 0.50beta: zdieľaný core pre _check_tvh_silent +
		_check_tvh_silent_no_recurse_for_poll.

		Vykoná dvojfázový check (prvý pokus + force_reauth retry),
		aktualizuje module-level _TVH_LOGIN_CACHE, a (ak je
		start_recovery_on_fail=True) pri zlyhaní spustí background
		fast-recovery poll cez _maybe_start_fast_recovery_poll.

		Vráti True/False.
		"""
		now = int(time.time())
		c = _TVH_LOGIN_CACHE

		if not self.tvh.is_configured():
			c['ts'] = now
			c['ok'] = False
			c['reason'] = 'not_configured'
			c['last_error'] = ''
			return False

		# Dvojfázový check: prvý pokus na existujúcom auth state,
		# druhý pokus s freshým HTTPDigestAuth (force_reauth=True)
		# rieši digest auth nonce expiry po idle period.
		err = ''
		ok = False
		try:
			self.tvh.check_login()
			ok = True
		except Exception as e:
			err = str(e)
			try:
				time.sleep(0.3)  # malé čakanie na sieťovú stabilizáciu
				self.tvh.check_login(force_reauth=True)
				ok = True
				err = ''
				try:
					self.log_info('[Tvheadend] check_login: recovered on retry '
					      'with force_reauth (was: %s)' % e)
				except Exception:
					pass
			except Exception as e2:
				err = str(e2)

		c['ts'] = now
		c['ok'] = ok
		c['reason'] = 'ok' if ok else 'unreachable'
		c['last_error'] = err

		if not ok and start_recovery_on_fail:
			try:
				self._maybe_start_fast_recovery_poll()
			except Exception:
				pass

		return ok

	def get_tvh_state(self):
		"""FIX 0.48h: vráti tuple (ok, reason, last_error) pre nadradenú logiku."""
		c = _TVH_LOGIN_CACHE
		return (c['ok'], c.get('reason'), c.get('last_error') or '')

	def _invalidate_tvh_login_cache(self):
		"""Vynúti čerstvý check pri ďalšom _check_tvh_silent()."""
		_TVH_LOGIN_CACHE['ts'] = 0

	def _maybe_start_fast_recovery_poll(self):
		"""FIX 0.48i: spustí background poll thread ktorý každých 10s skúša
		TVH check, kým TVH neobnovuje. Max 5 minút (30 pokusov), potom sa
		zastaví — watchdog tick (každých 5 min) obnoví normálny cyklus.

		Cieľ: užívateľ nemusí ručne stláčať Retry po TVH transient failure.
		Po naskočení TVH sa cache silently aktualizuje na ok=True a ďalšia
		navigácia uvidí všetko v poriadku.

		Idempotentné: ak už beží, druhé volanie nič nespraví.

		FIX 0.50beta: check-and-set chránený _FAST_RECOVERY_LOCK proti
		race condition keď 2+ threads zavolajú túto metódu súčasne.
		"""
		import threading as _th
		# FIX 0.50beta: atomic check-and-set namiesto zraniteľnej
		# kombinácie `if not running: ... running = True`
		with _FAST_RECOVERY_LOCK:
			if _FAST_RECOVERY_STATE.get('running'):
				return  # už beží
			ev_stop = _th.Event()
			_FAST_RECOVERY_STATE['stop_event'] = ev_stop
			_FAST_RECOVERY_STATE['running'] = True

		def _poll_loop():
			try:
				self.log_info('[Tvheadend] fast-recovery poll started '
				      '(every %ds, max %d attempts)' %
				      (_FAST_RECOVERY_INTERVAL_SEC, _FAST_RECOVERY_MAX_ATTEMPTS))
			except Exception:
				pass
			for attempt in range(_FAST_RECOVERY_MAX_ATTEMPTS):
				# Event.wait s timeout — kedykoľvek možno cancelnúť cez set()
				if ev_stop.wait(_FAST_RECOVERY_INTERVAL_SEC):
					break  # cancelled
				try:
					# force=True aby sme obišli TTL cache (5s je ešte v platnosti)
					ok = self._check_tvh_silent_no_recurse_for_poll()
					if ok:
						try:
							self.log_info('[Tvheadend] fast-recovery: TVH back '
							      'online after %d attempts (%ds total)' %
							      (attempt + 1,
							       (attempt + 1) * _FAST_RECOVERY_INTERVAL_SEC))
						except Exception:
							pass
						break
				except Exception:
					pass
			# FIX 0.50beta: reset running flag pod lockom, rovnaký lock
			# ako check-and-set v _maybe_start_fast_recovery_poll, aby
			# následné volanie videlo running=False atomicky
			with _FAST_RECOVERY_LOCK:
				_FAST_RECOVERY_STATE['running'] = False
			try:
				self.log_info('[plugin.tvheadend] fast-recovery poll ended')
			except Exception:
				pass

		t = _th.Thread(target=_poll_loop, name='TVHFastRecovery')
		t.daemon = True
		_FAST_RECOVERY_STATE['thread'] = t
		t.start()

	def _check_tvh_silent_no_recurse_for_poll(self):
		"""FIX 0.48i: variant _check_tvh_silent ktorý sa NEZAVOLÁVA
		fast-recovery (lebo my SME fast-recovery). Pomáha vyhnúť sa
		rekurzii / opakovanému spawnu thread-ov.

		FIX 0.50beta: namiesto duplicitnej kópie celej _check_tvh_silent
		logiky (auth retry, cache update, ...) volá zdieľaný core
		_do_tvh_login_check(start_recovery_on_fail=False).
		"""
		return self._do_tvh_login_check(start_recovery_on_fail=False)



	def _maybe_auto_refresh_bouquet(self):
		"""Automaticky refreshne bouquet ak uplynul nastavený interval.

		FIX 0.48: stamp sa zapíše AŽ po úspešnom spustení refreshu.
		Predtým sa zapísal pred volaním, takže pri zlyhaní (TVH dočasne
		nedostupný) sa nasledujúci pokus odložil o celý interval —
		bouquet ostal "navždy" zastaraný. Teraz pri zlyhaní zapíšeme
		"retry stamp" s krátkym intervalom (5 minút), takže auto-retry
		zbehne čoskoro keď sa TVH vráti.
		"""
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
			# Pri retry stamp-e (mtime v budúcnosti vďaka touch trickom by sme
			# museli komplikovať — držíme to jednoducho: posledný mtime + interval).
			if last and (now - last) < interval:
				return

			# Skontroluj TVH PRED volaním refreshu — keď je TVH down,
			# zmazaj len logically a skús o 5 minút.
			if not self._check_tvh_silent():
				# nastav stamp tak, aby ďalší pokus bol o 5 min
				retry_at = now - interval + 300
				try:
					os.utime(_BOUQUET_REFRESH_STAMP, (retry_at, retry_at))
				except Exception:
					try:
						with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
							f.write(str(retry_at))
					except Exception:
						pass
				return

			# Spusti refresh — task beží na pozadí
			try:
				self._bouquet_gen.refresh_userbouquet_start()
				# úspešne naplánované → stamp je teraz
				try:
					with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
						f.write(str(now))
				except Exception:
					pass
			except Exception as e:
				try:
					self.log_info('[plugin.tvheadend]auto-refresh bouquet failed: %s' % e)
				except Exception:
					pass
				# retry za 5 min
				retry_at = now - interval + 300
				try:
					with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
						f.write(str(retry_at))
					os.utime(_BOUQUET_REFRESH_STAMP, (retry_at, retry_at))
				except Exception:
					pass
		except Exception:
			pass

	# FIX 0.58.2: `_maybe_auto_inject_epg` method (~85 LoC) odstránená.
	# Framework `BouquetXmlEpgGenerator` automaticky volá `refresh_xmlepg()`
	# každé 4 hodiny v internom bgservice loope + pri každom settings
	# change. Custom debouncing cez `_EPG_INJECT_STAMP` už nepotrebujeme.

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
		"""Root menu - kontextové:
		- Nič nakonfigurované       → framework auto-zobrazí info dialog
		                              (login_settings_names check) — root()
		                              sa vôbec nezavolá
		- TVH dočasne nedostupný    → krátka chybová hláška + Retry položka
		                              (FIX 0.48h)
		- TVH login OK              → Live TV + Archive + Settings
		"""
		tvh_ok = self._check_tvh_silent()
		_, tvh_reason, tvh_err = self.get_tvh_state()

		# FIX 0.48h: rozlíšenie stavov.
		# - not_configured (reason): framework rieši cez login_settings_names
		# - unreachable (reason): krátka info hláška + Retry položka
		#   + Settings folder
		if not tvh_ok:
			if tvh_reason == 'unreachable':
				# TVH credentials sú vyplnené ale check_login zlyhal.
				# FIX 0.48i: namiesto modálneho dialógu (ktorý blokoval GUI
				# 3s) pridáme informačné položky priamo do menu — užívateľ
				# uvidí podstatu chyby (multi-line) a vie hneď tlačiť retry.
				# FIX 0.50beta: + user-friendly hint pre typické chyby
				# FIX 0.50beta (iter 3): ak hint matchol, NEUKAZUJ raw error
				# detail — duplicita ktorá mätie užívateľa. Raw error je
				# dostupný cez Settings → "Otestovať TVH login / spojenie".
				self.add_dir(self._("⟳ Retry TVH connection"),
				             cmd=self.action_retry_tvh_root,
				             info_labels={'title': self._("Retry")})
				self.add_dir(self._("TVH temporarily unreachable. "
				                    "Auto-recovery polling in background."),
				             cmd=self.action_retry_tvh_root,
				             info_labels={'title': self._("TVH status")})
				hint = self._guess_tvh_error_hint(tvh_err)
				if hint:
					self.add_dir(hint,
					             cmd=self.settings_menu,
					             info_labels={'title': self._("Open settings")})
				else:
					# Žiadny hint nematchol → ukáž raw multi-line error
					self._render_tvh_error_lines(tvh_err)
				self.add_dir(self._("Settings"),
				             cmd=self.settings_menu,
				             info_labels={'title': self._("Settings")})
				return

			# not_configured (chýbajúce host/user/pass) → framework už zobrazil
			# auto-info dialog cez login_settings_names check, kým sa táto
			# vetva dosiahne. Tu len return — root() ostane prázdny.
			return

		if tvh_ok:
			# FIX 0.52beta (iter 5): vrátený framework default `add_search_dir()`.
			# Predchádzajúci 1-click priamy-keyboard cez action_dvr_search()
			# síce eliminoval medzistránku, ale stratil **história hľadaní**.
			# Framework search_list ukáže:
			#   [Nové hľadanie - lupa]      ← 1 click → keyboard popup
			#   Markíza                     ← predošlé hľadanie, 1 click → priamy search
			#   Doktor Martin               ← bez znovuzadávania
			#   Na noze
			#   ...
			# Default 10 history entries (config 'keep-searches'). Framework
			# spravuje add/remove/edit predošlých — žiadny vlastný kód netreba.
			# Trade-off: 2-click na nový search (lupa → "Nové hľadanie" →
			# keyboard). Pre opakované hľadania (typický use-case) 1-click.
			try:
				dvr_entries_count = len(_get_dvr_finished_cached(self.tvh) or [])
				if dvr_entries_count > 0:
					self.add_search_dir(
						title=self._("Search archive"))
			except Exception as _e:
				try:
					self.log_info('[plugin.tvheadend]add_search_dir failed: %s' % _e)
				except Exception:
					pass

			self.add_dir(self._("Live TV"),
			             cmd=self.live_root,
			             info_labels={'title': self._("Live TV")})
			self.add_dir(self._("Archive"),
			             cmd=self.archive_channels,
			             info_labels={'title': self._("Archive")})

			# FIX 0.49 / 0.49b: Top-level kategórie (Filmy/Seriály/Šport/...)
			# Položka sa pridá len ak je v kategórii aspoň 1 záznam.
			# FIX 0.49b: počty v zátvorke ODSTRÁNENÉ z labelov (užívateľ
			# nechcel vidieť "(1417)" v menu).
			try:
				_, _, _counts, _, _ = _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
				for cat_id, label_base in _CAT_LABELS_ORDER:
					n = _counts.get(cat_id, 0)
					if n <= 0:
						continue
					self.add_dir(self._(label_base),
					             info_labels={'title': self._(label_base)},
					             cmd=self.archive_by_category,
					             cat_id=cat_id)
			except Exception as _e:
				try:
					self.log_info('[Tvheadend] root: dvr classify '
					      'failed (skipping categories): %s' % _e)
				except Exception:
					pass

			# FIX 0.52beta: "Posledné sledované" — shortcut k naposledy
			# otvoreným DVR nahrávkam (max 50). Sleduje sa cez play_dvr()
			# hook. Položka sa zobrazí len ak history má aspoň 1 entry.
			# Umiestnenie: za žánrové kategórie a pred Nastavenia
			# (logické miesto pre "rýchly skok do nedávno sledovaného").
			try:
				_wh = _load_watched_history()
				if _wh:
					self.add_dir(self._("Recently watched"),
					             cmd=self.recently_watched,
					             info_labels={'title': self._("Recently watched")})
			except Exception:
				pass
		elif tvh_reason == 'unreachable':
			# FIX 0.48h: ukáž retry ak má užívateľ vyplnené TVH credentials
			# ale práve teraz nejde (transient)
			# FIX 0.50beta: + user-friendly hint
			# FIX 0.50beta (iter 3): hint → skip raw error (čistejšie UI)
			self.add_dir(self._("⟳ Retry TVH connection (currently unreachable)"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry TVH")})
			hint = self._guess_tvh_error_hint(tvh_err)
			if hint:
				self.add_dir(hint,
				             cmd=self.settings_menu,
				             info_labels={'title': self._("Open settings")})
			else:
				self._render_tvh_error_lines(tvh_err)

		# Settings folder vždy prístupný (užívateľ ho potrebuje aj keď TVH zlyhal).
		self.add_dir(self._("Settings"),
		             cmd=self.settings_menu,
		             info_labels={'title': self._("Settings")})

	def action_retry_tvh_root(self):
		"""FIX 0.48h: užívateľský retry — invaliduj cache + re-render root.

		Volaná z root() retry položky a z live_root() pri transient failures.
		Po stlačení sa nasleduje ďalšie volanie root() ktoré spraví fresh
		check_login (cache=0 po invalidate).

		FIX 0.48i: aj zruší prípadný bežiaci fast-recovery poll (lebo
		urobíme manuálny check teraz, netreba zbytočne paralelne).
		"""
		try:
			self._invalidate_tvh_login_cache()
			# Vlastný TVH auth cache (separátny od _TVH_LOGIN_CACHE) tiež reset
			self.tvh.invalidate_auth_cache()
		except Exception:
			pass
		# FIX 0.48i: cancel fast-recovery poll ak beží
		try:
			ev = _FAST_RECOVERY_STATE.get('stop_event')
			if ev is not None and _FAST_RECOVERY_STATE.get('running'):
				ev.set()
		except Exception:
			pass
		# Re-render root menu — pridá nové items do tej istej "stránky"
		# (framework si ich vyberie ako návratový obsah z action_*)
		self.root()

	# ------------------------------------------------------------------
	# Settings menu - ručné akcie (refresh TVH/EPG/picons, status, atď.)
	# ------------------------------------------------------------------

	def settings_menu(self):
		"""Hlavné menu Nastavenia:
		Status info (TVH server, picon cache, EPG last inject, ...)
		+ TVH actions (refresh, EPG inject, picons, test login).
		"""
		tvh_ok = self._check_tvh_silent()

		# --- Status sekcia (vždy) ---
		for line in self._build_status_lines():
			self.add_dir(line, cmd=self.settings_menu,
			             info_labels={'title': line})

		# --- TVH sekcia (len ak je TVH nakonfigurované a prihlásené) ---
		if tvh_ok:
			self.add_dir("─" * 32, cmd=self.settings_menu,
			             info_labels={'title': self._("Tvheadend Actions")})

			self.add_dir(self._("Refresh TVH bouquet + XML EPG now"),
			             cmd=self.action_tvh_bouquet_refresh,
			             info_labels={'title': self._("Refresh TVH bouquet")})
			# FIX 0.58.2: "Inject EPG now" menu item odstránený — framework
			# triggeruje EPG inject po každom bouquet refresh, takže
			# "Refresh TVH bouquet + XML EPG now" robí oboje.
			self.add_dir(self._("Download TVH picons now"),
			             cmd=self.action_tvh_picons,
			             info_labels={'title': self._("TVH picons")})
			# FIX 0.48b: tlačidlo na vyčistenie 404 negatívnej cache.
			# Užitočné keď user opraví broken ikony v TVH webUI a chce
			# okamžitý retry namiesto čakania 1h na auto-expire.
			self.add_dir(self._("Clear 404 picon cache (retry broken icons)"),
			             cmd=self.action_clear_picon_404_cache,
			             info_labels={'title': self._("Clear 404 cache")})
			self.add_dir(self._("Invalidate TVH channel cache"),
			             cmd=self.action_tvh_invalidate_cache,
			             info_labels={'title': self._("Clear TVH cache")})
			self.add_dir(self._("Test TVH login / connection"),
			             cmd=self.action_tvh_test_login,
			             info_labels={'title': self._("Test login")})

		# --- Diagnostika (vždy ale relevantné položky) ---
		self.add_dir("─" * 32, cmd=self.settings_menu,
		             info_labels={'title': self._("Diagnostics")})


		# Show paths - vždy užitočné
		self.add_dir(self._("Show paths and generated files"),
		             cmd=self.action_show_paths,
		             info_labels={'title': self._("Paths")})

	# ------------------------------------------------------------------
	# Status info pre Settings menu
	# ------------------------------------------------------------------

	def _build_status_lines(self):
		"""Vráti zoznam status riadkov pre úvod Settings menu."""
		lines = []

		def _fmt_age(stamp_path):
			try:
				t = int(os.path.getmtime(stamp_path))
				dt = datetime.fromtimestamp(t).strftime('%d.%m.%Y %H:%M')
				age = int(time.time()) - t
				if age < 60:
					age_s = "%ds" % age
				elif age < 3600:
					age_s = "%dm" % (age // 60)
				elif age < 86400:
					age_s = "%dh %dm" % (age // 3600, (age % 3600) // 60)
				else:
					age_s = "%dd" % (age // 86400)
				return "%s (%s ago)" % (dt, age_s)
			except Exception:
				return self._("never")

		tvh_ok = self._check_tvh_silent()

		# TVH connection - len ak je nakonfigurované
		if tvh_ok:
			try:
				host = self.get_setting('host') or '127.0.0.1'
				port = self.get_setting('port') or '9981'
				lines.append("◆ %s: %s:%s" %
				             (self._("TVH server"), host, port))
			except Exception:
				pass

			# TVH bouquet refresh stamp
			try:
				lines.append("◆ %s: %s" %
				             (self._("Last TVH bouquet refresh"),
				              _fmt_age(_BOUQUET_REFRESH_STAMP)))
			except Exception:
				pass

			# FIX 0.58.2: EPG inject status line odstránená — framework
			# auto-triggeruje EPG inject po každom bouquet refresh,
			# takže "Last bouquet refresh" implicitne pokrýva aj EPG.

			# FIX 0.48b: pocet broken-icon channels (404 cache)
			try:
				from .tvheadend import _picon_404_count
				cnt = _picon_404_count()
				if cnt > 0:
					lines.append("◆ %s: %d" %
					             (self._("Picons with broken icons (404 cache)"),
					              cnt))
			except Exception:
				pass

		# Ak nič nie je nakonfigurované, ukáž aspoň hint
		if not tvh_ok:
			lines.append("◆ %s" %
			             self._("Configure TVH credentials in plugin settings"))

		return lines

	# ------------------------------------------------------------------
	# Action callbacks
	# ------------------------------------------------------------------





	def action_tvh_bouquet_refresh(self):
		"""Manuálne spustí TVH bouquet + XML EPG refresh."""
		if not self._check_tvh_silent():
			self.add_dir(self._("✗ TVH login failed - check settings"),
			             cmd=self.settings_menu)
			return
		if self._bouquet_gen is None:
			self.add_dir(self._("✗ Bouquet generator not initialised"),
			             cmd=self.settings_menu)
			return
		try:
			# Zmaž stamp aby refresh prebehol bez TTL gate
			try:
				if os.path.exists(_BOUQUET_REFRESH_STAMP):
					os.remove(_BOUQUET_REFRESH_STAMP)
			except Exception:
				pass
			self._bouquet_gen.refresh_userbouquet_start()
			# Zapíš nový stamp
			try:
				with open(_BOUQUET_REFRESH_STAMP, 'w') as f:
					f.write(str(int(time.time())))
			except Exception:
				pass
			self.add_dir(self._("✓ TVH bouquet refresh triggered"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_tvh_picons(self):
		"""Manuálne spustí stiahnutie TVH piconov.

		FIX 0.57.0 (skyjet PR #22 review #11-#14): pre 0.57.0 picon flow
		má dva paralelné kanály:
		  1) /tmp/ cache pre internal menu rendering cez make_icon_url()
		     — sťahuje TVH imagecache do /tmp/ cez init_picons_async().
		  2) /usr/share/enigma2/picon/ pre E2 skin-y cez framework
		     BouquetGeneratorTemplate.download_picons() — volá sa
		     z BouquetXmlEpgGenerator.run() pri bouquet refresh-e.

		Manuálna akcia spustí oboje — (1) priamo cez init_picons_async,
		(2) force bouquet refresh ktorý framework picon download triggerne
		v background thread.
		"""
		if not self._check_tvh_silent():
			self.add_dir(self._("✗ TVH login failed - check settings"),
			             cmd=self.settings_menu)
			return
		try:
			# (1) /tmp/ cache update pre menu rendering
			self.tvh.init_picons_async()

			# (2) Framework picon download — len ak enable_picons=true
			if self._bouquet_gen is None and TvheadendBouquetXmlEpgGenerator is not None:
				try:
					self._bouquet_gen = TvheadendBouquetXmlEpgGenerator(self)
				except Exception:
					self._bouquet_gen = None
			if (self._bouquet_gen is not None
			    and self._bouquet_gen.get_setting('enable_picons')):
				try:
					# FIX 0.57.0 debug: framework cache-uje channel checksum
					# a SKIP-uje bouquet_generator.run() ak sa nezmenil. To
					# znamená že framework download_picons sa nevolá pri
					# druhom+ behu. Invaliduj cache aby refresh vždy bežal.
					try:
						self.log_debug('[Tvheadend.debug] invalidating bouquet cache to force regenerate')
						self.save_cached_data('bouquet', {})
					except Exception as _e:
						self.log_debug('[Tvheadend.debug] cache invalidation failed: %s' % _e)

					self._bouquet_gen.refresh_userbouquet_start()
					self.add_dir(self._("✓ Bouquet refresh + TVH picon download started in background"),
					             cmd=self.settings_menu)
				except Exception as e:
					self.add_dir(self._("✓ TVH picon /tmp cache update started "
					                    "(framework download skipped: %s)") % str(e),
					             cmd=self.settings_menu)
			else:
				self.add_dir(self._("✓ TVH picon /tmp cache update started "
				                    "(framework download disabled — enable 'Automatically "
				                    "download picons' in Userbouquet settings)"),
				             cmd=self.settings_menu)
			# FIX 0.48j: logy idú cez print() do /tmp/archivCZSK.log,
			# nie do vlastného súboru
			self.add_dir(self._("Progress: see /tmp/archivCZSK.log "
			                    "(filter '[plugin.tvheadend')"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	# FIX 0.58.2: `action_tvh_inject_epg` (manual EPG injection) odstránená
	# — framework `BouquetXmlEpgGenerator` triggeruje EPG inject po každom
	# bouquet refresh, takže `action_tvh_bouquet_refresh` robí oboje.

	def action_tvh_invalidate_cache(self):
		"""Zmaže TVH channel cache - užitočné po pridaní/zmene kanálov v TVH."""
		try:
			self.tvh.invalidate_channels_cache()
			# FIX 0.49: zruš aj DVR klasifikačnú cache (jej obsah by inak
			# 60s ostal stale aj keď kanály sa zmenili)
			try:
				_invalidate_classify_cache()
			except Exception:
				pass
			self.add_dir(self._("✓ TVH channel cache cleared"),
			             cmd=self.settings_menu)
			self.add_dir(self._("Next channel listing will fetch fresh data"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_clear_picon_404_cache(self):
		"""FIX 0.48b: Vyčistí 404 negatívnu cache pre picony.

		Použiteľné keď užívateľ v TVH webUI opraví broken kanál icony
		a chce ich teraz znova stiahnuť bez čakania na 1h auto-expire.
		"""
		try:
			from .tvheadend import _picon_404_clear, _picon_404_count
			before = _picon_404_count()
			_picon_404_clear()
			self.add_dir(self._("✓ 404 picon cache cleared (was: %d entries)")
			             % before, cmd=self.settings_menu)
			self.add_dir(self._("Next picon refresh will retry all broken icons"),
			             cmd=self.settings_menu)
			# Hneď spusti retry na pozadí
			try:
				self.tvh.init_picons_async()
				self.add_dir(self._("✓ Picon download retry triggered in background"),
				             cmd=self.settings_menu)
			except Exception:
				pass
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_tvh_test_login(self):
		"""Otestuje TVH login + zobrazí informáciu o serveri."""
		try:
			self.tvh.check_login()
			# Pokus o get_channels pre overenie permissions
			chs = self.tvh.get_channels(force=True)
			tags = self.tvh.get_tags()
			self.add_dir(self._("✓ TVH login successful"),
			             cmd=self.settings_menu)
			self.add_dir(self._("Channels: ") + str(len(chs or [])),
			             cmd=self.settings_menu)
			self.add_dir(self._("Tags: ") + str(len(tags or [])),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Login failed: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)


	def action_show_paths(self):
		"""Zobrazí cesty k vygenerovaným súborom + ich veľkosti."""
		paths_to_check = [
			('/etc/enigma2/bouquets.tv', self._("Bouquets index")),
			('/usr/share/enigma2/picon', self._("Picon directory")),
			# FIX 0.48j: stampy sú teraz v persistent data dir-u, nie v /tmp
			(data_path('tvh_bouquet_refresh.stamp'),
				self._("TVH refresh stamp")),
			# Plugin data adresár — ukáže prehľad
			(get_data_dir(), self._("Plugin data dir")),
			# ArchivCZSK common log
			('/tmp/archivCZSK.log', self._("ArchivCZSK log")),
		]
		for path, label in paths_to_check:
			if os.path.exists(path):
				try:
					if os.path.isdir(path):
						count = sum(1 for _ in os.listdir(path)
						            if not _.startswith('.'))
						info = "%s (%d items)" % (path, count)
					else:
						sz = os.path.getsize(path)
						if sz > 1024 * 1024:
							sz_str = "%.1fMB" % (sz / 1024.0 / 1024.0)
						elif sz > 1024:
							sz_str = "%.1fKB" % (sz / 1024.0)
						else:
							sz_str = "%dB" % sz
						info = "%s (%s)" % (path, sz_str)
					self.add_dir("✓ " + label + ": " + info,
					             cmd=self.settings_menu)
				except Exception:
					self.add_dir("? " + label + ": " + path,
					             cmd=self.settings_menu)
			else:
				self.add_dir("✗ " + label + ": " + path + self._(" (missing)"),
				             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

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

	def _guess_tvh_error_hint(self, err):
		"""FIX 0.50beta: z technickej chybovej hlášky requests/urllib odhadne
		user-friendly hint čo má užívateľ skontrolovať v Nastaveniach.

		Pokrýva typické dôvody zlyhania pripojenia na TVH:
		- DNS chyba (Name or service not known, gaierror, getaddrinfo failed)
		  → "Server name not found — check 'host' in Settings"
		- Connection refused (TVH neštartol alebo zlý port)
		  → "Connection refused — wrong port or TVH not running"
		- Timeout (sieťová routovacia chyba alebo blokovaný firewall)
		  → "Connection timeout — check IP/host and firewall"
		- 401 Unauthorized (zlé credentials)
		  → "Authentication failed — check username/password"
		- 403 Forbidden (user nemá oprávnenia)
		  → "Forbidden — TVH user lacks permissions"
		- 404 Not Found (zlá API cesta — neštandardný TVH build?)
		  → "API endpoint not found — wrong TVH version?"
		- Iné: vráti None (volajúci ukáže len raw error riadok)
		"""
		if not err:
			return None
		e = str(err).lower()
		# Poradie matters — niektoré errors môžu mať viacero kľúčových slov
		if ('name or service not known' in e or 'gaierror' in e or
		    'getaddrinfo failed' in e or 'temporary failure in name resolution' in e or
		    'nodename nor servname' in e):
			return self._("⚠ Server name not found — check 'host' field in Settings")
		if 'connection refused' in e or 'econnrefused' in e:
			return self._("⚠ Connection refused — wrong port, or TVH server not running")
		if 'timed out' in e or 'timeout' in e:
			return self._("⚠ Connection timeout — check IP/host, network and firewall")
		if '401' in e or 'unauthorized' in e or 'authentication failed' in e:
			return self._("⚠ Authentication failed — check username and password")
		if '403' in e or 'forbidden' in e:
			return self._("⚠ Forbidden — TVH user lacks API permissions")
		if '404' in e or 'not found' in e:
			return self._("⚠ API endpoint not found — wrong TVH version or path?")
		if 'no route to host' in e or 'ehostunreach' in e or 'network is unreachable' in e:
			return self._("⚠ No route to host — check network connection")
		if 'ssl' in e or 'certificate' in e:
			return self._("⚠ SSL/certificate error — try disabling HTTPS or fix cert")
		return None

	def _render_tvh_error_lines(self, err, max_lines=3, max_chars=150):
		"""FIX 0.48i: rozdelí multi-line error string a pridá ho ako 1-3
		add_dir položky. Cieľ: aby užívateľ videl aj underlying error
		(typicky druhý riadok z api_get wrapper-a), nie len wrapper text
		"Tvheadend API request failed.".

		Volajúci je zodpovedný za pridanie retry položky pred týmto.
		"""
		if not err:
			return
		# Rozdeľ na riadky, vyfiltruj prázdne, oreže každý na max_chars
		parts = [p.strip() for p in err.split('\n') if p.strip()]
		for i, part in enumerate(parts[:max_lines]):
			prefix = "✗ " if i == 0 else "  → "
			title = self._("Last error") if i == 0 else self._("Detail")
			self.add_dir(prefix + part[:max_chars],
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': title})

	def live_root(self):
		if not self._check_tvh_silent():
			# FIX 0.48h: rozlíšenie stavov + retry položka pri transient failure
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH temporarily unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				# FIX 0.50beta: hint → skip raw error (čistejšie UI)
				hint = self._guess_tvh_error_hint(err)
				if hint:
					self.add_dir(hint,
					             cmd=self.settings_menu,
					             info_labels={'title': self._("Open settings")})
				else:
					# FIX 0.48i: full multi-line error namiesto len err[:80]
					self._render_tvh_error_lines(err)
			else:
				self.add_dir(
					self._("✗ Tvheadend server not configured. Open Settings to fill in host, username, password."),
					cmd=self.settings_menu,
					info_labels={'title': self._("TVH not configured")})
			return

		self.add_dir(self._("All"), cmd=self.live_channels, cat_id='')

		try:
			tags = self.tvh.get_tags()
		except Exception as e:
			# FIX 0.48h: nezostať s len "All" tichom — invaliduj cache (lebo
			# get_tags zlyhalo aj keď check_login pred chvíľou OK) a ponúkni retry
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(self._("⟳ Failed to load categories — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		tags = sorted(tags, key=lambda t: (_tag_sort_key(t), _norm_name(t.get('name') or '')))

		for t in tags:
			name = t.get('name') or ''
			uuid = t.get('uuid') or ''
			if not uuid:
				continue
			self.add_dir(name, cmd=self.live_channels, cat_id=uuid)

	def live_channels(self, cat_id=''):
		if not self._check_tvh_silent():
			# FIX 0.48h: namiesto tichého prázdneho zoznamu ponúkni retry
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				# FIX 0.48i: zobraz aj underlying error pre diagnostiku
				self._render_tvh_error_lines(err)
			return

		try:
			channels = self.tvh.get_channels_by_tag(cat_id) if cat_id else self.tvh.get_channels()
		except Exception:
			# FIX 0.48h: rovnaký pattern — invaliduj cache + ponúkni retry
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(self._("⟳ Failed to load channels — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
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
		if not self._check_tvh_silent():
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
		if not self._check_tvh_silent():
			# FIX 0.48h: rozlíšenie stavov + retry pri transient
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				# FIX 0.48i: zobraz aj underlying error
				self._render_tvh_error_lines(err)
			else:
				self.add_dir(
					self._("✗ Tvheadend server not configured. Open Settings to fill in host, username, password."),
					cmd=self.settings_menu,
					info_labels={'title': self._("TVH not configured")})
			return

		try:
			entries  = _get_dvr_finished_cached(self.tvh)
			channels = self.tvh.get_channels()
		except Exception:
			# FIX 0.48h: namiesto tichého empty → retry
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(self._("⟳ Failed to load archive — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
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
			# FIX 0.48h: zobrazuj len názov kanála bez čísla v zátvorke.
			# Poradie zoznamu sa naďalej riadi `num` (sort key vyššie),
			# len label sa neformátuje s "(num)". Day count ('- 8 dní') ostáva.
			label = name
			if day_cnt > 0:
				label = '%s - %d %s' % (label, day_cnt, self._('days'))
			self.add_dir(
				label, img=icon, info_labels={'title': label},
				cmd=self.archive_dates, channel_id=cid, channel_name=name
			)

	def recently_watched(self):
		"""FIX 0.52beta: Render zoznamu posledne sledovaných DVR nahrávok.

		Načíta `_load_watched_history()` (JSON v data dir-u, persistent
		cez reboot E2), pre každý UUID hľadá aktuálnu DVR entry v cache.
		Ak entry už neexistuje (user ju vymazal v TVH), preskočí ju.
		Zoradenie podľa naposledy otvoreného (ts desc).

		Plus pridáva kontextové menu "Vymazať históriu" na vyčistenie
		zoznamu (cez ArchivCZSK menu/INFO tlačidlo... ale to je nice-to-have,
		pre teraz necháme bez clear akcie — user môže zmazať data dir
		manuálne ak chce reset).
		"""
		if not self._check_tvh_silent():
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				hint = self._guess_tvh_error_hint(err)
				if hint:
					self.add_dir(hint,
					             cmd=self.settings_menu,
					             info_labels={'title': self._("Open settings")})
			return

		history = _load_watched_history()
		if not history:
			self.add_dir(
				self._("History is empty — start watching something."),
				info_labels={'title': self._("Recently watched")})
			return

		try:
			entries = _get_dvr_finished_cached(self.tvh) or []
		except Exception:
			self.add_dir(
				self._("⟳ Failed to load archive — tap to retry"),
				cmd=self.action_retry_tvh_root,
				info_labels={'title': self._("Retry")})
			return

		# Index aktuálnych entries cez UUID pre rýchly lookup
		by_uuid = {}
		for e in entries:
			uuid = e.get('uuid')
			if uuid:
				by_uuid[uuid] = e

		# Sortuj history podľa naposledy otvoreného (ts desc)
		sorted_history = sorted(history.items(),
		                        key=lambda kv: kv[1].get('ts', 0),
		                        reverse=True)

		shown = 0
		stale = 0
		for uuid, hist_entry in sorted_history:
			fresh_entry = by_uuid.get(uuid)
			if fresh_entry is None:
				# Entry bola vymazaná z TVH archívu — preskoč.
				# Mohli by sme ju aj odstrániť z history JSON, ale
				# uložené dáta sú malé a možno sa entry obnoví neskôr.
				stale += 1
				continue
			# Render rovnaký formát ako iné DVR menu (0.55beta:
			# show_resume=True pridá " (▶ MM:SS)" sufix ak entry má
			# zaznamenanú resume pozíciu).
			self._add_dvr_entry_item(fresh_entry, episode_format=False,
			                          show_resume=True)
			shown += 1

		if shown == 0:
			# Všetky entries v history boli medzitým zmazané z TVH
			self.add_dir(
				self._("Watched entries no longer exist in DVR archive."),
				info_labels={'title': self._("Recently watched")})

	def search(self, keyword=None, search_id=''):
		"""FIX 0.52beta: Vyhľadávanie v DVR archíve podľa názvu (bez diakritiky).

		ArchivCZSK framework volá túto metódu po tom, čo používateľ klikol
		na položku pridanú cez `add_search_dir()` a zadal text v keyboard
		popup-e. Signature `(keyword, search_id)` musí presne sedieť — inak
		framework hodí TypeError.

		Match je case-insensitive a diacritic-insensitive — typing 'Na noze'
		nájde 'Na nože', 'Markiza' nájde 'Markíza', atď. Pomocná funkcia
		_strip_accents_lower (modul-level) normalizuje text cez NFD + Mn
		filter, rovnaký mechanizmus ako pri klasifikácii DVR entries.

		Match scope: 'disp_title' + 'disp_subtitle'. Description sa
		nematchuje aby sa user nedostal k záplave false-positive výsledkov.

		Deduplikácia kľúčom (title, subtitle[:80]) — 7×24 autorec
		duplikáty sa zoskupia do jedného výsledku.

		Limit: 200 výsledkov (UI by sa pri tisíckach položiek stalo
		nepoužiteľným). Pri overflow sa zobrazí info že je limit.
		"""
		if not self._check_tvh_silent():
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				hint = self._guess_tvh_error_hint(err)
				if hint:
					self.add_dir(hint,
					             cmd=self.settings_menu,
					             info_labels={'title': self._("Open settings")})
			else:
				self.add_dir(
					self._("✗ Tvheadend server not configured."),
					cmd=self.settings_menu,
					info_labels={'title': self._("TVH not configured")})
			return

		if not keyword or len(keyword.strip()) < 2:
			self.add_dir(
				self._("Please type at least 2 characters."),
				info_labels={'title': self._("Search")})
			return

		query = _strip_accents_lower(keyword.strip())

		try:
			entries = _get_dvr_finished_cached(self.tvh) or []
		except Exception as e:
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(
				self._("⟳ Failed to load archive — tap to retry"),
				cmd=self.action_retry_tvh_root,
				info_labels={'title': self._("Retry")})
			return

		# Match + dedup + collect timestamps pre triedenie podľa recency
		seen = set()
		matches = []
		for e in entries:
			title = e.get('disp_title') or ''
			subtitle = e.get('disp_subtitle') or ''
			if not title and not subtitle:
				continue
			norm_t = _strip_accents_lower(title)
			norm_s = _strip_accents_lower(subtitle)
			if query not in norm_t and query not in norm_s:
				continue
			# Dedup kľúč (rovnaký ako _get_classified_dvr 7x24 dedup)
			key = (norm_t, norm_s[:80])
			if key in seen:
				continue
			seen.add(key)
			matches.append(e)

		if not matches:
			self.add_dir(
				self._("✗ Nothing found for: %s") % keyword,
				info_labels={
					'title': self._("Search"),
					'plot': self._("Try a shorter or simpler query. "
					               "Diacritics are ignored.")
				})
			return

		# Sortuj podľa najnovších záznamov (start_real desc)
		matches.sort(key=lambda e: e.get('start_real') or 0, reverse=True)

		# Limit + info ak je overflow
		LIMIT = 200
		total = len(matches)
		if total > LIMIT:
			self.add_dir(
				self._("Found %d results — showing first %d (most recent). "
				       "Refine the search for fewer results.") % (total, LIMIT),
				info_labels={'title': self._("Search")})
			matches = matches[:LIMIT]
		else:
			self.add_dir(
				self._("Found %d result(s) for: %s") % (total, keyword),
				info_labels={'title': self._("Search")})

		# Render results — rovnaký formát ako iné DVR menu (date · sub · channel)
		for e in matches:
			self._add_dvr_entry_item(e, episode_format=False)

	def archive_dates(self, channel_id, channel_name=None):
		# FIX 0.50beta: namiesto tichého empty zoznamu pri TVH transient
		# failure ukáž retry položku (paralela s archive_channels).
		# Predtým: user klikne na kanál v Archíve, TVH momentálne nedostupný,
		# zobrazí sa len ".." (parent) — vyzeralo to ako prázdny archív.
		if not self._check_tvh_silent():
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(self._("⟳ TVH unreachable — tap to retry"),
				             cmd=self.action_retry_tvh_root,
				             info_labels={'title': self._("Retry TVH")})
				self._render_tvh_error_lines(err)
			return

		try:
			entries = _get_dvr_finished_cached(self.tvh)
		except Exception:
			# FIX 0.50beta: tiež retry namiesto tichého empty
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(self._("⟳ Failed to load archive — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
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
		if not self._check_tvh_silent():
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

	# ------------------------------------------------------------------
	# FIX 0.49 (+0.49b): Top-level kategorizácia DVR
	# ------------------------------------------------------------------
	def archive_by_category(self, cat_id):
		"""Top-level otvorenie kategórie.

		FIX 0.49b:
		- Pre Filmy a Seriály ukáže najprv podžánre (Drama/Sci-fi/Komédia/...)
		- Pre ostatné kategórie priamo plochý zoznam záznamov
		- Pre Seriály v "Iné" zachová pôvodné správanie (zoznam sérií)
		"""
		if not self._check_tvh_silent():
			# FIX 0.48h: rozlíšenie stavov + retry pri transient
			_, reason, err = self.get_tvh_state()
			if reason == 'unreachable':
				self.add_dir(
					self._("⟳ TVH unreachable — tap to retry"),
					cmd=self.action_retry_tvh_root,
					info_labels={'title': self._("Retry TVH")})
				self._render_tvh_error_lines(err)
			else:
				self.add_dir(
					self._("✗ Tvheadend server not configured."),
					cmd=self.settings_menu,
					info_labels={'title': self._("TVH not configured")})
			return

		try:
			by_top, by_subcat, _counts, series_by_canonical, series_subcat_titles \
				= _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
		except Exception:
			try:
				self._invalidate_tvh_login_cache()
			except Exception:
				pass
			self.add_dir(self._("⟳ Failed to load archive — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		# Filmy → ukáž podžánre
		if cat_id == _CAT_FILM:
			for sub_id, sub_label in _MOVIE_SUBCAT_LABELS:
				entries = by_subcat.get((_CAT_FILM, sub_id), [])
				if not entries:
					continue
				self.add_dir(self._(sub_label),
				             info_labels={'title': self._(sub_label)},
				             cmd=self.archive_movie_subgenre,
				             sub_id=sub_id)
			return

		# Seriály → ukáž podžánre seriálov
		if cat_id == _CAT_SERIAL:
			for sub_id, sub_label in _MOVIE_SUBCAT_LABELS:
				titles = series_subcat_titles.get((_CAT_SERIAL, sub_id))
				if not titles:
					continue
				self.add_dir(self._(sub_label),
				             info_labels={'title': self._(sub_label)},
				             cmd=self.archive_series_subgenre,
				             sub_id=sub_id)
			return

		# FIX 0.49c/d: Ostatné kategórie s podžánrami cez registry
		# (Šport, Spravodajstvo, Šou, Detské, Hudba, Umenie, Dokumenty, Hobby)
		cfg = _SUBCAT_REGISTRY.get(cat_id)
		if cfg and cfg[1] is not None:
			labels = cfg[0]
			for sub_id, sub_label in labels:
				entries = by_subcat.get((cat_id, sub_id), [])
				if not entries:
					continue
				self.add_dir(self._(sub_label),
				             info_labels={'title': self._(sub_label)},
				             cmd=self.archive_generic_subgenre,
				             top_cat=cat_id, sub_id=sub_id)
			return

		# Kategórie bez podžánrov (napr. Nezaradené) — plochý zoznam
		entries = by_top.get(cat_id) or []
		for e in entries:
			self._add_dvr_entry_item(e)

	def archive_movie_subgenre(self, sub_id):
		"""FIX 0.49b: Plochý zoznam filmov v sub-žánre (napr. Filmy → Akčné)."""
		if not self._check_tvh_silent():
			return

		try:
			_by_top, by_subcat, _, _, _ = _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
		except Exception:
			self.add_dir(self._("⟳ Failed to load — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		entries = by_subcat.get((_CAT_FILM, sub_id)) or []
		for e in entries:
			self._add_dvr_entry_item(e)

	def archive_generic_subgenre(self, top_cat, sub_id):
		"""FIX 0.49d: Generická metóda na zobrazenie záznamov v podžánre
		ktoréhokoľvek top kategórie (Spravodajstvo, Šou, Detské, Hudba,
		Umenie, Dokumenty, Hobby, aj Šport).

		Pre Filmy a Seriály ostávajú samostatné metódy (archive_movie_subgenre,
		archive_series_subgenre) lebo Seriály ukazujú zoznam titulov nie
		zoznam epizód.
		"""
		if not self._check_tvh_silent():
			return

		try:
			_by_top, by_subcat, _, _, _ = _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
		except Exception:
			self.add_dir(self._("⟳ Failed to load — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		entries = by_subcat.get((top_cat, sub_id)) or []
		for e in entries:
			self._add_dvr_entry_item(e)

	def archive_series_subgenre(self, sub_id):
		"""FIX 0.49b: Zoznam sérií v rámci sub-žánru (napr. Seriály → Krimi).

		Po kliku na sériu sa otvorí zoznam jej epizód.
		"""
		if not self._check_tvh_silent():
			return

		try:
			_, _, _, series_by_canonical, series_subcat_titles \
				= _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
		except Exception:
			self.add_dir(self._("⟳ Failed to load — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		titles = series_subcat_titles.get((_CAT_SERIAL, sub_id)) or set()
		# Sort: najnovšia epizoda desc
		sorted_titles = sorted(
			titles,
			key=lambda t: _ts(series_by_canonical[t][0])
			              if series_by_canonical.get(t) else 0,
			reverse=True
		)
		for title in sorted_titles:
			eps = series_by_canonical.get(title) or []
			# Ikona z najnovšej epizódy
			icon = None
			if eps:
				try:
					icon = self.tvh.make_icon_url(
						eps[0].get('channel_icon') or None)
				except Exception:
					pass
			# FIX 0.49b: bez počtu epizód v zátvorke
			self.add_dir(title, img=icon,
			             info_labels={'title': title},
			             cmd=self.archive_series,
			             series_title=title)

	def archive_series(self, series_title):
		"""Zobrazí epizódy konkrétneho seriálu, najnovšie prvé.

		FIX 0.49b: series_title je teraz canonical title (bez "(N)" sufixu).
		"""
		if not self._check_tvh_silent():
			return

		try:
			_, _, _, series_by_canonical, _ = _get_classified_dvr(_get_dvr_finished_cached(self.tvh))
		except Exception:
			self.add_dir(self._("⟳ Failed to load — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		eps = series_by_canonical.get(series_title) or []
		if not eps:
			self.add_dir(self._("(no episodes found)"),
			             cmd=self.root,
			             info_labels={'title': series_title})
			return

		for e in eps:
			self._add_dvr_entry_item(e, episode_format=True)

	def _add_dvr_entry_item(self, e, episode_format=False, show_resume=False):
		"""Pomocný helper — pridá jednu položku DVR záznamu do menu.

		Spoločný kód pre archive_by_category, archive_movie_subgenre,
		archive_series. episode_format=True dáva inu form-u labelu
		(prefer X/Y vs full title).

		FIX 0.55beta: show_resume=True pridá "▶ MM:SS" sufix za labelom
		ak entry má zaznamenanú resume pozíciu. Default False — používa
		sa len v recently_watched() aby user vedel kde môže pokračovať.
		"""
		title = e.get('disp_title') or e.get('title') or self._("Recording")
		sub = (e.get('disp_subtitle') or '').strip()
		ts = _ts(e)
		dstr = datetime.fromtimestamp(ts).strftime('%d.%m. %H:%M') if ts > 0 else ''
		ch = e.get('channelname') or ''

		if episode_format:
			# Vnútri seriálu — preferuj "X/Y" alebo "(N)" prefix
			m = _SUBTITLE_SERIES_PATTERN.match(sub)
			if m:
				ep_part = sub[:m.end()].strip()
				rest = sub[m.end():].strip()[:60]
				if rest:
					label = '%s · %s · %s · %s' % (ep_part, rest, dstr, ch)
				else:
					label = '%s · %s · %s' % (ep_part, dstr, ch)
			else:
				# Skús extrahovat "(N)" z title (Otec Brown IV (1)).
				# FIX 0.50beta: strippe tech markery z konca title PRED
				# regex search-om. Predtým "(1) (ST) (HD)" zlyhalo na
				# _TITLE_EPISODE_PATTERN (regex chce \s*(?:\([A-Z]{1,3}\))?\s*$
				# = max 1 tech marker, ale tu sú 2). Po strippe ostáva "(1)"
				# čisté a regex match funguje.
				clean_title = _strip_tech_markers(title)
				m2 = _TITLE_EPISODE_PATTERN.search(clean_title)
				if m2:
					ep_n = m2.group(1)
					try:
						if not (1900 <= int(ep_n) <= 2099):
							short_sub = sub[:50] if sub else ''
							if short_sub:
								label = '(%s) · %s · %s · %s' % (
									ep_n, short_sub, dstr, ch)
							else:
								label = '(%s) · %s · %s' % (ep_n, dstr, ch)
						else:
							label = '%s · %s · %s' % (dstr, sub[:60] or title, ch)
					except ValueError:
						label = '%s · %s · %s' % (dstr, sub[:60] or title, ch)
				else:
					short_sub = sub[:60] if sub else title
					label = '%s · %s · %s' % (dstr, short_sub, ch)
		else:
			# Vonku (Filmy, Dokumenty, atď.) — "datum · title · channel"
			parts = [p for p in (dstr, title, ch) if p]
			label = ' · '.join(parts)

		# FIX 0.55beta: hviezdičkový marker pre už pozreté entries
		# (≥80 % duration). Sosáč-style sufix ' *' za labelom — diakritika-
		# safe, žiadne Unicode glyph dependencies, fungujú na všetkých
		# E2 skinoch a fontoch.
		try:
			if _is_fully_watched(e.get('uuid')):
				label = label + ' *'
		except Exception:
			pass

		# FIX 0.55beta: resume marker "▶ MM:SS" v recently_watched listingu —
		# user na prvý pohľad vidí kde môže pokračovať. Show_resume parameter
		# je default False; zapína sa len v recently_watched() handler-i.
		if show_resume:
			try:
				pos, _dur = _get_watched_position(e.get('uuid'))
				if pos and pos >= 30:  # pod 30s nemá zmysel zobrazovať
					mins = int(pos) // 60
					secs = int(pos) % 60
					if mins >= 60:
						hrs = mins // 60
						mins = mins % 60
						label = label + ' (▶ %d:%02d:%02d)' % (hrs, mins, secs)
					else:
						label = label + ' (▶ %d:%02d)' % (mins, secs)
			except Exception:
				pass

		icon = self.tvh.make_icon_url(e.get('channel_icon') or None)
		self.add_video(
			label, img=icon,
			info_labels=self._dvr_info_labels(label, e),
			cmd=self.play_dvr, entry=e, download=False
		)

	def play_dvr(self, entry):
		if not self._check_tvh_silent():
			return

		# FIX 0.52beta: track open into watched history (root menu shortcut)
		try:
			_track_watched(entry)
		except Exception:
			pass

		url   = self.tvh.make_dvr_url(entry.get('url') or '')
		title = entry.get('disp_title') or entry.get('channelname') or self._("DVR")

		# FIX 0.55beta: resume playback od poslednej pozície (sosáč-style).
		# Ak má entry zaznamenanú position z predošlého stop event-u a
		# user má toggle 'save_last_play_pos' zapnutý (default ON), pošli
		# resume_time_sec do framework streamer-a — ArchivCZSK ho prevezme
		# z settings a streamer začne od tej sekundy.
		#
		# Nepokračuj ak position == 0 (entry už dokončená / auto-cleared
		# nad 95 %) alebo ak position je menšia ako 30s (príliš začiatok,
		# nemá zmysel resume-ovať pár sekúnd).
		settings = self._player_settings() or {}
		try:
			save_resume = self.get_setting('save_last_play_pos')
			save_resume = bool(save_resume) if isinstance(save_resume, bool) \
				else str(save_resume).strip().lower() in ('true', '1', 'yes')
		except Exception:
			save_resume = True  # default ON

		if save_resume:
			try:
				pos, _dur = _get_watched_position(entry.get('uuid'))
				if pos and pos >= 30:
					settings['resume_time_sec'] = int(pos)
			except Exception:
				pass

		# 0.55beta: send data_item=entry so stats() callback (volaný
		# frameworkom pri end/next playback eventu) môže correlate
		# position s konkrétnou DVR entry.
		self.add_play(
			title, url,
			info_labels={'title': title},
			data_item=entry,
			settings=settings,
			live=False,
			download=True,
		)

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		"""FIX 0.55beta: ArchivCZSK framework callback po skončení
		playback-u. Pri action=='end' / 'next' framework dáva position
		(sekundy kde sa playback zastavil) a duration (celková dĺžka).

		Uložíme do watched_history.json aby _is_fully_watched()
		vedela označiť entry hviezdičkou v archive listing-u, a
		_get_watched_position() vedela ponúknuť resume pri ďalšom play.

		Auto-clear: ak position prekročí 95 % z duration, _set_watched_position
		vynuluje position (film dohraný, pri ďalšom play sa pustí od
		začiatku — ale hviezdičkový marker zostane lebo duration sa
		zachovala).
		"""
		try:
			if not isinstance(data_item, dict):
				return
			action_lower = (action or '').lower()
			if action_lower not in ('end', 'next'):
				return
			# Skontroluj setting (user môže mať tracking úplne vypnutý)
			try:
				save_resume = self.get_setting('save_last_play_pos')
				save_resume = bool(save_resume) if isinstance(save_resume, bool) \
					else str(save_resume).strip().lower() in ('true', '1', 'yes')
			except Exception:
				save_resume = True
			if not save_resume:
				return
			_set_watched_position(data_item, position, duration)
		except Exception:
			# Defensive — stats() callback nesmie nikdy crashnúť plugin,
			# je to ne-kritická feature.
			try:
				self.log_info('stats() callback failed (silently): %s' % sys.exc_info()[1])
			except Exception:
				pass

	# ------------------------------------------------------------------
	# get_url_by_channel_key – volané z HTTP handlera a bouquet generátora
	# ------------------------------------------------------------------

	def get_url_by_channel_key(self, channel_uuid):
		# FIX 0.48: light-weight login namiesto plného login(silent=True).
		# Plný login zbytočne spúšťa cleanup, picon worker, bouquet refresh
		# check — to všetko pri každom playback-u.
		#
		# FIX 0.57.0 (skyjet PR #22 review #10): vstup je teraz plain
		# channel UUID (framework PlayliveTVHTTPRequestHandler.decode_channel_key()
		# robí base64 decode v handler-i). Predtým bol vstup base64-encoded
		# key a metoda robila vlastný decode block.
		if not self._quick_login_for_http_handler():
			# TVH momentálne neodpovedá → zatvor HTTP handler s 404
			raise AddonErrorException('Tvheadend not reachable')

		channel_uuid = (channel_uuid or '').strip()
		if not channel_uuid:
			raise AddonErrorException('Missing or empty channel uuid')

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
