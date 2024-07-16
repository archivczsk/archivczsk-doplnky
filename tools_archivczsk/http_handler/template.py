# -*- coding: utf-8 -*-

import os, base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler
from Plugins.Extensions.archivCZSK.settings import USER_AGENT
from ..cache import SimpleAutokeyExpiringCache
import json

from twisted.web.client import CookieAgent, RedirectAgent, Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers
from twisted.internet.protocol import Protocol
from twisted.internet import reactor

try:
	from cookielib import CookieJar
except:
	from http.cookiejar import CookieJar

from tools_cenc.wvdecrypt import WvDecrypt
from binascii import crc32

# #################################################################################################

try:
	from twisted.web.iweb import IPolicyForHTTPS
	from twisted.internet.ssl import CertificateOptions
	from twisted.internet import _sslverify
	from zope.interface import implementer

	@implementer(IPolicyForHTTPS)
	class SSLNoVerifyContextFactory(object):
		def creatorForNetloc(self, hostname, port):
			return _sslverify.ClientTLSOptions(hostname.decode('utf-8'), CertificateOptions(verify=False).getContext())
except:
	SSLNoVerifyContextFactory = None

# #################################################################################################

class SegmentDataWriter(Protocol):
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

class HTTPRequestHandlerTemplate(AddonHttpRequestHandler, object):
	def __init__(self, content_provider, addon):
#		AddonHttpRequestHandler.__init__(self, addon)
		super(HTTPRequestHandlerTemplate, self).__init__(addon)

		self.cp = content_provider
		self.scache = SimpleAutokeyExpiringCache()
		timeout = int(self.cp.get_setting('loading_timeout'))
		if timeout == 0:
			timeout = 5 # it will be very silly to disable timeout, so set 5s here as default

		self._cookies = CookieJar()
		self._pool = HTTPConnectionPool(reactor)

		if SSLNoVerifyContextFactory == None:
			self.cp.log_error("Old/not compatible version of twisted library detected - unable to disable SSL verification")
			self.cookie_agent = Agent(reactor, connectTimeout=timeout/2, pool=self._pool)
		elif self.cp.get_setting('verify_ssl'):
			self.cookie_agent = Agent(reactor, connectTimeout=timeout/2, pool=self._pool)
		else:
			self.cookie_agent = Agent(reactor, connectTimeout=timeout/2, pool=self._pool, contextFactory=SSLNoVerifyContextFactory())

		self.cookie_agent = CookieAgent(self.cookie_agent, self._cookies)
		self.cookie_agent = RedirectAgent(self.cookie_agent)

		self.enable_devel_logs = os.path.isfile('/tmp/archivczsk_enable_devel_logs')
		self.wvdecrypt = WvDecrypt(enable_logging=self.enable_devel_logs)
		self.pssh = {}

	# #################################################################################################

	def log_devel(self, msg):
		if self.enable_devel_logs:
			self.cp.log_debug(msg)


	# #################################################################################################

	@staticmethod
	def encode_stream_key(endpoint, stream_key, uri, extension):
		'''
		Converts stream key (string or dictionary) to url, that can be played by player.
		'''
		if stream_key == None:
			stream_key = ""

		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		stream_key = base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')
		return "%s/%s/%s.%s" % (endpoint, uri, stream_key, extension)

	# #################################################################################################

	def decode_stream_key(self, path):
		'''
		Decodes stream key encoded using stream_key_to_dash_url or stream_key_to_hls_url
		'''
		if path.endswith('.mpd'):
			path = path[:-4]
		elif path.endswith('.m3u8'):
			path = path[:-5]

		if len(path) > 0:
			stream_key = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			if stream_key[0] == '{' and stream_key[-1] == '}':
				stream_key = json.loads(stream_key[1:-1])

			return stream_key

		else:
			return None

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
			request_headers.addRawHeader(b'User-Agent', USER_AGENT.encode('utf-8'))

		d = self.cookie_agent.request( b'GET', url.encode('utf-8'), request_headers, None)
		timeout_call = reactor.callLater(timeout, d.cancel)

		def request_created(response):
			cbk_response_code(response.code, response.request.absoluteURI)

#			self.log_devel("Response headers: %d" % response.code)
#			for k,v in response.headers.getAllRawHeaders():
#				self.log_devel("%s: %s" % (k.decode('utf-8'), v[0].decode('utf-8')))

			for k,v in response.headers.getAllRawHeaders():
				if k in (b'Accept-Ranges', b'Content-Type', b'Accept', b'Content-Range'):
					cbk_header(k,v[0])

			response.deliverBody(SegmentDataWriter(self.cp, d, cbk_data, timeout_call))

		def request_failed(response):
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))

			cbk_response_code(500, '')
			cbk_data(None)
			if timeout_call.active():
				timeout_call.cancel()

		d.addCallback(request_created)
		d.addErrback(request_failed)

	# #################################################################################################

	def request_http_data_async_simple(self, url, cbk, headers=None, range=None, **kwargs):
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

		return self.request_http_data_async( url, cbk_response_code, cbk_header, cbk_data, headers=headers, range=range)

	# #################################################################################################

	def get_wv_licence(self, drm_info, lic_request):
		session = self.cp.get_requests_session()
		try:
			response = session.post(drm_info['licence_url'], data=lic_request, headers=drm_info.get('headers',{}))
			response.raise_for_status()
			content = response.content
		except Exception as e:
			self.cp.log_error("Failed to get DRM licence: %s" % str(e))
			content = None

		session.close()

		return content

	# #################################################################################################

	def get_drm_keys(self, pssh_list, drm_info, privacy_mode=False):
		keys = []
		for p in pssh_list:
			k = self.pssh.get(p)
			if k == None:
				self.cp.log_debug("Requesting keys for pssh %s from licence server" % p)
				if privacy_mode:
					k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_wv_licence(drm_info, lic_request), lambda cert_request: self.get_wv_licence(drm_info, cert_request))
				else:
					k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_wv_licence(drm_info, lic_request))
				self.pssh[p] = k
				if k:
					keys.extend(k)
					self.cp.log_debug("Received %d keys for pssh %s" % (len(k), p))
				else:
					self.cp.log_error("Failed to get DRM keys for pssh %s" % p)
			else:
				self.cp.log_debug("Keys for pssh %s found in cache" % p)
				keys.extend(k)

		return keys

	# #################################################################################################

	@staticmethod
	def calc_cache_key(data):
		return str(crc32(data.encode('utf-8')) & 0xffffffff)

	# #################################################################################################
