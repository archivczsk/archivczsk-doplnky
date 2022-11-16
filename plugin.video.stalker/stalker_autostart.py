try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import traceback
import base64
from Plugins.Extensions.archivCZSK.version import version
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer, AddonHttpRequestHandler

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from stalker import StalkerCache
from time import time
import json

# #################################################################################################

__scriptid__ = 'plugin.video.stalker'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)


class StalkerHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		
	def P_playlive(self, request, path):
		try:
			path = base64.b64decode(path).decode("utf-8")
			ck, cmd, use_tmp_link = json.loads(path)
			
			if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
				log.debug("Returning result from cache" )
				url = self.live_cache[path]['result']
			else:
				s = StalkerCache.get_by_key( ck )
			
				if use_tmp_link:
					url = s.create_video_link( cmd )
				else:
					url = s.cmd_to_url( cmd )
					
				if url:
					self.live_cache[path] = { 'life': int(time())+300, 'result': url }
			
			location = url
			log.debug("Resolved stream address: %s" % location )
				
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		if location:
			return self.reply_redirect( request, location.encode('utf-8'))
		else:
			return self.reply_error404( request )
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre Stalker pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

		
#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')

# #################################################################################################

def init_all_portals():
	portals = StalkerCache.load_portals_cfg()
	data_dir=__addon__.getAddonInfo('profile')
	
	for portal in portals:
		StalkerCache.get( portal[1], data_dir, log.info )

# #################################################################################################	
	
request_handler = StalkerHTTPRequestHandler()

archivCZSKHttpServer.registerRequestHandler( request_handler )
log.info( "Stalker http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint( request_handler ) )
init_all_portals()

