# -*- coding: utf-8 -*-

import time
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive
from tools_archivczsk.string_utils import _I, _C, _B
from .telly import Telly
from .bouquet import TellyBouquetXmlEpgGenerator
import base64

class TellyModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')
		cache_hours = int(self.cp.get_setting('epgcache'))
		enable_xmlepg = self.cp.get_setting('enable_xmlepg') and self.cp.get_setting('enable_userbouquet')

		# reload EPG cache if needed
		ret = self.cp.telly.load_epg_cache()

		# ret == True -> there already exist cache file
		if ret and enable_xmlepg:
			# if there exists already cache file and xmlepg is enabled, then cache file
			# is managed by bgservice, so disable epg refresh here
			cache_hours = 0

		self.cp.telly.fill_epg_cache([channel.epg_id for channel in self.cp.channels], cache_hours)
		self.cp.telly.save_epg_cache()

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue

			epg = self.cp.telly.get_channel_current_epg(channel.epg_id)

			if epg:
				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), epg["desc"]),
					'title': epg["title"],
					'img': epg['img'],
					'year': epg['year'],
					'rating': epg['rating'],
					'adult': channel.adult
				}
			else:
				epg_str = ''
				info_labels = {
					'adult': channel.adult
				}

			self.cp.add_video(channel.name + epg_str, img=channel.preview, info_labels=info_labels, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel.name, channel_url=channel.stream_url)

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_url):
		enable_download = self.cp.get_setting('download_live')
		for one in self.cp.telly.get_video_link(channel_url, self.cp.get_setting('enable_h265'), self.cp.get_setting('max_bitrate'), self.cp.get_setting('use_http_for_stream')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bitrate'],
				'vcodec': one['vcodec']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, download=enable_download)

# #################################################################################################


class TellyModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	# #################################################################################################

	def get_archive_channels(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue

			if channel.timeshift > 0:
				self.add_archive_channel(channel.name, (channel.id, channel.epg_id,), channel.timeshift, img=channel.picon, info_labels={'adult': channel.adult})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for epg in self.cp.telly.get_archiv_channel_programs(channel_id[1], ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), _I(epg["title"]))

			info_labels = {
				'plot': epg['desc'],
				'title': epg["title"],
				'year': epg['year'],
				'rating': epg['rating']
			}
			self.cp.add_video(title, epg['img'], info_labels, cmd=self.get_archive_stream, archive_title=str(epg["title"]), channel_id=channel_id[0], ts_from=epg['start'], ts_to=epg['end'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, channel_id, ts_from, ts_to):
		for one in self.cp.telly.get_archive_video_link(channel_id, ts_from, ts_to, self.cp.get_setting('enable_h265'), self.cp.get_setting('max_bitrate'), self.cp.get_setting('use_http_for_stream')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bitrate'],
				'vcodec': one['vcodec']
			}
			self.cp.add_play(archive_title, one['url'], info_labels)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_id.get(channel_id)
		return channel.timeshift if channel else None

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			channel_id = base64.b64decode(path[9:].encode('utf-8')).decode("utf-8")
			channel = self.cp.channels_by_id.get(int(channel_id))
			return int(channel_id) if channel.timeshift else None

		return None

# #################################################################################################


class TellyContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='Telly', settings=settings, data_dir=data_dir, bgservice=bgservice)

		self.telly = None
		self.channels = []
		self.channels_next_load_time = 0
		self.channels_by_id = {}
		self.checksum = None
		self.http_endpoint = http_endpoint

		self.bxeg = TellyBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			TellyModuleLiveTV(self),
			TellyModuleArchive(self),
		]

	# #################################################################################################

	def login(self, silent):
		self.telly = None
		self.channels = []
		self.channels_by_id = {}

		telly = Telly(self)

		if telly.token_is_valid() == False:
			if silent:
				return False
			else:
				# ask user to enter pairing code
				code = self.get_text_input(self._('Enter pairing code from site') + ' https://moje.telly.cz', input_type='number')
				if code:
					if not telly.get_device_token_by_code(code):
						self.login_error(self._('Device pairing with your Telly account failed.\nCheck pairing code validity and try again.'))
						return False
				else:
					return False

		self.telly = telly
		return True

	# #################################################################################################

	def get_channels_checksum(self):
		ctx = md5()
		for ch in self.channels:
			item = {
				'id': ch.id,
				'name': ch.name,
				'type': ch.type,
				'picon': ch.picon,
				'adult': ch.adult
			}
			ctx.update(str(frozenset(item)).encode('utf-8'))

		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.telly.get_channel_list()
		self.checksum = self.get_channels_checksum()

		self.channels_by_id = {}
		for ch in self.channels:
			self.channels_by_id[ch.id] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		self.load_channel_list()
		channel = self.channels_by_id.get(int(channel_key))

		if not channel:
			return None

		video_links = self.telly.get_video_link(channel.stream_url, self.get_setting('enable_h265'), self.get_setting('max_bitrate'), self.get_setting('use_http_for_stream'))

		if len(video_links) > 0:
			return video_links[0]['url']
		else:
			return None

	# #################################################################################################
