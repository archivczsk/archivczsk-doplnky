# -*- coding: utf-8 -*-

import traceback
import base64
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler

from time import time
import xml.etree.ElementTree as ET

try:
	from urlparse import urlparse
except:
	from urllib.parse import urlparse

# #################################################################################################


class MagioGOHTTPRequestHandler(HlsHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		HlsHTTPRequestHandler.__init__(self, content_provider, addon, True)
		self.cp = content_provider
		self.live_cache = {}
	
	# #################################################################################################

	def get_hls_info(self, stream_key):
		'''
		Override implementation from HlsHTTPRequestHandler, because we want to call method P_hls directly from P_playlive handler and not from HTTP request
		'''
		return {
			'url': stream_key,
			'bandwidth': self.get_max_bitrate(),
			'headers': {
				'User-Agent': 'com.telekom.magiogo/%s (Linux;Android 6.0) ExoPlayerLib/2.18.1' % self.cp.magiogo.app_version
			}
		}
	
	# #################################################################################################

	def decode_stream_key(self, path):
		'''
		Override implementation from HlsHTTPRequestHandler, because we want to call method P_hls directly from P_playlive handler and not from HTTP request
		'''
		return path

	# #################################################################################################

	def get_stream_index_url(self, channel_id, service_type='LIVE', prof='p3' ):
		try:
			if channel_id in self.live_cache and self.live_cache[channel_id]['life'] > int(time()) and self.live_cache[channel_id]['p'] == prof:
#				self.cp.log_debug("Returning result from cache" )
				index_url = self.live_cache[channel_id]['index_url']
			else:
				index_url = self.cp.magiogo.get_stream_link(channel_id, service_type, prof)
				self.live_cache[channel_id] = { 'life': int(time())+60, 'index_url': index_url, 'p': prof }
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

	def handle_mpd_manifest(self, request, channel_id, index_url ):
		self.cp.log_debug("Requesting channel id %s MPD manifest: %s" % (channel_id, index_url))

		def p_continue(response, channel_id):
			if response['status_code'] != 200:
				self.cp.log_error("Server responsed with code %d for MPD index request" % response['status_code'])
				return self.reply_error404( request )
			
			redirect_url = response['url']
			redirect_url = redirect_url[:redirect_url.rfind('/')] + '/'
			
			root = ET.fromstring(response['content'].decode('utf-8'))
			
			# extract namespace of root element and set it as global namespace
			ET.register_namespace('', root.tag[1:root.tag.index('}')])
			max_bitrate = self.get_max_bitrate()
			
			# search for video representations and keep only highest resolution/bandwidth
			for root_child in root:
				if 'Period' in root_child.tag:
					for child in root_child:
						if 'AdaptationSet' in child.tag:
							if child.attrib.get('contentType','') == 'video':
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
			
			# build new XML and store base url for retrieving segment data
			mpd_data = ET.tostring(root, encoding='utf8', method='xml')
			self.live_cache[channel_id]['base_url'] = redirect_url
			request.setResponseCode(200)
			request.setHeader('content-type', "application/dash+xml")
			request.write(mpd_data)
			request.finish()
			return

		
		self.request_http_data_async_simple(index_url, cbk=p_continue, channel_id=channel_id)
		return self.NOT_DONE_YET
		
	
	# #################################################################################################
	
	def handle_segment(self, request, channel_id, path ):
		base_url = self.live_cache[channel_id].get('base_url')
		
		if not base_url:
			self.cp.log_error("Channel id %s found in cache - but no base url for segment is set" % channel_id)
			return self.reply_error500( request )
		
		url = base_url + path
		return self.P_s(request, base64.b64encode(url.encode('utf-8')).decode('utf-8'))

	# #################################################################################################

	def P_playarchive(self, request, path):
		return self.P_playlive( request, path, 'ARCHIVE')

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

		self.cp.log_debug("Playlive channel ID: %s, path: %s" % (channel_id, path))

		default_prof = 'p' + self.cp.get_setting('stream_profile')

		prof = request.args.get('p',[default_prof])[0]
		
		if path in ('index', 'index.m3u8', 'index.mpd'):
			# handle playlist/index request
			index_url = self.get_stream_index_url(channel_id, service_type, prof)
			index_path = urlparse(index_url).path

			if index_path.endswith('.mpd') or 'index.mpd' in index_url:
				return self.handle_mpd_manifest( request, channel_id, index_url )
			elif index_path.endswith('.m3u8') or 'index.m3u8' in index_url:
				return self.P_hls(request, index_url)
			else:
				self.cp.log_error("Unsupported index url: %s" % index_url)
				
		else:
			# handle segment request
			return self.handle_segment( request, channel_id, path )

		return self.reply_error404( request )
	
	# #################################################################################################
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre Magio GO pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")
