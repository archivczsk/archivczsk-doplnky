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

# FIX 0.48c (skyjet review #15): používať tools_archivczsk.string_utils.strip_accents
# namiesto vlastnej implementácie cez unicodedata. Fallback ostáva pre prípad
# že by tools_archivczsk verzia nemal tento helper.
try:
	from tools_archivczsk.string_utils import strip_accents as _strip_accents_tool
except Exception:
	_strip_accents_tool = None

def _strip_accents_compat(s):
	"""Vráti string bez diakritiky. Preferuje tools_archivczsk helper,
	pri jeho nedostupnosti používa lokálny unicodedata fallback."""
	if not s:
		return ''
	if _strip_accents_tool is not None:
		try:
			return _strip_accents_tool(s)
		except Exception:
			pass
	try:
		s = unicodedata.normalize('NFKD', s)
		return ''.join(c for c in s if not unicodedata.combining(c))
	except Exception:
		return s

from .tvheadend import Tvheadend

try:
	from .bouquet import TvheadendBouquetXmlEpgGenerator
except Exception:
	TvheadendBouquetXmlEpgGenerator = None

# M3U external source manager (optional - plugin works without it)
try:
	from .m3u_manager import M3URefreshManager
except Exception:
	M3URefreshManager = None

# FIX 0.48f: hardcoded M3U bouquet filename prefix (predtým configurable
# setting m3u_bouquet_prefix). Import s fallback aby plugin fungoval aj
# keď je m3u_bouquet modul nedostupný.
try:
	from .m3u_bouquet import M3U_BOUQUET_PREFIX
except Exception:
	M3U_BOUQUET_PREFIX = 'm3u_iptv'


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

# DVR entries cache – používame tools_archivczsk ExpiringLRUCache
try:
	from tools_archivczsk.cache import ExpiringLRUCache as _ExpiringLRUCache
	_DVR_CACHE = _ExpiringLRUCache(1, default_timeout=60)
except Exception:
	_DVR_CACHE = None
_DVR_CACHE_TS = 0
_DVR_CACHE_TTL = 60

# Bouquet auto-refresh stamp
_BOUQUET_REFRESH_STAMP = data_path("tvh_bouquet_refresh.stamp")

# FIX 0.48e: stamp pre auto-EPG-inject. Synchronizovaný s bouquet.py kde sa
# zapisuje po každej úspešnej injekcii. Provider číta tento súbor v
# _maybe_auto_inject_epg() na rozhodnutie či treba spustiť ďalšiu injekciu.
_EPG_INJECT_STAMP = data_path("tvh_epg_inject.stamp")

# FIX 0.48g: paralelný stamp pre M3U-side EPG injection.
# Zapisuje sa z m3u_manager.refresh_now() aj inject_epg_only().
_EPG_INJECT_STAMP_M3U = data_path("m3u_epg_inject.stamp")

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
				print('[plugin.tvheadend] poster cache cleanup: removed %d stale files' % removed)
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

import re as _re_dvr  # alias aby sa neprenášal _re v iných miestach
import unicodedata as _unicodedata_dvr


# FIX 0.49d: Helper na strippe diakritiky a lower-case textu pred regex match.
# Slovenské/české keyword matching by inak failovalo na "spr[á]vy" vs "sprav"
# (a vs á sú rôzne znaky aj s IGNORECASE flagom). Riešenie: pre matching
# si text aj keywords ponechávame bez diakritiky. Pridanie diakritiky v
# keywordoch (každý znak ako alternácia [aá]) by zložitosť regexov výrazne
# zhoršilo. Strippe je O(n) a O(15µs) per call — zanedbateľné.
def _strip_accents_lower(s):
	"""Vráti text bez diakritiky a v lowercase. Pre regex match."""
	if not s:
		return ''
	# NFD: 'á' → 'a' + combining acute
	nfd = _unicodedata_dvr.normalize('NFD', s)
	# Filter combining marks (category Mn = Mark, nonspacing)
	stripped = ''.join(c for c in nfd if _unicodedata_dvr.category(c) != 'Mn')
	return stripped.lower()


# --------------------------------------------------------------------------
# Regex patterns
# --------------------------------------------------------------------------
# "25/31 ..." v subtitle (CT/Nova OLD formát)
_SUBTITLE_SERIES_PATTERN = _re_dvr.compile(r'^\s*\d+/\d+\b')

# "(N)" alebo "(N) (XX)" na konci title — N je 1-9999 (epizoda alebo rok)
_TITLE_EPISODE_PATTERN = _re_dvr.compile(
	r'\((\d{1,4})\)\s*(?:\([A-Z]{1,3}\))?\s*$'
)

# Single tech/audio/subtitle marker — rozšír ak narazíš na ďalší.
# Pozn.: DTS-HD musí byť pred DTS aby alternace zachytila dlhšiu variantu.
_TECH_MARKER = (
	r'(?:DD5\.1|DTS-HD|DTS-MA|UHD|DTS|5\.1|7\.1|ST|HD|AD|SS|3D|DD|TT|P)'
)
# FIX 0.56beta (backport Kodi 1.0.2 fix): parens s 1+ tech markermi v
# jednej zátvorke, oddelenými čiarkou alebo lomkou (s alebo bez whitespace).
# Predtým regex match-oval len single token v zátvorke — kombinácie ako
# "(AD,ST)" alebo "(HD, DD5.1)" nezachytil, ich rozdielne stripping
# narúšalo episode grouping (rovnaký seriál s rôznymi tech flagmi
# končil ako separate "samostatné" entries vedľa hlavnej skupiny).
# Rieši napr.: "(AD,ST)", "(HD, DD5.1)", "(AD/ST)", "(AD, ST, HD)".
_TECH_MARKER_PATTERN = _re_dvr.compile(
	r'\s*\(\s*' + _TECH_MARKER +
	r'(?:\s*[,/]\s*' + _TECH_MARKER + r')*\s*\)\s*',
	_re_dvr.IGNORECASE
)


def _strip_tech_markers(text):
	"""Odstráni '(ST)', '(HD)', '(AD)', '(AD,ST)', '(HD, DD5.1)' atď. z textu."""
	if not text:
		return ''
	return _TECH_MARKER_PATTERN.sub(' ', text).strip()


def _has_episode_suffix(title):
	"""True ak title končí '(N)' a N je epizoda (nie rok 1900-2099)."""
	clean = _strip_tech_markers(title)
	m = _TITLE_EPISODE_PATTERN.search(clean)
	if not m:
		return False
	try:
		n = int(m.group(1))
	except (ValueError, TypeError):
		return False
	# Rok výroby filmu (typicky 1900-2099) → toto nie je epizoda
	if 1900 <= n <= 2099:
		return False
	# Inak (1-1899, 2100+) → epizoda
	if 1 <= n <= 9999:
		return True
	return False


def _series_canonical_title(title):
	"""Strip episode suffix + tech markers — aby sa epizódy toho istého seriálu
	dali grupovať pod jeden názov.

	"Otec Brown IV (1)"   → "Otec Brown IV"
	"Otec Brown IV (2)"   → "Otec Brown IV"
	"Cesty domů II (31) (ST)" → "Cesty domů II"
	"Casablanca (1942)"   → "Casablanca (1942)"  (rok, nie epizoda)
	"""
	if not title:
		return ''
	clean = _strip_tech_markers(title).strip()
	m = _TITLE_EPISODE_PATTERN.search(clean)
	if m:
		try:
			n = int(m.group(1))
			# Strip iba ak N NIE JE rok výroby
			if not (1900 <= n <= 2099):
				clean = clean[:m.start()].strip()
		except (ValueError, TypeError):
			pass
	return clean


# --------------------------------------------------------------------------
# Top-level kategórie
# --------------------------------------------------------------------------
_CAT_FILM           = 'film'
_CAT_SERIAL         = 'serial'
_CAT_SPRAVODAJSTVO  = 'spravodajstvo'
_CAT_SHOW           = 'show'
_CAT_SPORT          = 'sport'
_CAT_DETSKE         = 'detske'
_CAT_HUDBA          = 'hudba'
_CAT_UMENIE         = 'umenie'
_CAT_DOKUMENTY      = 'dokumenty'
_CAT_HOBBY          = 'hobby'
_CAT_INE            = 'ine'

# DVB EIT content_type (top nibble) → naša kategória.
_CT_TO_CAT_BASE = {
	2:  _CAT_SPRAVODAJSTVO,
	3:  _CAT_SHOW,
	4:  _CAT_SPORT,
	5:  _CAT_DETSKE,
	6:  _CAT_HUDBA,
	7:  _CAT_UMENIE,
	8:  _CAT_SHOW,            # Social/Political magazíny → spojené so Show
	9:  _CAT_DOKUMENTY,
	10: _CAT_HOBBY,
	# 0, 1, 11 sa riešia inde:
	#   1  = film vs seriál heuristika
	#   0, 11 = keyword fallback
}

# Poradie a slovenské label-y. FIX 0.49b: bez počtu (užívateľ chcel počty preč)
_CAT_LABELS_ORDER = (
	(_CAT_FILM,           'Filmy'),
	(_CAT_SERIAL,         'Seriály'),
	(_CAT_SPORT,          'Šport'),
	(_CAT_SPRAVODAJSTVO,  'Spravodajstvo'),
	(_CAT_SHOW,           'Šou / Relácie'),
	(_CAT_DETSKE,         'Detské'),
	(_CAT_HUDBA,          'Hudba'),
	(_CAT_UMENIE,         'Umenie / Kultúra'),
	(_CAT_DOKUMENTY,      'Dokumenty / Vzdelávacie'),
	(_CAT_HOBBY,          'Voľný čas / Hobby'),
	(_CAT_INE,            'Nezaradené'),
)


# --------------------------------------------------------------------------
# Podžánre (sub-categories) pre Filmy a Seriály
# --------------------------------------------------------------------------
_MV_AKCNY       = 'mv_akcny'
_MV_DRAMA       = 'mv_drama'
_MV_KOMEDIA     = 'mv_komedia'
_MV_KRIMI       = 'mv_krimi'
_MV_SCIFI       = 'mv_scifi'
_MV_ROMANTIKA   = 'mv_romantika'
_MV_HOROR       = 'mv_horor'
_MV_DOBRODR     = 'mv_dobrodruzny'
_MV_ANIMAK      = 'mv_animovany'
_MV_HISTORICKY  = 'mv_historicky'
_MV_WESTERN     = 'mv_western'
_MV_INE         = 'mv_ine'

_MOVIE_SUBCAT_LABELS = (
	(_MV_AKCNY,      'Akčné'),
	(_MV_KOMEDIA,    'Komédia'),
	(_MV_KRIMI,      'Krimi / Thriller / Detektívka'),
	(_MV_DRAMA,      'Drama'),
	(_MV_SCIFI,      'Sci-fi / Fantasy'),
	(_MV_ROMANTIKA,  'Romantické'),
	(_MV_HOROR,      'Horor'),
	(_MV_DOBRODR,    'Dobrodružné'),
	(_MV_ANIMAK,     'Animované'),
	(_MV_HISTORICKY, 'Historické / Vojnové'),
	(_MV_WESTERN,    'Western'),
	(_MV_INE,        'Iné'),
)

# DVB genre byte → sub-kategória (ak je dostupný v entry.genre)
_DVB_GENRE_TO_SUBCAT = {
	# 0x10 (16) = Movie/drama general — bez ďalšieho upresnenia → keyword fallback
	0x11: _MV_KRIMI,       # Detective/Thriller
	0x12: _MV_DOBRODR,     # Adventure/Western/War
	0x13: _MV_SCIFI,       # SF/Fantasy/Horror
	0x14: _MV_KOMEDIA,     # Comedy
	0x15: _MV_DRAMA,       # Soap/Melodrama/Folkloric
	0x16: _MV_ROMANTIKA,   # Romance
	0x17: _MV_HISTORICKY,  # Serious/Classical/Historical
	0x18: _MV_DRAMA,       # Adult — drama
}

# DVB Level 2 nibble decoding (FIX 0.53beta — z Kodi 1.0.4 portu).
# Keď je dostupný full 8-bit DVB genre kód (cca 6.5% entries), Level 2
# nibble priamo určuje sub-kategóriu pre non-film/serial kategórie —
# šport (0x40-0x4b), hudba (0x60-0x6b), arts (0x70-0x7b), dokumenty
# (0x90-0x9f), hobby (0xa0-0xaf). Funkcie _dvb_l2_sport_subgenre atď.
# použijú tieto mappingy pred keyword fallback-om (riešené v subgenre_fn
# pre každú kategóriu).

# Keyword regex → sub-kategória. PORADIE má význam: high-specificity first
# (krimi pred drama atď.).
# FIX 0.49d: keywords sú bez diakritiky a lowercase — match sa robí proti
# strippnutemu textu (cez _strip_accents_lower). re.IGNORECASE flag tým
# pádom nepotrebujeme.
# Horror keyword pattern — checkuje SAMOSTATNE proti title (FIX 0.53beta).
# Predtým bol horor v _KEYWORD_TO_SUBCAT spolu s ostatnými a matchol aj v
# description ("hrůza války" → war film padol do Horor). Teraz: horor patrí
# k filmu len ak slovo "horor/horror/desiv/hruz" je v title (nie subtitle,
# nie description). Ostatné podžánre matchujú proti celému textu — sú menej
# náchylné na false positives lebo "kriminálnik" v opise znamená naozaj krimi.
_HORROR_TITLE_PATTERN = _re_dvr.compile(r'\b(horor|horror|desiv|hruz)')

# Re-ordered _KEYWORD_TO_SUBCAT bez horor patternu (presunutý hore — FIX 0.53beta).
# Tiež: specifickejšie žánre majú prednosť pred genericky horor — historické,
# krimi, sci-fi, animované first. (Anyway, horor je teraz handled separately
# in _movie_subgenre cez _HORROR_TITLE_PATTERN.)
_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(detektiv|kriminal|krimi|thriller|vraz|policajn|vysetrov)'),
	 _MV_KRIMI),
	(_re_dvr.compile(r'\b(sci-?fi|sci\.\s?fi|fantasy|vedeckofant|vesmirn|mimozem|robot|kybern)'),
	 _MV_SCIFI),
	(_re_dvr.compile(r'\b(komedi|veselohra|humor|grotesk|sitcom)'),
	 _MV_KOMEDIA),
	(_re_dvr.compile(r'\b(romantick|milostn|romant)'),
	 _MV_ROMANTIKA),
	(_re_dvr.compile(r'\b(akcn|action|honic|prestrelk)'),
	 _MV_AKCNY),
	(_re_dvr.compile(r'\b(western|kovbo)'),
	 _MV_WESTERN),
	(_re_dvr.compile(r'\b(historick|valecn|vojensk|vojnov|histori)'),
	 _MV_HISTORICKY),
	(_re_dvr.compile(r'\b(dobrodruz|adventur|exped|cestopis)'),
	 _MV_DOBRODR),
	(_re_dvr.compile(r'\b(animovan|kreslen|animak|loutkov|cartoon|anime)'),
	 _MV_ANIMAK),
	(_re_dvr.compile(r'\b(drama|dramati)'),
	 _MV_DRAMA),
)


# --------------------------------------------------------------------------
# Sport sub-kategórie (FIX 0.49c)
# --------------------------------------------------------------------------
_SP_FUTBAL      = 'sp_futbal'
_SP_HOKEJ       = 'sp_hokej'
_SP_BASKETBAL   = 'sp_basketbal'
_SP_TENIS       = 'sp_tenis'
_SP_VOLEJBAL    = 'sp_volejbal'
_SP_HADZANA     = 'sp_hadzana'
_SP_ATLETIKA    = 'sp_atletika'
_SP_CYKLISTIKA  = 'sp_cyklistika'
_SP_MOTORSPORT  = 'sp_motorsport'
_SP_BOJOVE      = 'sp_bojove'
_SP_ZIMNE       = 'sp_zimne'
_SP_VODNE       = 'sp_vodne'
_SP_NEWS        = 'sp_news'
_SP_INE         = 'sp_ine'

_SPORT_SUBCAT_LABELS = (
	(_SP_FUTBAL,      'Futbal'),
	(_SP_HOKEJ,       'Hokej'),
	(_SP_BASKETBAL,   'Basketbal'),
	(_SP_TENIS,       'Tenis'),
	(_SP_VOLEJBAL,    'Volejbal'),
	(_SP_HADZANA,     'Hádzaná'),
	(_SP_ATLETIKA,    'Atletika'),
	(_SP_CYKLISTIKA,  'Cyklistika'),
	(_SP_MOTORSPORT,  'Motorsport'),
	(_SP_BOJOVE,      'Bojové športy'),
	(_SP_ZIMNE,       'Zimné športy'),
	(_SP_VODNE,       'Vodné športy'),
	(_SP_NEWS,        'Športové spravodajstvo'),
	(_SP_INE,         'Iné'),
)

# Keyword → sport sub-cat. PORADIE má význam:
#   - Sport news najprv (lebo "Sportovní noviny" by mohli matchovať aj iné)
#   - Pak explicitné názvy športov (Basketbal:, Volejbal:, Hádzaná:)
#   - Pak ligy a značky (UEFA, NHL, IIHF, MONACObet, ...)
#   - Najmenej špecifické na koniec
# FIX 0.49d: keywords bez diakritiky — text sa normalizuje pred match
_SPORT_KEYWORD_TO_SUBCAT = (
	# Sport news — high priority pred individual sport keywords
	(_re_dvr.compile(r'\b(sportovni\s+noviny|sportove\s+noviny|sport\s+news|'
	                 r'spravy\s+zo\s+sportu|sportovni\s+studio|sports?\s+report|'
	                 r'polední\s+sport|odpoledni\s+sport)'),
	 _SP_NEWS),
	# Hokej — IIHF, NHL, KHL, hokej, hockey, ZOH hokej
	(_re_dvr.compile(r'\b(hokej|hockey|nhl|iihf|khl|hokejov)'),
	 _SP_HOKEJ),
	# Bojové športy pred futbalom kvôli "UFC"
	(_re_dvr.compile(r'\b(ufc|mma|oktagon|pml|kickbox|k-1|judo|karate|wrestl|'
	                 r'zapas|sumo|taekwon|grappling)'),
	 _SP_BOJOVE),
	(_re_dvr.compile(r'\bbox(er|ing|u|y)?\b'),
	 _SP_BOJOVE),
	# Futbal — UEFA, MONACObet, Niké liga, Premier League, Bundesliga, La Liga
	(_re_dvr.compile(r'\b(futbal|football|uefa|monacobet|nike\s+liga|niké\s+liga|'
	                 r'tipsport\s+liga|fortuna\s+liga|premier\s+league|bundesliga|'
	                 r'la\s+liga|champion(s)?\s+league|europa\s+league|conference\s+league|'
	                 r'ligue\s+1|serie\s+a\b|el\s+uefa|cl\s+uefa)'),
	 _SP_FUTBAL),
	# Basketbal
	(_re_dvr.compile(r'\b(basketbal|basketbol|nba|euroliga\s+basketbal|sbl|wnba)'),
	 _SP_BASKETBAL),
	# Volejbal
	(_re_dvr.compile(r'\b(volejbal|volleyball)'),
	 _SP_VOLEJBAL),
	# Hádzaná
	(_re_dvr.compile(r'\b(hadzana|handball)'),
	 _SP_HADZANA),
	# Tenis
	(_re_dvr.compile(r'\b(tenis|tennis|atp|wta|wimbledon|roland\s+garros|'
	                 r'us\s+open|australian\s+open|french\s+open)'),
	 _SP_TENIS),
	# Cyklistika
	(_re_dvr.compile(r'\b(cyklist|tour\s+de\s+france|giro\s+d|vuelta)'),
	 _SP_CYKLISTIKA),
	# Motorsport
	(_re_dvr.compile(r'\b(formula|formule|f1\b|motogp|wrc|rally|nascar|'
	                 r'moto2|moto3|velka\s+cena|grand\s+prix)'),
	 _SP_MOTORSPORT),
	# Zimné športy — ZOH, lyžovanie, biatlon, snowboard, Cortina
	(_re_dvr.compile(r'\b(zoh|olympi.*zimn|zimn.*olympi|lyzov|lyziarsk|'
	                 r'biatlon|snowboard|sjazd|slalom|krasokorcul|cortina\s+2026|'
	                 r'milano\s+cortina)'),
	 _SP_ZIMNE),
	# Vodné športy
	(_re_dvr.compile(r'\b(kanoistik|plavan|plav(ec|ky)|jachting|surf|veslov|'
	                 r'kayaking|swimming|vodn[ey]\s+polo|vodne\s+slalom|'
	                 r'rychlostna\s+kanoistik)'),
	 _SP_VODNE),
	# Atletika
	(_re_dvr.compile(r'\b(atletik|atletic|athletics|maraton|marathon|'
	                 r'beh\s+na|skok\s+do|hod\s+ostepom|dialk)'),
	 _SP_ATLETIKA),
)


# FIX 0.50beta: pred 0.50 mal každý sub-žáner top kategórie (Šport,
# Spravodajstvo, Šou, Detské, Hudba, Umenie, Dokumenty, Hobby) vlastnú
# 9-riadkovú funkciu _XYZ_subgenre(entry) s úplne identickou body
# logikou (compose text → strip_accents_lower → regex iter → return).
# Celkom 9 takmer identických definícií, ~80 riadkov boilerplate-u.
# FIX 0.50beta: nahradené factory funkciou `_make_subgenre_fn(patterns,
# default)`, ktorá vráti closure s identickou semantikou. Public mená
# funkcií (_sport_subgenre, _news_subgenre, ...) ostávajú zachované —
# používame ich v _SUBCAT_REGISTRY a v UI flow.
def _make_subgenre_fn(patterns, default_subcat):
	"""Vyrobí subgenre-classifier closure pre dané keyword patterns +
	fallback subcat. Text na klasifikáciu sa skladá z disp_title +
	disp_subtitle + disp_description + channelname, normalizuje sa
	bez diakritiky a lowercase, pak iteruje cez regex patterns
	v poradí (poradie = priorita)."""
	def _classify(entry):
		text = ((entry.get('disp_title') or '') + ' ' +
		        (entry.get('disp_subtitle') or '') + ' ' +
		        (entry.get('disp_description') or '') + ' ' +
		        (entry.get('channelname') or ''))
		if not text.strip():
			return default_subcat
		text = _strip_accents_lower(text)
		for pattern, subcat in patterns:
			if pattern.search(text):
				return subcat
		return default_subcat
	return _classify


_sport_subgenre = _make_subgenre_fn(_SPORT_KEYWORD_TO_SUBCAT, _SP_INE)


# ==========================================================================
# FIX 0.49d: Podžánre pre ostatné top kategórie
# (Spravodajstvo, Šou/Relácie, Detské, Hudba, Umenie, Dokumenty, Voľný čas)
# ==========================================================================
# Pre tieto kategórie nepotrebujeme DVB genre mapovanie (nie je definované
# pre sub-žánre v týchto top-cat-och) ani channel-based hints (môžu prísť
# z hociakého kanála). Použijeme len keyword scan v title + subtitle +
# description + channelname. PORADIE keywordov má význam — specific najprv.
# ==========================================================================

# -------- Spravodajstvo (News) --------
_NW_HLAVNE      = 'nw_hlavne'        # Hlavné správy bulletinu
_NW_POLITIKA    = 'nw_politika'      # Politické diskusie, komentáre
_NW_KRIMI       = 'nw_krimi'         # Krimi noviny, investigatíva
_NW_MAGAZINY    = 'nw_magaziny'      # Spravodajské magazíny
_NW_POCASIE     = 'nw_pocasie'       # Počasie
_NW_INE         = 'nw_ine'

_NEWS_SUBCAT_LABELS = (
	(_NW_HLAVNE,    'Hlavné správy'),
	(_NW_POLITIKA,  'Politika / Diskusie'),
	(_NW_KRIMI,     'Krimi / Reportáže'),
	(_NW_MAGAZINY,  'Magazíny / Lifestyle'),
	(_NW_POCASIE,   'Počasie'),
	(_NW_INE,       'Iné'),
)

_NEWS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(pocasi|predpoved|predpovid)'),
	 _NW_POCASIE),
	(_re_dvr.compile(r'\b(krimi\s+noviny|reporter|reportaz|investigativ|'
	                 r'tajomstv|kriminal(ne)?\s+sprav|cernin)'),
	 _NW_KRIMI),
	(_re_dvr.compile(r'\b(politik|diskusia|diskuse|debata|otazk|otazky\s+vaclava|'
	                 r'studio\s+6|o\s+5\s+minut\s+12|polemika|interview\s+plus|'
	                 r'partia|sobotne\s+dial)'),
	 _NW_POLITIKA),
	(_re_dvr.compile(r'\b(magazin|spravodajsky\s+magazin|reflex\b|'
	                 r'7\s+dni|plus\s+7|fokus|profil|lifestyle)'),
	 _NW_MAGAZINY),
	(_re_dvr.compile(r'\b(noviny|sprav[yi]|udalosti|hlavni\s+sprav|hlavne\s+sprav|'
	                 r'tv\s+noviny|112\b|noviny\s+plus|teleráno|telerano|'
	                 r'spravy\s+rtvs|sledovanie\s+spravodajstv|spravodajstv)'),
	 _NW_HLAVNE),
)


_news_subgenre = _make_subgenre_fn(_NEWS_KEYWORD_TO_SUBCAT, _NW_INE)


# -------- Šou / Relácie (Show) --------
_SH_REALITY     = 'sh_reality'       # Reality show — Farmer, Survivor
_SH_TALK        = 'sh_talk'          # Talk show
_SH_SUTAZ       = 'sh_sutaz'         # Súťažné show — talent, X Factor
_SH_KUCHARSKE   = 'sh_kucharske'     # Kuchárske — MasterChef, Ano šéfe
_SH_ZABAVA      = 'sh_zabava'        # Humor, satira, estráda
_SH_MAGAZINY    = 'sh_magaziny'      # Magazíny ako Klíč, Reflex
_SH_INE         = 'sh_ine'

_SHOW_SUBCAT_LABELS = (
	(_SH_REALITY,    'Reality show'),
	(_SH_SUTAZ,      'Súťažné show / Talenty'),
	(_SH_KUCHARSKE,  'Kuchárske show'),
	(_SH_TALK,       'Talk show'),
	(_SH_ZABAVA,     'Zábava / Humor'),
	(_SH_MAGAZINY,   'Magazíny'),
	(_SH_INE,        'Iné'),
)

_SHOW_KEYWORD_TO_SUBCAT = (
	# Kuchárske najprv (lebo "show" v texte by ich zachytilo)
	(_re_dvr.compile(r'\b(kucharsk|masterchef|hell\'?s\s+kitchen|'
	                 r'ano,?\s+sefe|jamie\s+oliver|recept|kuchar|kucharka|'
	                 r'gordon\s+ramsay)'),
	 _SH_KUCHARSKE),
	# Reality show
	(_re_dvr.compile(r'\b(reality\s?show|farmer|farma\b|survivor|big\s+brother|'
	                 r'rande|love\s+island|vyzva\b|prezit|hlada\s+sa|holky\s+z|'
	                 r'mama\s+ja\s+chcem)'),
	 _SH_REALITY),
	# Súťažné show / talenty
	(_re_dvr.compile(r'\b(talent\b|x\s?factor|got\s+talent|the\s+voice|'
	                 r'superstar|tvoja\s+tvar|hviezda|dancing\s+with|'
	                 r'cesko\s+slovenska|stardance|let\'?s\s+dance)'),
	 _SH_SUTAZ),
	# Talk show
	(_re_dvr.compile(r'\b(talk\s?show|show\s+jana\s+krausa|late\s+night|'
	                 r'kraus\b|particka|cestou\s+necestou|vy(2|3|4)\s+show)'),
	 _SH_TALK),
	# Magazíny (vrátane Klíč, Reflex, lifestyle)
	(_re_dvr.compile(r'\b(magazin|reflex\b|zivot\s+v\s+luxuse|'
	                 r'plus\s+7\s+dni|5\s+proti\s+5|inkognito|klic|'
	                 r'lifestyle|polopate)'),
	 _SH_MAGAZINY),
	# Zábava / humor
	(_re_dvr.compile(r'\b(zabavn|humor|estrad|skecz|stand-?up|parodi|'
	                 r'sranda|veselohra|kabaret|satira)'),
	 _SH_ZABAVA),
)


_show_subgenre = _make_subgenre_fn(_SHOW_KEYWORD_TO_SUBCAT, _SH_INE)


# -------- Detské (Children) --------
_CH_ANIMAK      = 'ch_animak'        # Animované, kreslené
_CH_ROZPRAVKY   = 'ch_rozpravky'     # Rozprávky, pohádky
_CH_VZDELAVAC   = 'ch_vzdelavac'     # Vzdelávacie (Kouzelná školka)
_CH_FILMY       = 'ch_filmy'         # Detské filmy
_CH_INE         = 'ch_ine'

_CHILDREN_SUBCAT_LABELS = (
	(_CH_ANIMAK,     'Animované / Kreslené'),
	(_CH_ROZPRAVKY,  'Rozprávky'),
	(_CH_VZDELAVAC,  'Vzdelávacie'),
	(_CH_FILMY,      'Filmy pre deti'),
	(_CH_INE,        'Iné'),
)

_CHILDREN_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(rozpravk|pohadk|princ\b|princezn|'
	                 r'kralovstvo|carodej)'),
	 _CH_ROZPRAVKY),
	(_re_dvr.compile(r'\b(animovan|kreslen|loutkov|cartoon|anime|animak)'),
	 _CH_ANIMAK),
	(_re_dvr.compile(r'\b(kouzeln[aé]?\s+skolk|studio\s+kamar|vzdelavac|'
	                 r'vyuka|naucn|edukacn|do\s+skoly)'),
	 _CH_VZDELAVAC),
	(_re_dvr.compile(r'\b(detsk[yi]\s+film|pre\s+deti\s+film|family\s+film|'
	                 r'rodinny\s+film)'),
	 _CH_FILMY),
)


_children_subgenre = _make_subgenre_fn(_CHILDREN_KEYWORD_TO_SUBCAT, _CH_INE)


# -------- Hudba (Music) --------
_MU_KLASIKA     = 'mu_klasika'       # Klasická hudba, opera
_MU_KONCERT     = 'mu_koncert'       # Koncerty (pop/rock/jazz)
_MU_HITY        = 'mu_hity'          # Hitparáda, popové show
_MU_FOLK        = 'mu_folk'          # Folk, country, ľudovka
_MU_MAGAZINY    = 'mu_magaziny'      # Hudobné magazíny
_MU_INE         = 'mu_ine'

_MUSIC_SUBCAT_LABELS = (
	(_MU_KONCERT,   'Koncerty'),
	(_MU_KLASIKA,   'Klasická hudba / Opera'),
	(_MU_HITY,      'Hitparáda / Pop'),
	(_MU_FOLK,      'Folk / Country / Ľudová'),
	(_MU_MAGAZINY,  'Hudobné magazíny'),
	(_MU_INE,       'Iné'),
)

_MUSIC_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(klasick[ay]\s+hudb|opera|symfoni|filharmon|'
	                 r'orchester|orchestr|arie|arij|koncert\s+klasick|smetanova|'
	                 r'ma\s+vlast)'),
	 _MU_KLASIKA),
	(_re_dvr.compile(r'\b(koncert\b|live\s+concert|tour\s+(world|live)|'
	                 r'mtv\s+live|unplugged)'),
	 _MU_KONCERT),
	(_re_dvr.compile(r'\b(folk\b|country|ludova\s+hudba|lidova\s+hudba|'
	                 r'cimbal|ludovk|lidovk|ciganska\s+hudba|folklor)'),
	 _MU_FOLK),
	(_re_dvr.compile(r'\b(hitparad|top\s+\d+|chart|charts|pop\b|popmusic|'
	                 r'pisnicky\s+z\s+obrazovky|videoklip)'),
	 _MU_HITY),
	(_re_dvr.compile(r'\b(hudobn[ye]\s+magaz|music\s+news|hudba\s+\d|hudobnik)'),
	 _MU_MAGAZINY),
)


_music_subgenre = _make_subgenre_fn(_MUSIC_KEYWORD_TO_SUBCAT, _MU_INE)


# -------- Umenie / Kultúra (Arts) --------
_AR_DIVADLO     = 'ar_divadlo'       # Divadlo, opera
_AR_FILM        = 'ar_film'          # Filmové umenie, dokumenty o filme
_AR_VYTVARNE    = 'ar_vytvarne'      # Výtvarné umenie
_AR_LITERATURA  = 'ar_literatura'    # Literatúra, knihy
_AR_INE         = 'ar_ine'

_ARTS_SUBCAT_LABELS = (
	(_AR_DIVADLO,    'Divadlo'),
	(_AR_FILM,       'Filmové umenie'),
	(_AR_VYTVARNE,   'Výtvarné umenie / Maľba'),
	(_AR_LITERATURA, 'Literatúra / Knihy'),
	(_AR_INE,        'Iné'),
)

_ARTS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(divadl|theater|inscenace|cinohra|opera\s+plus|baletn|'
	                 r'cinoherni)'),
	 _AR_DIVADLO),
	(_re_dvr.compile(r'\b(vytvarn|malba|maliarstv|socharst|galeri|'
	                 r'umelci|umelec|art\s+(gallery|show)|vystav)'),
	 _AR_VYTVARNE),
	(_re_dvr.compile(r'\b(literatur|literar|knih[ay]|kniha\b|spisovate|'
	                 r'roman\b|prozaik|poezi|basen|kniznic)'),
	 _AR_LITERATURA),
	(_re_dvr.compile(r'\b(filmov[ey]\s+umen|filmov[ya]\s+klasik|filmovi\s+tvorco|'
	                 r'reziser|kameraman|filmari)'),
	 _AR_FILM),
)


_arts_subgenre = _make_subgenre_fn(_ARTS_KEYWORD_TO_SUBCAT, _AR_INE)


# -------- Dokumenty / Vzdelávacie (Documentaries) --------
_DC_PRIRODA     = 'dc_priroda'       # Príroda, zvieratá
_DC_HISTORIA    = 'dc_historia'      # História, archeológia
_DC_VEDA        = 'dc_veda'          # Veda, technika, vesmír
_DC_CESTOPIS    = 'dc_cestopis'      # Cestopis, geografia
_DC_SPOLOCNOST  = 'dc_spolocnost'    # Spoločnosť, ekonomika, politika
_DC_OSOBNOSTI   = 'dc_osobnosti'     # Biografie, portréty
_DC_INE         = 'dc_ine'

_DOCS_SUBCAT_LABELS = (
	(_DC_PRIRODA,    'Príroda / Zvieratá'),
	(_DC_HISTORIA,   'História / Archeológia'),
	(_DC_VEDA,       'Veda / Technika / Vesmír'),
	(_DC_CESTOPIS,   'Cestopisy / Geografia'),
	(_DC_SPOLOCNOST, 'Spoločnosť / Politika'),
	(_DC_OSOBNOSTI,  'Osobnosti / Biografie'),
	(_DC_INE,        'Iné'),
)

_DOCS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(prirod|zviera|zvire|zivocich|zivocisn|'
	                 r'fauna|flora|narodny\s+park|narodni\s+park|safari|'
	                 r'ocean|dzungla|jerab|orel|sokol|tiger|delfin|velryba|'
	                 r'animal\s+planet|kralovstvo\s+divociny|kralovstvi\s+divociny)'),
	 _DC_PRIRODA),
	(_re_dvr.compile(r'\b(histori|dejiny|stredovek|stredovek|archeo|'
	                 r'antick|stara\s+civiliza|imperi|cisar|kral|'
	                 r'pyramid|rimsk|grecka\s+civi|stredovek)'),
	 _DC_HISTORIA),
	(_re_dvr.compile(r'\b(veda|vedeck|fyzik|chemi|biolog|'
	                 r'matematik|technika|technolog|vesmir|kozmos|'
	                 r'planeta|nasa|esa\s+\w|raketa|vynalez|umela\s+inteligenci)'),
	 _DC_VEDA),
	(_re_dvr.compile(r'\b(cestopis|cesty|cestou\s+necestou|krajiny|cestovate|'
	                 r'expedici|expedice|geografi|narody\s+sveta)'),
	 _DC_CESTOPIS),
	(_re_dvr.compile(r'\b(biografi|portret\s+osob|osobnost|zivotopis|zivot\s+a\s+dielo|'
	                 r'pamati|memoare|spomienky\s+na|zivot\s+a\s+\w)'),
	 _DC_OSOBNOSTI),
	(_re_dvr.compile(r'\b(spoloc|spolecn|ekonom|politick[ay]\s+dokum|kapitalizm|'
	                 r'globali|investigativ\s+dokum|chudoba|migra|trzn[ay]\s+ekonomik)'),
	 _DC_SPOLOCNOST),
)


_docs_subgenre = _make_subgenre_fn(_DOCS_KEYWORD_TO_SUBCAT, _DC_INE)


# -------- Voľný čas / Hobby --------
_HB_ZAHRADA     = 'hb_zahrada'       # Záhrada
_HB_BYVANIE     = 'hb_byvanie'       # Bývanie, renovácie
_HB_VARENIE     = 'hb_varenie'       # Vaření (hobby — nie show)
_HB_AUTO        = 'hb_auto'          # Auto, moto, technika
_HB_CESTOVANIE  = 'hb_cestovanie'    # Cestovanie
_HB_ZDRAVIE     = 'hb_zdravie'       # Zdravie, životospráva, fitness
_HB_DIY         = 'hb_diy'           # DIY, kutilstvo
_HB_INE         = 'hb_ine'

_HOBBY_SUBCAT_LABELS = (
	(_HB_ZAHRADA,    'Záhrada'),
	(_HB_BYVANIE,    'Bývanie / Renovácie'),
	(_HB_VARENIE,    'Vaření / Recepty'),
	(_HB_AUTO,       'Auto / Moto'),
	(_HB_CESTOVANIE, 'Cestovanie'),
	(_HB_ZDRAVIE,    'Zdravie / Fitness'),
	(_HB_DIY,        'Kutilstvo / DIY'),
	(_HB_INE,        'Iné'),
)

_HOBBY_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(zahrad|kvetin|sklenik|tri\s+v\s+zahrade|'
	                 r'okrasn[ay]\s+rastlin)'),
	 _HB_ZAHRADA),
	(_re_dvr.compile(r'\b(byvan|interier|renovac|architektur|'
	                 r'rekonstruk|nabytk|kuchyna\s+(snov|sna|dizajn)|bydleni)'),
	 _HB_BYVANIE),
	(_re_dvr.compile(r'\b(varen|recept|jedl[oa]|kuchar(stvo|ka|i)?|'
	                 r'peciem|s\s+kuchar|kucharka|babickovy)'),
	 _HB_VARENIE),
	(_re_dvr.compile(r'\b(auto\b|moto\b|automobil|motorka|automotive|'
	                 r'autosalon|garaz)'),
	 _HB_AUTO),
	(_re_dvr.compile(r'\b(cestovan|cestujeme|destinac|hotel\s+test|'
	                 r'vylety|vylet\s+po|destination|on\s+the\s+road|cestopis|'
	                 r'z\s+metropol)'),
	 _HB_CESTOVANIE),
	(_re_dvr.compile(r'\b(zdrav[ie]\s+|fitness|cvicen|wellness|'
	                 r'beh\s+v\s+meste|zivotospravu|chudnut)'),
	 _HB_ZDRAVIE),
	(_re_dvr.compile(r'\b(kutil|diy\b|hand\s+made|vlastnorucn|svojpomocn|'
	                 r'workshop|tvorime|dilna)'),
	 _HB_DIY),
)


_hobby_subgenre = _make_subgenre_fn(_HOBBY_KEYWORD_TO_SUBCAT, _HB_INE)


# --------------------------------------------------------------------------
# Title-based sci-fi/fantasy franchise override (FIX 0.53beta — z Kodi 1.0.5)
# --------------------------------------------------------------------------
# Známe sci-fi/fantasy franchise tituly — keyword scan v opise nezachytí,
# lebo distributori opisujú plot (vojna, pomsta, drama), nie žáner. Napr.
# Duna: Část druhá má v oficiálnom opise len "válečnou stezku pomsty" — bez
# slova sci-fi. Title-based override má prednosť pred keyword scan-om aj pred
# channel subgenre hint-om.
# Patterns anchored ku konkrétnym title-pozíciám (začiatok alebo s ":") pre
# dvojzmyselné mená (Batman, Hulk, Tenet, atď.) ktoré inak môžu byť v opise
# dokumentov mythológie/histórie.
_TITLE_SCIFI_PATTERNS = (
	_re_dvr.compile(r'^duna\b|\bduna\s*:|dune\b'),       # Duna / Dune
	_re_dvr.compile(r'\bstar\s*wars\b'),                 # Star Wars
	_re_dvr.compile(r'\bhvezdne\s*valky\b'),             # Hvězdné války
	_re_dvr.compile(r'\bstar\s*trek\b'),                 # Star Trek
	_re_dvr.compile(r'\bmatrix\b'),                      # Matrix
	_re_dvr.compile(r'^avatar\b|\bavatar\s*:'),          # Avatar
	_re_dvr.compile(r'\bterminator|\bterminat'),         # Terminátor
	_re_dvr.compile(r'\bblade\s*runner\b'),              # Blade Runner
	_re_dvr.compile(r'^pan\s+prsten|^pan\s+prstenu'),    # Pán prstenů / prsteňov
	_re_dvr.compile(r'^(hobit|hobbit)\b|:\s*(hobit|hobbit)\b'),  # Hobit
	_re_dvr.compile(r'\b(vetrelec|alien)\b'),            # Vetřelec / Alien
	_re_dvr.compile(r'\b(predator|predátor)\b'),         # Predator
	_re_dvr.compile(r'\btransformers\b'),                # Transformers
	_re_dvr.compile(r'\bspider-?man\b'),                 # Spider-Man
	_re_dvr.compile(r'^iron\s*man\b|\biron\s*man\s*:'),  # Iron Man (anchored)
	_re_dvr.compile(r'\bavengers\b'),                    # Avengers
	_re_dvr.compile(r'\bx-?men\b'),                      # X-Men
	_re_dvr.compile(r'\bhunger\s*games\b'),              # Hunger Games
	_re_dvr.compile(r'\bmaze\s*runner\b'),               # Maze Runner
	_re_dvr.compile(r'\bjurassic\b|\bjursk'),            # Jurassic / Jurský
	_re_dvr.compile(r'\binterstellar\b'),                # Interstellar
	_re_dvr.compile(r'\binception\b'),                   # Inception
	_re_dvr.compile(r'^tenet\b'),                        # Tenet (anchored - tenet=slovo)
	_re_dvr.compile(r'\bmen\s+in\s+black\b'),            # Men In Black
	_re_dvr.compile(r'\bmad\s+max\b'),                   # Mad Max
	_re_dvr.compile(r'\bedge\s+of\s+tomorrow\b'),        # Edge of Tomorrow
	_re_dvr.compile(r'\boblivion\b'),                    # Oblivion
	_re_dvr.compile(r'^gravity\b'),                      # Gravity (anchored)
	_re_dvr.compile(r'^ender|\bender.?s\s+game\b'),      # Ender's Game
	_re_dvr.compile(r'\bgodzilla\b|^king\s*kong\b|\bking\s*kong\s*:'),  # Godzilla / King Kong
	_re_dvr.compile(r'^superman\b|\bsuperman\s*:'),      # Superman (anchored)
	_re_dvr.compile(r'^batman\b|\bbatman\s*:|the\s+batman\b|\bdark\s+knight\b'),  # Batman
	_re_dvr.compile(r'\bdeadpool\b'),                    # Deadpool
	_re_dvr.compile(r'\bdoctor\s*strange\b'),            # Doctor Strange
	_re_dvr.compile(r'\bguardians\s+of\s+the\s+galax'),  # Guardians of the Galaxy
	_re_dvr.compile(r'\bjustice\s*league\b'),            # Justice League
	_re_dvr.compile(r'\bwonder\s*woman\b'),              # Wonder Woman
	_re_dvr.compile(r'\bharry\s*potter\b'),              # Harry Potter — fantasy override
)


def _title_franchise_scifi_match(entry):
	"""Vráti True ak title obsahuje známy sci-fi/fantasy franchise."""
	title = entry.get('disp_title') or ''
	if not title:
		return False
	title_only = _strip_accents_lower(title)
	for pat in _TITLE_SCIFI_PATTERNS:
		if pat.search(title_only):
			return True
	return False


# --------------------------------------------------------------------------
# Title corpus (FIX 0.53beta — z Kodi 1.0.6)
# --------------------------------------------------------------------------
# Statický corpus filmov a seriálov v každom žánri + lokalizované sk/cs
# preklady. Klasifikátor sa pýta corpus-u PRED keyword scan-om — title-based
# match je spoľahlivejší ako "drama" keyword v opise.
#
# Corpus súbor: resources/title_genre_corpus.json relatívne k provider.py.
# Lazy načítanie pri prvom volaní. Bez I/O ak corpus chýba (graceful fallback).
_CORPUS_CODE_TO_SUBCAT = {
	'ak': _MV_AKCNY,
	'ko': _MV_KOMEDIA,
	'kr': _MV_KRIMI,
	'dr': _MV_DRAMA,
	'sf': _MV_SCIFI,
	'ro': _MV_ROMANTIKA,
	'ho': _MV_HOROR,
	'do': _MV_DOBRODR,
	'an': _MV_ANIMAK,
	'hi': _MV_HISTORICKY,
	'we': _MV_WESTERN,
}

_CORPUS_STATE = {
	'loaded': False,
	'titles': {},    # normalized_title → subcat constant
	'load_error': None,
	'meta': None,
}


def _corpus_path():
	"""Vráti absolútnu cestu k corpus JSON súboru.

	provider.py je v plugin_video_tvheadend/, corpus je v
	plugin_video_tvheadend/resources/.
	"""
	here = os.path.dirname(os.path.abspath(__file__))
	return os.path.join(here, 'resources', 'title_genre_corpus.json')


def _load_corpus_if_needed():
	"""Lazy načítanie corpus-u. Idempotentné — volá sa pred každým lookup-om."""
	if _CORPUS_STATE['loaded']:
		return
	_CORPUS_STATE['loaded'] = True  # set early — jeden pokus o load, no retry loop
	path = _corpus_path()
	try:
		with io.open(path, 'r', encoding='utf-8') as f:
			data = json.load(f)
	except (IOError, OSError):
		_CORPUS_STATE['load_error'] = 'corpus file not found: %s' % path
		return
	except (ValueError,) as e:
		_CORPUS_STATE['load_error'] = 'corpus load failed: %s' % e
		return

	raw_titles = (data.get('titles') if isinstance(data, dict) else None) or {}
	out = {}
	for k, code in raw_titles.items():
		sub = _CORPUS_CODE_TO_SUBCAT.get(code)
		if sub is None or not isinstance(k, str):
			continue
		if k:
			out[k] = sub
	_CORPUS_STATE['titles'] = out
	_CORPUS_STATE['meta'] = data.get('_meta') if isinstance(data, dict) else None

	try:
		print('[plugin.tvheadend] title corpus loaded: %d entries' % len(out))
	except Exception:
		pass


# Regex na odstránenie "(YYYY)" suffixu — corpus tituly tento suffix nemajú.
_TITLE_YEAR_SUFFIX = _re_dvr.compile(r'\s*\(\s*(?:19|20)\d{2}\s*\)\s*$')


def _canonical_title_for_corpus(title):
	"""Normalizuje title pre corpus lookup. Musí ladiť s normalizáciou
	použitou pri tvorbe corpus JSON-u."""
	if not title:
		return ''
	t = _strip_tech_markers(title)
	t = _series_canonical_title(t)
	t = _TITLE_YEAR_SUFFIX.sub('', t).strip()
	return _strip_accents_lower(t)


def _corpus_subgenre_match(entry):
	"""Vráti subcat constant ak title match-ne v corpuse, inak None."""
	_load_corpus_if_needed()
	titles = _CORPUS_STATE['titles']
	if not titles:
		return None
	title = entry.get('disp_title') or ''
	key = _canonical_title_for_corpus(title)
	if not key:
		return None
	return titles.get(key)


# --------------------------------------------------------------------------
# Registry: mapuje top_cat → (labels, subgenre_fn)
# Použité v archive_by_category na rozhodnutie či pridať podžánre menu
# --------------------------------------------------------------------------
_SUBCAT_REGISTRY = {
	_CAT_FILM:           (_MOVIE_SUBCAT_LABELS,    None),   # špeciálne — viď archive
	_CAT_SERIAL:         (_MOVIE_SUBCAT_LABELS,    None),   # špeciálne — viď archive
	_CAT_SPORT:          (_SPORT_SUBCAT_LABELS,    _sport_subgenre),
	_CAT_SPRAVODAJSTVO:  (_NEWS_SUBCAT_LABELS,     _news_subgenre),
	_CAT_SHOW:           (_SHOW_SUBCAT_LABELS,     _show_subgenre),
	_CAT_DETSKE:         (_CHILDREN_SUBCAT_LABELS, _children_subgenre),
	_CAT_HUDBA:          (_MUSIC_SUBCAT_LABELS,    _music_subgenre),
	_CAT_UMENIE:         (_ARTS_SUBCAT_LABELS,     _arts_subgenre),
	_CAT_DOKUMENTY:      (_DOCS_SUBCAT_LABELS,     _docs_subgenre),
	_CAT_HOBBY:          (_HOBBY_SUBCAT_LABELS,    _hobby_subgenre),
}


def _movie_subgenre(entry):
	"""Vráti sub-kategóriu pre film/seriál.

	Logika (od 0.53beta — z Kodi 1.0.4/1.0.5/1.0.6 portu):
	1. DVB genre byte (ak je dostupný) → primary signal
	2. Title-based sci-fi franchise override (Duna, Star Wars, Matrix, …)
	   — keyword scan nezachytí lebo distributor opisuje plot, nie žáner
	3. Title corpus match (~1940 hand-curated titulov) → confident sub-genre
	4. Keyword scan title + subtitle + description → secondary signal
	5. Horror — len v title (FIX 0.53beta: bez tohto matchol aj v opise
	   "hrůza války" → war film padol do Horor)
	6. Inak _MV_INE
	"""
	# 1) DVB genre check
	for g in (entry.get('genre') or []):
		try:
			g = int(g)
		except (ValueError, TypeError):
			continue
		sub = _DVB_GENRE_TO_SUBCAT.get(g)
		if sub:
			return sub

	# 2) Title franchise sci-fi override (Duna, Star Wars, Matrix, …)
	title = entry.get('disp_title') or ''
	title_only = _strip_accents_lower(title)
	for pat in _TITLE_SCIFI_PATTERNS:
		if pat.search(title_only):
			return _MV_SCIFI

	# 3) Title corpus lookup
	corpus_sub = _corpus_subgenre_match(entry)
	if corpus_sub is not None:
		return corpus_sub

	# 4) Specifickejšie keyword scan
	text = ((entry.get('disp_title') or '') + ' ' +
	        (entry.get('disp_subtitle') or '') + ' ' +
	        (entry.get('disp_description') or ''))
	if not text.strip():
		return _MV_INE
	text = _strip_accents_lower(text)
	for pattern, subcat in _KEYWORD_TO_SUBCAT:
		if pattern.search(text):
			return subcat

	# 5) Horror — len v title
	if _HORROR_TITLE_PATTERN.search(title_only):
		return _MV_HOROR

	return _MV_INE


# --------------------------------------------------------------------------
# Channel-based hints (FIX 0.49b)
# --------------------------------------------------------------------------
# Niektoré kanály majú jednoznačnú orientáciu žánru — táto orientácia je
# spoľahlivejšia ako DVB content_type ktorý broadcast environment občas
# vypĺňa zle. Substring match v channelname (case-insensitive).
_CHANNEL_TOP_HINTS = (
	# Deti — CT :D, JOJ-ko, Disney, Nick atď.
	('ct :d',       _CAT_DETSKE),
	('ct d-art',    _CAT_DETSKE),
	('ct d/art',    _CAT_DETSKE),
	('decko',       _CAT_DETSKE),
	('jojko',       _CAT_DETSKE),
	('minimax',     _CAT_DETSKE),
	('cartoon',     _CAT_DETSKE),
	('disney',      _CAT_DETSKE),
	('nick',        _CAT_DETSKE),
	('boomerang',   _CAT_DETSKE),
	('baby tv',     _CAT_DETSKE),
	('duck tv',     _CAT_DETSKE),
	# Šport — substring 'sport' chytí Premier Sport, Nova Sport, Eurosport...
	('sport',       _CAT_SPORT),
	('eurosport',   _CAT_SPORT),
	('digi sport',  _CAT_SPORT),
	('nova sport',  _CAT_SPORT),
	('o2 sport',    _CAT_SPORT),
	# Spravodajstvo
	('cnn',         _CAT_SPRAVODAJSTVO),
	('bbc news',    _CAT_SPRAVODAJSTVO),
	('bbc world',   _CAT_SPRAVODAJSTVO),
	('ta3',         _CAT_SPRAVODAJSTVO),
	('ct24',        _CAT_SPRAVODAJSTVO),
	('ct 24',       _CAT_SPRAVODAJSTVO),
	('euronews',    _CAT_SPRAVODAJSTVO),
	# Hudba
	('ocko',        _CAT_HUDBA),
	('now 80',      _CAT_HUDBA),
	('now 90',      _CAT_HUDBA),
	('now rock',    _CAT_HUDBA),
	('mtv',         _CAT_HUDBA),
	('vh1',         _CAT_HUDBA),
	('mezzo',       _CAT_HUDBA),
	('óčko',        _CAT_HUDBA),
	# Dokumentárne kanály (FIX 0.53beta — z Kodi 1.0.4 portu).
	# Broadcasters často taggujú obsah na týchto kanáloch ako ct=1
	# (Movie/Drama) alebo ct=2 (News), čo nie je presné — drvivá väčšina
	# obsahu je documentary. Pre ct=0/1/2/9 doc channel hint vyhráva
	# (riešené v _determine_top_cat). Pre ct=3-10 explicit DVB tag
	# (Šport/Hudba/Šou) zostáva — športové news na doc kanáli má zmysel
	# klasifikovať podľa DVB tagu, nie ako documentary.
	('discovery',         _CAT_DOKUMENTY),
	('viasat history',    _CAT_DOKUMENTY),
	('viasat explore',    _CAT_DOKUMENTY),
	('viasat nature',     _CAT_DOKUMENTY),
	('viasat true crime', _CAT_DOKUMENTY),
	('national geographic', _CAT_DOKUMENTY),
	('nat geo',           _CAT_DOKUMENTY),
	('spektrum',          _CAT_DOKUMENTY),
	('animal planet',     _CAT_DOKUMENTY),
	('history channel',   _CAT_DOKUMENTY),
	('history hd',        _CAT_DOKUMENTY),
	('bbc earth',         _CAT_DOKUMENTY),
	('bbc knowledge',     _CAT_DOKUMENTY),
	('love nature',       _CAT_DOKUMENTY),
	('docubox',           _CAT_DOKUMENTY),
	('crime+investigation', _CAT_DOKUMENTY),
	('crime + investigation', _CAT_DOKUMENTY),
	# Krimi kanály — strong hint pre Filmy/Seriály sub-žáner
	# (HANDLED v _channel_subgenre_hint nižšie, nie tu — to je sub override)
)

# Channel name → movie/serial sub-genre hint (silnejší než keyword scan)
_CHANNEL_SUBCAT_HINTS = (
	('krimi',       _MV_KRIMI),       # JOJ KRIMI, Nova Krimi, Prima Krimi
	('action',      _MV_AKCNY),       # Nova Action
	('romantica',   _MV_ROMANTIKA),   # Nova Romantica
	('romantika',   _MV_ROMANTIKA),
	('comedy',      _MV_KOMEDIA),     # Comedy Central
	('cinema',      None),             # Nova Cinema, AXN Cinema — generic film
	('horror',      _MV_HOROR),
	('history',     _MV_HISTORICKY),
)


def _channel_top_hint(entry):
	"""Vráti top-level kategóriu na základe channelname, alebo None."""
	ch = (entry.get('channelname') or '').lower()
	if not ch:
		return None
	for substring, cat in _CHANNEL_TOP_HINTS:
		if substring in ch:
			return cat
	return None


def _channel_subgenre_hint(entry):
	"""Vráti sub-kategóriu na základe channelname, alebo None."""
	ch = (entry.get('channelname') or '').lower()
	if not ch:
		return None
	for substring, subcat in _CHANNEL_SUBCAT_HINTS:
		if substring in ch:
			return subcat
	return None


# --------------------------------------------------------------------------
# Series detection (FIX 0.49b: rozšírené)
# --------------------------------------------------------------------------
# Keywords v description ktoré naznačujú seriál (Czech/Slovak)
_SERIES_KEYWORDS = ('seriál', 'série', ' díl ', 'epizoda', 'epizóda',
                    'season ', 'episode ')


def _is_series_entry(entry):
	"""True ak je entry seriálom (na základe akéhokoľvek dostupného signálu).

	Detekuje 4 vzory:
	  1) "25/31 ..." v subtitle (CT/Nova old format)
	  2) "...(N)" sufix v title kde N nie je rok (Otec Brown IV (1))
	  3) episode_disp non-empty (TVH má explicit episode info)
	  4) keyword 'seriál'/'díl'/'epizoda' v description
	"""
	subtitle = (entry.get('disp_subtitle') or '').strip()
	if _SUBTITLE_SERIES_PATTERN.match(subtitle):
		return True

	title = (entry.get('disp_title') or '').strip()
	if _has_episode_suffix(title):
		return True

	if entry.get('episode_disp'):
		return True

	desc = ((entry.get('disp_description') or '') + ' ' + subtitle).lower()
	for kw in _SERIES_KEYWORDS:
		if kw in desc:
			return True

	return False


# --------------------------------------------------------------------------
# Fallback keyword guess pre Nezaradené (ct=0 alebo 11)
# FIX 0.53beta — z Kodi 1.0.4 + 1.0.7 portu:
#   - Detské: odstránený generický "detsk" pattern (matchol slovo "detský" v
#     opisoch home renovation shows). Iba explicitné detské markery zostávajú.
#   - Show: rozšírené o ~30 sk/cz reality/talk/cooking patternov ktoré
#     padali do _CAT_INE — Zámena manželiek, Top Gear, MasterChef atď.
#   - Hobby: nový pattern pre home/garden/design programmes
#     (Nové bývanie, Nová záhrada, Jak se staví sen).
# --------------------------------------------------------------------------
_FALLBACK_KEYWORD_TO_TOP = (
	# Šport
	(_re_dvr.compile(r'\b(futbal|hokej|tenis|golf|formula|f1|oktagon|liga|'
	                 r'majstrov|olympi|rally|cyklist|atletik|box|wrestlin|'
	                 r'biatlon|lyzovan|sjazd|mma|ufc|pml)'),
	 _CAT_SPORT),
	# Spravodajstvo
	(_re_dvr.compile(r'\b(spravodajstvo|sprav[yi]|udalosti|aktualn|reporter|noviny\s+tv|'
	                 r'tv\s+noviny|pocasi|uvodnik)'),
	 _CAT_SPRAVODAJSTVO),
	# Detské (FIX 0.53beta — odstránený generický 'detsk' ktorý matchol
	# "detský domov" v krimi reportáži, "detskú izbu" v design show, atď.
	# Iba explicitné detské markery zostávajú + konkrétne show formáty.)
	(_re_dvr.compile(r'\b(rozpravk|pohadk|pre\s+deti|pro\s+deti|pre\s+najmens|'
	                 r'kreslen[ay]|animovan[ay]|loutkov[ay]|'
	                 r'byl\s+jednou\s+jeden|fidlibum|miniatel|trpaslic|'
	                 r'labkov[aá]\s+patrol)'),
	 _CAT_DETSKE),
	# Hudba
	(_re_dvr.compile(r'\b(koncert|hudba|hudobn|hudebni|spevok|zpevak|spevak|'
	                 r'piesn|pisni|pop\s|rock\s|metal\s|klasick)'),
	 _CAT_HUDBA),
	# Šou (FIX 0.53beta — rozšírené o sk/cz reality/talk/cooking formáty)
	(_re_dvr.compile(r'\b(magazin|talk\s?show|\bshow\b|soutez|sutaz|'
	                 r'reality\s?show|farmer|farma|zabavn|estrada|kucharsk|'
	                 r'zamena\s+manzeliek|nebezpecne\s+vztahy|jak\s+to\s+dopadl|'
	                 r'intim\s+s\s|prima\s+pauza|najlepsie\s+viraln|'
	                 r'extremne\s+pripad|dokonaly\s+sef|utajeny\s+sef|spriznene\s+duse|'
	                 r'v\s+siedmom\s+nebi|poklad\s+z\s+pud|jak\s+se\s+stavi\s+sen|'
	                 r'ano\s+sefe|top\s+gear|masterchef|babicovy\s+tip|'
	                 r'varime\s+s|vareni\s+s|recept[aá]r|recepta?\s+prima|'
	                 r'babica\s+vs|co\s+bude\s+dnes\s+k\s+vecer|nase\s+zlepsovak|'
	                 r'afery\s+-?\s*neuver|rodinna\s+firma|vip\s+svet|na\s+plac|'
	                 r'exkluziv|zachranari|u\s+tebe\s+nebo\s+u\s+me|'
	                 r'nedorucena\s+tajemstv)'),
	 _CAT_SHOW),
	# Hobby (FIX 0.53beta — nový pattern pre home/garden/design)
	(_re_dvr.compile(r'\b(byvani[ae]?|byvanie|zahrad[ay]|zahradka|'
	                 r'navrhar|dizajn\s+|design\s+interier|'
	                 r'remeselni|stolarsk|truhlarsk|rybarsk[ay])'),
	 _CAT_HOBBY),
	# Dokumenty
	(_re_dvr.compile(r'\b(dokument|documentary|prirod|history|'
	                 r'vesmir|national\s+geographic|discovery)'),
	 _CAT_DOKUMENTY),
)


def _guess_top_category_from_keywords(entry):
	"""Pre záznamy s ct=0 alebo ct=11 (undefined) skús určiť top-level
	kategóriu cez keywords v title + subtitle + description + channelname.
	"""
	text = ((entry.get('disp_title') or '') + ' ' +
	        (entry.get('disp_subtitle') or '') + ' ' +
	        (entry.get('disp_description') or '') + ' ' +
	        (entry.get('channelname') or ''))
	if not text.strip():
		return _CAT_INE
	text = _strip_accents_lower(text)
	for pattern, cat in _FALLBACK_KEYWORD_TO_TOP:
		if pattern.search(text):
			return cat
	return _CAT_INE


# --------------------------------------------------------------------------
# Hlavná klasifikačná funkcia
# --------------------------------------------------------------------------
def _classify_dvr_entry(entry):
	"""Vráti (top_cat, sub_cat).

	sub_cat môže byť None ak top_cat nemá podžánre. Inak je to jeden
	z _MV_* / _SP_* / _NW_* / _SH_* / _CH_* / _MU_* / _AR_* / _DC_* / _HB_*
	identifikátorov.

	Priorita signálov pre Filmy/Seriály subcat (od 0.53beta):
	  1. Title franchise sci-fi override (Duna, Star Wars, …) — vyhráva
	     aj nad channel subgenre hint-om (Duna na akčnom kanáli ostane sci-fi)
	  2. Title corpus match (~1940 titulov)
	  3. Channel sub-genre hint (Nova Krimi → krimi)
	  4. DVB genre byte + keyword scan (_movie_subgenre)
	"""
	# Najprv urči top kategóriu
	top = _determine_top_cat(entry)

	if top == _CAT_FILM or top == _CAT_SERIAL:
		# FIX 0.53beta: franchise override beats channel hint (Duna na
		# action kanáli = sci-fi, nie akčný).
		if _title_franchise_scifi_match(entry):
			return top, _MV_SCIFI

		# Title corpus beats channel hint (známy titul = silný signál).
		corpus_sub = _corpus_subgenre_match(entry)
		if corpus_sub is not None:
			return top, corpus_sub

		# Channel hint má prednosť pred DVB/keyword scan
		sub = _channel_subgenre_hint(entry)
		if sub is None:
			sub = _movie_subgenre(entry)
			# FIX 0.54beta (z Kodi 1.0.9): ak movie_subgenre vrátil
			# mv_ine, skús IMDb lookup ako posledný fallback. Default
			# OFF cez settings toggle "online_metadata_lookup".
			if sub == _MV_INE:
				try:
					from . import imdb_lookup as _imdb
					_, imdb_sub = _imdb.lookup(entry)
					if imdb_sub is not None:
						sub = imdb_sub
				except Exception:
					pass
		return top, sub

	# FIX 0.49d: ostatné kategórie s podžánrami cez registry dispatch
	entry_cfg = _SUBCAT_REGISTRY.get(top)
	if entry_cfg and entry_cfg[1] is not None:
		# entry_cfg = (labels, subgenre_fn)
		sub = entry_cfg[1](entry)
		return top, sub

	# Kategórie bez podžánrov (napr. _CAT_INE)
	return top, None


def _determine_top_cat(entry):
	"""Helper: vráti top-level kategóriu pre entry.

	Logika (od 0.53beta — z Kodi 1.0.4 portu):
	- content_type je explicitný DVB-SI Level 1 signál z broadcaster-a —
	  má prednosť pred channel hint pre ct=2-10 (DVB tag presnejší než
	  channel name pre Šport/Hudba/News/Show/Arts/Edu/Hobby).
	- Pre dokumentárne kanály (Discovery, Viasat, NG, …) doc hint vyhráva
	  aj nad ct=0/1/2/9 lebo broadcasters routinely mistagujú obsah ako
	  Movie/Drama alebo News na týchto kanáloch.
	- Pre ct=1 (Movie/Drama) a ct=0/5/11: channel hint a series detection
	  majú zmysel — children's animated series channel by mal override-nuť
	  generic Movie tag.
	- Vrátí tuple (top_cat, reason_str) ak je diagnostika ON, inak iba top_cat.
	"""
	try:
		ct = int(entry.get('content_type') or 0)
	except Exception:
		ct = 0

	channel_top = _channel_top_hint(entry)

	# 1) Dokumentárne kanály overrideujú aj ct=0/1/2/9 — broadcasters mistagujú
	#    obsah ako Movie/Drama (ct=1) alebo News (ct=2). Pre ct=3-10 doc hint
	#    NEvyhráva (Šport/Hudba/Šou explicitne tagované je spec. program).
	if channel_top == _CAT_DOKUMENTY and ct in (0, 1, 2, 9):
		return _CAT_DOKUMENTY

	# 2) Explicit DVB-SI Level 1 (ct=2-10) — broadcaster vie čo nahral, dôveruj.
	if ct in (2, 3, 4, 6, 7, 8, 9, 10):
		return _CT_TO_CAT_BASE[ct]

	# 3) Channel hint pre kategórie kde channel name je presný signál
	#    (detský/športový/hudobný/spravodajský kanál).
	if channel_top in (_CAT_DETSKE, _CAT_SPORT, _CAT_HUDBA, _CAT_SPRAVODAJSTVO):
		return channel_top

	# 4) Series detection pred ct=1/5/0 — seriál môže mať ct=1 (Movie/Drama).
	if _is_series_entry(entry):
		return _CAT_SERIAL

	# 5) ct=1 Movie/Drama → film
	if ct == 1:
		return _CAT_FILM

	# 6) ct=5 Children → detské
	if ct == 5:
		return _CAT_DETSKE

	# 7) Keyword fallback pre ct=0/11 (undefined)
	guessed = _guess_top_category_from_keywords(entry)

	# 7b) Corpus-based top promotion (FIX 0.53beta — z Kodi 1.0.7).
	# Ak by entry skončila v _CAT_INE, ale titul je v title corpuse,
	# povýši sa na _CAT_FILM (corpus pozná film/seriál sub-genre).
	if guessed == _CAT_INE:
		if _corpus_subgenre_match(entry) is not None:
			return _CAT_FILM

		# 7c) FIX 0.54beta (z Kodi 1.0.9): IMDb GraphQL lookup ako
		# posledný safety net pred _CAT_INE. Default OFF cez settings
		# toggle "online_metadata_lookup". Ak je zapnutý a IMDb vráti
		# top override (Reality-TV/Documentary/News/Sport/Music/
		# Talk-Show/Game-Show), použij. Inak ak vráti film sub-žáner,
		# povýš top na CAT_FILM. Inak → ine.
		try:
			from . import imdb_lookup as _imdb
			imdb_top, imdb_sub = _imdb.lookup(entry)
			if imdb_top is not None and imdb_top in _IMDB_TOP_TO_CAT:
				return _IMDB_TOP_TO_CAT[imdb_top]
			if imdb_sub is not None:
				return _CAT_FILM
		except Exception:
			pass  # graceful — never crash classification on network problem

	return guessed


# Map IMDb-derived top names to our _CAT_* constants. Kept here (not in
# imdb_lookup.py) to avoid a circular import between the two modules.
# Order matches Kodi 1.0.9: Shows / Documentaries / News / Sports / Music.
_IMDB_TOP_TO_CAT = {
	'show':           _CAT_SHOW,
	'dokumenty':      _CAT_DOKUMENTY,
	'spravodajstvo':  _CAT_SPRAVODAJSTVO,
	'sport':          _CAT_SPORT,
	'hudba':          _CAT_HUDBA,
	'detske':         _CAT_DETSKE,
}


def _dedup_dvr_entries(entries):
	"""Vráti deduplikované entries — najnovší z každej (title, subtitle) skupiny.

	TVH 7x24 autorec môže nahrať tú istú epizódu viackrát počas dňa
	(napr. Pension pro svobodné pány 3× za pár hodín). Pre menu chceme
	ukázať len jeden záznam. Kľúč: (disp_title, disp_subtitle[:80]).
	Z duplikátov ostane ten s najvyšším _ts (najnovšie nahranie).
	"""
	by_key = {}
	for e in entries:
		title = (e.get('disp_title') or '').strip()
		if not title:
			continue
		sub = (e.get('disp_subtitle') or '')[:80]
		key = (title, sub)
		prev = by_key.get(key)
		if prev is None or _ts(e) > _ts(prev):
			by_key[key] = e
	return list(by_key.values())


# Cache pre klasifikáciu (60s TTL — rovnaké ako DVR cache)
_DVR_CLASSIFY_CACHE = {'ts': 0, 'data': None}
_DVR_CLASSIFY_TTL_SEC = 60


def _invalidate_classify_cache():
	_DVR_CLASSIFY_CACHE['ts'] = 0
	_DVR_CLASSIFY_CACHE['data'] = None


def _get_classified_dvr(tvh):
	"""Vráti tuple s klasifikovanými dátami pre menu rendering.

	Returns:
	    entries_by_top: {top_cat: [entry, ...]}  flat lists pre non-Filmy/Seriály
	    entries_by_subcat: {(top_cat, sub_cat): [entry, ...]}  pre Filmy detail
	    counts: {top_cat: int}  pre rozhodovanie či pridať položku do root
	    series_by_canonical: {canonical_title: [entry, ...]}  pre Seriály detail
	    series_subcat_titles: {(top_cat, sub_cat): set(canonical_title)}
	                          pre filtrovanie zoznamu sérií v sub-žánre

	Sort: všetky listy newest-first (key=_ts, reverse=True).
	Cache: 60s.
	"""
	now = int(time.time())
	cached = _DVR_CLASSIFY_CACHE
	if cached['data'] and (now - cached['ts']) < _DVR_CLASSIFY_TTL_SEC:
		return cached['data']

	entries = _get_dvr_finished_cached(tvh)
	entries = _dedup_dvr_entries(entries)

	entries_by_top = {}
	entries_by_subcat = {}
	series_by_canonical = {}
	series_subcat_titles = {}

	for e in entries:
		top, sub = _classify_dvr_entry(e)
		entries_by_top.setdefault(top, []).append(e)
		if sub is not None:
			entries_by_subcat.setdefault((top, sub), []).append(e)

		if top == _CAT_SERIAL:
			title = (e.get('disp_title') or '').strip()
			if title:
				canonical = _series_canonical_title(title)
				if canonical:
					series_by_canonical.setdefault(canonical, []).append(e)
					if sub is not None:
						series_subcat_titles.setdefault(
							(top, sub), set()).add(canonical)

	# Sort: newest first
	for k in entries_by_top:
		entries_by_top[k].sort(key=_ts, reverse=True)
	for k in entries_by_subcat:
		entries_by_subcat[k].sort(key=_ts, reverse=True)
	for t in series_by_canonical:
		series_by_canonical[t].sort(key=_ts, reverse=True)

	counts = {cat: len(entries_by_top[cat]) for cat in entries_by_top}
	data = (entries_by_top, entries_by_subcat, counts,
	        series_by_canonical, series_subcat_titles)

	cached['ts'] = now
	cached['data'] = data
	return data
# ============================================================================
# end FIX 0.49 classification helpers
# ============================================================================


def _norm_name(s):
	# FIX 0.48c: používa centrálny _strip_accents_compat (tools_archivczsk
	# helper s fallback-om) namiesto duplicitnej implementácie cez unicodedata.
	if not s:
		return ''
	return _strip_accents_compat(s).lower()


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

	# login_settings_names = tuple() je DÔLEŽITÉ:
	#
	# Framework's process_login() pri prázdnom value v login_settings_names
	# vráti False BEZ ZOBRAZENIA DIALÓGU a NEZAVOLÁ login() ani root().
	# Tým by sa plugin otvoril prázdny ale bez informácie pre používateľa.
	#
	# Preto necháme tuple() (vždy povolíme volanie login/root) a dialóg
	# "nie je nakonfigurované" zobrazíme z root() vyhodením
	# AddonErrorException — framework ho zachytí v run() cez:
	#     except AddonErrorException as e:
	#         client.showError(str(e))
	# a zobrazí "Chyba" dialóg s našou správou. Po stlačení OK sa plugin
	# otvorí prázdny.
	#
	# login_optional_settings_names je len pre notification: framework zavolá
	# login_data_changed() keď user zmení niektorú z týchto settings.
	login_settings_names = tuple()
	login_optional_settings_names = (
		'host', 'port', 'use_https',
		'username', 'password',
		'http_auth_mode', 'use_ticket_url',
		'profile', 'loading_timeout',
		'enable_m3u_source', 'm3u_url', 'm3u_epg_url',
	)

	def __init__(self, *args, **kwargs):
		CommonContentProvider.__init__(self, *args, **kwargs)
		self.tvh = Tvheadend(self)
		self._bouquet_gen = None
		self._m3u_manager = None

	# ------------------------------------------------------------------
	# login() – volá sa automaticky pri štarte aj po zmene nastavení
	# ------------------------------------------------------------------

	def login(self, silent=False):
		# Python 2 – best-effort beh, len jednorazové upozornenie do logu
		if sys.version_info[0] < 3:
			if not getattr(self, '_py2_warned', False):
				try:
					print("[plugin.video.tvheadend] WARNING: running on "
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
		try:
			import logging as _logging
			_lg = _logging.getLogger('plugin.video.tvheadend.provider')
			from . import imdb_lookup as _imdb
			raw = self.get_setting('online_metadata_lookup')
			# ArchivCZSK vracia bool pre type="bool" settings, ale pre
			# istotu akceptujeme aj "true"/"1"/True/1.
			if isinstance(raw, bool):
				enabled = raw
			else:
				enabled = str(raw).strip().lower() in ('true', '1', 'yes')
			_imdb.set_enabled(enabled)
			_lg.info('IMDb lookup setting raw=%r resolved=%s',
			          raw, 'ON' if enabled else 'OFF')
		except Exception as _e:
			try:
				import logging as _logging
				_logging.getLogger('plugin.video.tvheadend.provider').warning(
					'IMDb lookup setup failed: %s', _e)
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
		# Settings menu + M3U source ostanú prístupné aj keď TVH nie je nastavené)
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

			# FIX 0.48e: nezávislý EPG auto-inject podľa tvh_epg_inject_interval
			# (typicky častejšie ako bouquet refresh — EPG sa mení denne)
			try:
				self._maybe_auto_inject_epg()
			except Exception:
				pass

		# ----- External M3U playlist source (nezávislý od TVH loginu) -----
		# Pozn.: aj keď je M3U vypnuté, _maybe_init_m3u_manager() môže
		# vykonať one-shot cleanup zostatkov.
		try:
			self._maybe_init_m3u_manager()
		except Exception:
			pass

		# FIX 0.48g: paralelný EPG auto-inject pre M3U side (s vlastným
		# intervalom m3u_epg_inject_interval, default 4h). Beží len ak
		# je M3U source zapnutý.
		try:
			self._maybe_auto_inject_m3u_epg()
		except Exception:
			pass

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
		  - _maybe_init_m3u_manager (kompletná inicializácia M3U manager-a
		    + možné re-schedule eTimera)
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
						print('[plugin.tvheadend] watchdog: TVH back online — '
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
					# FIX 0.48e: aj EPG auto-inject (typicky kratší interval)
					try:
						self._maybe_auto_inject_epg()
					except Exception:
						pass
				# FIX 0.48g: M3U EPG auto-inject (nezávislý od TVH stavu —
				# M3U source nemusí byť TVH-based)
				try:
					self._maybe_auto_inject_m3u_epg()
				except Exception:
					pass
			except Exception as e:
				try:
					print('[plugin.tvheadend] watchdog error: %s' % e)
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
				print('[plugin.tvheadend] watchdog started '
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
					print('[plugin.tvheadend] check_login: recovered on retry '
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
				print('[plugin.tvheadend] fast-recovery poll started '
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
							print('[plugin.tvheadend] fast-recovery: TVH back '
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
				print('[plugin.tvheadend] fast-recovery poll ended')
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

	def _maybe_init_m3u_manager(self):
		"""
		Inicializuje M3U refresh manager pre externý playlist (ak je zapnutý
		v settings). Beží paralelne s TVH zdrojom, nemodifikuje TVH bouquet.
		Generuje samostatný userbouquet so service refmi type=1 (native DVB)
		pre podporu DVB titulkov.

		Ak je M3U vypnuté ale existujú zostatkové súbory z predošlého
		zapnutia (userbouquet, bouquets.tv záznam, epgimport súbory), tak
		ich vyčistí jednorazovo (one-shot cleanup stamp).
		"""
		if M3URefreshManager is None:
			return
		try:
			if self._m3u_manager is None:
				def _m3u_log(*parts):
					try:
						msg = ' '.join(str(p) for p in parts)
						print('[plugin.tvheadend.m3u] ' + msg)
					except Exception:
						pass

				def _settings_get(key, default=None):
					try:
						val = self.get_setting(key)
						return default if val is None else val
					except Exception:
						return default

				self._m3u_manager = M3URefreshManager(
					settings_getter=_settings_get,
					log=_m3u_log,
					tvh_client=self.tvh,
				)

			if not self._m3u_manager.is_enabled():
				# M3U je vypnuté — ak existujú zostatkové artefakty z minulého
				# zapnutia, jednorazovo ich vyčistíme.
				try:
					self._maybe_cleanup_disabled_m3u()
				except Exception:
					pass
				return

			# Prvý refresh asynchronne, aby login() nezablokoval
			self._m3u_manager.refresh_async()

			# Periodický refresh cez enigma2 eTimer (alebo threading.Timer fallback)
			try:
				from enigma import eTimer
				self._m3u_manager.schedule(etimer_class=eTimer)
			except ImportError:
				self._m3u_manager.schedule(etimer_class=None)
		except Exception as e:
			try:
				print('[plugin.tvheadend.m3u] init failed:', e)
			except Exception:
				pass

	def _maybe_cleanup_disabled_m3u(self):
		"""
		Ak je M3U vypnuté v settings ale na disku existuje userbouquet alebo
		záznam v bouquets.tv, zavolá cleanup. Idempotentné: keď nič nie je,
		nič neurobí. Vykoná sa pri každom login() — operácia je O(1) keď nie
		je čo mazať.
		"""
		if self._m3u_manager is None:
			return
		prefix = M3U_BOUQUET_PREFIX  # FIX 0.48f: hardcoded
		ub_path = '/etc/enigma2/userbouquet.{}.tv'.format(prefix)
		bq_index = '/etc/enigma2/bouquets.tv'

		need_cleanup = os.path.isfile(ub_path)
		if not need_cleanup and os.path.isfile(bq_index):
			try:
				with open(bq_index, 'r') as f:
					content = f.read()
				if ('userbouquet.%s.tv' % prefix) in content:
					need_cleanup = True
			except Exception:
				pass

		if need_cleanup:
			try:
				print('[plugin.tvheadend.m3u] cleanup: M3U is disabled but '
				      'bouquet artefacts exist — removing them')
			except Exception:
				pass
			self._m3u_manager.cleanup()

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
					print('[plugin.tvheadend] auto-refresh bouquet failed: %s' % e)
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

	def _maybe_auto_inject_epg(self):
		"""FIX 0.48e: nezávislý EPG auto-inject podľa tvh_epg_inject_interval.

		Beží OKREM bouquet refresh-u (ten injektuje EPG ako vedľajší produkt).
		Tým môže mať EPG refresh kratší interval než bouquet refresh —
		typicky bouquet 24h (kanály sa nemenia tak často), EPG 4-12h
		(programy sa menia denne).

		Logika:
		  - Zisti `tvh_epg_inject_interval` zo settings (sekundy, 0 = vypnuté)
		  - Skontroluj `_EPG_INJECT_STAMP` (zapisuje sa po každej úspešnej
		    injekcii, či už cez bouquet refresh _post() alebo cez nás)
		  - Ak je rozdiel >= interval, spusti injekciu na pozadí
		  - Pri zlyhaní nastaví retry stamp 5 min v budúcnosti (rovnaká
		    logika ako _maybe_auto_refresh_bouquet)
		"""
		if self._bouquet_gen is None:
			return
		try:
			interval = 0
			try:
				interval = int(self._bouquet_gen.get_setting('tvh_epg_inject_interval') or 0)
			except Exception:
				interval = 0
			if interval <= 0:
				return  # vypnuté

			now = int(time.time())
			last = 0
			try:
				last = int(os.path.getmtime(_EPG_INJECT_STAMP))
			except Exception:
				pass

			if last and (now - last) < interval:
				return  # interval ešte neuplynul

			# Skontroluj TVH konektivitu
			if not self._check_tvh_silent():
				retry_at = now - interval + 300
				try:
					if os.path.isfile(_EPG_INJECT_STAMP):
						os.utime(_EPG_INJECT_STAMP, (retry_at, retry_at))
					else:
						with open(_EPG_INJECT_STAMP, 'w') as f:
							f.write(str(retry_at))
						os.utime(_EPG_INJECT_STAMP, (retry_at, retry_at))
				except Exception:
					pass
				return

			# Spusti injekciu na pozadí — XMLTV fetch + parse trvá desiatky sekúnd
			import threading as _th

			def _runner():
				try:
					ok = self._bouquet_gen.inject_tvh_epg_into_enigma()
					if not ok:
						# inject_tvh_epg sám zapíše stamp len pri úspechu;
						# pri zlyhaní nastavíme retry-at-5min
						# FIX 0.50beta: použiť aktuálny čas, nie captured `now`
						# zo spustenia metódy (môže byť o desiatky sekúnd starší)
						_now_fail = int(time.time())
						retry_at = _now_fail - interval + 300
						try:
							with open(_EPG_INJECT_STAMP, 'w') as f:
								f.write(str(retry_at))
							os.utime(_EPG_INJECT_STAMP, (retry_at, retry_at))
						except Exception:
							pass
				except Exception as e:
					try:
						print('[plugin.tvheadend] auto-inject EPG failed: %s' % e)
					except Exception:
						pass

			t = _th.Thread(target=_runner, name='TVHEPGAutoInject')
			t.daemon = True
			t.start()
		except Exception:
			pass

	def _maybe_auto_inject_m3u_epg(self):
		"""FIX 0.48g: paralelný EPG auto-inject pre M3U side (analógia
		s _maybe_auto_inject_epg pre TVH).

		Beží OKREM m3u refresh-u (ten injektuje EPG ako vedľajší produkt).
		Tým môže M3U EPG refresh bežať s kratším intervalom než celý
		M3U refresh — typicky M3U bouquet 24h, EPG 4h.

		Logika identická s _maybe_auto_inject_epg, len pre M3U:
		  - Setting: m3u_epg_inject_interval (0 = vypnuté)
		  - Stamp: _EPG_INJECT_STAMP_M3U
		  - Volaná metóda: self._m3u_manager.inject_epg_only()
		"""
		if self._m3u_manager is None:
			return
		if not self._bool_setting('enable_m3u_source'):
			return
		try:
			try:
				interval = int(self.get_setting('m3u_epg_inject_interval') or 0)
			except Exception:
				interval = 0
			if interval <= 0:
				return

			now = int(time.time())
			last = 0
			try:
				last = int(os.path.getmtime(_EPG_INJECT_STAMP_M3U))
			except Exception:
				pass

			if last and (now - last) < interval:
				return

			# Spusti na pozadí — fetch M3U + XMLTV + parse môže trvať 10-30s
			import threading as _th

			def _runner():
				try:
					ok = self._m3u_manager.inject_epg_only()
					if not ok:
						# FIX 0.50beta: použiť aktuálny čas, nie captured `now`
						_now_fail = int(time.time())
						retry_at = _now_fail - interval + 300
						try:
							with open(_EPG_INJECT_STAMP_M3U, 'w') as f:
								f.write(str(retry_at))
							os.utime(_EPG_INJECT_STAMP_M3U, (retry_at, retry_at))
						except Exception:
							pass
				except Exception as e:
					try:
						print('[plugin.tvheadend] M3U auto-inject EPG failed: %s' % e)
					except Exception:
						pass

			t = _th.Thread(target=_runner, name='M3UEPGAutoInject')
			t.daemon = True
			t.start()
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
		"""Root menu - kontextové:
		- Nič nakonfigurované       → zobrazí sa "Chyba" dialóg, plugin sa
		                              otvorí ÚPLNE PRÁZDNY (užívateľ pôjde
		                              cez modré tlačidlo Nastavenia)
		- TVH dočasne nedostupný    → krátka chybová hláška + Retry položka
		                              (FIX 0.48h)
		- Len M3U zapnuté           → zobrazí sa len Settings folder
		- TVH login OK + M3U on/off → Live TV + Archive + Settings
		"""
		tvh_ok = self._check_tvh_silent()
		_, tvh_reason, tvh_err = self.get_tvh_state()
		m3u_enabled = self._bool_setting('enable_m3u_source')

		# FIX 0.48h: rozlíšenie stavov.
		# Predtým: pri akomkoľvek tvh_ok=False (či už chýbali credentials
		# alebo TVH transient failne) → "Plugin is not configured" dialóg
		# + return → prázdny plugin. Užívateľ to interpretoval ako "prihlasenie
		# vypršalo" hoci credentials boli vyplnené.
		# Teraz:
		#  - not_configured (reason): klasická hláška + return
		#  - unreachable (reason): krátka info hláška + Retry položka
		#    + Settings + (ak je) M3U Settings folder
		if not tvh_ok and not m3u_enabled:
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

			# not_configured (alebo None reason) → klasika
			try:
				self.show_error(
				    self._("Plugin is not configured.\n\n"
				           "Fill in TVH server (host, username, password) "
				           "OR enable External M3U playlist in plugin "
				           "settings (blue 'Nastavenia' button)."),
				    noexit=True,
				    timeout=3   # FIX 0.48h: znížené z 10s
				)
			except Exception as e:
				# Fallback: pri starších verziách tools_archivczsk
				# kde show_error nemá noexit alebo neexistuje
				print('[plugin.tvheadend] show_error failed: %s' % e)
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
						title=self._("Hľadať v archíve"))
			except Exception as _e:
				try:
					print('[plugin.tvheadend] add_search_dir failed: %s' % _e)
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
				_, _, _counts, _, _ = _get_classified_dvr(self.tvh)
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
					print('[plugin.tvheadend] root: dvr classify '
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
					self.add_dir(self._("Posledné sledované"),
					             cmd=self.recently_watched,
					             info_labels={'title': self._("Posledné sledované")})
			except Exception:
				pass
		elif tvh_reason == 'unreachable':
			# FIX 0.48h: aj pri M3U-only setup-e ukáž retry ak má užívateľ
			# vyplnené TVH credentials ale práve teraz nejde (transient)
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

		# Settings folder len ak je niečo nakonfigurované (TVH alebo M3U).
		# Pri úplne prázdnej konfigurácii sme sa už vrátili vyššie cez return.
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

	def _bool_setting(self, key, default=False):
		"""Helper - read a boolean setting safely."""
		try:
			v = self.get_setting(key)
		except Exception:
			return default
		if isinstance(v, bool):
			return v
		if v is None:
			return default
		s = str(v).strip().lower()
		return s in ('1', 'true', 'yes', 'on', 'áno', 'ano')

	# ------------------------------------------------------------------
	# Settings menu - ručné akcie (refresh M3U/EPG/picons, status, atď.)
	# ------------------------------------------------------------------

	def settings_menu(self):
		"""Hlavné menu Nastavenia - kontextové:
		- M3U sekcia: len ak M3U source je zapnutý v settings
		- TVH sekcia: len ak TVH credentials sú vyplnené a prihlasenie funguje
		- Diagnose M3U EPG: len ak M3U je zapnutý
		"""
		tvh_ok = self._check_tvh_silent()
		m3u_enabled = self._bool_setting('enable_m3u_source')

		# --- Status sekcia (vždy) ---
		for line in self._build_status_lines():
			self.add_dir(line, cmd=self.settings_menu,
			             info_labels={'title': line})

		# --- M3U sekcia (len ak je zapnuté) ---
		if m3u_enabled:
			self.add_dir("─" * 32, cmd=self.settings_menu,
			             info_labels={'title': self._("M3U Playlist Actions")})

			self.add_dir(self._("Refresh M3U playlist + EPG now"),
			             cmd=self.action_m3u_refresh,
			             info_labels={'title': self._("Refresh M3U now")})
			self.add_dir(self._("Refresh M3U playlist (background)"),
			             cmd=self.action_m3u_refresh_async,
			             info_labels={'title': self._("Refresh M3U background")})
			self.add_dir(self._("Download M3U picons now"),
			             cmd=self.action_m3u_picons,
			             info_labels={'title': self._("M3U picons")})
		else:
			# M3U je vypnuté — ak existujú zostatkové súbory (napr. user
			# práve vypol M3U), ponúkneme manuálny cleanup.
			prefix = M3U_BOUQUET_PREFIX  # FIX 0.48f: hardcoded
			ub_path = '/etc/enigma2/userbouquet.{}.tv'.format(prefix)
			if os.path.isfile(ub_path):
				self.add_dir("─" * 32, cmd=self.settings_menu,
				             info_labels={'title': self._("M3U cleanup")})
				self.add_dir(self._("✗ Remove leftover M3U bouquet now"),
				             cmd=self.action_m3u_cleanup,
				             info_labels={'title': self._("Remove M3U bouquet")})

		# --- TVH sekcia (len ak je TVH nakonfigurované a prihlásené) ---
		if tvh_ok:
			self.add_dir("─" * 32, cmd=self.settings_menu,
			             info_labels={'title': self._("Tvheadend Actions")})

			self.add_dir(self._("Refresh TVH bouquet + XML EPG now"),
			             cmd=self.action_tvh_bouquet_refresh,
			             info_labels={'title': self._("Refresh TVH bouquet")})
			# FIX 0.48d: manuálne spustenie direct EPG injection do Enigma2
			self.add_dir(self._("Inject EPG into Enigma2 now (no epgimport)"),
			             cmd=self.action_tvh_inject_epg,
			             info_labels={'title': self._("Inject EPG now")})
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

		# Diagnose M3U EPG matching - len ak M3U je zapnutý
		if m3u_enabled:
			self.add_dir(self._("Diagnose M3U EPG matching"),
			             cmd=self.action_diagnose_m3u_epg,
			             info_labels={'title': self._("Diagnose EPG")})

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
		m3u_enabled = self._bool_setting('enable_m3u_source')

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

			# FIX 0.48e: EPG inject status — len ak je zapnuté (interval > 0)
			try:
				if self._bouquet_gen is not None:
					interval = int(self._bouquet_gen.get_setting(
						'tvh_epg_inject_interval') or 0)
					if interval > 0:
						# Format interval ako human-readable
						if interval >= 86400:
							iv = "%dd" % (interval // 86400)
						else:
							iv = "%dh" % (interval // 3600)
						lines.append("◆ %s: %s (every %s)" %
						             (self._("Last EPG inject"),
						              _fmt_age(_EPG_INJECT_STAMP), iv))
			except Exception:
				pass

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

		# M3U status - len ak je zapnuté
		if m3u_enabled:
			m3u_url = self.get_setting('m3u_url') or ''
			short = m3u_url
			if len(short) > 40:
				short = short[:37] + '...'
			lines.append("◆ %s: %s" % (self._("M3U source"),
			                            short or '(not set)'))

			try:
				# FIX 0.48j: použiť persistent stamp namiesto /tmp
				stamp = data_path('m3u_last_refresh.stamp')
				lines.append("◆ %s: %s" %
				             (self._("Last M3U refresh"), _fmt_age(stamp)))
			except Exception:
				pass

			# FIX 0.48g: M3U EPG inject status — len ak je zapnuté
			try:
				interval = int(self.get_setting('m3u_epg_inject_interval') or 0)
				if interval > 0:
					if interval >= 86400:
						iv = "%dd" % (interval // 86400)
					else:
						iv = "%dh" % (interval // 3600)
					lines.append("◆ %s: %s (every %s)" %
					             (self._("Last M3U EPG inject"),
					              _fmt_age(_EPG_INJECT_STAMP_M3U), iv))
			except Exception:
				pass

			st = self.get_setting('m3u_service_type') or '1'
			lines.append("◆ %s: %s" %
			             (self._("M3U service type"), st))

		# Ak nič nie je nakonfigurované, ukáž aspoň hint
		if not tvh_ok and not m3u_enabled:
			lines.append("◆ %s" %
			             self._("Configure TVH credentials or enable External M3U in plugin settings"))

		return lines

	# ------------------------------------------------------------------
	# Action callbacks
	# ------------------------------------------------------------------

	def action_m3u_refresh(self):
		"""Synchrónne spustí M3U refresh, zobrazí výsledok."""
		if self._m3u_manager is None or not self._m3u_manager.is_enabled():
			self.add_dir(self._("✗ M3U source is not enabled"),
			             cmd=self.settings_menu)
			return
		try:
			ok = self._m3u_manager.refresh_now()
			if ok:
				self.add_dir(self._("✓ M3U refresh completed successfully"),
				             cmd=self.settings_menu)
			else:
				self.add_dir(self._("✗ M3U refresh failed - check log"),
				             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_m3u_refresh_async(self):
		"""Spustí M3U refresh na pozadí, okamžite sa vráti."""
		if self._m3u_manager is None or not self._m3u_manager.is_enabled():
			self.add_dir(self._("✗ M3U source is not enabled"),
			             cmd=self.settings_menu)
			return
		try:
			self._m3u_manager.refresh_async()
			self.add_dir(self._("✓ M3U refresh started in background"),
			             cmd=self.settings_menu)
			self.add_dir(self._("Check 'Last M3U refresh' in status "
			                    "after ~30 seconds"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_m3u_picons(self):
		"""Iba picon download (bez bouquet write)."""
		if self._m3u_manager is None or not self._m3u_manager.is_enabled():
			self.add_dir(self._("✗ M3U source is not enabled"),
			             cmd=self.settings_menu)
			return
		try:
			# Trick: temporarily forc-write but only the picon stage.
			# Easiest path: just call full refresh — it includes picons
			# and is fast on subsequent runs (most cached).
			self._m3u_manager.refresh_async()
			self.add_dir(self._("✓ Picon download started "
			                    "(via full refresh on background)"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_m3u_cleanup(self):
		"""
		Manuálne zmaže M3U bouquet zo systému (userbouquet, záznam
		v bouquets.tv, epgimport súbory). Užitočné keď user vypol M3U
		a nechce čakať na ďalší login plugin-u.
		"""
		# Manager je inicializovaný v _maybe_init_m3u_manager aj keď je
		# M3U vypnuté (vďaka novej logike), takže by tu mal existovať.
		if self._m3u_manager is None:
			# Fallback: vytvorme jednorazový manager len pre cleanup
			try:
				self._maybe_init_m3u_manager()
			except Exception:
				pass

		if self._m3u_manager is None:
			self.add_dir(self._("✗ M3U manager not available"),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		try:
			stats = self._m3u_manager.cleanup()
			if stats:
				self.add_dir(self._("✓ M3U bouquet cleanup done"),
				             cmd=self.settings_menu)
				self.add_dir("  bouquets.tv updated: %s" %
				             ("yes" if stats.get('bouquets_tv_updated') else "no"),
				             cmd=self.settings_menu)
				self.add_dir("  userbouquet deleted: %s" %
				             ("yes" if stats.get('userbouquet_deleted') else "no"),
				             cmd=self.settings_menu)
				self.add_dir("  epgimport files deleted: %d" %
				             stats.get('epgimport_deleted', 0),
				             cmd=self.settings_menu)
				self.add_dir("  Enigma2 reloaded: %s" %
				             ("yes" if stats.get('reloaded') else "no"),
				             cmd=self.settings_menu)
			else:
				self.add_dir(self._("✗ Cleanup returned no stats"),
				             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

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
		"""Manuálne spustí stiahnutie TVH piconov."""
		if not self._check_tvh_silent():
			self.add_dir(self._("✗ TVH login failed - check settings"),
			             cmd=self.settings_menu)
			return
		try:
			self.tvh.init_picons_async()
			self.add_dir(self._("✓ TVH picon download started in background"),
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

	def action_tvh_inject_epg(self):
		"""FIX 0.48d: manuálne spustí direct EPG injection do Enigma2 eEPGCache.

		Funguje aj keď epgimport plugin nie je nainštalovaný. Použiteľné
		po pridaní nových kanálov v TVH, na rýchle naplnenie EPG bez
		čakania na ďalší bouquet refresh.
		"""
		if not self._check_tvh_silent():
			self.add_dir(self._("✗ TVH login failed - check settings"),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return
		if self._bouquet_gen is None:
			self.add_dir(self._("✗ Bouquet generator not initialised"),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		# Spusti injection na pozadí, lebo XMLTV fetch + parse môže trvať
		# desiatky sekúnd pre veľký EPG (500+ kanálov × 7 dní = MB súbor).
		import threading as _th

		def _runner():
			try:
				self._bouquet_gen.inject_tvh_epg_into_enigma()
			except Exception as e:
				try:
					print('[plugin.tvheadend] inject_tvh_epg failed: %s' % e)
				except Exception:
					pass

		try:
			t = _th.Thread(target=_runner, name='TVHEPGInject')
			t.daemon = True
			t.start()
			self.add_dir(self._("✓ EPG injection started in background"),
			             cmd=self.settings_menu)
			# FIX 0.48j: logy idú cez print() do /tmp/archivCZSK.log
			self.add_dir(self._("Progress: see /tmp/archivCZSK.log "
			                    "(filter 'inject_epg')"),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ Error: ") + str(e),
			             cmd=self.settings_menu)
		self.add_dir(self._("« Back"), cmd=self.settings_menu)

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

	def action_diagnose_m3u_epg(self):
		"""
		Stiahne TVH XMLTV, porovná IDs s M3U channels.xml,
		ukáže koľko kanálov sa nájde v XMLTV (a teda bude mať EPG).
		"""
		self.add_dir(self._("Diagnosing M3U EPG matching..."),
		             cmd=self.settings_menu)

		# Step 1: where's our channels.xml?
		prefix = M3U_BOUQUET_PREFIX  # FIX 0.48f: hardcoded
		channels_xml_path = '/etc/epgimport/{}.channels.xml'.format(prefix)
		if not os.path.exists(channels_xml_path):
			self.add_dir(self._("✗ channels.xml not found: ") + channels_xml_path,
			             cmd=self.settings_menu)
			self.add_dir(self._("Run 'Refresh M3U playlist' first"),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		# Step 2: parse channels.xml -> collect tvg-ids we expect
		try:
			tree = _et_parse(channels_xml_path)
			our_ids = set()
			for c in tree.getroot().findall('channel'):
				cid = c.get('id')
				if cid:
					our_ids.add(cid.lower())
			self.add_dir(self._("M3U channels.xml has %d <channel> entries")
			             % len(our_ids),
			             cmd=self.settings_menu)
		except Exception as e:
			self.add_dir(self._("✗ channels.xml parse failed: ") + str(e),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		# Step 3: figure out EPG source URL
		epg_url = (self.get_setting('m3u_epg_url') or '').strip()
		if not epg_url:
			try:
				from .m3u_tvh_enricher import derive_tvh_xmltv_url
				epg_url = derive_tvh_xmltv_url(self.tvh) or ''
			except Exception:
				epg_url = ''
		if not epg_url:
			self.add_dir(self._("✗ No EPG URL configured or derivable"),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		self.add_dir(self._("EPG source: ") + epg_url[:50],
		             cmd=self.settings_menu)

		# Step 4: fetch XMLTV, extract channel ids
		try:
			req = Request(epg_url)
			req.add_header('User-Agent', 'Tvheadend-plugin/diag')
			resp = urlopen(req, timeout=30)
			data = resp.read()
			resp.close()
		except Exception as e:
			self.add_dir(self._("✗ EPG fetch failed: ") + str(e),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		# Decompress if needed
		try:
			if data[:2] == b'\x1f\x8b':
				data = gzip.decompress(data) if hasattr(gzip, 'decompress') \
					else gzip.GzipFile(fileobj=io.BytesIO(data)).read()
			elif data[:6] == b'\xfd7zXZ\x00' and lzma is not None:
				data = lzma.decompress(data)
		except Exception:
			pass

		# Parse XMLTV channel ids (stream to handle large files).
		# IMPORTANT: cElementTree on Py2 rejects unicode event names with
		# "invalid event tuple" — `from __future__ import unicode_literals`
		# makes all string literals in this module unicode. We must convert
		# event names to native str (bytes on Py2, text on Py3) via str().
		xmltv_ids = set()
		try:
			for event, elem in _et_iterparse(io.BytesIO(data),
			                                 events=(str('start'),)):
				if elem.tag == 'channel':
					cid = elem.get('id')
					if cid:
						xmltv_ids.add(cid.lower())
				elif elem.tag == 'programme':
					break
		except Exception as e:
			self.add_dir(self._("✗ XMLTV parse failed: ") + str(e),
			             cmd=self.settings_menu)
			self.add_dir(self._("« Back"), cmd=self.settings_menu)
			return

		self.add_dir(self._("XMLTV source has %d <channel id> entries")
		             % len(xmltv_ids),
		             cmd=self.settings_menu)

		# Step 5: compute intersection
		matched = our_ids & xmltv_ids
		missed_from_m3u = our_ids - xmltv_ids
		extra_in_xmltv = xmltv_ids - our_ids

		self.add_dir(self._("✓ Matched: %d / %d") %
		             (len(matched), len(our_ids)),
		             cmd=self.settings_menu)
		self.add_dir(self._("M3U ids not in XMLTV: %d") % len(missed_from_m3u),
		             cmd=self.settings_menu)
		self.add_dir(self._("XMLTV ids not in M3U: %d") % len(extra_in_xmltv),
		             cmd=self.settings_menu)

		# Show samples
		if missed_from_m3u:
			self.add_dir(self._("--- Sample M3U IDs missing in XMLTV ---"),
			             cmd=self.settings_menu)
			for mid in list(missed_from_m3u)[:5]:
				self.add_dir("  " + mid[:60], cmd=self.settings_menu)

		if extra_in_xmltv:
			self.add_dir(self._("--- Sample XMLTV IDs not in M3U ---"),
			             cmd=self.settings_menu)
			for xid in list(extra_in_xmltv)[:5]:
				self.add_dir("  " + xid[:60], cmd=self.settings_menu)

		self.add_dir(self._("« Back"), cmd=self.settings_menu)

	def action_show_paths(self):
		"""Zobrazí cesty k vygenerovaným súborom + ich veľkosti."""
		paths_to_check = [
			('/etc/enigma2/bouquets.tv', self._("Bouquets index")),
			('/etc/enigma2/userbouquet.{}.tv'.format(
				M3U_BOUQUET_PREFIX),  # FIX 0.48f: hardcoded
				self._("M3U bouquet")),
			('/etc/epgimport/{}.channels.xml'.format(
				M3U_BOUQUET_PREFIX),  # FIX 0.48f: hardcoded
				self._("M3U epgimport channels")),
			('/etc/epgimport/{}.sources.xml'.format(
				M3U_BOUQUET_PREFIX),  # FIX 0.48f: hardcoded
				self._("M3U epgimport sources")),
			('/usr/share/enigma2/picon', self._("Picon directory")),
			# FIX 0.48j: stampy sú teraz v persistent data dir-u, nie v /tmp
			(data_path('m3u_last_refresh.stamp'),
				self._("M3U refresh stamp")),
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
				info_labels={'title': self._("Posledné sledované")})
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
				info_labels={'title': self._("Posledné sledované")})

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
				= _get_classified_dvr(self.tvh)
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
			_by_top, by_subcat, _, _, _ = _get_classified_dvr(self.tvh)
		except Exception:
			self.add_dir(self._("⟳ Failed to load — tap to retry"),
			             cmd=self.action_retry_tvh_root,
			             info_labels={'title': self._("Retry")})
			return

		entries = by_subcat.get((_CAT_FILM, sub_id)) or []
		for e in entries:
			self._add_dvr_entry_item(e)

	def archive_sport_subgenre(self, sub_id):
		"""FIX 0.49c: Plochý zoznam športových záznamov v podžánre
		(napr. Šport → Futbal). Zachované pre backward compat — interne
		volá archive_generic_subgenre.
		"""
		self.archive_generic_subgenre(top_cat=_CAT_SPORT, sub_id=sub_id)

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
			_by_top, by_subcat, _, _, _ = _get_classified_dvr(self.tvh)
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
				= _get_classified_dvr(self.tvh)
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
			_, _, _, series_by_canonical, _ = _get_classified_dvr(self.tvh)
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
				import logging as _logging
				_logging.getLogger('plugin.video.tvheadend.provider').warning(
					'stats() callback failed (silently): %s', sys.exc_info()[1])
			except Exception:
				pass

	# ------------------------------------------------------------------
	# get_url_by_channel_key – volané z HTTP handlera a bouquet generátora
	# ------------------------------------------------------------------

	def get_url_by_channel_key(self, key):
		# FIX 0.48: light-weight login namiesto plného login(silent=True).
		# Plný login zbytočne spúšťa cleanup, picon worker, M3U manager
		# init a auto-refresh check — to všetko pri každom playback-u.
		if not self._quick_login_for_http_handler():
			# TVH momentálne neodpovedá → zatvor HTTP handler s 404
			raise AddonErrorException('Tvheadend not reachable')

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
