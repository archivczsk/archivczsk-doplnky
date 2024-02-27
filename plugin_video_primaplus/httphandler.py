# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler

# #################################################################################################

class PrimaPlusHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(PrimaPlusHTTPRequestHandler, self).__init__(content_provider, addon)
