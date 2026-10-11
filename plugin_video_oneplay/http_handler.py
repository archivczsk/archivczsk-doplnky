# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.playlive import PlayliveTVHTTPRequestHandler
from tools_archivczsk.date_utils import iso8601_duration_to_seconds, iso8601_to_datetime

from Plugins.Extensions.archivCZSK.gsession import GlobalSession
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Screens.ChoiceBox import ChoiceBox
from Plugins.Extensions.archivCZSK.client.shortcut import run_shortcut

# #################################################################################################

class OneplayHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler, PlayliveTVHTTPRequestHandler):
	def __init__(self, content_provider, addon):
		super(OneplayHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.enable_hls_multiaudio = False
		self.dash_proxy_segments = False
		self.cache_life = 10
		self.last_played_channel = None

	# #################################################################################################

	def show_md_menu(self, md):
		session = GlobalSession.getSession()

		def md_continue(answer):
			if answer == None:
				return

			try:
				run_shortcut(session, None, 'oneplay-md', {'md': md, 'play_idx': choicelist.index(answer) }, True)
			except:
				self.cp.log_exception()

		choicelist = [(toString(mi['title']),) for mi in md]
		session.openWithCallback(md_continue, ChoiceBox, toString(self.cp._("Multidimension - select stream")), choicelist, skin_name="ArchivCZSKChoiceBox")

	# #################################################################################################

	def P_playlive(self, request, path):
		if path.endswith('/index.mpd'):
			path = path[:-10]
		elif path.endswith('/index.m3u8'):
			path = path[:-11]

		channel_key = self.decode_channel_key(path)

		result = self.live_cache_get(channel_key)
		if not result:
			self.cp.log_debug("Adding channel to cache: %s" % channel_key)
			result = self.get_url_by_channel_key(channel_key)

			if not result.get('url'):
				return self.reply_error404(request)

			self.live_cache_put(channel_key, result)

		if result.get('md') and self.last_played_channel != channel_key and self.cp.get_setting('show_md_choice'):
			self.run_in_reactor(self.show_md_menu, result['md'])

		self.last_played_channel = channel_key

		return self.reply_redirect(request, result['url'])

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
