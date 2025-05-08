# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.parser.hls import HlsPlaylist

# #################################################################################################

class DisneyHlsMaster(HlsPlaylist):
	def __init__(self, content_provider, url):
		super(DisneyHlsMaster, self).__init__(url)
		self.cp = content_provider

	# #################################################################################################

	def filter_master_playlist(self):
		codec = self.cp.get_setting('video_codec')
		playlists = self.video_playlists
		playlists = list(filter(lambda p: p.get('CODECS','').startswith(codec), playlists))

		if len(playlists) == 0:
			playlists = self.video_playlists

		if self.cp.get_setting('enable_ac3'):
			playlists = sorted(playlists, key=lambda p: ('ec-3' in p.get('CODECS',''), p.get('CODECS','').startswith(codec), int(p.get('BANDWIDTH',0)) ), reverse=True)
		else:
			playlists = sorted(playlists, key=lambda p: ('ec-3' not in p.get('CODECS',''), p.get('CODECS','').startswith(codec), int(p.get('BANDWIDTH',0)) ), reverse=True)

		self.video_playlists = [playlists[0]]

		super(DisneyHlsMaster, self).filter_master_playlist()

	# #################################################################################################

	def cleanup_master_playlist(self):
		super(DisneyHlsMaster, self).cleanup_master_playlist()

		# sort audio streams and select the best (or let the user decide)
		def audio_cmp_key(p):
			key = []
			for l in self.cp.dubbed_lang_list + ['en']:
				key.append(p.get('LANGUAGE') == l)

			return key

		self.audio_playlists = sorted(self.audio_playlists, key=audio_cmp_key, reverse=True)

		# filter and sort subtitles - prefer lang choosed by user and also prefer forced subtitles
		def subtitles_cmp_key(p):
			key = []
			for l in self.cp.dubbed_lang_list:
				key.append(int(p.get('LANGUAGE') == l)*2 + int(p.get('FORCED') == 'YES'))

			return key

		self.subtitles_playlists = list(filter(lambda p: p.get('LANGUAGE') in self.cp.dubbed_lang_list, self.subtitles_playlists))
		self.subtitles_playlists = sorted(self.subtitles_playlists, key=subtitles_cmp_key, reverse=True)

# #################################################################################################

class DisneyPlusHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(DisneyPlusHTTPRequestHandler, self).__init__(content_provider, addon, proxy_segments=False, proxy_variants=True, internal_decrypt=True)

	# #################################################################################################

	def P_hls(self, request, path):
		'''
		Handles request to hls master playlist. Address is created using stream_key_to_hls_url()
		'''
		try:
			stream_key = self.decode_stream_key(path)
			hls_info = self.get_hls_info(stream_key)

			if not hls_info:
				self.reply_error404(request)

			pls = hls_info['master_playlist']

			if int(request.getHeader('X-DRM-Api-Level') or '0') >= 1 and hls_info.get('ext_drm_decrypt', True):
				# player supports DRM, so don't do internal decryption and let player handle DRM
				hls_info['hls_internal_decrypt'] = False

			mp_data = self.process_master_playlist(pls.mp_url, pls.to_string(audio_idx=stream_key['aid']), hls_info)
			return self.reply_ok(request, mp_data, "application/vnd.apple.mpegurl")
		except:
			self.cp.log_exception()
			return self.reply_error500(request)

	# #################################################################################################
