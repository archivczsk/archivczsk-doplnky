# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler, HlsMasterProcessor
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################

class OrangeTVHlsMasterProcessor(HlsMasterProcessor):
	def cleanup_master_playlist(self):
		super(OrangeTVHlsMasterProcessor, self).cleanup_master_playlist()

		if self.request_handler.cp.get_setting('hls_multiaudio') == False:
			external_audio_cnt = 0
			internal_audio_cnt = 0

			for p in self.audio_playlists:
				if p.playlist_url:
					external_audio_cnt += 1
				else:
					internal_audio_cnt += 1


			if external_audio_cnt > 0 and internal_audio_cnt > 0:
				# exteplayer3 has problems playing HLS when there is a mix of audio tracks with external URI and internal (embedded to video track - without URI in playlist)
				# only external audio is played and switching to internal one doesn't work
				# workaround to play embedded audio is to remove all external tracks

				playlists = []
				for p in self.audio_playlists:
					if not p.playlist_url:
						playlists.append(p)

				self.audio_playlists = playlists


# #################################################################################################

class OrangeTVHTTPRequestHandler(PlayliveTVHTTPRequestHandler, HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(OrangeTVHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = True
		self.hls_master_processor = OrangeTVHlsMasterProcessor

	def process_variant_playlist(self, playlist_url, playlist_data, hls_info={}):
		playlist_data = super(OrangeTVHTTPRequestHandler, self).process_variant_playlist(playlist_url, playlist_data, hls_info)

		if hls_info.get('startover') == True:
			self.cp.log_debug("Startover is set - setting playlist type to EVENT")
			playlist_data = playlist_data.replace('#EXTM3U\n', '#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n')
		else:
			self.cp.log_debug("Startover is not set")

		return playlist_data
