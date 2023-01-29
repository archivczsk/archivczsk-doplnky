# -*- coding: utf-8 -*-

import traceback
import base64
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from .sweettv import SweetTvCache
from time import time

# #################################################################################################

__scriptid__ = 'plugin.video.sweettv'
addon = ArchivCZSK.get_addon(__scriptid__)


class SweetTvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		self.last_stream_id = None
		
	def P_playlive(self, request, path):
		try:
			username=addon.get_setting('username')
			password=addon.get_setting('password')
			device_id = addon.get_setting( 'device_id' )
			data_dir=addon.get_info('profile')
			
			sweettv = SweetTvCache.get(username, password, device_id, data_dir, log.info )
			path = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			
#			if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
#				log.debug("Returning result from cache" )
#				result = self.live_cache[path]['result']
#			else:

			if self.last_stream_id:
				sweettv.close_stream( self.last_stream_id )
				
			result = sweettv.get_live_link(path)
#			self.live_cache[path] = { 'life': int(time())+60, 'result': result }

			location = result[0]['url']
			self.last_stream_id = result[0].get('stream_id')
#			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect(request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre SweetTV pre path: %s" % path_full
		return self.reply_ok(request, data, "text/plain; charset=UTF-8")
