# -*- coding: utf-8 -*-
try:
	from Plugins.Extensions.archivCZSK.engine.trakttv import trakttv
except:
	trakttv = None

from datetime import date
import json
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from tools_archivczsk.cache import lru_cache

from .kraska import Kraska, KraskaLoginFail, KraskaResolveException
from .sc_api import SC_API
from .watched import SCWatched
from .prehrajto import PrehrajTo

######################

try:
	from urlparse import urlparse, urlunparse, parse_qsl
	from urllib import quote, urlencode
except:
	from urllib.parse import quote, urlparse, urlunparse, urlencode, parse_qsl

# #################################################################################################

# fake translation func - needed for gettext to properly extract texts needed for translation
def _(s):
	return s


# #################################################################################################
# disabled, because images doesn't look very good on enigma2 skins
_KODI_IMG_MAP = {
#	'defaultmovies.png': 'DefaultMovies.png',
#	'defaulttvshows.png': 'DefaultTVShows.png',
#	'defaultmusicvideos.png': 'DefaultMusicVideos.png',
#	'defaultaddonpvrclient.png': 'DefaultAddonPVRClient.png',
}

_KODI_IMG_URL = 'https://github.com/xbmc/skin.confluence/raw/master/media/'
#_KODI_IMG_URL = 'https://github.com/xbmc/repo-skins/raw/matrix/skin.tetradui/media/'

# these methods are supported by SC
_KODI_SORT_METHODS = {
	39: (None, _("Default")),
	19: ('rating', _("Rating")), # works ok
	30: ('mpaa', _("MPAA Rating")), # No idea if it works ok
	36: ('title', _("Title")), # wtf???
	26: ('name', _("Name")), # results are funny ...
	18: ('year', _("Year")), # works ok
	21: ('datum', _("Date added")), # works ok?
}

# #################################################################################################

class StreamCinemaContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'stream-cinema', settings=settings, data_dir=data_dir)
		self.login_optional_settings_names = ('kruser', 'krpass', 'ptouser', 'ptopass')
		self.tapi = trakttv

		if not self.get_setting('deviceid'):
			self.set_setting('deviceid', SC_API.create_device_id())

		self.watched = SCWatched(self.data_dir, trakttv, int(self.get_setting('keep-last-seen')))

		self.api = SC_API(self)
		self.kraska = Kraska(self)
		self.prehrajto = PrehrajTo(self)

	# ##################################################################################################################

	def kraska_update_vipdays(self):
		try:
			days_left = self.kraska.refresh_login_data()
			if days_left == None:
				days_left = -1
		except:
			days_left = -2

		# update remaining vip days
		if self.get_setting('krvipdays') != str(days_left):
			self.set_setting('krvipdays', str(days_left))

		return days_left

	# ##################################################################################################################

	def login(self, silent):
		self.build_lang_lists()
		self.kraska_update_vipdays()
		self.prehrajto.login()

		if self.kraska_update_vipdays() <= 0:
			# no username/password provided or vip expired - continue with free account
			if self.get_setting('kruser') and self.get_setting('krpass'):
				self.log_info("Kraska subscription account expired")

				if not silent:
					self.show_info(self._("Subscription for kra.sk expired"), noexit=True)
				else:
					# return False, so we can show message about expired account to user when no silent flag will be set
					return False
			else:
				self.log_info("No kraska username or password provided")

				if not silent:
					self.show_info(self._("No kra.sk username and password provided"), noexit=True)
				else:
					return False

		return True

	# ##################################################################################################################

	def root(self):
		self.build_lang_lists()
		self.kraska_update_vipdays()

		return self.render_menu('/')

	# #################################################################################################

	def build_lang_lists(self):
		self.dubbed_lang_list = self.get_dubbed_lang_list()
		self.lang_list = self.dubbed_lang_list[:]
		if 'en' not in self.lang_list:
			self.lang_list.append('en')

	# #################################################################################################

	def fill_trakt_info(self, menu_item, is_watched=None ):
		if not self.get_setting('trakt_enabled') or 'unique_ids' not in menu_item:
			return None

		mediatype = menu_item.get('info',{}).get('mediatype')

		if mediatype == None:
			return None

		if mediatype == 'movie':
			trakt_type = 'movie'
		else:
			trakt_type = 'show'

		trakt_items = {
			'watched': is_watched,
			'type': trakt_type,
			'ids' : menu_item['unique_ids'],
			'episode' : menu_item['info'].get('episode') if mediatype == 'episode' else None,
			'season': menu_item['info'].get('season') if mediatype in ('episode', 'season') else None,
		}

		return { k: v for k, v in trakt_items.items() if v is not None }

	# #################################################################################################

	def play_trailer(self, media_title, url):
		if not url.startswith('http'):
			url = "https://" + url.lstrip('./')

		if 'youtube.com' in url  or 'youtu.be' in url:
			video_formats = self.youtube_resolve(url)
			if video_formats and len(video_formats) > 0:
				video_url = video_formats[-1].get('url')
				if video_url:
					self.add_play(media_title, video_url)
		else:
			self.add_play(media_title, url)

	# #################################################################################################

	def render_menu(self, url, params=None, data=None):
		result = []

		resp = self.api.call_api(url, data=data, params=params)

		for menu_item in resp.get('menu', []):
			ctx_menu = self.create_ctx_menu()
			data_item = {}
			trakt_item = None

			trailer = menu_item.get('info', {}).get('trailer')
			if trailer:
				ctx_menu.add_media_menu_item(self._('Play trailer'), cmd=self.play_trailer, media_title="Trailer", url=trailer)

			if '/latest' not in url:
				self.add_filter_ctx_menu(ctx_menu, url, resp.get('filter'), resp.get('system', {}).get('addSortMethods'), params=params, data=data)

			is_watched = False
			is_fully_watched = False
			lid = None
			mid = None
			if 'unique_ids' in menu_item:
				lid = menu_item.get('lid')
				mid = menu_item['unique_ids'].get('sc')
				data_item.update({ 'url': menu_item['url'], 'lid': lid, 'mid': mid })

				if self.get_setting('trakt_enabled'):
					# check if this item is watched
					if menu_item['type'] == 'video':
						if 'episode' in menu_item.get('info', {}):
							is_watched = self.watched.is_trakt_watched_show(menu_item['unique_ids'], menu_item['info'].get('season', 1), menu_item['info'].get('episode'))
						else:
							is_watched = self.watched.is_trakt_watched_movie(menu_item['unique_ids'])

					elif menu_item['type'] == 'dir':
						# if there is a season dir or the show has no seasons, then check if we watched all episodes
						if menu_item['info'].get('mediatype', '') == 'season':
							is_watched, is_fully_watched = self.watched.is_trakt_watched_season(menu_item['unique_ids'], menu_item['info'].get('season', 1), menu_item['info'].get('episode', -1))
						else:
							is_watched, is_fully_watched = self.watched.is_trakt_watched_serie(menu_item['unique_ids'], menu_item['info'].get('season', -1))

					# this is needed for trakt
					trakt_item = self.fill_trakt_info(menu_item, is_watched)

			if '/Last' in url and lid and mid:
				ctx_menu.add_menu_item(self._('Remove from seen'), cmd=self.remove_last_seen, lid=lid, mid=mid)

			if menu_item['type'] == 'dir':
				self.add_sc_dir_item(menu_item, ctx_menu, data_item, trakt_item, (is_watched, is_fully_watched,))
			elif menu_item['type'] == 'next':
				self.add_next(cmd=self.render_menu, url=menu_item.get('url'))
			elif menu_item['type'] == 'video':
				self.add_sc_video_item(menu_item, ctx_menu, data_item, trakt_item, is_watched)
			elif menu_item['type'] == 'action':
				if menu_item['action'] == 'csearch':
					self.add_sc_search_item(menu_item)
				elif menu_item['action'] == 'last':
					self.add_sc_last_seen_dir(menu_item)
				elif menu_item['action'] == 'trakt.list':
					if self.tapi and self.tapi.valid():
						self.add_sc_trakt_dir()
				else:
					self.log_info("UNHANDLED ACTION: %s" % menu_item['action'])
			else:
				self.log_info("UNHANDLED ITEM TYPE: %s" % menu_item['type'])

		return result

	# #################################################################################################

	def search(self, keyword, search_id):
		query = {
			'search': keyword,
			'id': search_id
		}
		if search_id.startswith('search-people'):
			query['ms'] = '1'

		return self.render_menu('/Search/' + search_id, params=query)

	# #################################################################################################

	def get_i18n_list(self, i18n_base, lang_list=None ):
		if isinstance(i18n_base, (type(u''), type(''),)):
			# hack to solve bad data returned for movies, when i18n_base is not dictionary but directly title name
			return { 'title': i18n_base }

		if lang_list == None:
			lang_list = self.lang_list

		if isinstance(i18n_base, type({})):
			for l in lang_list:
				if l in i18n_base:
					return i18n_base[l]

		return None

	# #################################################################################################

	def is_adult(self, sc_item):
		info = self.get_i18n_list( sc_item.get('i18n_info', {}), ['en'] )
		if not info:
			return False

		for g in info.get('genre', []):
			if g.lower() in ('erotic', 'adult', 'pornographic', 'porn'):
				return True

		return False

	# #################################################################################################

	def show_trakt_list(self, user, list_id):
		@lru_cache(30, timeout=1800)
		def get_list_items(list_id, user):
			return self.tapi.get_list_items(list_id, user)

		track_ids = []
		# get list from Trakt.tv and extract trakt ID + type
		for titem in get_list_items(list_id, user):
			titem_type = titem.get('type')

			if titem_type not in ['movie', 'tvshow', 'show']:
				continue

			sc_type = 1 if titem_type == 'movie' else 3
			data = titem.get(titem_type, {})
			tr = data.get('ids', {}).get('trakt')
			track_ids.append("{},{}".format(sc_type, tr))

		if len(track_ids) > 0:
			self.render_menu('/Search/getTrakt', data={ 'ids': json.dumps(track_ids)})

	# #################################################################################################

	def show_trakt_history(self, media_type):
		@lru_cache(30, timeout=1800)
		def get_list_items(media_type):
			if media_type == 'movie':
				return self.tapi.get_watched_movies()
			else:
				return self.tapi.get_watched_shows()

		track_ids = []
		sc_type = 1 if media_type == 'movie' else 3
		# get list from Trakt.tv and extract trakt ID + type
		for data in get_list_items(media_type):
			track_ids.append("{},{}".format(sc_type, str(data['trakt'])))

		if len(track_ids) > 0:
			self.render_menu('/Search/getTrakt', data={ 'ids': json.dumps(track_ids)})

	# ##################################################################################################################

	def add_sc_trakt_dir(self, dir_type=None, page=0):
		if not self.get_setting('trakt_enabled'):
			return

		if dir_type == None:
			self.add_dir(self._("Trakt.tv"), cmd=self.add_sc_trakt_dir, dir_type='root')
		elif dir_type == 'root':
			self.add_dir(self._("My lists"), cmd=self.add_sc_trakt_dir, dir_type='my_lists')
			self.add_dir(self._("History"), cmd=self.add_sc_trakt_dir, dir_type='history')
			self.add_dir(self._("Trending"), cmd=self.add_sc_trakt_dir, dir_type='trending')
			self.add_dir(self._("Popular"), cmd=self.add_sc_trakt_dir, dir_type='popular')
		elif dir_type == 'history':
			self.add_dir(self._("Movies"), cmd=self.add_sc_trakt_dir, dir_type='history_movies')
			self.add_dir(self._("Series"), cmd=self.add_sc_trakt_dir, dir_type='history_shows')
		elif dir_type == 'history_movies':
			self.show_trakt_history('movie')
		elif dir_type == 'history_shows':
			self.show_trakt_history('tvshow')
		elif dir_type == 'my_lists':
			for titem in self.tapi.get_lists():
				self.add_dir(titem['name'], info_labels={'plot': titem.get('description')}, cmd=self.show_trakt_list, user='me', list_id=titem['id'])
		elif dir_type in ('trending', 'popular'):
			for titem in self.tapi.get_global_lists(dir_type, page):
				if titem['id'] and titem['user']:
					self.add_dir(titem['name'], info_labels={'plot': titem.get('description')}, cmd=self.show_trakt_list, user=titem['user'], list_id=titem['id'])
			self.add_next(cmd=self.add_sc_trakt_dir, page_info=(page + 2), dir_type=dir_type, page=page + 1)

	# #################################################################################################

	def add_sc_dir_item(self, sc_item, ctx_menu, data_item, trakt_item, is_watched):
		url = sc_item.get('url')

		visible = sc_item.get('visible', '')
		if visible.startswith('sc://config(stream.dubed') and self.get_setting('item-lang-filter') == 'dub':
			# do not show this item, if only dubed movies are allowed
			self.log_debug("No visible for %s" % str(sc_item))
			return

		if not url:
			self.log_debug("No url for %s" % str(sc_item))
			return

#		if url == '/huste': #hack to not show Huste TV dir
#			return None

		info_labels = {}

		title = sc_item.get('title')
		otitle = title

		info_labels['adult'] = self.is_adult(sc_item)
		if self.get_setting('enable-adult') == False and info_labels['adult']:
			return

		info = self.get_i18n_list( sc_item.get('i18n_info', {}) )

		if info:
			title = info.get('title')
			otitle = info.get('otitle') or title
			genre = ' / '.join(info.get('genre', []))
			if len(genre) > 0:
				genre = '[' + genre + ']\n'
				info_labels['plot'] = genre + info.get('plot')
				info_labels['genre'] = ', '.join(info.get('genre', []))
			else:
				info_labels['plot'] = info.get('plot')

		if not title: # hack to skip recursive items in Documentary section
			self.log_debug("No title for %s" % str(sc_item))
			return

		if is_watched[0]:
			if is_watched[1]:
				title += _B(' *')
			else:
				title += ' *'

		info = self.get_i18n_list( sc_item.get('i18n_art', {}) )
		if info:
			img = self.get_poster_url(info.get('poster'))
		else:
			img = sc_item.get('art', {}).get('icon')

		if img:
			if not img.startswith('http'):
				if img in _KODI_IMG_MAP:
					img = _KODI_IMG_URL + _KODI_IMG_MAP[ img ]
				else:
					img = None

		info = sc_item.get('info', {})
		info_labels['year'] = info.get('year')
		info_labels['title'] = otitle
		info_labels['duration'] = int(info.get('duration', 0))
		info_labels['rating'] = info.get('rating')

		if info.get('mediatype') == 'episode':
			info_labels['episode'] = info.get('episode', 0)
			info_labels['epname'] = info.get('epname')

			if 'season' in info:
				info_labels['season'] = info['season']
				ep_code = ' %s (%d)' % (int_to_roman(info['season']), int(info.get('episode', 0)))
				ep_code2 = ' S%02dE%02d' % (int(info['season']), int(info.get('episode', 0)))
			else:
				ep_code = ' (%d)' % int(info.get('episode', 0))
				ep_code2 = ' E%02d' % int(info.get('episode', 0))

			info_labels['title'] += ep_code

			search_query = otitle + ep_code2
			ctx_menu.add_menu_item(self._('Search on prehraj.to'), cmd=self.prehrajto_search, keyword=search_query)
		elif info.get('mediatype') == 'season':
			info_labels['season'] = info.get('season', 0)
			ep_code = ' %s' % int_to_roman(info.get('season', 0))
			ep_code2 = ' S%02d' % int(info.get('season', 0))
			info_labels['title'] += ep_code

			search_query = otitle + ep_code2
			ctx_menu.add_menu_item(self._('Search on prehraj.to'), cmd=self.prehrajto_search, keyword=search_query)
		else:
			if info_labels['year']:
				info_labels['title'] += ' (%s)' % info_labels['year']

			if info.get('mediatype') == 'tvshow':
				ctx_menu.add_menu_item(self._('Search on prehraj.to'), cmd=self.prehrajto_search, keyword=otitle)

		self.add_dir(title, img or self.get_poster_url(None), info_labels, menu=ctx_menu, data_item=data_item, trakt_item=trakt_item, cmd=self.render_menu, url=url)

	# #################################################################################################

	def add_sc_video_item(self, sc_item, ctx_menu, data_item, trakt_item, is_watched):
		url = sc_item['url']

		info_labels = {}

		info = self.get_i18n_list( sc_item.get('i18n_info') )
		epname = info.get('epname')
		genre = ' / '.join( info.get('genre', []))
		if len(genre) > 0:
			genre = '[' + genre + ']\n'

		title = info.get('title', "???").replace('[LIGHT]', '').replace('[/LIGHT]', '')
		otitle = info.get('otitle') or title

		if is_watched:
			title += _B(' *')

		info_labels['plot'] = genre + info.get('plot', '')
		info_labels['genre'] = ', '.join(info.get('genre', []))
#		sorttitle = info.get('sorttitle','')

		info = self.get_i18n_list( sc_item.get('i18n_art') )
		img = self.get_poster_url(info.get('poster'))

		info_labels['adult'] = self.is_adult(sc_item)
		if self.get_setting('enable-adult') == False and info_labels['adult']:
			return

		info = sc_item.get('info',{})
		info_labels['year'] = info.get('year')
		info_labels['title'] = otitle
		info_labels['duration'] = int(info.get('duration', 0))
		info_labels['rating'] = info.get('rating')

		ep_code2 = ''

		if info.get('mediatype') == 'episode':
			info_labels['episode'] = info['episode']
			info_labels['epname'] = epname

			if 'season' in info:
				info_labels['season'] = info['season']
				ep_code = ' %s (%d)' % (int_to_roman(info['season']), info['episode'])
				ep_code2 = ' S%02dE%02d' % (int(info['season']), int(info['episode']))
			else:
				ep_code = ' (%d)' % info['episode']
				ep_code2 = ' E%02d' % int(info['episode'])

			info_labels['title'] += ep_code
			info_labels['filename'] = otitle + ep_code2
			if epname:
				info_labels['filename'] += ': %s' % epname
		else:
			if info_labels['year']:
				info_labels['title'] += ' (%s)' % info_labels['year']

		search_query = otitle + ep_code2 + ' ' + str(info.get('year', ""))

		if self.get_setting('prehrajto-primary'):
			self.add_dir(title, img, info_labels, menu=ctx_menu, data_item=data_item, trakt_item=trakt_item, cmd=self.prehrajto_search, keyword=search_query)
		else:
			ctx_menu.add_menu_item(self._('Search on prehraj.to'), cmd=self.prehrajto_search, keyword=search_query)
			self.add_video(title, img, info_labels, menu=ctx_menu, data_item=data_item, trakt_item=trakt_item, cmd=self.resolve_video_streams, url=url, info=info_labels)

	# #################################################################################################

	def add_sc_search_item(self, sc_item):
		info = self.get_i18n_list( sc_item.get('i18n_info') )

		self.add_search_dir(info.get('title'), sc_item.get('id'), img=sc_item.get('art', {}).get('icon'))

	# #################################################################################################

	def add_sc_last_seen_dir(self, sc_item):
		lid = sc_item.get('id')

		# if there are no items in history, then do not show this dir
		if len(self.watched.get(lid)) == 0:
			return

		info = self.get_i18n_list( sc_item.get('i18n_info') )
		self.add_dir(info.get('title'), sc_item.get('art', {}).get('icon'), cmd=self.render_menu, url='/Last', data={ 'ids': json.dumps(self.watched.get(lid)) })

	# #################################################################################################

	def remove_last_seen(self, lid, mid):
		self.watched.remove(lid, mid)
		self.watched.save()
		self.refresh_screen()

	# #################################################################################################

	def prehrajto_search(self, keyword):
		for item in self.prehrajto.search(keyword):
			self.add_video(item['title'] + _I(' [' + item['size'] + ']'), item['img'], cmd=self.prehrajto_resolve, video_title=item['title'], video_id=item['id'])

	# #################################################################################################

	def prehrajto_resolve(self, video_title, video_id):
		video_url, subs_url = self.prehrajto.resolve_video(video_id)
		if video_url:
			self.add_play(video_title, video_url, subs=subs_url)

	# #################################################################################################

	def update_url_filter(self, url, key, value ):
		u = urlparse( url )
		q = dict(parse_qsl( u.query ))
		if value:
			q.update( { key: value } )
		elif value in q:
			del q[value]

		res = urlunparse( ('', '', u.path, '', urlencode(q), '') )
		return res

	# #################################################################################################

	def add_filter_ctx_menu(self, ctx_menu, url, filter_data, sort_methods, params, data):
		if not filter_data:
			# nothing to filter
			return

		od = filter_data.get('od', '')
		if od == 'asc':
			url2 = self.update_url_filter( url, 'od', 'desc')
			ctx_menu.add_menu_item(self._("Order descending (Z-A)"), cmd=self.render_menu, url=url2, params=params, data=data)
		elif od == "desc":
			url2 = self.update_url_filter( url, 'od', 'asc')
			ctx_menu.add_menu_item(self._("Order ascending (A-Z)"), cmd=self.render_menu, url=url2, params=params, data=data)

		if sort_methods and 0 not in sort_methods:
			ctx_menu.add_menu_item(self._("Sort"), cmd=self.set_sort, url=url, sort_methods=sort_methods, params=params, data=data)

		if od != '':
			ctx_menu.add_menu_item(self._("Filter by year"), cmd=self.filter_by_year, url=url, params=params, data=data)

	# #################################################################################################

	def set_sort(self, url, sort_methods, params, data):
		lang_code = self.dubbed_lang_list[0]

		sm_url = []
		titles = []
		for m in sort_methods:
			m = int(m)
			if m in _KODI_SORT_METHODS:
				sm = _KODI_SORT_METHODS[m]
				mn = sm[0]
				if m == 26:
					mn += '_%s' % lang_code

				sm_url.append(self.update_url_filter(url, 'of', mn))
				titles.append(self._(sm[1]))
			else:
				self.log_info("UNHANDLED SORT METHOD: %d" % m)

		sm_url.append(self.update_url_filter(url, 'of', 'random'))
		titles.append(self._("Random"))

		idx = self.get_list_input(titles, self._('Sort by'))
		if idx == -1:
			self.refresh_screen()
		else:
			self.render_menu(sm_url[idx], params=params, data=data)

	# #################################################################################################

	def filter_by_year(self, url, params, data):
		idx = self.get_list_input([self._("Older than"), self._("Younger than"), self._("Exact in year")], self._('Choose by year'))
		if idx != -1:
			cur_year = date.today().year
			idx2 = self.get_list_input([str(x) for x in range(cur_year, 1949, -1) ], self._('Choose by year'))
			if idx2 != -1:
				year = str(cur_year - idx2)
				url = self.update_url_filter(url, 'y', [ '<', '>', ''][idx] + year)

			self.render_menu(url, params=params, data=data)
		else:
			self.refresh_screen()

	# #################################################################################################

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

	# #################################################################################################

	def get_poster_url(self, url):
		if not url:
			return 'https://stream-cinema.online/images/poster_300x200.jpg'

		if 'image.tmdb.org' in url:
			return url.replace('original', 'w400')
		elif 'img.csfd.cz' in url:
			return url + '?h480'
		elif 'stream-cinema.online/images/poster_1000x680.jpg' in url:
			return url.replace('1000x680', '300x200')
		return url

	# #################################################################################################

	def parse_hr_size( self, size ):
		units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40}

		try:
			number, unit = [string.strip() for string in size.split()]
			return int(float(number.replace(',','')) * units[unit])
		except:
			return None

	# #################################################################################################

	def filter_streams(self, streams ):
		result = []
		max_file_size = int(self.get_setting('max-file-size')) * (2 ** 30)
		enable_hevc = self.get_setting('enable-hevc')
		enable_hdr = self.get_setting('show-hdr')
		enable_dv = self.get_setting('show-dv')
		enable_3d = self.get_setting('show-3d')
		min_quality = int(self.get_setting('min-quality'))
		max_quality = int(self.get_setting('max-quality'))
		item_lang_filter = self.get_setting('item-lang-filter')
		lang_filter = self.get_setting('stream-lang-filter')

		for strm in streams:
			self.log_debug("Filtering stream [%s%s][%s][%s][%s]" % (strm.get('quality', '???'), strm.get('vinfo', '???'), strm.get('size', '???'), strm.get('lang', '???'), strm.get('ainfo', '???')[2:].replace('[', '').replace(']', '')))

			if strm['provider'] != 'kraska':
				self.log_error("Unsupported stream provider: %s" % strm['provider'])
				continue

			# stream size filter
			if max_file_size > 0:
				file_size = self.parse_hr_size(strm.get('size', '0 B'))
				if file_size and file_size > max_file_size:
					self.log_debug("Stream filtered due size %s" % strm.get('size', '???'))
					continue

			# hevc filter
			if not enable_hevc and strm.get('stream_info', {}).get('HEVC', 0) == 1:
				self.log_debug("Stream filtered due HEVC")
				continue

			# hdr filter
			if not enable_hdr and strm.get('stream_info', {}).get('HDR', 0) == 1:
				self.log_debug("Stream filtered due HDR")
				continue

			# dolby vision filter
			if not enable_dv and strm.get('stream_info', {}).get('DV', 0) == 1:
				self.log_debug("Stream filtered due dolby vision")
				continue

			strm_quality = strm.get('quality','').lower()
			if strm_quality:
				# 3D filter
				if not enable_3d and strm_quality.startswith('3d-'):
					self.log_debug("Stream filtered due 3D")
					continue

				try:
					# convert string representing stream quality (720p, 1080i, 4k, ...) to vertical resolution
					if strm_quality.endswith('p') or strm_quality.endswith('i'):
						strm_quality = int(strm_quality[:-1])
					elif strm_quality.endswith('k'):
						strm_quality = int(strm_quality[:-1]) * 540
					elif strm_quality.startswith('3d-'):
						# 3D movie, but we have no quality info - assuming 1080p
						strm_quality = 1080
					elif strm_quality == 'sd':
						strm_quality = 640
					else:
						raise Exception('Unsupported stream quality format: "%s"' % strm_quality)
				except:
					self.log_exception()
					# SD quality
					strm_quality = 640

				# min quality filter: Všetko|720p|1080p|4k
				if strm_quality < min_quality:
					self.log_debug("Stream filtered due min quality (%d < %d)" % (strm_quality, min_quality))
					continue


				# max quality filter: 720p|1080p|4k|8k
				if strm_quality > max_quality:
					self.log_debug("Stream filtered due max quality (%d > %d)" % (strm_quality, max_quality))
					continue

			#lang filter
			# ALL|CZ or SK|CZ|SK|EN
			avail_langs = strm.get('stream_info',{}).get('langs')

			if lang_filter != 'all' and avail_langs:
				if lang_filter == 'cs+sk': # CZ or SK
					ll = [ 'CZ', 'SK']
				elif lang_filter == 'cs': # CZ
					ll = [ 'CZ' ]
				elif lang_filter == 'sk': # SK
					ll = [ 'SK' ]
				elif lang_filter == 'en': # EN
					ll = [ 'EN', 'EN+tit']
				else:
					ll = []

				for l in ll:
					if l in avail_langs:
						break
				else:
					# configured lang not found in available languages

					# if show all items or show dubed or with subtitles is set, then check also if there are subtitles available
					if item_lang_filter == 'all' or item_lang_filter == 'dubsubs':
						# check if there are subtitles available
						for a in avail_langs:
							if '+tit' in a:
								break
						else:
							self.log_debug("Stream filtered due lang 1")
							continue
					else:
						self.log_debug("Stream filtered due lang 2")
						continue

			self.log_debug("Stream added")
			# strm passed filtering
			result.append(strm)

		return result

	# #################################################################################################

	def resolve_video_streams(self, url, info):
		# get info about files from stream cinema
		result = self.api.call_api(url)

		streams = result.get('strms')
		if not streams:
			return

		streams_filtered = self.filter_streams( streams )
		idx = None
		if len( streams_filtered ) > 0:
			streams = streams_filtered
			if len(streams) == 1 or self.silent_mode:
				idx = 0
		else:
			# no stream passed filtering - let the user decide what now
			pass

		titles = []
		for strm in streams:
			title = "[%s%s][%s][%s][%s]" % (_I(strm['quality']), strm['vinfo'], strm['size'], _I(strm['lang']), strm['ainfo'][2:].replace('[', '').replace(']', ''))
			titles.append( title )

		if idx == None:
			idx = self.get_list_input(titles, self._('Please select a stream'))
			if idx == -1:
				return

		stream = streams[idx]
		ident = self.api.call_api(stream['url']).get('ident')

		subs_url = stream.get('subs')

		if subs_url and subs_url.startswith('https://kra.sk/file/'):
			subs_url = subs_url[20:]

			try:
				subs_url = self.kraska.resolve(subs_url)
				self.log_info("RESOLVED SUBS: %s" % subs_url)
			except:
				# ignore problems with subtitles
				subs_url = None
				pass

		info_item = result.get('info', {})
		duration = info_item.get('info', {}).get('duration')

		media_title = info.get('epname') or info['title']
		info_labels = { 'title': media_title, 'filename': info.get('filename') }
		data_item = { 'url': info_item['url'], 'lid': info_item.get('lid'), 'mid': info_item.get('unique_ids', {}).get('sc') }
		settings = {}

		last_position = self.watched.get_last_position(info_item['url'])

		if self.silent_mode == False and self.get_setting('save-last-play-pos') and last_position > 0 and (not duration or last_position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100):
			settings['resume_time_sec'] = last_position

		settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in settings['lang_priority']:
			settings['lang_fallback'] = ['en']

		settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')
		settings['skip_times'] = self.create_skip_times(stream)

		trakt_info = self.fill_trakt_info(info_item)

		play_params = { 'info_labels': info_labels, 'trakt_item': trakt_info, 'data_item': data_item, 'settings': settings}

		playlist = self.add_playlist(media_title, variant=True)
		try:
			playlist.add_play(titles[idx], self.kraska.resolve(ident), subs=subs_url, **play_params)
		except (KraskaLoginFail, KraskaResolveException) as e:
			self.show_error(str(e))

		for i in range(len(streams)):
			if i != idx:
				playlist.add_video(titles[i], cmd=self.kraska_resolve, url=streams[i].get('url'), subs_url=streams[i].get('subs'), skip_times=self.create_skip_times(streams[i]), media_title=media_title, play_params=play_params, **play_params)

	# #################################################################################################

	def create_skip_times(self, stream):
		skip_times = []
		notifications = stream.get('notifications')

		if notifications:
			skip_start = int(notifications.get('skip_start', 0))
			skip_end = int(notifications.get('skip_end', 0))
			skip_end_titles = int(notifications.get('skip_end_titles', 0))

			if skip_end:
				self.log_debug("Adding skip times: (%d:%d)" % (skip_start, skip_end))
				skip_times.append((skip_start, skip_end,))

			if skip_end_titles:
				self.log_debug("Adding skip_end_titles: %d" % skip_end_titles)

				if len(skip_times) == 0:
					# add dummy intro skip times
					skip_times.append((-1, -1,))

				skip_times.append((skip_end_titles, 0,))

		return skip_times if len(skip_times) > 0 else None

	# #################################################################################################

	def kraska_resolve(self, media_title, url, subs_url, skip_times, settings, play_params={}):
		if subs_url and subs_url.startswith('https://kra.sk/file/'):
			subs_url = subs_url[20:]

			try:
				subs_url = self.kraska.resolve(subs_url)
				self.log_info("RESOLVED SUBS: %s" % subs_url)
			except:
				# ignore problems with subtitles
				subs_url = None
				pass

		try:
			ident = self.api.call_api(url).get('ident')
			play_params['settings'] = play_params['settings'].copy()
			play_params['settings']['skip_times'] = skip_times
			self.add_play(media_title, self.kraska.resolve(ident), subs=subs_url, **play_params)
		except (KraskaLoginFail, KraskaResolveException) as e:
			self.show_error(str(e))

	# #################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if data_item:
			url = data_item.get('url')
			lid = data_item.get('lid')
			mid = data_item.get('mid')
		else:
			url = None
			lid = None
			mid = None

		try:
			if action.lower() == 'play':
				if lid and mid:
					self.watched.set( lid, mid )

			elif action.lower() == 'watching':
				pass

			elif action.lower() == 'end':
				if url and position and self.get_setting('save-last-play-pos'):
					if not duration or position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100:
						self.watched.set_last_position(url, position)
					else:
						# remove saved position from database
						self.watched.set_last_position( url, None )

				self.watched.save()

		except:
			self.log_error("Stats processing failed")
			self.log_exception()

	# #################################################################################################

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

	# #################################################################################################
