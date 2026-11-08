# -*- coding: utf-8 -*-

import re
import struct

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler, stream_key_to_dash_url
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################
# HTTP handler for Skylink.
#
# P_dash serves playback started from the addon menu, P_playlive serves channels from the
# userbouquet - it resolves a fresh manifest URL from the channel key and redirects the player
# to the DASH handler. The license request is handled by the common implementation, URL and
# headers come from get_dash_info() in the provider.
# #################################################################################################


# #################################################################################################
# Minimal ISO BMFF helpers (Python 2 and 3) for shifting the decode time of DASH fragments.
# #################################################################################################

def _mp4_boxes(data, start, end):
	"""Yields (type, box_start, payload_start, box_end) of the boxes in data[start:end]."""
	pos = start
	while pos + 8 <= end:
		size, = struct.unpack('>I', data[pos:pos + 4])
		btype = data[pos + 4:pos + 8]
		header = 8
		if size == 1:
			size, = struct.unpack('>Q', data[pos + 8:pos + 16])
			header = 16
		elif size == 0:
			size = end - pos
		if size < header:
			return
		yield btype, pos, pos + header, pos + size
		pos += size


def mp4_track_timescale(init):
	"""Timescale of the (first) track in an init segment, from moov/trak/mdia/mdhd."""
	for btype, _s, ps, e in _mp4_boxes(init, 0, len(init)):
		if btype != b'moov':
			continue
		for btype2, _s2, ps2, e2 in _mp4_boxes(init, ps, e):
			if btype2 != b'trak':
				continue
			for btype3, _s3, ps3, e3 in _mp4_boxes(init, ps2, e2):
				if btype3 != b'mdia':
					continue
				for btype4, _s4, ps4, _e4 in _mp4_boxes(init, ps3, e3):
					if btype4 == b'mdhd':
						version = struct.unpack('>B', init[ps4:ps4 + 1])[0]
						off = ps4 + 4 + (16 if version == 1 else 8)
						return struct.unpack('>I', init[off:off + 4])[0]
	return None


def mp4_set_decode_time(data, value):
	"""Sets the decode time of the fragment to value (track timescale units): the first tfdt
	baseMediaDecodeTime becomes value and all other tfdt/sidx times are shifted by the same
	difference. Returns (data, original decode time) or (data, None) when there is no tfdt."""
	data = bytearray(data)
	fields = []

	for btype, _s, ps, e in _mp4_boxes(data, 0, len(data)):
		if btype == b'sidx':
			fields.append(('sidx', ps + 12, 8 if data[ps] == 1 else 4))
		elif btype == b'moof':
			for btype2, _s2, ps2, e2 in _mp4_boxes(data, ps, e):
				if btype2 != b'traf':
					continue
				for btype3, _s3, ps3, _e3 in _mp4_boxes(data, ps2, e2):
					if btype3 == b'tfdt':
						fields.append(('tfdt', ps3 + 4, 8 if data[ps3] == 1 else 4))

	def read(off, size):
		return struct.unpack('>Q' if size == 8 else '>I', bytes(data[off:off + size]))[0]

	first = [read(off, size) for kind, off, size in fields if kind == 'tfdt']
	if not first:
		return bytes(data), None

	delta = first[0] - value
	for _kind, off, size in fields:
		fmt = '>Q' if size == 8 else '>I'
		data[off:off + size] = struct.pack(fmt, max(0, read(off, size) - delta))

	return bytes(data), first[0]


# #################################################################################################

class SkylinkHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
	# 'T<offset>s<timescale>o<time>' in a segment URL - see fix_static_timeline_offset
	TIME_OFFSET_RE = re.compile(r'T(\d+)s(\d+)o(\d+)')

	def __init__(self, content_provider, addon):
		super(SkylinkHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True
		# the resolved stream URL is kept only for a short time: while playing, the player refreshes
		# the manifest via /dash (the URL is encoded in it); the next tune-in asks for a fresh one
		self.cache_life = 60
		self._headers_web = None

	# #################################################################################################

	def ensure_stream_headers(self):
		"""Segments are downloaded via the handler's req_session (its own session, not the API one)
		and the framework doesn't pass dash_info headers to them, so the CDN headers are set on
		this session here. They depend on the selected brand (Origin/Referer), which is known only
		after login, so they are applied when the brand's web URL changes - not on every manifest."""
		try:
			web = self.cp.api.web_url()
			if web != self._headers_web:
				self.req_session.headers.update(self.cp.stream_headers(web))
				self._headers_web = web
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	def get_stream_info_by_channel_key(self, channel_key):
		try:
			stream = self.cp.get_stream_info(channel_key)
		except Exception:
			self.cp.log_exception()
			return None

		if not stream.get('url'):
			return None

		max_bitrate = self.cp.get_setting('max_bitrate')
		try:
			max_bitrate = int(max_bitrate)
		except Exception:
			max_bitrate = 0
		max_bitrate = max_bitrate * 1000000 if max_bitrate > 0 else 1000000000

		# pick the representation according to the configured resolution
		bandwidth = max_bitrate
		try:
			streams = self.cp.resolve_streams_for_channel(stream['url'])
			if streams:
				bandwidth = int(streams[0]['bandwidth'])
		except Exception:
			self.cp.log_exception()

		return {
			'url': stream['url'],
			'bandwidth': bandwidth,
			'license_url': stream.get('license_url', ''),
			'drm_system': stream.get('drm_system', ''),
			'privacy_mode': bool(self.cp.get_setting('privacy_mode')),
			'web': self.cp.api.web_url(),
		}

	# #################################################################################################

	def P_playlive(self, request, path):
		"""Channel started from the userbouquet - the path carries the encoded channel key."""
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index'):
			path = path[:-6]

		try:
			channel_key = self.decode_channel_key(path)
		except Exception:
			return self.reply_error404(request)

		stream_info = self.live_cache_get(channel_key)

		# after a PlayReady failure a new URL for Widevine is needed
		if stream_info and self.cp.drm_failed and str(stream_info.get('drm_system', '')).lower().startswith('play'):
			stream_info = None

		if not stream_info:
			stream_info = self.get_stream_info_by_channel_key(channel_key)
			if not stream_info:
				return self.reply_error404(request)

			self.live_cache_put(channel_key, stream_info)

		# redirect to /dash/<key>.mpd - the player refreshes the manifest from this URL from now on
		return self.reply_redirect(request, stream_key_to_dash_url(self.cp.http_endpoint, stream_info))

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		"""Common processing plus Skylink specific manifest cleanup.

		1. When segments are decrypted by the framework (internal decrypt, e.g. gstplayer),
		   subtitle AdaptationSets are removed first: their init segment is not a CENC
		   protected mp4 and the decrypt step fails on it (HTTP 501), which makes the
		   player give up. With exteplayer3 the player decrypts itself, so they are kept.
		2. Skylink splits video into two AdaptationSets - one with resolutions up to 720p
		   and one with 1080p only. The common processing keeps one representation per
		   set, so two would remain and the player could pick a higher one than
		   configured - only one video set is kept.
		3. Live: all tracks get the same segment time span (align_live_timelines).
		4. Archive (static manifest, segments served through the proxy): the segment
		   timeline and the fragments' decode times are wall-clock based, which gstplayer
		   shows as a position of many hours into the recording and seeking fails.
		   The timeline is rebased to zero, see fix_static_timeline_offset.
		"""
		self.ensure_stream_headers()
		internal_decrypt = dash_info.get('dash_internal_decrypt', self.dash_internal_decrypt)

		if internal_decrypt:
			try:
				self.remove_subtitle_sets(root)
			except Exception:
				self.cp.log_exception()

		had_video = self.has_video(root)

		super(SkylinkHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
		                                                           dash_info, cache_key)

		# no key came for PlayReady - Widevine is used from now on
		if had_video and not self.has_video(root) and 'pr' in (dash_info.get('drm') or {}):
			self.cp.drm_failed = True

		try:
			self.keep_single_video_set(root, bandwidth)
			self.align_live_timelines(root)
			if internal_decrypt:
				self.fix_static_timeline_offset(root)
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	@staticmethod
	def _ns(root):
		ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
		return '{%s}' % ns if ns else ''

	# #################################################################################################

	@classmethod
	def has_video(cls, root):
		"""Whether the manifest contains at least one video AdaptationSet."""
		ns = cls._ns(root)

		for e_set in root.iter('%sAdaptationSet' % ns):
			if e_set.get('contentType') == 'video' or (e_set.get('mimeType') or '').startswith('video/'):
				return True

		return False

	# #################################################################################################

	@classmethod
	def remove_subtitle_sets(cls, root):
		"""Removes all subtitle (text) AdaptationSets from the manifest."""
		ns = cls._ns(root)

		for e_period in root.findall('%sPeriod' % ns):
			for e_set in e_period.findall('%sAdaptationSet' % ns):
				content_type = e_set.get('contentType', '')
				mime_type = e_set.get('mimeType', '') or ''
				codecs = (e_set.get('codecs', '') or '').lower()
				if content_type in ('text', 'subtitle') or mime_type.startswith('text/') or mime_type == 'application/ttml+xml' \
					or codecs.startswith('stpp') or codecs.startswith('wvtt'):
					e_period.remove(e_set)
					continue

				# contentType/mimeType may be set only on the Representation
				for e_rep in e_set.findall('%sRepresentation' % ns):
					r_mime = e_rep.get('mimeType', '') or ''
					r_codecs = (e_rep.get('codecs', '') or '').lower()
					if r_mime.startswith('text/') or r_codecs.startswith('stpp') or r_codecs.startswith('wvtt'):
						e_period.remove(e_set)
						break

	# #################################################################################################

	@classmethod
	def align_live_timelines(cls, root):
		"""Gives all live tracks the same segment time span.

		exteplayer3 (dashdec) computes the start of each track separately from the end
		of its timeline and then shifts the times of each track from zero. Skylink often
		has one video segment more than audio in the manifest and refreshes the manifest
		every 2 seconds, so the tracks start from different segments and the audio stays
		out of sync.
		"""
		if root.get('type') != 'dynamic':
			return

		ns = cls._ns(root)

		# the manifest must not be refreshed while the tracks are being opened at start
		m = re.match(r'^PT([\d.]+)S$', root.get('minimumUpdatePeriod') or '')
		if m and float(m.group(1)) < 10:
			root.set('minimumUpdatePeriod', 'PT10S')

		for e_period in root.findall('%sPeriod' % ns):
			tracks = []
			for e_template in e_period.iter('%sSegmentTemplate' % ns):
				e_timeline = e_template.find('%sSegmentTimeline' % ns)
				if e_timeline is None:
					continue

				timescale = float(e_template.get('timescale') or 1)
				offset = int(e_template.get('presentationTimeOffset') or 0)
				segments = []
				t = 0
				for e_s in e_timeline.findall('%sS' % ns):
					t = int(e_s.get('t', t))
					d = int(e_s.get('d'))
					for _i in range(int(e_s.get('r') or 0) + 1):
						segments.append(((t - offset) / timescale, (t + d - offset) / timescale, t, d))
						t += d

				# r=-1 (repeat until the end) can't be expanded this way
				if segments and all(int(e_s.get('r') or 0) >= 0 for e_s in e_timeline.findall('%sS' % ns)):
					tracks.append((e_timeline, segments))

			if len(tracks) < 2:
				continue

			# common span of all tracks, half a second tolerance for small time differences
			start = max(seg[0][0] for _e, seg in tracks) - 0.5
			end = min(seg[-1][1] for _e, seg in tracks) + 0.5

			for e_timeline, segments in tracks:
				keep = [s for s in segments if s[0] >= start and s[1] <= end]
				if not keep or len(keep) == len(segments):
					continue

				for e_s in list(e_timeline):
					e_timeline.remove(e_s)

				for _start, _end, t, d in keep:
					e_s = e_timeline.makeelement('%sS' % ns, {'t': str(t), 'd': str(d)})
					e_timeline.append(e_s)

	# #################################################################################################

	@classmethod
	def keep_single_video_set(cls, root, bandwidth):
		"""Of all video AdaptationSets keeps the one whose representation best fits
		the selected bandwidth."""
		ns = cls._ns(root)

		for e_period in root.findall('%sPeriod' % ns):
			video_sets = []
			for e_set in e_period.findall('%sAdaptationSet' % ns):
				content_type = e_set.get('contentType', '')
				mime_type = e_set.get('mimeType', '') or ''
				if content_type == 'video' or mime_type.startswith('video/'):
					best = 0
					for e_rep in e_set.findall('%sRepresentation' % ns):
						try:
							best = max(best, int(e_rep.get('bandwidth') or 0))
						except Exception:
							pass
					video_sets.append((best, e_set))

			if len(video_sets) < 2:
				continue

			# the closest one below or equal to the selected bandwidth, otherwise the lowest
			allowed = [v for v in video_sets if v[0] <= bandwidth]
			if allowed:
				chosen = max(allowed, key=lambda v: v[0])[1]
			else:
				chosen = min(video_sets, key=lambda v: v[0])[1]

			for _best, e_set in video_sets:
				if e_set is not chosen:
					e_period.remove(e_set)

	# #################################################################################################

	@classmethod
	def fix_static_timeline_offset(cls, root):
		"""For a static (archive) manifest moves the segment timeline of every track to zero.

		Broadpeak DVR manifests have segment times based on wall-clock time (a huge value)
		with a matching presentationTimeOffset, but gstplayer ignores the offset and takes
		the decode time from the fragments, so it reports a position of many hours and
		seeking fails. The timeline is rebased so that the first segment starts at (nearly)
		zero and presentationTimeOffset keeps only the small remaining part. The media URL uses $Time$, so the original
		offset and the timescale are kept in the URL template as 'T<offset>s<timescale>o$Time$';
		P_dsp adds the offset back before fetching the segment and sets the decode time
		(tfdt/sidx) inside the fragment to the rebased segment time, whatever base the
		packager used for it.
		"""
		if root.get('type') == 'dynamic':
			return

		ns = cls._ns(root)

		for e_template in root.iter('%sSegmentTemplate' % ns):
			e_timeline = e_template.find('%sSegmentTimeline' % ns)
			media = e_template.get('media') or ''
			if e_timeline is None or '$Time$' not in media or cls.TIME_OFFSET_RE.search(media.replace('$Time$', '0')):
				continue

			segments = e_timeline.findall('%sS' % ns)
			if not segments or not segments[0].get('t'):
				continue

			# the first segment may start a bit before the period start (presentationTimeOffset
			# is then larger than its time) - shift by the smaller of the two so no time goes
			# negative and keep the small remaining offset, which the player handles fine
			pto = int(e_template.get('presentationTimeOffset') or 0)
			first = int(segments[0].get('t'))
			offset = min(pto, first) if pto else first
			if offset == 0:
				continue

			t = 0
			for e_s in segments:
				t = int(e_s.get('t', t))
				e_s.set('t', str(t - offset))
				t += int(e_s.get('d')) * (int(e_s.get('r') or 0) + 1)

			if pto:
				e_template.set('presentationTimeOffset', str(pto - offset))
			e_template.set('media', media.replace('$Time$', 'T%ds%so$Time$' % (offset, e_template.get('timescale') or '1')))

	# #################################################################################################

	def P_dsp(self, request, path):
		"""Segments of a rebased archive timeline (see fix_static_timeline_offset): restores the
		original segment time in the URL and shifts the decode time inside the fragment."""
		m = self.TIME_OFFSET_RE.search(path)
		if not m:
			return super(SkylinkHTTPRequestHandler, self).P_dsp(request, path)

		offset, timescale, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
		path = path[:m.start()] + str(offset + t) + path[m.end():]
		data = super(SkylinkHTTPRequestHandler, self).P_dsp(request, path)

		try:
			segment_type = path.split('/')[1]
			if data and segment_type[0] == 'm':
				track_timescale = self._track_timescale(path.split('/')[0], segment_type[1:])
				if track_timescale:
					# decode time inside the fragment = time of the segment in the rebased manifest
					data, original = mp4_set_decode_time(data, t * track_timescale // timescale)
					self.log_devel("Segment time %d/%d: fragment decode time %s -> %d/%d" % (t, timescale, original, t * track_timescale // timescale, track_timescale))
		except Exception:
			self.cp.log_exception()

		return data

	# #################################################################################################

	def _track_timescale(self, stream_key, track_id):
		"""Timescale of the track from its init segment (stored by the framework in scache)."""
		cache_data = self.scache.get(stream_key)
		init = (cache_data or {}).get('init', {}).get(track_id)
		if not init:
			return None

		cache = self.__dict__.setdefault('_timescales', {})
		key = (stream_key, track_id)
		if key not in cache:
			cache[key] = mp4_track_timescale(init)
		return cache[key]

	# #################################################################################################

	def default_handler(self, request, path_full):
		data = 'Default Skylink handler for path: %s' % path_full
		return self.reply_ok(request, data.encode('utf-8'), 'text/plain; charset=UTF-8')
