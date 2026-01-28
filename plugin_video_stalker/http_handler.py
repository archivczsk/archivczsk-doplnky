# -*- coding: utf-8 -*-

import traceback
import base64
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from .stalker import StalkerCache
from .http_provider import stalkerHttpProvider
from time import time
import json

# #################################################################################################

class StalkerHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self, addon):
		AddonHttpRequestHandler.__init__(self, addon)
		self.live_cache = {}
#		self.user_agent = 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3'
		self.user_agent = 'Mozilla/5.0'

	# #################################################################################################

	def file_name_sanitize(self, name ):
		return name.replace('/', '').replace('\\', '').replace('#', '').replace(':', '').replace(' ', '_')

	# #################################################################################################

	def P_playlive(self, request, path):
		path_orig = path

		if path.endswith('.m3u8'):
			is_m3u8 = True
			path = path[:-5]
		else:
			is_m3u8 = False

		path = base64.b64decode(path.encode('utf-8')).decode("utf-8")
		link_info = json.loads(path)

		if len( link_info ) == 3:
			ck, cmd, use_tmp_link = link_info
			name = 'Unknown'
			link_type = 'itv'
			series = None
		else:
			ck, cmd, use_tmp_link, link_type, name, series = link_info

		if is_m3u8:
			ret = '#EXTM3U\n#EXTVLCOPT:http-user-agent=%s\n%s/playlive/%s\n' % (self.user_agent, self.get_endpoint(request), path_orig[:-5])
			request.send_header('Content-Disposition', 'attachment; filename="%s.m3u8"' % self.file_name_sanitize(name))

			return self.reply_ok(request, ret, "application/x-mpegURL; charset=UTF-8")

		if path in self.live_cache and self.live_cache[path]['life'] > int(time()):
			log.debug("Returning result from cache" )
			url = self.live_cache[path]['result']
		else:
			s = StalkerCache.get_by_key( ck )

			if use_tmp_link:
				if series == -1:
					series = None
				url = s.create_video_link( cmd, link_type, series=series )
			else:
				url = s.cmd_to_url( cmd )

#				if url:
#					self.live_cache[path] = { 'life': int(time())+300, 'result': url }

		location = url
		log.debug("Resolved stream address: %s" % location )


		if location:
			return self.reply_redirect(request, location)
		else:
			return self.reply_error404( request )

	# #################################################################################################

	def default_handler(self, request, path_full ):
		if path_full == '' or path_full.startswith('list/'):
			endpoint = self.get_endpoint(request)

			data_dir=self.addon.get_info('data_path')

			try:
				if path_full.endswith('.m3u8'):
					content_encoding = "application/x-mpegURL; charset=UTF-8"
					ret, file_name = stalkerHttpProvider(endpoint, data_dir).handle_m3u8(path_full[:-5])

					data = ('#EXTM3U\n#EXTVLCOPT:http-user-agent=%s\n' % self.user_agent)

					if isinstance(ret,type([])):
						data += ('\n#EXTVLCOPT:http-user-agent=%s\n' % self.user_agent).join(ret)
					else:
						data += ret

					request.send_header('Content-Disposition', 'attachment; filename="%s.m3u8"' % self.file_name_sanitize(file_name))
				else:
					content_encoding = "text/html; charset=UTF-8"
					ret = stalkerHttpProvider(endpoint, data_dir).handle_html(path_full)

					if isinstance(ret,type([])):
						data = '<html>' + ''.join(ret) + '</html>'
					else:
						data = ret

			except Exception as e:
				log.error("Stalker HTTP request processing ERROR:\n%s" % traceback.format_exc())
				data = '<html><h2>Error by processing request!</h2><p>%s</p></html>' % str(e)
				content_encoding = "text/html; charset=UTF-8"

		else:
			data = "Default handler pre Stalker pre path: %s" % path_full
			content_encoding = "text/plain; charset=UTF-8"

		if data:
			return self.reply_ok(request, data, content_encoding)
		else:
			return self.reply_error404( request )


#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')

# #################################################################################################
