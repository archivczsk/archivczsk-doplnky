# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler, HlsMasterProcessor
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

# #################################################################################################

class iVysilaniHlsMasterProcessor(HlsMasterProcessor):
	def cleanup_master_playlist(self):
		super(iVysilaniHlsMasterProcessor, self).cleanup_master_playlist()

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

class iVysilaniHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(iVysilaniHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.dash_proxy_segments = True
		self.dash_internal_decrypt = True
		self.hls_master_processor = iVysilaniHlsMasterProcessor

	# #################################################################################################
