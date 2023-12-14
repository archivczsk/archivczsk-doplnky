# -*- coding: utf-8 -*-

import base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler
from time import time
import requests
import re
import json

from twisted.web.client import CookieAgent, RedirectAgent, Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.internet.protocol import Protocol
from twisted.internet import reactor

try:
	from cookielib import CookieJar
except:
	from http.cookiejar import CookieJar


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

class HlsSegmentDataWriter(Protocol):
	def __init__(self, cp, d, cbk_data, timeout_call ):
		self.cp = cp
		self.d = d # reference to defered object - needed to ensure, that it is not destroyed during operation
		self.cbk_data = cbk_data
		self.timeout_call = timeout_call

	def dataReceived(self, data):
		try:
			self.cbk_data(data)
		except:
			self.cp.log_exception()

	def connectionLost(self, reason):
		try:
			self.cbk_data(None)
		except:
			self.cp.log_exception()

		if self.timeout_call.active():
			self.timeout_call.cancel()

# #################################################################################################

class HlsHTTPRequestHandler(AddonHttpRequestHandler):
	'''
	Http request handler that implements processing of HLS master playlist and exports new one with only selected one video stream.
	Other streams (audio, subtitles, ...) are preserved.
	'''
	def __init__(self, content_provider, addon, proxy_segments=False):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider
		self.proxy_segments = proxy_segments

		timeout = int(self.cp.get_setting('loading_timeout'))
		if timeout == 0:
			timeout = 5 # it will be very silly to disable timeout, so set 5s here as default

		self._cookies = CookieJar()
		self._pool = HTTPConnectionPool(reactor)
		self.cookie_agent = Agent(reactor, connectTimeout=timeout/2, pool=self._pool)
		self.cookie_agent = CookieAgent(self.cookie_agent, self._cookies)
		self.cookie_agent = RedirectAgent(self.cookie_agent)

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

	def proxify_segment_url(self, url):
		'''
		Redirects segment url to use proxy
		'''

		segment_key = base64.b64encode(url.encode('utf-8')).decode('utf-8')
		return "/%s/s/%s" % (self.name, segment_key)

	# #################################################################################################

	def proxify_playlist_url(self, url):
		'''
		Redirects segment url to use proxy
		'''

		segment_key = base64.b64encode(url.encode('utf-8')).decode('utf-8')
		return "/%s/p/%s" % (self.name, segment_key)

	# #################################################################################################

	def P_s(self, request, path):
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

	def request_http_data_async(self, url, cbk_response_code, cbk_header, cbk_data, headers=None, range=None):
		timeout = int(self.cp.get_setting('loading_timeout'))
		if timeout == 0:
			timeout = 5 # it will be very silly to disable timeout, so set 5s here as default

		request_headers = Headers()

		if headers:
			for k, v in headers.items():
				request_headers.addRawHeader(k.encode('utf-8'), v.encode('utf-8'))

		if range != None:
			request_headers.addRawHeader(b'Range', range)

		if not request_headers.hasHeader('User-Agent'):
			# empty user agent is not what we want, so use something common
			request_headers.addRawHeader(b'User-Agent', b'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

		d = self.cookie_agent.request( b'GET', url.encode('utf-8'), request_headers, None)

		timeout_call = reactor.callLater(timeout, d.cancel)

		def request_created(response):
			cbk_response_code(response.code, response.request.absoluteURI)

			for k,v in response.headers.getAllRawHeaders():
				if k in (b'Content-Length', b'Accept-Ranges', b'Content-Type', b'Accept'):
					cbk_header(k,v[0])

			response.deliverBody(HlsSegmentDataWriter(self.cp, d, cbk_data, timeout_call))

		def request_failed(response):
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))

			cbk_response_code(500, '')
			cbk_data(None)
			if timeout_call.active():
				timeout_call.cancel()

		d.addCallback(request_created)
		d.addErrback(request_failed)

	# #################################################################################################

	def request_http_data_async_simple(self, url, cbk, headers=None, **kwargs):
		response = {
			'status_code': None,
			'url': None,
			'headers': {},
			'content': b''
		}

		def cbk_response_code(rcode, rurl):
			response['status_code'] = rcode
			response['url'] = rurl.decode('utf-8')

		def cbk_header(k, v):
			response['headers'][k] = v

		def cbk_data(data):
			if data == None:
				try:
					cbk(response, **kwargs)
				except:
					self.cp.log_exception()
			else:
				response['content'] += data
		
		return self.request_http_data_async( url, cbk_response_code, cbk_header, cbk_data, headers=headers)
		
	# #################################################################################################

	def P_p(self, request, path):
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
					
					surl = self.proxify_segment_url(surl)

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
				
				if self.proxy_segments:
					surl = self.proxify_playlist_url(surl)

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
