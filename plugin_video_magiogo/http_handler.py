# -*- coding: utf-8 -*-

import traceback
import base64
import re
from Plugins.Extensions.archivCZSK.version import version
from Plugins.Extensions.archivCZSK.engine.client import log
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from .magiogo import MagioGoCache
from time import time
import xml.etree.ElementTree as ET
import requests

# #################################################################################################

__scriptid__ = 'plugin.video.magiogo'
addon = ArchivCZSK.get_addon(__scriptid__)

# #################################################################################################

class MagioGoTvHTTPRequestHandler( AddonHttpRequestHandler ):
	def __init__(self):
		AddonHttpRequestHandler.__init__(self, __scriptid__)
		self.live_cache = {}
		self.magiogo_session = requests.session() 
	
	# #################################################################################################
	
	def get_stream_index_url(self, channel_id, service_type='LIVE' ):
		try:
			if channel_id in self.live_cache and self.live_cache[channel_id]['life'] > int(time()):
#				log.debug("Returning result from cache" )
				index_url = self.live_cache[channel_id]['index_url']
			else:
				device_type = int(addon.get_setting('devicetype'))
				region = addon.get_setting('region')

				username=addon.get_setting('username')
				password=addon.get_setting('password')
				device_id = addon.get_setting( 'deviceid' )
				data_dir=addon.get_info('profile')
				
				magiogo = MagioGoCache.get(region, username, password, device_id, device_type, data_dir, log.info )
				
				index_url = magiogo.get_stream_link(channel_id, service_type)
				self.live_cache[channel_id] = { 'life': int(time())+900, 'index_url': index_url }
		except:
			log.error(traceback.format_exc())
			index_url = None

		return index_url

	# #################################################################################################
	
	def get_best_stream_from_m3u8(self, m3u8_data ):
		result = []
		# EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2400000,CODECS="mp4a.40.2,avc1.64001f",RESOLUTION=1280x720,AUDIO="AACL"
		for m in re.finditer('#EXT-X-STREAM-INF:.*?BANDWIDTH=(?P<bandwidth>\d+),.*?\s(?P<chunklist>[^\s]+)', m3u8_data, re.DOTALL):
			bandwidth = int(m.group('bandwidth'))
			url = m.group('chunklist')
			result.append( (url, bandwidth ) )
		
		result.sort( key=lambda r: r[1], reverse=True )
		return result[0][0]

	# #################################################################################################
	
	def handle_m3u8_master_playlist(self, request, channel_id, index_url ):
		log.debug("Requesting channel id %s HLS master playlist: %s" % (channel_id, index_url) )
		response = self.magiogo_session.get( index_url )
	
		if response.status_code != 200:
			log.error("Server responsed with code %d for HLS master index request" % response.status_code )
			return self.reply_error404( request )

		# choose best quality stream and get variant playlist
		variant_url = self.get_best_stream_from_m3u8( response.text )

		redirect_url = response.url
		index_url = redirect_url[:redirect_url.rfind('/')] + '/' + variant_url

		self.live_cache[channel_id]['variant_url'] = index_url
		
		return self.reply_redirect( request, ('/%s/playlive/%s/index_cached.m3u8' % (self.name, base64.b64encode( channel_id.encode("utf-8") ).decode("utf-8"))).encode('utf-8'))
	
	# #################################################################################################
	
	def handle_m3u8_variant_playlist(self, request, channel_id ):
		index_url = self.live_cache.get(channel_id, {}).get('variant_url')
		
		if not index_url:
			log.error("No cached variant index url found for channel ID %s" % channel_id )
			return self.reply_error404( request )
		
		log.debug("Requesting channel id %s HLS variant playlist: %s" % (channel_id, index_url) )
		response = self.magiogo_session.get( index_url )

		if response.status_code != 200:
			log.error("Server responsed with code %d for HLS variant index request" % response.status_code )
			return self.reply_error404( request )

		redirect_url = response.url
		redirect_url = redirect_url[:redirect_url.rfind('/')] + '/'

		self.live_cache[channel_id]['base_url'] = redirect_url
		return self.reply_ok( request, response.content, content_type = response.headers.get('content-type'))
	
	# #################################################################################################

	def handle_mpd_manifest(self, request, channel_id, index_url ):
		log.debug("Requesting channel id %s MPD manifest: %s" % (channel_id, index_url) )
		
		response = self.magiogo_session.get( index_url )
	
		if response.status_code != 200:
			log.error("Server responsed with code %d for MPD index request" % response.status_code )
			return self.reply_error404( request )
		
		redirect_url = response.url
		redirect_url = redirect_url[:redirect_url.rfind('/')] + '/'
		
		root = ET.fromstring(response.text)
		
		# extract namespace of root element and set it as global namespace
		ET.register_namespace('', root.tag[1:root.tag.index('}')])
		
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
		
							# remove Representations with lower resolutions because some players play only first one (lowest) 
							for child2 in rep_childs[1:]:
								child.remove(child2)
		
		# build new XML and store base url for retrieving segment data
		mpd_data = ET.tostring(root, encoding='utf8', method='xml')
		self.live_cache[channel_id]['base_url'] = redirect_url
		
		return self.reply_ok( request, mpd_data, content_type = 'application/dash+xml')
		
	
	# #################################################################################################
	
	def handle_segment(self, request, channel_id, path ):
		base_url = self.live_cache[channel_id].get('base_url')
		
		if not base_url:
			log.error("Channel id %s found in cache - but no base url for segment is set" % channel_id )
			return self.reply_error500( request )
		
		log.debug('Requesting segment: %s' % base_url + path )
		response = self.magiogo_session.get( base_url + path )
#		log.info("Response code: %d, headers: %s" % (response.status_code, response.headers))
		
		return self.reply_ok( request, response.content, content_type = response.headers.get('content-type') )
		
	# #################################################################################################

	def P_playarchive(self, request, path):
		return self.P_playlive( request, path, 'ARCHIVE')

	# #################################################################################################
		
	def P_playlive(self, request, path, service_type='LIVE'):
		if b'/' not in path:
			return self.reply_error404( request )
		
		channel_id = path[:path.find(b'/')]
		channel_id = base64.b64decode(channel_id).decode("utf-8")
		path = path[path.find(b'/')+1:].decode("utf-8")

		log.debug("Playlive channel ID: %s, path: %s" % (channel_id, path) )
		
		if path == 'index':
			# handle playlist/index request
			index_url = self.get_stream_index_url(channel_id, service_type)
			
			if 'index.mpd' in index_url:
				if addon.get_setting('preprocess_mpd'):
					return self.handle_mpd_manifest( request, channel_id, index_url )
				else:
					return self.reply_redirect( request, index_url.encode('utf-8'))
			elif 'index.m3u8' in index_url:
				if addon.get_setting('preprocess_hls'):
					return self.handle_m3u8_master_playlist( request, channel_id, index_url )
				else:
					return self.reply_redirect( request, index_url.encode('utf-8'))
			else:
				log.error("Unsupported index url: %s" % index_url )
				
		elif path == 'index_cached.m3u8':
			return self.handle_m3u8_variant_playlist(request, channel_id )
		else:
			# handle segment request
			return self.handle_segment( request, channel_id, path )

		return self.reply_error404( request )
#		return self.reply_redirect( request, location.encode('utf-8'))
	
	# #################################################################################################
	
	def default_handler(self, request, path_full ):
		data = "Default handler pre Magio GO pre path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

		
#		request.write( data.encode('utf-8') )
#		request.finish()
#		return server.NOT_DONE_YET
#		return data.encode('utf-8')

