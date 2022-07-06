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
from orangetv import OrangeTVcache

# #################################################################################################

__scriptid__ = 'plugin.video.orangetv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


class OrangetvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)

	def P_playlive(self, request, path):
		try:
			username=__addon__.getSetting('orangetvuser')
			password=__addon__.getSetting('orangetvpwd')
			device_id=__addon__.getSetting( 'deviceid' )
			data_dir=__addon__.getAddonInfo('profile')

			orangetv = OrangeTVcache.get(username, password, device_id, data_dir, log.info )
			path = base64.b64decode(path).decode("utf-8")
			result = orangetv.getVideoLink(path + '|||')
			location = result[0]['url']
			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect( request, location)
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre orange pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

		
#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')

request_handler = OrangetvHTTPRequestHandler()

archivCZSKHttpServer.registerRequestHandler( request_handler )
log.info( "OrangeTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint( request_handler ) )
