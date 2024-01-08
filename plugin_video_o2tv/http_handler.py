# -*- coding: utf-8 -*-

import traceback
import base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from time import time
import xml.etree.ElementTree as ET

# #################################################################################################


class O2HTTPRequestHandler(AddonHttpRequestHandler):
	def __init__(self, content_provider, addon):
		AddonHttpRequestHandler.__init__(self, addon)
		self.cp = content_provider
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

	def get_cache_key(self, service_type, channel_id):
		return '%s_%s' % (service_type, channel_id)

	# #################################################################################################

	def get_stream_index_url(self, channel_id, service_type='LIVE' ):
		try:
			key = self.get_cache_key(service_type, channel_id)

			if key in self.live_cache and self.live_cache[key]['life'] > int(time()):
#				self.cp.log_debug("Returning result from cache" )
				index_url = self.live_cache[key]['index_url']
				self.live_cache[key]['life'] = int(time())+60
			else:
				if service_type == 'LIVE':
					index_url = self.cp.o2tv.get_live_link(channel_id)
				elif service_type == 'ARCHIVE':
					index_url = self.cp.o2tv.get_archive_link(channel_id)
				elif service_type == 'STARTOVER':
					index_url = self.cp.o2tv.get_startover_link(channel_id)
				elif service_type == 'REC':
					index_url = self.cp.o2tv.get_recording_link(channel_id)

				self.live_cache_cleanup()
				self.live_cache[key] = { 'life': int(time())+60, 'index_url': index_url }
		except:
			self.cp.log_error(traceback.format_exc())
			index_url = None

		return index_url

	# #################################################################################################

	def get_max_bitrate(self):
		max_bitrate = self.cp.get_setting('max_bitrate')
		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

		return max_bitrate

	# #################################################################################################

	def handle_mpd_manifest(self, request, channel_id, service_type, index_url ):
#		self.cp.log_debug("Requesting resource id %s:%s MPD manifest: %s" % (service_type, channel_id, index_url))

		key = self.get_cache_key(service_type, channel_id)

		response = self.o2_session.get( index_url )

		if response.status_code != 200:
			self.cp.log_error("Server responsed with code %d for MPD index request" % response.status_code)
			del self.live_cache[key]
			return self.reply_error404( request )

		redirect_url = response.url
		redirect_url = redirect_url[:redirect_url.rfind('/')] + '/'

		root = ET.fromstring(response.text)

		# extract namespace of root element and set it as global namespace
		ET.register_namespace('', root.tag[1:root.tag.index('}')])
		max_bitrate = self.get_max_bitrate()

		# modify MPD manifest and make it as best playable on enigma2 as possible
		for root_child in root:
			if 'Period' in root_child.tag:
				base_path_set = False
				audio_list = []

				for child in root_child:
					if 'BaseURL' in child.tag:
						# modify base url for segments to correct one
						child.text = redirect_url + child.text
						base_path_set = True

					if 'AdaptationSet' in child.tag:
						if child.attrib.get('contentType','') == 'video':
							# search for video representations and keep only highest resolution/bandwidth
							rep_childs = []
							for child2 in child:
								if 'Representation' in child2.tag:
									rep_childs.append( child2 )

							rep_childs.sort(key=lambda x: int(x.get('bandwidth',0)), reverse=True)

							# remove Representations with higher bitrate then max_bitrate
							for child2 in rep_childs:
								if int(child2.get('bandwidth', 0)) > max_bitrate:
									child.remove(child2)
								else:
									break

							# remove Representations with lower resolutions because some players play only first one (lowest)
							for child2 in rep_childs[1:]:
								child.remove(child2)

						if child.attrib.get('contentType','') == 'audio':
							audio_list.append(child)

				if len(audio_list) > 0:
					# all enigma2 players use first audio track as the default, so move CZ and SK audio tracks on the top

					# remove all audio AdaptationSets
					for a in audio_list:
						root_child.remove(a)

					# sort audio AdaptationSets by language - cz and sk tracks first ...
					audio_list.sort(key=lambda a: a.get('lang','').lower() in ('cs', 'sk', 'ces', 'cze', 'slo', 'slk'), reverse=True)

					# add it back to Period element
					for a in audio_list:
						root_child.append(a)


				if not base_path_set:
					# base path not found in MPD, so set it ...
					child = ET.SubElement(root_child, 'BaseURL')
					child.text = redirect_url


		# build new XML and store base url for retrieving segment data
		mpd_data = ET.tostring(root, encoding='utf8', method='xml')

		self.live_cache[key].update({
			'base_url' :redirect_url,
			'index_url': response.url
		})

		return self.reply_ok( request, mpd_data, content_type = 'application/dash+xml')

	# #################################################################################################

	def handle_segment(self, request, channel_id, service_type, path ):
		key = '%s_%s' % (service_type, channel_id)
		base_url = self.live_cache.get(key, {}).get('base_url')

		if not base_url:
			self.cp.log_error("Channel id %s found in cache - but no base url for segment is set" % channel_id)
			return self.reply_error500( request )

		self.cp.log_debug('Requesting segment: %s' % base_url + path)
		response = self.o2_session.get( base_url + path )
#		self.cp.log_info("Response code: %d, headers: %s" % (response.status_code, response.headers))

		return self.reply_ok( request, response.content, content_type = response.headers.get('content-type') )

	# #################################################################################################

	def P_playstartover(self, request, path):
		return self.P_playlive( request, path, 'STARTOVER')

	# #################################################################################################

	def P_playarchive(self, request, path):
		return self.P_playlive( request, path, 'ARCHIVE')

	# #################################################################################################

	def P_playrec(self, request, path):
		return self.P_playlive( request, path, 'REC')

	# #################################################################################################

	def decode_channel_id(self, path):
		return base64.b64decode(path.encode('utf-8')).decode("utf-8")

	# #################################################################################################

	def P_playlive(self, request, path, service_type='LIVE'):
		if '/' not in path:
			return self.reply_error404( request )

		channel_id = path[:path.find('/')]
		channel_id = self.decode_channel_id(channel_id)
		path = path[path.find('/') + 1:]

#		self.cp.log_debug("%s resource ID: %s, path: %s" % (service_type, channel_id, path))

		if path == 'index.mpd':
			# handle playlist/index request
			index_url = self.get_stream_index_url(channel_id, service_type)

			if self.cp.get_setting('preprocess_mpd'):
				return self.handle_mpd_manifest( request, channel_id, service_type, index_url )
			else:
				return self.reply_redirect( request, index_url.encode('utf-8'))

		else:
			# handle segment request
			return self.handle_segment( request, channel_id, service_type, path )

		return self.reply_error404( request )
#		return self.reply_redirect( request, location.encode('utf-8'))

	# #################################################################################################

	def default_handler(self, request, path_full ):
		data = "Default handler O2TV for path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")


#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')
