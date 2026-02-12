# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from base64 import b64decode
import os

# #################################################################################################

class StremioHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(StremioHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False

	# #################################################################################################
