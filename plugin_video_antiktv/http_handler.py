# -*- coding: utf-8 -*-

import base64
import binascii
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

# #################################################################################################

class AntikTVHTTPRequestHandler( AddonHttpRequestHandler ):
	getkey_uri = "/getkey/"
	getsegment_live_uri = "/getslive/"
	getsegment_archive_uri = "/getsarchive/"

	def __init__(self, content_provider, addon ):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider

	# #################################################################################################

	def P_playlive(self, request, path):
		try:
			channel_type, channel_id = self.cp.decode_playlive_url(path)
			url = self.cp.atk.get_direct_stream_url(channel_type, channel_id)
			if url != None:
				return self.reply_redirect(request, url)

			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri, self.get_endpoint(request, True) + self.getsegment_live_uri)
		except:
			self.cp.log_error("Failed for path: %s" % path)
			self.cp.log_exception()
			return self.reply_error500( request )

		return self.reply_ok(request, data, "application/x-mpegURL; charset=UTF-8")

	# #################################################################################################

	def P_playarchive(self, request, path):
		try:
			channel_type, channel_id, epg_start, epg_stop = self.cp.decode_playarchive_url(path)
			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri, self.get_endpoint(request, True) + self.getsegment_archive_uri, epg_start, epg_stop)
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

	def P_getslive(self, request, path, live=True):
		try:
			if path.endswith('.ts'):
				path = path[:-3]

			segment_url = base64.b64decode(path.encode('utf-8')).decode("utf-8")

			def http_data_write( code, header, data ):
				if code != None:
					request.setResponseCode(code)

				if header != None:
					request.setHeader(header[0], header[1])

				if data != None:
					request.write(data)

				if code == None and header == None and data == None:
					request.finish()

			self.cp.atk.get_segment_data_async(segment_url, http_data_write, live, request.getHeader(b'Range'))
			return self.NOT_DONE_YET

		except:
			self.cp.log_exception()
			return self.reply_error500(request)

	# #################################################################################################

	def P_getsarchive(self, request, path):
		return self.P_getslive(request, path, False)

# #################################################################################################
