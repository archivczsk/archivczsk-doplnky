# -*- coding: utf-8 -*-

import traceback
import base64
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler, HlsMasterProcessor
from tools_archivczsk.date_utils import iso8601_duration_to_seconds
import json

from time import time

from Plugins.Extensions.archivCZSK.gsession import GlobalSession
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Screens.ChoiceBox import ChoiceBox
from Plugins.Extensions.archivCZSK.client.shortcut import run_shortcut

# #################################################################################################

class OneplayHlsMasterProcessor(HlsMasterProcessor):
	def cleanup_master_playlist(self):
		super(OneplayHlsMasterProcessor, self).cleanup_master_playlist()

		external_audio_cnt = 0
		internal_audio_cnt = 0

		for p in self.audio_playlists:
			if p.playlist_url:
				external_audio_cnt += 1
			else:
				internal_audio_cnt += 1


		if external_audio_cnt > 0 and internal_audio_cnt > 0:
			# exteplayer3 has problems playing HLS when there is a mix of audio tracks with external URI and internal (embedded to video track - without URI in playlist)
			# only external audio is played and switching to internal one doesn't work
			# workaround to play embedded audio is to remove all external tracks

			playlists = []
			for p in self.audio_playlists:
				if not p.playlist_url:
					playlists.append(p)

			self.audio_playlists = playlists

# #################################################################################################

class OneplayHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		super(OneplayHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.hls_master_processor = OneplayHlsMasterProcessor

		self.live_cache = {}
		self.oneplay_session = self.cp.get_requests_session()
		self.last_played_channel = None

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

	def get_stream_index_url(self, channel_id):
		try:
			key = channel_id
			stream_info = {}

			if key in self.live_cache and self.live_cache[key]['life'] > int(time()):
#				self.cp.log_debug("Returning result from cache" )
				stream_info = self.live_cache[key]['stream_info']
				self.live_cache[key]['life'] = int(time())+20
			else:
				channel = self.cp.channels_by_key.get(key)
				if channel:
					stream_info = self.cp.oneplay.get_live_link(channel_id)
					if stream_info:
						while True:
							# follow redirects to get last URL and cache it
							response = self.oneplay_session.get(stream_info['url'], allow_redirects=False)
							if response.status_code > 300 and response.status_code < 310:
								stream_info['url'] = response.headers['Location']
							else:
								break

					self.live_cache_cleanup()
					self.live_cache[key] = { 'life': int(time())+20, 'stream_info': stream_info }
		except:
			self.cp.log_error(traceback.format_exc())
			stream_info = None

		return stream_info

	# #################################################################################################

	def decode_channel_id(self, path):
		return base64.b64decode(path.encode('utf-8')).decode("utf-8")

	# #################################################################################################

	def encode_p_dash_key(self, stream_key):
		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		return base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def show_md_menu(self, stream_info):
		session = GlobalSession.getSession()

		def md_continue(answer):
			if answer == None:
				return

			try:
				run_shortcut(session, None, 'oneplay-md', {'stream_info': stream_info, 'play_idx': choicelist.index(answer) }, True)
			except:
				self.cp.log_exception()

		choicelist = [(toString(mi['title']),) for mi in stream_info['md']]
		session.openWithCallback(md_continue, ChoiceBox, toString(self.cp._("Multidimension - select stream")), choicelist, skin_name="ArchivCZSKChoiceBox")

	# #################################################################################################

	def P_playlive(self, request, path):
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index.m3u8'):
			path = path[:-11]

		channel_id = self.decode_channel_id(path)

#		self.cp.log_debug("%s resource ID: %s, path: %s" % (service_type, channel_id, path))

		max_bitrate = int(self.cp.get_setting('max_bitrate'))
		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 1000000000

		# get real mainfest url and forwad it to dash handler ...
		stream_index_info = self.get_stream_index_url(channel_id)

		stream_info = {
			'url': stream_index_info['url'],
			'bandwidth': max_bitrate,
		}

		drm_info = stream_index_info.get('drm', {})
		if drm_info.get('licence_url') and drm_info.get('licence_key'):
			stream_info.update({
				'drm' : {
					'licence_url': drm_info['licence_url'],
					'headers': {
						'X-AxDRM-Message': drm_info['licence_key']
					}
				}
			})

		# if channels broatcasts MD, then show menu to select MD stream
		if 'md' in stream_index_info and self.last_played_channel != channel_id and self.cp.get_setting('show_md_choice'):
			self.show_md_menu(stream_index_info)

		self.last_played_channel = channel_id

		if stream_index_info['type'] == 'dash':
			return self.P_dash(request, self.encode_p_dash_key(stream_info))
		else:
			return self.P_hls(request, self.encode_p_dash_key(stream_info))

	# #################################################################################################

	def default_handler(self, request, path_full ):
		data = "Default Oneplay handler for path: %s" % path_full
		return self.reply_ok( request, data.encode('utf-8'), "text/plain; charset=UTF-8")

	# #################################################################################################

	def fix_duration(self, root, offset=0):
		if offset == 0:
			return

		duration = iso8601_duration_to_seconds(root.get('mediaPresentationDuration'))
		if duration != None:
			duration += offset
			duration_str = 'PT%dH%dM%dS' % ((duration // 3600), (duration //60) % 60, duration % 60)
			root.set('mediaPresentationDuration', duration_str)

			ns = root.tag[1:root.tag.index('}')]
			ns = '{%s}' % ns

			for e_period in root.findall('{}Period'.format(ns)):
				e_period.set('duration', duration_str)
				for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
					for e in e_adaptation_set.findall('{}SegmentTemplate'.format(ns)):
						timescale = int(e.get('timescale'))
						for st in e.findall('{}SegmentTimeline'.format(ns)):
							for s in st.findall('{}S'.format(ns)):
								try:
									t = int(s.get('t', 0))
									d = int(s.get('d'))
									r = int(s.get('r', 1))

									if t and r > 1:
										new_t = t + (d * r) + (timescale * offset)

										if offset > 0:
											while (t + (d * r)) < new_t:
												r += 1
										else:
											while (t + (d * r)) > new_t and r > 1:
												r -= 1

										s.set('r', str(r))
								except:
									self.cp.log_exception()

	# #################################################################################################

	def fix_startover(self, root):
		root.set('startover', '1')

	# #################################################################################################

	def fix_buffer_time(self, root, extra_cache_time):
		if root.get('type') == 'dynamic':
			buffer_time = iso8601_duration_to_seconds(root.get('minBufferTime'))

			if buffer_time and buffer_time < 40:
				root.set('minBufferTime', 'PT{}S'.format(buffer_time + extra_cache_time))

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		super(OneplayHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		extra_cache_time = int(self.cp.get_setting('extra_cache_time'))
		if extra_cache_time > 0:
			self.fix_buffer_time(root, extra_cache_time * 2)

		fix = dash_info.get('fix')

		if fix == 'duration':
			self.fix_duration(root, dash_info.get('offset', 0))
		elif fix == 'startover':
			self.fix_startover(root)

	# #################################################################################################
