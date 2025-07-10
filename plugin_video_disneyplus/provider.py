# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from .disneyplus import DisneyPlus
from .httphandler import DisneyHlsMaster
import base64
import json

WATCHED_PERCENT = 95.0
SUGGESTED_ID = '3cd8f37d-5480-46fb-9eeb-5002123abe53'
EXTRAS_ID = '83f33e19-3e08-490d-a59a-6ef5cb93f030'

class DisneyPlusContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'Disney+', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.http_handler = None
		self.disneyplus = None
		self.login_optional_settings_names = ('username', 'password')
		self.scache = SimpleAutokeyExpiringCache()

	# ##################################################################################################################

	def set_http_handler(self, http_handler):
		self.http_handler = http_handler

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			if not silent:
				self.show_info(self._("To display the content, you must enter a login name and password in the addon settings"), noexit=True)
			return False

		self.build_lang_lists()
		self.disneyplus = DisneyPlus(self)
		if self.disneyplus.check_access_token(True) == False:
			self.disneyplus.refresh_token()

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

		account = self.disneyplus.get_account_info()['account']
		profiles = account['profiles']

		if len(profiles) < 2:
			return

		active_id = None
		choices = []

		for i, profile in enumerate(profiles):
			if profile['attributes']['parentalControls']['isPinProtected']:
				label = '%s (%s)' % (profile['name'], self._('PIN protected'))
			else:
				label = profile['name']

			if account['activeProfile'] and profile['id'] == account['activeProfile']['id']:
				active_id = profile['id']
				label = _I(label)

			choices.append(label)

		answer = self.get_list_input(choices, self._("Select profile"))
		if answer == None:
			return

		profile = profiles[answer]
		if profile['id'] == active_id:
			return

		self.switch_profile(profile, confirm_switch=False)

	# ##################################################################################################################

	def root(self):
		PlayerFeatures.check_latest_exteplayer3(self)

		self.build_lang_lists()
		self.select_profile_on_startup()

		self.add_search_dir()
		self.add_dir(self._("Home"), cmd=self.deeplink_page, ref_id='home')
		self.add_dir(self._("Brands"), cmd=self.brands)
		self.add_dir(self._("Discover"), cmd=self.search, keyword='')
		self.add_dir(self._("Movies"), cmd=self.deeplink_page, ref_id='movies')
		self.add_dir(self._("Series"), cmd=self.deeplink_page, ref_id='series')
		self.add_dir(self._("Disney Originals"), cmd=self.deeplink_page, ref_id='originals')

		if self.get_setting('sync_watchlist'):
			self.add_dir(self._("Watchlist"), cmd=self.watchlist)

		if self.get_setting('sync_playback'):
			self.add_dir(self._("Continue watching"), cmd=self.continue_watching)

		self.add_dir(self._("Informations and settings"), cmd=self.list_info)

	# ##################################################################################################################

	def list_info(self):
		self.add_dir(self._("Profiles"), cmd=self.list_profiles)

	# ##################################################################################################################

	def _avatars(self, ids):
		avatars = {}

		data = self.disneyplus.avatar_by_id(ids)
		for row in data['avatars']:
			avatars[row['avatarId']] = row['image']['tile']['1.00']['avatar']['default']['url'] + '/scale?width=300'

		return avatars

	# ##################################################################################################################

	def list_profiles(self):
		account = self.disneyplus.get_account_info()['account']
		profiles = account['profiles']
		avatars = self._avatars([x['attributes']['avatar']['id'] for x in profiles])

		for profile in profiles:
			profile['_avatar'] = avatars.get(profile['attributes']['avatar']['id'])

			if profile['attributes']['parentalControls']['isPinProtected']:
				label = '%s (%s)' % (profile['name'], self._('PIN protected'))
			else:
				label = profile['name']

			if account['activeProfile'] and profile['id'] == account['activeProfile']['id']:
				label = _I(label)
				self.add_video(label, profile['_avatar'], cmd=self.switch_profile, profile=None)
			else:
				self.add_video(label, profile['_avatar'], cmd=self.switch_profile, profile=profile)

	# ##################################################################################################################

	def switch_profile(self, profile, confirm_switch=True):
		if profile == None:
			return

		if confirm_switch == False or self.get_yes_no_input(self._("Do you realy want to switch profile?")) == True:
			pin = None
			if profile['attributes']['parentalControls']['isPinProtected']:
				pin = self.get_text_input(self._('Enter PIN'), input_type='pin')
				if not pin:
					return

			self.disneyplus.switch_profile(profile['id'], pin=pin)
			self.scache.scache = {}
			self.refresh_screen()

	# ##################################################################################################################

	def add_watchlist(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')))
		info = self._get_info(data)
		self.disneyplus.edit_watchlist('add', page_info=data['infoBlock'], action_info=info['actions']['modifySaves']['infoBlock'])

		self.refresh_screen()

	# ##################################################################################################################

	def delete_watchlist(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')))
		info = self._get_info(data)
		self.disneyplus.edit_watchlist('remove', page_info=data['infoBlock'], action_info=info['actions']['modifySaves']['infoBlock'])

		self.refresh_screen()

	# ##################################################################################################################

	def remove_continue_watching(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')))
		info = self._get_info(data)
		self.disneyplus.remove_continue_watching(action_info=info['actions']['contextMenu']['removeFromContinueWatching']['infoBlock'])

		self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		if search_id:
			self.ensure_supporter()

		data = self.disneyplus.search(keyword)
		if data['containers']:
			self._process_rows(data['containers'][0])

	# ##################################################################################################################

	def _get_actions(self, data):
		actions = {}
		for row in data.get('actions', []):
			if row['type'] == 'contextMenu':
				actions[row['type']] = {}

				for sub_row in row.get('actions', []):
					actions[row['type']][sub_row['type']] = sub_row
			else:
				actions[row['type']] = row

		actions['playback'] = actions.get('playback') or actions.get('browse') or {}
		return actions

	# ##################################################################################################################

	def _get_action_page_id(self, data):
		actions = self._get_actions(data)
		return actions.get('browse',{}).get('pageId')

	# ##################################################################################################################

	def _get_info(self, data):
		actions = self._get_actions(data)

		containers = {
			'episodes': {'seasons': []},
			'suggested': {},
			'extras': {},
			'details': {'visuals': {}},
		}
		for row in data.get('containers', []):
			if row.get('id') == SUGGESTED_ID:
				containers['suggested'] = row
			elif row.get('id') == EXTRAS_ID:
				containers['extras'] = row
			else:
				containers[row['type']] = row


		description = containers['details']['visuals'].get('description') or data['visuals'].get('description', {})
		plot = description.get('medium') or description.get('brief') or description.get('full')
		title = containers['details']['visuals'].get('title') or data['visuals'].get('title')

		return {
			'title': title,
			'plot': plot,
			'containers': containers,
			'actions': actions,
			'art': self._get_art(data),
			'content_id': actions.get('playback',{}).get('legacyPartnerFeed', {}).get('dmcContentId') or actions.get('playback',{}).get('partnerFeed',{}).get('dmcContentId'),
			'deeplink_id': actions.get('playback',{}).get('deeplinkId')
		}

	# ##################################################################################################################

	def deeplink_page(self, ref_id):
		data = self.disneyplus.deeplink(ref_id)
		page_id = self._get_action_page_id(data)
		data = self.disneyplus.explore_page(page_id, limit=1, enhanced_limit=99)
		return self._process_rows(data)

	# ##################################################################################################################

	def list_page(self, page_id):
		data = self.disneyplus.explore_page(page_id, limit=1, enhanced_limit=99)
		return self._process_rows(data, flatten=True)

	# ##################################################################################################################

	def brands(self, page=0, set_id=None):
		if not set_id:
			data = self.disneyplus.deeplink('home')
			page_id = self._get_action_page_id(data)
			data = self.disneyplus.explore_page(page_id, limit=0, enhanced_limit=0)

			set_id = [x for x in data['containers'] if 'brand' in x['style']['name'].lower()][0]['id']

		data = self.disneyplus.explore_set(set_id, page=page)
		self._process_rows(data)

		if data['pagination']['hasMore']:
			self.add_next(cmd=self.brands, page=page+1, set_id=set_id)

	# ##################################################################################################################

	def watchlist(self):
		data = self.disneyplus.deeplink('watchlist')
		page_id = self._get_action_page_id(data)
		data = self.disneyplus.explore_page(page_id, limit=1, enhanced_limit=15)
		self._process_rows(data, True)

	# ##################################################################################################################

	def continue_watching(self, page=0, set_id=None):
		if not set_id:
			data = self.disneyplus.deeplink('home')
			page_id = self._get_action_page_id(data)
			data = self.disneyplus.explore_page(page_id, limit=0, enhanced_limit=0)

			set_id = [x for x in data['containers'] if 'continue_watching' in x['style']['name'].lower()][0]['id']

		data = self.disneyplus.explore_set(set_id, page=page)
		self._process_rows(data, continue_watching=True)

		if data['pagination']['hasMore']:
			self.add_next(cmd=self.brands, page=page+1, set_id=set_id)

	# ##################################################################################################################

	def get_progress(self, user_state):
		if not user_state:
			return {}

		progress = {}
		if user_state['progress']['progressPercentage'] == 100:
			progress['fully_played'] = True
			progress['played'] = True

		elif user_state['progress']['progressPercentage'] > 0:
			progress['fully_played'] = False
			progress['played'] = True
			if 'secondsRemaining' in user_state['progress']:
				progress['remaining_sec'] = user_state['progress']['secondsRemaining']
			else:
				progress['progress_percentage'] = user_state['progress']['progressPercentage']

		return progress

	# ##################################################################################################################

	def list_set(self, set_id, watchlist=False, continue_watching=False, page=0):
		data = self.disneyplus.explore_set(set_id, page=page)
		self._process_rows(data, watchlist, continue_watching=continue_watching)

		if data['pagination']['hasMore']:
			self.add_next(cmd=self.list_set, page=page+1, set_id=set_id, watchlist=watchlist, continue_watching=continue_watching)

	# ##################################################################################################################

	def _process_rows(self, data, watchlist=False, flatten=False, short_episode_name=False, continue_watching=False):
		if not data or not data.get('visuals'):
			return

		rows = data.get('containers') or data.get('items') or []

		user_states = {}
		if self.get_setting('sync_playback'):
			pids = [row.get('personalization',{}).get('pid') for row in rows if row['visuals'].get('durationMs')]
			pids = [x for x in pids if x]
			if pids:
				user_states = self.disneyplus.userstates(pids)

		rows_len = len(rows)
		for row in rows:
			row_type = row.get('type')

			if row_type == 'set' and row['style']['name'] == 'hero_inline_single' and len(row['items']) == 1:
				row = row['items'][0]
				row_type = row.get('type')

			if row_type == 'set':
				if 'hero' in row['style']['name'].lower() or 'brand' in row['style']['name'].lower() or 'continue_watching' in row['style']['name'].lower():
					continue

				if rows_len == 1 and flatten:
					return self.list_set(row['id'], watchlist, continue_watching)
				else:
					self.add_dir(row['visuals']['name'], self._get_art(row), cmd=self.list_set, set_id=row['id'], watchlist=watchlist, continue_watching=continue_watching)

			elif row.get('actions', []):
				# MOVIE / TV SHOW / EPISODE / REPLAY / LIVE
				progress = self.get_progress(user_states.get(row['personalization']['pid']))
				self._parse_row(row, watchlist, continue_watching, progress, short_episode_name)

	# ##################################################################################################################

	def get_ep_code(self, info):
		s = int(info.get('season', 1))
		e = int(info.get('episode', 1))
		return '{} ({})'.format(int_to_roman(s), e)

	# ##################################################################################################################

	def set_progress(self, title, progress):
		if progress.get('played'):
			if progress.get('fully_played'):
				return title + _I(' *')
			else:
				return title + ' *'
		else:
			return title

	# ##################################################################################################################

	def _parse_episode(self, data, continue_watching=False, progress={}, short_episode_name=False):
		info = self._get_info(data)
		info_labels = self.get_common_info_labels(data)

		info['progress'] = progress

		info_labels.update({
			'plot': info['plot'],
			'season': data['visuals'].get('seasonNumber'),
			'episode': data['visuals'].get('episodeNumber'),
			'tvshowtitle': info['title'],
			'duration': int(data['visuals'].get('durationMs', 0) / 1000),
			'mediatype': 'episode',
		})

		info_labels['title'] = '{} {}'.format(info['title'], self.get_ep_code(info_labels))

		title = '{:02d}. {}'.format(int(info_labels['episode']), data['visuals']['episodeTitle'])

		if not short_episode_name:
			title = '{} {} - {}'.format(info['title'], int_to_roman(int(info_labels['season'])), title)

		# TODO: remove from watched doesn't work for episodes, because explore_page() will fail - needs more investigation
#		menu = self.get_common_menu(info, False, continue_watching)
		menu = self.get_common_menu(info, False, False)

		show_id = info.get('actions', {}).get('browse', {}).get('pageId')
		if show_id:
			menu.add_menu_item(self._("Go to series"), cmd=self.list_show, show_id=show_id)

		self.add_video( self.set_progress(title, progress), info['art'], info_labels, menu, cmd=self.play_item, item_info=info)

	# ##################################################################################################################

	def _parse_page(self, data):
		info = self._get_info(data)

		info_labels = {
			'plot': info['plot'],
		}

		self.add_dir(info['title'], info['art'], info_labels, cmd=self.list_page, page_id=info['actions']['browse']['pageId'])

	# ##################################################################################################################

	def _parse_event(self, data, watchlist=False, progress={}):
		info = self._get_info(data)
		info['progress'] = progress

		info_labels = self.get_common_info_labels(data)
		menu = self.get_common_menu(info, watchlist)

		meta = data['visuals'].get('metastringParts', {})

		#TODO: is this info needed?
		is_live = data['visuals']['badging']['airingEventState']['state'] == 'live'
		title_prefix = ''
		plot_prefix = ''

		# TODO: Watch from live / start
		if 'sportsLeague' in meta:
			league = meta['sportsLeague']['name']
			if 'releaseYearRange' in meta:
				league = u'{} - {}'.format(league, meta['releaseYearRange']['startYear'])
			plot_prefix = '[{}]\n'.format(league)

		if data['visuals']['badging']['airingEventState']['state'] not in ('replay',):
			title_prefix = '{} '.format(_I(data['visuals']['badging']['airingEventState']['badgeLabel']))

		if 'prompt' in data['visuals'] and not info.get('actions',{}).get('modal'):
			plot_prefix = '[{}]\n{}'.format(data['visuals']['prompt'], plot_prefix)


		actions = info.get('actions',{})
		if actions.get('modal'):
			actions = self._get_actions(actions['modal'])

		if actions.get('playback',{}).get('contentType') == 'linear':
			resource_data = json.loads(base64.b64decode(actions['playback']['resourceId']).decode("utf-8"))
			info['channel_id'] = resource_data['channelId']

			if not info.get('art'):
				try:
					info['art'] = 'https://disney.images.edge.bamgrid.com/ripcut-delivery/v2/variant/disney/{}/scale?width=800&aspectRatio=1.78'.format(
						data['visuals']['networkAttribution']['artwork']['brand']['logo']['2.00']['imageId'])
				except:
					pass

			self.add_video(title_prefix + data['visuals']['networkAttribution']['ttsText'], info.get('art'), info_labels, cmd=self.play_item, item_info=info)
		else:
			info_labels.update({
				'plot': plot_prefix + info['plot']
			})

			self.add_video(title_prefix + info['title'], info['art'], info_labels, menu=menu, cmd=self.play_item, item_info=info)

	# ##################################################################################################################

	def _parse_movie(self, data, watchlist=False, continue_watching=False, progress={}):
		info = self._get_info(data)
		info['progress'] = progress

		info_labels = self.get_common_info_labels(data)
		menu = self.get_common_menu(info, watchlist, continue_watching)

		menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, deeplink_id=info.get('deeplink_id'))
		menu.add_menu_item(self._('Extras'), cmd=self.extras, deeplink_id=info.get('deeplink_id'))
		menu.add_menu_item(self._('Suggested'), cmd=self.suggested, deeplink_id=info.get('deeplink_id'))

		meta = data['visuals'].get('metastringParts', {})

		info_labels.update({
			'title': info['title'],
			'plot': info['plot'],
			'duration': int(meta['runtime']['runtimeMs'] / 1000),
		})

		if info_labels.get('year'):
			title = '{} ({})'.format(info['title'], info_labels['year'])
		else:
			title = info['title']

		self.add_video(self.set_progress(title, progress), info['art'], info_labels, menu, cmd=self.play_item, item_info=info)

	# ##################################################################################################################

	def _parse_show(self, data, watchlist=False, continue_watching=False, progress={}):
		info = self._get_info(data)

		info_labels = self.get_common_info_labels(data)
		menu = self.get_common_menu(info, watchlist, continue_watching)

		menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, deeplink_id=info.get('deeplink_id'))
		menu.add_menu_item(self._('Extras'), cmd=self.extras, deeplink_id=info.get('deeplink_id'))
		menu.add_menu_item(self._('Suggested'), cmd=self.suggested, deeplink_id=info.get('deeplink_id'))

		info_labels.update({
			'plot': info['plot'],
		})

		if info_labels.get('year'):
			title = '{} ({})'.format(info['title'], info_labels['year'])
		else:
			title = info['title']

		self.add_dir(self.set_progress(title, progress), info['art'], info_labels, menu, cmd=self.list_show, show_id=info.get('actions',{}).get('browse',{}).get('pageId'))

	# ##################################################################################################################v

	def _parse_row(self, data, watchlist=False, continue_watching=False, progress={}, short_episode_name=False):
		meta = data['visuals'].get('metastringParts', {})

		if 'airingEventState' in data['visuals'].get('badging', {}):
			self._parse_event(data, watchlist, progress)

		elif 'episodeTitle' in data['visuals']:
			self._parse_episode(data, continue_watching, progress, short_episode_name)

		elif 'runtime' in meta:
			self._parse_movie(data, watchlist, continue_watching, progress)

		elif meta:
			self._parse_show(data, watchlist, continue_watching, progress)

		else:
			self._parse_page(data)


	# ##################################################################################################################

	def list_show(self, show_id):
		data = self.disneyplus.explore_page(show_id, limit=1, enhanced_limit=15)
		info = self._get_info(data)

		for row in info['containers']['episodes']['seasons']:
			info_labels = {
				'plot': '{}\n{}'.format(info['plot'], row['visuals']['episodeCountDisplayText']),
			}
			self.add_dir(row['visuals']['name'], self._get_art(row) or info['art'], info_labels, cmd=self.list_season, season_id=row['id'])

		if info.get('actions',{}).get('trailer'):
			self.add_video(self._("Trailer"), cmd=self.play_trailer, deeplink_id=data['id'])

		if info['containers']['suggested']:
			self.add_dir(self._('Suggested'), cmd=self.suggested, deeplink_id=data['id'])

		if info['containers']['extras']:
			self.add_dir(self._('Extras'), cmd=self.extras, deeplink_id=data['id'])

	# ##################################################################################################################

	def list_season(self, season_id, page=0):
		data = self.disneyplus.explore_season(season_id, page)
		self._process_rows(data, short_episode_name=True)

		if data['pagination']['hasMore']:
			self.add_next(cmd=self.list_season, season_id=season_id, page=page+1)

	# ##################################################################################################################

	def get_common_info_labels(self, data):
		meta = data.get('visuals',{}).get('metastringParts', {})
		info_labels = {}

		if 'genres' in meta:
			info_labels['genre'] = meta['genres']['values']

		if 'ratingInfo' in meta:
			info_labels['rating'] = meta['ratingInfo']['rating']['text']

		if 'releaseYearRange' in meta:
			info_labels['year'] = meta['releaseYearRange'].get('startYear')

		return info_labels

	# ##################################################################################################################

	def get_common_menu(self, item_info, watchlist, continue_watching=False ):
		menu = self.create_ctx_menu()
		deeplink_id = item_info.get('deeplink_id')

		if deeplink_id and self.get_setting('sync_watchlist'):
			if watchlist:
				menu.add_menu_item(self._("Remove from watchlist"), cmd=self.delete_watchlist, deeplink_id=deeplink_id)
			else:
				menu.add_menu_item(self._("Add to watchlist"), cmd=self.add_watchlist, deeplink_id=deeplink_id)

		if deeplink_id and self.get_setting('sync_playback'):
			if continue_watching:
				menu.add_menu_item(self._("Remove from watched"), cmd=self.remove_continue_watching, deeplink_id=deeplink_id)

		return menu

	# ##################################################################################################################

	def suggested(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')), enhanced_limit=15)
		info = self._get_info(data)
		return self._process_rows(info['containers']['suggested'])

	# ##################################################################################################################

	def play_trailer(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')), enhanced_limit=15)
		info = self._get_info(data)

		if not info['actions'].get('trailer'):
			return

		info['resource_id'] = info['actions']['trailer']['resourceId']

		return self.play_item(item_info=info)

	# ##################################################################################################################

	def extras(self, deeplink_id):
		data = self.disneyplus.explore_page('entity-{}'.format(deeplink_id.replace('entity-', '')), enhanced_limit=15)
		info = self._get_info(data)
		return self._process_rows(info['containers']['extras'])

	# ##################################################################################################################

	def _get_art(self, row):
		if not row or 'artwork' not in row['visuals'] or 'standard' not in row['visuals']['artwork']:
			return {}

		is_episode = 'episodeTitle' in row['visuals']
		images = row['visuals']['artwork']['standard']
		if 'tile' in row['visuals']['artwork']:
			images['hero_tile'] = row['visuals']['artwork']['tile']['background']

		if 'network' in row['visuals']['artwork']:
			images['thumbnail'] = row['visuals']['artwork']['network']['tile']

		for key in ('hero', 'brand', 'up_next'):
			try:
				images['background'] = row['visuals']['artwork'][key]['background']
			except KeyError:
				pass

		def _first_image_url(d):
			return 'https://disney.images.edge.bamgrid.com/ripcut-delivery/v2/variant/disney/{}'.format(d['imageId'])

		art = {}
		# don't ask for jpeg thumb; might be transparent png instead
		thumbsize = '/scale?width=400&aspectRatio=1.78'
		bannersize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'
		fullsize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'

		thumb_ratios = ['1.78', '1.33', '1.00']
		poster_ratios = ['0.71', '0.75', '0.80']
		clear_ratios = ['2.00', '1.78', '3.32']
		banner_ratios = ['3.91', '3.00', '1.78']
		watermark_used = False

		if is_episode:
			thumbs = ('thumbnail',)
		else:
			thumbs = ('thumbnail', 'tile', 'watermark')

		fanart_count = 0
		for name in images or []:
			art_type = images[name]

			tr = br = pr = ''

			for ratio in thumb_ratios:
				if ratio in art_type:
					tr = ratio
					break

			for ratio in banner_ratios:
				if ratio in art_type:
					br = ratio
					break

			for ratio in poster_ratios:
				if ratio in art_type:
					pr = ratio
					break

			for ratio in clear_ratios:
				if ratio in art_type:
					cr = ratio
					break

			if name in thumbs:
				if tr:
					art['thumb'] = _first_image_url(art_type[tr]) + thumbsize
				if pr:
					art['poster'] = _first_image_url(art_type[pr]) + thumbsize

				if (tr or pr) and name == 'watermark':
					watermark_used = True

			elif name == 'hero_tile':
				if br:
					art['banner'] = _first_image_url(art_type[br]) + bannersize

			elif name in ('hero_collection', 'background_details', 'background'):
				if tr:
					k = 'fanart{}'.format(fanart_count) if fanart_count else 'fanart'
					art[k] = _first_image_url(art_type[tr]) + fullsize
					fanart_count += 1
				if pr:
					art['keyart'] = _first_image_url(art_type[pr]) + bannersize

			elif name in ('title_treatment', 'logo'):
				if cr:
					art['clearlogo'] = _first_image_url(art_type[cr]) + thumbsize

		if is_episode or watermark_used:
			art.pop('poster', None)

		return art.get('poster') or art.get('thumb')

	# ##################################################################################################################

	def create_skip_times(self, milestones, use_explore=False):
		skip_times = []

		if not milestones:
			return None

		def get_milestone(name, default=0):
			if use_explore:
				for row in milestones:
					if row['label'] == name:
						return int(row['offsetMillis'] / 1000)

			else:
				for key in milestones:
					if key == name:
						return int(milestones[key][0]['milestoneTime'][0]['startMillis'] / 1000)

			return default

		recap_start = get_milestone('recap_start')
		recap_end = get_milestone('recap_end')
		if recap_end > recap_start:
			skip_times.append((recap_start, recap_end,))

		intro_start = get_milestone('intro_start')
		intro_end = get_milestone('intro_end')

		if intro_start > 0 and intro_end > intro_start:
			skip_times.append((intro_start, intro_end,))
		elif len(skip_times) == 0:
			skip_times.append((-1, -1,))

		credits_start = get_milestone('up_next')
		tag_start = get_milestone('tag_start')
		tag_end = get_milestone('tag_end')
		skip_times.append((credits_start, tag_start,))

		if tag_end:
			skip_times.append((credits_start, tag_start,))

		return skip_times if len(skip_times) > 0 else None

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		cache_data = self.scache.get(stream_key['ck'])

		return {
			'ext_drm_decrypt': self.get_setting('ext_drm_decrypt'),
			'master_playlist': cache_data['mp'],
			'drm': {
				'licence_url': self.disneyplus.get_config()['services']['drm']['client']['endpoints'][cache_data['lic_key']]['href'],
				'headers': {
					'Authorization': 'Bearer {}'.format(self.disneyplus.login_data.get('access_token')),
				}
			}
		}

	# ##################################################################################################################

	def prepare_playback_urls(self, media_stream, lic_key):
		cache_key = self.http_handler.calc_cache_key(media_stream)
		response = self.disneyplus.req_session.get(media_stream)
		response.raise_for_status()

		pls = DisneyHlsMaster(self, response.url)
		pls.parse(response.text)
		pls.filter_master_playlist()
		pls.cleanup_master_playlist()

		self.scache.put_with_key({'mp': pls, 'lic_key': lic_key}, cache_key)

		play_urls = []
		for i, p in enumerate(pls.audio_playlists):
			play_urls.append( (p.get('NAME', '?'), stream_key_to_hls_url(self.http_endpoint, {'ck': cache_key, 'aid': i}),) )

		return play_urls

	# ##################################################################################################################

	def play_item(self, item_info):
		resource_id = item_info.get('resource_id')
		is_linear = False

		if not resource_id:
			if item_info.get('channel_id'):
				data = self.disneyplus.deeplink(item_info['channel_id'], ref_type='channelId', action='playback')
			elif item_info.get('content_id'):
				data = self.disneyplus.deeplink(item_info['content_id'], ref_type='dmcContentId', action='playback')
			elif item_info.get('family_id'):
				data = self.disneyplus.deeplink(item_info['family_id'], ref_type='encodedFamilyId', action='playback')
			else:
				data = self.disneyplus.deeplink(item_info['deeplink_id'].replace('entity-', ''), action='playback')

			resource_id = data['actions'][0]['resourceId']
			is_linear = data['actions'][0].get('contentType') == 'linear'

		playback_data = self.disneyplus.playback(resource_id)

		if is_linear:
			media_stream = playback_data['stream']['sources'][0]['slide']['url']
			lic_key = 'widevineLinearLicense'
		else:
			media_stream = playback_data['stream']['sources'][0]['complete']['url']
			lic_key = 'widevineLicense'

		player_settings = {}
		if self.silent_mode == False:
			if playback_data['playhead']['status'] == 'PlayheadFound' and playback_data['playhead']['position'] > 0:
				player_settings['resume_time_sec'] = playback_data['playhead']['position']

		player_settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in player_settings['lang_priority']:
			player_settings['lang_fallback'] = ['en']

		player_settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		player_settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		player_settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')
		player_settings['skip_times'] = self.create_skip_times(playback_data['stream'].get('editorial') or [], use_explore=True)
		player_settings['relative_seek_enabled'] = self.get_setting('relative_seek')
#		player_settings['stype'] = 5002

		self.log_debug("Explore media stream URL: %s" % media_stream)

		info_labels = {
			'title': item_info['title']
		}

		pls = self.add_playlist(item_info['title'], True)
		for audio_name, url in self.prepare_playback_urls(media_stream, lic_key):
			pls.add_play(audio_name, url, info_labels=info_labels, settings=player_settings, data_item=playback_data['tracking']['telemetry'])

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if position == None:
			return

		if action in ('watching', 'end'):
			if self.get_setting('sync_playback'):
				telemetry = data_item
				self.disneyplus.update_resume(telemetry['mediaId'], telemetry['fguid'], position)

	# ##################################################################################################################
