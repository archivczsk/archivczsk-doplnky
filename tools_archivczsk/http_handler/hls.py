# -*- coding: utf-8 -*-

import base64
from .template import HTTPRequestHandlerTemplate
import re

# #################################################################################################

def stream_key_to_hls_url(endpoint, stream_key):
	'''
	Converts stream key (string or dictionary) to url, that can be played by player. It is then handled by HlsHTTPRequestHandler that will respond with processed hls master playlist
	'''
	return HTTPRequestHandlerTemplate.encode_stream_key(endpoint, stream_key, 'hls', 'm3u8')

# #################################################################################################

class HlsHTTPRequestHandler(HTTPRequestHandlerTemplate):
	'''
	Http request handler that implements processing of HLS master playlist and exports new one with only selected one video stream.
	Other streams (audio, subtitles, ...) are preserved.
	'''
	def __init__(self, content_provider, addon, proxy_segments=False):
		super(HlsHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_segments = proxy_segments

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

		def hls_continue(data):
			if data:
				request.setResponseCode(200)
				request.setHeader('content-type', "application/vnd.apple.mpegurl")
				request.write(data.encode('utf-8'))
			else:
				request.setResponseCode(401)
			request.finish()


		try:
			stream_key = self.decode_stream_key(path)

			hls_info = self.get_hls_info(stream_key)

			if not hls_info:
				self.reply_error404(request)

			if not isinstance(hls_info, type({})):
				hls_info = { 'url': hls_info }

			# resolve HLS playlist and get only best stream
			self.get_hls_playlist_data_async(hls_info['url'], hls_info.get('bandwidth'), hls_info.get('headers'), cbk=hls_continue)
			return self.NOT_DONE_YET

		except:
			self.cp.log_exception()
			return self.reply_error500(request)


	# #################################################################################################

	def hls_proxify_segment_url(self, url):
		'''
		Redirects segment url to use proxy
		'''

		segment_key = base64.b64encode(url.encode('utf-8')).decode('utf-8')
		return "/%s/hs/%s" % (self.name, segment_key)

	# #################################################################################################

	def hls_proxify_playlist_url(self, url):
		'''
		Redirects segment url to use proxy
		'''

		segment_key = base64.b64encode(url.encode('utf-8')).decode('utf-8')
		return "/%s/hp/%s" % (self.name, segment_key)

	# #################################################################################################

	def P_hs(self, request, path):
		url = base64.b64decode(path.encode('utf-8')).decode('utf-8')

		self.cp.log_debug('Requesting HLS segment: %s' % url)
		flags = {
			'finished': False
		}
		def http_code_write( code, rurl ):
			request.setResponseCode(code)

		def http_header_write( k, v ):
			request.setHeader(k, v)

		def http_data_write( data ):
			if data != None:
				request.write(data)
			else:
				if flags['finished'] == False:
					request.finish()

		def request_finished(reason):
			flags['finished'] = True

		self.request_http_data_async(url, http_code_write, http_header_write, http_data_write, range=request.getHeader(b'Range'))
		request.notifyFinish().addBoth(request_finished)
		return self.NOT_DONE_YET

	# #################################################################################################

	def P_hp(self, request, path):
		url = base64.b64decode(path.encode('utf-8')).decode('utf-8')

		self.cp.log_debug('Requesting HLS variant playlist: %s' % url)

		def p_continue(response):
#			self.cp.log_debug('Received HLS variant response: %s' % response)
			if response['status_code'] != 200:
				self.cp.log_error("Status code response for HLS variant playlist: %d" % response['status_code'])
				request.setResponseCode(401)
				request.finish()
				return

			def process_url(surl, redirect_url):
				if not surl.startswith('http'):
					if surl.startswith('/'):
						surl = redirect_url[:redirect_url[9:].find('/') + 9] + surl
					else:
						surl = redirect_url[:redirect_url.rfind('/') + 1] + surl

					surl = self.hls_proxify_segment_url(surl)

				return surl

			resp_data = []
			stream_url_line = False

			for line in iter(response['content'].decode('utf-8').splitlines()):
				if stream_url_line:
					resp_data.append(process_url(line, response['url']))
					stream_url_line = False
					continue

				if 'URI=' in line:
					# fix uri to full url
					uri = line[line.find('URI=') + 4:]

					if uri[0] in ('"', "'"):
						uri = uri[1:uri[1:].find(uri[0]) + 1]

					line = line.replace(uri, process_url(uri, response['url']))

				if line.startswith("#EXTINF:"):
					stream_url_line = True

				resp_data.append(line)

			request.setResponseCode(200)
			request.setHeader('content-type', "application/vnd.apple.mpegurl")
			request.write(('\n'.join(resp_data) + '\n').encode('utf-8'))
			request.finish()
			return

		self.request_http_data_async_simple(url, cbk=p_continue)
		return self.NOT_DONE_YET


	# #################################################################################################

	def get_hls_playlist_data_async(self, url, bandwidth=None, headers=None, cbk=None):
		'''
		Processes HLS master playlist from given url and returns new one with only one variant playlist specified by bandwidth (or with best bandwidth if no bandwidth is given)
		'''

		def process_url(surl, redirect_url):
			if not surl.startswith('http'):
				if surl.startswith('/'):
					surl = redirect_url[:redirect_url[9:].find('/') + 9] + surl
				else:
					surl = redirect_url[:redirect_url.rfind('/') + 1] + surl

				if self.hls_proxy_segments:
					surl = self.hls_proxify_playlist_url(surl)

			return surl

		def p_continue(response, bandwidth):
#			self.cp.log_error("HLS response received: %s" % response)

			if response['status_code'] != 200:
				self.cp.log_error("Status code response for HLS master playlist: %d" % response['status_code'])
				return cbk(None)

			if bandwidth == None:
				bandwidth = 1000000000
			else:
				bandwidth = int(bandwidth)

			streams = []

			response_text = response['content'].decode('utf-8')
			for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', response_text, re.MULTILINE):
				stream_info = {}
				for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
					key, val = info.split('=', 1)
					stream_info[key.strip().lower()] = val.strip()

				stream_info['url'] = process_url(m.group('chunk'), response['url'])

				if int(stream_info.get('bandwidth', 0)) <= bandwidth:
					streams.append(stream_info)

			streams = sorted(streams, key=lambda i: int(i['bandwidth']), reverse=True)

			if len(streams) == 0:
				self.cp.log_error("No streams found for bandwidth %d" % bandwidth)
				return None

			resp_data = []
			ignore_next = False
			stream_to_keep = 'BANDWIDTH=%s' % streams[0].get('bandwidth', 0)

			for line in iter(response_text.splitlines()):
				if ignore_next:
					ignore_next = False
					continue

				if 'URI=' in line:
					# fix uri to full url
					uri = line[line.find('URI=') + 4:]

					if uri[0] in ('"', "'"):
						uri = uri[1:uri[1:].find(uri[0]) + 1]

					line = line.replace(uri, process_url(uri, response['url']))

				if line.startswith("#EXT-X-STREAM-INF:"):
					if stream_to_keep in line:
						resp_data.append(line)
						resp_data.append(streams[0]['url'])

					ignore_next = True
				else:
					resp_data.append(line)

			cbk('\n'.join(resp_data) + '\n')
			return

		self.request_http_data_async_simple(url, cbk=p_continue, headers=headers, bandwidth=bandwidth)

	# #################################################################################################
