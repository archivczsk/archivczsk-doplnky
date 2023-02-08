# -*- coding: utf-8 -*-

import time
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.string_utils import _I, _C, _B
from .rebittv import RebitTV
from .bouquet import RebitTVBouquetXmlEpgGenerator

# #################################################################################################


class RebitTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()

		enable_adult = self.cp.get_setting('enable_adult')
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
					'title': epg_title
				}
			else:
				epg_str = ""
				info_labels = {}

			self.cp.add_video(channel['name'] + epg_str, img=channel.get('picon'), info_labels=info_labels, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['id'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key):
		for one in self.cp.rebittv.get_live_link(channel_key):
			info_labels = {
				'quality': one['resolution'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, live=True)

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
				self.add_archive_channel(channel['name'], channel['id'], channel['timeshift'], img=channel['picon'])

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
		for one in self.cp.rebittv.get_live_link(channel_id, event_id):
			info_labels = {
				'quality': one['resolution'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(archive_title, one['url'], info_labels, live=True)

	# #################################################################################################


# #################################################################################################

class RebitTVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Špeciálna sekcia")

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self, section=None):
		info_labels = {'plot': "Tu si môžete zobraziť a prípadne vymazať/odregistrovať zbytočná zariadenia, aby ste sa mohli znova inde prihlásiť." }
		self.cp.add_dir('Zaregistrované zariadenia', info_labels=info_labels, cmd=self.list_devices)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.rebittv.get_devices():
			dev_added = self.cp.timestamp_to_str(int(pdev["created_at"]), format='%d.%m.%Y %H:%M')
			title = 'Model: %s, Typ: %s, Pridané: %s' % (pdev['title'], pdev["type"], dev_added)
			info_labels = { 'plot': 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'}

			menu = {}
			self.cp.add_menu_item(menu, 'Zmazať zariadenie!', self.delete_device, device_id=pdev["id"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu)

	# #################################################################################################

	def delete_device(self, device_id):
		self.rebittv.device_remove(device_id)
		self.cp.add_video(_C('red', 'Zariadenie %s bolo vymazané!' % device_id))

# #################################################################################################

class RebitTVContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='RebitTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'device_name')

		self.rebittv = None
		self.channels = []
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint

		self.bxeg = RebitTVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			RebitTVModuleLiveTV(self),
			RebitTVModuleArchive(self),
			RebitTVModuleExtra(self)
		]

	# #################################################################################################

	def login(self):
		self.rebittv = None

		rebittv = RebitTV(self.get_setting('username'), self.get_setting('password'), self.get_setting('device_name'), self.data_dir, self.log_info)
		self.rebittv = rebittv

		return True

	# #################################################################################################

	def get_channels_checksum(self):
		ctx = md5()
		for ch in self.channels:
			ctx.update(str(frozenset(ch.items())).encode('utf-8'))

		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.rebittv.get_channels()
		self.checksum = self.get_channels_checksum()

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		return self.rebittv.get_live_link(channel_key)[0]['url']

	# #################################################################################################

