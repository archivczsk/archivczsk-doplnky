# -*- coding: utf-8 -*-
"""
M3U TVH Auth-Token Client

When the user has set only M3U URL (without separate TVH username/password
in plugin settings) but the M3U URL contains a TVH auth token like
'?auth=Pg6Guxs.YMDKvEAr3ylwG72cqIb4', we can still call TVH /api/*
endpoints using that same token.

This module provides a lightweight TVH client that:
  - Extracts base URL + auth token from M3U URL
  - Calls /api/channel/grid and /api/channeltag/grid using ?auth=<token>
  - Returns the same data shape as the full Tvheadend class
  - Is fully self-contained (no dependency on the main tvheadend.py)

Used as fallback enrichment path when plugin's TVH client is not
configured but the M3U URL is from TVH.

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import json
import re

try:
	from urllib.request import Request, urlopen
	from urllib.parse import urlparse, parse_qs
except ImportError:
	from urllib2 import Request, urlopen
	from urlparse import urlparse, parse_qs


_TVH_PATH_RE = re.compile(r'/(?:playlist|xmltv|stream|api)(?:/|$|\?)',
                          re.IGNORECASE)


def is_tvh_url(url):
	"""Heuristic: does URL look like a TVH endpoint?"""
	if not url:
		return False
	return bool(_TVH_PATH_RE.search(url))


def parse_tvh_url(url):
	"""
	Extract (base_url, auth_token) from a TVH URL.
	Returns (None, None) if URL isn't a TVH URL.

	Example:
	  parse_tvh_url('http://host:9981/playlist/auth?auth=ABC&profile=pass')
	  -> ('http://host:9981', 'ABC')
	"""
	if not is_tvh_url(url):
		return None, None
	try:
		p = urlparse(url)
		base = '{}://{}'.format(p.scheme, p.netloc)
		qs = parse_qs(p.query or '')
		auth = ''
		for key in ('auth', 'ticket'):
			if key in qs and qs[key]:
				auth = qs[key][0]
				break
		return base, auth
	except Exception:
		return None, None


class TvhAuthTokenClient(object):
	"""
	Drop-in subset of the main Tvheadend class, but uses ?auth=<token>
	query parameter for all API calls instead of HTTP Basic/Digest.

	Implements just the methods needed by m3u_tvh_enricher:
	    - base_url()
	    - get_channels()
	    - get_tags()
	"""

	def __init__(self, base_url, auth_token, log=None, timeout=20):
		self._base = base_url.rstrip('/')
		self._token = (auth_token or '').strip()
		self._timeout = timeout
		self.log = log or (lambda *a, **k: None)
		self._channels_cache = None
		self._tags_cache = None

	def base_url(self):
		return self._base

	def _build_url(self, path, params=None):
		path = path.lstrip('/')
		url = '{}/{}'.format(self._base, path)
		query = []
		if params:
			for k, v in params.items():
				query.append('{}={}'.format(k, v))
		if self._token:
			query.append('auth={}'.format(self._token))
		if query:
			sep = '&' if '?' in url else '?'
			url = url + sep + '&'.join(query)
		return url

	def _http_get_json(self, url):
		req = Request(url)
		req.add_header('User-Agent', 'Tvheadend-plugin/AuthToken')
		req.add_header('Accept', 'application/json')
		resp = urlopen(req, timeout=self._timeout)
		try:
			raw = resp.read()
		finally:
			try:
				resp.close()
			except Exception:
				pass
		if isinstance(raw, bytes):
			raw = raw.decode('utf-8', errors='replace')
		return json.loads(raw)

	def api_get(self, path, params=None):
		"""Compatibility shim - returns dict with 'entries' / 'total'."""
		url = self._build_url(path, params=params)
		return self._http_get_json(url)

	def api_get_all(self, path, params=None, page_limit=1000):
		"""Pagination over /api/* grid endpoints."""
		params = dict(params or {})
		params.setdefault('start', 0)
		params['limit'] = page_limit

		entries = []
		while True:
			params['start'] = len(entries)
			data = self.api_get(path, params=params)
			batch = (data or {}).get('entries') or []
			if not batch:
				break
			entries.extend(batch)
			total = (data or {}).get('total')
			if total is not None and len(entries) >= int(total):
				break
			if len(batch) < page_limit:
				break
		return entries

	def get_channels(self, force=False):
		if not force and self._channels_cache is not None:
			return self._channels_cache
		try:
			result = self.api_get_all('api/channel/grid', {'start': 0},
			                          page_limit=1000)
		except Exception as e:
			self.log('[TVH-token] get_channels failed: %s' % e)
			result = []
		self._channels_cache = result
		return result

	def get_tags(self):
		if self._tags_cache is not None:
			return self._tags_cache
		try:
			result = self.api_get_all('api/channeltag/grid', {'start': 0},
			                          page_limit=200)
		except Exception as e:
			self.log('[TVH-token] get_tags failed: %s' % e)
			result = []
		self._tags_cache = result
		return result

	def check_login(self):
		"""Minimal self-test: call /api/serverinfo and verify response."""
		url = self._build_url('api/serverinfo')
		try:
			data = self._http_get_json(url)
			return bool(data)
		except Exception as e:
			raise RuntimeError('TVH auth-token login failed: %s' % e)


def build_token_client_from_url(m3u_url, log=None):
	"""
	Convenience factory: takes M3U URL, returns ready-to-use
	TvhAuthTokenClient or None if URL isn't a TVH URL.
	"""
	base, token = parse_tvh_url(m3u_url)
	if not base:
		return None
	return TvhAuthTokenClient(base, token, log=log)


# ---------------------------------------------------------------------------
# URL-based tag enrichment (works even when /api/* requires Basic auth)
#
# TVH exposes /playlist/tags/auth?auth=<token> which returns a meta M3U
# listing each tag as a sub-playlist. The same auth token used for the main
# /playlist/auth M3U works here, so this path needs NO username/password
# and no /api/* permissions on the ticket.
# ---------------------------------------------------------------------------

def _extract_channel_id_from_url(url):
	"""Extract channel ID from TVH stream URL like /stream/channelid/<id>."""
	if not url:
		return None
	m = re.search(r'/stream/(?:channelid|channel|service)/([^/?&]+)', url)
	return m.group(1) if m else None


def _http_get_text(url, timeout=20):
	"""Simple HTTP GET that returns decoded text."""
	req = Request(url)
	req.add_header('User-Agent', 'Tvheadend-plugin/TagsViaURL')
	resp = urlopen(req, timeout=timeout)
	try:
		data = resp.read()
	finally:
		try:
			resp.close()
		except Exception:
			pass
	if isinstance(data, bytes):
		data = data.decode('utf-8', errors='replace')
	return data


def fetch_tvh_tags_via_url(m3u_url, log=None, timeout=20):
	"""
	Fetch channel_id -> tag_name mapping using TVH's /playlist/tags endpoint.

	This is the most robust enrichment path:
	  - Uses same auth token as M3U URL (no separate credentials needed)
	  - Doesn't require API permissions on the ticket
	  - Works on all TVH versions that support /playlist/tags/auth

	URL transformation:
	  M3U URL:    http://host:9981/playlist/auth?auth=TOKEN[&profile=pass]
	  Tags URL:   http://host:9981/playlist/tags/auth?auth=TOKEN

	Returns:
	  dict mapping channel_id (str) -> tag_name (str), or {} on failure
	"""
	log = log or (lambda *a, **k: None)

	base, token = parse_tvh_url(m3u_url)
	if not base:
		log('[tags-url] not a TVH URL, skipping')
		return {}

	# Build tags meta URL by inserting /tags before /auth
	tags_meta_url = '%s/playlist/tags/auth' % base
	if token:
		tags_meta_url += '?auth=%s' % token

	log('[tags-url] fetching tags meta from: %s' % tags_meta_url)
	try:
		meta = _http_get_text(tags_meta_url, timeout=timeout)
	except Exception as e:
		log('[tags-url] tags meta fetch FAILED: %s' % e)
		return {}

	# Parse meta M3U format:
	#   #EXTM3U
	#   #EXTINF:-1 type="playlist",TagName1
	#   http://host:9981/playlist/tagid/<id>?profile=pass
	#   #EXTINF:-1 type="playlist",TagName2
	#   http://host:9981/playlist/tagid/<id>?profile=pass
	tags = []  # list of (tag_name, tag_url)
	pending_name = None
	for line in meta.splitlines():
		line = line.strip()
		if not line:
			continue
		if line.startswith('#EXTINF') and 'playlist' in line.lower():
			if ',' in line:
				pending_name = line.split(',', 1)[1].strip()
		elif line.startswith('http') and pending_name:
			# Ensure auth token is propagated to the tag URL
			url = line
			if token and 'auth=' not in url:
				url += ('&' if '?' in url else '?') + 'auth=' + token
			tags.append((pending_name, url))
			pending_name = None
		elif line.startswith('#EXTINF') or line.startswith('#'):
			# Non-playlist EXTINF or comment — ignore
			pending_name = None

	log('[tags-url] found %d TVH tags' % len(tags))

	# For each tag, fetch its M3U and extract channel IDs
	channel_to_tag = {}
	for tag_name, tag_url in tags:
		try:
			content = _http_get_text(tag_url, timeout=timeout)
		except Exception as e:
			log('[tags-url] tag "%s" fetch FAILED: %s' % (tag_name, e))
			continue

		channels_in_tag = 0
		for line in content.splitlines():
			line = line.strip()
			if line.startswith('http') and '/stream/' in line:
				ch_id = _extract_channel_id_from_url(line)
				if ch_id and ch_id not in channel_to_tag:
					channel_to_tag[ch_id] = tag_name
					channels_in_tag += 1

		log('[tags-url] tag "%s": %d channels' % (tag_name, channels_in_tag))

	log('[tags-url] total mapped: %d channels' % len(channel_to_tag))
	return channel_to_tag
