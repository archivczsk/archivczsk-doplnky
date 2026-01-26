# -*- coding: utf-8 -*-

import os
from datetime import datetime
import time
import json
from hashlib import md5
from functools import partial

from tools_archivczsk.contentprovider.extended import ModuleContentProvider, CPModuleLiveTV, CPModuleArchive, CPModuleTemplate, CPModuleSearch
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from tools_archivczsk.generator.lamedb import channel_name_normalise
from .oneplay import Oneplay
from .bouquet import OneplayTVBouquetXmlEpgGenerator
import base64

# #################################################################################################

class OneplayTVModuleLiveTV(CPModuleLiveTV):

	def __init__(self, content_provider):
		CPModuleLiveTV.__init__(self, content_provider, categories=True)

	# #################################################################################################

	def get_live_tv_categories(self):
		for item in self.cp.oneplay.get_channel_sets():
			self.add_live_tv_category(item['title'], item['id'])

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		enable_adult = self.cp.get_setting('enable_adult')
		enable_download = self.cp.get_setting('download_live')

		for channel in self.cp.oneplay.get_channels_by_set(cat_id):
			if not enable_adult and channel['adult']:
				continue

			epg = self.cp.oneplay.get_channel_current_epg(channel['id'])

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

			menu = self.cp.create_ctx_menu()
			if channel['timeshift'] > 0:
				menu.add_media_menu_item(self._("Play from beginnig"), cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'], startover=True)

			if channel['fav']:
				menu.add_menu_item(self._("Remove from favourites"), cmd=self.del_fav, key=channel['key'])
			else:
				menu.add_menu_item(self._("Add to favourites"), cmd=self.add_fav, key=channel['key'])

			self.cp.add_video(channel['name'] + epg_str, img=epg.get('img') or channel['logo'], info_labels=info_labels, menu=menu, download=enable_download, cmd=self.get_livetv_stream, channel_title=channel['name'], channel_key=channel['key'])

	# #################################################################################################

	def get_livetv_stream(self, channel_title, channel_key, startover=False):
		if startover:
			stream_info = self.cp.oneplay.get_startover_link(channel_key)
			fix_live='startover'
		else:
			stream_info = self.cp.oneplay.get_live_link(channel_key)
			fix_live = None

		self.cp.resolve_streams(stream_info, channel_title, fix=fix_live)

	# #################################################################################################

	def add_fav(self, key):
		self.cp.oneplay.add_fav_channel(key)
		self.cp.channels_next_load_time = 0
		self.cp.refresh_screen()

	# #################################################################################################

	def del_fav(self, key):
		self.cp.oneplay.remove_fav_channel(key)
		self.cp.channels_next_load_time = 0
		self.cp.refresh_screen()

# #################################################################################################


class OneplayTVModuleArchive(CPModuleArchive):

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
				self.add_archive_channel(channel['name'], channel['key'], channel['timeshift'], img=channel['logo'], info_labels={'adult': channel['adult']})

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		ts_from, ts_to = self.archive_day_to_datetime_range(archive_day, True)

		adult = self.cp.channels_by_key.get(channel_id,{}).get('adult', False)

		channel_number = self.cp.channels_by_key[channel_id]['number']

		for epg in self.cp.oneplay.get_channel_epg(channel_id, channel_number, ts_from, ts_to):
			rec_id = epg['id']

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), _I(epg["title"]))

			info_labels = {
				'plot': epg.get('desc'),
				'title': epg['title'],
				'adult': adult
			}

			menu = self.cp.create_ctx_menu()
			menu.add_menu_item(self._('Add to my list'), cmd=self.cp.mylist_add, item_id=rec_id)
			self.cp.add_video(title, epg.get('img'), info_labels, menu, cmd=self.get_archive_stream, channel_id=channel_id, epg=epg)

	# #################################################################################################

	def get_archive_hours(self, channel_id):
		self.cp.load_channel_list()
		channel = self.cp.channels_by_key.get(channel_id)
		return channel['timeshift'] if channel else None

	# #################################################################################################

	def get_archive_stream(self, channel_id, epg):
		cur_time = int(time.time())
		startover = self.cp.is_supporter() and cur_time > epg["start"] and cur_time < epg["end"]

		if startover:
			self.cp.get_module(OneplayTVModuleLiveTV).get_livetv_stream( str(epg["title"]), channel_id, True)
		else:
			stream_info = self.cp.oneplay.get_archive_link(epg['id'])
			self.cp.resolve_streams(stream_info, str(epg['title']), fix='duration', offset=int(self.cp.get_ssetting('archive_end_offset', 0)) * 60)

	# #################################################################################################

	def get_channel_id_from_path(self, path):
		if path.startswith('playlive/'):
			path = path[9:]
			if path.endswith('/index.mpd'):
				path = path[:-10]
			elif path.endswith('/index.m3u8'):
				path = path[:-11]
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
		self.cp.load_channel_list()
		adult = self.cp.channels_by_key.get(channel_id,{}).get('adult', False)
		channel_number = self.cp.channels_by_key[channel_id]['number']

		for epg in self.cp.oneplay.get_channel_epg(channel_id, channel_number, event_start - 14400, (event_end or event_start) + 14400):
			if abs(epg["start"] - event_start) > 60:
#				self.cp.log_debug("Archive event %d - %d doesn't match: %s" % (epg["start"], epg["end"], epg.get("title") or '???'))
				continue

			title = '%s - %s - %s' % (self.cp.timestamp_to_str(epg["start"]), self.cp.timestamp_to_str(epg["end"]), _I(epg["title"]))
			self.cp.log_debug("Found matching archive event: %s" % title)

			info_labels = {
				'plot': epg.get('desc'),
				'title': epg['title'],
				'adult': adult
			}

			self.cp.add_video(title, epg.get('img'), info_labels, cmd=self.get_archive_stream, channel_id=channel_id, epg=epg)
			break

# #################################################################################################

class OneplayTVModuleRecordings(CPModuleTemplate):

	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("Plan recording"), content_provider._('Here you can plan recordings for future programs'))

	# #################################################################################################

	def root(self):
		self.cp.load_channel_list()
		enable_adult = self.cp.get_setting('enable_adult')

		for channel in self.cp.channels:
			if not enable_adult and channel['adult']:
				continue

			self.cp.add_dir(channel['name'], img=channel['logo'], info_labels={'adult': channel['adult']}, cmd=self.plan_recordings_for_channel, channel_key=channel['key'])

	# #################################################################################################

	def plan_recordings_for_channel(self, channel_key):
		from_datetime = datetime.now()
		from_ts = int(time.mktime(from_datetime.timetuple()))
		to_ts = from_ts

		channel_number = self.cp.channels_by_key[channel_key]['number']

		for i in range(7):
			from_ts = to_ts
			to_ts = from_ts + 24 * 3600

			events = self.cp.oneplay.get_channel_epg(channel_key, channel_number, from_ts, to_ts)

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

				menu = self.cp.create_ctx_menu()
				menu.add_menu_item(self._('Add to my list'), cmd=self.cp.mylist_add, item_id=epg_id)
				self.cp.add_video(title, img, info_labels, menu, cmd=self.cp.mylist_add, item_id=epg_id)

# #################################################################################################

class OneplayTVModuleVOD(CPModuleTemplate):
	def __init__(self, content_provider):
		CPModuleTemplate.__init__(self, content_provider, content_provider._("VOD"))

	# #################################################################################################

	def add(self):
		for item in self.cp.oneplay.get_categories():
			self.cp.add_dir(item['title'], cmd=self.list_category, category_id=item['id'])

	# #################################################################################################

	def list_category(self, category_id, carousel_id=None, criteria=None):
		self.cp.ensure_supporter()
		for item in self.cp.oneplay.get_category_items(category_id, carousel_id, criteria):
			self.add_item_uni(item)

	# #################################################################################################

	def list_filter(self, category_id, filters):
		for item in self.cp.oneplay.get_filter_items(category_id, filters):
			self.add_item_uni(item)

	# #################################################################################################

	def list_series(self, series_id):
		for item in self.cp.oneplay.get_series_items(series_id):
			self.add_item_uni(item)

	# #################################################################################################

	def list_season(self, carousel_id, criteria):
		for item in self.cp.oneplay.get_season_items(carousel_id, criteria):
			self.add_item_uni(item)

	# #################################################################################################

	def list_carousel(self, carousel_id, criteria, page=0):
		for item in self.cp.oneplay.get_carousel_items(carousel_id, criteria, page):
			self.add_item_uni(item)

	# #################################################################################################

	def list_tab(self, tab_id, mylist=False):
		for item in self.cp.oneplay.get_tab_items(tab_id):
			self.add_item_uni(item, mylist)

	# #################################################################################################

	def play_item(self, item_title, item_id):
		stream_info = self.cp.oneplay.get_archive_link(item_id)
		self.cp.resolve_streams(stream_info, item_title)

	# #################################################################################################

	def list_related(self, item_id):
		for item in self.cp.oneplay.get_related(item_id):
			self.add_item_uni(item)

	# #################################################################################################

	def add_item_uni(self, item, mylist=False):
		def get_ctx_menu():
			menu = self.cp.create_ctx_menu()
			if mylist:
				menu.add_menu_item(self._('Remove from my list'), cmd=self.cp.mylist_remove, item_id=item['id'])
			else:
				menu.add_menu_item(self._('Add to my list'), cmd=self.cp.mylist_add, item_id=item['id'])

			menu.add_menu_item(self._('List related'), cmd=self.list_related, item_id=item['id'])

			return menu

		if item['type'] == 'filter':
			self.cp.add_dir(item['title'], item.get('img'), cmd=self.list_filter, category_id=item['id'], filters=item['filters'])
		elif item['type'] == 'category':
			self.cp.add_dir(item['title'], item.get('img'), cmd=self.list_category, category_id=item['id'], carousel_id=item.get('carousel_id'), criteria=item.get('criteria'))
		elif item['type'] == 'tab':
			self.cp.add_dir(item['title'], item.get('img'), cmd=self.list_tab, tab_id=item['id'], mylist=item.get('mylist'))
		elif item['type'] == 'series':
			info_labels = partial(self.cp.load_info_labels, item_id=item['id'])
			self.cp.add_dir(item['title'], item.get('img'), info_labels, get_ctx_menu(), cmd=self.list_series, series_id=item['id'])
		elif item['type'] == 'season':
			self.cp.add_dir(item['title'], item.get('img'), cmd=self.list_season, carousel_id=item['id'], criteria=item['criteria'])
		elif item['type'] == 'video':
			info_labels = partial(self.cp.load_info_labels, item_id=item['id'])
			title = item['title']
			if item.get('subtitle'):
				title += '  {}'.format(_I(item['subtitle']))

			self.cp.add_video(title, item.get('img'), info_labels, get_ctx_menu(), cmd=self.play_item, item_id=item['id'], item_title=item['title'])
		elif item['type'] == 'next':
			if item['subtype'] == 'carousel':
				self.cp.add_next(cmd=self.list_carousel, carousel_id=item['id'], criteria=item.get('criteria'), page=item['page'])


# #################################################################################################

class OneplayTVModuleExtra(CPModuleTemplate):

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

		info_labels = {'plot': self._("Here you can see the list of created profiles for this account and optionally change active one.") }
		self.cp.add_dir(self._('Profiles'), info_labels=info_labels, cmd=self.list_profiles)

		self.cp.add_video(self._("Run EPG export to enigma or XML files"), cmd=self.export_epg)

		info_labels = {'plot': self._("This will force login reset. New device identificator will be created and used for login.") }
		self.cp.add_video(self._('Reset login'), info_labels=info_labels, cmd=self.reset_login)

	# #################################################################################################

	def export_epg(self):
		self.cp.bxeg.refresh_xmlepg_start(True)
		self.cp.show_info(self._("EPG export started"), noexit=True)

	# #################################################################################################

	def list_devices(self):
		for pdev in self.cp.oneplay.get_devices():
			name = pdev["name"]

			if pdev['this_one']:
				name = _I(name)

			title = '{} [{}]'.format(name, pdev['type'])

			info_labels = {
				'plot': '{}: {}\n{}: {}'.format(self._("Last used"), pdev['last_used'], self._("Is streaming now"), 'yes' if pdev['is_streaming'] else 'no')
			}

			menu = {}
			if not pdev['this_one']:
				self.cp.add_menu_item(menu, self._('Remove device!'), self.delete_device, device_id=pdev["id"])

			self.cp.add_video(title, info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def delete_device(self, device_id):
		self.cp.oneplay.device_remove(device_id)
		self.cp.refresh_screen()

	# #################################################################################################

	def list_profiles(self):
		self.cp.oneplay.fill_profiles()

		for profile in self.cp.oneplay.profiles:
			name = profile['name']

			menu = self.cp.create_ctx_menu()
			if profile['id'] == self.cp.oneplay.profile_id:
				name += _I(' *')
				info_labels = {}
			else:
				info_labels = { 'plot': self._('In menu you can activate service using "Make activate"')}
				menu.add_menu_item(self._('Make active'), self.activate_profile, profile_id=profile['id'])

			self.cp.add_video(name, profile['img'], info_labels=info_labels, menu=menu, download=False)

	# #################################################################################################

	def activate_profile(self, profile_id):
		self.cp.oneplay.select_profile(profile_id)
		self.cp.load_channel_list(True)
		self.cp.bxeg.bouquet_settings_changed("", "")
		self.cp.refresh_screen()

	# #################################################################################################

	def reset_login(self):
		self.cp.oneplay.reset_login_data()
		self.cp.login(silent=False)
		self.cp.load_channel_list(True)
		if self.cp.oneplay:
			self.cp.show_info(self._('New login session using device ID {device_id} was created!').format(device_id=self.cp.oneplay.device_id))
		else:
			self.cp.show_error(self._('Failed to create new login session!'))

# #################################################################################################

class OneplayTVContentProvider(ModuleContentProvider):
	DOWNLOAD_FORMAT='mp4'

	def __init__(self):
		ModuleContentProvider.__init__(self, 'Oneplay')

		# list of settings used for login - used to auto call login when they change
		self.login_settings_names = ('username', 'password')

		self.oneplay = self.get_nologin_helper()
		self.channels = []
		self.channels_by_key = {}
		self.channels_next_load_time = 0
		self.checksum = None
		self.favourites = None
		self.scache = SimpleAutokeyExpiringCache()
		self.day_name_short = (self._("Mo"), self._("Tu"), self._("We"), self._("Th"), self._("Fr"), self._("Sa"), self._("Su"))
		self.register_shortcut('oneplay-md', self.shortcut_oneplay_md)

		self.bxeg = OneplayTVBouquetXmlEpgGenerator(self)

		self.modules = [
			CPModuleSearch(self),
			OneplayTVModuleLiveTV(self),
			OneplayTVModuleArchive(self),
			OneplayTVModuleVOD(self),
			OneplayTVModuleRecordings(self),
			OneplayTVModuleExtra(self)
		]

	# #################################################################################################

	def root(self):
		if self.get_setting('player-check'):
			PlayerFeatures.check_latest_exteplayer3(self)

		def account_choose(names):
			return self.get_list_input(names, self._("Select account"))

		if self.oneplay.refresh_login(account_choose_cbk=account_choose) == False:
			self.log_info("Canceling request - user is not logged in")
			return

		ModuleContentProvider.root(self)

	# #################################################################################################

	def login(self, silent):
		self.oneplay = self.get_nologin_helper()
		self.channels = []
		self.channels_by_key = {}
		self.channels_by_norm_name = {}

		oneplay = Oneplay(self)
		oneplay.refresh_login()
		self.oneplay = oneplay

		return True

	# #################################################################################################

	def get_channels_checksum(self):
		ctx = md5()
		for ch in self.channels:
			item = {
				'id': ch['id'],
				'name': ch['name'],
				'picon': ch['picon'],
				'adult': ch['adult'],
			}

			ctx.update(json.dumps(item, sort_keys=True).encode('utf-8'))

		return ctx.hexdigest()

	# #################################################################################################

	def load_channel_list(self, force=False):
		if not self.oneplay.is_logged_in():
			self.channels_by_key = {}
			self.channels_by_norm_name = {}
			return

		act_time = int(time.time())

		if not force and self.channels and self.channels_next_load_time > act_time:
			return

		self.channels = self.oneplay.get_channels()
		self.checksum = self.get_channels_checksum()

		self.channels_by_key = {}
		self.channels_by_norm_name = {}
		for ch in self.channels:
			self.channels_by_key[ch['key']] = ch
			self.channels_by_norm_name[channel_name_normalise(ch['name'])] = ch

		# allow channels reload once a hour
		self.channels_next_load_time = act_time + 3600

	# #################################################################################################

	def mylist_add(self, item_id):
		self.oneplay.mylist_add(item_id)
		self.show_info(self._("Item was added to my list"))

	# #################################################################################################

	def mylist_remove(self, item_id):
		self.oneplay.mylist_remove(item_id)
		self.show_info(self._("Item was removed from my list"))

	# #################################################################################################

	def mylist_add_remove(self, item_id):
		info = self.oneplay.get_item_detail(item_id)

		if info.get('mylist', False) == False:
			self.oneplay.mylist_add(item_id)
			self.show_info(self._("Item was added to my list"))
		else:
			self.oneplay.mylist_remove(item_id)
			self.show_info(self._("Item was removed from my list"))

	# #################################################################################################

	def load_info_labels(self, item_id):
		info = self.oneplay.get_item_detail(item_id)

		genre_str = ' / '.join(info.get('genre') or [])

		if info.get('playable') == False and info.get('playable_msg'):
			plot = '{}\n\n{}'.format(info['playable_msg'], info.get('plot') or '').strip()
		else:
			if genre_str:
				plot = '[' + genre_str + ']\n' + (info.get('plot') or '')
			else:
				plot = info.get('plot')

		return {
			'plot': plot,
			'genre': info.get('genre'),
			'year': info.get('year'),
			'duration': info.get('duration'),
			'rating': info.get('rating')
		}

	# #################################################################################################

	def search(self, keyword, search_id=''):
		self.ensure_supporter()
		add_item_uni = self.get_module(OneplayTVModuleVOD).add_item_uni
		for item in self.oneplay.search(keyword):
			add_item_uni(item)

	# #################################################################################################

	def get_ssetting(self, name, default_value):
		if self.is_supporter():
			return self.get_setting(name)
		else:
			return default_value

	# #################################################################################################

	def get_dash_info(self, stream_key):
		if 'url' in stream_key:
			# needed for playlive handler
			return stream_key

		cache_data = self.scache.get(stream_key['key'])

		ret_data = {
			'ext_drm_decrypt': self.get_setting('ext_drm_decrypt'),
			'url': cache_data['url'],
			'bandwidth': stream_key['bandwidth'],
			'fix': stream_key.get('fix'),
			'offset': stream_key.get('offset', 0),
		}

		drm_info = cache_data.get('drm', {})
		if drm_info.get('license_url') and drm_info.get('license_key'):
			ret_data.update({
				'drm' : {
					'wv': {
						'license_url': drm_info['license_url'],
						'headers': {
							'X-AxDRM-Message': drm_info['license_key']
						}
					}
				}
			})

		return ret_data

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return self.get_dash_info(stream_key)

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, playlist=None, fix=None, offset=0, drm=None):
		if not url:
			return

		supporter = self.is_supporter()
		streams = self.get_dash_streams(url, self.oneplay.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		play_settings = {
			'check_seek_borders': fix == 'startover',
			'playlist_on_start': playlist != None
		}

		cache_data = {
			'url': streams[0]['playlist_url'],
			'drm': drm or {}
		}

		cache_key = self.scache.put(cache_data)

		for one in streams:
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth'],
				'fix': fix,
				'offset': offset,
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('height', '720') + 'p'
			}

			if not supporter and int(info_labels['quality'][:-1]) > 720:
				continue

			if playlist:
				playlist.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)
				break
			else:
				self.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)

	# ##################################################################################################################

	def resolve_hls_streams(self, url, video_title, playlist=None, fix=None, offset=0):
		if not url:
			return

		supporter = self.is_supporter()
		streams = self.get_hls_streams(url, self.oneplay.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		play_settings = {
			'check_seek_borders': fix == 'startover',
			'playlist_on_start': playlist != None
		}

		cache_data = {
			'url': streams[0]['playlist_url'],
		}

		cache_key = self.scache.put(cache_data)

		for one in streams:
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth'],
				'fix': fix,
				'offset': offset,
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x720').split('x')[1] + 'p'
			}
			if not supporter and int(info_labels['quality'][:-1]) > 720:
				continue

			if playlist:
				playlist.add_play(video_title, stream_key_to_hls_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)
				break
			else:
				self.add_play(video_title, stream_key_to_hls_url(self.http_endpoint, key), info_labels=info_labels, settings=play_settings)

	# ##################################################################################################################

	def resolve_md_stream(self, item, playlist_on_start=False):
		stream_info = self.oneplay.get_stream_url(item['id'], item['start_mode'], True)
		stream_type = stream_info.get('type')

		if stream_type == 'dash':
			self.resolve_dash_streams(stream_info['url'], item['title'], self if playlist_on_start else None, item.get('fix'), item.get('offset', 0), stream_info.get('drm'))
		elif stream_type == 'hls':
			self.resolve_hls_streams(stream_info['url'], item['title'], self if playlist_on_start else None, item.get('fix'), item.get('offset', 0))

	# ##################################################################################################################

	def resolve_streams(self, stream_info, video_title, fix=None, offset=0):
		stream_type = stream_info.get('type')

		if stream_info.get('md'):
			# we have multidimension
			playlist = self.add_playlist(self._("Multidimension - select stream"))
			md_item = {
				'title': video_title,
				'fix': fix,
				'offset': offset,
				'id': stream_info['id'],
				'start_mode': stream_info['start_mode']
			}
			playlist.add_video(video_title, cmd=self.resolve_md_stream, item=md_item, playlist_on_start=True)

			for item in stream_info['md']:
				md_item = {
					'title': item['title'],
					'fix': fix,
					'offset': offset,
					'id': item['id'],
					'start_mode': item['start_mode']
				}
				playlist.add_video(item['title'], cmd=self.resolve_md_stream, item=md_item)

			return

		if stream_type == 'dash':
			self.resolve_dash_streams(stream_info['url'], video_title, None, fix, offset, stream_info.get('drm'))
		elif stream_type == 'hls':
			self.resolve_hls_streams(stream_info['url'], video_title, None, fix, offset)

	# ##################################################################################################################

	def shortcut_oneplay_md(self, stream_info, play_idx=0):
		playlist = self.add_playlist('Multidimension')
		items = [stream_info['md'][play_idx]]
		items.extend(stream_info['md'][:play_idx])
		items.extend(stream_info['md'][play_idx+1:])

		for item in items:
			md_item = {
				'title': item['title'],
				'fix': stream_info.get('fix'),
				'offset': stream_info.get('offset',0),
				'id': item['id'],
				'start_mode': item['start_mode']
			}
			playlist.add_video(item['title'], cmd=self.resolve_md_stream, item=md_item)

	# ##################################################################################################################
