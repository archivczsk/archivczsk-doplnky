# -*- coding: utf-8 -*-

import traceback
import base64
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler, stream_key_to_dash_url
from tools_archivczsk.date_utils import iso8601_duration_to_seconds
import json

from time import time
import xml.etree.ElementTree as ET
from Plugins.Extensions.archivCZSK.gsession import GlobalSession
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Screens.ChoiceBox import ChoiceBox
from enigma import eServiceReference

PLAYER_MAPPING = {
	"1": 5001, # gstplayer,
	"2": 5002, # exteplayer3
	"3": 8193, # DMM
	"4": 1,    # DVB service (OE >=2.5)
}

# #################################################################################################

class O2HTTPRequestHandler(DashHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		DashHTTPRequestHandler.__init__(self, content_provider, addon, proxy_segments=False)
		self.live_cache = {}
		self.o2_session = self.cp.get_requests_session()
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
			index_url = None

			if key in self.live_cache and self.live_cache[key]['life'] > int(time()):
#				self.cp.log_debug("Returning result from cache" )
				index_url = self.live_cache[key]['index_url']
				self.live_cache[key]['life'] = int(time())+20
			else:
				channel = self.cp.channels_by_key.get(key)
				if channel and (channel['md_subchannel'] == False or self.cp.is_supporter()):
					index_url = self.cp.o2tv.get_live_link(channel_id)
					if index_url:
						while True:
							# follow redirects to get last URL and cache it
							response = self.o2_session.get(index_url, allow_redirects=False)
							if response.status_code > 300 and response.status_code < 310:
								index_url = response.headers['Location']
							else:
								break

					self.live_cache_cleanup()
					self.live_cache[key] = { 'life': int(time())+20, 'index_url': index_url }
		except:
			self.cp.log_error(traceback.format_exc())
			index_url = None

		return index_url

	# #################################################################################################

	def decode_channel_id(self, path):
		return base64.b64decode(path.encode('utf-8')).decode("utf-8")

	# #################################################################################################

	def encode_p_dash_key(self, stream_key):
		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		return base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')

	# #################################################################################################

	def show_md_menu(self, channel_id):
		channel = self.cp.channels_by_key.get(channel_id)
		if not channel:
			self.cp.log_error("Channel %s not found in channel list!" % channel_id)
			return

		if not channel['name'].strip().startswith('Oneplay'):
			# only Oneplay ... broadcasts MD at the moment ...
#			self.cp.log_debug("Channel %s doesn't broadcasts multidimension" % channel['name'])
			return

		epg_data = self.cp.o2tv.get_current_epg([channel['id']])
		mosaic_id = epg_data.get(channel['id'], {}).get('mosaic_id')

		if not mosaic_id:
			self.cp.log_debug("Channel %s doesn't broadcasts multidimension at the moment" % channel['name'])
			return

		mosaic_info = self.cp.o2tv.get_mosaic_info(mosaic_id, True).get('mosaic_info', [])

		if len(mosaic_info) < 2:
			return

		# And now some part, that is not programed very cleanly and it shouldn't be in addon at all (it interacts directly with enigma). But it is quick and hopefuly works ...
		# 1) get global session stored by archivczsk core
		# 2) show choicebox using this session to show menu with multidimension stream's choices
		# 3) process answer from user - get MD stream used by user and get real playable stream URL
		# 4) create service reference from service URL
		# 5) stop current playling service and run new one chosen by user

		session = GlobalSession.getSession()

		def md_continue(answer):
			if answer == None:
				return

			try:
				mi = mosaic_info[choicelist.index(answer)]
				streams = self.cp.get_dash_streams(self.cp.o2tv.get_live_link(mi['id']), self.cp.o2tv.req_session, max_bitrate=self.cp.get_setting('max_bitrate'))

				if not streams:
					return

				key = {
					'key': self.cp.scache.put(streams[0]['playlist_url']),
					'bandwidth': streams[0]['bandwidth'],
				}

				url = stream_key_to_dash_url(self.cp.http_endpoint, key)
				service_ref = eServiceReference(PLAYER_MAPPING.get(self.cp.get_setting('player_name'), 4097), 0, toString(url))
				service_ref.setName(toString(channel['name']))
				session.nav.stopService()
				session.nav.playService(service_ref)
			except:
				self.cp.log_exception()


		choicelist = [(toString(mi['title']),) for mi in mosaic_info]
		session.openWithCallback(md_continue, ChoiceBox, toString(self.cp._("Multidimension")), choicelist, skin_name="ArchivCZSKChoiceBox")

	# #################################################################################################

	def P_playlive(self, request, path):
		if path.endswith('/index.mpd'):
			path = path[:-10]

		channel_id = self.decode_channel_id(path)

#		self.cp.log_debug("%s resource ID: %s, path: %s" % (service_type, channel_id, path))

		max_bitrate = int(self.cp.get_setting('max_bitrate'))
		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 1000000000

		# get real mainfest url and forwad it to dash handler ...
		stream_info = {
			'url': self.get_stream_index_url(channel_id),
			'bandwidth': max_bitrate,
		}

		export_md_subchannels = self.cp.get_setting('export_md_subchannels') and self.cp.is_supporter()

		# if channels broatcasts MD, then show menu to select MD stream
		if export_md_subchannels == False and self.last_played_channel != channel_id and self.cp.get_setting('show_md_choice'):
			self.last_played_channel = channel_id
			self.show_md_menu(channel_id)

		return self.P_dash(request, self.encode_p_dash_key(stream_info))

	# #################################################################################################

	def default_handler(self, request, path_full ):
		data = "Default handler O2TV for path: %s" % path_full
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
		super(O2HTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		extra_cache_time = int(self.cp.get_setting('extra_cache_time'))
		if extra_cache_time > 0:
			self.fix_buffer_time(root, extra_cache_time * 2)

		fix = dash_info.get('fix')

		if fix == 'duration':
			self.fix_duration(root, dash_info.get('offset', 0))
		elif fix == 'startover':
			self.fix_startover(root)

	# #################################################################################################
