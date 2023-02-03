# -*- coding: utf-8 -*-

import time
import base64
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.string_utils import _I, _C, _B
from .magiogo import MagioGO
from .bouquet import MagioGOBouquetXmlEpgGenerator

# #################################################################################################


class MagioGOModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list(True)

		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel.adult:
				continue

			if channel.epg_name and channel.epg_desc:
				epg_str = '  ' + _I(channel.epg_name)

				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(channel.epg_start), self.cp.timestamp_to_str(channel.epg_stop), channel.epg_desc)
				}
			else:
				epg_str = ""
				info_labels = {}

			self.cp.add_video(channel.name + epg_str, img=channel.preview, info_labels=info_labels, cmd=self.get_livetv_stream, channel_title=channel.name, channel_id=channel.id)

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_id):
		url = self.cp.http_endpoint + '/playlive/' + base64.b64encode(str(channel_id).encode("utf-8")).decode("utf-8") + '/index'
		self.cp.add_play(channel_title, url, live=True, playlist_autogen=False)

# #################################################################################################


class MagioGOModuleArchive(CPModuleArchive):

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
				self.add_archive_channel(channel.name, channel.id, channel.timeshift, img=channel.picon)

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for event in self.cp.magiogo.get_archiv_channel_programs(channel_id, ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(event["start"]), self.cp.timestamp_to_str(event["stop"]), _I(event["title"]))

			self.cp.add_video(title, event['image'], info_labels={'plot': event.get('plot')}, cmd=self.get_archive_stream, archive_title=str(event["title"]), event_id=event['id'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, event_id):
		url = self.cp.http_endpoint + '/playarchive/' + base64.b64encode(str(event_id).encode("utf-8")).decode("utf-8") + '/index'
		self.cp.add_play(archive_title, url, live=True, playlist_autogen=False)

	# #################################################################################################

# #################################################################################################


class MagioGOModuleExtra(CPModuleTemplate):

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
		for pdev in self.cp.magiogo.get_devices():
			title = pdev["name"] + "  -  " + pdev['cat']

			menu = {}
			if pdev['this']:
				title += ' *'
				info_labels = {}
			else:
				self.cp.add_menu_item(menu, 'Zmazať zariadenie!', self.delete_device, device_name=pdev["name"], device_id=pdev["id"])
				info_labels = { 'plot': 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'}

			self.cp.add_video(title, info_labels=info_labels, menu=menu)

	# #################################################################################################

	def delete_device(self, device_name, device_id):
		ret, msg = self.cp.magiogo.remove_device(device_id)

		if ret:
			self.cp.add_video(_C('red', 'Zariadenie %s bolo vymazané!' % device_name))
		else:
			self.cp.add_video(_C('red', 'Chyba: %s' % msg))

# #################################################################################################


class MagioGOContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='MagioGO', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('region', 'username', 'password', 'deviceid', 'devicetype')

		self.magiogo = None
		self.channels = []
		self.channels_next_load_time = 0
		self.epg_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint

		self.bxeg = MagioGOBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			MagioGOModuleLiveTV(self),
			MagioGOModuleArchive(self),
			MagioGOModuleExtra(self)
		]

	# #################################################################################################

	def login(self):
		self.magiogo = None
		self.channels = []
		device_id = self.get_setting('deviceid')

		if not self.get_setting('username') or not self.get_setting('password'):
			return False

		if not device_id:
			device_id = MagioGO.create_device_id()
			self.set_setting('deviceid', device_id)

		magiogo = MagioGO(self.get_setting('region'), self.get_setting('username'), self.get_setting('password'), device_id, int(self.get_setting('devicetype')), self.data_dir, self.log_info)
		self.magiogo = magiogo

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

	def load_channel_list(self, fill_epg=False):
		act_time = int(time.time())

		if self.channels:
			if fill_epg:
				if self.epg_next_load_time > act_time:
					return
			else:
				if self.channels_next_load_time > act_time:
					return

		self.channels = self.magiogo.get_channel_list(fill_epg)
		self.checksum = self.get_channels_checksum()

		if fill_epg:
			# allow channels reload once a hour and epg once a minute
			self.epg_next_load_time = act_time + 60
			self.channels_next_load_time = act_time + 3600
		else:
			# allow channels reload once a hour
			self.channels_next_load_time = act_time + 3600

	# #################################################################################################
