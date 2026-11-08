# -*- coding: utf-8 -*-
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler, stream_key_to_dash_url
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler


# #################################################################################################
# HTTP handler for Canal+.
#
# P_dash serves playback started from the addon menu, P_playlive serves channels from the userbouquet.
# The Canal+ license is not a plain POST to one URL but a GetLicence call with an envelope
# (LiveToken, EpgId, challenge) - that's why get_drm_license is overridden.
# #################################################################################################


class CanalplusHTTPRequestHandler(DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
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

		1. STPP (TTML in mp4) subtitles are removed - they are not supported in Enigma2 and cause
		   problems by playback (same as in Oneplay).
		2. Canal+ (like Skylink, same CDN) splits video into several AdaptationSets
		   (e.g. up to 720p and a separate 1080p). The common processing keeps one
		   representation per set, so several would remain and the player could pick
		   a lower one than selected - only one video set is kept.
		"""
		self.remove_stpp_subtitles(root)

		super(CanalplusHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth,
		                                                             dash_info, cache_key)
		try:
			self.keep_single_video_set(root, bandwidth)
		except Exception:
			self.cp.log_exception()

	# #################################################################################################

	@staticmethod
	def _ns(root):
		ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
		return '{%s}' % ns if ns else ''

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
