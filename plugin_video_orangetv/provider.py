# -*- coding: utf-8 -*-

from datetime import datetime
import time
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.string_utils import _I, _C, _B
from .orangetv import OrangeTV
from .bouquet import OrangeTVBouquetXmlEpgGenerator


class OrangeTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()

		show_epg = self.cp.get_setting('showliveepg')
		enable_adult = self.cp.get_setting('enable_adult')
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
				info_labels = {'plot': epg['desc'] }
			else:
				epg_str = ''
				info_labels = {}

			self.cp.add_video(channel['name'] + epg_str, img=channel['snapshot'], info_labels=info_labels, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'])

		self.cp.orangetv.saveEpgCache()

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key):
		for one in self.cp.orangetv.get_live_link(channel_key):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, live=True)

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
				self.add_archive_channel(channel['name'], channel['key'], channel['timeshift'], img=channel['logo'])

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for ch in self.cp.orangetv.getArchivChannelPrograms(channel_id, ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(ch["start"]), self.cp.timestamp_to_str(ch["stop"]), _I(ch["title"]))
			
			self.cp.add_video(title, ch['img'], info_labels={'plot': ch['plot']}, cmd=self.get_archive_stream, archive_title=str(ch["title"]), channel_key=channel_id, epg_id=ch['epg_id'], ts_from=ch['start'], ts_to=ch['stop'])

	# #################################################################################################

	def get_archive_stream(self, archive_title, channel_key, epg_id, ts_from, ts_to):
		for one in self.cp.orangetv.get_archive_link(channel_key, epg_id, ts_from, ts_to):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(archive_title, one['url'], info_labels, live=True)

# #################################################################################################


class OrangeTVModuleExtra(CPModuleTemplate):

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
		self.cp.orangetv.refresh_configuration(True)

		for pdev in self.cp.orangetv.devices:
			title = pdev["deviceName"] + " - " + self.cp.timestamp_to_str(pdev["lastLoginTimestamp"] / 1000, format='%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + pdev["deviceId"]
			info_labels = { 'plot': 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'}

			menu = {}
			self.cp.add_menu_item(menu, 'Zmazať zariadenie!', self.delete_device, device_id=pdev["deviceId"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu)

	# #################################################################################################
	
	def delete_device(self, device_id):
		self.cp.orangetv.device_remove(device_id)
		self.cp.add_video(_C('red', 'Zariadenie %s bolo vymazané!' % device_id))

# #################################################################################################

class OrangeTVContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='OrangeTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'deviceid')

		self.orangetv = None
		self.channels = []
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint

		self.bxeg = OrangeTVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			OrangeTVModuleLiveTV(self),
			OrangeTVModuleArchive(self),
			OrangeTVModuleExtra(self)
		]

	# #################################################################################################
	
	def login(self):
		self.orangetv = None
		device_id = self.get_setting('deviceid')

		if not self.get_setting('username') or not self.get_setting('password'):
			return False

		if not device_id:
			device_id = OrangeTV.create_device_id()
			self.set_setting('deviceid', device_id)

		orangetv = OrangeTV(self.get_setting('username'), self.get_setting('password'), device_id, self.data_dir, self.log_info)
		orangetv.refresh_configuration()

		self.orangetv = orangetv

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
		
		self.channels = self.orangetv.get_live_channels()
		self.checksum = self.get_channels_checksum()
		
		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		return self.orangetv.get_live_link(channel_key)[0]['url']

	# #################################################################################################
