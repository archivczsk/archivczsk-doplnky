# -*- coding: utf-8 -*-
#
# IMDb GraphQL genre lookup with local persistent cache.
#
# Used as an optional online fallback for the DVR archive classifier when:
#   - the local title corpus has no match for the recording title
#   - the keyword-based fallback would route the recording to "Other"
#
# Strategy:
#   1. Normalize the recording title (same canonicalization as the corpus
#      uses — strip year suffix, tech markers, accents, lowercase).
#   2. Look up in the local on-disk cache. Hit -> return cached result
#      (positive or negative).
#   3. Cache miss -> single POST to IMDb GraphQL endpoint. Parse the first
#      "Title" result (skip TV episodes). Map IMDb genre array to our
#      _MV_* sub-genre + optional top-category override.
#   4. Persist the result (positive AND negative) to the cache so the
#      next session does not re-fetch.
#
# Network safety:
#   - 5 s timeout per request
#   - All exceptions caught; on failure returns (None, None) and the
#     classifier falls through to its original logic. Plugin never
#     crashes because of an IMDb hiccup.
#   - Rate limit: 1 request/sec minimum spacing between live calls.
#   - Settings toggle "online_metadata_lookup" (default OFF) so the
#      user opts in explicitly; addon never makes network calls behind
#      the user's back.
#
# Cache layout: {addon_data}/imdb_cache.json
#   { "<normalized_title>": {
#         "sub": "mv_akcny" | null,
#         "top": "show" | "sport" | "dokumenty" | "spravodajstvo" |
#                "hudba" | "detske" | null,
#         "year": 2024 | null,
#         "ts":  1735660800     # unix seconds, for diagnostics
#       },
#     ... }
#
# IMDb's GraphQL endpoint is unofficial but stable for years (the IMDb
# web frontend itself uses it). On schema changes the plugin will return
# (None, None) and degrade gracefully to the existing fallback logic.

from __future__ import absolute_import, unicode_literals, print_function

import json
import logging
import os
import re
import threading
import time
import unicodedata

try:
	import requests
except ImportError:
	requests = None

# Module-level logger. Predtým: logging.getLogger('plugin.video.tvheadend.imdb_lookup')
# — TIETO LOGY NEŠLI DO archivCZSK.log (framework zachytí len cp.log_info()).
# FIX 0.57.0: callback pattern. Provider.py si pri __init__ nastaví callback
# cez set_log_callback(self.log_info) a set_log_debug_callback(self.log_debug).
# Info messages → vždy viditeľné. Debug messages → len v ArchivCZSK Debug mode.
_LOGGER = logging.getLogger('plugin.video.tvheadend.imdb_lookup')
_LOG_CALLBACK = None        # info-level (vždy viditeľné)
_LOG_DEBUG_CALLBACK = None  # debug-level (len v Debug mode)

def set_log_callback(callback):
	"""Nastaviť log_info callback (provider.log_info). Pre warnings/info."""
	global _LOG_CALLBACK
	_LOG_CALLBACK = callback if callable(callback) else None

def set_log_debug_callback(callback):
	"""Nastaviť log_debug callback (provider.log_debug). Pre verbose tracing
	ktoré sa zobrazuje len keď je v ArchivCZSK zapnutý Debug mode."""
	global _LOG_DEBUG_CALLBACK
	_LOG_DEBUG_CALLBACK = callback if callable(callback) else None

# E2 / ArchivCZSK environment: persistent data dir via _paths helper,
# logging via the standard logging module.
try:
	from ._paths import data_path as _data_path

	_DATA_DIR = _data_path('')  # data dir root, no filename suffix

	def _log(level, msg):
		# level je legacy Kodi xbmc.LOG* numeric:
		#   0=DEBUG, 1=INFO, 2=NOTICE, 3=WARNING, 4=ERROR, 5=FATAL
		# Mapping (FIX 0.57.0):
		#   level >= 3 (warning+) → log_info (vždy viditeľné)
		#   level 0-2 (debug/info/notice) → log_debug (len v Debug mode)
		# Plus prefix '[Tvheadend.imdb]' pre easy grep.
		try:
			if level and level >= 3:
				prefix = '[Tvheadend.imdb] WARNING: '
				if _LOG_CALLBACK is not None:
					_LOG_CALLBACK(prefix + str(msg))
					return
				# Fallback: stdlib logger
				_LOGGER.warning('%s', msg)
			else:
				prefix = '[Tvheadend.imdb] '
				# Prefer debug callback (silenced in normal mode)
				if _LOG_DEBUG_CALLBACK is not None:
					_LOG_DEBUG_CALLBACK(prefix + str(msg))
				elif _LOG_CALLBACK is not None:
					_LOG_CALLBACK(prefix + str(msg))
				else:
					_LOGGER.info('%s', msg)
		except Exception:
			pass

	# Module-level enable flag. The provider sets this at login() time
	# based on self.get_setting('online_metadata_lookup'). No file flag
	# needed (E2 has no "Invalid setting type" log spam problem like
	# Kodi 21) — provider just calls set_enabled(True/False) when its
	# config changes.
	_ENABLED = False
	_SETTING_STATE_LOGGED = False

	def _setting_enabled():
		global _SETTING_STATE_LOGGED
		if not _SETTING_STATE_LOGGED:
			_SETTING_STATE_LOGGED = True
			_log(1, 'feature %s' % ('ENABLED' if _ENABLED else 'disabled'))
		return _ENABLED

	def set_enabled(enabled):
		"""Toggle the feature on/off. Called by provider.login() after
		reading the 'online_metadata_lookup' setting."""
		global _ENABLED, _SETTING_STATE_LOGGED
		new = bool(enabled)
		if new != _ENABLED:
			_ENABLED = new
			# Reset the one-shot log marker so the next classify call
			# logs the new state once.
			_SETTING_STATE_LOGGED = False
			# Toggle je dôležitý info entry — cez log_info (vždy viditeľné)
			# namiesto _log() ktorý by ho mapoval na debug level.
			try:
				if _LOG_CALLBACK is not None:
					_LOG_CALLBACK('[Tvheadend.imdb] set_enabled: %s' %
					              ('ON' if new else 'OFF'))
			except Exception:
				pass
except ImportError:
	# Standalone test mode (no E2 / ArchivCZSK)
	_DATA_DIR = '/tmp/imdb_lookup_test/'

	def _log(level, msg):
		print('imdb_lookup: %s' % msg)

	def _setting_enabled():
		return True

	def set_enabled(enabled):
		pass


_IMDB_GRAPHQL_URL = 'https://caching.graphql.imdb.com/'
_IMDB_HOME_URL = 'https://www.imdb.com/'

# IMDb GraphQL is gated behind a "looks like a real browser/bot" check on
# the User-Agent header. A plain Python requests UA gets a HTTP 403. The
# Enigma2 IMDb plugin (Dreambox, andreas.frisch@dream-property.net) uses
# Googlebot UA and has been working for years, so we use the same.
_IMDB_USER_AGENT = (
	'Mozilla/5.0 (compatible; Googlebot/2.1; '
	'+http://www.google.com/bot.html)'
)

_REQUEST_TIMEOUT = 5.0
_MIN_INTERVAL_SEC = 1.0  # rate-limit between live calls (cache hits unlimited)
_NEGATIVE_CACHE_TTL = 30 * 24 * 3600  # retry "no match" titles after 30 days

# Session reused across calls (carries the imdb.com session-id cookie that
# the GraphQL endpoint requires). Built lazily on first lookup.
_SESSION = None
_SESSION_INITIALIZED = False

# IMDb returns genres as English text. Map to our sub-genre constants
# (defined in classifier.py). We import these as strings to avoid a circular
# import — classifier.py imports this module, not the other way around.
_IMDB_GENRE_TO_SUBCAT = {
	'Action':       'mv_akcny',
	'Adventure':    'mv_dobrodr',
	'Animation':    'mv_animak',
	'Biography':    'mv_historicky',
	'Comedy':       'mv_komedia',
	'Crime':        'mv_krimi',
	'Drama':        'mv_drama',
	'Family':       'mv_dobrodr',
	'Fantasy':      'mv_scifi',
	'Film-Noir':    'mv_krimi',
	'History':      'mv_historicky',
	'Horror':       'mv_horor',
	'Mystery':      'mv_krimi',
	'Romance':      'mv_romantika',
	'Sci-Fi':       'mv_scifi',
	'Thriller':     'mv_krimi',
	'War':          'mv_historicky',
	'Western':      'mv_western',
}

# Some IMDb genres are stronger signals for the TOP category than they are
# for a Film/Series sub-genre. If any of these appear, override the top
# category. Order matters: more specific wins.
_IMDB_GENRE_TO_TOP_OVERRIDE = (
	('Reality-TV',   'show'),
	('Talk-Show',    'show'),
	('Game-Show',    'show'),
	('Documentary',  'dokumenty'),
	('News',         'spravodajstvo'),
	('Sport',        'sport'),
	('Musical',      'hudba'),
	('Music',        'hudba'),
)


# ---------------------------------------------------------------------------
# Title normalization — must match classifier._canonical_title_for_corpus()
# so the cache key is consistent with the corpus key.
# ---------------------------------------------------------------------------
_TITLE_YEAR_SUFFIX = re.compile(r'\s*\(\s*(?:19|20)\d{2}\s*\)\s*$')
_TECH_MARKER_PATTERN = re.compile(
	r'\s*\(\s*(?:ST|HD|AD|SS|3D|UHD|DD|DTS|[\d.]+)\s*\)\s*', re.IGNORECASE
)
# Episode suffix like "(12)" or "(N)" where N is not a year — for series.
_EPISODE_SUFFIX_PATTERN = re.compile(r'\s*\(\s*\d{1,3}\s*\)\s*$')


def _strip_accents_lower(s):
	if not s:
		return ''
	s = unicodedata.normalize('NFD', s)
	s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
	return s.lower().strip()


def _canonical_title(title):
	"""Match classifier._canonical_title_for_corpus() so the IMDb cache
	key collides with the corpus key for the same canonical title."""
	if not title:
		return ''
	t = _TECH_MARKER_PATTERN.sub(' ', title)
	# Strip episode suffix BEFORE year suffix (year regex is stricter).
	t = _EPISODE_SUFFIX_PATTERN.sub('', t)
	t = _TITLE_YEAR_SUFFIX.sub('', t).strip()
	t = re.sub(r'\s+', ' ', t)
	return _strip_accents_lower(t)


def _is_worth_searching(canonical):
	"""Filter out queries that are too short / generic to give useful IMDb
	matches. Returns False for things like 'PML 20', empty strings, or
	queries that are just digits. Saves wasted network calls."""
	if not canonical or len(canonical) < 4:
		return False
	# Need at least one word of >=3 letters
	words = [w for w in canonical.split() if any(c.isalpha() for c in w)]
	if not words:
		return False
	if max(len(w) for w in words) < 3:
		return False
	return True


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.RLock()
_CACHE_STATE = {
	'loaded': False,
	'data': {},       # canonical_title -> result dict
	'last_call': 0.0, # rate-limit
	'last_save': 0.0, # debounce disk writes
	'dirty': False,
}

# Background prefetch — keeps UI snappy.
# When classify_dvr_entry() asks about an uncached title, we DON'T block
# the call. Instead the title is queued for a background worker to fetch
# at rate-limited speed. The first display of a "/Other" category returns
# instantly (uncached titles fall through to keyword logic), and over the
# next few seconds the cache fills up. Second open of the same category
# shows the correct classification.
_PREFETCH_QUEUE = []      # list of (canonical_key, original_title)
_PREFETCH_SEEN = set()    # canonical_keys already queued in this session
_PREFETCH_THREAD = None
_PREFETCH_MAX_QUEUE = 500


def _cache_path():
	if not os.path.isdir(_DATA_DIR):
		try:
			os.makedirs(_DATA_DIR)
		except OSError:
			pass
	return os.path.join(_DATA_DIR, 'imdb_cache.json')


def _load_cache_if_needed():
	if _CACHE_STATE['loaded']:
		return
	path = _cache_path()
	with _CACHE_LOCK:
		if _CACHE_STATE['loaded']:
			return
		_CACHE_STATE['loaded'] = True
		if not os.path.isfile(path):
			return
		try:
			with open(path, 'r', encoding='utf-8') as f:
				_CACHE_STATE['data'] = json.load(f)
			_log(0, 'cache loaded: %d entries' % len(_CACHE_STATE['data']))
		except Exception as e:
			_log(2, 'cache load failed: %s' % e)
			_CACHE_STATE['data'] = {}


def _save_cache(force=False):
	"""Persist cache to disk. Debounced to 1×/10s unless force=True."""
	with _CACHE_LOCK:
		if not _CACHE_STATE['dirty'] and not force:
			return
		now = time.time()
		if not force and now - _CACHE_STATE['last_save'] < 10.0:
			return
		try:
			tmp = _cache_path() + '.tmp'
			with open(tmp, 'w', encoding='utf-8') as f:
				json.dump(_CACHE_STATE['data'], f, ensure_ascii=False, indent=1)
			os.replace(tmp, _cache_path())
			_CACHE_STATE['last_save'] = now
			_CACHE_STATE['dirty'] = False
		except Exception as e:
			_log(2, 'cache save failed: %s' % e)


def cache_size():
	"""For diagnostics — number of entries in cache."""
	_load_cache_if_needed()
	with _CACHE_LOCK:
		return len(_CACHE_STATE['data'])


def cache_wipe():
	"""Wipe cache (called from Settings → Diagnostics)."""
	with _CACHE_LOCK:
		_CACHE_STATE['data'] = {}
		_CACHE_STATE['dirty'] = True
		_save_cache(force=True)


# ---------------------------------------------------------------------------
# GraphQL request
# ---------------------------------------------------------------------------
_GRAPHQL_QUERY = (
	'query Search($q: String!) { '
	'  mainSearch(first: 5, options: { '
	'    searchTerm: $q '
	'    type: TITLE '
	'    titleSearchOptions: { type: [MOVIE, TV] } '
	'  }) { '
	'    edges { node { entity { ... on Title { '
	'      titleText { text } '
	'      titleType { text } '
	'      releaseYear { year } '
	'      genres { genres { text } } '
	'    } } } } '
	'  } '
	'}'
)


def _get_session():
	"""Lazy-initialise the HTTP session with imdb.com cookies."""
	global _SESSION, _SESSION_INITIALIZED
	if _SESSION_INITIALIZED:
		return _SESSION
	_SESSION_INITIALIZED = True
	if requests is None:
		return None
	s = requests.Session()
	s.headers.update({
		'User-Agent': _IMDB_USER_AGENT,
		'Accept-Language': 'en-US,en;q=0.9',
	})
	# Initial GET on imdb.com sets the session-id cookie that the GraphQL
	# endpoint requires. Failure is non-fatal — POST without cookie may
	# still work with Googlebot UA.
	try:
		s.get(_IMDB_HOME_URL, timeout=_REQUEST_TIMEOUT)
	except Exception as e:
		_log(2, 'session init GET failed (non-fatal): %s' % e)
	_SESSION = s
	return s


def _do_imdb_request(query_term):
	"""Single POST to IMDb GraphQL. Returns parsed JSON or None on failure."""
	s = _get_session()
	if s is None:
		return None
	payload = {
		'query': _GRAPHQL_QUERY,
		'variables': {'q': query_term},
	}
	headers = {
		'Content-Type': 'application/json',
		'Accept': 'application/json',
		'X-Imdb-User-Language': 'en-US',
		'X-Imdb-User-Country': 'US',
		'Origin': 'https://www.imdb.com',
		'Referer': 'https://www.imdb.com/',
	}
	try:
		r = s.post(
			_IMDB_GRAPHQL_URL,
			json=payload,
			headers=headers,
			timeout=_REQUEST_TIMEOUT,
		)
		if r.status_code != 200:
			_log(2, 'GraphQL HTTP %d for %r' % (r.status_code, query_term))
			return None
		return r.json()
	except Exception as e:
		_log(2, 'GraphQL request failed for %r: %s' % (query_term, e))
		return None


def _parse_imdb_response(data, expect_year=None):
	"""Parse GraphQL response → {'sub', 'top', 'year'} or None."""
	if not data or not isinstance(data, dict):
		return None
	try:
		edges = data['data']['mainSearch']['edges']
	except (KeyError, TypeError):
		return None
	if not edges:
		return None

	# Try each result in order — preferentially the one whose year matches
	# the expected (broadcast) year if we have one.
	candidates = []
	for edge in edges:
		try:
			ent = edge['node']['entity']
		except (KeyError, TypeError):
			continue
		if not ent:
			continue
		year = None
		try:
			year = ent.get('releaseYear', {}).get('year')
		except Exception:
			pass
		candidates.append((year, ent))

	# Pick the best candidate: matching year first, else first result
	pick = None
	if expect_year is not None:
		for y, ent in candidates:
			if y == expect_year:
				pick = ent
				break
	if pick is None and candidates:
		pick = candidates[0][1]
	if pick is None:
		return None

	# Extract genres
	genres = []
	try:
		for g in (pick.get('genres') or {}).get('genres') or []:
			t = g.get('text')
			if t:
				genres.append(t)
	except (AttributeError, TypeError):
		pass

	if not genres:
		return None

	# Top-category override has priority
	for override_name, override_top in _IMDB_GENRE_TO_TOP_OVERRIDE:
		if override_name in genres:
			return {
				'sub': None,
				'top': override_top,
				'year': pick.get('releaseYear', {}).get('year') if pick.get('releaseYear') else None,
				'genres': genres,
			}

	# Otherwise map first matching genre to a sub-genre
	sub = None
	for g in genres:
		if g in _IMDB_GENRE_TO_SUBCAT:
			sub = _IMDB_GENRE_TO_SUBCAT[g]
			break

	return {
		'sub': sub,
		'top': None,
		'year': pick.get('releaseYear', {}).get('year') if pick.get('releaseYear') else None,
		'genres': genres,
	}


# ---------------------------------------------------------------------------
# Background prefetch worker
# ---------------------------------------------------------------------------
def _prefetch_worker():
	"""Background thread that drains _PREFETCH_QUEUE. Rate-limited to one
	IMDb request per _MIN_INTERVAL_SEC. Terminates when queue is empty."""
	while True:
		with _CACHE_LOCK:
			if not _PREFETCH_QUEUE:
				return
			key, title = _PREFETCH_QUEUE.pop(0)
			# If already cached (another path got there first), skip.
			if key in _CACHE_STATE['data']:
				continue

		# Rate limit live calls
		with _CACHE_LOCK:
			elapsed = time.time() - _CACHE_STATE['last_call']
		if elapsed < _MIN_INTERVAL_SEC:
			time.sleep(_MIN_INTERVAL_SEC - elapsed)
		with _CACHE_LOCK:
			_CACHE_STATE['last_call'] = time.time()

		# Setting may have been toggled off mid-flight
		if not _setting_enabled():
			return

		try:
			data = _do_imdb_request(title)
			parsed = _parse_imdb_response(data)
		except Exception as e:
			_log(2, 'prefetch failed for %r: %s' % (title, e))
			parsed = None

		with _CACHE_LOCK:
			if parsed:
				_CACHE_STATE['data'][key] = {
					'sub': parsed.get('sub'),
					'top': parsed.get('top'),
					'year': parsed.get('year'),
					'ts': int(time.time()),
				}
				_log(1, 'prefetched %r → top=%s sub=%s year=%s genres=%s' % (
					title, parsed.get('top'), parsed.get('sub'),
					parsed.get('year'), parsed.get('genres')))
			else:
				_CACHE_STATE['data'][key] = {
					'sub': None,
					'top': None,
					'year': None,
					'ts': int(time.time()),
				}
				_log(1, 'prefetched %r → NO MATCH (negative cache)' % title)
			_CACHE_STATE['dirty'] = True
		_save_cache()


def _enqueue_for_prefetch(key, original_title):
	"""Add (key, title) to the background prefetch queue. Idempotent — same
	key only enqueued once per session. Starts the worker thread if needed."""
	global _PREFETCH_THREAD
	with _CACHE_LOCK:
		if key in _PREFETCH_SEEN:
			return
		if len(_PREFETCH_QUEUE) >= _PREFETCH_MAX_QUEUE:
			return  # back-pressure: drop oldest enqueues on huge libraries
		_PREFETCH_SEEN.add(key)
		_PREFETCH_QUEUE.append((key, original_title))

		# Start worker if not running
		if _PREFETCH_THREAD is None or not _PREFETCH_THREAD.is_alive():
			_PREFETCH_THREAD = threading.Thread(
				target=_prefetch_worker,
				name='imdb_lookup_prefetch',
				daemon=True,
			)
			_PREFETCH_THREAD.start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def lookup(entry):
	"""
	Return (top_override, sub_override) for a DVR entry, or (None, None) if
	the lookup is disabled, the title is empty, the cache has not yet been
	populated, or the negative cache says "no match".

	Non-blocking: a cache miss enqueues the title for a background worker
	and returns (None, None) immediately so the UI stays snappy. The cache
	fills up over the next few seconds; subsequent views of the same
	category show the IMDb-derived classification.

	Cached results return immediately and never wait for the network.
	"""
	if not _setting_enabled():
		return None, None
	title = entry.get('disp_title') or ''
	if not title:
		return None, None

	key = _canonical_title(title)
	if not _is_worth_searching(key):
		return None, None

	_load_cache_if_needed()

	with _CACHE_LOCK:
		cached = _CACHE_STATE['data'].get(key)

	if cached:
		# Negative cache: respect TTL
		if cached.get('sub') is None and cached.get('top') is None:
			age = time.time() - cached.get('ts', 0)
			if age < _NEGATIVE_CACHE_TTL:
				return None, None
			# else: re-queue for retry
		else:
			return cached.get('top'), cached.get('sub')

	# Cache miss → enqueue for background fetch, return (None, None) so the
	# caller falls through to its keyword fallback for this display cycle.
	_log(0, 'cache miss for %r — enqueueing for background fetch' % title)
	_enqueue_for_prefetch(key, title)
	return None, None
