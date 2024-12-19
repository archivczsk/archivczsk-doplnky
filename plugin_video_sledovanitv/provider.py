# -*- coding: utf-8 -*-

from datetime import datetime, date, timedelta
import time
import json
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.contentprovider.exception import LoginException
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .sledovanitv import SledovaniTV
from .bouquet import SledovaniTVBouquetXmlEpgGenerator
import base64

# #################################################################################################


class SledovaniTVModuleHome(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Main page"))

	# #################################################################################################

	def root(self):

		for event in self.cp.sledovanitv.get_home():
			info_labels = {
				'plot': event.get('plot'),
				'duration': event.get('duration'),
				'title': event['title'],
			}

			day_name = self.cp.day_name_short[datetime.fromtimestamp(event['start']).weekday()]
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
		enable_download = self.cp.get_setting('download_live')

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
					'year': epg.get('year'),
					'adult': channel['adult']
				}
				img = epg.get('poster')
			else:
				epg_str = ''
				info_labels = {
					'adult': channel['adult']
				}
				img = None

			self.cp.add_video(title + epg_str, img, info_labels, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_url=channel['url'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_url):
		enable_download = self.cp.get_setting('download_live')

		for one in self.cp.sledovanitv.get_live_link(channel_url, self.cp.get_setting('max_bitrate')):
			info_labels = {
				'quality': one['quality'],
				'bandwidth': one['bandwidth']
			}
			self.cp.add_play(channel_title, one['url'], info_labels, download=enable_download)

# #################################################################################################


class SledovaniTVModuleRadio(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, content_provider._('Radios'), plot=content_provider._('Here you will find the list of radios available in your subscription'))

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		enable_download = self.cp.get_setting('download_live')
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

			self.cp.add_video(channel['name'] + epg_str, img, info_labels, download=enable_download, cmd=channel['url'])

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
				self.add_archive_channel(channel['name'], channel['id'], channel['timeshift'], img=channel['picon'], info_labels={'adult': channel['adult']})

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
			self.cp.add_menu_item(menu, self._('Add recording'), cmd=self.cp.add_recording, event_id=epg['eventId'])
			self.cp.add_video(title, epg.get('poster'), info_labels, menu, cmd=self.cp.get_event_stream, video_title=str(epg["title"]), event_id=epg['eventId'])

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_id.get(channel_id)
		return channel['timeshift'] if channel else None

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			channel_id = base64.b64decode(path[9:].encode('utf-8')).decode("utf-8")
			channel = self.cp.channels_by_id.get(channel_id, {})
			return channel_id if channel.get('timeshift') else None

		return None

	# #################################################################################################

	def get_channel_id_from_sref(self, sref):
		name = channel_name_normalise(sref.getServiceName())
		channel = self.cp.channels_by_norm_name.get(name, {})
		return channel.get('id') if channel.get('timeshift') else None

	# #################################################################################################

	def get_archive_event(self, channel_id, event_start, event_end=None):
		for epg in self.cp.sledovanitv.get_epg(event_start - 14400, (event_end or event_start) + 14400).get(channel_id, []):
			start_ts = self.cp.sledovanitv.convert_time(epg["startTime"])
			end_ts = self.cp.sledovanitv.convert_time(epg["endTime"])

			if (abs(start_ts) - event_start) > 60:
#				self.cp.log_debug("Archive event %d - %d doesn't match: %s" % (start_ts, end_ts, epg.get("title") or '???'))
				continue

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(start_ts), self.cp.timestamp_to_str(end_ts), _I(epg["title"]))

			info_labels = {
				'plot': epg.get('description'),
				'title': epg['title']
			}

			self.cp.add_video(title, epg.get('poster'), info_labels, cmd=self.cp.get_event_stream, video_title=str(epg["title"]), event_id=epg['eventId'])
			break

# #################################################################################################


class SledovaniTVModuleRecordings(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Recordings"), content_provider._('Here you will find recordings of your programs'))
		self.day_name = (_('Monday'), _('Tuesday'), _('Wednesday'), _('Thursday'), 	_('Friday'), _('Saturday'), _('Sunday'))

	# #################################################################################################

	def root(self):
		self.cp.add_dir(self._("Plan recording"), cmd=self.plan_recordings)
		self.cp.add_dir(self._("Futures - planed"), cmd=self.show_recordings, only_finished=False)
		self.cp.add_dir(self._("Existing"), cmd=self.show_recordings, only_finished=True)

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
			is_adult = record.get('channelLocked', '') == 'pin'

			if not enable_adult and is_adult:
				continue

			if check_recording_state(record["enabled"], 1):
				event = record.get('event', {})

				if not event:
					continue

				desc = event.get("title", '')

				if 'expires' in record:
					desc += ' [' + self._('expires') + ' ' + datetime.strptime(record["expires"], "%Y-%m-%d").strftime("%d.%m.%Y") + ']'

				title = convert_time(event["startTime"]) + " - " + event["endTime"][11:16] + " [" + record["channelName"] + "] " + _I(record["title"])

				info_labels = {
					'title': record["title"],
					'plot': desc + '\n' + event.get('description', ''),
					'year': event.get("year"),
					'duration': record.get("eventDuration", 0) * 60,
					'adult': is_adult
				}

				menu = {}
				self.cp.add_menu_item(menu, self._('Delete recording'), cmd=self.del_recording, pvr_id=record["id"])

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

			self.cp.add_dir(channel['name'], img=channel['picon'], info_labels={'adult': channel['adult']}, cmd=self.show_future_days, channel_id=channel['id'])

	# #################################################################################################

	def show_future_days(self, channel_id):
		for i in range(7):
			if i == 0:
				day_name = self._("Today")
			elif i == 1:
				day = date.today() + timedelta(days=i)
				day_name = self._("Tomorrow") + ' ' + day.strftime("%d.%m.%Y")
			else:
				day = date.today() + timedelta(days=i)
				day_name = self.day_name[day.weekday()] + " " + day.strftime("%d.%m.%Y")

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
			self.cp.add_menu_item(menu, self._('Record the event'), cmd=self.cp.add_recording, event_id=event_id)
			self.cp.add_video(title, img, info_labels, menu, cmd=self.cp.add_recording, event_id=event_id)

# #################################################################################################


class SledovaniTVModuleExtra(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Special section"))

	# #################################################################################################

	def add(self):
		if self.cp.get_setting('enable_extra'):
			CPModuleTemplate.add(self)

	# #################################################################################################

	def root(self):
		info_labels = {'plot': self._("Here you can show and optionaly remove/unregister unneeded devices, so you can login on another one.") }
		self.cp.add_dir(self._('Registered devices'), info_labels=info_labels, cmd=self.list_devices)
		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.sledovanitv.get_devices():
			title = 'ID: %d, %s: %s' % (pdev['deviceId'], pdev["typeName"], pdev['title'])
			info_labels = { 'plot': self._('In menu you can remove device using Remove device!')}

			menu = {}
			if pdev['self']:
				title += _C('yellow', ' *')
			else:
				self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_id=pdev["deviceId"])

			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_id):
		self.cp.sledovanitv.device_remove(device_id)
#		self.cp.add_video(_C('red', self._('Device {device} was removed!').format(device=device_id)), download=False)
		self.cp.add_video(_C('red', self._('This operation is not supported yet')), download=False)

# #################################################################################################


class SledovaniTVContentProvider(ModuleContentProvider):
	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='SledovaniTV', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password', 'serialid')
		self.login_optional_settings_names = ('pin')

		self.sledovanitv = self.get_nologin_helper()
		self.channels = []
		self.channels_by_id = {}
		self.channels_by_norm_name = {}
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint
		self.day_name_short = (self._("Mo"), self._("Tu"), self._("We"), self._("Th"), self._("Fr"), self._("Sa"), self._("Su"))

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
		self.sledovanitv = self.get_nologin_helper()
		self.channels = []
		self.channels_by_id = {}

		sledovanitv = SledovaniTV(self)
		if not sledovanitv.check_pairing():
			raise LoginException(self._('Login failed'))

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
			ctx.update(json.dumps(item, sort_keys=True).encode('utf-8'))

		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self):
		act_time = int(time.time())

		if self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.sledovanitv.get_channels()
		self.checksum = self.get_channels_checksum()

		self.channels_by_id = {}
		self.channels_by_norm_name = {}
		for ch in self.channels:
			self.channels_by_id[ch['id']] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

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
		self.show_info(self._("Recording added") if ret else self._("There was an error by adding recording"))

	# #################################################################################################

	def search(self, keyword, search_id=''):
		if not self.sledovanitv:
			return

		for event in self.sledovanitv.search(keyword):
			if event['availability'] != "timeshift":
				continue

			start = self.sledovanitv.convert_time(event["startTime"])
			end = self.sledovanitv.convert_time(event["endTime"])

			day_name = self.day_name_short[datetime.fromtimestamp(start).weekday()]
			title = day_name + ' ' + self.timestamp_to_str(start, format='%d.%m. %H:%M') + ' - ' + self.timestamp_to_str(end, format='%H:%M') + ' ' + _I(event['title']) + ' ' + _C('grey', '[' + event['channel'].upper() + ']')

			info_labels = {
				'plot': event.get("description"),
				'title': event["title"],
				'year': event.get("year")
			}

			menu = {}
			self.add_menu_item(menu, self._('Record the event'), self.add_recording, event_id=event['eventId'])
			self.add_video(title, event.get("poster"), info_labels, menu, cmd=self.get_event_stream, video_title=event["title"], event_id=event['eventId'])

	# #################################################################################################
