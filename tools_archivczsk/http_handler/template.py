# -*- coding: utf-8 -*-

import os, base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler
from ..cache import SimpleAutokeyExpiringCache
import json

from tools_cenc.wvdecrypt import WvDecrypt
from tools_cenc.prdecrypt import PrDecrypt
from tools_cenc.mp4decrypt import mp4_pssh_get
from binascii import crc32

# #################################################################################################

class HTTPRequestHandlerTemplate(AddonHttpRequestHandler):
	CHUNK_SIZE = 40960

	def __init__(self, content_provider, addon):
		super(HTTPRequestHandlerTemplate, self).__init__(addon)

		self.cp = content_provider
		self.scache = SimpleAutokeyExpiringCache()
		self.req_session = self.cp.get_requests_session()

		self.enable_devel_logs = os.path.isfile('/tmp/archivczsk_enable_devel_logs')
		self.wvdecrypt = WvDecrypt.get_instance()
		self.prdecrypt = PrDecrypt.get_instance()
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

	def forward_http_data(self, request, url, headers=None):
		h = {}
		h.update(headers or {})

		r = request.get_header('Range')
		if r:
			h['Range'] = r

		try:
			response = self.req_session.get(url, headers=headers, stream=True)
		except:
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))
			request.send_response(500)
			return

		request.send_response(response.status_code)
		self.forward_http_headers(request, response)

		for chunk in response.iter_content(self.CHUNK_SIZE):
			request.write(chunk)

	# #################################################################################################

	def request_http_data(self, url, headers=None):
		try:
			response = self.req_session.get(url, headers=headers)
		except:
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))
			return 500, None

		return response.status_code, response.content

	# #################################################################################################

	def forward_http_headers(self, request, response, headers=None):
		headers = headers or ('Accept-Ranges', 'Content-Type', 'Accept', 'Content-Range')

		for k,v in response.headers.items():
			if k in headers:
				request.send_header(k, v)

	# #################################################################################################

	def get_drm_license(self, drm_info, lic_request):
		session = self.cp.get_requests_session()

		try:
			response = session.post(drm_info['license_url'], data=lic_request, headers=drm_info.get('headers',{}))
			response.raise_for_status()
			content = response.content
		except Exception as e:
			self.cp.log_error("Failed to get DRM license: %s" % str(e))
			content = None

		session.close()

		return content

	# #################################################################################################


	def get_drm_keys(self, pssh_list, drm_info):
		wv_drm_info = drm_info.get('wv',{})
		pr_drm_info = drm_info.get('pr',{})

		keys = []
		for drm_type in ('wv', 'pr'):
			for p in pssh_list.get(drm_type,[]):
				if p == 'dynamic':
					# skip dummy pssh
					continue

				k = self.pssh.get(p)
				if k == None:
					self.cp.log_debug("Requesting keys for pssh from %s license server" % p)

					if drm_type == 'wv':
						if wv_drm_info:
							if wv_drm_info.get('privacy_mode', False):
								k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(wv_drm_info, lic_request), lambda cert_request: self.get_drm_license(wv_drm_info, cert_request))
							else:
								k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(wv_drm_info, lic_request))

							if not k:
								self.cp.log_error("Failed to get DRM keys for WV pssh %s" % p)
						else:
							self.cp.log_debug("No widevine license URL provided")

					elif drm_type == 'pr':
						if pr_drm_info:
							k = self.prdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(pr_drm_info, lic_request))

							if not k:
								self.cp.log_error("Failed to get DRM keys for PR pssh %s" % p)
						else:
							self.cp.log_debug("No playready license URL provided")

					self.pssh[p] = k
					if k:
						keys.extend(k)
						self.cp.log_debug("Received %d keys for pssh %s" % (len(k), p))
				else:
					self.cp.log_debug("Keys for pssh %s found in cache" % p)
					keys.extend(k)

		return keys

	# #################################################################################################

	def get_mp4_pssh(self, data, pssh_list={}):
		pssh, kid, drm_type = mp4_pssh_get(data)

		self.log_devel("Received %s PSSH from mp4: %s" % (drm_type, pssh))
		self.log_devel("Received KID from mp4: %s" % kid)

		if pssh and pssh not in pssh_list[drm_type]:
			pssh_list.append(pssh)
			self.cp.log_debug("Adding PSSH %s from mp4 to list of available PSSHs" % pssh)

		return kid

	# #################################################################################################

	@staticmethod
	def calc_cache_key(data):
		return str(crc32(data.encode('utf-8')) & 0xffffffff)

	# #################################################################################################
