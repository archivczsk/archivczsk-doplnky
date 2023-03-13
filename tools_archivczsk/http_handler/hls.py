# -*- coding: utf-8 -*-

import base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler
from time import time
import requests
import re
import json

# #################################################################################################

def stream_key_to_hls_url(endpoint, stream_key):
	'''
	Converts stream key (string or dictionary) to url, that can be played by player. It is then handled by HlsHTTPRequestHandler that will respond with processed hls master playlist
	'''

	if stream_key == None:
		stream_key = ""
	
	if isinstance( stream_key, (type({}), type([]), type(()),) ):
		stream_key = '{' + json.dumps(stream_key) + '}'

	stream_key = base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')
	return "%s/hls/%s.m3u8" % (endpoint, stream_key)

# #################################################################################################


class HlsHTTPRequestHandler(AddonHttpRequestHandler):
	'''
	Http request handler that implements processing of HLS master playlist and exports new one with only selected one video stream.
	Other streams (audio, subtitles, ...) are preserved.
	'''
	def __init__(self, content_provider, addon):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider
		self.hls_session = requests.Session()

	# #################################################################################################
	def decode_stream_key(self, path):
		'''
		Decodes stream key encoded using stream_key_to_hls_url
		'''
		if path.endswith('.m3u8'):
			path = path[:-5]

		if len(path) > 0:
			stream_key = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			if stream_key[0] == '{' and stream_key[-1] == '}':
				stream_key = json.loads(stream_key[1:-1])

			return stream_key

		else:
			return None

	# #################################################################################################

	def get_hls_info(self, stream_key):
		'''
		This is default implementation, that just forwards this call to content provider.
		Replace it with your own implementation if you need something different.
		'''
		return self.cp.get_hls_info(stream_key)

	# #################################################################################################

	def P_hls(self, request, path):
		'''
		Handles request to hls master playlist. Address is created using stream_key_to_hls_url()
		'''
		try:
			stream_key = self.decode_stream_key(path)

			hls_info = self.get_hls_info(stream_key)

			if not hls_info:
				self.reply_error404(request)

			if not isinstance(hls_info, type({})):
				hls_info = { 'url': hls_info }

			# resolve HLS playlist and get only best stream
			data = self.get_hls_playlist_data(hls_info['url'], hls_info.get('bandwidth'), hls_info.get('headers'))

			if not data:
				self.reply_error404(request)

		except:
			self.cp.log_exception()
			return self.reply_error500(request)

		return self.reply_ok(request, data, "application/vnd.apple.mpegurl")

	# #################################################################################################

	def get_hls_playlist_data(self, url, bandwidth=None, headers=None):
		'''
		Processes HLS master playlist from given url and returns new one with only one variant playlist specified by bandwidth (or with best bandwidth if no bandwidth is given)
		'''

		def process_url(surl):
			if not surl.startswith('http'):
				if surl.startswith('/'):
					surl = url[:url[9:].find('/') + 9] + surl
				else:
					surl = url[:url.rfind('/') + 1] + surl

			return surl

		try:
			response = self.hls_session.get(url, headers=headers)
		except:
			self.cp.log_exception()
			return None

		if response.status_code != 200:
			self.cp.log_error("Status code response for HLS master playlist: %d" % response.status_code)
			return None

		if bandwidth == None:
			bandwidth = 1000000000
		else:
			bandwidth = int(bandwidth)

		streams = []

		for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', response.text, re.MULTILINE):
			stream_info = {}
			for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
				key, val = info.split('=', 1)
				stream_info[key.strip().lower()] = val.strip()

			stream_info['url'] = process_url(m.group('chunk'))

			if int(stream_info.get('bandwidth', 0)) <= bandwidth:
				streams.append(stream_info)

		streams = sorted(streams, key=lambda i: int(i['bandwidth']), reverse=True)
		
		if len(streams) == 0:
			self.log_error("No streams found for bandwidth %d" % bandwidth)
			return None

		resp_data = []
		ignore_next = False
		stream_to_keep = 'BANDWIDTH=%s' % streams[0].get('bandwidth', 0)

		for line in iter(response.text.splitlines()):
			if ignore_next:
				ignore_next = False
				continue

			if 'URI=' in line:
				# fix uri to full url
				uri = line[line.find('URI=') + 4:]

				if uri[0] in ('"', "'"):
					uri = uri[1:uri[1:].find(uri[0]) + 1]

				line = line.replace(uri, process_url(uri))

			if line.startswith("#EXT-X-STREAM-INF:"):
				if stream_to_keep in line:
					resp_data.append(line)
					resp_data.append(streams[0]['url'])

				ignore_next = True
			else:
				resp_data.append(line)

		return '\n'.join(resp_data) + '\n'

	# #################################################################################################
