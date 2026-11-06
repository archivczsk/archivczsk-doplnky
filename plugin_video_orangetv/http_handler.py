# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from tools_archivczsk.date_utils import iso8601_duration_to_seconds, iso8601_to_datetime

# #################################################################################################

class OrangeTVHTTPRequestHandler(PlayliveTVHTTPRequestHandler, HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(OrangeTVHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = True
		self.dash_proxy_segments = False
		self.enable_hls_multiaudio = property(lambda self: self.cp.get_setting('hls_multiaudio') == True)

	def process_variant_playlist(self, playlist_url, playlist_data, hls_info={}):
		playlist_data = super(OrangeTVHTTPRequestHandler, self).process_variant_playlist(playlist_url, playlist_data, hls_info)

		if hls_info.get('startover') == True:
			self.cp.log_debug("Startover is set - setting playlist type to EVENT")
			playlist_data = playlist_data.replace('#EXTM3U\n', '#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n')
		else:
			self.cp.log_debug("Startover is not set")

		return playlist_data

# #################################################################################################

	def fix_startover(self, root):
		root.set('startover', '1')

		if not root.get('timeShiftBufferDepth'):
			# buffer depth is required for startover to work - create new one by substracting availabilityStartTime and publishTime
			try:
				availability_start_time = iso8601_to_datetime(root.get('availabilityStartTime'))
				publish_time = iso8601_to_datetime(root.get('publishTime'))
				if availability_start_time and publish_time:
					buffer_depth = (publish_time - availability_start_time).total_seconds()
					root.set('timeShiftBufferDepth', 'PT{}S'.format(int(buffer_depth)))
			except:
				self.cp.log_exception()

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		super(OrangeTVHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		if dash_info.get('startover'):
			self.fix_startover(root)

		# remove STPP TTML subtitles - they are not supported and they cause problems by playback
		ns = root.tag[1:root.tag.index('}')]
		ns = '{%s}' % ns
		for e_period in root.findall('{}Period'.format(ns)):
			e_adaptation_list = []
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if e_adaptation_set.get('contentType','') == 'text' and e_adaptation_set.get('mimeType', '') == 'application/mp4':
					e_adaptation_list.append(e_adaptation_set)

			for e in e_adaptation_list:
				e_period.remove(e)


	# #################################################################################################
