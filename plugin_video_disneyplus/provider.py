# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.player.features import PlayerFeatures
from .disneyplus import DisneyPlus
from .httphandler import DisneyHlsMaster
from functools import partial
import base64

WATCHED_PERCENT = 95.0
WATCHLIST_SET_ID = '6f3e3200-ce38-4865-8500-a9f463c1971e'
WATCHLIST_SET_TYPE = 'WatchlistSet'
CONTINUE_WATCHING_SET_ID = '76aed686-1837-49bd-b4f5-5d2a27c0c8d4'
CONTINUE_WATCHING_SET_TYPE = 'ContinueWatchingSet'

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
		PlayerFeatures.request_exteplayer3_version(self, 170)
		self.build_lang_lists()
		self.select_profile_on_startup()

		self.add_search_dir()
		self.add_dir(self._("Home"), cmd=self.collection, slug='home', content_class='home')
		self.add_dir(self._("Hubs"), cmd=self.hubs)
		self.add_dir(self._("Movies"), cmd=self.collection, slug='movies', content_class='contentType')
		self.add_dir(self._("Series"), cmd=self.collection, slug='series', content_class='contentType')
		self.add_dir(self._("Disney Originals"), cmd=self.collection, slug='originals', content_class='originals')

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

	def add_watchlist(self, ref_type, ref_id):
		self.disneyplus.add_watchlist(ref_type, ref_id)
		self.refresh_screen()

	# ##################################################################################################################

	def delete_watchlist(self, ref_type, ref_id):
		self.disneyplus.api.delete_watchlist(ref_type, ref_id)
		self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		if self.disneyplus.feature_flags().get('wpnx-disney-searchOnExplore'):
			data = self.disneyplus.explore_search(keyword)
			return self._process_explore(data['containers'][0]).items if data['containers'] else []
		else:
			data = self.disneyplus.search(keyword)
			hits = [x['hit'] for x in data['hits']]
			return self._process_rows(hits)

	# ##################################################################################################################

	def get_item_metadata(self, row):
		result1 = []

		audio_tracks = {}
		for t in row.get('mediaMetadata', {}).get('audioTracks',[]) or []:
			audio_tracks[t['language'].split('-')[0]] = t['renditionName']

		subtitle_tracks = {}
		for t in row.get('mediaMetadata', {}).get('captions',[]) or []:
			if t['trackType'] != "FORCED":
				subtitle_tracks[t['language'].split('-')[0]] = t['renditionName']

		for l in ('cs', 'sk', 'en'):
			if l in audio_tracks:
				result1.append(l.upper())

		if len(result1) == 0 and audio_tracks:
			result1.append(list(audio_tracks.keys())[0].upper())

		if len(result1) > 0:
			for l in ('cs', 'sk'):
				if l in subtitle_tracks:
					break
			else:
				result1[len(result1)-1] += '/notit'

		return ', '.join(result1), self.get_release_year(row)

	# ##################################################################################################################

	def _get_text(self, row, field, source, add_metadata=False):
		if not row:
			return None

		texts = None
		if 'text' in row:
			# api 5.1
			texts = row['text']
		elif 'texts' in row:
			# api 3.1
			texts = {}
			for data in row['texts']:
				if data['field'] not in texts:
					texts[data['field']] = {}
				texts[data['field']][data['type']] = {data['sourceEntity']: {'default': data}}

		if not texts:
			return None

		_types = ['medium', 'brief', 'full']

		candidates = []
		for key in texts:
			if key != field:
				continue

			for _type in texts[key]:
				if _type not in _types or source not in texts[key][_type]:
					continue

				for t in texts[key][_type][source]:
					candidates.append((_types.index(_type), texts[key][_type][source][t]['content']))

		if not candidates:
			return None

		result = sorted(candidates, key=lambda x: x[0])[0][1]

		if add_metadata:
			metadata = self.get_item_metadata(row)
			for i, m in enumerate(metadata):
				if i == 0:
					if m:
						result += ' - %s' % _I(m)
				else:
					if m:
						result += ' (%s)' % m

		return result

	# ##################################################################################################################

	def _get_art(self, row):
		if not row:
			return {}

		if 'image' in row:
			# api 5.1
			images = row['image']
		elif 'images' in row:
			#api 3.1
			images = {}
			for data in row['images']:
				if data['purpose'] not in images:
					images[data['purpose']] = {}
				images[data['purpose']][str(data['aspectRatio'])] = {data['sourceEntity']: {'default': data}}
		else:
			return None

		def _first_image_url(d):
			for r1 in d:
				for r2 in d[r1]:
					return d[r1][r2]['url']

		art = {}
		# don't ask for jpeg thumb; might be transparent png instead
		thumbsize = '/scale?width=400&aspectRatio=1.78'
		bannersize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'
		fullsize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'

		thumb_ratios = ['1.78', '1.33', '1.00']
		poster_ratios = ['0.71', '0.75', '0.80']
		clear_ratios = ['2.00', '1.78', '3.32']
		banner_ratios = ['3.91', '3.00', '1.78']

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

			if name in ('tile', 'thumbnail'):
				if tr:
					art['thumb'] = _first_image_url(art_type[tr]) + thumbsize
				if pr:
					art['poster'] = _first_image_url(art_type[pr]) + thumbsize

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

		return art

	# ##################################################################################################################

	def hubs(self):
		data = self.disneyplus.collection_by_slug('home', 'home', 'PersonalizedCollection')
		for row in data['containers']:
			_style = row.get('style')
			_set = row.get('set')
			if _set and _style in('brandSix', 'brand'):
				self._process_rows(_set.get('items', []), 'brand')

	# ##################################################################################################################

	def collection(self, slug, content_class):
		data = self.disneyplus.collection_by_slug(slug, content_class, 'PersonalizedCollection' if slug == 'home' else 'StandardCollection')
		if not data:
			return

		def process_row(row):
			_set = row.get('set')
			_style = row.get('style')
			ref_type = _set['refType'] if _set['type'] == 'SetRef' else _set['type']

			if _set.get('refIdType') == 'setId':
				set_id = _set['refId']
			else:
				set_id = _set.get('setId')

			if not set_id:
				return

			if slug == 'home' and (_style in ('brand', 'brandSix', 'hero', 'heroInteractive') or ref_type in ('ContinueWatchingSet', 'WatchlistSet')):
				return

			title = self._get_text(_set, 'title', 'set')

			if not title or '{title}' in title:
				data = self.disneyplus.set_by_id(set_id, ref_type, page_size=0)
				# if not data['meta']['hits']:
				#     return
				title = self._get_text(data, 'title', 'set')
				if not title or '{title}' in title:
					return

			self.add_dir(title, cmd=self._sets, set_id=set_id, set_type=ref_type)

		for row in data['containers']:
			process_row(row)

	# ##################################################################################################################

	def watchlist(self):
		#TODO: if api.feature_flags().get('wpnx-disney-watchlistOnExplore'):
		return self._sets(set_id=WATCHLIST_SET_ID, set_type=WATCHLIST_SET_TYPE)

	# ##################################################################################################################

	def continue_watching(self):
		return self._sets(set_id=CONTINUE_WATCHING_SET_ID, set_type=CONTINUE_WATCHING_SET_TYPE)

	# ##################################################################################################################

	def _sets(self, set_id, set_type, page=1):
		data = self.disneyplus.set_by_id(set_id, set_type, page=page)

		self._process_rows(data.get('items', []), data['type'])

		if (data['meta']['page_size'] + data['meta']['offset']) < data['meta']['hits']:
			self.add_next(cmd=self._sets, set_id=set_id, set_type=set_type, page=page+1)

	# ##################################################################################################################

	def _process_rows(self, rows, content_class=None):
		watchlist_enabled = self.get_setting('sync_watchlist')

		for row in rows:
			menu = self.create_ctx_menu()
			content_type = row.get('type')

			ref_types = ['programId', 'seriesId']
			ref_type = None
			for _type in ref_types:
				if row.get(_type):
					ref_type = _type
					break

			program_type = row.get('programType')

			if watchlist_enabled and ref_type:
				if content_class == 'WatchlistSet':
					menu.add_menu_item(self._('Delete from watchlist'), cmd=self.delete_watchlist, ref_type=ref_type, ref_id=row[ref_type])
				elif (content_type == 'DmcSeries' or (content_type == 'DmcVideo' and program_type != 'episode')):
					menu.add_menu_item(self._('Add to watchlist'), cmd=self.add_watchlist, ref_type=ref_type, ref_id=row[ref_type])

			if content_type == 'DmcVideo':
				if program_type == 'episode':
					if content_class in ('episode', CONTINUE_WATCHING_SET_TYPE):
						self._parse_video(row, menu)
					else:
						self._parse_series(row, menu)
				else:
					self._parse_video(row, menu)

			elif content_type == 'DmcSeries':
				self._parse_series(row, menu)

			elif content_type in ('PersonalizedCollection', 'StandardCollection'):
				self._parse_collection(row, menu)

	# ##################################################################################################################

	def _parse_collection(self, row, menu={}):
		info_labels = {
			'plot': self._get_text(row, 'description', 'collection'),
		}

		title = self._get_text(row, 'title', 'collection')
		img = self._get_art(row).get('poster')

		if row.get('actions', []) and row['actions'][0]['type'] == 'browse':
			self.add_dir(title, img, info_labels=info_labels, menu=menu, cmd=self.explore_page, page_id=row['actions'][0]['pageId'])
		else:
			self.add_dir(title, img, info_labels=info_labels, menu=menu, cmd=self.collection, slug=row['collectionGroup']['slugs'][0]['value'], content_class=row['collectionGroup']['contentClass'])

	# ##################################################################################################################

	def get_release_year(self, row):
		releases = row.get('releases',[]) or []

		if len(releases):
			year = releases[0].get('releaseYear')
		else:
			year = None

		return year

	# ##################################################################################################################

	def load_info_labels(self, family_id=None, series_id=None):
		plot_prefix = ''

		if series_id:
			row = self.disneyplus.series_bundle(series_id)['series']
			genres = [g['name'] for g in row.get('typedGenres') or []]

			if genres:
				plot_prefix = '[' + ' / '.join(genres) + ']\n'

			return {
				'plot': plot_prefix + self._get_text(row, 'description', 'series'),
				'year': self.get_release_year(row),
				'genre': ', '.join(genres)
			}

		elif family_id:
			row = self.disneyplus.video_bundle(family_id)['video']
			genres = [g['name'] for g in row.get('typedGenres') or []]

			if genres:
				plot_prefix = '[' + ' / '.join(genres) + ']\n'

			return {
				'plot': plot_prefix + self._get_text(row, 'description', 'program'),
				'duration': row['mediaMetadata']['runtimeMillis']/1000,
				'year': self.get_release_year(row),
				'genre': ', '.join(genres)
			}

		return {}

	# ##################################################################################################################

	def _parse_series(self, row, menu=None):
		info_labels = {
			'plot': self._get_text(row, 'description', 'series'),
			'year': self.get_release_year(row),
		}

		if not menu:
			menu = self.create_ctx_menu()

		menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, series_id=row['encodedSeriesId'])

		if not info_labels['plot']:
			info_labels = partial(self.load_info_labels, series_id=row['encodedSeriesId'])

		self.add_dir(self._get_text(row, 'title', 'series', True), self._get_art(row).get('poster'), info_labels=info_labels, menu=menu, cmd=self.series, series_id=row['encodedSeriesId'])

	# ##################################################################################################################

	def _parse_season(self, row, series):
		title = self._("Season") + ': %d' % row['seasonSequenceNumber']
		img = self._get_art(row) or self._get_art(series)
		if img:
			img = img.get('poster')


		info_labels = {
			'plot': self._get_text(row, 'description', 'season') or self._get_text(series, 'description', 'series'),
			'year': self.get_release_year(row),
			'season': row['seasonSequenceNumber'],
		}
		self.add_dir(title, img, info_labels=info_labels, cmd=self.season, season_id=row['seasonId'])

	# ##################################################################################################################

	def _parse_video(self, row, menu=None):
		if not menu:
			menu = self.create_ctx_menu()

		info_labels  = {
			'plot': self._get_text(row, 'description', 'program'),
			'duration': row['mediaMetadata']['runtimeMillis']/1000,
			'year': self.get_release_year(row),
		}

		if row['programType'] == 'episode':
			info_labels.update({
				'season': row['seasonSequenceNumber'],
				'episode': row['episodeSequenceNumber'],
				'tvshowtitle': self._get_text(row, 'title', 'series'),
			})
		else:
			if not info_labels['plot']:
				info_labels = partial(self.load_info_labels, family_id=row['family']['encodedFamilyId'])

			menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, family_id=row['family']['encodedFamilyId'])
			menu.add_menu_item(self._('Extras'), cmd=self.extras, family_id=row['family']['encodedFamilyId'])
			menu.add_menu_item(self._('Suggested'), cmd=self.suggested, family_id=row['family']['encodedFamilyId'])

		self.add_video(self._get_text(row, 'title', 'program', True), self._get_art(row).get('poster'), info_labels=info_labels, menu=menu, cmd=self.play_item, content_id=row['contentId'])

	# ##################################################################################################################

	def series(self, series_id):
		data = self.disneyplus.series_bundle(series_id)
		art = self._get_art(data['series'])
		title = self._get_text(data['series'], 'title', 'series')

		for row in data['seasons']['seasons']:
			self._parse_season(row, data['series'])

		if data['extras']['videos']:
			self.add_dir(self._("Extras"), art.get('poster'), cmd=self.extras, series_id=series_id)

		if data['related']['items']:
			self.add_dir(self._("Suggested"), art.get('poster'), cmd=self.suggested, series_id=series_id)

	# ##################################################################################################################

	def season(self, season_id, page=1):
		data = self.disneyplus.episodes(season_id, page=page)
		self._process_rows(data['videos'], content_class='episode')

		if (data['meta']['page_size'] + data['meta']['offset']) < data['meta']['hits']:
			self.add_next(cmd=self.season, season_id=season_id, page=page+1)

	# ##################################################################################################################

	def suggested(self, family_id=None, series_id=None):
		if family_id:
			data = self.disneyplus.video_bundle(family_id)
		elif series_id:
			data = self.disneyplus.series_bundle(series_id)

		self._process_rows(data['related']['items'])

	# ##################################################################################################################

	def play_trailer(self, family_id=None, series_id=None):
		if family_id:
			data = self.disneyplus.video_bundle(family_id)
		elif series_id:
			data = self.disneyplus.series_bundle(series_id)

		videos = [x for x in data['extras']['videos'] if x.get('contentType') == 'trailer']
		if not videos:
			return

		return self.play_item(content_id=videos[0]['contentId'])

	# ##################################################################################################################

	def extras(self, family_id=None, series_id=None):
		if family_id:
			data = self.disneyplus.video_bundle(family_id)
		elif series_id:
			data = self.disneyplus.series_bundle(series_id)

		self._process_rows(data['extras']['videos'])

	# ##################################################################################################################

	def explore_page(self, page_id):
		data = self.disneyplus.explore_page(page_id)
		self._process_explore(data)

	# ##################################################################################################################

	def explore_set(self, set_id, page=1):
		data = self.disneyplus.explore_set(set_id, page=page)
		self._process_explore(data)
		if data['pagination']['hasMore']:
			self.add_next(cmd=self.explore_set, set_id=set_id, page=page+1)

	# ##################################################################################################################

	def explore_season(self, show_id, season_id):
		data = self.disneyplus.explore_season(season_id)
		self._process_explore(data)

	# ##################################################################################################################

	def _process_explore(self, data):
		title = data['visuals'].get('title') or data['visuals'].get('name')

		if 'containers' in data:
			rows = data['containers']
		elif 'items' in data:
			rows = data['items']
		else:
			rows = []

		is_show = 'seasonsAvailable' in data['visuals'].get('metastringParts', {})
		is_season = data['type'] == 'season'

		for row in rows:
			if not is_show and row['type'] == 'set' and row['pagination'].get('totalCount', 0) > 0:
				self.add_dir(row['visuals']['name'], self._get_explore_art(row).get('poster'), cmd=self.explore_set, set_id=row['id'])

			elif is_show and row['type'] == 'episodes':
				for season in row.get('seasons', []):
					info_labels = {
						'plot': data['visuals']['description']['full'],
						'tvshowtitle': title,
					}

					self.add_dir(season['visuals']['name'], self._get_explore_art(season).get('poster'), info_labels=info_labels, cmd=self.explore_season, show_id=data['id'], season_id=season['id'])

			elif is_season and row['type'] == 'view':
				info_labels = {
					'plot': row['visuals']['description']['full'],
					'season': row['visuals']['seasonNumber'],
					'episode': row['visuals']['episodeNumber'],
					'tvshowtitle': row['visuals']['title'],
					'duration': int(row['visuals'].get('durationMs',0) / 1000),
				}

				self.add_video(row['visuals']['episodeTitle'], self._get_explore_art(row).get('poster'), info_labels=info_labels, cmd=self.play_explore, resource_id=row['actions'][0]['resourceId'])

			elif not is_show and row.get('actions', []) and row['actions'][0]['type'] in ('browse', 'legacyBrowse'):
				meta = row['visuals']['metastringParts']
				title = row['visuals']['title']
				img = self._get_explore_art(row).get('poster')

				info_labels = {}

				if 'description' in row['visuals']:
					info_labels['plot'] = row['visuals']['description']['full']

				if 'releaseYearRange' in meta:
					info_labels['year'] = meta['releaseYearRange']['startYear']

				if 'genres' in meta:
					info_labels['genre'] = meta['genres']['values']

				if 'ratingInfo' in meta:
					info_labels['rating'] = meta['ratingInfo']['rating']['text']

				info = base64.b64decode(row['infoBlock'])
				if b':movie' in info:
					self.add_video(title, img, info_labels=info_labels, cmd=self.play_item, family_id=row['actions'][0]['refId'])

					if row['actions'][0]['type'] == 'legacyBrowse':
						self.add_video(title, img, info_labels=info_labels, cmd=self.play_item, family_id=row['actions'][0]['refId'])
					else:
						self.add_video(title, img, info_labels=info_labels, cmd=self.play_explore, page_id=row['actions'][0]['pageId'])

				elif b':series' in info and row['actions'][0]['type'] == 'legacyBrowse':
					self.add_dir(title, img, info_labels=info_labels, cmd=self.series, series_id=row['actions'][0]['refId'])
				elif row['actions'][0]['type'] == 'browse':
					self.add_dir(title, img, info_labels=info_labels, cmd=self.explore_page, page_id=row['actions'][0]['pageId'])

	# ##################################################################################################################

	def _get_explore_art(self, row):
		if not row or 'artwork' not in row['visuals']:
			return {}

		images = row['visuals']['artwork']['standard']
		if 'tile' in row['visuals']['artwork']:
			images['hero_tile'] = row['visuals']['artwork']['tile']['background']
		if 'hero' in row['visuals']['artwork']:
			images['background'] = row['visuals']['artwork']['hero']['background']
		if 'network' in row['visuals']['artwork']:
			images['thumbnail'] = row['visuals']['artwork']['network']['tile']

		def _first_image_url(d):
			return 'https://disney.images.edge.bamgrid.com/ripcut-delivery/v1/variant/disney/{}'.format(d['imageId'])

		art = {}
		# don't ask for jpeg thumb; might be transparent png instead
		thumbsize = '/scale?width=400&aspectRatio=1.78'
		bannersize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'
		fullsize = '/scale?width=1440&aspectRatio=1.78&format=jpeg'

		thumb_ratios = ['1.78', '1.33', '1.00']
		poster_ratios = ['0.71', '0.75', '0.80']
		clear_ratios = ['2.00', '1.78', '3.32']
		banner_ratios = ['3.91', '3.00', '1.78']

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

			if name in ('tile', 'thumbnail'):
				if tr:
					art['thumb'] = _first_image_url(art_type[tr]) + thumbsize
				if pr:
					art['poster'] = _first_image_url(art_type[pr]) + thumbsize

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

		return art

	# ##################################################################################################################

	def create_skip_times(self, milestones):
		skip_times = []

		if not milestones:
			return None

		def get_milestone(name, default=0):
			for key in milestones:
				if key == name:
					return int(milestones[key][0]['milestoneTime'][0]['startMillis'] / 1000)

			return default

		intro_start = get_milestone('intro_start')
		intro_end = get_milestone('intro_end')

		if intro_start > 0 and intro_end > intro_start:
			skip_times.append((intro_start, intro_end,))
		else:
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
		return {
			'master_playlist': self.scache.get(stream_key['ck']),
			'drm': {
				'licence_url': self.disneyplus.get_config()['services']['drm']['client']['endpoints']['widevineLicense']['href'],
				'headers': {
					'Authorization': 'Bearer {}'.format(self.disneyplus.login_data.get('access_token')),
				}
			}
		}

	# ##################################################################################################################

	def prepare_playback_urls(self, media_stream):
		cache_key = self.http_handler.calc_cache_key(media_stream)
		response = self.disneyplus.req_session.get(media_stream)
		response.raise_for_status()

		pls = DisneyHlsMaster(self, response.url)
		pls.parse(response.text)
		pls.filter_master_playlist()
		pls.cleanup_master_playlist()

		self.scache.put_with_key(pls, cache_key)

		play_urls = []
		for i, p in enumerate(pls.audio_playlists):
			play_urls.append( (p.get('NAME', '?'), stream_key_to_hls_url(self.http_endpoint, {'ck': cache_key, 'aid': i}),) )

		return play_urls

	# ##################################################################################################################

	def play_item(self, family_id=None, content_id=None):
		if family_id:
			data = self.disneyplus.video_bundle(family_id)
		else:
			data = self.disneyplus.video(content_id)

		video = data.get('video')
		if not video:
			raise AddonErrorException("Video not found")

		playback_url = video['mediaMetadata']['playbackUrls'][0]['href']
		playback_data = self.disneyplus.playback_data(playback_url)
		telemetry = playback_data['tracking']['telemetry']

		try:
			#v6
			media_stream = playback_data['stream']['sources'][0]['complete']['url']
		except KeyError:
			#v5
			media_stream = playback_data['stream']['complete'][0]['url']

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
		player_settings['skip_times'] = self.create_skip_times(video.get('milestone', []))
		player_settings['relative_seek_enabled'] = self.get_setting('relative_seek')
#		player_settings['stype'] = 5002

		self.log_debug("Media stream URL: %s" % media_stream)

		pls = self.add_playlist(self._get_text(video, 'title', 'program'), True)
		for audio_name, url in self.prepare_playback_urls(media_stream):
			pls.add_play(audio_name, url, settings=player_settings, data_item=telemetry)

	# ##################################################################################################################

	def play_explore(self, page_id=None, resource_id=None):
		if resource_id is None:
			data = self.disneyplus.explore_page(page_id)
			play_action = [x for x in data['actions'] if x['type'] == 'playback'][0]
			resource_id = play_action['resourceId']

		playback_data = self.disneyplus.explore_playback(resource_id)
		player_settings = {
#			'stype': 5002,
			'relative_seek_enabled': self.get_setting('relative_seek')
		}

		media_stream = playback_data['stream']['sources'][0]['complete']['url']

		self.log_debug("Media stream URL: %s" % media_stream)

		pls = self.add_playlist("Video", True)
		for audio_name, url in self.prepare_playback_urls(media_stream):
			pls.add_play(audio_name, url, settings=player_settings)

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if position == None:
			return

		if action in ('watching', 'end'):
			if self.get_setting('sync_playback'):
				telemetry = data_item
				self.disneyplus.update_resume(telemetry['mediaId'], telemetry['fguid'], position)

	# ##################################################################################################################
