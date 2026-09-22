# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

# #################################################################################################

class JojPlayHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(JojPlayHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = False
		self.enable_hls_multiaudio = property(lambda self: self.cp.get_setting('hls_multiaudio') == True)
