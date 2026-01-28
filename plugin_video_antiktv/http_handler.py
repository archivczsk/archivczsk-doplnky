# -*- coding: utf-8 -*-

import base64
import binascii
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

# #################################################################################################

class AntikTVHTTPRequestHandler( AddonHttpRequestHandler ):
	getkey_uri = "/getkey/"
	getsegment_live_uri = "/getslive/"
	getsegment_archive_uri = "/getsarchive/"
	playlive_redirect_uri = "/playliver/"
	plaarchive_redirect_uri = "/playarchiver/"

	def __init__(self, content_provider, addon ):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider

	# #################################################################################################

	def P_playliver(self, request, path):
		path_parts = path.split('~')
		redirect_url = base64.b64decode(path_parts[0].encode('utf-8')).decode("utf-8")
		return self.P_playlive(request, path_parts[1], redirect_url)

	# #################################################################################################

	def P_playlive(self, request, path, redirect_url=None):
		try:
			channel_type, channel_id = self.cp.decode_playlive_url(path)
			if redirect_url:
				url = self.cp.atk.get_direct_stream_url(channel_type, channel_id)
				if url != None:
					return self.reply_redirect(request, url)

			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri, self.get_endpoint(request, True) + self.getsegment_live_uri, url=redirect_url)
		except self.cp.atk.AtkHlsRedirect as new_url:
			if redirect_url:
				# this should never happen
				self.cp.log_error("HLS recursion detected for path: %s" % path)
				return self.reply_error500( request )

			return self.reply_redirect(request, self.get_endpoint(request, True) + self.playlive_redirect_uri + base64.b64encode(str(new_url).encode('utf-8')).decode("utf-8") + '~' + path)

		return self.reply_ok(request, data, "application/x-mpegURL; charset=UTF-8")

	# #################################################################################################

	def P_playarchiver(self, request, path):
		path_parts = path.split('~')
		redirect_url = base64.b64decode(path_parts[0].encode('utf-8')).decode("utf-8")
		return self.P_playarchive(request, path_parts[1], redirect_url)

	# #################################################################################################

	def P_playarchive(self, request, path, redirect_url=None):
		try:
			channel_type, channel_id, epg_start, epg_stop = self.cp.decode_playarchive_url(path)
			data = self.cp.atk.get_hls_playlist(channel_type, channel_id, self.get_endpoint(request, True) + self.getkey_uri, self.get_endpoint(request, True) + self.getsegment_archive_uri, epg_start, epg_stop, url=redirect_url)
		except self.cp.atk.AtkHlsRedirect as new_url:
			if redirect_url:
				# this should never happen
				self.cp.log_error("HLS recursion detected for path: %s" % path)
				return self.reply_error500( request )

			return self.reply_redirect(request, self.get_endpoint(request, True) + self.playarchive_redirect_uri + base64.b64encode(str(new_url).encode('utf-8')).decode("utf-8") + '~' + path)

		return self.reply_ok(request, data, "application/x-mpegURL; charset=UTF-8")

	# #################################################################################################

	def P_getkey(self, request, path):
		key = self.cp.atk.get_content_key(path)
		key = binascii.a2b_hex(key)

		return self.reply_ok( request, key, "application/octet-stream", raw=True)

	# #################################################################################################

	def P_getslive(self, request, path, live=True):
		if path.endswith('.ts'):
			path = path[:-3]

		segment_url = base64.b64decode(path.encode('utf-8')).decode("utf-8")
		request.send_response(200)
		self.cp.atk.get_segment_data(segment_url, live, request.get_header('Range'), request.send_header, request.write)

	# #################################################################################################

	def P_getsarchive(self, request, path):
		return self.P_getslive(request, path, False)

# #################################################################################################
