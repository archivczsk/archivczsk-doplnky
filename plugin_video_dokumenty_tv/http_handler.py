# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler

# #################################################################################################

class DokumentyTVHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(DokumentyTVHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False

	# #################################################################################################

	def P_img(self, request, path):
		img_path = None
		resolver = self.cp.img_cache.get(path)

		if resolver:
			img_path = resolver.get_video_img()

		self.cp.log_debug("IMG path: %s" % img_path)

		if not img_path:
			return self.reply_error500(request)

		response = self.req_session.get(img_path)
		response.raise_for_status()

		request.send_response(200)
		request.send_header(response.headers.get('Content-Type'))
		return response.content

	# #################################################################################################
