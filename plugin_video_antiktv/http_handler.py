# -*- coding: utf-8 -*-

import base64
import requests
import binascii
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

# #################################################################################################

class AntikTVHTTPRequestHandler( AddonHttpRequestHandler ):
	getkey_uri = "/getkey/"

	def __init__(self, content_provider, addon ):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider
		
	# #################################################################################################
	
	def P_playlive(self, request, path):
		try:
			channel_type, channel_id = self.cp.decode_playlive_url(path)
			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri)
		except:
			self.cp.log_error("Failed for path: %s" % path)
			self.cp.log_exception()
			return self.reply_error500( request )

		return self.reply_ok(request, data, "application/x-mpegURL; charset=UTF-8")

	# #################################################################################################

	def P_playarchive(self, request, path):
		try:
			channel_type, channel_id, epg_start, epg_stop = self.cp.decode_playarchive_url(path)
			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri, epg_start, epg_stop)
		except:
			self.cp.log_error("Failed for path: %s" % path)
			self.cp.log_exception()
			return self.reply_error500(request)

		return self.reply_ok(request, data, "application/x-mpegURL; charset=UTF-8")

	# #################################################################################################
	
	def P_getkey(self, request, path):
		try:
			key = self.cp.atk.get_content_key(path)
			key = binascii.a2b_hex(key)
		except:
			self.cp.log_exception()
			return self.reply_error500(request)
		
		return self.reply_ok( request, key, "application/octet-stream", raw=True)
	
# #################################################################################################
