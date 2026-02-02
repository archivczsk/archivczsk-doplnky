# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from base64 import b64decode
import os

# #################################################################################################

class DupeHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(DupeHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False

	# #################################################################################################

	def P_img(self, request, path):
		file_out = '/tmp/dupe_img.jpg'
		url = b64decode(path.encode('ascii')).decode('utf-8')
		os.system('ffmpeg -i "{}" -frames:v 1 {}'.format(url, file_out))

		if os.path.isfile(file_out):
			with open(file_out, 'rb') as f:
				img_data = f.read()

			os.remove(file_out)
		else:
			img_data = None

		if not img_data:
			return self.reply_error500(request)

		request.send_response(200)
		request.send_header('Content-Type', 'image/jpeg')
		return img_data

	# #################################################################################################

