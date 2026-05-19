# -*- coding: utf-8 -*-
"""
M3UProvider - external M3U + XMLTV source for Tvheadend plugin.

Fetches an M3U playlist from a URL, parses #EXTINF tags into channel
records, optionally fetches an XMLTV EPG to determine which channels
have EPG coverage, and exposes channel data for the bouquet writer.

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import re
import io
import time
import gzip
import base64

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
	from urllib.parse import urlparse, parse_qs
except ImportError:
	from urllib2 import Request, urlopen
	from urlparse import urlparse, parse_qs

try:
	from xml.etree.cElementTree import iterparse, fromstring
except ImportError:
	from xml.etree.ElementTree import iterparse, fromstring


# -------------------------------------------------
# Regex helpers for M3U parsing
# -------------------------------------------------
_EXTINF_ATTR_RE = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
_EXTINF_LINE_RE = re.compile(r'^#EXTINF:-?\d+\s*(.*?),(.*)$')

# Default HTTP User-Agent (some IPTV providers reject default urllib UA)
_DEFAULT_UA = 'Mozilla/5.0 (Enigma2; Tvheadend-plugin) M3UProvider/1.0'


def _strip_bom(s):
	if s and s[:1] == '\ufeff':
		return s[1:]
	return s


def _decode_bytes(b):
	"""Best-effort decode of HTTP body bytes -> str."""
	if isinstance(b, str):
		return b
	for enc in ('utf-8', 'utf-8-sig', 'latin-1'):
		try:
			return b.decode(enc)
		except Exception:
			continue
	return b.decode('utf-8', errors='replace')


def _maybe_decompress(data, url=''):
	"""Detect gzip/xz/plain XML by magic bytes; return raw XML bytes."""
	if not data:
		return data
	if data[:2] == b'\x1f\x8b':
		return gzip.decompress(data) if hasattr(gzip, 'decompress') \
			else gzip.GzipFile(fileobj=io.BytesIO(data)).read()
	if data[:6] == b'\xfd7zXZ\x00':
		if lzma is None:
			raise RuntimeError('XZ-compressed EPG but no lzma module available')
		return lzma.decompress(data)
	# gzip header sometimes embedded by URL .gz/.xz extension even without magic
	if url.endswith('.gz') and len(data) > 2:
		try:
			return gzip.GzipFile(fileobj=io.BytesIO(data)).read()
		except Exception:
			pass
	return data


# -------------------------------------------------
# M3UProvider
# -------------------------------------------------
class M3UProvider(object):
	"""
	External M3U + XMLTV content provider.

	Usage:
		p = M3UProvider(m3u_url='http://...', epg_url='http://...',
		                http_auth='user:pass', log=print)
		p.fetch_and_parse()
		for cat in p.get_categories():
			for ch in p.get_channels_by_category(cat):
				...
	"""

	def __init__(self, m3u_url, epg_url=None, http_auth=None,
	             user_agent=None, timeout=30, log=None):
		self.m3u_url = m3u_url
		self.epg_url = epg_url or ''
		self.http_auth = http_auth or ''
		self.user_agent = user_agent or _DEFAULT_UA
		self.timeout = timeout
		self.log = log or (lambda *a, **k: None)

		# Parsed state
		self._channels = []          # list of dicts
		self._categories = []        # ordered unique categories
		self._epg_channel_ids = set()
		self._raw_m3u_bytes = b''
		self._raw_epg_bytes = b''

	# ------------------ HTTP helpers ------------------

	def _build_request(self, url):
		req = Request(url)
		req.add_header('User-Agent', self.user_agent)
		req.add_header('Accept', '*/*')

		if self.http_auth and ':' in self.http_auth:
			token = base64.b64encode(
				self.http_auth.encode('utf-8')).decode('ascii')
			req.add_header('Authorization', 'Basic ' + token)
		return req

	def _http_get_bytes(self, url):
		req = self._build_request(url)
		resp = urlopen(req, timeout=self.timeout)
		try:
			return resp.read()
		finally:
			try:
				resp.close()
			except Exception:
				pass

	# ------------------ Public fetch API ------------------

	def fetch_and_parse(self, fetch_epg=True):
		"""Download M3U + (optionally) XMLTV. Populate channel list."""
		if not self.m3u_url:
			raise ValueError('M3U URL is empty')

		t0 = time.time()
		self.log('[M3U] Fetching playlist: %s' % self.m3u_url)
		self._raw_m3u_bytes = self._http_get_bytes(self.m3u_url)
		txt = _strip_bom(_decode_bytes(self._raw_m3u_bytes))
		self._parse_m3u_text(txt)
		self.log('[M3U] Parsed %d channels in %d categories (%.1fs)' %
		         (len(self._channels), len(self._categories), time.time() - t0))

		# Post-process: add auth token to tvg-logo URLs that point to same
		# host as M3U URL (e.g. TVH /imagecache/175 needs ?auth=<token>)
		self._auth_tvg_logos()

		if fetch_epg and self.epg_url:
			try:
				t1 = time.time()
				self.log('[M3U] Fetching EPG: %s' % self.epg_url)
				raw = self._http_get_bytes(self.epg_url)
				self._raw_epg_bytes = raw
				xml_bytes = _maybe_decompress(raw, self.epg_url)
				self._parse_xmltv_channels(xml_bytes)
				self.log('[M3U] EPG has %d channel IDs (%.1fs)' %
				         (len(self._epg_channel_ids), time.time() - t1))
			except Exception as e:
				self.log('[M3U] EPG fetch/parse failed: %s' % e)

	# ------------------ Parsers ------------------

	def _parse_m3u_text(self, text):
		"""Parse M3U / extended M3U into self._channels."""
		self._channels = []
		self._categories = []
		seen_cats = {}  # name -> index

		lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
		current = None
		line_idx = 0

		while line_idx < len(lines):
			ln = lines[line_idx].strip()
			line_idx += 1

			if not ln:
				continue

			# Skip M3U header
			if ln.startswith('#EXTM3U'):
				continue

			if ln.startswith('#EXTINF'):
				m = _EXTINF_LINE_RE.match(ln)
				if not m:
					current = None
					continue
				attr_blob = m.group(1) or ''
				display_name = (m.group(2) or '').strip()
				attrs = dict(_EXTINF_ATTR_RE.findall(attr_blob))

				current = {
					'name': display_name,
					'tvg_id': attrs.get('tvg-id', '').strip(),
					'tvg_name': attrs.get('tvg-name', display_name).strip(),
					'tvg_logo': attrs.get('tvg-logo', '').strip(),
					'tvg_chno': attrs.get('tvg-chno', '').strip(),
					'group': (attrs.get('group-title', '') or 'Uncategorized').strip(),
					'radio': attrs.get('radio', 'false').lower() == 'true',
					'url': None,
					'_extra_headers': {},
				}
				continue

			# Extended M3U "vlc-style" header directives
			if ln.startswith('#EXTVLCOPT:') and current is not None:
				kv = ln[len('#EXTVLCOPT:'):].strip()
				if '=' in kv:
					k, v = kv.split('=', 1)
					k = k.strip().lower()
					v = v.strip()
					if k == 'http-user-agent':
						current['_extra_headers']['User-Agent'] = v
					elif k == 'http-referrer':
						current['_extra_headers']['Referer'] = v
				continue

			if ln.startswith('#KODIPROP:') and current is not None:
				continue  # ignored

			if ln.startswith('#'):
				continue  # other unsupported directives

			# Stream URL line
			if current is not None and (ln.startswith('http://') or
			                            ln.startswith('https://') or
			                            ln.startswith('rtmp://') or
			                            ln.startswith('rtsp://')):
				current['url'] = ln

				cat = current['group']
				if cat not in seen_cats:
					seen_cats[cat] = len(self._categories)
					self._categories.append(cat)

				self._channels.append(current)
				current = None

	def _parse_xmltv_channels(self, xml_bytes):
		"""Stream-parse XMLTV to collect channel IDs only (memory friendly)."""
		self._epg_channel_ids = set()
		if not xml_bytes:
			return

		try:
			# iterparse over BytesIO so we don't load full tree.
			# IMPORTANT: cElementTree on Py2 rejects unicode event names
			# with "invalid event tuple" - unicode_literals makes literals
			# unicode in Py2. Convert event name to native str.
			ctx = iterparse(io.BytesIO(xml_bytes), events=(str('start'),))
			for event, elem in ctx:
				if elem.tag == 'channel':
					cid = elem.get('id')
					if cid:
						self._epg_channel_ids.add(cid)
				elif elem.tag == 'programme':
					# all channels seen by now in well-formed XMLTV
					break
		except Exception as e:
			# Fallback: full parse, but only collect <channel> tags
			self.log('[M3U] iterparse failed, falling back to fromstring: %s' % e)
			root = fromstring(xml_bytes)
			for ch in root.findall('channel'):
				cid = ch.get('id')
				if cid:
					self._epg_channel_ids.add(cid)

	# ------------------ Public accessor API ------------------

	def get_categories(self):
		return list(self._categories)

	def get_channels_by_category(self, category):
		return [c for c in self._channels if c['group'] == category]

	def get_all_channels(self):
		return list(self._channels)

	def channel_count(self):
		return len(self._channels)

	def _auth_tvg_logos(self):
		"""
		Pre tvg-logo URL ktoré pochádzajú z rovnakého hosta ako M3U URL
		(typicky TVH /imagecache/), pripoj auth token z M3U URL.

		TVH /imagecache/N endpoint vracia 401/403 bez auth tokenu, takže
		bez tejto úpravy by sa picons nedali stiahnuť z TVH M3U.
		"""
		if not self.m3u_url:
			return

		try:
			m3u_parsed = urlparse(self.m3u_url)
			m3u_qs = parse_qs(m3u_parsed.query or '')
			auth_token = ''
			for key in ('auth', 'ticket'):
				if key in m3u_qs and m3u_qs[key]:
					auth_token = m3u_qs[key][0]
					break

			if not auth_token:
				return  # M3U URL nemá token, nič nepridať

			m3u_host = (m3u_parsed.netloc or '').lower()
			if not m3u_host:
				return

			updated = 0
			for ch in self._channels:
				logo = ch.get('tvg_logo', '') or ''
				if not logo:
					continue
				try:
					lp = urlparse(logo)
				except Exception:
					continue
				# Len ak logo je z rovnakého hosta ako M3U
				if (lp.netloc or '').lower() != m3u_host:
					continue
				# Ak už má auth, nepridať znova
				if 'auth=' in (lp.query or '') or 'ticket=' in (lp.query or ''):
					continue
				sep = '&' if lp.query else '?'
				ch['tvg_logo'] = logo + sep + 'auth=' + auth_token
				updated += 1

			if updated:
				self.log('[M3U] Auth-token appended to %d tvg-logo URLs '
				         '(same host as M3U)' % updated)
		except Exception as e:
			self.log('[M3U] _auth_tvg_logos failed: %s' % e)

	def apply_tag_mapping(self, channel_to_tag_map):
		"""
		Aplikuje externý channel_id -> tag_name mapping na self._channels.
		Použité typicky pri URL-based enrichment cez /playlist/tags/auth
		(keď nemáme prístup k /api/* endpointom).

		Argument:
		    channel_to_tag_map: dict {channel_id_str: tag_name_str}

		Vráti počet updatovaných kanálov.
		"""
		updated = 0
		new_categories = []  # preserve insertion order
		_seen = set()

		# Pattern pre extrakciu channel ID z TVH stream URL
		ch_id_re = re.compile(
			r'/stream/(?:channelid|channel|service)/([^/?&]+)')

		for ch in self._channels:
			url = ch.get('url', '') or ''
			m = ch_id_re.search(url)
			if not m:
				continue
			ch_id = m.group(1)
			tag = channel_to_tag_map.get(ch_id)
			if not tag:
				continue
			# Override len ak je 'Uncategorized' alebo prazdne
			current = ch.get('group') or ''
			if current and current.lower() not in ('uncategorized', 'unknown', ''):
				continue
			ch['group'] = tag
			updated += 1

		# Rebuild categories list to reflect new tags
		for ch in self._channels:
			g = ch.get('group') or 'Uncategorized'
			if g not in _seen:
				_seen.add(g)
				new_categories.append(g)
		self._categories = new_categories

		return updated


# -------------------------------------------------
# Standalone smoke test
# -------------------------------------------------
if __name__ == '__main__':
	import sys
	if len(sys.argv) < 2:
		print('Usage: m3u_provider.py <m3u_url> [<epg_url>]')
		sys.exit(1)

	m3u = sys.argv[1]
	epg = sys.argv[2] if len(sys.argv) > 2 else None

	p = M3UProvider(m3u_url=m3u, epg_url=epg, log=print)
	p.fetch_and_parse()

	print('=' * 60)
	print('Categories (%d):' % len(p.get_categories()))
	for cat in p.get_categories():
		chs = p.get_channels_by_category(cat)
		print('  %-30s %d channels' % (cat, len(chs)))

	print('=' * 60)
	print('First 5 channels:')
	for ch in p.get_all_channels()[:5]:
		print('  %s [tvg-id=%s] -> %s' %
		      (ch['name'], ch['tvg_id'], ch['url'][:60]))
