# -*- coding: utf-8 -*-
"""
M3U EPG Injector

Parses XMLTV (the same data fetched by M3UProvider) and injects
EPG events directly into Enigma2's eEPGCache via importEvent() API.

This bypasses the external epgimport plugin entirely - EPG appears
immediately after refresh, no separate plugin needed.

Mechanism:
  1. Build mapping: every XMLTV channel id (and alias) -> service ref
  2. Stream-parse XMLTV <programme> elements (memory-friendly via iterparse)
  3. For matched programmes, build event tuples
  4. Call eEPGCache.importEvent(service_ref, [events...]) per channel

Event tuple format (Enigma2 eEPGCache API):
    (start_unix, duration_sec, title, short_desc, long_desc, event_type)

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import sys
import io
import calendar
from datetime import datetime, timedelta

try:
	from xml.etree.cElementTree import iterparse
except ImportError:
	from xml.etree.ElementTree import iterparse


# -----------------------------------------------------------------
# Py2/Py3 string compat for eEPGCache API
# -----------------------------------------------------------------
# On Python 2 with `unicode_literals` import active, all string literals
# in this module are `unicode`. But Enigma2's C++ eEPGCache.importEvent()
# on Py2 expects native `str` (= bytes), and crashes with TypeError on
# unicode input. On Python 3 the API takes `str` (= text) - no conversion
# needed.
_PY2 = sys.version_info[0] < 3

def _to_native_str(s):
	"""Convert any string-like value to the native `str` type for the
	current Python (bytes on Py2, text on Py3). Returns empty string on
	None. Safely handles already-correct types."""
	if s is None:
		return ''
	if _PY2:
		# Py2: native str == bytes. Convert unicode to UTF-8 bytes.
		try:
			if isinstance(s, unicode):  # noqa: F821 (Py2 builtin)
				return s.encode('utf-8', 'replace')
		except NameError:
			pass
		return str(s)
	else:
		# Py3: native str == text. Decode bytes if needed.
		if isinstance(s, bytes):
			return s.decode('utf-8', 'replace')
		return s


def _to_text(s):
	"""Convert any string-like value to TEXT type (unicode on Py2,
	str on Py3) for safe dict-key comparison. On Py2 a mix of str and
	unicode dict keys silently fails to match across types."""
	if s is None:
		return u''
	if _PY2:
		try:
			if isinstance(s, unicode):  # noqa: F821 (Py2 builtin)
				return s
		except NameError:
			pass
		try:
			return s.decode('utf-8', 'replace')
		except AttributeError:
			return str(s)
	else:
		if isinstance(s, bytes):
			return s.decode('utf-8', 'replace')
		return s


def _parse_xmltv_time(s):
	"""
	Parse XMLTV time stamp into unix epoch (int).
	XMLTV format: 'YYYYMMDDhhmmss ±HHMM' or 'YYYYMMDDhhmmss' (UTC).
	Examples:
		'20260512063000 +0200' -> 1747... (epoch for 04:30 UTC)
		'20260512063000'       -> epoch for 06:30 UTC
	"""
	if not s:
		return 0
	s = s.strip()
	if len(s) < 14:
		return 0
	try:
		dt = datetime.strptime(s[:14], '%Y%m%d%H%M%S')
		# Treat naive datetime as UTC, then apply explicit offset if given
		tz = s[14:].strip()
		if tz and tz[0] in ('+', '-') and len(tz) >= 5:
			sign = 1 if tz[0] == '+' else -1
			hh = int(tz[1:3])
			mm = int(tz[3:5])
			offset_min = sign * (hh * 60 + mm)
			# Convert local-with-offset to UTC
			dt = dt - timedelta(minutes=offset_min)
		# Convert UTC naive datetime to epoch
		# (calendar.timegm is the pure-UTC inverse of time.gmtime)
		return int(calendar.timegm(dt.timetuple()))
	except Exception:
		return 0


def _service_ref_for_epg(full_ref):
	"""
	Strip URL + name from full service ref, leaving first 10 fields + ':'.
	Format eEPGCache.importEvent() expects:
		'1:0:1:1:6c6e:ae88:0:0:0:0:'
	"""
	if not full_ref:
		return ''
	parts = full_ref.split(':')
	if len(parts) < 10:
		return ''
	return ':'.join(parts[:10]) + ':'


def _strip_xml_text(node):
	"""Best-effort text extraction from XMLTV sub-elements."""
	if node is None:
		return ''
	t = node.text or ''
	return t.strip()


def inject_epg_into_enigma(provider, xmltv_bytes, log=None,
                           max_title_len=255, max_desc_len=4095):
	"""
	Inject XMLTV programmes directly into Enigma2's EPG cache.

	provider:    M3UProvider with channels having '_service_ref',
	             'tvg_id' and optional '_tvg_id_aliases' (set)
	xmltv_bytes: raw (decompressed) XMLTV content (bytes)

	Returns dict: {events_total, services_total, programmes_seen,
	               programmes_matched}
	"""
	log = log or (lambda *a, **k: None)
	stats = {
		'events_total': 0,
		'services_total': 0,
		'programmes_seen': 0,
		'programmes_matched': 0,
	}

	if not xmltv_bytes:
		log('[M3U-epg] no XMLTV data to inject')
		return stats

	# Import enigma APIs - only available on real Enigma2 box
	try:
		from enigma import eEPGCache
		epgcache = eEPGCache.getInstance()
	except Exception as e:
		log('[M3U-epg] eEPGCache not available (not running on Enigma2?): %s' % e)
		return stats

	# Build lookup: lower(channel_id) -> short_service_ref
	# All keys normalised to TEXT type so Py2 str/unicode mix doesn't
	# break dict lookup later when matching against XMLTV channel ids.
	id_to_ref = {}
	for ch in provider.get_all_channels():
		full_ref = ch.get('_service_ref')
		if not full_ref:
			continue
		sref = _service_ref_for_epg(full_ref)
		if not sref:
			continue

		ids = set()
		primary = _to_text(ch.get('tvg_id') or '').strip()
		if primary:
			ids.add(primary.lower())
		for alias in (ch.get('_tvg_id_aliases') or set()):
			if alias:
				ids.add(_to_text(alias).lower())

		for cid in ids:
			# First-write wins (in case different M3U channels share an alias)
			id_to_ref.setdefault(cid, sref)

	log('[M3U-epg] built id->service_ref map: %d ids -> %d unique services' %
	    (len(id_to_ref), len(set(id_to_ref.values()))))

	# Stream-parse XMLTV
	# IMPORTANT: cElementTree on Py2 rejects unicode event names with
	# "invalid event tuple" - unicode_literals makes string literals
	# unicode in Py2. Convert event names to native str.
	events_by_ref = {}  # service_ref -> list of event tuples

	try:
		for event, elem in iterparse(io.BytesIO(xmltv_bytes),
		                             events=(str('end'),)):
			if elem.tag == 'channel':
				elem.clear()
				continue
			if elem.tag != 'programme':
				continue

			stats['programmes_seen'] += 1

			# Normalize XMLTV channel id to TEXT type for consistent
			# dict-key comparison with id_to_ref (which has TEXT keys)
			channel_id = _to_text(elem.get('channel') or '').lower().strip()
			if not channel_id:
				elem.clear()
				continue

			sref = id_to_ref.get(channel_id)
			if not sref:
				elem.clear()
				continue

			start_str = elem.get('start') or ''
			stop_str = elem.get('stop') or ''
			start = _parse_xmltv_time(start_str)
			stop = _parse_xmltv_time(stop_str)
			if not start or not stop or stop <= start:
				elem.clear()
				continue

			duration = stop - start
			if duration <= 0 or duration > 86400 * 2:  # cap at 2 days sanity
				elem.clear()
				continue

			title = _strip_xml_text(elem.find('title'))
			short_desc = _strip_xml_text(elem.find('sub-title'))
			long_desc = _strip_xml_text(elem.find('desc'))

			if not title:
				elem.clear()
				continue

			# Trim to safe sizes (DVB EIT short event descriptor limits)
			title = title[:max_title_len]
			short_desc = short_desc[:max_title_len]
			long_desc = long_desc[:max_desc_len]

			# Py2/Py3 string conversion for eEPGCache C++ API
			t_native = _to_native_str(title)
			sd_native = _to_native_str(short_desc)
			ld_native = _to_native_str(long_desc)

			# Event tuple: (start, duration, title, short, long, event_type)
			ev = (int(start), int(duration),
			      t_native, sd_native, ld_native, 0)
			events_by_ref.setdefault(sref, []).append(ev)
			stats['programmes_matched'] += 1
			elem.clear()
	except Exception as e:
		log('[M3U-epg] iterparse error: %s (will inject what was collected)' % e)

	# Flush per service ref
	# eEPGCache.importEvent(sref, events) - on Py2 needs str (bytes) sref
	# and event tuples with str (bytes) titles/desc. Older E2 images
	# may only have `importEvents` (plural) - try both.
	method = getattr(epgcache, 'importEvent', None) \
	    or getattr(epgcache, 'importEvents', None)
	if method is None:
		log('[M3U-epg] eEPGCache has neither importEvent nor importEvents!')
		return stats

	for sref, events in events_by_ref.items():
		if not events:
			continue
		# Sort by start for stable insert order
		events.sort(key=lambda e: e[0])
		# Convert service ref to native str (bytes on Py2, text on Py3)
		sref_native = _to_native_str(sref)
		try:
			method(sref_native, events)
			stats['events_total'] += len(events)
			stats['services_total'] += 1
		except Exception as e:
			log('[M3U-epg] importEvent failed for %s: %s' % (sref, e))

	# Persist EPG to disk so it survives reboot
	try:
		epgcache.save()
	except Exception as e:
		log('[M3U-epg] eEPGCache.save() failed: %s' % e)

	log('[M3U-epg] Injection complete: %d events across %d services '
	    '(seen=%d, matched=%d)' %
	    (stats['events_total'], stats['services_total'],
	     stats['programmes_seen'], stats['programmes_matched']))

	return stats
