# -*- coding: utf-8 -*-

import time
import json
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .orangetv import OrangeTV
from .bouquet import OrangeTVBouquetXmlEpgGenerator
import base64


class OrangeTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()

		show_epg = self.cp.get_setting('showliveepg')
		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')
		cache_hours = int(self.cp.get_setting('epgcache'))
		enable_xmlepg = self.cp.get_setting('enable_xmlepg') and self.cp.get_setting('enable_userbouquet')

		if show_epg:
			# reload EPG cache if needed
			ret = self.cp.orangetv.loadEpgCache()

			# ret == True -> there already exist cache file
			if ret and enable_xmlepg:
				# if there exists already cache file and xmlepg is enabled, then cache file
				# is managed by bgservice, so disable epg refresh here
				cache_hours = 0

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			if show_epg:
				epg = self.cp.orangetv.getChannelCurrentEpg(channel['key'], cache_hours)
			else:
				epg = None

			if epg:
				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot':epg['desc'],
					'title': epg["title"],
					'img': epg['img'],
					'adult': channel['adult']
				}
			else:
				epg_str = ''
				info_labels = {
					'adult': channel['adult']
				}

			self.cp.add_video(channel['name'] + epg_str, img=channel['snapshot'], info_labels=info_labels, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'])

		self.cp.orangetv.saveEpgCache()

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key):
		enable_download = self.cp.get_setting('download_live')
		playlist = self.cp.orangetv.get_live_link(channel_key)
		self.cp.resolve_hls_streams(channel_title, playlist, download=self.cp.get_setting('download_live'))

# #################################################################################################

class OrangeTVModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	# #################################################################################################

	def get_archive_channels(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			if channel['timeshift'] > 0:
				self.add_archive_channel(channel['name'], channel['key'], channel['timeshift'], img=channel['logo'], info_labels={'adult': channel['adult']})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for epg in self.cp.orangetv.getArchivChannelPrograms(channel_id, ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["stop"]), _I(epg["title"]))

			info_labels = {
				'plot': epg['plot'],
				'title': epg["title"]
			}
			self.cp.add_video(title, epg['img'], info_labels, cmd=self.get_archive_stream, archive_title=str(epg["title"]), channel_key=channel_id, epg_id=epg['epg_id'], ts_from=epg['start'], ts_to=epg['stop'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, channel_key, epg_id, ts_from, ts_to):
		playlist = self.cp.orangetv.get_archive_link(channel_key, epg_id, ts_from, ts_to)
		self.cp.resolve_hls_streams(archive_title, playlist)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_key.get(channel_id)
		return channel['timeshift'] if channel else None

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			channel_id = base64.b64decode(path[9:].encode('utf-8')).decode("utf-8")
			channel = self.cp.channels_by_key.get(channel_id, {})
			return channel_id if channel.get('timeshift') else None

		return None

	# #################################################################################################

	def get_channel_id_from_sref(self, sref):
		name = channel_name_normalise(sref.getServiceName())
		channel = self.cp.channels_by_norm_name.get(name, {})

		return channel.get('key') if channel.get('timeshift') else None

# #################################################################################################


class OrangeTVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Special section"))

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self, section=None):
		info_labels = {'plot': self._("Here you can show and optionaly remove/unregister unneeded devices, so you can login on another one.") }
		self.cp.add_dir(self._('Registered devices'), info_labels=info_labels, cmd=self.list_devices)
		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def list_devices(self):
		self.cp.orangetv.refresh_configuration(True)

		for pdev in self.cp.orangetv.devices:
			title = pdev["deviceName"] + " - " + self.cp.timestamp_to_str(pdev["lastLoginTimestamp"] / 1000, format='%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + pdev["deviceId"]
			info_labels = { 'plot': self._('In menu you can remove device using Remove device!')}

			menu = {}
			self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_id=pdev["deviceId"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_id):
		self.cp.orangetv.device_remove(device_id)
		self.cp.add_video(_C('red', self._('Device {device} was removed!').format(device=device_id)), download=False)

# #################################################################################################

class OrangeTVContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, http_endpoint_rel, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='OrangeTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'deviceid')

		self.orangetv = None
		self.channels = []
		self.channels_next_load_time = 0
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.checksum = None
		self.http_endpoint = http_endpoint
		self.http_endpoint_rel = http_endpoint_rel

		if not self.get_setting('deviceid'):
			self.set_setting('deviceid', OrangeTV.create_device_id())

		self.bxeg = OrangeTVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			OrangeTVModuleLiveTV(self),
			OrangeTVModuleArchive(self),
			OrangeTVModuleExtra(self)
		]

	# #################################################################################################

	def login(self, silent):
		self.orangetv = None
		self.channels = []

		orangetv = OrangeTV(self)
		orangetv.refresh_configuration()

		self.orangetv = orangetv

		return True

	# #################################################################################################

	def get_channels_checksum(self):
		ctx = md5()
		for ch in self.channels:
			ctx.update(json.dumps(ch, sort_keys=True).encode('utf-8'))

		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.orangetv.get_live_channels()
		self.checksum = self.get_channels_checksum()

		self.channels_by_key = {}
		self.channels_by_norm_name = {}

		for ch in self.channels:
			self.channels_by_key[ch['key']] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_hls_info(self, stream_key):
		resp = {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

		return resp

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		playlists = self.orangetv.get_live_link(channel_key)

		for playlist in playlists:
			try:
				for p in (self.get_hls_streams(playlist, self.orangetv.req_session, max_bitrate=self.get_setting('max_bitrate')) or []):
					if self.get_setting('hls_multiaudio'):
						return stream_key_to_hls_url(self.http_endpoint_rel, {'url': p['playlist_url'], 'bandwidth': p['bandwidth']})
					else:
						return p['url']
			except:
				self.log_exception()

		return None

	# #################################################################################################

	def resolve_hls_streams(self, title, playlist_urls, **kwargs):
		for playlist_url in playlist_urls:
			try:
				streams = self.get_hls_streams(playlist_url, self.orangetv.req_session, max_bitrate=self.get_setting('max_bitrate'))
				for p in (streams or []):
					bandwidth = int(p['bandwidth'])
					if bandwidth < 2000000:
						quality = "480p"
					elif bandwidth < 3000000:
						quality = "576p"
					elif bandwidth < 6000000:
						quality = "720p"
					else:
						quality = "1080p"

					info_labels = {
						'quality': quality,
						'bandwidth': bandwidth
					}

					if self.get_setting('hls_multiaudio'):
						url = stream_key_to_hls_url(self.http_endpoint, {'url': p['playlist_url'], 'bandwidth': p['bandwidth']})
					else:
						url = p['url']

					self.add_play(title, url, info_labels, **kwargs)

				if streams:
					break
			except:
				self.log_exception()

	# #################################################################################################
