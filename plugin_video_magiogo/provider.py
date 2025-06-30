# -*- coding: utf-8 -*-

import time
import base64
import json
from hashlib import md5

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.generator.lamedb import channel_name_normalise
from tools_archivczsk.player.features import PlayerFeatures
from .magiogo import MagioGO
from .bouquet import MagioGOBouquetXmlEpgGenerator

# #################################################################################################


class MagioGOModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider, channel_type):
		if channel_type == 'VOD':
			name = content_provider._('VOD Channels')
			plot = content_provider._('Here you will find list of channels broadcasting video on demand')
		else:
			name = None
			plot = None

		CPModuleLiveTV.__init__(self, content_provider, name, img=None, plot=plot)
		self.channel_type = channel_type

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		self.cp.load_channel_list(True)

		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')

		for channel in self.cp.channels:
			if channel.type != self.channel_type:
				continue

			if not enable_adult and channel.adult:
				continue

			if channel.epg_name and channel.epg_desc:
				epg_str = '  ' + _I(channel.epg_name)

				info_labels = {
					'plot': '%s - %s\n%s' % (self.cp.timestamp_to_str(channel.epg_start), self.cp.timestamp_to_str(channel.epg_stop), channel.epg_desc),
					'title': channel.epg_name,
					'year': channel.epg_year,
					'duration': channel.epg_duration,
					'adult': channel.adult
				}
			else:
				epg_str = ""
				info_labels = {
					'adult': channel.adult
				}

			if channel.type == 'VOD':
				event_start = channel.epg_start
			else:
				event_start = None

			menu = self.cp.create_ctx_menu()
			if channel.archive > 0 and channel.epg_id:
				menu.add_media_menu_item(self._("Play from beginning"), cmd=self.get_startover_stream, channel_title=channel.name, event_id=channel.epg_id)

#			works only on some channels even if its is marked as supported
#			if channel.timeshift > 0:
#				menu.add_media_menu_item(self._("Play timeshift"), cmd=self.get_timeshift_stream, channel_title=channel.name, channel_id=channel.id)

			self.cp.add_video(channel.name + epg_str, channel.preview, info_labels, menu, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel.name, channel_id=channel.id, event_start=event_start)

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_id, event_start=None):
		index_url = self.cp.magiogo.get_stream_link(channel_id)
		return self.cp.resolve_streams(index_url, channel_title, event_start)

	# #################################################################################################

	def get_timeshift_stream(self, channel_title, channel_id):
		self.cp.ensure_supporter()
		index_url = self.cp.magiogo.get_stream_link(channel_id, service='TIMESHIFT')
		return self.cp.resolve_streams(index_url, channel_title, startover=True)

	# #################################################################################################

	def get_startover_stream(self, channel_title, event_id):
		self.cp.ensure_supporter()
		index_url = self.cp.magiogo.get_stream_link(event_id, 'ARCHIVE')
		return self.cp.resolve_streams(index_url, channel_title, startover=True)

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

			if channel.archive > 0:
				self.add_archive_channel(channel.name, channel.id, channel.archive, img=channel.picon, info_labels={'adult': channel.adult})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		for event in self.cp.magiogo.get_archiv_channel_programs(channel_id, ts_from, ts_to):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(event["start"]), self.cp.timestamp_to_str(event["stop"]), _I(event["title"]))

			info_labels = {
				'plot': event.get('plot'),
				'title': event["title"],
				'duration': event['duration'],
				'year': event['year']
			}

			self.cp.add_video(title, event['image'], info_labels, cmd=self.get_archive_stream, archive_title=str(event["title"]), event_id=event['id'], epg=event)

	# #################################################################################################

	def get_archive_stream(self, archive_title, event_id, epg):
		index_url = self.cp.magiogo.get_stream_link(event_id, 'ARCHIVE')

		cur_time = int(time.time())
		startover = self.cp.is_supporter() and cur_time > epg["start"] and cur_time < epg["stop"]

		return self.cp.resolve_streams(index_url, archive_title, startover=startover)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_key.get(channel_id)
		return channel.archive if channel else None

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			path = path[9:]
			if path.endswith('/index'):
				path = path[:-6]
			channel_id = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			channel = self.cp.channels_by_key.get(int(channel_id))
			return int(channel_id) if channel and channel.archive else None

		return None

	# #################################################################################################

	def get_channel_id_from_sref(self, sref):
		name = channel_name_normalise(sref.getServiceName())
		ch = self.cp.channels_by_norm_name.get(name)
		return ch.id if ch and ch.archive else None

       # #################################################################################################

	def get_archive_event(self, channel_id, event_start, event_end=None):
		for event in self.cp.magiogo.get_archiv_channel_programs(channel_id, event_start - 14400, (event_end or event_start) + 14400):
			title = '%s - %s - %s' % (self.cp.timestamp_to_str(event["start"]), self.cp.timestamp_to_str(event["stop"]), _I(event["title"]))

			if abs(event["start"] - event_start) > 60:
#				self.cp.log_debug("Archive event %d - %d doesn't match: %s - %s" % (event["start"], event["stop"], title, event.get("title") or '???'))
				continue

			self.cp.log_debug("Found matching archive event: %s" % title)

			info_labels = {
				'plot': event.get('plot'),
				'title': event["title"],
				'duration': event['duration'],
				'year': event['year']
			}

			self.cp.add_video(title, event['image'], info_labels, cmd=self.get_archive_stream, archive_title=str(event["title"]), event_id=event['id'], epg=event)
			break

# #################################################################################################


class MagioGOModuleExtra(CPModuleTemplate):

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
		info_labels = {'plot': self._("With this button you can check if playback works OK or it gives some error from the server.") }
		self.cp.add_dir(self._('Check playback'), info_labels=info_labels, cmd=self.check_playback)
		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.magiogo.get_devices():
			title = pdev["name"] + "  -  " + pdev['cat']

			menu = {}
			if pdev['this']:
				title += ' *'
				info_labels = {}
			else:
				self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_name=pdev["name"], device_id=pdev["id"])
				info_labels = { 'plot': self._('In menu you can remove device using Remove device!') }

			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_name, device_id):
		ret, msg = self.cp.magiogo.remove_device(device_id)

		if ret:
			self.cp.add_video(_C('red', self._('Device {device} was removed!').format(device=device_name)), download=False)
		else:
			self.cp.add_video(_C('red', self._('Error') + ': %s' % msg), download=False)

	# #################################################################################################

	def check_playback(self):
		if len(self.cp.channels) > 0:
			channel = self.cp.channels[0]

			try:
				self.cp.magiogo.get_stream_link(channel.id)
			except Exception as e:
				self.cp.show_error(self._('Playback failed:') + '\n' + str(e))
			else:
				self.cp.show_info(self._('No error occured during playback check. Playback should work.'))
		else:
			self.cp.show_error(self._("Can't check playback. There are no channels available."))


# #################################################################################################


class MagioGOContentProvider(ModuleContentProvider):

	def __init__(self, settings, http_endpoint, data_dir=None, bgservice=None):
		ModuleContentProvider.__init__(self, name='MagioGO', settings=settings, data_dir=data_dir, bgservice=bgservice)

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('region', 'username', 'password', 'deviceid', 'devicetype')

		self.magiogo = self.get_nologin_helper()
		self.channels = []
		self.channels_next_load_time = 0
		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		self.epg_next_load_time = 0
		self.checksum = None
		self.http_endpoint = http_endpoint

		if not self.get_setting('deviceid'):
			self.set_setting('deviceid', MagioGO.create_device_id())

		self.bxeg = MagioGOBouquetXmlEpgGenerator(self, http_endpoint, None)

		self.modules = [
			MagioGOModuleLiveTV(self, channel_type='TV'),
			MagioGOModuleLiveTV(self, channel_type='VOD'),
			MagioGOModuleArchive(self),
			MagioGOModuleExtra(self)
		]

	# #################################################################################################

	def login(self, silent):
		self.magiogo = self.get_nologin_helper()
		self.channels = []

		magiogo = MagioGO(self)

		self.magiogo = magiogo

		return True

	# #################################################################################################

	def root(self):
		if self.get_setting('player-check'):
			try:
				PlayerFeatures.check_latest_exteplayer3(self)
			except:
				self.log_exception()

		return super(MagioGOContentProvider, self).root()

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

			ctx.update(json.dumps(item, sort_keys=True).encode('utf-8'))

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

		self.channels_by_key = {}
		self.channels_by_norm_name = {}

		for ch in self.channels:
			self.channels_by_key[int(ch.id)] = ch
			self.channels_by_norm_name[channel_name_normalise(ch.name)] = ch

		if fill_epg:
			# allow channels reload once a hour and epg once a minute
			self.epg_next_load_time = act_time + 60
			self.channels_next_load_time = act_time + 3600
		else:
			# allow channels reload once a hour
			self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def get_hls_info(self, stream_key):
		resp = {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
			'headers': {
				'User-Agent': self.magiogo.user_agent_playback
			}
		}

		if stream_key.get('cookies'):
			resp['headers']['Cookies'] = stream_key['cookies']

		if stream_key.get('fix'):
			resp['fix'] = stream_key['fix']

		return resp

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		return self.get_hls_info(stream_key)

	# ##################################################################################################################

	def resolve_hls_streams(self, url, video_title, player_settings):
		for one in (self.get_hls_streams(url, self.magiogo.req_session, max_bitrate=self.get_setting('max_bitrate')) or []):
			key = {
				'url': one['playlist_url'],
				'bandwidth': one['bandwidth'],
				'cookies': one['cookies']
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, stream_key_to_hls_url(self.http_endpoint, key), info_labels=info_labels, settings=player_settings)

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, player_settings, startover=False):
		for one in (self.get_dash_streams(url, self.magiogo.req_session, max_bitrate=self.get_setting('max_bitrate')) or []):
			key = {
				'url': one['playlist_url'],
				'bandwidth': one['bandwidth'],
				'cookies': one['cookies']
			}

			if startover:
				key['fix'] = 'startover'

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('height', '???') + 'p'
			}

			self.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels, settings=player_settings)

	# ##################################################################################################################

	def resolve_streams(self, url, video_title, event_start = None, startover=False):
		if not url:
			self.log_error("No stream url passed")
			return

		player_settings = {
			"resume_time_sec": int(time.time()) - event_start if event_start != None else None,
			"resume_popup": False,
			'check_seek_borders': startover
		}

		if self.magiogo.stream_type_by_device() == 'm3u8':
			return self.resolve_hls_streams(url, video_title, player_settings)
		else: # mpd
			return self.resolve_dash_streams(url, video_title, player_settings, startover)

	# ##################################################################################################################
