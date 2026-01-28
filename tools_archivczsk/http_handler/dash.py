# -*- coding: utf-8 -*-
import os
from .template import HTTPRequestHandlerTemplate
from ..compat import urljoin
import xml.etree.ElementTree as ET

from tools_cenc.mp4decrypt import mp4decrypt, mp4_cenc_info_remove

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
	def __init__(self, content_provider, addon, proxy_segments=True, internal_decrypt=True):
		super(DashHTTPRequestHandler, self).__init__(content_provider, addon)
		self.dash_proxy_segments = proxy_segments
		self.dash_internal_decrypt = internal_decrypt

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
		if path.startswith('%s/dsp/' % self.name):
			# workaround for buggy internal player in OpenATV 7.3 (doesn't handle properly BaseURL tag)
			return self.P_dsp(request, path[len(self.name)+5:])

		if path.startswith('%s/ds/' % self.name):
			# workaround for buggy internal player in OpenATV 7.3 (doesn't handle properly BaseURL tag)
			return self.P_ds(request, path[len(self.name)+4:])

		self.log_devel("Request for MPD manifest for: %s" % path)

		stream_key = self.decode_stream_key(path)

		dash_info = self.get_dash_info(stream_key)

		if not dash_info:
			return self.reply_error404(request)

		if not isinstance(dash_info, type({})):
			dash_info = { 'url': dash_info }

		if int(request.get_header('X-DRM-Api-Level') or '0') >= 1 and dash_info.get('ext_drm_decrypt', True):
			# player supports DRM, so don't do internal decryption and let player handle DRM
			dash_info['dash_internal_decrypt'] = False

		self.log_devel("Dash info: %s" % str(dash_info))

		# resolve and process DASH playlist
		data = self.get_dash_playlist_data(dash_info)

		if data:
			request.send_response(200)
			request.send_header('content-type', "application/dash+xml")
			return data
		else:
			request.send_response(401)


	# #################################################################################################

	def dash_proxify_base_url(self, url, dash_internal_decrypt, pssh_list={}, default_kid=False, drm=None, cache_key=None):
		'''
		Redirects segment url to use proxy
		'''

		for p in ('wv', 'pr'):
			if len(pssh_list[p]) == 0 and isinstance(drm, type({})) and drm.get(p, {}).get('pssh'):
				pssh_list[p] = drm[p]['pssh']

		cached_data = {'init':{}}
		if cache_key:
			cached_data = self.scache.get(cache_key, cached_data)

		cached_data.update({
			'url': url,
			'pssh': pssh_list,
			'drm': drm,
			'default_kid': default_kid
		})

		if cache_key == None:
			cache_key = self.scache.put(cached_data)
		else:
			cache_key = self.scache.put_with_key(cached_data, cache_key)

		if (len(pssh_list['wv']) > 0 or len(pssh_list['pr']) > 0) and dash_internal_decrypt:
			self.cp.log_debug("Enabling DRM proxy handler for url %s with key %s" % (url, cache_key))
			# drm protectet content - use handler for protectet segments
			return "/%s/dsp/%s/" % (self.name, cache_key)
		else:
			self.cp.log_debug("Enabling proxy handler for url %s with key %s" % (url, cache_key))
			return "/%s/ds/%s/" % (self.name, cache_key)

	# #################################################################################################

	def P_ds(self, request, path):
		# split path to encoded base URL and segment part
		url_parts=path.split('/')
		cache_data = self.scache.get(url_parts[0])

		if not cache_data:
			self.log_error("No cached data found for key: %s" % url_parts[0])
			return self.reply_error500(request)

		base_url = cache_data['url']

		# recreate original segment URL
		# url_parts[1] is segment type - this information is only needed when DRM is active
		url = '/'.join(url_parts[2:])
		url = urljoin(base_url, url.replace('dot-dot-slash', '../'))

		self.log_devel('Requesting DASH segment: %s' % url)
		self.forward_http_data(request, url)

	# #################################################################################################

	def process_drm_protected_segment(self, segment_type, data, cache_data):
		# handle DRM protected segment data
		if segment_type[0] == 'i':
			self.log_devel("Received init segment data for %s" % segment_type[1:])

			# init segment is not encrypted, but we need it for decrypting data segments
			cache_data['init'][segment_type[1:]] = data
			return mp4_cenc_info_remove(data)

		if cache_data['default_kid']:
			kid = None
		else:
			# we don't have default kid specified - search kid and pssh directly in mp4 data
			kid = self.get_mp4_pssh(data, cache_data['pssh'])

		# collect keys for protected content
		keys = self.get_drm_keys(cache_data['pssh'], cache_data['drm'])

		if len(keys) == 0:
			self.cp.log_error("No keys to decrypt DRM protected content")
			return None

		self.log_devel("Keys for pssh: %s" % str(keys))

		if kid:
			# kid directly from mp4 is found - look for right key and set it as default
			self.cp.log_debug("Looking for kid %s to set default decryption key" % kid)
			for k in keys:
				if k.startswith(kid + ':'):
					keys.append('00000000000000000000000000000000:' + k.split(':')[1])
					self.cp.log_debug("Adding default key: %s" % keys[-1][33:])
					break

		return mp4decrypt(keys, cache_data['init'].get(segment_type[1:]), data)

	# #################################################################################################

	def P_dsp(self, request, path):
		self.log_devel("Received segment request: %s" % path)

		# split path to encoded base URL and segment part
		url_parts=path.split('/')
		cache_data = self.scache.get(url_parts[0])

		if not cache_data:
			self.log_error("No cached data found for key: %s" % url_parts[0])
			return self.reply_error500(request)

		segment_type = url_parts[1]
		base_url = cache_data['url']

		# recreate original segment URL
		url = '/'.join(url_parts[2:])
		url = urljoin(base_url, url.replace('dot-dot-slash', '../'))
		self.log_devel("Original URL: %s" % url)
		self.log_devel("Segment type: %s" % segment_type)
#		self.log_devel("cache_data: %s" % str(cache_data))

		headers = {}
		r = request.get_header('Range')
		if r:
			headers['Range'] = r

		self.log_devel('Requesting DASH segment: %s' % url)
		try:

			response = self.req_session.get(url, headers=headers)
		except:
			self.cp.log_error('Failed to retrieve segment data from %s\n%s' % (url, str(response)))
			request.send_response(500)
			return

		if response.status_code >= 400:
			self.cp.log_error("Response code for DASH segment: %d" % response['status_code'])
			request.send_response(403)

		data = self.process_drm_protected_segment(segment_type, response.content, cache_data)

		if not data:
			self.cp.log_error('Failed to decrypt segment for stream key: %s' % url_parts[0])
			request.send_response(501)
		else:
			request.send_response(response.status_code)
			self.forward_http_headers(request, response)
			return data

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		pssh_list = { 'wv': [], 'pr': []}
		kid_rep_mapping = {}
		drm = dash_info.get('drm',{})

		dash_proxy_segments = dash_info.get('dash_proxy_segments', self.dash_proxy_segments)
		dash_internal_decrypt = dash_info.get('dash_internal_decrypt', self.dash_internal_decrypt)

		# extract namespace of root element and set it as global namespace
		ns = root.tag[1:root.tag.index('}')]
		ET.register_namespace('', ns)
		ns = '{%s}' % ns

		e_base_url = root.find('{}BaseURL'.format(ns))
		if e_base_url != None:
			base_url = urljoin(base_url, e_base_url.text.strip())
			root.remove(e_base_url)

		e_base_url = root.find('{}Location'.format(ns))
		if e_base_url != None:
			base_url = e_base_url.text.strip()
			root.remove(e_base_url)

		def search_drm_data(element):
			kid = None
			is_protected = False
			e = element.find('./{}ContentProtection[@schemeIdUri="urn:mpeg:dash:mp4protection:2011"]'.format(ns))
			if e != None:
				is_protected = True
				kid = e.get('{urn:mpeg:cenc:2013}default_KID') or e.get('default_KID')
				if kid:
					self.cp.log_debug("Found KID: %s" % kid)
					kid = kid.replace('-', '').lower()

			e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e == None:
				e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e != None and e.text:
				self.cp.log_debug("Found WV PSSH: %s" % e.text)
				pssh_list['wv'].append(e.text.strip())
			elif is_protected:
				self.cp.log_debug("Content is DRM protected, but no default WV PSSH is set - adding dummy one")
				# add dummy PSSH - this is needed to enable DRM proxy handler
				# this dummy pssh will be skipped by WV keys receiver
				pssh_list['wv'].append('dynamic')

			e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e == None:
				e = element.find('./%sContentProtection[@schemeIdUri="urn:uuid:9A04F079-9840-4286-AB92-E65BE0885F95"]/{urn:mpeg:cenc:2013}pssh' % ns)
			if e != None and e.text:
				self.cp.log_debug("Found PR PSSH: %s" % e.text)
				pssh_list['pr'].append(e.text.strip())
			elif is_protected:
				self.cp.log_debug("Content is DRM protected, but no default PR PSSH is set - adding dummy one")
				# add dummy PSSH - this is needed to enable DRM proxy handler
				# this dummy pssh will be skipped by PR keys receiver
				pssh_list['pr'].append('dynamic')

			return kid

		def patch_segment_url(element):
			if dash_proxy_segments or (dash_internal_decrypt and drm):
				ck = self.calc_cache_key(element.get('id'))
				i = 0
				e_base_url = element.find('{}BaseURL'.format(ns))
				if e_base_url != None:
					element.remove(e_base_url)
					e_base_url = e_base_url.text.strip()
				else:
					e_base_url = ''

				for e_segment_template in element.findall('{}SegmentTemplate'.format(ns)):
					v = e_segment_template.get('initialization')
					if v:
						e_segment_template.set('initialization', 'i%s%d/%s' % (ck, i, urljoin(e_base_url, v.replace('../', 'dot-dot-slash'))))

					v = e_segment_template.get('media')
					if v:
						e_segment_template.set('media', 'm%s%d/%s' % (ck, i, urljoin(e_base_url, v.replace('../', 'dot-dot-slash'))))
					i += 1

		def remove_content_protection(element):
			for e in element.findall('{}ContentProtection'.format(ns)):
				element.remove(e)

		have_default_kid = False

		# search for DRM data first
		for e_period in root.findall('{}Period'.format(ns)):
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				a_kid = search_drm_data(e_adaptation_set)
				for e in e_adaptation_set.findall('{}Representation'.format(ns)):
					r_kid = search_drm_data(e) or a_kid
					kid_rep_mapping[e.get('id')] = {
						'kid': r_kid
					}

					if r_kid:
						have_default_kid = True

		# cleanup duplicate PSSH entries
		pssh_list['wv'] = list(set(pssh_list['wv']))
		pssh_list['pr'] = list(set(pssh_list['pr']))

		# request and preprocess CENC keys
		keys = self.get_drm_keys(pssh_list, drm)
		kid_key_mapping = {}
		for k in keys:
			kid, key = k.split(':')
			if key != '00000000000000000000000000000000':
				kid_key_mapping[kid] = key

		# search add info to representations, if they are decryptable
		for rep_info in kid_rep_mapping.values():
			if not rep_info['kid']:
				# representation is probably not encrypted
				rep_info['decryptable'] = True
				rep_info['key'] = None
			elif rep_info['kid'] in kid_key_mapping:
				# we have key for this representation
				rep_info['decryptable'] = True
				rep_info['key'] = kid_key_mapping[rep_info['kid']]
			else:
				# we don't have key for this representation - mark as not decryptable
				rep_info['decryptable'] = False

		# search for all representations and remove all undecryptable
		for e_period in root.findall('{}Period'.format(ns)):
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				for e_rep in e_adaptation_set.findall('{}Representation'.format(ns)):
					if kid_rep_mapping[e_rep.get('id')]['decryptable'] == False:
						e_adaptation_set.remove(e_rep)

		# remove empty AdaptationSets
		for e_period in root.findall('{}Period'.format(ns)):
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if len(e_adaptation_set.findall('{}Representation'.format(ns))) == 0:
					e_period.remove(e_adaptation_set)

		# remove empty Periods
		for e_period in root.findall('{}Period'.format(ns)):
			if len(e_period.findall('{}AdaptationSet'.format(ns))) == 0:
				root.remove(e_period)

		# remove all content protection elements - we have enough data for player to play this content
		for e_period in root.findall('{}Period'.format(ns)):
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				remove_content_protection(e_adaptation_set)
				for e in e_adaptation_set.findall('{}Representation'.format(ns)):
					remove_content_protection(e)

		# modify MPD manifest and make it as best playable on enigma2 as possible
		for e_period in root.findall('{}Period'.format(ns)):
			audio_list = []
			other_list = []

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

				elif e_adaptation_set.get('contentType','') == 'audio' or e_adaptation_set.get('mimeType','').startswith('audio/'):
					audio_list.append(e_adaptation_set)

				elif e_adaptation_set.get('contentType','') == 'text' or e_adaptation_set.get('mimeType','').startswith('text/'):
					# subtitles
					pass
				else:
					# add everything else to others
					other_list.append(e_adaptation_set)

				# for DRM protected content we need to add distinguish between init and data segment, so set prefix for it
				patch_segment_url(e_adaptation_set)
				for e in e_adaptation_set.findall('{}Representation'.format(ns)):
					patch_segment_url(e)
					cenc_key = kid_rep_mapping[e.get('id')]['key']
					if cenc_key and dash_internal_decrypt != True:
						self.cp.log_debug("Setting CENC key %s for representation %s" % (cenc_key, e.get('id')))
						e.set('cenc_decryption_key', cenc_key)

			# remove all adaptation sets except audio, video and subtitles
			for a in other_list:
				e_period.remove(a)

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

			if e_base_url != None:
				base_url_set = urljoin(base_url, e_base_url.text)

				if dash_proxy_segments or (dash_internal_decrypt and drm):
					base_url_set = self.dash_proxify_base_url(base_url_set, pssh_list=pssh_list, default_kid=have_default_kid, drm=drm, cache_key=cache_key, dash_internal_decrypt=dash_internal_decrypt)

				e_base_url.text = base_url_set
			else:
				# base path not found in MPD, so set it ...
				if dash_proxy_segments or (dash_internal_decrypt and drm):
					base_url_set = self.dash_proxify_base_url(base_url, pssh_list=pssh_list, default_kid=have_default_kid, drm=drm, cache_key=cache_key, dash_internal_decrypt=dash_internal_decrypt)
				else:
					base_url_set = base_url

				be = ET.Element('BaseURL')
				be.text = base_url_set
				e_period.insert(0, be)
#				ET.SubElement(e_period, 'BaseURL').text = base_url_set


	# #################################################################################################

	def get_dash_playlist_data(self, dash_info):
		'''
		Processes DASH playlist from given url and returns new one with only one video adaptive specified by bandwidth (or with best bandwidth if no bandwidth is given)
		'''
		try:
			response = self.req_session.get(dash_info['url'], headers=dash_info.get('headers'))
			response.raise_for_status()
		except:
			self.cp.log_error('Failed to retrieve DASH playlist data from %s\n%s' % (dash_info['url'], str(response)))
			return None

#		self.log_devel("MPD response received: %s" % response)

		bandwidth = dash_info.get('bandwidth')
		if bandwidth == None:
			bandwidth = 1000000000
		else:
			bandwidth = int(bandwidth)

		redirect_url = response.url
#		self.log_devel("Playlist URL after redirect: %s" % redirect_url)
		cache_key = self.calc_cache_key(redirect_url)

#		self.log_devel("Cache key: %s" % cache_key)
		redirect_url = urljoin(redirect_url, 'X')[:-1]

		response_data = response.text
#		self.log_devel("Received MPD:\n%s" % response_data)

		root = ET.fromstring(response_data)
		self.handle_mpd_manifest(redirect_url, root, bandwidth, dash_info, cache_key)
		return ET.tostring(root, encoding='utf8', method='xml')

	# #################################################################################################
