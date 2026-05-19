# -*- coding: utf-8 -*-
"""
M3U TVH Enricher

Many TVH M3U endpoints (`/playlist/channels`) do NOT include `group-title`
or `tvg-id` attributes in #EXTINF lines, so the resulting bouquet ends
up with everything in "Uncategorized" and no EPG match.

This module enriches an M3UProvider's parsed channel list using the
existing Tvheadend API client (from tvheadend.py). It detects whether
the M3U stream URLs point to a TVH server, then queries the TVH API
to fill in:

    channel['group']     <- first tag name from TVH channel
    channel['tvg_id']    <- channel UUID from TVH
    channel['tvg_logo']  <- icon_public_url from TVH (if missing)

Detection: stream URL matches one of:
    /stream/channelid/<numeric_or_uuid>
    /stream/channel/<uuid>
    /stream/channelnumber/<n>

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import re


# TVH stream URL patterns
_TVH_STREAM_RE = re.compile(
	r'/stream/(channelid|channel|channelnumber)/([^/?&]+)',
	re.IGNORECASE
)

# Slugify regex for channel name aliases
_SLUG_RE = re.compile(r'[^a-zA-Z0-9]+')


def _slugify(name):
	if not name:
		return ''
	s = _SLUG_RE.sub('_', name).strip('_').lower()
	return s


def _extract_tvh_channel_id(url):
	"""
	Returns (kind, value) for TVH stream URLs:
		('channelid',     '1818809399')
		('channel',       'abcdef12-...')
		('channelnumber', '23')
	or None if URL is not a TVH stream.
	"""
	if not url:
		return None
	m = _TVH_STREAM_RE.search(url)
	if not m:
		return None
	return (m.group(1).lower(), m.group(2))


def looks_like_tvh_playlist(channels, sample_size=5):
	"""Heuristic: are at least 80% of first N channel URLs TVH stream URLs?"""
	if not channels:
		return False
	sample = channels[:sample_size]
	hits = sum(1 for ch in sample
	           if _extract_tvh_channel_id(ch.get('url', '')) is not None)
	return hits >= max(1, len(sample) * 0.8)


def enrich_with_tvh(provider, tvh_client, log=None,
                    name_match_fallback=True,
                    fill_logo=True, force=False):
	"""
	Enrich provider._channels in place using TVH API data.

	Returns dict with stats: {matched, by_id, by_name, missed}.
	"""
	log = log or (lambda *a, **k: None)

	if not provider._channels:
		log('[M3U-enrich] provider has no channels')
		return {'matched': 0, 'by_id': 0, 'by_name': 0, 'missed': 0}

	if not force and not looks_like_tvh_playlist(provider._channels):
		log('[M3U-enrich] M3U URLs do not look like TVH stream URLs; skipping')
		return {'matched': 0, 'by_id': 0, 'by_name': 0, 'missed': 0}

	# Fetch TVH metadata
	try:
		tvh_channels = tvh_client.get_channels()
	except Exception as e:
		log('[M3U-enrich] get_channels() failed: %s' % e)
		return {'matched': 0, 'by_id': 0, 'by_name': 0, 'missed': 0}

	try:
		tvh_tags = tvh_client.get_tags() or []
	except Exception as e:
		log('[M3U-enrich] get_tags() failed: %s' % e)
		tvh_tags = []

	# Build lookup maps
	tag_uuid_to_name = {}
	for t in tvh_tags:
		uuid = t.get('uuid') or t.get('id')
		name = t.get('name') or ''
		if uuid and name:
			tag_uuid_to_name[uuid] = name

	by_uuid = {}
	by_name_lower = {}
	by_number = {}

	# TVH channel records typically have: uuid, name, number, tags, icon_public_url
	# The numeric channelid used in /stream/channelid/<N> URLs is the channel
	# "id" field (signed int). Some TVH versions expose this as 'id', others
	# rely on the URL's UUID.
	for ch in tvh_channels:
		uuid = ch.get('uuid') or ch.get('id') or ''
		name = (ch.get('name') or '').strip()
		num  = ch.get('number')
		if uuid:
			by_uuid[str(uuid)] = ch
		if name:
			by_name_lower[name.lower()] = ch
		if num is not None:
			try:
				by_number[str(int(num))] = ch
			except (TypeError, ValueError):
				pass

	log('[M3U-enrich] TVH inventory: %d channels, %d tags' %
	    (len(tvh_channels), len(tag_uuid_to_name)))

	# Walk M3U channels and enrich
	stats = {'matched': 0, 'by_id': 0, 'by_name': 0, 'missed': 0}
	rebuilt_categories = []
	seen_categories = set()

	for m_ch in provider._channels:
		tvh_ch = None
		match_kind = None

		# Try URL-based match first
		key = _extract_tvh_channel_id(m_ch.get('url', ''))
		if key is not None:
			kind, value = key
			if kind == 'channelnumber':
				tvh_ch = by_number.get(str(value))
				if tvh_ch:
					match_kind = 'by_id'
			else:
				tvh_ch = by_uuid.get(str(value))
				if tvh_ch:
					match_kind = 'by_id'

		# Fallback: match by channel name
		if tvh_ch is None and name_match_fallback:
			lname = (m_ch.get('name') or '').strip().lower()
			if lname:
				tvh_ch = by_name_lower.get(lname)
				if tvh_ch:
					match_kind = 'by_name'

		if tvh_ch is None:
			stats['missed'] += 1
			# Track original group anyway (don't drop the channel)
			cat = m_ch.get('group') or 'Uncategorized'
			if cat not in seen_categories:
				seen_categories.add(cat)
				rebuilt_categories.append(cat)
			continue

		stats['matched'] += 1
		stats[match_kind] += 1

		# Collect all possible tvg-id aliases for this channel.
		# TVH XMLTV may use any of these as <channel id="X">:
		#   - UUID (hex string like "abc-def-1234")
		#   - numeric channel id (e.g. "1818809399")
		#   - channel name (e.g. "Jednotka HD")
		#   - slug (e.g. "jednotka_hd")
		# We emit channels.xml entries for ALL aliases so at least one
		# of them will match whatever TVH XMLTV produces.
		aliases = set()

		uuid = tvh_ch.get('uuid') or ''
		if uuid:
			aliases.add(str(uuid))

		num_id = tvh_ch.get('id')
		if num_id is not None and num_id != uuid:
			try:
				aliases.add(str(int(num_id)))
			except (TypeError, ValueError):
				aliases.add(str(num_id))

		ch_num = tvh_ch.get('number')
		if ch_num is not None:
			try:
				aliases.add('channel_number_' + str(int(ch_num)))
			except (TypeError, ValueError):
				pass

		tvh_name = tvh_ch.get('name') or ''
		if tvh_name:
			aliases.add(tvh_name)
			slug = _slugify(tvh_name)
			if slug:
				aliases.add(slug)

		# Preserve M3U's existing tvg_id as primary (it may already match
		# the XMLTV source if TVH provides matching IDs in M3U+XMLTV);
		# otherwise use UUID as primary.
		existing_tvg_id = (m_ch.get('tvg_id') or '').strip()
		if existing_tvg_id:
			aliases.add(existing_tvg_id)
		elif uuid:
			m_ch['tvg_id'] = str(uuid)

		# Store full alias set for channels.xml writer
		m_ch['_tvg_id_aliases'] = aliases

		# Fill group from first tag
		tag_uuids = tvh_ch.get('tags') or []
		first_tag_name = ''
		for tuid in tag_uuids:
			if tuid in tag_uuid_to_name:
				first_tag_name = tag_uuid_to_name[tuid]
				break

		if first_tag_name:
			m_ch['group'] = first_tag_name
		# else: leave group as parsed from M3U (or Uncategorized)

		# Fill tvg-logo if empty
		if fill_logo and not m_ch.get('tvg_logo'):
			icon = tvh_ch.get('icon_public_url') or ''
			if icon:
				# icon_public_url is usually relative ("imagecache/123")
				# Build absolute URL using tvh base_url
				try:
					base = tvh_client.base_url()
				except Exception:
					base = ''
				if icon.startswith('http'):
					m_ch['tvg_logo'] = icon
				elif base:
					m_ch['tvg_logo'] = base.rstrip('/') + '/' + icon.lstrip('/')

		# Track category in insertion order
		cat = m_ch['group']
		if cat not in seen_categories:
			seen_categories.add(cat)
			rebuilt_categories.append(cat)

	# Replace category order in the provider
	provider._categories = rebuilt_categories

	log('[M3U-enrich] Matched %d/%d channels (by_id=%d, by_name=%d, missed=%d), '
	    'final categories=%d' %
	    (stats['matched'], len(provider._channels),
	     stats['by_id'], stats['by_name'], stats['missed'],
	     len(rebuilt_categories)))

	return stats


def derive_tvh_xmltv_url(tvh_client):
	"""
	Returns TVH's XMLTV endpoint URL (with credentials) for use as
	m3u_epg_url. The channel/@id in this XMLTV matches channel UUIDs,
	so after enrichment our channels.xml will reference the right ids.

	Path: <base>/xmltv/channels   (TVH 4.2+ standard)
	"""
	try:
		base = tvh_client.base_url()
	except Exception:
		return ''
	if not base:
		return ''
	# _url_with_creds embeds user:pass@host for endpoints that need basic auth
	url = base.rstrip('/') + '/xmltv/channels'
	try:
		url = tvh_client._url_with_creds(url)
	except Exception:
		pass
	return url
