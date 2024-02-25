# -*- coding: utf-8 -*-

from .template import HTTPRequestHandlerTemplate
import base64
import json

import xml.etree.ElementTree as ET

try:
	from urlparse import urljoin
except:
	from urllib.parse import urljoin

from tools_cenc.wvl3.wvdecryptcustom import WvDecrypt
from tools_cenc.mp4decrypt import mp4decrypt

# #################################################################################################

def stream_key_to_dash_url(endpoint, stream_key):
	'''
	Converts stream key (string or dictionary) to url, that can be played by player. It is then handled by DashHTTPRequestHandler that will respond with processed MPD playlist
	'''
	return HTTPRequestHandlerTemplate.encode_stream_key(endpoint, stream_key, 'dash', 'mpd')

# #################################################################################################

class DashHTTPRequestHandler(HTTPRequestHandlerTemplate):
	'''
	Http request handler that implements processing of DASH master playlist and exports new one with only selected one video stream.
	Other streams (audio, subtitles, ...) are preserved.
	'''
	def __init__(self, content_provider, addon, proxy_segments=True):
		super(DashHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = proxy_segments
		self.enable_devel_logs = False
		self.wvdecrypt = WvDecrypt(enable_logging=self.enable_devel_logs)
		self.pssh = {}
		self.segment_counter = 0

	# #################################################################################################

	def log_devel(self, msg):
		if self.enable_devel_logs:
			self.cp.log_debug(msg)

	# #################################################################################################

	def get_dash_info(self, stream_key):
		'''
		This is default implementation, that just forwards this call to content provider.
		Replace it with your own implementation if you need something different.
		'''
		return self.cp.get_dash_info(stream_key)

	# #################################################################################################

	def P_dash(self, request, path):
		'''
		Handles request to MPD playlist. Address is created using stream_key_to_dash_url()
		'''
		def dash_continue(data):
			if data:
				self.log_devel("Processed MPD:\n%s" % data.decode('utf-8'))
				request.setResponseCode(200)
				request.setHeader('content-type', "application/dash+xml")
				request.write(data)
			else:
				request.setResponseCode(401)
			request.finish()


		try:
			stream_key = self.decode_stream_key(path)

			dash_info = self.get_dash_info(stream_key)

			if not dash_info:
				self.reply_error404(request)

			if not isinstance(dash_info, type({})):
				dash_info = { 'url': dash_info }

			# resolve and process DASH playlist
			self.get_dash_playlist_data_async(dash_info['url'], dash_info.get('bandwidth'), dash_info.get('headers'), dash_info.get('drm',{}), cbk=dash_continue)
			return self.NOT_DONE_YET

		except:
			self.cp.log_exception()
			return self.reply_error500(request)


	# #################################################################################################

	def dash_proxify_base_url(self, url, pssh=[], drm=None):
		'''
		Redirects segment url to use proxy
		'''
		if len(pssh) == 0 and isinstance(drm, type({})) and drm.get('pssh'):
			pssh = drm['pssh']

		key = self.scache.put({
			'url': url,
			'pssh': pssh,
			'drm': drm,
			'init': {}
		})

		if len(pssh) > 0:
			# drm protectet content - use handler for protectet segments
			return "/%s/dsp/%s/" % (self.name, key)
		else:
			return "/%s/ds/%s/" % (self.name, key)

	# #################################################################################################

	def P_ds(self, request, path):
		# split path to encoded base URL and segment part
		url_parts=path.split('/')
		cache_data = self.scache.get(url_parts[0])

		if not cache_data:
			self.log_error("No cached data found for key: %s" % url_parts[0])
			self.reply_error500(request)

		base_url = cache_data['url']

		# recreate original segment URL
		# url_parts[0] is segment type - this information is only needed when DRM is active
		url = '/'.join(url_parts[2:])
		url = urljoin(base_url, url.replace('dot-dot-slash', '../'))

		self.log_devel('Requesting DASH segment: %s' % url)
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

	def process_drm_protected_segment(self, segment_type, data, cache_data):
		# handle DRM protected segment data
		if segment_type[0] == 'i':
			self.log_devel("Received init segment data for %s" % segment_type[1:])

			# init segment is not encrypted, but we need it for decrypting data segments
			cache_data['init'][segment_type[1:]] = data
			return data

		# collect keys for protected content
		keys = []
		for p in cache_data['pssh']:
			k = self.pssh.get(p)
			if k == None:
				self.cp.log_debug("Requesting keys for pssh %s from licence server" % p)
				if cache_data['drm'].get('privacy_mode', False):
					k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_wv_licence(cache_data['drm'], lic_request), lambda cert_request: self.get_wv_licence(cache_data['drm'], cert_request))
				else:
					k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_wv_licence(cache_data['drm'], lic_request))
				self.pssh[p] = k
				if k:
					keys.extend(k)
				else:
					self.cp.log_error("Failed to get DRM keys for pssh %s" % p)
			else:
				self.log_devel("Keys for pssh %s found in cache" % p)
				keys.extend(k)

		if len(keys) == 0:
			self.cp.log_error("No keys to decrypt DRM protected content")
			return None

		self.log_devel("Keys for pssh: %s" % str(keys))
		return mp4decrypt(keys, cache_data['init'][segment_type[1:]], data)

	# #################################################################################################

	def P_dsp(self, request, path):
		self.log_devel("Received segment request: %s" % path)
		# split path to encoded base URL and segment part
		url_parts=path.split('/')
		cache_data = self.scache.get(url_parts[0])

		if not cache_data:
			self.log_error("No cached data found for key: %s" % url_parts[0])
			self.reply_error500(request)

		segment_type = url_parts[1]
		base_url = cache_data['url']

		# recreate original segment URL
		url = '/'.join(url_parts[2:])
		url = urljoin(base_url, url.replace('dot-dot-slash', '../'))
		self.log_devel("Original URL: %s" % url)
		self.log_devel("Segment type: %s" % segment_type)
#		self.log_devel("cache_data: %s" % str(cache_data))

		def dsp_continue(response):
			if response['status_code'] >= 400:
				self.cp.log_error("Response code for DASH segment: %d" % response['status_code'])
				request.setResponseCode(403)
			else:
				data = self.process_drm_protected_segment(segment_type, response['content'], cache_data)

				if not data:
					request.setResponseCode(501)
				else:
					request.setResponseCode(200)
					for k,v in response['headers'].items():
						if k != b'Content-Length':
							request.setHeader(k, v)

					request.setHeader(b'Content-Length', str(len(data)))
					request.write(data)

			request.finish()

		self.log_devel('Requesting DASH segment: %s' % url)
		self.request_http_data_async_simple(url, cbk=dsp_continue, range=request.getHeader(b'Range'))
		return self.NOT_DONE_YET

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, drm=None):
		kid_list = []
		pssh_list = []

		# extract namespace of root element and set it as global namespace
		ns = root.tag[1:root.tag.index('}')]
		ET.register_namespace('', ns)
		ns = '{%s}' % ns

		def search_drm_data(element):
			ret = False
			kid = None
			e = element.find('./{}ContentProtection[@schemeIdUri="urn:mpeg:dash:mp4protection:2011"]'.format(ns))
			if e != None:
				kid = e.get('{urn:mpeg:cenc:2013}default_KID') or e.get('default_KID')
				if kid:
					self.log_devel("Found KID: %s" % kid)
					kid_list.append(kid)
					ret = True

			e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e == None:
				e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e != None and e.text:
				self.log_devel("Found PSSH: %s" % e.text)
				pssh_list.append(e.text.strip())
				ret = True

			return ret

		def path_segment_url(element):
			for e_segment_template in element.findall('{}SegmentTemplate'.format(ns)):
				v = e_segment_template.get('initialization')
				if v:
					e_segment_template.set('initialization', 'i%d/%s' % (self.segment_counter, v.replace('../', 'dot-dot-slash')))

				v = e_segment_template.get('media')
				if v:
					e_segment_template.set('media', 'm%d/%s' % (self.segment_counter, v.replace('../', 'dot-dot-slash')))
				self.segment_counter += 1

		def remove_content_protection(element):
			for e in element.findall('{}ContentProtection'.format(ns)):
				element.remove(e)


		# modify MPD manifest and make it as best playable on enigma2 as possible
		for e_period in root.findall('{}Period'.format(ns)):
			audio_list = []
			kid_list = []
			pssh_list = []


			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if e_adaptation_set.get('contentType','') == 'video' or e_adaptation_set.get('mimeType','').startswith('video/'):
					# search for video representations and keep only highest resolution/bandwidth
					rep_childs = e_adaptation_set.findall('{}Representation'.format(ns))

					# sort representations based on bandwidth
					# if representation's bandwidth is <= then user specified max bandwidth, then sort it from best to worst
					# if representation's bandwidth is > then user specified max bandwidth, then sort it from worst to best
					rep_childs.sort(key=lambda x: int(x.get('bandwidth',0)) if int(x.get('bandwidth',0)) <= bandwidth else -int(x.get('bandwidth',0)), reverse=True)

					# keep only first Representation and remove all others
					for child2 in rep_childs[1:]:
						e_adaptation_set.remove(child2)

				if e_adaptation_set.get('contentType','') == 'audio' or e_adaptation_set.get('mimeType','').startswith('audio/'):
					audio_list.append(e_adaptation_set)

				search_drm_data(e_adaptation_set)
				for e in e_adaptation_set.findall('{}Representation'.format(ns)):
					search_drm_data(e)

				# for DRM protected content we need to add distinguish between init and data segment, so set prefix for it
				# and also remove ContentProtection elements from manifest
				path_segment_url(e_adaptation_set)
				remove_content_protection(e_adaptation_set)
				for e in e_adaptation_set.findall('{}Representation'.format(ns)):
					path_segment_url(e)
					remove_content_protection(e)

			if len(audio_list) > 0:
				# all enigma2 players use first audio track as the default, so move CZ and SK audio tracks on the top

				# remove all audio AdaptationSets
				for a in audio_list:
					e_period.remove(a)

				# sort audio AdaptationSets by language - cz and sk tracks first ...
				audio_list.sort(key=lambda a: a.get('lang','').lower() in ('cs', 'sk', 'ces', 'cze', 'slo', 'slk'), reverse=True)

				# add it back to Period element
				for a in audio_list:
					e_period.append(a)

			# either update BaseURL or create element and set it
			e_base_url = e_period.find('{}BaseURL'.format(ns))
			if  e_base_url == None:
				e_base_url = root.find('{}BaseURL'.format(ns))

			if e_base_url != None:
				base_url_set = urljoin(base_url, e_base_url.text)

				if self.dash_proxy_segments:
					base_url_set = self.dash_proxify_base_url(base_url_set, pssh=list(set(pssh_list)), drm=drm)

				e_base_url.text = base_url_set
			else:
				# base path not found in MPD, so set it ...
				if self.dash_proxy_segments:
					base_url_set = self.dash_proxify_base_url(base_url, pssh=list(set(pssh_list)), drm=drm)
				else:
					base_url_set = base_url

				ET.SubElement(root, 'BaseURL').text = base_url_set


	# #################################################################################################

	def get_dash_playlist_data_async(self, url, bandwidth=None, headers=None, drm=None, cbk=None):
		'''
		Processes DASH playlist from given url and returns new one with only one video adaptive specified by bandwidth (or with best bandwidth if no bandwidth is given)
		'''
		def p_continue(response, bandwidth):
#			self.log_devel("MPD response received: %s" % response)

			if response['status_code'] != 200:
				self.cp.log_error("Status code response for MPD playlist: %d" % response['status_code'])
				return cbk(None)

			if bandwidth == None:
				bandwidth = 1000000000
			else:
				bandwidth = int(bandwidth)

			redirect_url = response['url']
			redirect_url = redirect_url[:redirect_url.rfind('/')] + '/'

			response_data = response['content'].decode('utf-8')
			self.log_devel("Received MPD:\n%s" % response_data)

			root = ET.fromstring(response_data)
			self.handle_mpd_manifest(redirect_url, root, bandwidth, drm)
			cbk( ET.tostring(root, encoding='utf8', method='xml'))
			return

		self.request_http_data_async_simple(url, cbk=p_continue, headers=headers, bandwidth=bandwidth)


	# #################################################################################################
