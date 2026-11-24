# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler

# #################################################################################################

class TellyHTTPRequestHandler(PlayliveTVHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(TellyHTTPRequestHandler, self).__init__(content_provider, addon)
		self.cache_life = 0
