# -*- coding: utf-8 -*-

import base64
from .template import HTTPRequestHandlerTemplate
from ..parser.hls import HlsPlaylist
import re
import binascii

from ..compat import quote, unquote, urljoin
from tools_cenc.mp4decrypt import mp4decrypt, mp4_cenc_info_remove

# #################################################################################################

class HlsMasterProcessor(HlsPlaylist):
	def __init__(self, request_handler, url, hls_info=None):
		super(HlsMasterProcessor, self).__init__(url)
		self.request_handler = request_handler
		self.hls_info = hls_info or {}

	# #################################################################################################

	def filter_master_playlist(self):
		super(HlsMasterProcessor, self).filter_master_playlist(max_bandwidth=self.hls_info.get('bandwidth'))

		if self.hls_info.get('drm'):
			# session key is not supported by the player - it will be handled in variant playlist
			self.header = list(filter(lambda p: not p.startswith("#EXT-X-SESSION-KEY:"), self.header))

	# #################################################################################################

	def process_playlist_urls(self):
		super(HlsMasterProcessor, self).process_playlist_urls()

		if self.request_handler.hls_proxy_variants:
			for playlist_group in (self.audio_playlists, self.subtitles_playlists, self.video_playlists):
				for p in playlist_group:
					if p.playlist_url:
						p.playlist_url = self.request_handler.hls_proxify_variant_url(p.playlist_url, self.hls_info)


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
	def __init__(self, content_provider, addon, proxy_segments=False, proxy_variants=False, internal_decrypt=False):
		super(HlsHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_segments = proxy_segments
		self.hls_proxy_variants = proxy_variants
		self.hls_internal_decrypt = proxy_segments and internal_decrypt
		self.hls_master_processor = HlsMasterProcessor

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
			self.get_hls_playlist_data_async(hls_info, cbk=hls_continue)
			return self.NOT_DONE_YET

		except:
			self.cp.log_exception()
			return self.reply_error500(request)

	# #################################################################################################

	def hls_proxify_segment_url(self, segment_cache_key, url, segment_type):
		'''
		Redirects segment url to use proxy
		'''

		if segment_cache_key:
			# drm protected segment, that should be decrypted by hsp handler
			return "/%s/hsp/%s/%s/%s" % (self.name, segment_type, segment_cache_key, quote(url))
		else:
			# not crypted segment, or segment that should be forwarded directly to player
			return "/%s/hs/%s" % (self.name, quote(url))

	# #################################################################################################

	def hls_proxify_playlist_url(self, cache_key):
		'''
		Redirects segment url to use proxy
		'''
		return self.encode_stream_key('/' + self.name, cache_key, 'hp', 'm3u8')

	# #################################################################################################

	def hls_proxify_variant_url(self, variant_url, hls_info={}):
		cache_key = self.calc_cache_key(variant_url)
		cache_data = {
			'url': variant_url,
			'hls_info': hls_info
		}
		self.scache.put_with_key(cache_data, cache_key)
		return self.hls_proxify_playlist_url(cache_key)

	# #################################################################################################

	def P_clearkey(self, request, path):
		self.cp.log_debug("Returning decryption key: %s" % path)
		key = binascii.a2b_hex(path)
		return self.reply_ok( request, key, "application/octet-stream", raw=True)

	# #################################################################################################

	def process_drm_key_line(self, line, drm_info, segment_cache_data):
		self.cp.log_debug('Processing DRM line: %s' % line)

		attr = {}
		for a in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', line[11:]):
			s = a.split('=')
			attr[s[0]] = '='.join(s[1:])

#		self.cp.log_debug('Attrs: %s' % attr)

		if attr.get('KEYFORMAT','').lower() == '"urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"':
			self.cp.log_debug("Widevine keyformat found")
			# wv drm data
			pssh = attr.get('URI','')
			if not pssh.startswith('"data:text/plain;base64,'):
				self.cp.log_error("Failed to process PSSH key - URI format not supported: '%s'" % line)
				line = ''
			else:
				pssh = pssh[24:-1]
				segment_cache_data['pssh'].append(pssh)
				keys = self.get_drm_keys([pssh], drm_info)
				if self.hls_internal_decrypt:
					# when doing internal decrypt, then remove #EXT-X-KEY: line to not confuse player
					line = ''
				else:
					if len(keys) == 1:
						line = '#EXT-X-KEY:METHOD=SAMPLE-AES,URI="/%s/clearkey/%s"' % (self.name, keys[0].split(':')[1])
					else:
						line = '#EXT-X-KEY:METHOD=SAMPLE-AES,URI="keys://' + ':'.join(k.replace(':','=') for k in keys) + '"'
		elif attr.get('METHOD') == 'SAMPLE-AES-CTR':
			# remove not supported DRM line by player
			line = ''

		return line

	# #################################################################################################

	def hls_process_drm_protected_segment(self, segment_type, data, cache_data):
		# handle DRM protected segment data
		if segment_type == 'i':
			self.log_devel("Received init segment data")

			# init segment is not encrypted, but we need it for decrypting data segments
			cache_data['init'] = data

			# remove info about encryption from init data - needed for gstreamer
			return mp4_cenc_info_remove(data)

		# collect keys for protected content
		keys = self.get_drm_keys(cache_data['pssh'], cache_data['drm'], cache_data['drm'].get('privacy_mode', False))

		if len(keys) == 0:
			self.cp.log_error("No keys to decrypt DRM protected content")
			return None

		self.log_devel("Keys for pssh: %s" % str(keys))

		self.log_devel("Decrypting media segment with size %d" % len(data))
		data_out = mp4decrypt(keys, cache_data['init'], data)
		self.log_devel("Decrypted media segment with size %d" % len(data_out))
		return data_out

	# #################################################################################################

	def P_hsp(self, request, path):
		path_splitted = path.split('/')
		segment_type = path_splitted[0]
		segment_cache_key = path_splitted[1]
		segment_url = '/'.join(path_splitted[2:])
		segment_url = unquote(segment_url)

		self.cp.log_debug('Requesting HLS %s segment: %s' % ('init' if segment_type == 'i' else 'media', segment_url))
		cache_data = self.scache.get(segment_cache_key)

		def hsp_continue(response):
			if response['status_code'] >= 400:
				self.cp.log_error("Response code for HLS segment: %d" % response['status_code'])
				request.setResponseCode(403)
			else:
				data = self.hls_process_drm_protected_segment(segment_type, response['content'], cache_data)

				if not data:
					self.cp.log_error('Failed to decrypt segment for stream key: %s' % segment_cache_key)
					request.setResponseCode(501)
				else:
					request.setResponseCode(response['status_code'])
					for k,v in response['headers'].items():
						request.setHeader(k, v)

					request.write(data)

			request.finish()

		self.request_http_data_async_simple(segment_url, cbk=hsp_continue, range=request.getHeader(b'Range'))
		return self.NOT_DONE_YET

	# #################################################################################################

	def P_hs(self, request, path):
		segment_url = unquote(path)

		self.cp.log_debug('Requesting HLS segment: %s' % segment_url)
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

		self.request_http_data_async(segment_url, http_code_write, http_header_write, http_data_write, range=request.getHeader(b'Range'))
		request.notifyFinish().addBoth(request_finished)
		return self.NOT_DONE_YET

	# #################################################################################################

	def process_variant_playlist(self, playlist_url, playlist_data, hls_info={}):
		drm_info = hls_info.get('drm', {})
		segment_cache_data = {
			'drm': drm_info,
			'pssh': []
		}

		segment_cache_key = self.calc_cache_key('segment' + playlist_url)
		self.scache.put_with_key(segment_cache_data, segment_cache_key)

		def process_url(surl, redirect_url, segment_type='m'):
			surl = urljoin(redirect_url, surl)

			if self.hls_proxy_segments:
				surl = self.hls_proxify_segment_url(segment_cache_key if len(segment_cache_data['pssh']) > 0 else None, surl, segment_type)

			return surl

		resp_data = []
		stream_url_line = False

		for line in iter(playlist_data.splitlines()):
			if stream_url_line and not line.startswith('#'):
				resp_data.append(process_url(line, playlist_url))
				stream_url_line = False
				continue

			if drm_info and line.startswith("#EXT-X-KEY:"):
				line = self.process_drm_key_line(line, drm_info, segment_cache_data)
			elif 'URI=' in line:
				# fix uri to full url
				uri = line[line.find('URI=') + 4:]

				if uri[0] in ('"', "'"):
					uri = uri[1:uri[1:].find(uri[0]) + 1]

				line = line.replace(uri, process_url(uri, playlist_url, 'i' if line.startswith('#EXT-X-MAP:') else 'm'))

			if line.startswith("#EXTINF:"):
				stream_url_line = True

			resp_data.append(line)

		return '\n'.join(resp_data) + '\n'

 	# #################################################################################################

	def P_hp(self, request, path):
		cache_key = self.decode_stream_key(path)
		stream_data = self.scache.get(cache_key)
		url = stream_data['url']

		self.cp.log_debug('Requesting HLS variant playlist: %s' % url)

		def p_continue(response):
#			self.cp.log_debug('Received HLS variant response: %s' % response)
			if response['status_code'] != 200:
				self.cp.log_error("Status code response for HLS variant playlist: %d" % response['status_code'])
				request.setResponseCode(401)
				request.finish()
				return

			resp_data = self.process_variant_playlist(response['url'], response['content'].decode('utf-8'), stream_data['hls_info'])

			request.setResponseCode(200)
			request.setHeader('content-type', "application/vnd.apple.mpegurl")
			request.write(resp_data.encode('utf-8'))
			request.finish()
			return

		self.request_http_data_async_simple(url, cbk=p_continue)
		return self.NOT_DONE_YET

	# #################################################################################################

	def process_master_playlist(self, playlist_url, playlist_data, hls_info):
		return self.hls_master_processor(self, playlist_url, hls_info).process(playlist_data)

	# #################################################################################################

	def get_hls_playlist_data_async(self, hls_info, cbk=None):
		'''
		Processes HLS master playlist from given url and returns new one with only one variant playlist specified by bandwidth (or with best bandwidth if no bandwidth is given)
		'''

		def p_continue(response):
#			self.cp.log_error("HLS response received: %s" % response)

			if response['status_code'] != 200:
				self.cp.log_error("Status code response for HLS master playlist: %d" % response['status_code'])
				return cbk(None)

			resp_data = self.process_master_playlist(response['url'], response['content'].decode('utf-8'), hls_info)
			cbk(resp_data)
			return

		self.request_http_data_async_simple(hls_info['url'], cbk=p_continue, headers=hls_info.get('headers'))

	# #################################################################################################
