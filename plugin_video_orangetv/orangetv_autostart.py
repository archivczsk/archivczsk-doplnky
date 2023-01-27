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
from time import time

# #################################################################################################

__scriptid__ = 'plugin.video.orangetv'
addon = ArchivCZSK.get_addon(__scriptid__)

class OrangetvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		
	def P_playlive(self, request, path):
		try:
			username=addon.get_setting('orangetvuser')
			password=addon.get_setting('orangetvpwd')
			device_id=addon.get_setting( 'deviceid' )
			data_dir=addon.get_info('profile')

			orangetv = OrangeTVcache.get(username, password, device_id, data_dir, log.info )
			path = base64.b64decode(path).decode("utf-8")
			
			if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
				log.debug("Returning result from cache" )
				result = self.live_cache[path]['result']
			else:
				result = orangetv.getVideoLink(path + '|||')
				self.live_cache[path] = { 'life': int(time())+900, 'result': result }

			location = result[0]['url']
#			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect( request, location.encode('utf-8'))
	
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

def setting_changed_notification(name, value):
	if name and value:
		if name == 'orangetvpwd':
			# do write sensitive data to log file
			value = '***'

		log.debug('OrangeTV setting "%s" changed to "%s"' % (name, value) )
		
	# check if we need service to be enabled
	if addon.get_setting('orangetvuser') and addon.get_setting('orangetvpwd') and addon.get_setting('enable_userbouquet'):
		addon.set_service_enabled(True)
	else:
		addon.set_service_enabled(False)
	
addon.add_setting_change_notifier('orangetvuser', setting_changed_notification )
addon.add_setting_change_notifier('orangetvpwd', setting_changed_notification )
addon.add_setting_change_notifier('enable_userbouquet', setting_changed_notification )
setting_changed_notification(None, None)
