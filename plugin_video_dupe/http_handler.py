# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler

# #################################################################################################

class DupeHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(DupeHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False

	# #################################################################################################
