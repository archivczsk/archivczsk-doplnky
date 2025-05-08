# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler, HlsMasterProcessor
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

# #################################################################################################

class VoyoHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(VoyoHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True

	# #################################################################################################
