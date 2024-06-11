# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################

class OrangeTVHTTPRequestHandler(PlayliveTVHTTPRequestHandler, HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(OrangeTVHTTPRequestHandler, self).__init__(content_provider, addon)
