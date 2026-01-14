# -*- coding: utf-8 -*-

import time
import json
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .rebittv import RebitTV
from .bouquet import RebitTVBouquetXmlEpgGenerator
import base64

# #################################################################################################


class RebitTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')
		epg = self.cp.rebittv.get_current_epg()

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			epgdata = epg.get(channel['id'])

			if epgdata:
				epg_title = epgdata['title']

				if epgdata.get('subtitle'):
					epg_title += ': ' + epgdata['subtitle']

				epg_str = "  " + _I(epg_title)

				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(int(epgdata["start"])), self.cp.timestamp_to_str(int(epgdata["stop"])), epgdata.get('description', '')),
					'title': epg_title,
					'adult': channel['adult']
				}
			else:
				epg_str = ""
				info_labels = {
					'adult': channel['adult']
				}

			self.cp.add_video(channel['name'] + epg_str, img=channel.get('picon'), info_labels=info_labels, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['id'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key):
		enable_download = self.cp.get_setting('download_live')
		for one in self.cp.rebittv.get_live_link(channel_key, max_bitrate=self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['resolution'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, download=enable_download)

# #################################################################################################


class RebitTVModuleArchive(CPModuleArchive):

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
				self.add_archive_channel(channel['name'], channel['id'], channel['timeshift'], img=channel['picon'], info_labels={'adult': channel['adult']})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for event in self.cp.rebittv.get_epg(channel_id, ts_from, ts_to):
			if event["start"] < ts_from:
				continue

			if ts_to <= event["start"]:
				break

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(event["start"]), self.cp.timestamp_to_str(event["stop"]), _I(event["title"]))

			info_labels = {
				'plot': event.get('description'),
				'title': event["title"]
			}

			self.cp.add_video(title, None, info_labels, cmd=self.get_archive_stream, archive_title=str(event["title"]), channel_id=channel_id, event_id=event['id'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, channel_id, event_id):
		for one in self.cp.rebittv.get_live_link(channel_id, event_id, max_bitrate=self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['resolution'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(archive_title, one['url'], info_labels)

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
		return channel.get('id') if channel.get('timeshift') else None

	# #################################################################################################

	def get_archive_event(self, channel_id, event_start, event_end=None):
		for event in self.cp.rebittv.get_epg(channel_id, event_start - 14400, (event_end or event_start) + 14400):
			if abs(event["start"] - event_start) > 60:
				self.cp.log_debug("Archive event %d - %d doesn't match: %s" % (event["start"], event["stop"], event.get("title") or '???'))
				continue

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(event["start"]), self.cp.timestamp_to_str(event["stop"]), _I(event["title"]))

			info_labels = {
				'plot': event.get('description'),
				'title': event["title"]
			}

			self.cp.add_video(title, None, info_labels, cmd=self.get_archive_stream, archive_title=str(event["title"]), channel_id=channel_id, event_id=event['id'])
			break

# #################################################################################################

class RebitTVModuleExtra(CPModuleTemplate):

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
		for pdev in self.cp.rebittv.get_devices():
			dev_added = self.cp.timestamp_to_str(int(pdev["created_at"]), format='%d.%m.%Y %H:%M')
			title = 'Model: %s, Typ: %s, %s: %s' % (pdev['title'], pdev["type"], self._('Added'), dev_added)
			info_labels = { 'plot': self._('In menu you can remove device using Remove device!')}

			menu = {}
			self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_id=pdev["id"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_id):
		self.cp.rebittv.device_remove(device_id)
		self.cp.add_video(_C('red', self._('Device {device} was removed!').format(device=device_id)), download=False)

# #################################################################################################

class RebitTVContentProvider(ModuleContentProvider):

	def __init__(self):
		ModuleContentProvider.__init__(self)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'device_name')

		self.rebittv = self.get_nologin_helper()
		self.channels = []
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.channels_next_load_time = 0
		self.checksum = None

		self.bxeg = RebitTVBouquetXmlEpgGenerator(self)

		self.modules = [
			RebitTVModuleLiveTV(self),
			RebitTVModuleArchive(self),
			RebitTVModuleExtra(self)
		]

	# #################################################################################################

	def login(self, silent):
		self.rebittv = self.get_nologin_helper()

		rebittv = RebitTV(self)
		self.rebittv = rebittv

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

		self.channels = self.rebittv.get_channels()
		self.checksum = self.get_channels_checksum()
		self.channels_by_key = {}
		self.channels_by_norm_name = {}

		for ch in self.channels:
			self.channels_by_key[str(ch['id'])] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		streams = self.rebittv.get_live_link(channel_key, max_bitrate=self.get_setting('max_bitrate'))

		if len(streams) > 0:
			return streams[0]['url']
		else:
			return None

	# #################################################################################################
