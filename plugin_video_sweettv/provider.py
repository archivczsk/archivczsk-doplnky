# -*- coding: utf-8 -*-

import time

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .bouquet import SweetTVBouquetXmlEpgGenerator
from .sweettv import SweetTV
import base64

# #################################################################################################

class SweetTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################

	def get_live_tv_channels(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')

		epg = self.cp.sweettv.get_epg()

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			epgdata = epg.get(channel['id'])

			if epgdata:
				epgdata = epgdata[0]

				info_labels = {
					'plot': '%s - %s' % (self.cp.timestamp_to_str(int(epgdata["time_start"])), self.cp.timestamp_to_str(int(epgdata["time_stop"]))),
					'title': epgdata["text"],
					'adult': channel['adult']
				}
				epg_str = "  " + _I(epgdata["text"])
				img = epgdata.get('preview_url')
			else:
				epg_str = ""
				info_labels = {
					'adult': channel['adult']
				}
				img = None

			self.cp.add_video(channel['name'] + epg_str, img=img, info_labels=info_labels, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_id=channel['id'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_id):
		enable_download = self.cp.get_setting('download_live')

		for one in self.cp.sweettv.get_live_link(channel_id, max_bitrate=self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one.get('name', '???').replace('"', ''),
				'bandwidth': one['bandwidth']
			}

			data_item = {
				'stream_id': one.get('stream_id')
			}

			settings = {
				'user-agent' : self.cp.sweettv.get_user_agent(),
			}
			self.cp.add_play(channel_title, one['url'], info_labels, data_item=data_item, settings=settings, download=enable_download)

# #################################################################################################


class SweetTVModuleArchive(CPModuleArchive):

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

		for event in self.cp.sweettv.get_epg(ts_from, 100, [ channel_id ]).get(channel_id, []):
			startts = event["time_start"]
			endts = event["time_stop"]

			if startts < ts_from:
				continue

			if ts_to <= int(startts):
				break

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(startts), self.cp.timestamp_to_str(endts), _I(event["text"]))
			info_labels = {
				'title': event["text"]
			}

			self.cp.add_video(title, event.get('preview_url'), info_labels, cmd=self.cp.get_archive_stream, archive_title=str(event["text"]), channel_id=channel_id, epg_id=event['id'])

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

class SweetTVModuleVOD(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Filmy")

	# #################################################################################################

	def root(self, cat=None):
		if cat == None:
			self.cp.add_dir(self._('By genre'), cmd=self.root, cat='genres')
			self.cp.add_dir(self._('By collection'), cmd=self.root, cat='collections')
			return

		data = self.cp.sweettv.get_movie_configuration()

		if cat == 'collections':
			data = data['collections'] + self.cp.sweettv.get_movie_collections()
			prefix = '#movie_collection#'
			cmd = self.get_movies_collection
		elif cat == 'genres':
			data = data['genres']
			prefix = '#movie_genre#'
			cmd = self.get_movies_genre
		else:
			data = []

		for one in data:
			self.cp.add_dir(one['title'], cmd=cmd, id=one['id'])

	# #################################################################################################

	def get_movies_collection(self, id):
		data = self.cp.sweettv.get_movie_collection(id)
		return self.cp.process_movie_data(data)

	# #################################################################################################

	def get_movies_genre(self, id):
		data = self.cp.sweettv.get_movie_genre(id)
		return self.cp.process_movie_data(data)

# #################################################################################################


class SweetTVModuleExtra(CPModuleTemplate):

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
		info_labels = {'plot': self._("Forces logout from this devices and does new login. Use if you have problem with playback. After running this option it's necessary to go out of this addon to force new automatic login.") }
		self.cp.add_dir(self._('Logout from this device'), info_labels=info_labels, cmd=self.logout)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def logout(self):
		self.cp.sweettv.logout()
		self.cp.sweettv = None
		self.cp.add_video(_C('red', self._('You have been logged out!')), download=False)
		self.cp.login_error(self._('You have been logged out!'))

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.sweettv.get_devices():
			dev_added = self.cp.timestamp_to_str(int(pdev["date_added"]), format='%d.%m.%Y %H:%M')
			title = 'Model: %s, Typ: %s, Pridané: %s' % (pdev['model'], pdev["type"], dev_added)
			info_labels = { 'plot': self._('In menu you can remove device using Remove device!')}

			menu = {}
			self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, token_id=pdev["token_id"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, token_id):
		self.cp.sweettv.device_remove(token_id)
		self.cp.add_video(_C('red', self._('Device {device} was removed!').format(device=token_id)), download=False)

# #################################################################################################

class SweetTVContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='SweetTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'device_id')

		self.sweettv = None
		self.channels = []
		self.channels_next_load_time = 0
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.checksum = None
		self.http_endpoint = http_endpoint
		self.last_stream_id = None

		if not self.get_setting('device_id'):
			self.set_setting('device_id', SweetTV.create_device_id())

		self.bxeg = SweetTVBouquetXmlEpgGenerator(self, http_endpoint, SweetTV.get_user_agent())

		self.modules = [
			CPModuleSearch(self),
			SweetTVModuleLiveTV(self),
			SweetTVModuleArchive(self),
			SweetTVModuleVOD(self),
			SweetTVModuleExtra(self)
		]

	# #################################################################################################

	def login(self, silent):
		self.sweettv = None
		self.channels = []
		sweettv = SweetTV(self)
		self.sweettv = sweettv

		return True

	# #################################################################################################

	def search(self, keyword, search_id):
		events = self.sweettv.search(keyword)

		self.process_movie_data(events['movies'])

		for event in events['events']:
			self.add_video(event['title'] + _C('yellow', ' ' + event['time']), img=event['poster'], cmd=self.get_archive_stream, archive_title=event['title'], channel_id=event['channel_id'], epg_id=event['event_id'])

	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return

		self.channels, self.checksum = self.sweettv.get_channels()

		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		for ch in self.channels:
			self.channels_by_key[ch['id']] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def process_movie_data(self, data):
		show_paid = self.get_setting('show_paid_movies')

		for movie in data:
			if movie['available']:
				movie_id = movie['id']
				owner_id = movie['owner_id']
				title = movie['title']
			else:
				# this is a PPV movie
				if not show_paid:
					continue

				title = _C('yellow', '* ') + movie['title']
				movie_id = None
				owner_id = None

			info_labels = {
				'plot': movie['plot'],
				'duration': movie['duration'],
				'year': movie['year'],
				'rating': movie.get('rating'),
				'title': movie['title']
			}

			menu = {}
			if movie['trailer'] and movie['available']:
				self.add_menu_item(menu, self._("Play trailer"), cmd=self.get_raw_stream, stream_title='Trailer: ' + movie['title'], url=movie['trailer'])

			if movie_id and owner_id:
				self.add_video(title, movie.get('poster'), info_labels=info_labels, menu=menu, cmd=self.get_movie_stream, movie_name=movie['title'], movie_id=movie_id, owner_id=owner_id)
			else:
				self.add_video(title, movie.get('poster'), info_labels=info_labels, menu=menu, cmd=self.get_raw_stream, stream_title='Trailer: ' + movie['title'], url=movie.get('trailer'))

	# #################################################################################################

	def get_movie_stream(self, movie_name, movie_id, owner_id):
		for one in self.sweettv.get_movie_link(movie_id, owner_id):
			info_labels = {
				'quality': one.get('name', '???').replace('"', ''),
				'bandwidth': one['bandwidth']
			}

			data_item = {
				'stream_id': one.get('stream_id')
			}

			settings = {
				'user-agent': self.sweettv.get_user_agent(),
			}
			self.add_play(movie_name, one['url'], info_labels, data_item=data_item, settings=settings)

	# #################################################################################################

	def get_raw_stream(self, stream_title, url):
		if url:
			self.add_play(stream_title, url)

	# #################################################################################################

	def get_archive_stream(self, archive_title, channel_id, epg_id):
		for one in self.sweettv.get_live_link(channel_id, epg_id, max_bitrate=self.get_setting('max_bitrate')):
			info_labels = {
				'quality': one.get('name', '???').replace('"', ''),
				'bandwidth': one['bandwidth']
			}

			data_item = {
				'stream_id': one.get('stream_id')
			}

			settings = {
				'user-agent': self.sweettv.get_user_agent(),
			}
			self.add_play(archive_title, one['url'], info_labels, data_item=data_item, settings=settings)

	# #################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if action == 'end':
			stream_id = data_item.get('stream_id')

			if stream_id:
				self.sweettv.close_stream(stream_id)

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		if self.last_stream_id:
			self.sweettv.close_stream(self.last_stream_id)

		resp = self.sweettv.get_live_link(channel_key, max_bitrate=self.get_setting('max_bitrate'))

		if len(resp) > 0:
			self.last_stream_id = resp[0].get('stream_id')
			return resp[0]['url']
		else:
			self.last_stream_id = None
			return None

	# #################################################################################################
