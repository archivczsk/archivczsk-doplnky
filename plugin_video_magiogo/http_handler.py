# -*- coding: utf-8 -*-

import traceback
import base64
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

from time import time
import json

# #################################################################################################

class MagioGOHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(MagioGOHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = True
		self.hls_proxy_segments = True
		self.dash_proxy_segments = True
		self.live_cache = {}

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
				cookies = self.live_cache[key]['cookies']
				self.live_cache[key]['life'] = int(time())+20
			else:
				self.cp.log_debug("Getting stream URL for channel ID: %s" % channel_id)
				index_url = self.cp.magiogo.get_stream_link(channel_id)
				if index_url:
					while True:
						# follow redirects to get last URL and cache it
						response = self.cp.magiogo.req_session.get(index_url, allow_redirects=False)
						if response.status_code > 300 and response.status_code < 310:
							index_url = response.headers['Location']
						else:
							break

					cookies = ','.join('%s=%s' % x for x in response.cookies.items())
				else:
					cookies = None

				self.live_cache_cleanup()
				self.live_cache[key] = {
					'life': int(time())+20,
					'index_url': index_url,
					'cookies': cookies
				}
		except:
			self.cp.log_error(traceback.format_exc())
			index_url = None
			cookies = None

		return index_url, cookies

	# #################################################################################################

	def encode_p_dash_hls_key(self, stream_key):
		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		return base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def decode_channel_id(self, path):
		return base64.b64decode(path.encode('utf-8')).decode("utf-8")

	# #################################################################################################

	def P_playlive(self, request, path):
		if path.endswith('/index'):
			path = path[:-6]

		channel_id = self.decode_channel_id(path)

		max_bitrate = int(self.cp.get_setting('max_bitrate'))
		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 1000000000

		# get real mainfest url and forwad it to dash handler ...
		index_url, cookies = self.get_stream_index_url(channel_id)
		stream_info = {
			'url': index_url,
			'bandwidth': max_bitrate,
			'cookies': cookies
		}

		if self.cp.magiogo.stream_type_by_device() == 'm3u8':
			return self.P_hls(request, self.encode_p_dash_hls_key(stream_info))
		else:
			return self.P_dash(request, self.encode_p_dash_hls_key(stream_info))

	# #################################################################################################

	def default_handler(self, request, path_full ):
		data = "Default handler pre Magio GO pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

	# #################################################################################################

	def fix_startover(self, root):
		root.set('startover', '1')

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		super(MagioGOHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		fix = dash_info.get('fix')

		if fix == 'startover':
			self.fix_startover(root)

	# #################################################################################################
