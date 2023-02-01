# -*- coding: utf-8 -*-

import base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from time import time

# #################################################################################################

class OrangeTVHTTPRequestHandler(AddonHttpRequestHandler):

	def __init__(self, content_provider, addon):
		AddonHttpRequestHandler.__init__(self, addon.id)
		self.live_cache = {}
		self.cp = content_provider

	def P_playlive(self, request, path):
		try:
			channel_key = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			
			if channel_key in self.live_cache and self.live_cache[channel_key]['life'] > int(time()):
				self.cp.log_debug("Returning result from cache")
				result = self.live_cache[channel_key]['result']
			else:
				result = self.cp.orangetv.get_live_link(channel_key)
				self.live_cache[channel_key] = { 'life': int(time()) + 900, 'result': result }

			location = result[0]['url']
#			self.log_debug("Resolved stream address: %s" % location )
		except:
			self.cp.log_exception()
			return self.reply_error500( request )

		return self.reply_redirect(request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre orange pre path: %s" % path_full
		return self.reply_ok(request, data, "text/plain; charset=UTF-8")

