# -*- coding: utf-8 -*-

import re

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


class SkylinkHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
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
		url = stream['url']
		bandwidth = max_bitrate
		try:
			streams = self.cp.resolve_streams_for_channel(stream['url'])
			if streams:
				bandwidth = int(streams[0]['bandwidth'])
				# the URL from the server carries a token valid only for a few minutes and the
				# player refreshes the manifest during the whole playback - use the URL after
				# the redirect, the same as playback started from the addon menu does
				url = streams[0].get('playlist_url') or url
		except Exception:
			self.cp.log_exception()

		return {
			'url': url,
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

		1. STPP (TTML in mp4) subtitles are removed - they are not supported in Enigma2 and cause
		   problems by playback (same as in Oneplay).
		2. Skylink splits video into two AdaptationSets - one with resolutions up to 720p
		   and one with 1080p only. The common processing keeps one representation per
		   set, so two would remain and the player could pick a higher one than
		   configured - only one video set is kept.
		3. Live: all tracks get the same segment time span (align_live_timelines).
		"""
		self.ensure_stream_headers()
		self.remove_stpp_subtitles(root)

		had_video = self.has_video(root)

		super(SkylinkHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
		                                                           dash_info, cache_key)

		# no key came for PlayReady - Widevine is used from now on
		if had_video and not self.has_video(root) and 'pr' in (dash_info.get('drm') or {}):
			self.cp.drm_failed = True

		try:
			self.keep_single_video_set(root, bandwidth)
			self.align_live_timelines(root)
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
	def remove_stpp_subtitles(cls, root):
		"""Removes STPP TTML subtitles (text AdaptationSets packed in mp4)."""
		ns = cls._ns(root)

		for e_period in root.findall('%sPeriod' % ns):
			for e_set in e_period.findall('%sAdaptationSet' % ns):
				if e_set.get('contentType', '') == 'text' and e_set.get('mimeType', '') == 'application/mp4':
					e_period.remove(e_set)

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

	def default_handler(self, request, path_full):
		data = 'Default Skylink handler for path: %s' % path_full
		return self.reply_ok(request, data.encode('utf-8'), 'text/plain; charset=UTF-8')
