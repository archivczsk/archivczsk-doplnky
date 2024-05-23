# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

# #################################################################################################

class iVysilaniHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(iVysilaniHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.dash_proxy_segments = True
		self.dash_internal_decrypt = True

	# #################################################################################################
