# -*- coding: utf-8 -*-

import base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

# #################################################################################################

class SweetTvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self, content_provider, addon):
		AddonHttpRequestHandler.__init__(self, addon.id)
		self.cp = content_provider
		self.last_stream_id = None
		
	def P_playlive(self, request, path):
		try:
			sweettv = self.cp.sweettv

			if sweettv:
				path = base64.b64decode(path.encode('utf-8')).decode("utf-8")

				if self.last_stream_id:
					sweettv.close_stream(self.last_stream_id)

				result = sweettv.get_live_link(path)

				location = result[0]['url']
				self.last_stream_id = result[0].get('stream_id')
#				self.cp.log_debug("Resolved stream address: %s" % location )
			else:
				return self.reply_error404(request)
		except:
			self.cp.log_exception()
			return self.reply_error500( request )

		return self.reply_redirect(request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre SweetTV pre path: %s" % path_full
		return self.reply_ok(request, data, "text/plain; charset=UTF-8")
