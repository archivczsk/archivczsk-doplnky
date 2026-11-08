# -*- coding: utf-8 -*-
import re
import struct
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler, stream_key_to_dash_url
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler


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
# HTTP handler for Canal+.
#
# P_dash serves playback started from the addon menu, P_playlive serves channels from the userbouquet.
# The Canal+ license is not a plain POST to one URL but a GetLicence call with an envelope
# (LiveToken, EpgId, challenge) - that's why get_drm_license is overridden.
# #################################################################################################


class CanalplusHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
	# 'T<offset>s<timescale>o<time>' in a segment URL - see fix_static_timeline_offset
	TIME_OFFSET_RE = re.compile(r'T(\d+)s(\d+)o(\d+)')

	def __init__(self, content_provider, addon):
		super(CanalplusHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True
		# the resolved stream URL is kept only for a short time: while playing, the player refreshes
		# the manifest via /dash (the URL is encoded in it); the next tune-in asks for a fresh one
		self.cache_life = 60

		# Segments are downloaded via the handler's req_session (its own session, not the API one) and
		# the framework doesn't pass dash_info headers to them - so the CDN headers are set on this
		# session once here. The DRM path (PlayReady/Widevine) depends on the Python version and
		# doesn't change at runtime.
		try:
			if content_provider.widevine_wanted():
				self.req_session.headers.update(content_provider.api.solocoo.stream_headers())
			else:
				self.req_session.headers.update(content_provider.stream_headers())
		except Exception:
			content_provider.log_exception()

	# #################################################################################################

	def get_drm_license(self, drm_info, lic_request):
		"""Canal+ license via GetLicence. For other license types behaves like the parent."""
		ctx = drm_info.get('canalplus')
		if not ctx:
			return super(CanalplusHTTPRequestHandler, self).get_drm_license(drm_info, lic_request)

		try:
			return self.cp.api.get_license(ctx, lic_request)
		except Exception:
			self.cp.log_exception()
			return None

	# #################################################################################################

	def get_stream_info_by_channel_key(self, channel_key):
		try:
			stream = self.cp.get_stream_info(channel_key)
		except Exception:
			self.cp.log_exception()
			return None

		if not stream.get('url'):
			return None

		bandwidth = 1000000000
		try:
			if stream.get('license_url'):
				streams = self.cp.limit_streams(self.cp.get_dash_streams(stream['url'],
				                                headers=self.cp.api.solocoo.stream_headers(),
				                                max_bitrate=self.cp.get_setting('max_bitrate')))
			else:
				streams = self.cp.resolve_streams_for_channel(stream['url'])
			if streams:
				bandwidth = int(streams[0]['bandwidth'])
		except Exception:
			self.cp.log_exception()

		info = {
			'url': stream['url'],
			'bandwidth': bandwidth,
			'license': stream.get('license') or {},
		}
		if stream.get('license_url'):
			# Widevine path (Solocoo)
			info['wv'] = stream['license_url']
		return info

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

		if not stream_info:
			stream_info = self.get_stream_info_by_channel_key(channel_key)
			if not stream_info:
				return self.reply_error404(request)
			self.live_cache_put(channel_key, stream_info)

		# redirect to /dash/<key>.mpd - the player refreshes the manifest from this URL from now on
		return self.reply_redirect(request, stream_key_to_dash_url(self.cp.http_endpoint, stream_info))

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		"""Common processing plus Canal+ specific manifest cleanup.

		1. When segments are decrypted by the framework (internal decrypt, e.g. gstplayer),
		   subtitle AdaptationSets are removed first: their init segment is not a CENC
		   protected mp4 and the decrypt step fails on it (HTTP 501), which makes the
		   player give up. With exteplayer3 the player decrypts itself, so they are kept.
		2. Canal+ (like Skylink, same CDN) splits video into several AdaptationSets
		   (e.g. up to 720p and a separate 1080p). The common processing keeps one
		   representation per set, so several would remain and the player could pick
		   a lower one than selected - only one video set is kept.
		3. Archive (static manifest with begin/end, segments served through the proxy):
		   the segment timeline and the fragments' decode times are wall-clock based, which
		   gstplayer shows as a position of many hours into the recording and seeking fails.
		   The timeline is rebased to zero, see fix_static_timeline_offset.
		"""
		internal_decrypt = dash_info.get('dash_internal_decrypt', self.dash_internal_decrypt)
		if internal_decrypt:
			try:
				self.remove_subtitle_sets(root)
			except Exception:
				self.cp.log_exception()

		super(CanalplusHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
		                                                             dash_info, cache_key)
		try:
			self.keep_single_video_set(root, bandwidth)
			if internal_decrypt:
				self.fix_static_timeline_offset(root)
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	@classmethod
	def fix_static_timeline_offset(cls, root):
		"""For a static (archive) manifest moves the segment timeline of every track to zero.

		Broadpeak DVR manifests have segment times based on wall-clock time (a huge value)
		with a matching presentationTimeOffset, but gstplayer ignores the offset and takes
		the decode time from the fragments, so it reports a position of many hours and
		seeking fails. The timeline is rebased so that the first segment starts at (nearly)
		zero and presentationTimeOffset is removed. The media URL uses $Time$, so the original
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

			offset = int(e_template.get('presentationTimeOffset') or segments[0].get('t'))
			if offset == 0:
				continue

			t = 0
			for e_s in segments:
				t = int(e_s.get('t', t))
				e_s.set('t', str(t - offset))
				t += int(e_s.get('d')) * (int(e_s.get('r') or 0) + 1)

			e_template.attrib.pop('presentationTimeOffset', None)
			e_template.set('media', media.replace('$Time$', 'T%ds%so$Time$' % (offset, e_template.get('timescale') or '1')))

	# #################################################################################################

	def P_dsp(self, request, path):
		"""Segments of a rebased archive timeline (see fix_static_timeline_offset): restores the
		original segment time in the URL and shifts the decode time inside the fragment."""
		m = self.TIME_OFFSET_RE.search(path)
		if not m:
			return super(CanalplusHTTPRequestHandler, self).P_dsp(request, path)

		offset, timescale, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
		path = path[:m.start()] + str(offset + t) + path[m.end():]
		data = super(CanalplusHTTPRequestHandler, self).P_dsp(request, path)

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

	@staticmethod
	def _ns(root):
		ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
		return '{%s}' % ns if ns else ''

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

			allowed = [v for v in video_sets if v[0] <= bandwidth]
			if allowed:
				chosen = max(allowed, key=lambda v: v[0])[1]
			else:
				chosen = min(video_sets, key=lambda v: v[0])[1]

			for _best, e_set in video_sets:
				if e_set is not chosen:
					e_period.remove(e_set)

	# #################################################################################################

	def default_handler(self, request, path_full):
		data = 'Default Canal+ handler for path: %s' % path_full
		return self.reply_ok(request, data.encode('utf-8'), 'text/plain; charset=UTF-8')
