# -*- coding: utf-8 -*-

import traceback
import base64
from Plugins.Extensions.archivCZSK.version import version
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from .rebittv import RebitTvCache
from time import time

# #################################################################################################

__scriptid__ = 'plugin.video.rebittv'
addon = ArchivCZSK.get_addon(__scriptid__)


class RebitTvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		
	def P_playlive(self, request, path):
		try:
			username=addon.get_setting('username')
			password=addon.get_setting('password')
			device_name=addon.get_setting( 'device_name' )
			data_dir=addon.get_info('profile')
			
			rebittv = RebitTvCache.get(username, password, device_name, data_dir, log.info )
			path = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			
			if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
				log.debug("Returning result from cache" )
				result = self.live_cache[path]['result']
			else:
				result = rebittv.get_live_link(path)
				self.live_cache[path] = { 'life': int(time())+900, 'result': result }

			location = result[0]['url']
#			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect(request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre RebitTV pre path: %s" % path_full
		return self.reply_ok(request, data, "text/plain; charset=UTF-8")