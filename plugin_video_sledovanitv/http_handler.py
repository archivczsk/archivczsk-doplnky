# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################

class SledovaniTVHTTPRequestHandler(PlayliveTVHTTPRequestHandler, HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(SledovaniTVHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = True
		self.hls_internal_decrypt = True
		self.enable_hls_multiaudio = property(lambda self: self.cp.get_setting('hls_multiaudio') == True)

# #################################################################################################
