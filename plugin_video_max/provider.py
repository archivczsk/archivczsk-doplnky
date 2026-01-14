# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider, NoLoginHelper
from tools_archivczsk.contentprovider.exception import AddonErrorException, AddonSilentExitException
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from tools_archivczsk.date_utils import iso8601_to_timestamp
from time import time
from .wbdmax import WBDMax
import re
import sys

is_py2 = (sys.version_info[0] == 2)

class WBDMaxContentProvider(CommonContentProvider):
	def __init__(self):
		CommonContentProvider.__init__(self, 'Max')
		self.wbdmax = WBDMax(self)
		self.scache = SimpleAutokeyExpiringCache()
		self.drm_failed = False

	# ##################################################################################################################

	def build_lang_lists(self):
		self.dubbed_lang_list = self.get_dubbed_lang_list()
		self.log_info("Interface language set to: %s" % self.dubbed_lang_list[0])

	# ##################################################################################################################

	def get_dubbed_lang_list(self):
		dl = self.get_setting('dubbed-lang')

		if dl == 'auto':
			lang_code = self.get_lang_code()
			if lang_code == 'cs':
				return ['cs', 'sk']
			elif lang_code == 'sk':
				return ['sk', 'cs']
			else:
				return ['en']
		else:
			return dl.split('+')

	# ##################################################################################################################

	def select_profile_on_startup(self):
		if self.get_setting('select_profile') == False:
			return

		profiles = self.wbdmax.get_profiles()
		active_profile_id = self.wbdmax.get_active_profile_id()

		if len(profiles) < 2:
			return

		choices = []
		for i, p in enumerate(profiles):
			if p['id'] == active_profile_id:
				title = _I(p['profileName'])
			else:
				title = p['profileName']

			if p.get('pinRestricted'):
				title += ' (pin)'

			if p.get('ageRestricted'):
				title += ' (kid)'

			choices.append(title)

		answer = self.get_list_input(choices, self._("Select profile"))
		if answer == -1:
			return

		profile = profiles[answer]
		if profile['id'] == active_profile_id:
			return

		pin = None
		if profile.get('pinRestricted'):
			pin = self.get_text_input(self._("Enter PIN"), input_type='pin')
			if not pin:
				return

		self.wbdmax.switch_profile(profile['id'], pin=pin)
		self.scache.scache = {}

	# ##################################################################################################################

	def process_login(self, provider=False):
		self.log_debug("starting login process")

		if isinstance(self.wbdmax, NoLoginHelper):
			self.wbdmax = WBDMax(self)

		if not self.wbdmax.need_login():
			self.show_info(self._("You are already logged in. Please exit addon and run it again."))
			return

		url, code = self.wbdmax.get_device_code(provider)

		for i in range(30):
			msg = self._("Go to following URL and enter device code:\n\nURL: {url}\nDevice code: {code}").format(url=url, code=code)
			ret = self.show_info(msg, noexit=True, timeout=10)
			self.log_debug("show_info resp: %s" % ret)

			if ret == False:
				self.log_error("Login canceled by user")
				break

			if self.wbdmax.device_login():
				self.log_info("Login successful")
				break
			else:
				self.log_debug("Device login failed")
		else:
			self.log_error("Login timed out")

		self.exit_screen()

	# ##################################################################################################################

	def root(self):
		PlayerFeatures.check_latest_exteplayer3(self)

		self.build_lang_lists()

		if isinstance(self.wbdmax, NoLoginHelper) or self.wbdmax.need_login():
			self.add_video(self._("Start login process"), info_labels=self._("Use this if you want to pair this device with your HBO Max account."), cmd=self.process_login)

			if self.get_setting('login_using_provider'):
				self.add_video(self._("Start login process using provider"), info_labels=self._("Use this if you use login to HBO Max using provider, like google, amazon, ..."), cmd=self.process_login, provider=True)

			return

		self.select_profile_on_startup()

		self.add_main_menu()
		self.add_dir(self._("My items"), cmd=self.list_watchlist)

		self.add_dir(self._("Informations and settings"), cmd=self.list_info)

	# ##################################################################################################################

	def add_main_menu(self):
		data = self.wbdmax.get_collection('web-menu-bar')

		ignore = ['search-menu-item', 'my-stuff-menu-item']
		for row in data['items']:
			if row['collection']['name'] == 'search-menu-item':
				search_title = row['collection']['title']
				self.add_search_dir(search_title)
				continue

			if row.get('hidden') or row['collection']['name'] in ignore:
				continue

			self.add_dir(row['collection']['title'], cmd=self.list_page, route=row['collection']['items'][0]['link']['linkedContentRoutes'][0]['url'].lstrip('/'))

	# ##################################################################################################################

	def list_page(self, route, page=1, ignored_id=None):
		data = self.wbdmax.get_route(route, page)

		for row in data.get('items') or []:
			if 'collection' not in row:
				continue

			if 'component' in row['collection'] and row['collection']['component'].get('id') in ('hero','tab-group'):
				self._process_items(row['collection'].get('items', []), ignored_id=ignored_id)
				continue

			label = row['collection'].get('title')
			if label:
				self.add_dir(label, cmd=self.list_collection, collection_id=row['collection']['id'])

		self.add_paging(data.get('meta',{}), self.list_page, route=route, page=page+1)

	# ##################################################################################################################

	def add_paging(self, meta, cmd, **kwargs):
		if meta.get('itemsCurrentPage', 1) < meta.get('itemsTotalPages', 1):
			if 'page' not in kwargs:
				kwargs['page'] = meta.get('itemsCurrentPage', 1)
			self.add_next(cmd, **kwargs)

	# ##################################################################################################################

	def list_collection(self, collection_id, page=1):
		data = self.wbdmax.get_collection(collection_id, page=page)
		if 'items' not in data:
			return

		self._process_items(data['items'])
		self.add_paging(data['meta'], self.list_collection, collection_id=collection_id, page=page+1)

	# ##################################################################################################################

	def remove_viewed(self, item_id, show_id):
		if item_id and show_id:
			self.wbdmax.watchtime_reset(item_id, show_id)
			self.refresh_screen()

	# ##################################################################################################################

	def _art(self, images, only_keys=None):
		images = {x['kind']: x for x in images if x.get('src') and x.get('kind')}
		ART_MAP = {
			'clearlogo': {'kinds': ['logo-centered', 'content-logo-monochromatic', 'logo-left'], 'url_append': '?w=600', 'valid': lambda data: data['src'].lower().endswith('png')},
			'thumb': {'kinds': ['cover-artwork-square', 'poster-with-logo', 'default', 'cover-artwork'], 'url_append': '?w=600'},
			'poster': {'kinds': ['poster-with-logo'], 'url_append': '?w=600'},
			'fanart': {'kinds': ['default', 'default-wide']},
		}
		art = {}
		for key in only_keys or ART_MAP:
			art[key] = None
			for kind in ART_MAP[key]['kinds']:
				if kind in images:
					if ART_MAP[key].get('valid', lambda x: True)(images[kind]):
						art[key] = images[kind]['src'] + ART_MAP[key].get('url_append','')
						break
		return art.get('poster') or art.get('thumb') or art.get('fanart') or art.get('clearlogo')

	# ##################################################################################################################

	def _process_items(self, rows, add_show_title=False, ignored_id=None):
		for row in rows:
			self._process_item(row, add_show_title, ignored_id)

	# ##################################################################################################################

	def _process_item(self, row, add_show_title=False, ignored_id=None):
		data = row.get('show') or row.get('video') or row.get('taxonomyNode') or row.get('link') or row.get('collection') or row.get('airing')
		if not data:
			self.log_error("Unsupported ROW:\n%s" % row)
			return

		if ignored_id and data.get('id') == ignored_id:
			# needed to break endless recursion in some categories
			return

		data['name'] = data.get('title', data['name'])
		try:
			data['name'] = re.sub(r'\([0-9]{4}\)$', '', data['name']).strip()
			data['originaltitle'] = re.sub(r'\([0-9]{4}\)$', '', data['originaltitle']).strip()
		except:
			pass

		label = data['name']

		if data.get('secondaryTitle') and label and data.get('secondaryTitle') != label:
			label += ' - ' + data.get('secondaryTitle')

		for badge in data.get('badges', []):
			if badge['id'] == 'release-state-coming-soon':
				data['premiereDate'] = data['firstAvailableDate']
		#  label += ' [B][{}][/B]'.format(badge['displayText'])

		menu = self.create_ctx_menu()

		if data.get('viewingHistory',{}).get('viewed', False):
			menu.add_menu_item(self._("Remove from viewed"), cmd=self.remove_viewed, item_id=data.get('id'), show_id=data.get('show',{}).get('id'))

			if data.get('viewingHistory',{}).get('completed', False):
				label = label + ' ' + _I('*')
			else:
				label = label + ' *'

		edit = data.get('edit',{})

		# check if event is playable now
		playable_start = edit.get('playableStart')
		playable_end = edit.get('playableEnd')
		playable_start = iso8601_to_timestamp(playable_start) if playable_start else 0
		playable_end = iso8601_to_timestamp(playable_end) if playable_end else 0
		cur_time = int(time())

		if playable_end == 0 or (playable_start <= cur_time and playable_end > cur_time):
			playable_now = True
		else:
			playable_now = False
			label = _C('gray', label)

		year = data.get('premiereDate','')[:4]

		info_labels = {
			'sorttitle': data['name'],
			'originaltitle': data.get('originalName'),
			'plot': data.get('longDescription') or data.get('description') or '',
			'aired': data.get('premiereDate'),
			'genre': [x['name'] for x in data.get('txGenres', [])],
			'duration': edit.get('duration',0) // 1000,
			'year': int(year) if year else None,
			'title': data.get('originalName') or data.get('name')
		}

		if year:
			info_labels['title'] = '{} ({})'.format(info_labels['title'], year)

		if 'txCorporate-genre' in data:
			info_labels['plot'] = '[{}]\n{}'.format(data['txCorporate-genre'][0]['name'], info_labels['plot'])

		schedule_start = data.get('scheduleStart')
		schedule_end = data.get('scheduleEnd')

		if schedule_start and schedule_end:
			schedule_start = self.timestamp_to_str(iso8601_to_timestamp(schedule_start), '%d.%m.%Y %H:%M')
			schedule_end = self.timestamp_to_str(iso8601_to_timestamp(schedule_end))
			info_labels['plot'] = '[{} - {}]\n{}'.format(schedule_start, schedule_end, info_labels['plot'])

		img = self._art(data.get('images',{}))

		if data.get('primaryChannel'):
			info_labels['studio'] = data['primaryChannel']['name']

#		for rating in data.get('ratings', []):
#			if 'mpaa' in rating['contentRatingSystem']['system'].lower():
#				item.info['mpaa'] = rating['code']
#				break

		if 'trailerVideo' in data and 'edit' in data['trailerVideo']:
			menu.add_media_menu_item(self._("Trailer"), cmd=self.play_item, edit_id=data['trailerVideo']['edit']['id'], video_title=self._("Trailer") + ': ' + label)

		if 'shortPreviewVideo' in data:
			menu.add_media_menu_item(self._("Short preview"), cmd=self.play_item, edit_id=data['shortPreviewVideo']['edit']['id'], video_title=self._("Short preview") + ': ' + label)

		if data.get('isFavorite', False):
			menu.add_menu_item(self._("Remove from watchlist"), cmd=self.del_watchlist, item_id=data.get('show', data)['id'])
		else:
			menu.add_menu_item(self._("Add to watchlist"), cmd=self.add_watchlist, item_id=data.get('show', data)['id'])

		# bug in hbo sometimes returns missing the edit relationship for episode, so link to show instead (website does same)
		if data.get('videoType') == 'EPISODE' and 'edit' not in data:
			data['showType'] = 'SERIES'
			data['id'] = data['show']['id']

		if data.get('showType') in ('SERIES', 'TOPICAL', 'MINISERIES'):
			if data.get('showType') in ('SERIES', 'MINISERIES') and year:
				label = '{} ({})'.format(label, year)

			self.add_dir(label, img, info_labels, menu, cmd=self.list_series, series_id=data['id'])

		elif data.get('showType') in ('MOVIE', 'STANDALONE'):
			if data.get('showType') == 'MOVIE' and year:
				label = '{} ({})'.format(label, year)

			self.add_video(label, img, info_labels, menu, cmd=self.play_item, item_id=data['id'] if playable_now else None, video_title=label)

		elif data.get('videoType') == 'EPISODE':
			img = self._art(data['show']['images'])
			if not img:
				img = self._art(data['images'], only_keys=('thumb','poster'))

			info_labels.update({
				'mediatype': 'episode',
				'episode': data.get('episodeNumber'),
				'season': data.get('seasonNumber'),
				'tvshowtitle': data['show']['name'],
			})

			if add_show_title and info_labels.get('tvshowtitle'):
				label = '{} - {}'.format(info_labels['tvshowtitle'], label)

			menu.add_menu_item(self._("Go to series"), cmd=self.list_series, series_id=data['show']['id'])
			self.add_video(label, img, info_labels, menu, cmd=self.play_item, edit_id=data['edit']['id'], video_title=label, src_data=self.create_src_data(data))

		elif data.get('videoType') in ('STANDALONE_EVENT', 'CLIP', 'LIVE', 'MOVIE'):
			if data.get('videoType') == 'MOVIE' and year:
				label = '{} ({})'.format(label, year)

			self.add_video(label, img, info_labels, menu, cmd=self.play_item, edit_id=data['edit']['id'] if playable_now else None, video_title=label, src_data=self.create_src_data(data))

		elif row.get('collection'):
			# ignore collections without title
			if data.get('title'):
				self.add_dir(label, img, info_labels, cmd=self.list_collection, collection_id=data['id'])
			else:
				if 'items' in data:
					self._process_items(data['items'], add_show_title=True)
					self.add_paging(data['meta'], self.list_collection, collection_id=data['id'])

		elif data.get('kind') in ('genre', 'sporting-event'):
			self.add_dir(label, img, info_labels, cmd=self.list_page, route=data['routes'][0]['url'][1:], ignored_id=data.get('id'))

		elif data.get('kind') == 'Internal Link':
			self.add_dir(label, img, info_labels, cmd=self.list_page, route=data['linkedContentRoutes'][0]['url'][1:])

		elif row.get('airing') and data.get('distributionChannel'):
			event_start = data.get('scheduleStart')
			event_end = data.get('scheduleEnd')
			event_start = iso8601_to_timestamp(event_start) if event_start else 0
			event_end = iso8601_to_timestamp(event_end) if event_start else 0

			if event_start <= cur_time and event_end > cur_time:
				channel = data.get('distributionChannel')
				label = '{} ({})'.format(channel['name'], _I(label))
				self.add_video(label, img, info_labels, menu, cmd=self.play_item, edit_id=channel['edit']['id'], video_title=channel['name'])
		else:
			self.log_error("Unexpected data: {}".format(data))

	# ##################################################################################################################

	def create_src_data(self, data):
		ret = {}
		resume_from = self.wbdmax.fill_data_item(data, ret)
		return ret, resume_from

	# ##################################################################################################################

	def list_series(self, series_id, page=1, season=None):
		if season:
			data = self.wbdmax.get_season(series_id, season, page=page)
			self._process_items(data.get('items',[]))
			self.add_paging(data['meta'], self.list_series, series_id=series_id, page=page+1, season=season)
			return

		data = self.wbdmax.get_series(series_id)
		img = self._art(data.get('images',{}))

		for row in sorted(data.get('seasons', []), key=lambda x: x['seasonNumber']):
			# ignore empty seasons
			if not 'videoCountByType' in row or not row['videoCountByType'].get('EPISODE'):
				continue

			info_labels = {
				'plot': row.get('longDescription') or data.get('longDescription'),
				'plotoutline': row.get('description') or data.get('description'),
				'mediatype': 'season',
				'season': row['seasonNumber'],
				'tvshowtitle': data['name'],
			}

			self.add_dir(self._('Season') + ' {}'.format(row['displayName']), img, info_labels=info_labels, cmd=self.list_series, series_id=series_id, season=row['seasonNumber'])

	# ##################################################################################################################

	def list_info(self):
		self.add_dir(self._("Profiles"), cmd=self.list_profiles)
		self.add_dir(self._("Devices"), cmd=self.list_devices)
		self.add_dir(self._("Logout"), cmd=self.logout)

	# ##################################################################################################################

	def logout(self):
		self.wbdmax.logout()
		self.wbdmax = self.get_nologin_helper()

	# ##################################################################################################################

	def list_devices(self):
		profiles = self.wbdmax.get_profiles()

		def get_profile_name(pid):
			for p in profiles:
				if p['id'] == pid:
					return p['profileName']
			else:
				return self._("Unknown")

		for item in self.wbdmax.get_devices():
			plot = self._("Created") + ': %s\n' % self.timestamp_to_str(int(item['created'] // 1000), '%d.%m.%Y %H:%M')
			plot += self._("Make") + ': %s\n' % item['make']
			plot += self._("Model") + ': %s\n' % item['model']
			plot += self._("OS") + ': %s %s\n' % (item['osName'], item['osVersion'])

			title = '[%s] %s [I]([/I]%s[I])[/I]' % (_I(item['countryCode']), _I(item['deviceDisplayName']) if item['isMe'] else item['deviceDisplayName'], get_profile_name(item['profileId']))
			if item['isMe']:
				title += _I(' *')

			self.add_video(title, info_labels={'plot': plot}, cmd=self.delete_device, device_id=None if item['isMe'] else item['id'] )

	# ##################################################################################################################

	def delete_device(self, device_id):
		if device_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to delete this device?")) == True:
			self.wbdmax.delete_device(device_id)
			self.refresh_screen()

	# ##################################################################################################################

	def list_profiles(self):
		active_profile_id = self.wbdmax.get_active_profile_id()

		for p in self.wbdmax.get_profiles():
			plot = []
			if p['id'] == active_profile_id:
				plot.append(self._("Active profile"))

			if p.get('pinRestricted'):
				plot.append(self._("Pin protected"))

			if p.get('ageRestricted'):
				plot.append(self._("Kids profile"))

			if p['id'] == active_profile_id:
				title = _I(p['profileName'])
			else:
				title = p['profileName']

			self.add_video(title, info_labels={'plot':'\n'.join(plot)}, cmd=self.switch_profile, profile_id=p['id'], need_pin=p.get('pinRestricted', False))

	# ##################################################################################################################

	def switch_profile(self, profile_id, need_pin):
		if profile_id == self.wbdmax.get_active_profile_id():
			return

		if self.get_yes_no_input(self._("Do you realy want to switch profile?")) == True:
			pin = None
			if need_pin:
				pin = self.get_text_input(self._("Enter PIN"), input_type='pin')
				if not pin:
					return

			self.wbdmax.switch_profile(profile_id, pin)
			self.scache.scache = {}
			self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id='', page=1):
		data = self.wbdmax.search(keyword, page=page)
		if 'items' not in data:
			return

		self._process_items(data['items'])
		self.add_paging(data['meta'], self.search, keyword=keyword, page=page+1)

	# ##################################################################################################################

	def add_watchlist(self, item_id):
		self.wbdmax.add_watchlist(item_id)
		self.refresh_screen()

	# ##################################################################################################################

	def del_watchlist(self, item_id):
		self.wbdmax.del_watchlist(item_id)
		self.refresh_screen()

	# ##################################################################################################################

	def list_watchlist(self):
		data = self.wbdmax.watchlist()

		for row in data.get('items') or []:
			if 'collection' not in row:
				continue

			if 'component' in row['collection'] and row['collection']['component'].get('id') in ('hero','tab-group'):
				self._process_items(row['collection'].get('items', []))
				continue

			label = row['collection'].get('title')
			if label:
				self.add_dir(label, cmd=self.list_collection, collection_id=row['collection']['id'])

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		data = self.scache.get(stream_key)
		drm_info = data['drm_info']

		ret_data = {
			'url': data['url'],
		}

		if drm_info['wv_license_url']:
			ret_data.update({
				'drm': {
					'wv' : {
						'license_url': drm_info['wv_license_url'],
					}
				}
			})

		if drm_info['pr_license_url']:
			ret_data.update({
				'drm': {
					'pr' : {
						'license_url': drm_info['pr_license_url'],
					}
				}
			})

		return ret_data

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, drm_info, player_settings={}, data_item={}):
		streams = self.get_dash_streams(url, self.wbdmax.req_session, max_bitrate=self.get_setting('max_bitrate'))
		if not streams:
			return

		data = {
			'url': streams[0]['playlist_url'],
			'drm_info': drm_info
		}

		cache_key = self.scache.put(data)
		video_url = stream_key_to_dash_url(self.http_endpoint, cache_key)
		self.add_play(video_title, video_url, settings=player_settings, data_item=data_item)

	# ##################################################################################################################

	def play_item(self, video_title=None, item_id=None, edit_id=None, src_data=None):
		if item_id == None and edit_id == None:
			return

		if not self.is_supporter():
			self.show_info(self._("Full stream quality is available only for ArchivCZSK product supporters. Quality of the playback will be limited to SD resolution."), noexit=True)
		elif self.drm_failed and self.get_setting('drm_playready'):
			self.show_info(self._("Playback of stream with quality >=1080p failed. Switching back to 720p quality."), noexit=True)
		elif self.get_setting('drm_playready') and is_py2:
			self.show_info(self._("You have enabled 1080p and 4k streams support in addon settings. This option works only in distributions based on python 3.8+ like OpenATV 7.x, OpenPLi > 9.x etc. Update software in you receiver to get better quality streams."), noexit=True)

		self.build_lang_lists()
		data_item = None
		resume_from = None

		if item_id:
			data_item = {}
			edit_id, resume_from = self.wbdmax.get_edit_id(item_id, data_item)
		elif src_data:
			data_item = src_data[0]
			resume_from = src_data[1]

		data = self.wbdmax.play(edit_id, force_wv=self.drm_failed)

		if data_item:
			data_item["playableStatus"] = data['manifest']['streamMode'].upper()

		drm_info = {
			'wv_license_url': data.get('drm',{}).get('schemes',{}).get('widevine',{}).get('licenseUrl'),
			'pr_license_url': data.get('drm',{}).get('schemes',{}).get('playready',{}).get('licenseUrl')
		}

		player_settings = {}
		if self.silent_mode == False and resume_from and self.get_setting('sync_playback'):
			player_settings['resume_time_sec'] = int(resume_from // 1000)

		player_settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in player_settings['lang_priority']:
			player_settings['lang_fallback'] = ['en']

		player_settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		player_settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		player_settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')
		player_settings['skip_times'] = self.create_skip_times(data, data_item)
		player_settings['stype'] = 5002

		self.resolve_dash_streams(data['manifest']['url'], video_title or "Video", drm_info, player_settings, data_item)

	# ##################################################################################################################

	def create_skip_times(self, data, data_item=None):
		skip_times = []
		skip_end_titles = None

		for note in data.get('videos', [{}])[0].get('annotations',[]):
			if note['type'] == 'end-credits':
				skip_end_titles = int(note.get('start', 0))

				if data_item != None and skip_end_titles:
					data_item["creditsStartTimeSec"] = skip_end_titles

			elif note['type'] == 'skip' and note['secondaryType'] == 'intro':
				skip_start = int(note.get('start', 0))
				skip_end = int(note.get('end', 0))
				self.log_debug("Adding skip times: (%d:%d)" % (skip_start, skip_end))
				skip_times.append((skip_start, skip_end,))
			else:
				self.log_error("Unsupported annotation: %s" % str(note))


		if skip_end_titles:
			self.log_debug("Adding skip_end_titles: %d" % skip_end_titles)

			if len(skip_times) == 0:
				# add dummy intro skip times
				skip_times.append((-1, -1,))

			skip_times.append((skip_end_titles, 0,))

		return skip_times if len(skip_times) > 0 else None

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if position == None:
			return

		if action in ('watching', 'end'):
			if self.get_setting('sync_playback'):
				self.wbdmax.set_marker(data_item, position)

	# ##################################################################################################################
