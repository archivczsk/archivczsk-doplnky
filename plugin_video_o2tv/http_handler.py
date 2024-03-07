# -*- coding: utf-8 -*-

import traceback
import base64
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
import json

from time import time
import xml.etree.ElementTree as ET

# #################################################################################################

class O2HTTPRequestHandler(DashHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		DashHTTPRequestHandler.__init__(self, content_provider, addon, proxy_segments=False)
		self.live_cache = {}
		self.o2_session = self.cp.get_requests_session()

	# #################################################################################################

	def live_cache_cleanup(self):
		act_time = int(time())

		to_clean_list = []
		for k, v in self.live_cache.items():
			if v['life'] < act_time:
				to_clean_list.append(k)

		for k in to_clean_list:
			del self.live_cache[k]


	# #################################################################################################

	def get_stream_index_url(self, channel_id):
		try:
			key = channel_id

			if key in self.live_cache and self.live_cache[key]['life'] > int(time()):
#				self.cp.log_debug("Returning result from cache" )
				index_url = self.live_cache[key]['index_url']
				self.live_cache[key]['life'] = int(time())+20
			else:
				index_url = self.cp.o2tv.get_live_link(channel_id)
				if index_url:
					while True:
						# follow redirects to get last URL and cache it
						response = self.o2_session.get(index_url, allow_redirects=False)
						if response.status_code > 300 and response.status_code < 310:
							index_url = response.headers['Location']
						else:
							break

				self.live_cache_cleanup()
				self.live_cache[key] = { 'life': int(time())+20, 'index_url': index_url }
		except:
			self.cp.log_error(traceback.format_exc())
			index_url = None

		return index_url

	# #################################################################################################

	def decode_channel_id(self, path):
		return base64.b64decode(path.encode('utf-8')).decode("utf-8")

	# #################################################################################################

	def encode_p_dash_key(self, stream_key):
		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		return base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def P_playlive(self, request, path):
		if path.endswith('/index.mpd'):
			path = path[:-10]

		channel_id = self.decode_channel_id(path)

#		self.cp.log_debug("%s resource ID: %s, path: %s" % (service_type, channel_id, path))

		max_bitrate = int(self.cp.get_setting('max_bitrate'))
		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 1000000000

		# get real mainfest url and forwad it to dash handler ...
		stream_info = {
			'url': self.get_stream_index_url(channel_id),
			'bandwidth': max_bitrate
		}
		return self.P_dash(request, self.encode_p_dash_key(stream_info))

	# #################################################################################################

	def default_handler(self, request, path_full ):
		data = "Default handler O2TV for path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")
