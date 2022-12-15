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
from sweettv import SweetTvCache
from time import time

# #################################################################################################

__scriptid__ = 'plugin.video.sweettv'
addon = ArchivCZSK.get_addon(__scriptid__)


class SweetTvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		
	def P_playlive(self, request, path):
		try:
			username=addon.get_setting('username')
			password=addon.get_setting('password')
			device_id = addon.get_setting( 'device_id' )
			data_dir=addon.get_info('profile')
			
			sweettv = SweetTvCache.get(username, password, device_id, data_dir, log.info )
			path = base64.b64decode(path).decode("utf-8")
			
			if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
				log.debug("Returning result from cache" )
				result = self.live_cache[path]['result']
			else:
				result = sweettv.get_live_link(path)
				self.live_cache[path] = { 'life': int(time())+60, 'result': result }

			location = result[0]['url']
#			log.debug("Resolved stream address: %s" % location )
		except:
			log.error(traceback.format_exc())
			return self.reply_error500( request )

		return self.reply_redirect( request, location.encode('utf-8'))
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre SweetTV pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

		
#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')

request_handler = SweetTvHTTPRequestHandler()

archivCZSKHttpServer.registerRequestHandler( request_handler )
log.info( "SweetTV http endpoint: %s" % archivCZSKHttpServer.getAddonEndpoint( request_handler ) )

def setting_changed_notification(name, value):
	if name and value:
		if name == 'password':
			# do write sensitive data to log file
			value = '***'
		log.debug('SweetTV setting "%s" changed to "%s"' % (name, value) )
		
	# check if we need service to be enabled
	if addon.get_setting('username') and addon.get_setting('password') and addon.get_setting('enable_userbouquet'):
		addon.set_service_enabled(True)
	else:
		addon.set_service_enabled(False)
	
addon.add_setting_change_notifier('username', setting_changed_notification )
addon.add_setting_change_notifier('password', setting_changed_notification )
addon.add_setting_change_notifier('enable_userbouquet', setting_changed_notification )
setting_changed_notification(None, None)
