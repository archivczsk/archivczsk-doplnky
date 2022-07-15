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
from telly import TellyCache

# #################################################################################################

__scriptid__ = 'plugin.video.telly'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


class TellyHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)

	def P_playlive(self, request, path):
		try:
			data_dir = __addon__.getAddonInfo('profile')
			enable_h265 = __addon__.getSetting('enable_h265')=='true'

			telly = TellyCache.get(data_dir, log.info)
			path = base64.b64decode(path).decode("utf-8")
			result = telly.get_video_link_by_id(path, enable_h265)
			
			max_bitrate = __addon__.getSetting('max_bitrate')
			if ' Mbit' in max_bitrate:
				max_bitrate = int(max_bitrate.split(' ')[0]) * 1000
			else:
				max_bitrate = 100000
		
			location = None
			for one in result:
				if one['bitrate'] <= max_bitrate:
					location = one['url']
					break
				
			if not location:
				location = result[-1]['url']

#			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect( request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default Telly handler pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

		
request_handler = TellyHTTPRequestHandler()

archivCZSKHttpServer.registerRequestHandler( request_handler )
log.info( "Telly http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint( request_handler ) )
