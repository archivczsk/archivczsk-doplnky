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

		def reply_img_data(response):
			if response['status_code'] != 200:
				request.setResponseCode(401)
				request.finish()
				return

			request.setResponseCode(200)
			if 'content-type' in response['headers']:
				request.setHeader('content-type', response['headers']['content-type'])

			request.write(response['content'])
			request.finish()
			return

		self.request_http_data_async_simple(img_path, cbk=reply_img_data)
		return self.NOT_DONE_YET

	# #################################################################################################
