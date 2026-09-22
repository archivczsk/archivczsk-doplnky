# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################

class OrangeTVHTTPRequestHandler(PlayliveTVHTTPRequestHandler, HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(OrangeTVHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = True
		self.enable_hls_multiaudio = property(lambda self: self.cp.get_setting('hls_multiaudio') == True)

	def process_variant_playlist(self, playlist_url, playlist_data, hls_info={}):
		playlist_data = super(OrangeTVHTTPRequestHandler, self).process_variant_playlist(playlist_url, playlist_data, hls_info)

		if hls_info.get('startover') == True:
			self.cp.log_debug("Startover is set - setting playlist type to EVENT")
			playlist_data = playlist_data.replace('#EXTM3U\n', '#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n')
		else:
			self.cp.log_debug("Startover is not set")

		return playlist_data
