# -*- coding: utf-8 -*-

import os
from datetime import datetime, date, timedelta
import time
import random
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.string_utils import _I, _C, _B
from .sledovanitv import SledovaniTV
from .bouquet import SledovaniTVBouquetXmlEpgGenerator

DAY_NAME_SHORT = ("Po", "Ut", "St", "Čt", "Pá", "So", "Ne")
DAY_NAME = ('Pondelí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Nedele')

# #################################################################################################


class SledovaniTVModuleHome(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Úvodní stránka")

	# #################################################################################################

	def root(self):

		for event in self.cp.sledovanitv.get_home():
			info_labels = {
				'plot': event.get('plot'),
				'duration': event.get('duration'),
				'title': event['title'],
			}
			
			day_name = DAY_NAME_SHORT[datetime.fromtimestamp(event['start']).weekday()]
			title = day_name + ' ' + self.cp.timestamp_to_str(event['start'], format='%d.%m. %H:%M') + ' - ' + self.cp.timestamp_to_str(event['end'], format='%H:%M') + ' ' + _I(event['title']) + ' '

			if event['start'] > int(time.time()):
				title += _C('red', '* ') + _C('grey', '[' + event['channel'] + ']')
				self.cp.add_video(title, event.get('thumb'), info_labels)
			else:
				title += _C('grey', '[' + event['channel'] + ']')
				self.cp.add_video(title, event.get('thumb'), info_labels, cmd=self.cp.get_event_stream, video_title=event['title'], event_id=event['eventid'])

# #################################################################################################


class SledovaniTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider)

	# #################################################################################################
	
	def get_live_tv_channels(self, cat_id=None):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		epgdata = self.cp.sledovanitv.get_epg()

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			if channel['type'] != 'tv':
				continue

			epg = epgdata.get(channel['id'], [])

			if channel['adult']:
				title = _C('red', channel['name'])
			else:
				title = channel['name']

			if epg:
				epg = epg[0]
				if self.cp.sledovanitv.epg_event_is_garbage(epg):
					epg = None

			if epg:
				start_ts = self.cp.sledovanitv.convert_time(epg["startTime"])
				end_ts = self.cp.sledovanitv.convert_time(epg["endTime"])
				plot = epg['description'] if epg.get('description') else ""

				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot': "%s - %s\n%s" % (self.cp.timestamp_to_str(start_ts), self.cp.timestamp_to_str(end_ts), plot),
					'title': epg["title"],
					'duration': epg.get('duration') * 60,
					'year': epg.get('year')
				}
				img = epg.get('poster')
			else:
				epg_str = ''
				info_labels = {}
				img = None

			self.cp.add_video(title + epg_str, img, info_labels, download=False, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_url=channel['url'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_url):
		for one in self.cp.sledovanitv.get_live_link(channel_url, self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, download=False)

# #################################################################################################


class SledovaniTVModuleRadio(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, 'Radia', plot='Obsahuje seznam rádií dostupných s vašim předplatným')

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		self.cp.load_channel_list()

		epgdata = self.cp.sledovanitv.get_epg()

		for channel in self.cp.channels:
			if channel['type'] != 'radio':
				continue

			epg = epgdata.get(channel['id'], [])

			if epg:
				epg = epg[0]
				if self.cp.sledovanitv.epg_event_is_garbage(epg):
					epg = None

			if epg:
				start_ts = self.cp.sledovanitv.convert_time(epg["startTime"])
				end_ts = self.cp.sledovanitv.convert_time(epg["endTime"])
				plot = epg['description'] if epg.get('description') else ""

				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot': "%s - %s\n%s" % (self.cp.timestamp_to_str(start_ts), self.cp.timestamp_to_str(end_ts), plot),
					'title': epg["title"],
					'duration': epg.get('duration') * 60,
					'year': epg.get('year')
				}
				img = epg.get('poster')
			else:
				epg_str = ''
				info_labels = {}
				img = None

			self.cp.add_video(channel['name'] + epg_str, img, info_labels, download=False, cmd=channel['url'])

# #################################################################################################


class SledovaniTVModuleArchive(CPModuleArchive):

	def __init__(self, content_provider):
		CPModuleArchive.__init__(self, content_provider)

	# #################################################################################################

	def get_archive_channels(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue
			
			if channel['type'] == 'tv' and channel['timeshift'] > 0:
				self.add_archive_channel(channel['name'], channel['id'], channel['timeshift'], img=channel['picon'])

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for epg in self.cp.sledovanitv.get_epg(ts_from, ts_to).get(channel_id, []):
			start_ts = self.cp.sledovanitv.convert_time(epg["startTime"])
			end_ts = self.cp.sledovanitv.convert_time(epg["endTime"])
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start_ts), self.cp.timestamp_to_str(end_ts), _I(epg["title"]))
			
			info_labels = {
				'plot': epg.get('description'),
				'title': epg['title']
			}

			menu = {}
			self.cp.add_menu_item(menu, 'Nahrát pořad', cmd=self.cp.add_recording, event_id=epg['eventId'])
			self.cp.add_video(title, epg.get('poster'), info_labels, menu, cmd=self.cp.get_event_stream, video_title=str(epg["title"]), event_id=epg['eventId'])

# #################################################################################################


class SledovaniTVModuleRecordings(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Nahrávky", 'Tu najdete nahrávky vašich programů')

	# #################################################################################################

	def root(self):
		self.cp.add_dir("Naplánovat nahrávání", cmd=self.plan_recordings)
		self.cp.add_dir("Budoucí - plánováne", cmd=self.show_recordings, only_finished=False)
		self.cp.add_dir("Existujíci", cmd=self.show_recordings, only_finished=True)
	
	# #################################################################################################

	def show_recordings(self, only_finished=True):
		enable_adult = self.cp.get_setting('enable_adult')

		if only_finished:
			def check_recording_state(s1, s2):
				return s1 == s2
		else:
			def check_recording_state(s1, s2):
				return s1 != s2

		def convert_time(t):
			return t[8:10] + "." + t[5:7] + ". " + t[11:16]

		for record in self.cp.sledovanitv.get_recordings():
			if not enable_adult and record.get('channelLocked', '') == 'pin':
				continue

			if check_recording_state(record["enabled"], 1):
				event = record.get('event', {})

				desc = event.get("title", '')

				if 'expires' in record:
					desc += ' [expiruje ' + datetime.strptime(record["expires"], "%Y-%m-%d").strftime("%d.%m.%Y") + ']'

				title = convert_time(event["startTime"]) + " - " + event["endTime"][11:16] + " [" + record["channelName"] + "] " + _I(record["title"])

				info_labels = {
					'title': record["title"],
					'plot': desc + '\n' + event.get('description', ''),
					'year': event.get("year"),
					'duration': record.get("eventDuration", 0) * 60
				}
				
				menu = {}
				self.cp.add_menu_item(menu, 'Smazat nahrávku', cmd=self.del_recording, pvr_id=record["id"])
				
				if record["enabled"] != 1:
					self.cp.add_video(title, event.get("poster"), info_labels, menu)
				else:
					self.cp.add_video(title, event.get("poster"), info_labels, menu, cmd=self.play_recording, pvr_title=record["title"], pvr_id=record["id"])

	
	# #################################################################################################

	def play_recording(self, pvr_title, pvr_id):
		for one in self.cp.sledovanitv.get_recording_link(pvr_id, self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(pvr_title, one['url'], info_labels)

	# #################################################################################################

	def del_recording(self, pvr_id):
		self.cp.sledovanitv.delete_recording(pvr_id)
		self.cp.refresh_screen()

	# #################################################################################################
	
	def plan_recordings(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			self.cp.add_dir(channel['name'], img=channel['picon'], cmd=self.show_future_days, channel_id=channel['id'])

	# #################################################################################################

	def show_future_days(self, channel_id):
		for i in range(7):
			if i == 0:
				day_name = "Dnes"
			elif i == 1:
				day = date.today() + timedelta(days=i)
				day_name = "Zítra " + day.strftime("%d.%m.%Y")
			else:
				day = date.today() + timedelta(days=i)
				day_name = DAY_NAME[day.weekday()] + " " + day.strftime("%d.%m.%Y")

			self.cp.add_dir(day_name, cmd=self.plan_recordings_for_channel, channel_id=channel_id, day=i)
	
	# #################################################################################################
	
	def plan_recordings_for_channel(self, channel_id, day):
		if day == 0:
			from_datetime = datetime.now()
			to_datetime = datetime.combine(date.today(), datetime.max.time())
		else:
			from_datetime = datetime.combine(date.today(), datetime.min.time()) + timedelta(days=day)
			to_datetime = datetime.combine(from_datetime, datetime.max.time())

		from_ts = int(time.mktime(from_datetime.timetuple()))
		to_ts = int(time.mktime(to_datetime.timetuple()))

		for event in self.cp.sledovanitv.get_epg(from_ts, to_ts).get(channel_id, []):
			startts = self.cp.sledovanitv.convert_time(event["startTime"])
			start = datetime.fromtimestamp(startts)
			endts = self.cp.sledovanitv.convert_time(event["endTime"])
			end = datetime.fromtimestamp(endts)
			event_id = event['eventId']

			title = start.strftime("%H:%M") + " - " + end.strftime("%H:%M") + " | " + event["title"]

			info_labels = {
				'plot': event.get('description'),
				'title': event['title']
			}
			img = event.get('poster')

			menu = {}
			self.cp.add_menu_item(menu, 'Nahrát pořad', cmd=self.cp.add_recording, event_id=event_id)
			self.cp.add_video(title, img, info_labels, menu, cmd=self.cp.add_recording, event_id=event_id)
		
# #################################################################################################


class SledovaniTVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, "Speciálni sekce")

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self):
		info_labels = {'plot': "Tu si můžete zobrazit a případně vymazat/odregistrovat zbytečná zařízení, aby ste se mohli znova jinde přihlásit." }
		self.cp.add_dir('Zaregistrovaná zařízení', info_labels=info_labels, cmd=self.list_devices)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.sledovanitv.get_devices():
			title = 'ID: %d, %s: %s' % (pdev['deviceId'], pdev["typeName"], pdev['title'])
			info_labels = { 'plot': 'V menu můžete zařízení vymazat pomocí Smazat zařízení!'}

			menu = {}
			if pdev['self']:
				title += _C('yellow', ' *')
			else:
				self.cp.add_menu_item(menu, 'Smazat zařízení!', self.delete_device, device_id=pdev["deviceId"])

			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################
	
	def delete_device(self, device_id):
		self.cp.sledovanitv.device_remove(device_id)
#		self.cp.add_video(_C('red', 'Zařízení %s bylo vymazáno!' % device_id), download=False)
		self.cp.add_video(_C('red', 'Tato operace zatím není implementována'), download=False)

# #################################################################################################


class SledovaniTVContentProvider(ModuleContentProvider):
	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='SledovaniTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'serialid')
		self.login_optional_settings_names = ('pin')

		self.sledovanitv = None
		self.channels = []
		self.channels_by_id = {}
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint

		if not self.get_setting('serialid'):
			self.set_setting('serialid', SledovaniTV.create_serialid())

		self.bxeg = SledovaniTVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			CPModuleSearch(self, 'Vyhledat'),
			SledovaniTVModuleHome(self),
			SledovaniTVModuleLiveTV(self),
			SledovaniTVModuleRadio(self),
			SledovaniTVModuleArchive(self),
			SledovaniTVModuleRecordings(self),
			SledovaniTVModuleExtra(self)
		]

	# #################################################################################################
	
	def login(self, silent):
		self.sledovanitv = None
		self.channels = []
		self.channels_by_id = {}

		sledovanitv = SledovaniTV(self.get_setting('username'), self.get_setting('password'), self.get_setting('pin'), self.get_setting('serialid'), self.data_dir, self.log_info)
		if not sledovanitv.check_pairing():
			raise LoginException('Přihlášení selhalo')

		self.sledovanitv = sledovanitv

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
		
		self.channels = self.sledovanitv.get_channels()
		self.checksum = self.get_channels_checksum()
		
		self.channels_by_id = {}
		for ch in self.channels:
			self.channels_by_id[ch['id']] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_url_by_channel_key(self, channel_key):
		self.load_channel_list()
		channel = self.channels_by_id.get(channel_key)

		if channel:
			streams = self.sledovanitv.get_live_link(channel['url'], self.get_setting('max_bitrate'))
			if len(streams) > 0:
				return streams[0]['url']

		return None

	# #################################################################################################

	def get_event_stream(self, video_title, event_id):
		for one in self.sledovanitv.get_event_link(event_id, self.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.add_play(video_title, one['url'], info_labels)

	# #################################################################################################

	def add_recording(self, event_id):
		ret = self.sledovanitv.add_recording(event_id)
		self.show_info("Nahrávka přidána" if ret else "Při přidávaní nahrávky nastala chyba")

	# #################################################################################################

	def search(self, keyword, search_id=''):
		if not self.sledovanitv:
			return

		for event in self.sledovanitv.search(keyword):
			if event['availability'] != "timeshift":
				continue

			start = self.sledovanitv.convert_time(event["startTime"])
			end = self.sledovanitv.convert_time(event["endTime"])

			day_name = DAY_NAME_SHORT[datetime.fromtimestamp(start).weekday()]
			title = day_name + ' ' + self.timestamp_to_str(start, format='%d.%m. %H:%M') + ' - ' + self.timestamp_to_str(end, format='%H:%M') + ' ' + _I(event['title']) + ' ' + _C('grey', '[' + event['channel'].upper() + ']')

			info_labels = {
				'plot': event.get("description"),
				'title': event["title"],
				'year': event.get("year")
			}

			menu = {}
			self.add_menu_item(menu, 'Nahrát pořad', self.add_recording, event_id=event['eventId'])
			self.add_video(title, event.get("poster"), info_labels, menu, cmd=self.get_event_stream, video_title=event["title"], event_id=event['eventId'])

	# #################################################################################################
