# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from .hbomax import HboMax
from functools import partial
from xml.etree import ElementTree as ET

WATCHED_PERCENT = 95.0

class HboMaxContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'HBO Max', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.hbomax = None
		self.login_optional_settings_names = ('username', 'password')
		self.scache = SimpleAutokeyExpiringCache()

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			if not silent:
				self.show_info(self._("To display the content, you must enter a login name and password in the addon settings"), noexit=True)
			return False

		self.build_lang_lists()
		self.hbomax = HboMax(self)
		if self.hbomax.check_access_token(True) == False:
			self.hbomax.login()

		return True

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

		profiles = self.hbomax.get_profiles()

		if len(profiles) < 2:
			return

		# filter out child profiles - they are not working properly because of unknown reason
		profiles = list(filter(lambda p: p['profileType'] != 'child', profiles))

		choices = []
		for i, p in enumerate(profiles):
			if p['isMe']:
				title = _I(p['name'])
			else:
				title = p['name']
			choices.append(title)

		answer = self.get_list_input(choices, self._("Select profile"))
		if answer == None:
			return

		if profiles[answer]['isMe']:
			return

		self.hbomax.set_profile(profiles[answer]['profileId'])
		self.scache.scache = {}

	# ##################################################################################################################

	def root(self):
		PlayerFeatures.request_exteplayer3_cenc_support(self)
		self.build_lang_lists()
		self.select_profile_on_startup()

		self.add_search_dir()
		self.add_dir(self._("Home"), cmd=self.list_page, slug='urn:hbo:page:home')
		self.add_dir(self._("Movies"), cmd=self.list_page, slug='urn:hbo:page:movies')
		self.add_dir(self._("Series"), cmd=self.list_page, slug='urn:hbo:page:series')
		self.add_dir(self._("HBO Originals"), cmd=self.list_page, slug='urn:hbo:page:originals')
		self.add_dir(self._("Just added"), cmd=self.list_page, slug='urn:hbo:page:just-added')
#		self.add_dir(self._("Last chance"), cmd=self.list_page, slug='urn:hbo:page:last-chance')
		self.add_dir(self._("Coming soon"), cmd=self.list_page, slug='urn:hbo:page:coming-soon')
		self.add_dir(self._("Trending"), cmd=self.list_page, slug='urn:hbo:page:trending')

		if self.get_setting('sync_watchlist'):
			self.add_dir(self._("Watchlist"), cmd=self.list_watchlist)

		if self.get_setting('sync_playback'):
			self.add_dir(self._("Continue watching"), cmd=self.list_continue_watching)

		self.add_dir(self._("Informations and settings"), cmd=self.list_info)

	# ##################################################################################################################

	def list_info(self):
		self.add_dir(self._("Profiles"), cmd=self.list_profiles)
		self.add_dir(self._("Devices"), cmd=self.list_devices)

	# ##################################################################################################################

	def list_devices(self):
		my_id = 'urn:hbo:device:' + self.hbomax.login_data['device_id']

		for item in self.hbomax.get_devices():
			plot = self._("Last used") + ':\n%s' % item['lastUsedDate'].replace('T',' ')[:19]
			title = '%s [%s: %s]' % (item['deviceName'], item['deviceCode'], item['platformType'])
			if item['id'] == my_id:
				title = _I(title)
			self.add_video(title, info_labels={'plot': plot}, cmd=self.delete_device, device_id=item['id'] if item['id'] != my_id else None )

	# ##################################################################################################################

	def delete_device(self, device_id):
		if device_id == None:
			return

		self.show_info(self._("This operation is not yet implemented!"))
#		if self.get_yes_no_input(self._("Do you realy want to delete this device?")) == True:
#			self.hbomax.delete_device(device_id)
#			self.refresh_screen()

	# ##################################################################################################################

	def list_profiles(self):
		for p in self.hbomax.get_profiles():
			plot = []
			if p['isMe']:
				plot.append(self._("Active profile"))
			if p['profileType'] == 'child':
				plot.append(self._("Kids profile"))

			if p['isMe']:
				title = _I(p['name'])
			else:
				title = p['name']

			self.add_video(title, info_labels={'plot':'\n'.join(plot)}, cmd=self.switch_profile, profile_id=p['profileId'] if p['isMe'] == False else None)

	# ##################################################################################################################

	def switch_profile(self, profile_id):
		if profile_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to switch profile?")) == True:
			self.hbomax.set_profile(profile_id)
			self.scache.scache = {}
			self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		data = self.hbomax.search(keyword)
		if data:
			self.process_rows(data['items'], 'search')


	# ##################################################################################################################

	def load_info_labels(self, slug):
		data = self.hbomax.express_content(slug)
		ret = {}

		if ':series' in slug or ':feature' in slug:
			try:
				year = data['seasons'][0]['episodes'][0]['releaseYear']
			except:
				try:
					year = data['releaseYear']
				except:
					year = None

			try:
				duration = data['duration']
			except:
				duration = None

			ret = {
				'plot': data['summaries']['full'],
				'img': self._image(data['images'].get('tileburnedin')),
				'title': data['titles']['full'],
				'duration': duration,
				'year': year
			}

		return ret

	# ##################################################################################################################

	def _image(self, url, size='256x256', protection=False):
		if not url:
			return None

		replaces = {
			'size': size,
			'compression': 'low',
			'protection': 'false' if not protection else 'true',
			'scaleDownToFit': 'false',
		}

		for key in replaces:
			url = url.replace('{{{{{}}}}}'.format(key), replaces[key])

		return url

	# ##################################################################################################################

	def process_rows(self, rows, slug):
		sync_watchlist = self.get_setting('sync_watchlist')
		sync_playback = self.get_setting('sync_playback')

		markers = {}
		if sync_playback:
			ids = []
			for row in rows:
				viewable = row.get('viewable') or ''
				if viewable:
					ids.append(viewable.split(':')[-1])

			markers = self.hbomax.markers(ids)

		for row in rows:
			viewable = row.get('viewable') or ''
			resume_from = None
			content_type = row.get('contentType')

			menu = self.create_ctx_menu()
			if row.get('viewable'):
				if slug == 'watchlist':
					menu.add_menu_item(self._("Remove from watchlist"), cmd=self.remove_watchlist, slug=row['viewable'])
				elif sync_watchlist:
					menu.add_menu_item(self._("Add to watchlist"), cmd=self.add_watchlist, slug=row['viewable'])

			if viewable.startswith('urn:hbo:franchise'):
				content_type = 'SERIES'
				viewable = 'urn:hbo:series:'+row['images']['tile'].split('/')[4]

			if viewable in markers:
				if float(markers[viewable]['position']) / markers[viewable]['runtime'] <= (WATCHED_PERCENT / 100.0):
					resume_from = markers[viewable]['position']

			if content_type in ('FEATURE', 'EXTRA'):
				info_labels = partial(self.load_info_labels, viewable)
				menu.add_menu_item(self._("Extras"), cmd=self.list_extras, slug=viewable)
				self.add_video(row['titles']['full'], self._image(row['images'].get('tileburnedin')), info_labels=info_labels, menu=menu, cmd=self.play_item, slug=viewable, resume_from=resume_from)

			elif content_type == 'SERIES':
				info_labels = partial(self.load_info_labels, viewable)
				self.add_dir(row['titles']['full'], self._image(row['images'].get('tileburnedin')), info_labels=info_labels, menu=menu, cmd=self.list_series, slug=viewable)

			elif content_type in ('SERIES_EPISODE', 'MINISERIES_EPISODE'):
				info_labels = {
					'season': row.get('seasonNumber', 1),
					'episode': row.get('numberInSeason', row.get('numberInSeries', 1)),
					'duration': row['duration']
				}
				menu.add_menu_item(self._("Go to series"), cmd=self.list_series, slug=row['series'])
				self.add_video(row['titles']['full'], self._image(row['images'].get('tileburnedin')), info_labels=info_labels, menu=menu, cmd=self.play_item, slug=viewable, resume_from=resume_from)

			elif row['id'].startswith('urn:hbo:themed-tray') and row['items']:
				info_labels = {
					'plot': row['summary']['description'],
				}
				self.add_dir(row['summary']['title'], info_labels=info_labels, cmd=self.list_page, slug=slug, tab=row['id'])

			elif row['id'].startswith('urn:hbo:tray') and row['items']:
				if 'header' not in row:
					continue

				self.add_dir(row['header']['label'], cmd=self.list_page, slug=slug, tab=row['id'])

			# elif row['id'].startswith('urn:hbo:highlight'):
			#     print(row)
			#     raise

			elif row['id'].startswith('urn:hbo:tab-group'):
				for tab in row['tabs']:
					if tab['items']:
						self.add_dir(tab['label'], cmd=self.list_page, slug=slug, tab=tab['id'])

			elif row['id'].startswith('urn:hbo:grid'):
				self.process_rows(row['items'], slug)


	# ##################################################################################################################

	def list_page(self, slug, tab=None):
		data = self.scache.get(slug)
		if not data:
			data = self.hbomax.get_express_content(slug)
			self.scache.put_with_key(data, slug)

		pdata = self.hbomax.process_express_content_data(data, slug, tab)
		self.process_rows(pdata['items'], slug)

	# ##################################################################################################################

	def list_series(self, slug, season=None):
		data = self.hbomax.express_content(slug, tab=season)
		sync_watchlist = self.get_setting('sync_watchlist')
		sync_playback = self.get_setting('sync_playback')

		if len(data['seasons']) > 1:
			for row in data['seasons']:
				title = "%s: %d" % (self._("Season"), row['seasonNumber'])
				info_labels = {
					'plot': row['summaries']['short'],
					'season': row['seasonNumber'],
				}

				self.add_dir(title, self._image(data['images'].get('tileburnedin')), info_labels=info_labels, cmd=self.list_series, slug=slug, season=row['id'])
		else:
			markers = {}
			if sync_playback:
				ids = []
				for row in data['episodes']:
					ids.append(row['id'].split(':')[-1])

				markers = self.hbomax.markers(ids)

			for row in data['episodes']:
				menu = self.create_ctx_menu()
				resume_from = None

				if sync_watchlist:
					menu.add_menu_item(self._("Add to watchlist"), cmd=self.add_watchlist, slug=row['id'])

				if row['id'] in markers:
					if float(markers[row['id']]['position']) / markers[row['id']]['runtime'] <= (WATCHED_PERCENT / 100.0):
						resume_from = markers[row['id']]['position']

				info_labels = {
					'plot': row['summaries']['short'],
					'duration': row['duration'],
					'season': row.get('seasonNumber', 1),
					'episode': row.get('numberInSeason', row.get('numberInSeries', 1)),
				}

				self.add_video(row['titles']['full'], self._image(data['images'].get('tileburnedin')), info_labels=info_labels, menu=menu, cmd=self.play_item, slug=row['id'], resume_from=resume_from)

	# ##################################################################################################################

	def list_extras(self, slug):
		content = self.hbomax.express_content(slug)
		sync_playback = self.get_setting('sync_playback')

		markers = {}
		if sync_playback:
			ids = []
			for row in content['extras']:
				if row.get('playbackMarkerId'):
					ids.append(row['playbackMarkerId'])

			markers = self.hbomax.markers(ids)

		for row in content['extras']:
			if not row.get('playbackMarkerId'):
				continue

			info_labels = {
				'plot': row['summaries']['short'],
				'duration': row['duration']
			}

			resume_from = None
			if row['id'] in markers:
				if float(markers[row['id']]['position']) / markers[row['id']]['runtime'] <= (WATCHED_PERCENT / 100.0):
					resume_from = markers[row['id']]['position']

			self.add_video(row['titles']['full'], self._image(row['images'].get('tileburnedin')), info_labels=info_labels, cmd=self.play_item, slug=row['id'], resume_from=resume_from)

	# ##################################################################################################################

	def add_watchlist(self, slug):
		self.hbomax.add_watchlist(slug)
		self.refresh_screen()

	# ##################################################################################################################

	def remove_watchlist(self, slug):
		self.hbomax.delete_watchlist(slug)
		self.refresh_screen()

	# ##################################################################################################################

	def list_watchlist(self):
		rows = self.hbomax.watchlist()
		self.process_rows(rows, 'watchlist')

	# ##################################################################################################################

	def list_continue_watching(self):
		data = self.hbomax.continue_watching()
		self.process_rows(data['items'], 'continue_watching')

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		data = self.scache.get(stream_key)
		drm_info = data['drm_info']

		ret_data = {
			'url': data['url'],
		}

		if drm_info['licence_url']:
			ret_data.update({
				'drm' : {
					'licence_url': drm_info['licence_url'],
					'headers': {
						'Authorization': 'Bearer {}'.format(self.hbomax.login_data.get('access_token')),
					}
				}
			})

		return ret_data

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, drm_info, player_settings={}, data_item={}):
		streams = self.get_dash_streams(url, self.hbomax.req_session, max_bitrate=self.get_setting('max_bitrate'))
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

	def play_item(self, slug, resume_from=None):
		data, content, edit = self.hbomax.play(slug)
		if not data or not content or not edit:
			return

		drm_info = {
			'licence_url': data.get('drm',{}).get('licenseUrl')
		}

		player_settings = {}
		if self.silent_mode == False and resume_from:
			player_settings['resume_time_sec'] = resume_from

		player_settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in player_settings['lang_priority']:
			player_settings['lang_fallback'] = ['en']

		player_settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		player_settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		player_settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')
		player_settings['skip_times'] = self.create_skip_times(edit, data)
		player_settings['stype'] = 5002

		self.resolve_dash_streams(data['url'], content['titles']['full'], drm_info, player_settings, self.create_data_item(edit))

	# ##################################################################################################################

	def create_skip_times(self, edit, data):
		skip_times = []

		for note in data.get('annotations', []):
			if note['type'] == 'SKIP' and note['secondaryType'] == 'Intro':
				skip_start = int(note.get('start', 0))
				skip_end = int(note.get('end', 0))
				self.log_debug("Adding skip times: (%d:%d)" % (skip_start, skip_end))
				skip_times.append((skip_start, skip_end,))

		skip_end_titles = int(edit.get('creditsStartTime', 0))

		if skip_end_titles:
			self.log_debug("Adding skip_end_titles: %d" % skip_end_titles)

			if len(skip_times) == 0:
				# add dummy intro skip times
				skip_times.append((-1, -1,))

			skip_times.append((skip_end_titles, 0,))

		return skip_times if len(skip_times) > 0 else None

	# ##################################################################################################################

	def create_data_item(self, edit):
		return {
			'cut_id': edit['playbackMarkerId'],
			'runtime': edit['duration'],
			'endpoint': ('markers', '/markers')
		}

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if position == None:
			return

		if action in ('watching', 'end'):
			if self.get_setting('sync_playback'):
				self.hbomax.update_marker( data_item['endpoint'], data_item['cut_id'], data_item['runtime'], position)

	# ##################################################################################################################
