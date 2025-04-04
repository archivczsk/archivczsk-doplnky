# -*- coding: utf-8 -*-

import os
from datetime import datetime
import time
import json
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .o2tv import O2TV
from .bouquet import O2TVBouquetXmlEpgGenerator
import base64


class O2TVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=True)

	# #################################################################################################

	def get_live_tv_categories(self, section=None):
		if section == None:
			self.add_live_tv_category(self._('All channels'), None)
			self.cp.add_dir(self._('Favourites'), cmd=self.get_live_tv_categories, section='fav')
		elif section == 'fav':
			self.cp.load_favourites()
			self.show_my_list(self.cp.favourites, fav=True)

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

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')
		show_md_subchannels = self.cp.get_ssetting('show_md_subchannels', False)

		if channels == None:
			channels = self.cp.channels
			epg_data = self.cp.o2tv.get_current_epg()
		else:
			epg_data = self.cp.o2tv.get_current_epg([ch['id'] for ch in channels])

		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			if channel['md_subchannel'] and show_md_subchannels == False:
				continue

			epg = epg_data.get(channel['id'])

			if show_md_subchannels == False and epg and epg.get('mosaic_id'):
				epg = self.cp.o2tv.get_mosaic_info(epg['mosaic_id'], True)

			if epg:
				epg_str = '  ' + _I(epg["title"])
				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), epg["desc"]),
					'title': epg["title"],
					'img': epg['img'],
					'adult': channel['adult']
				}
			else:
				epg_str = ''
				info_labels = {
					'adult': channel['adult']
				}

			menu = {}
			if channel['startover']:
				self.cp.add_media_menu_item(menu, self._("Play from beginnig"), cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'], channel_id=channel['id'], startover=True)

			if fav:
				self.cp.add_menu_item(menu, self._("Remove from favourites"), cmd=self.del_fav, key=channel['key'])
			else:
				self.cp.add_menu_item(menu, self._("Add to favourites"), cmd=self.add_fav, key=channel['key'])

			self.cp.add_video(channel['name'] + epg_str, img=channel['logo'], info_labels=info_labels, menu=menu, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'], channel_id=channel['id'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key, channel_id, startover=False):
		if startover:
			self.cp.ensure_supporter()

		show_md_subchannels = self.cp.get_ssetting('show_md_subchannels', False)
		fix_live = None

		if show_md_subchannels == False:
			epg_data = self.cp.o2tv.get_current_epg([channel_id])
		else:
			epg_data = {}

		mi_set = False
		if show_md_subchannels == False:
			mosaic_id = epg_data.get(channel_id, {}).get('mosaic_id')

			if mosaic_id:
				# this is mosaic event - extract mosaic streams and add it to playlist
				playlist = self.cp.add_playlist(channel_title)
				for mi in self.cp.o2tv.get_mosaic_info(mosaic_id, True).get('mosaic_info', []):
					if startover:
						url = self.cp.o2tv.get_startover_link(mi['id'])
						fix_live='startover'
					else:
						url = self.cp.o2tv.get_live_link(mi['id'])

					self.cp.resolve_dash_streams(url, mi['title'], playlist=playlist, fix=fix_live)
					mi_set = True

		if mi_set == False:
			if startover:
				url = self.cp.o2tv.get_startover_link(channel_key)
				fix_live='startover'
			else:
				url = self.cp.o2tv.get_live_link(channel_key)

			self.cp.resolve_dash_streams(url, channel_title, fix=fix_live)

	# #################################################################################################

	def add_fav(self, key):
		if key not in self.cp.favourites:
			self.cp.favourites.append(key)
			self.cp.save_favourites()
			self.cp.show_info(self._('Added to favourites'))
		else:
			self.cp.show_info(self._('Channel is already in favourites'))

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
		show_md_subchannels = self.cp.get_ssetting('show_md_subchannels', False)

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			if channel['md_subchannel'] and show_md_subchannels == False:
				continue

			if channel['timeshift'] > 0:
				self.add_archive_channel(channel['name'], channel['key'], channel['timeshift'], img=channel['logo'], info_labels={'adult': channel['adult']})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		show_md_subchannels = self.cp.get_ssetting('show_md_subchannels', False)
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		adult = self.cp.channels_by_key.get(channel_id,{}).get('adult', False)

		for epg in self.cp.o2tv.get_channel_epg(channel_id, ts_from, ts_to):
			mosaic_id = epg['mosaic_id'] if show_md_subchannels == False else None

			rec_id = epg['id']

			if mosaic_id:
				# if this is mosaic event, then replace current epg info with mosaic one
				epg = self.cp.o2tv.get_mosaic_info(mosaic_id)

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), _I(epg["title"]))

			info_labels = {
				'plot': epg.get('desc'),
				'title': epg['title'],
				'adult': adult
			}

			menu = {}
			self.cp.add_menu_item(menu, self._('Record the event'), cmd=self.cp.add_recording, epg_id=rec_id)
			self.cp.add_video(title, epg.get('img'), info_labels, menu, cmd=self.get_archive_stream, epg_title=str(epg["title"]), epg_id=epg['id'], epg=epg)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_key.get(channel_id)
		return channel['timeshift'] if channel else None

	# #################################################################################################

	def get_archive_stream(self, epg_title, epg_id, epg):
		show_md_subchannels = self.cp.get_ssetting('show_md_subchannels', False)
		mosaic_info=epg.get('mosaic_info',[]) if show_md_subchannels == False else []

		cur_time = int(time.time())
		startover = self.cp.is_supporter() and cur_time > epg["start"] and cur_time < epg["end"]

		if len(mosaic_info) > 0:
			playlist = self.cp.add_playlist(epg_title)
			for mi in mosaic_info:
				url = self.cp.o2tv.get_archive_link(mi['id'])
				self.cp.resolve_dash_streams(url, mi['title'], playlist=playlist)
		else:
			url = self.cp.o2tv.get_archive_link(epg_id)
			self.cp.resolve_dash_streams(url, epg_title, fix='startover' if startover else 'duration', offset=int(self.cp.get_ssetting('archive_end_offset', 0)) * 60)

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			path = path[9:]
			if path.endswith('/index.mpd'):
				path = path[:-10]
			channel_id = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			channel = self.cp.channels_by_key.get(channel_id, {})
			return channel_id if channel.get('timeshift') else None

		return None

	# #################################################################################################

	def get_channel_id_from_sref(self, sref):
		name = channel_name_normalise(sref.getServiceName())

		channel = self.cp.channels_by_norm_name.get(name, {})
		return channel.get('key') if channel.get('timeshift') else None

	# #################################################################################################

	def get_archive_event(self, channel_id, event_start, event_end=None):
		export_md_subchannels = self.cp.get_ssetting('export_md_subchannels', False)
		adult = self.cp.channels_by_key.get(channel_id,{}).get('adult', False)

		for epg in self.cp.o2tv.get_channel_epg(channel_id, event_start - 14400, (event_end or event_start) + 14400):
			if abs(epg["start"] - event_start) > 60:
#				self.cp.log_debug("Archive event %d - %d doesn't match: %s" % (epg["start"], epg["end"], epg.get("title") or '???'))
				continue

			mosaic_id = epg['mosaic_id'] if export_md_subchannels else None

			if mosaic_id:
				# if this is mosaic event, then replace current epg info with mosaic one
				epg = self.cp.o2tv.get_mosaic_info(mosaic_id)

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), _I(epg["title"]))
			self.cp.log_debug("Found matching archive event: %s" % title)

			info_labels = {
				'plot': epg.get('desc'),
				'title': epg['title'],
				'adult': adult
			}

			self.cp.add_video(title, epg.get('img'), info_labels, cmd=self.get_archive_stream, epg_title=str(epg["title"]), epg_id=epg['id'], epg=epg)
			break

# #################################################################################################


class O2TVModuleRecordings(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Recordings"), content_provider._('Here you will find recordings of your programs'))

	# #################################################################################################

	def root(self):
		self.cp.add_dir(self._("Plan recording"), cmd=self.plan_recordings)
		self.cp.add_dir(self._("Futures - planed"), cmd=self.show_recordings, only_finished=False)
		self.cp.add_dir(self._("Existing"), cmd=self.show_recordings, only_finished=True)

	# #################################################################################################

	def show_recordings(self, only_finished=True):
		recordings = {}

		if only_finished:
			recordings = self.cp.o2tv.get_recordings()
		else:
			recordings = self.cp.o2tv.get_future_recordings()

		for rec in recordings:
			metas = rec.get('metas', {})
			rating = metas.get('o2-rating', {}).get('value', '%')[:-1]
			year = metas.get('year', {}).get('value')

			img = None
			for i in rec.get('images', []):
				img = i.get('url')

				if i.get('ratio') == '2x3':
					img = i.get('url','') + '/height/720/width/480'
					break

			info_labels = {
				'plot': '[' + self._('Available until') + ': %s]\n%s' % (self.cp.timestamp_to_str(rec['viewableUntilDate'], '%d.%m. %H:%M'), rec['description']),
				'rating': int(rating) / 10 if rating else None,
				'year': int(year) if year else None,
				'title': rec["name"]
			}

			channel = self.cp.channels_by_key.get(str(rec.get('linearAssetId')),{}).get('name') or '???'
			title = rec["name"] + " (" + channel + " | " + self.cp.timestamp_to_str(rec['startDate'], '%d.%m. %H:%M') + " - " + self.cp.timestamp_to_str(rec['endDate']) + ")"

			menu = {}
			self.cp.add_menu_item(menu, self._('Delete recording'), cmd=self.del_recording, rec_id=int(rec['recordingId']), future=not only_finished)

			if only_finished:
				self.cp.add_video(title, img, info_labels, menu, cmd=self.play_recording, rec_title=title, rec_id=int(rec['recordingId']))
			else:
				self.cp.add_video(title, img, info_labels, menu)

	# #################################################################################################

	def play_recording(self, rec_title, rec_id):
		url = self.cp.o2tv.get_recording_link(rec_id)
		self.cp.resolve_dash_streams(url, rec_title)

	# #################################################################################################

	def del_recording(self, rec_id, future):
		self.cp.o2tv.delete_recording(rec_id, future)
		self.cp.refresh_screen()

	# #################################################################################################

	def plan_recordings(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			if channel['md_subchannel']:
				continue

			self.cp.add_dir(channel['name'], img=channel['logo'], info_labels={'adult': channel['adult']}, cmd=self.plan_recordings_for_channel, channel_key=channel['key'])

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
				startts = event["start"]
				start = datetime.fromtimestamp(startts)
				endts = event["end"]
				end = datetime.fromtimestamp(endts)
				epg_id = event['id']

				title = self.cp.day_name_short[start.weekday()] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["title"]

				info_labels = {
					'plot': event.get('desc'),
					'title': event['title']
				}
				img = event.get('img')

				menu = {}
				self.cp.add_menu_item(menu, self._('Record the event'), cmd=self.cp.add_recording, epg_id=epg_id)
				self.cp.add_video(title, img, info_labels, menu, cmd=self.cp.add_recording, epg_id=epg_id)

# #################################################################################################


class O2TVModuleExtra(CPModuleTemplate):

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

		info_labels = {'plot': self._("Here you can see the list of available services for this account and optionally change active one.") }
		self.cp.add_dir(self._('Available services'), info_labels=info_labels, cmd=self.list_services)

		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

		info_labels = {'plot': self._("This will force login reset. New device identificator will be created and used for login.") }
		self.cp.add_video(self._('Reset login'), info_labels=info_labels, cmd=self.reset_login)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.o2tv.get_devices():
			name = pdev["name"]

			if pdev['this_one']:
				name += _C('yellow', '*')

			title = pdev['type'] + '(' + name + ')' + " - " + self.cp.timestamp_to_str(pdev["activatedOn"], format='%d.%m.%Y %H:%M') + " - " + pdev["id"]
			info_labels = { 'plot': self._('In menu you can remove device using Remove device!')}

			menu = {}
			self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_id=pdev["id"])
			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_id):
		ret = self.cp.o2tv.device_remove(device_id)

		if ret:
			self.cp.show_info(self._('Device {device} was removed!').format(device=device_id))
		else:
			self.cp.show_info(self._('Failed to remove device {device}!').format(device=device_id))

	# #################################################################################################

	def list_services(self):
		self.cp.o2tv.refresh_configuration()

		for service in self.cp.o2tv.services:
			title = service['name'] or str(service['id'])

			menu = {}
			if service['id'] == self.cp.o2tv.active_service:
				title += _C('yellow', ' *')
				info_labels = {}
			else:
				info_labels = { 'plot': self._('In menu you can activate service using "Make activate"')}
				self.cp.add_menu_item(menu, self._('Make active'), self.activate_service, service_name=service['name'], service_id=service['id'])

			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def activate_service(self, service_name, service_id):
		self.cp.o2tv.activate_service(service_id)
		self.cp.add_video(_C('red', self._('Service {service} was activated!').format(service=service_name)), download=False)
		self.cp.load_channel_list(True)
		self.cp.bxeg.bouquet_settings_changed("", "")

	# #################################################################################################

	def reset_login(self):
		self.cp.o2tv.reset_login_data()
		self.cp.login(silent=True)
		self.cp.load_channel_list()
		if self.cp.o2tv:
			self.cp.show_info(self._('New login session using device ID {device_id} was created!').format(device_id=self.cp.o2tv.deviceid))
		else:
			self.cp.show_error(self._('Failed to create new login session!'))

# #################################################################################################

class O2TVContentProvider(ModuleContentProvider):
	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='O2 TV 2.0', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password')

		self.o2tv = self.get_nologin_helper()
		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint
		self.favourites = None
		self.scache = SimpleAutokeyExpiringCache()
		self.day_name_short = (self._("Mo"), self._("Tu"), self._("We"), self._("Th"), self._("Fr"), self._("Sa"), self._("Su"))

		self.bxeg = O2TVBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			CPModuleSearch(self, self._('Search')),
			O2TVModuleLiveTV(self),
			O2TVModuleArchive(self),
			O2TVModuleRecordings(self),
			O2TVModuleExtra(self)
		]

		self.load_favourites()

	# #################################################################################################

	def root(self):
		if self.get_setting('player-check'):
			PlayerFeatures.check_latest_exteplayer3(self)

		if not self.is_supporter():
			msgs  = [ self._("You have enabled these options in addon settings:"), '\n' ]
			if self.get_setting('show_md_subchannels'):
				msgs.append(self._("Show multidimension subchannels"))

			if self.get_setting('export_md_subchannels'):
				msgs.append(self._("Export multidimension subchannels"))

			if int(self.get_setting('archive_end_offset')) > 0:
				msgs.append(self._("How many minutes to play after event ends in archive"))

			try:
				if len(msgs) > 2:
					self.ensure_supporter('\n'.join(msgs) + '\n')
			except:
				pass

		ModuleContentProvider.root(self)

	# #################################################################################################

	def login(self, silent):
		self.o2tv = self.get_nologin_helper()
		self.channels = []
		self.channels_by_key = {}
		self.channels_by_norm_name = {}

		o2tv = O2TV(self)
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
				'adult': ch['adult'],
				'service': ch['service']
			}

			ctx.update(json.dumps(item, sort_keys=True).encode('utf-8'))

		ctx.update(str(self.is_supporter()).encode('utf-8'))
		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self, force=False):
		act_time = int(time.time())

		if not force and self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.o2tv.get_channels()
		self.checksum = self.get_channels_checksum()

		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		for ch in self.channels:
			self.channels_by_key[ch['key']] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

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

	def add_recording(self, epg_id):
		ret = self.o2tv.add_recording(epg_id)
		self.show_info(self._("Recording added") if ret else self._("There was an error by adding recording"))

	# #################################################################################################

	def search(self, keyword, search_id=''):
		self.load_channel_list()

		for programs in self.o2tv.search(keyword):
			startts = programs["start"]
			start = datetime.fromtimestamp(startts)
			endts = programs["end"]
			end = datetime.fromtimestamp(endts)
			epg_id = programs["id"]

			channel = self.channels_by_key.get(str(programs['channel_id']),{}).get('name') or '???'

			title = programs["title"] + " (" + channel + " | " + self.day_name_short[start.weekday()] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"

			info_labels = {
				'plot': programs.get('desc'),
				'title': programs["title"]
			}

			menu = {}
			self.add_menu_item(menu, self._('Record the event'), self.add_recording, epg_id=epg_id)
			self.add_video(title, programs['img'], info_labels, menu, cmd=self.get_archive_stream, epg_title=programs["title"], epg_id=epg_id)

	# #################################################################################################

	def get_ssetting(self, name, default_value):
		if self.is_supporter():
			return self.get_setting(name)
		else:
			return default_value

	# #################################################################################################

	def get_archive_stream(self, epg_title, epg_id):
		url = self.o2tv.get_archive_link(epg_id)
		self.resolve_dash_streams(url, epg_title, fix='duration', offset=int(self.get_ssetting('archive_end_offset', 0)) * 60)

	# #################################################################################################

	def get_dash_info(self, stream_key):
		if 'url' in stream_key:
			# needed for playlive handler
			return stream_key

		url = self.scache.get(stream_key['key'])

		return {
			'url': url,
			'bandwidth': stream_key['bandwidth'],
			'fix': stream_key.get('fix'),
			'offset': stream_key.get('offset', 0),
		}

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, playlist=None, fix=None, offset=0):
		if not url:
			return

		streams = self.get_dash_streams(url, self.o2tv.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		play_settings = {
			'check_seek_borders': fix == 'startover',
			'playlist_on_start': playlist != None and self.get_setting('show_md_choice')
		}

		cache_key = self.scache.put(streams[0]['playlist_url'])

		for one in streams:
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth'],
				'fix': fix,
				'offset': offset,
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('height', '???') + 'p'
			}
			if playlist:
				playlist.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)
				break
			else:
				self.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)

	# ##################################################################################################################
