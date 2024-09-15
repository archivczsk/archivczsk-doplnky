# -*- coding: utf-8 -*-
try:
	from Plugins.Extensions.archivCZSK.engine.trakttv import trakttv
except:
	trakttv = None

import re, sys
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman, strip_accents
from tools_archivczsk.cache import lru_cache
from bisect import bisect
from .webshare import Webshare, WebshareLoginFail, ResolveException, WebshareApiError
from .scc_api import SCC_API
from .watched import SCWatched
from .lang_lists import lang_code_to_lang
from .seasonal_events import SeasonalEventManager
from .csfd import Csfd

# ##################################################################################################################

# fake translation func - needed for gettext to properly extract texts needed for translation
def _(s):
	return s

# ##################################################################################################################


class SccContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'SCC', settings=settings, data_dir=data_dir)
		self.login_optional_settings_names = ('wsuser', 'wspass')
		self.tapi = trakttv
		self.webshare = None
		self.scc = None
		self.page_size = 100

		if not self.get_setting('deviceid'):
			self.set_setting('deviceid', SCC_API.create_device_id())

		self.watched = SCWatched(self.data_dir, trakttv, int(self.get_setting('keep-last-seen')))

		# init SCC Api - will be good to cache its settings and reinit it when some of them change
		self.api = SCC_API(self)
		self.csfd = Csfd(self)
		self.webshare = Webshare(self)

	# ##################################################################################################################

	def webshare_update_vipdays(self):
		try:
			days_left = self.webshare.refresh_login_data()
		except:
			days_left = -2

		# update remaining vip days
		if self.get_setting('wsvipdays') != str(days_left):
			self.set_setting('wsvipdays', str(days_left))

		return days_left

	# ##################################################################################################################

	def login(self, silent):
		if self.webshare_update_vipdays() <= 0:
			# no username/password provided or vip expired - continue with free account
			if self.get_setting('wsuser') and self.get_setting('wspass'):
				self.log_info("Webshare VIP account expired - continuing with free account")

				if not silent:
					self.show_info(self._("Webshare VIP account expired"), noexit=True)
				else:
					# return False, so we can show message about expired account to user when no silent flag will be set
					return False
			else:
				self.log_info("No webshare username or password provided - continuing with free account")

				if not silent:
					self.show_info(self._("No Webshare username and password provided - continuing with free account"), noexit=True)
				else:
					return False

		return True

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

	def root(self, media_type=None):
		if media_type == None:
			self.webshare_update_vipdays()

			# render main menu
			self.add_search_dir()
			self.add_dir(self._("Movies"), cmd=self.root, media_type='movie')
			self.add_dir(self._("Series"), cmd=self.root, media_type='tvshow')
			self.show_current_seasonal_events()
			self.show_trakt_dir()
			self.add_dir(self._("CSFD Tips"), cmd=self.show_csfd_list, media_type='movie', csfd_cbk=self.csfd.get_tips)
			self.add_dir(self._("Concerts"), cmd=self.root, media_type='concert')
			self.add_dir(self._("Anime"), cmd=self.root, media_type='anime')
			self.add_dir(self._("Thematic lists"), cmd=self.show_thematic_lists)
		elif media_type == 'anime':
			self.add_dir(self._("All"), cmd=self.root, media_type='anime-*')
			self.add_dir(self._("Movies"), cmd=self.root, media_type='anime-movie')
			self.add_dir(self._("Series"), cmd=self.root, media_type='anime-tvshow')
		elif media_type in ('movie', 'tvshow', 'concert') or media_type.startswith('anime-'):
			category = media_type.replace('*', 'all')
			lang_list = self.get_dubbed_lang_list()

			self.show_last_seen_dir(media_type, category)
			self.add_search_dir(search_id=category)
			self.add_dir(self._("Trending"), cmd=self.call_filter_api, params={'type': media_type, 'sort': 'trending', 'order': 'desc'}, render_params={'category': category})
			if media_type == 'tvshow':
				self.add_dir(self._("New episodes"), cmd=self.call_filter_api, params={'type': media_type, 'sort': 'lastChildPremiered', 'days': 365, 'order': 'desc'}, render_params={'category': category})
			self.add_dir(self._("Popular"), cmd=self.call_filter_api, params={'type': media_type, 'sort': 'popularity', 'order': 'desc'}, render_params={'category': category})
			self.add_dir(self._("Most watched"), cmd=self.call_filter_api, params={'type': media_type, 'sort':'playCount', 'order': 'desc' }, render_params={'category': category})
			self.add_dir(self._("New releases"), cmd=self.call_filter_api, filter_name='news', params={'type': media_type, 'sort': 'dateAdded', 'order': 'desc', 'days': 365}, render_params={'category': category})
			self.add_dir(self._("New dubbed releases"), cmd=self.call_filter_api, filter_name='newsDubbed', params={'type': media_type, 'sort': 'langDateAdded', 'order': 'desc', 'days': 730, 'lang': lang_list}, render_params={'category': category})
			self.add_dir(self._("New releases with subtitles"), cmd=self.call_filter_api, filter_name='newsSubs', params={'type': media_type, 'sort': 'dateAdded', 'order': 'desc', 'days': 730, 'lang': lang_list}, render_params={'category': category})
			self.add_dir(self._("Latest added"), cmd=self.call_filter_api, params={'type': media_type, 'sort': 'dateAdded', 'days': 365, 'order': 'desc'}, render_params={'category': category})
			self.add_dir(self._("Latest added streams"), cmd=self.call_filter_api, params={'type': media_type, 'sort': 'lastChildrenDateAdded', 'days': 365, 'order': 'desc'}, render_params={'category': category})

			if media_type in ('movie', 'tvshow'):
				self.add_dir(self._("CSFD Top 100"), cmd=self.show_csfd_list, media_type=media_type, csfd_cbk=lambda: self.csfd.get_top(media_type, Csfd.TOP100_ALL))
				self.add_dir(self._("CSFD Top 100 CZ & SK"), cmd=self.show_csfd_list, media_type=media_type, csfd_cbk=lambda: self.csfd.get_top(media_type, Csfd.TOP100_CSSK))
				self.add_dir(self._("CSFD Top 100 CZ"), cmd=self.show_csfd_list, media_type=media_type, csfd_cbk=lambda: self.csfd.get_top(media_type, Csfd.TOP100_CS))
				self.add_dir(self._("CSFD Top 100 SK"), cmd=self.show_csfd_list, media_type=media_type, csfd_cbk=lambda: self.csfd.get_top(media_type, Csfd.TOP100_SK))

			self.add_dir(self._("By alphabet"), cmd=self.call_filter_count_api, filter_name='startsWithSimple', count_name='titles', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'az'})
			self.add_dir(self._("By genre"), cmd=self.call_filter_count_api, count_name='genres', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'genre'})
			self.add_dir(self._("By country"), cmd=self.call_filter_count_api, count_name='countries', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'country'})
			self.add_dir(self._("By language"), cmd=self.call_filter_count_api, count_name='languages', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'language'})
			self.add_dir(self._("By year"), cmd=self.call_filter_count_api, count_name='years', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'year'})
			self.add_dir(self._("By studio"), cmd=self.call_filter_count_api, count_name='studios', params={'type': media_type, 'value': ''}, render_params={'category': category, 'folder': 'studio'})

	# ##################################################################################################################

	def show_last_seen_dir(self, media_type, category):
		# if there are no items in history, then do not show this dir
		ids = self.watched.get(media_type)
		if len(ids) == 0:
			return

		def check_and_call_filter_api(**kwargs):
			if len(ids) > 0:
				self.call_filter_api(**kwargs)

		self.add_dir(self._("Last seen"), cmd=check_and_call_filter_api, filter_name='ids', params={ 'id': ids, 'type': media_type }, render_params={'category': category, 'folder': 'last_seen'})

	# ##################################################################################################################

	def show_thematic_lists(self):
		lists_info = [
			{ 'name': _('Fairy Tales'), 'id': 'rozpravky'},
			{ 'name': _('Golden fund'), 'id': 'zlaty-fond-cz-sk' },
			{ 'name': _('Czech and Slovak'), 'id': 'czech_slovak' },
			{ 'name': _('Movie Club'), 'id': 'club' },
			{ 'name': _('Religious'), 'id': 'nabozenske' }
		]

		lists_info.extend(SeasonalEventManager.current_region_all_events(self.get_lang_code()))

		for info in lists_info:
			self.add_dir(self._(info['name']), cmd=self.show_trakt_list, user=info.get('user', 'tarzanislav'), list_id=info['id'])

	# ##################################################################################################################

	def show_current_seasonal_events(self):
		lists_info = SeasonalEventManager.current_region_events(self.get_lang_code())

		for info in lists_info:
			self.add_dir(self._(info['name']), cmd=self.show_trakt_list, user=info.get('user', 'tarzanislav'), list_id=info['id'])

	# ##################################################################################################################

	def show_trakt_list(self, user, list_id):
		@lru_cache(30, timeout=1800)
		def get_list_items(list_id, user):
			return self.tapi.get_list_items(list_id, user)

		ids = []
		# get list from Trakt.tv and extract trakt ID + type
		for data in get_list_items(list_id, user):
			scc_type = 'tvshow' if data['type'] == 'show' else data['type']
			ids.append(scc_type + ':' + str(data[data['type']]['ids']['trakt']))

		self.call_filter_api('service', params={'type': '*', 'service': 'trakt_with_type', 'value': ids }, render_params={'folder': 'trakt'})

	# ##################################################################################################################

	def show_csfd_list(self, media_type, csfd_cbk, **kwargs):
		@lru_cache(30, timeout=1800)
		def get_list_items(**kwargs):
			return csfd_cbk(**kwargs)

		ids = get_list_items(**kwargs)

		self.call_filter_api('service', params={'type': media_type, 'service': 'csfd', 'value': ids }, render_params={'category': media_type, 'folder': 'csfd'})

	# ##################################################################################################################

	def show_trakt_history(self, media_type):
		@lru_cache(30, timeout=1800)
		def get_list_items(media_type):
			if media_type == 'movie':
				return self.tapi.get_watched_movies()
			else:
				return self.tapi.get_watched_shows()

		ids = []
		# get list from Trakt.tv and extract trakt ID + type
		for data in get_list_items(media_type):
			ids.append(media_type + ':' + str(data['trakt']))

		self.call_filter_api('service', params={'type': '*', 'service': 'trakt_with_type', 'value': ids }, render_params={'folder': 'trakt'})

	# ##################################################################################################################

	def show_trakt_dir(self, dir_type=None, page=0):
		if not self.get_setting('trakt_enabled'):
			return

		if dir_type == None:
			self.add_dir(self._("Trakt.tv"), cmd=self.show_trakt_dir, dir_type='root')
		elif dir_type == 'root':
			self.add_dir(self._("My lists"), cmd=self.show_trakt_dir, dir_type='my_lists')
			self.add_dir(self._("History"), cmd=self.show_trakt_dir, dir_type='history')
			self.add_dir(self._("Trending"), cmd=self.show_trakt_dir, dir_type='trending')
			self.add_dir(self._("Popular"), cmd=self.show_trakt_dir, dir_type='popular')
		elif dir_type == 'history':
			self.add_dir(self._("Movies"), cmd=self.show_trakt_dir, dir_type='history_movies')
			self.add_dir(self._("Series"), cmd=self.show_trakt_dir, dir_type='history_shows')
		elif dir_type == 'history_movies':
			self.show_trakt_history('movie')
		elif dir_type == 'history_shows':
			self.show_trakt_history('tvshow')
		elif dir_type == 'my_lists':
			try:
				tlist = self.tapi.get_lists()
			except Exception as e:
				self.log_exception()
				raise AddonErrorException("%s: %s" % (self._("Failed to load trakt.tv list"), str(e)))

			for titem in tlist:
				self.add_dir(titem['name'], info_labels={'plot': titem.get('description')}, cmd=self.show_trakt_list, user='me', list_id=titem['id'])
		elif dir_type in ('trending', 'popular'):
			try:
				tlist = self.tapi.get_global_lists(dir_type, page)
			except Exception as e:
				self.log_exception()
				raise AddonErrorException("%s: %s" % (self._("Failed to load trakt.tv list"), str(e)))

			for titem in tlist:
				if titem['id'] and titem['user']:
					self.add_dir(titem['name'], info_labels={'plot': titem.get('description')}, cmd=self.show_trakt_list, user=titem['user'], list_id=titem['id'])
			self.add_next(cmd=self.show_trakt_dir, page_info=(page + 2), dir_type=dir_type, page=page + 1)

	# ##################################################################################################################

	def call_filter_count_api(self, filter_name='all', count_name='titles', params={}, render_params={}, page=0):
		# build query
		page_size = 200
		req_params = {
			'from': page * page_size,
			'limit': page_size
		}
		req_params.update(params)

		data = self.api.call_filter_count_api(filter_name, count_name, req_params).get('data', [])

		self.render_count_dir(data, params, **render_params)

		if len(data) >= page_size:
			page += 1
			self.add_next(cmd=self.call_filter_count_api, page_info=(page + 1), filter_name=filter_name, count_name=count_name, page=page, params=params, render_params=render_params)

	# ##################################################################################################################

	def call_filter_api(self, filter_name='all', params={}, render_params={}, page=0):
		# build query
		req_params = {
			'from': page * self.page_size,
			'size': self.page_size
		}
		req_params.update(params)

		data = self.api.call_filter_api(filter_name, req_params).get('hits', {})

		self.render_media_dir(data, **render_params)

		if 'total' in data:
			total = data['total']['value']
			page_count = int(total // self.page_size)
			page += 1
			if page <= page_count:
				self.add_next(cmd=self.call_filter_api, page_info=(page + 1, page_count + 1,), filter_name=filter_name, page=page, params=params, render_params=render_params)

	# ##################################################################################################################

	def is_adult_content(self, media):
		if media.get('adult', False) == True:
			return True

		genres = media.get('info_labels', {}).get('genre', [])

		return ('Pornographic' in genres) or ('Erotic' in genres) or ('Adult' in genres) or ('porno' in media.get('tags', []))

	# ##################################################################################################################

	def is_adult_dir(self, name):
		return name in ('Adult', 'Pornographic', 'Erotic')

	# ##################################################################################################################

	def lang_filter_passed(self, media):
		item_filter = self.get_setting('item-lang-filter')
		stream_filter = self.get_setting('stream-lang-filter').split('+')

		if item_filter == 'all':
			return True

		if stream_filter[0] == 'all':
			return True

		alangs = media.get("available_streams", {}).get("languages", {}).get("audio", {}).get("map", [])

		if item_filter == 'dub':
			for l in stream_filter:
				if l in alangs:
					return True

		subs = media.get("available_streams", {}).get("languages", {}).get("subtitles", {}).get("map", [])
		if item_filter == 'dubsubs':
			for l in stream_filter:
				if l in subs:
					return True

		return False

	# ##################################################################################################################

	def get_i18n_list(self, i18n_base ):
		lang = self.get_lang_code()

		if lang == 'sk':
			lang_list = ['sk', 'cs', 'en']
		elif lang == 'cs':
			lang_list = ['cs', 'sk', 'en']
		else:
			lang_list = ['en', 'cs', 'sk']

		ll = []
		for l in lang_list:
			for lb in i18n_base:
				if lb.get('lang') == l:
					ll.append(lb)

		return ll

	# ##################################################################################################################

	def get_media_info(self, media, title_hint=None):
		def check_ascii(s):
			if sys.version_info[0] >= 3 and sys.version_info[1] >= 7:
				return s.isascii()
			else:
				try:
					s.decode('ascii')
					return True
				except:
					return False

		# build title, img and info_labels dictionary

		# title_hint is used when building title for a-z menu because of horrible API and results - bleah :-(
		if title_hint:
			title_hint = re.sub(r'[^A-Za-z0-9]+|\s+', '', strip_accents(title_hint)).lower()

		title = ''
		ep_code = ''
		ep_code2 = ''
		se_title = ''
		ep_name_postfix = ''
		info_labels = {}
		img = None

		i18n_info = self.get_i18n_list(media.get('i18n_info_labels', []))
		info = media.get('info_labels', {})
		media_type = info.get('mediatype')

		if media_type == 'episode':
			title = self._("Episode") + ' %02d' % info['episode']
			info_labels['episode'] = info['episode']

			if info.get('season'):
				ep_code = ' %s (%d)' % (int_to_roman(info['season']), info['episode'])
				ep_code2 = ' S%02dE%02d' % (int(info['season']), int(info['episode']))
				info_labels['season'] = info['season']
			else:
				ep_code = ' (%d)' % info['episode']
				ep_code2 = ' E%02d' % int(info['episode'])
		elif media_type == 'season':
			if info.get('season'):
				ep_code = ' %s' % int_to_roman(info['season'])
				info_labels['season'] = info['season']

		if i18n_info:
			for l in i18n_info:
				if l.get('title'):
					info_title = l['title']

					if title_hint and info_title:
						stripped_value = re.sub(r'[^A-Za-z0-9]+|\s+', '', strip_accents(info_title)).lower()
						if not stripped_value.startswith(title_hint):
							info_title = None

					# check if there is at leas one ascii char in title - there is a lot of mess in database ...
					if info_title and any(check_ascii(c) and (not c.isspace()) for c in info_title):
						if media_type == 'episode':
							info_labels['epname'] = info_title
							ep_name_postfix = ': ' + info_title

						if title:
							title += ': ' + info_title
						else:
							title = info_title
						break

			for l in i18n_info:
				if 'parent_titles' in l and len(l['parent_titles']) > 0:
					se_title = l['parent_titles'][0]
					info_labels['sename'] = se_title
					break

			for l in i18n_info:
				info_labels['plot'] = l.get('plot')
				if info_labels['plot']:
					break

			for l in i18n_info:
				img = l.get('art', {}).get('poster')
				if img:
					if img.startswith('//'):
						img = 'http:' + img
					break

		info_labels['duration'] = info.get('duration')
		info_labels['year'] = info.get('year')

		if not title:
			title = info.get('originaltitle') or ''

		info_labels['title'] = (se_title or title) + ep_code
		info_labels['search_keyword'] = (se_title or title) + ep_code2
		info_labels['filename'] = (se_title or title) + ep_code2 + ep_name_postfix

		info_labels['genre'] = ', '.join(self._(g) for g in info.get('genre', []))
		if info_labels['genre']:
			# prefix list of genres to plot
			info_labels['plot'] = '[' + ' / '.join(self._(g) for g in info['genre']) + ']\n' + (info_labels.get('plot','') or '')

		ratings = media.get('ratings', {})
		ratings = ratings.get('csfd', ratings.get('tmdb', ratings.get('trakt', {})))
		info_labels['rating'] = ratings.get('rating')

		# add aditional informations to title

		alangs = media.get("available_streams", {}).get("languages", {}).get("audio", {}).get("map", [])
		subs_available = self.get_lang_code() in media.get("available_streams", {}).get("languages", {}).get("subtitles", {}).get("map", [])

		# mark that there are subtitles available
		alangs_upper = []
		for l in alangs:
			if subs_available and l not in ('cs', 'sk'):
				alangs_upper.append(l.upper() + '+tit')
			else:
				alangs_upper.append(l.upper())

		if alangs_upper:
			title += ' - ' + _I(', '.join(sorted(set(alangs_upper))))

		if info_labels['year']:
			title += ' (%d)' % info_labels['year']

		return title, img, info_labels, media_type

	# ##################################################################################################################

	def fill_trakt_info(self, menu_item, is_watched=None):
		if not self.get_setting('trakt_enabled'):
			return None

		services = menu_item.get('services')

		if not services:
			return None

		if 'trakt_with_type' in services:
			trakt_type, trakt_id = services['trakt_with_type'].split(':')
			trakt_items = {
				'watched': is_watched,
				'type': trakt_type,
				'ids': {
					'trakt': trakt_id
				}
			}
		else:
			mediatype = menu_item.get('info_labels', {}).get('mediatype')

			if mediatype == None:
				return None

			if mediatype == 'movie':
				trakt_type = 'movie'
			else:
				trakt_type = 'show'

			trakt_items = {
				'watched': is_watched,
				'type': trakt_type,
				'ids': services,
				'episode': menu_item['info_labels'].get('episode') if mediatype == 'episode' else None,
				'season': menu_item['info_labels'].get('season') if mediatype in ('episode', 'season') else None,
			}

		return { k: v for k, v in trakt_items.items() if v is not None }

	# ##################################################################################################################

	def remove_from_seen(self, category, media_id):
		self.watched.remove(category, media_id)
		self.watched.save()
		self.refresh_screen()

	# ##################################################################################################################

	def render_count_dir(self, data, params, category=None, folder=None):
		enable_adult = self.get_setting('enable-adult')

		render_params = {
			'category': category,
			'folder': folder
		}

		if folder == 'az':
			for az in data:
				if not az['key']:
					continue

				title = az['key'] + _I(' (' + str(az['doc_count']) + ')')

				if az['doc_count'] < 50:
					params2 = {
						'type': params['type'],
						'value': az['key'],
						'sort': 'year',
						'order': 'desc'
					}

					render_params2 = {
						'category': category,
						'folder': 'az:' + az['key']
					}
					self.add_dir(title, cmd=self.call_filter_api, filter_name='startsWithSimple', params=params2, render_params=render_params2)
				else:
					params = params.copy()
					params['value'] = az['key']
					self.add_dir(title, cmd=self.call_filter_count_api, params=params, render_params=render_params)
		else:
			for item in data:
				if not item['key']:
					continue

				title = item['key']


				if folder == 'genre':
					is_adult = self.is_adult_dir(title)

					if is_adult and enable_adult == False:
						continue
				else:
					is_adult = False

				if folder == 'language':
					if len(title) != 2:
						# filter out some garbage with no results that is returned from server
						continue

					# translate lang code to country name
					title = lang_code_to_lang.get(title, title)

				if folder in ('genre', 'country', 'language'):
					title = self._(title)

				title += _I(' (' + str(item['doc_count']) + ')')

				params2 = {
					'type': params['type'],
					'value': item['key'],
					'sort': 'year',
					'order': 'desc'
				}
				self.add_dir(title, info_labels={'adult': is_adult}, cmd=self.call_filter_api, filter_name=folder, params=params2, render_params=render_params)
			self.sort_content_items(reverse=(folder == 'year'), use_diacritics=False, ignore_case=True)

	# ##################################################################################################################

	def render_media_dir(self, data, category=None, services=None, folder=None):
		# this is needed for trakt - we need unique id's of parent for seasons and episodes
		prehrajto_primary = self.get_setting('prehrajto-primary')
		services_parent = services
		title_hint = folder[3:].lower() if folder is not None and folder.startswith('az:') else None
		enable_adult = self.get_setting('enable-adult')

		for media in data.get('hits', []):
			source = media['_source']
			media_type = source.get('info_labels', {}).get('mediatype')

			if category == None or category.endswith('-all'):
				# category not set, so try to guess it
				if category and category.endswith('-all'):
					cat = category[:-4]
					if len(cat) > 0:
						cat += '-'
				else:
					cat = ''

				if media_type == 'movie':
					cat += 'movie'
				elif media_type in ('season', 'episode'):
					cat += 'tvshow'
				elif media_type == 'concert' or source.get('is_concert', False):
					cat += 'concert'
				else:
					cat = None
			else:
				cat = category

			is_adult = self.is_adult_content(source)
			if is_adult and enable_adult == False:
				continue

			if self.lang_filter_passed(source) == False:
				continue

			title, img, info_labels, media_type = self.get_media_info(source, title_hint)
			info_labels['adult'] = is_adult
			menu = self.create_ctx_menu()

			if folder == 'last_seen':
				menu.add_menu_item(self._('Remove from seen'), cmd=self.remove_from_seen, category=cat, media_id=media['_id'])

			if not prehrajto_primary:
				menu.add_menu_item(self._('Search on prehraj.to'), cmd=self.prehrajto_search, keyword=info_labels['search_keyword'])

			if len(source.get('videos', [])) > 0:
				menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, media_id=media['_id'])

			is_watched = None

			if services_parent == None:
				services = source.get('services')
			else:
				services = services_parent

			if services:
				cid = services.get('csfd')
				if cid:
					cid = int(cid)
					menu.add_menu_item(self._('Related'), cmd=self.show_csfd_list, media_type='movie', csfd_cbk=self.csfd.get_related, cid=cid)
					menu.add_menu_item(self._('Similar'), cmd=self.show_csfd_list, media_type='movie', csfd_cbk=self.csfd.get_similar, cid=cid)

				if self.get_setting('trakt_enabled'):
					# check if this item is watched
					if media_type == 'movie':
						is_watched = self.watched.is_trakt_watched_movie(services)
						is_fully_watched = True
					elif media_type == 'episode':
						is_watched = self.watched.is_trakt_watched_show(services, source['info_labels'].get('season', 1), source['info_labels'].get('episode'))
						is_fully_watched = True
					elif media_type == 'season':
						is_watched, is_fully_watched = self.watched.is_trakt_watched_season(services, source['info_labels'].get('season', 1), source.get('children_count', -1))
					elif media_type == 'tvshow':
						is_watched, is_fully_watched = self.watched.is_trakt_watched_serie(services, source.get('children_count', -1))
					else:
						is_watched = False

					if is_watched:
						# mark item as watched
						if is_fully_watched:
							title += ' ' + _B('*')
						else:
							title += ' *'

			trakt_item = self.fill_trakt_info(source, is_watched)

			if media_type in ('tvshow', 'season'):
				self.add_dir(title, img, info_labels=info_labels, menu=menu, trakt_item=trakt_item, cmd=self.get_data_by_parent, media_id=media['_id'], services=services, category=cat)
			elif media_type in ('movie', 'episode', 'concert'):
				if prehrajto_primary:
					self.add_dir(title, img, info_labels=info_labels, menu=menu, cmd=self.prehrajto_search, keyword=info_labels['search_keyword'])
				else:
					root_media_id = source.get('root_parent') if media_type == 'episode' else None
					self.add_video(title, img, info_labels=info_labels, menu=menu, trakt_item=trakt_item, cmd=self.get_streams, info=info_labels, media_id=media['_id'], category=cat, root_media_id=root_media_id, trakt_info=trakt_item)
			else:
				self.log_error("Unhandled media type: %s" % media_type)

	# ##################################################################################################################

	def get_data_by_parent(self, media_id, services=None, category=None):
		self.call_filter_api('parent', params={ 'sort': 'episode', 'value': media_id }, render_params={'services': services, 'category': category})

	# ##################################################################################################################

	def resolve_yt_trailer(self, video_title, video_id):
		youtube_params = {
			'url': video_id,
			'title': video_title
		}
		self.call_another_addon('plugin.video.yt', youtube_params, 'resolve')

	# ##################################################################################################################

	def play_trailer(self, media_id):
		media = self.api.call_filter_api('ids', params={'id': media_id }).get('hits', {}).get('hits',[{}])
		playlist = self.add_playlist('Trailers')

		for video in sorted(media[0].get('_source', {}).get('videos', []), key=lambda i: i.get('lang', '') in ('cs', 'sk'), reverse=True):
			if video.get('type', '').lower() != 'trailer':
				continue

			url = video.get('url')
			if not url:
				continue

			if not url.startswith('http'):
				url = "https://" + url.lstrip('./')

			lang = video.get('lang')
			title = video.get('name', '') or 'Trailer'

			if lang:
				title += ' ' + _I('(' + lang.upper() + ')')

			if 'youtube.com' in url  or 'youtu.be' in url:
				playlist.add_video(title, cmd=self.resolve_yt_trailer, video_title=title, video_id=url)
			else:
				subs = None
				for s in video.get('subtitles', []):
					subs = s.get('src')
					if s.get('language') in ('cs', 'sk'):
						title += ' (%s tit)' % s['language'].upper()
						break

				if subs and not subs.startswith('http'):
					subs = "https://" + subs.lstrip('./')

				playlist.add_play(title, url, subs=subs)

	# ##################################################################################################################

	def get_quality(self, video, with_3d=True, raw=False):
		quality_map = {144: '144p', 240: '240p', 360: '360p', 480: '480p', 720: '720p', 1080: '1080p', 2160: '4k', 4320: '8k'}

		def find_closest_resolution(height):
			keys = sorted(quality_map.keys())
			index = bisect(keys, height)
			if raw:
				return keys[index]
			else:
				return quality_map[keys[index]]

		height = int(video.get('height', 0))

		if raw:
			return height if height in quality_map else find_closest_resolution(height)

		quality = quality_map.get(height) or find_closest_resolution(height)
		if with_3d and video.get('3d', False):
			quality += ' 3D'
		return quality

	# ##################################################################################################################

	def convert_size(self, size_bytes):
		# convert to MB
		size = float(size_bytes) / 1024 / 1024

		if size > 1024:
			return "%.2f GB" % (size / 1024)
		else:
			return "%.2f MB" % size

	# ##################################################################################################################

	def filter_streams(self, streams):
		result = []
		max_file_size = self.get_setting('max-file-size') * 1024 * 1024 * 1024
		enable_hevc = self.get_setting('enable-hevc')
		enable_3d = self.get_setting('enable-3d')
		enable_hdr = self.get_setting('enable-hdr')
		min_quality = int(self.get_setting('min-quality'))
		max_quality = int(self.get_setting('max-quality'))
		item_lang_filter = self.get_setting('item-lang-filter')
		lang_filter = self.get_setting('stream-lang-filter')

		for strm in streams:
#			self.log_debug("Filtering stream [%s%s][%s][%s][%s]" % (strm.get('quality', '???'), strm.get('vinfo', '???'), strm.get('size', '???'), strm.get('lang', '???'), strm.get('ainfo', '???')[2:].replace('[', '').replace(']', '')))

			# stream size filter
			if max_file_size > 0:
				file_size = strm.get('size')
				if file_size and file_size > max_file_size:
					self.log_debug("Stream filtered due size %s" % strm.get('size', '???'))
					continue

			# hevc filter
			video = (strm.get('video') or [{}])[0]
			if not enable_hevc and video.get('codec') == 'HEVC':
				self.log_debug("Stream filtered due HEVC")
				continue

			if not enable_3d and video.get('3d', False):
				self.log_debug("Stream filtered due 3D")
				continue

			if not enable_hdr and video.get('hdr', False):
				self.log_debug("Stream filtered due HDR")
				continue

			quality = self.get_quality(video, raw=True)

			if quality < min_quality:
				self.log_debug("Stream filtered due min quality: %s < %s" % (quality, min_quality))
				continue

			if quality > max_quality:
				self.log_debug("Stream filtered due max quality: %s > %s" % (quality, max_quality))
				continue

			#lang filter
			# ALL|CZ or SK|CZ|SK|EN
			avail_langs = [l.get('language', '???') for l in strm.get('audio', [])]
			avail_subs = [l.get('language', '???') for l in strm.get('subtitles', [])]

			if lang_filter != 'all' and avail_langs:
				for l in lang_filter.split('+'):
					if l in avail_langs:
						break
				else:
					# configured lang not found in available languages

					# if show all items or show dubed or with subtitles is set, then check also if there are subtitles available
					if item_lang_filter == 'all' or item_lang_filter == 'dubsubs':
						# check if there are subtitles available
						for l in lang_filter.split('+'):
							if l in avail_subs:
								break
						else:
							self.log_debug("Stream filtered due lang 1")
							continue
					else:
						self.log_debug("Stream filtered due lang 2")
						continue

			# strm passed filtering
			result.append(strm)

		return result

	# ##################################################################################################################

	def sort_streams(self, streams):
		lang = self.get_lang_code()

		if lang == 'cs':
			k1 = 'cs'
			k2 = 'sk'
			k3 = 'en'
		elif lang == 'sk':
			k1 = 'sk'
			k2 = 'cs'
			k3 = 'en'
		else:
			k1 = 'en'
			k2 = 'cs'
			k3 = 'sk'

		def sort_fn(strm):
			video = (strm.get('video') or [{}])[0]
			height = video.get('height', 0)

			auds = { 'cs': 0, 'sk': 0, 'en': 0 }
			for audio in (strm.get('audio') or []):
				a = audio.get('language')
				if a in auds:
					auds[a] = 1

			subs = { 'cs': 0, 'sk': 0, 'en': 0 }
			for audio in (strm.get('subtitles') or []):
				s = audio.get('language')
				if s in subs:
					subs[s] = 1

			return '%d_%d_%d_%d_%d_%d_%04d_%012d' % (auds[k1], auds[k2], auds[k3], subs[k1], subs[k2], subs[k3], height, strm.get('size', 0))

		streams.sort(key=sort_fn, reverse=True)

	# ##################################################################################################################

	def get_streams(self, info, media_id, category=None, root_media_id=None, trakt_info=None):
		audios = { 1: '1.0', 2: '2.0', 6: '5.1', 8: '7.1'}
		data = self.api.call_streams_api(media_id)

		if not data:
			return

		streams_filtered = self.filter_streams(data)

		idx = None
		if len(streams_filtered) > 0:
			data = streams_filtered
			if len(data) == 1 or self.silent_mode:
				idx = 0
		else:
			# no stream passed filtering - let the user decide what now
			pass

		# sort streams by quality and language
		self.sort_streams(data)

		titles = []
		for strm in data:
			video = strm.get('video', [{}])[0]

			auds = []
			for audio in strm.get('audio', []):
				if 'language' in audio:
					if audio['language'] == "":
						auds.append(audio.get('codec', '') + " " + audios.get(audio.get('channels', 2), "") + " ??")
					else:
						auds.append(audio.get('codec', '') + " " + audios.get(audio.get('channels', 2), "") + " " + _I(audio['language']))

			auds = sorted(set(auds))

			subs = []
			for sub in strm.get('subtitles', []):
				if 'language' in sub and sub['language'] != "":
					subs.append(_I(sub['language']))

			subs = sorted(set(subs))

			title = "[%s %s][%s][%s]" % (_I(self.get_quality(video)), video.get('codec'), self.convert_size(strm.get('size', 0)), (', '.join(auds)).upper())
			if len(subs) > 0:
				title += '[tit. %s]' % (', '.join(subs)).upper()
			titles.append(title)

		if idx == None:
			idx = self.get_list_input(titles, '')
			if idx == -1:
				return

		ident = data[idx].get('ident')
		file_name = data[idx].get('name')
		duration = int(data[idx].get('video', [{}])[0].get('duration', 0))

		if not ident:
			return

		media_title = info.get('epname') or info['title']
		info_labels = { 'title': media_title, 'filename': info['filename'] }

		data_item = { 'category': category, 'id': media_id, 'root_id': root_media_id }
		settings = {}

		last_position = self.watched.get_last_position(media_id)

		if self.silent_mode == False and self.get_setting('save-last-play-pos') and last_position > 0 and (not duration or last_position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100):
			settings['resume_time_sec'] = last_position

		settings['lang_priority'] = self.get_dubbed_lang_list()
		if 'en' not in settings['lang_priority']:
			settings['lang_fallback'] = ['en']

		settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')

		play_params = { 'info_labels': info_labels, 'trakt_item': trakt_info, 'data_item': data_item, 'settings': settings}

		playlist = self.add_playlist(media_title, variant=True)
		try:
			playlist.add_play(titles[idx], self.webshare.resolve(ident, file_name), **play_params)
		except (WebshareLoginFail, ResolveException, WebshareApiError) as e:
			self.show_error(str(e))

		for i in range(len(data)):
			if i != idx:
				playlist.add_video(titles[i], cmd=self.webshare_resolve, ident=data[i].get('ident'), file_name=data[i].get('name'), media_title=media_title, play_params=play_params, **play_params)

	# ##################################################################################################################

	def webshare_resolve(self, media_title, ident, file_name, settings, play_params={}):
		try:
			self.add_play(media_title, self.webshare.resolve(ident, file_name), **play_params)
		except (WebshareLoginFail, ResolveException, WebshareApiError) as e:
			self.show_error(str(e))

	# ##################################################################################################################

	def prehrajto_search(self, keyword):
		self.call_another_addon('plugin.video.prehrajto', keyword)

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		if search_id is not None and search_id.endswith('-all'):
			search_id = search_id.replace('-all', '-*')

		params = {
			'type': search_id or '*',
			'sort': 'score',
			'order': 'desc',
			'value': keyword
		}

		render_params = {
			'category': search_id or '-all',
		}

		self.call_filter_api('search', params, render_params)

	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		self.log_info("Stats command called: %s" % action)
		if data_item:
			category = data_item.get('category')
			media_id = data_item.get('id')
			root_media_id = data_item.get('root_id')
		else:
			category = None
			media_id = None
			root_media_id = None

		self.log_info("Category: %s, media_id: %s, duration: %s, position: %s" % (category, media_id, duration, position))

		try:
			if action == 'play':
				if category and (media_id or root_media_id):
					self.watched.set(category, root_media_id or media_id)

			elif action == 'end':
				if media_id and position and self.get_setting('save-last-play-pos'):
					if not duration or position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100:
						self.watched.set_last_position(media_id, position)
					else:
						# remove saved position from database
						self.watched.set_last_position(media_id, None)

				self.watched.save()

		except:
			self.log_error("Stats processing failed")
			self.log_exception()

	# ##################################################################################################################

	def trakt(self, trakt_item, action, result):
		if self.get_setting('trakt_enabled'):
			self.log_debug("Trakt action=%s, result=%s" % (action, result))
#			self.log_debug("Trakt item=%s" % trakt_item)

			if action == 'watched':
				self.watched.trakt_need_reload = True
			elif action == 'unwatched':
				self.watched.trakt_need_reload = True
			elif action == 'scrobble':
				self.watched.trakt_need_reload = True
			elif action == 'reload':
				self.watched.force_reload()

	# ##################################################################################################################
