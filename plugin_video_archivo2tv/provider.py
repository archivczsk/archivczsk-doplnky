# -*- coding: utf-8 -*-

import os
from datetime import datetime
import time
import random
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.string_utils import _I, _C, _B
from .o2tv import O2TV
from .bouquet import O2TVBouquetXmlEpgGenerator

DAY_NAME_SHORT = ("Po", "Ut", "St", "Čt", "Pá", "So", "Ne")


class O2TVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=True)

	# #################################################################################################
	
	def get_live_tv_categories(self, section=None):
		if section == None:
			self.add_live_tv_category('Všechny kanály', None)
			self.cp.add_dir('Favoritní', cmd=self.get_live_tv_categories, section='fav')
			self.cp.add_dir('Moje seznamy kanálů', cmd=self.get_live_tv_categories, section='my_lists')
		elif section == 'fav':
			self.cp.load_favourites()
			self.show_my_list(self.cp.favourites, fav=True)
		elif section == 'my_lists':
			user_lists = self.cp.o2tv.get_user_channel_lists()
			for name, keys in user_lists.items():
				self.cp.add_dir(name, cmd=self.show_my_list, keys=keys)
		
	# #################################################################################################

	def show_my_list(self, keys, fav=False):
		self.cp.load_channel_list()

		channels = []
		for key in keys:
			ch = self.cp.channels_by_key.get(key)

			if ch:
				channels.append(ch)

		self.get_live_tv_channels(channels=channels, fav=fav)

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None, channels=None, fav=False):
		self.cp.load_channel_list()

		show_epg = self.cp.get_setting('showliveepg')
		enable_adult = self.cp.get_setting('enable_adult')
		cache_hours = int(self.cp.get_setting('epgcache'))
		enable_xmlepg = self.cp.get_setting('enable_xmlepg') and self.cp.get_setting('enable_userbouquet')

		if channels == None:
			channels = self.cp.channels

		if show_epg:
			# reload EPG cache if needed
			ret = self.cp.o2tv.load_epg_cache()

			# ret == True -> there already exist cache file
			if ret and enable_xmlepg:
				# if there exists already cache file and xmlepg is enabled, then cache file
				# is managed by bgservice, so disable epg refresh here
				cache_hours = 0

		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			if show_epg:
				epg = self.cp.o2tv.get_channel_current_epg(channel['key'], cache_hours)
			else:
				epg = None

			if epg:
				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot': epg['desc'],
					'title': epg["title"],
					'img': epg['img']
				}
			else:
				epg_str = ''
				info_labels = {}

			menu = {}
			if fav:
				self.cp.add_menu_item(menu, "Odstranit z favoritních", cmd=self.del_fav, key=channel['key'])
			else:
				self.cp.add_menu_item(menu, "Přidat do favoritních", cmd=self.add_fav, key=channel['key'])

			self.cp.add_video(channel['name'] + epg_str, img=channel['screenshot'], info_labels=info_labels, menu=menu, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'])

		self.cp.o2tv.save_epg_cache()

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key):
		for one in self.cp.o2tv.get_live_link(channel_key):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, live=True)

	# #################################################################################################

	def add_fav(self, key):
		if key not in self.cp.favourites:
			self.cp.favourites.append(key)
			self.cp.save_favourites()
			self.cp.show_info('Přidáno do favoritních')
		else:
			self.cp.show_info('Kanál už je ve favoritních')

	# #################################################################################################

	def del_fav(self, key):
		if key in self.cp.favourites:
			self.cp.favourites.remove(key)
			self.cp.save_favourites()
			self.cp.refresh_screen()

# #################################################################################################


class O2TVModuleArchive(CPModuleArchive):

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

		for epg in self.cp.o2tv.get_channel_epg(channel_id, ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["startTimestamp"] / 1000), self.cp.timestamp_to_str(epg["endTimestamp"] / 1000), _I(epg["name"]))
			
			info_labels = {
				'plot': epg.get('shortDescription'),
				'title': epg['name']
			}

			menu = {}
			self.cp.add_menu_item(menu, 'Nahrát pořad', cmd=self.cp.add_recording, epg_id=epg['epgId'])
			self.cp.add_video(title, epg.get('picture'), info_labels, menu, cmd=self.cp.get_video_stream, video_title=str(epg["name"]), channel_key=channel_id, epg_id=epg['epgId'], ts_from=epg['startTimestamp'], ts_to=epg['endTimestamp'])

	# #################################################################################################

# #################################################################################################


class O2TVModuleRecordings(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Nahrávky", 'Tu najdete nahrávky vašich programů')

	# #################################################################################################

	def root(self):
		self.cp.add_dir("Naplánovat nahrávání", cmd=self.plan_recordings)
		self.cp.add_dir("Budoucí - plánováne", cmd=self.show_recordings, only_finished=False)
		self.cp.add_dir("Existujíci", cmd=self.show_recordings, only_finished=True)
	
	# #################################################################################################

	def show_recordings(self, only_finished=True):
		result = []
		recordings = {}

		if only_finished:
			def check_recording_state(s1, s2):
				return s1 == s2
		else:
			def check_recording_state(s1, s2):
				return s1 != s2

		data_pvr = self.cp.o2tv.get_recordings()

		if "result" in data_pvr and len(data_pvr["result"]) > 0:
			for program in data_pvr["result"]:
				if check_recording_state(program["state"], "DONE"):
					pvrProgramId = program["pvrProgramId"]
					epgId = program["program"]["epgId"]
					if "ratings" in program["program"] and len(program["program"]["ratings"]) > 0:
						ratings = program["program"]["ratings"]
					else:
						ratings = {}
					if "longDescription" in program["program"] and len(program["program"]["longDescription"]) > 0:
						plot = program["program"]["longDescription"]
					else:
						plot = None
					if "images" in program["program"] and len(program["program"]["images"]) > 0 and "cover" in program["program"]["images"][0]:
						img = program["program"]["images"][0]["cover"]
					else:
						img = None
					recordings.update({program["program"]["start"] + random.randint(0, 100): {"pvrProgramId": pvrProgramId, "name": program["program"]["name"], "channelKey": program["program"]["channelKey"], "start": datetime.fromtimestamp(program["program"]["start"] / 1000).strftime("%d.%m %H:%M"), "end": datetime.fromtimestamp(program["program"]["end"] / 1000).strftime("%H:%M"), "plot": plot, "img": img, "ratings": ratings}})

			for recording in sorted(list(recordings.keys()), reverse=True):
				title = recordings[recording]["name"] + " (" + recordings[recording]["channelKey"] + " | " + recordings[recording]["start"] + " - " + recordings[recording]["end"] + ")"

				thumb = "https://www.o2tv.cz/" + recordings[recording]["img"]
				rating = None
				for _, rating_value in list(recordings[recording]["ratings"].items()):
					rating = rating_value / 10
					break

				info_labels = {
					'plot': plot,
					'rating': rating,
					'title': recordings[recording]["name"]
				}

				menu = {}
				self.cp.add_menu_item(menu, 'Smazat nahrávku', cmd=self.del_recording, pvr_id=recordings[recording]["pvrProgramId"])

				if only_finished:
					self.cp.add_video(title, thumb, info_labels, menu, cmd=self.play_recording, pvr_title=title, pvr_id=recordings[recording]["pvrProgramId"])
				else:
					self.cp.add_video(title, thumb, info_labels, menu)
	
	# #################################################################################################

	def play_recording(self, pvr_title, pvr_id):
		for one in self.cp.o2tv.get_recording_link(pvr_id):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(pvr_title, one['url'], info_labels)

	# #################################################################################################

	def del_recording(self, pvr_id):
		self.cp.o2tv.delete_recording(pvr_id)
		self.cp.refresh_screen()

	# #################################################################################################
	
	def plan_recordings(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			self.cp.add_dir(channel['name'], img=channel['logo'], cmd=self.plan_recordings_for_channel, channel_key=channel['key'])
	
	# #################################################################################################
	
	def plan_recordings_for_channel(self, channel_key):
		from_datetime = datetime.now()
		from_ts = int(time.mktime(from_datetime.timetuple()))
		to_ts = from_ts

		for i in range(7):
			from_ts = to_ts
			to_ts = from_ts + 24 * 3600

			events = self.cp.o2tv.get_channel_epg(channel_key, from_ts, to_ts)

			for event in events:
				startts = event["startTimestamp"]
				start = datetime.fromtimestamp(startts / 1000)
				endts = event["endTimestamp"]
				end = datetime.fromtimestamp(endts / 1000)
				epg_id = event['epgId']

				title = DAY_NAME_SHORT[start.weekday()] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["name"]

				info_labels = {
					'plot': event['shortDescription'] if 'shortDescription' in event else None,
					'title': event['name']
				}
				img = event['picture'] if 'picture' in event else None

				menu = {}
				self.cp.add_menu_item(menu, 'Nahrát pořad', cmd=self.cp.add_recording, epg_id=epg_id)
				self.cp.add_video(title, img, info_labels, menu, cmd=self.cp.add_recording, epg_id=epg_id)
		
# #################################################################################################


class O2TVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Speciálni sekce")

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self, section=None):
		info_labels = {'plot': "Tu si můžete zobrazit a případně vymazat/odregistrovat zbytečná zařízení, aby ste se mohli znova jinde přihlásit." }
		self.cp.add_dir('Zaregistrovaná zařízení', info_labels=info_labels, cmd=self.list_devices)

	# #################################################################################################

	def list_devices(self):
		self.cp.o2tv.refresh_configuration(True)

		for pdev in self.cp.o2tv.devices:
			title = pdev["deviceName"] + " - " + self.cp.timestamp_to_str(pdev["lastLoginTimestamp"] / 1000, format='%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + pdev["deviceId"]
			info_labels = { 'plot': 'V menu můžete zařízení vymazat pomocí Smazat zařízení!'}

			menu = {}
			self.cp.add_menu_item(menu, 'Smazat zařízení!', self.delete_device, device_id=pdev["deviceId"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu)

	# #################################################################################################
	
	def delete_device(self, device_id):
		self.cp.o2tv.device_remove(device_id)
		self.cp.add_video(_C('red', 'Zařízení %s bylo vymazáno!' % device_id))

# #################################################################################################


class O2TVContentProvider(ModuleContentProvider):
	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='O2TV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'deviceid', 'devicename')

		self.o2tv = None
		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint
		self.favourites = None

		if not self.get_setting('deviceid'):
			self.set_setting('deviceid', O2TV.create_device_id())

		self.bxeg = O2TVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			CPModuleSearch(self, 'Vyhledat'),
			O2TVModuleLiveTV(self),
			O2TVModuleArchive(self),
			O2TVModuleRecordings(self),
			O2TVModuleExtra(self)
		]

		self.load_favourites()

	# #################################################################################################
	
	def login(self, silent):
		self.o2tv = None
		self.channels = []
		self.channels_by_key = {}

		o2tv = O2TV(self.get_setting('username'), self.get_setting('password'), self.get_setting('deviceid'), self.get_setting('devicename'), self.data_dir, self.log_info)
		o2tv.refresh_configuration()

		self.o2tv = o2tv

		return True

	# #################################################################################################
	
	def get_channels_checksum(self):
		ctx = md5()
		for ch in self.channels:
			item = {
				'id': ch['id'],
				'name': ch['name'],
				'type': ch['type'],
				'picon': ch['picon'],
				'adult': ch['adult']
			}

			ctx.update(str(frozenset(item)).encode('utf-8'))

		return ctx.hexdigest()
	
	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return
		
		self.channels = self.o2tv.get_channels()
		self.checksum = self.get_channels_checksum()
		
		self.channels_by_key = {}
		for ch in self.channels:
			self.channels_by_key[ch['key']] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		self.load_channel_list()
		return self.o2tv.get_live_link(channel_key)[0]['url']

	# #################################################################################################

	def load_favourites(self):
		if self.favourites != None:
			return

		result = []

		try:
			with open(os.path.join(self.data_dir, 'favourites.txt'), 'r') as f:
				for line in f.readlines():
					result.append(line.rstrip())
		except:
			pass

		self.favourites = result

	# #################################################################################################

	def save_favourites(self):
		with open(os.path.join(self.data_dir, 'favourites.txt'), 'w') as f:
			for fav in self.favourites:
				f.write(fav + '\n')

	# #################################################################################################

	def get_video_stream(self, video_title, channel_key, epg_id, ts_from, ts_to):
		for one in self.o2tv.get_video_link(channel_key, ts_from, ts_to + (int(self.get_setting("offset")) * 60 * 1000), epg_id):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.add_play(video_title, one['url'], info_labels, live=True)

	# #################################################################################################

	def add_recording(self, epg_id):
		ret = self.o2tv.add_recording(epg_id)
		self.show_info("Nahrávka přidána" if ret else "Při přidávaní nahrávky nastala chyba")

	# #################################################################################################

	def search(self, keyword, search_id=''):
		self.load_channel_list()

		for programs in self.o2tv.search(keyword):
			programs = programs["programs"][0]

			if programs["channelKey"] not in self.channels_by_key:
				continue # nezobrazovat nezakoupene kanaly

			startts = programs["start"]
			start = datetime.fromtimestamp(startts / 1000)
			endts = programs["end"]
			end = datetime.fromtimestamp(endts / 1000)
			epg_id = programs["epgId"]

			title = programs["name"] + " (" + programs["channelKey"] + " | " + DAY_NAME_SHORT[start.weekday()] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"

			img = 'https://www.o2tv.cz' + programs['picture'] if 'picture' in programs else None
			info_labels = {
				'plot': programs.get('shortDescription'),
				'title': programs["name"]
			}

			menu = {}
			self.add_menu_item(menu, 'Nahrát pořad', self.add_recording, epg_id=epg_id)
			self.add_video(title, img, info_labels, menu, cmd=self.get_video_stream, video_title=programs["name"], channel_key=programs["channelKey"], epg_id=epg_id, ts_from=startts, ts_to=endts)

	# #################################################################################################
