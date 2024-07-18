# -*- coding: utf-8 -*-
import os
from datetime import date, datetime, timedelta
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException, AddonSilentExitException
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman

from .sosac import Sosac

######################

# fake translation func - needed for gettext to properly extract texts needed for translation
def _(s):
	return s

# #################################################################################################

LETTER_LIST = ['0-9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

QUALITY_LIST = [
	("", _("All"),),
	("fhd", 'Full HD (1080p)',),
	("uhd", 'Ultra HD (4k)',),
	("hd", 'HD (720p)',),
	("sd", 'SD (<720p)',),
	("kinorip", 'Kinorip',),
	("tvrip", "TV Rip",),
]

GENRE_LIST = [
	# (id, name, adult)
	("", _("All"), False,),
	("action", _("Action"), False,),
	("adventure", _("Adventure"), False,),
	("animation", _("Animation"), False,),
	("biography", _("Biography"), False,),
	("cartoons", _("Cartoons"), False,),
	("comedy", _("Comedy"), False,),
	("crime", _("Crime"), False,),
	("disaster", _("Disaster"), False,),
	("documentary", _("Documentary"), False,),
	("drama", _("Drama"), False,),
	("erotic", _("Erotic"), True,),
	("experimental", _("Experimental"), False,),
	("fairytales", _("Fairytales"), False,),
	("family", _("Family"), False,),
	("fantasy", _("Fantasy"), False,),
	("history", _("History"), False,),
	("horror", _("Horror"), False,),
	("imax", _("Imax"), False,),
	("krimi", _("Krimi"), False,),
	("music", _("Music"), False,),
	("mystery", _("Mystery"), False,),
	("psychological", _("Psychological"), False,),
	("publicistic", _("Publicistic"), False,),
	("realitytv", _("Reality TV"), False,),
	("romance", _("Romance"), False,),
	("sci-fi", _("Sci-Fi"), False,),
	("sport", _("Sport"), False,),
	("talkshow", _("Talkshow"), False,),
	("thriller", _("Thriller"), False,),
	("war", _("War"), False,),
	("western", _("Western"), False,),
]

SORT_LIST = [
	# sort keyword, name
	("", _('Best match'),),

	("v1", _('popularity'),),
	("-v1", _('popularity descending'),),

	("v2", _('CSFD rating'), ),
	("-v2", _('CSFD rating descending'),),

	("v3", _('IMDB rating'),),
	("-v3", _('IMDB rating descending'),),

	("v4", _('Movie budget'),),
	("-v4", _('Movie budget descending'),),

	("v5", _('Movie revenue'),),
	("-v5", _('Movie revenue descending'),),

	("v6", _('Alphabet'),),
	("-v6", _('Alphabet descending'),),

	("v7", _('Date added'),),
	("-v7", _('Date added descending'),),
]

SORT_TVSHOWS_LIST = [
	# sort keyword, name
	("", _('Best match'),),

	("v1", _('popularity'),),
	("-v1", _('popularity descending'),),

	("v2", _('CSFD rating'), ),
	("-v2", _('CSFD rating descending'),),

	("v3", _('IMDB rating'),),
	("-v3", _('IMDB rating descending'),),

	("v6", _('Alphabet'),),
	("-v6", _('Alphabet descending'),),

	("v7", _('Date added'),),
	("-v7", _('Date added descending'),),
]

COUNTRY_LIST = [
	("", _("All"),),
	("cs", _("Czech Republic"),),
	("us", _("USA"),),
	("sk", _("Slovakia"),),
	("uk", _("Great Britain"),),
	("de", _("Germany"),),
	("es", _("Spain"),),
	("en", _("America"),),
	("fr", _("France"),),
	("it", _("Italia"),),
	("ca", _("Canada"),),
	("ro", _("Romania"),),
	("ja", _("Japan"),),
	("cn", _("HongKong"),),
	("tr", _("Turkey"),),
	("de", _("Austria"),),
	("dk", _("Denmark"),),
	("nl", _("Netherlands"),),
	("be", _("Belgium"),),
	("ie", _("Ireland"),),
	("eg", _("Egypt"),),
	("ch", _("Switzerland"),),
	("pe", _("Peru"),),
	("lu", _("Luxembourg"),),
	("za", _("JAR"),),
	("nz", _("New Zealand"),),
	("cn", _("China"),),
	("ua", _("Ukraine"),),
	("fi", _("Finland"),),
	("se", _("Sweden"),),
	("ru", _("Russia"),),
]

LANG_LIST = [
	("", _("All"),),
	('cz', _('Czech'),),
	('sk', _('Slovak'),),
	('en', _('English'),),
	('cn', _('Chinese'),),
	('de', _('German'),),
	('el', _('Greek'),),
	('es', _('Spanish'),),
	('fi', _('Finnish'),),
	('fr', _('French'),),
	('hr', _('Croatian'),),
	('id', _('Indu'),),
	('it', _('Italian'),),
	('ja', _('Japanese'),),
	('ko', _('Korean'),),
	('nl', _('Dutch'),),
	('no', _('Norwegian'),),
	('pl', _('Polish'),),
	('pt', _('Portuguese'),),
	('ru', _('Russian'),),
	('tr', _('Turkish'),),
	('vi', _('Vietnamese'),),
]

class SosacContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, icons_dir=None):
		CommonContentProvider.__init__(self, 'sosac', settings=settings, data_dir=data_dir)
		self.days_of_week = (_('Monday'), _('Tuesday'), _('Wednesday'), _('Thursday'), 	_('Friday'), _('Saturday'), _('Sunday'))
		self.icons_dir = icons_dir
		self.login_optional_settings_names = ('streamujtv_user', 'streamujtv_pass', 'sosac_user', 'sosac_pass')
		self.sosac = None

	# ##################################################################################################################

	def login(self, silent):
		self.sosac = Sosac(self)
		self.sosac.request_configuration()
		self.sosac.check_login(True)

		return True

	# ##################################################################################################################

	def get_icon(self, name):
		return os.path.join(self.icons_dir, name + '.png')

	# ##################################################################################################################

	def root(self):
		self.sosac.request_configuration()
		self.sosac.check_login()
		self.build_lang_lists()

		info_labels = self._('Simple and advanced search for movies and series.')
		self.add_dir(self._("Search"), self.get_icon('search'), info_labels, cmd=self.list_search_menu)
		info_labels = self._('You can choose movies to watch on the web page movies.sosac.tv.')
		self.add_dir(self._("Movies"), self.get_icon('movies'), info_labels, cmd=self.list_movies_menu)
		info_labels = self._('You can choose series to watch on the web page tv.sosac.tv.')
		self.add_dir(self._("Tv Shows"), self.get_icon('tvshows'), info_labels, cmd=self.list_tvshows_menu)
		info_labels = self._('Movies and series as they were shown on TV.')
		self.add_dir(self._("Tv Guide"), self.get_icon('tvguide'), cmd=self.list_tvguide)

	# #################################################################################################

	def list_movies_menu(self):
		self.add_search_dir(search_id='movies')

		info_labels = self._('Advanced search by many parameters')
		self.add_dir(self._("Advanced search"), self.get_icon('advancedsearch'), info_labels, cmd=self.list_advanced_search)

		info_labels = self._('Here you will find your favourite movies. You can add items to favourite by using context menu or on the web movies.sosac.tv.')
		self.add_dir(self._("My playlist"), self.get_icon('playlist'), info_labels, cmd=self.list_movies, stream='queue', in_playlist=True)

		info_labels = self._('Your unfinished movies.')
		self.add_dir(self._("Unfinished"), self.get_icon('unfinishedmovies'), info_labels, cmd=self.list_movies, stream='unfinished')

		info_labels = self._('History of watched movies')
		self.add_dir(self._("Watched"), self.get_icon('watchedmovies'), info_labels, cmd=self.list_movies, stream='finished')

		info_labels = self._('New movies with dubbing')
		self.add_dir(self._("News with dubbing"), self.get_icon('newdubbedmovies'), info_labels, cmd=self.list_movies, stream='news-with-dubbing')

		info_labels = self._('New movies with subtitles')
		self.add_dir(self._("News with subtitles"), self.get_icon('withsubtitles'), info_labels, cmd=self.list_movies, stream='news-with-subtitles')

		info_labels = self._('Last added new or older movies.')
		self.add_dir(self._("Last added"), self.get_icon('lastaddedmovies'), info_labels, cmd=self.list_movies, stream='last-added')

		if self.sosac.configuration.get('current_topic'):
			try:
				info_labels = self._('Actual thematic movies category')
				if self.lang_list[0] == 'en':
					i = 0
				else:
					i = 1

				self.add_dir(self.sosac.configuration.get('current_topic').split('|')[i].strip(), self.get_icon('movies'), info_labels, cmd=self.list_movies, stream='current-topic')
			except:
				self.log_exception()

		info_labels = self._('Popular movies released in the last 3 years.')
		self.add_dir(self._("Popular news"), self.get_icon('newmostpopular'), info_labels, cmd=self.list_movies, stream='news-popular')

		info_labels = self._('All popular movies')
		self.add_dir(self._("Popular"), self.get_icon('mostpopular'), info_labels, cmd=self.list_movies, stream='popular')

		info_labels = self._('Top rated movies released in the last 3 years.')
		self.add_dir(self._("Top rated news"), self.get_icon('bestratednew'), info_labels, cmd=self.list_movies, stream='news-top-rated')

		info_labels = self._('All top rated movies')
		self.add_dir(self._("Top rated"), self.get_icon('bestrated'), info_labels, cmd=self.list_movies, stream='top-rated')

		info_labels = self._('All movies sorted by starting letter')
		self.add_dir(self._("By letter"), self.get_icon('movies-tvshows-a-z'), info_labels, cmd=self.list_categories, stream='a-z', movies=True)

		info_labels = self._('All movies sorted by genre')
		self.add_dir(self._("By genre"), self.get_icon('genre'), info_labels, cmd=self.list_categories, stream='by-genre', movies=True)

		info_labels = self._('All movies sorted by year of release')
		self.add_dir(self._("By year"), self.get_icon('byyear'), info_labels, cmd=self.list_categories, stream='by-year', movies=True)

		info_labels = self._('All movies sorted by available stream quality')
		self.add_dir(self._("By quality"), self.get_icon('byquality'), info_labels, cmd=self.list_categories, stream='by-quality', movies=True)

	# #################################################################################################

	def list_tvshows_menu(self):
		self.add_search_dir(search_id='tvshows')

		info_labels = self._('Advanced search by many parameters')
		self.add_dir(self._("Advanced search"), self.get_icon('advancedsearch'), info_labels, cmd=self.list_advanced_search, category='tvshows')

		info_labels = self._('Here you will find your favourite tv shows. You can add new tv shows by using context menu or on the web tv.sosac.tv.')
		self.add_dir(self._("My playlist"), self.get_icon('playlist'), info_labels, cmd=self.list_tvshows, stream='queue', in_playlist=True)

		info_labels = self._('Tv shows with at least one not fully watched episode.')
		self.add_dir(self._("Unfinished"), self.get_icon('unfinishedtvshows'), info_labels, cmd=self.list_tvshows, stream='unfinished')

		info_labels = self._('Tv shows where all episodes are maked as watched.')
		self.add_dir(self._("Watched"), self.get_icon('watchedtvshows'), info_labels, cmd=self.list_tvshows, stream='finished')

		info_labels = self._('Last added new or older tv shows.')
		self.add_dir(self._("Last added"), self.get_icon('lastaddedtvshows'), info_labels, cmd=self.list_tvshows, stream='last-added')

		info_labels = self._('New episodes with dubbing or older episodes with newly added dubbing.')
		self.add_dir(self._("News with dubbing"), self.get_icon('newmostpopular'), info_labels, cmd=self.list_tvshows, stream='news-with-dubbing', episodes=True)

		info_labels = self._('New episodes with subtitles')
		self.add_dir(self._("News with subtitles"), self.get_icon('withsubtitles'), info_labels, cmd=self.list_tvshows, stream='news-with-subtitles', episodes=True)

		info_labels = self._('Last added episodes.')
		self.add_dir(self._("Last added"), self.get_icon('newmostpopular'), info_labels, cmd=self.list_tvshows, stream='last-added', episodes=True)

		info_labels = self._('The broadcast schedule of tv show episodes. This list also include inactive episodes that will be added after they air.')
		self.add_dir(self._("Episodes calendar"), self.get_icon('tvtracker'), info_labels, cmd=self.list_episodes_by_date)

		info_labels = self._('Popular tv shows released in the last 3 years with highest number of views or number of ratings (good or bad).')
		self.add_dir(self._("Popular news"), self.get_icon('newmostpopular'), info_labels, cmd=self.list_tvshows, stream='news-popular')

		info_labels = self._('Popular tv shows with highest number of views or number of ratings (good or bad).')
		self.add_dir(self._("Popular"), self.get_icon('mostpopular'), info_labels, cmd=self.list_tvshows, stream='popular')

		info_labels = self._('Top rated tv shows released in the last 3 years.')
		self.add_dir(self._("Top rated news"), self.get_icon('bestratednew'), info_labels, cmd=self.list_tvshows, stream='news-top-rated')

		info_labels = self._('All top rated tv shows')
		self.add_dir(self._("Top rated"), self.get_icon('bestrated'), info_labels, cmd=self.list_tvshows, stream='top-rated')

		info_labels = self._('All tv shows sorted by starting letter')
		self.add_dir(self._("By letter"), self.get_icon('movies-tvshows-a-z'), info_labels, cmd=self.list_categories, stream='a-z', movies=False)

		info_labels = self._('All tv shows sorted by genre')
		self.add_dir(self._("By genre"), self.get_icon('genre'), info_labels, cmd=self.list_categories, stream='by-genre', movies=False)

		info_labels = self._('All tv shows sorted by year of release')
		self.add_dir(self._("By year"), self.get_icon('byyear'), info_labels, cmd=self.list_categories, stream='by-year', movies=False)

	# #################################################################################################

	def list_search_menu(self):
		self.add_search_dir(self._("Simple movies search"), search_id='movies')

		info_labels = self._('Advanced search by many parameters')
		self.add_dir(self._("Advanced movies search"), self.get_icon('advancedsearch'), info_labels, cmd=self.list_advanced_search)

		self.add_search_dir(self._("Simple TV shows search"), search_id='tvshows')

		info_labels = self._('Advanced search by many parameters')
		self.add_dir(self._("Advanced TV shows search"), self.get_icon('advancedsearch'), info_labels, cmd=self.list_advanced_search, category='tvshows')


	# #################################################################################################

	def advanced_search_cmd(self, sname, c):
		data = self.load_cached_data(sname)

		if c == 'reset':
			data = {}

		elif c in ('sort', 'genre', 'origin', 'lang', 'quality'):
			cfg = {
				'sort' : (self._("Select sort method"), SORT_LIST if sname.endswith('movies') else SORT_TVSHOWS_LIST,),
				'genre': (self._("Select genre"), GENRE_LIST,),
				'origin': (self._("Select origin country"), COUNTRY_LIST,),
				'lang': (self._("Select language"), LANG_LIST,),
				'quality': (self._("Select quality"),QUALITY_LIST,),
			}

			lst = [self._(s[1]) for s in cfg[c][1]]
			idx = self.get_list_input(lst, cfg[c][0], data.get(c, 0))
			if idx >= 0:
				data[c] = idx

		elif c in ('keyword', 'director', 'screenwriter', 'actor'):
			cfg = {
				'keyword' : self._("Enter search keyword"),
				'director': self._("Enter director name"),
				'screenwriter': self._("Enter screenwriter name"),
				'actor': self._("Enter actor name"),
			}

			ret = self.get_text_input(cfg[c])
			if ret != None:
				data[c] = ret

		elif c in ('year_from', 'year_to'):
			ret = self.get_text_input(self._("Enter year"), input_type='number')
			if ret != None:
				data[c] = ret

		self.save_cached_data(sname, data)
		self.refresh_screen()

	# #################################################################################################

	def list_advanced_search(self, category='movies'):
		sname = 'adv_search_' + category
		data = self.load_cached_data(sname)

		sort_list = SORT_LIST if category == 'movies' else SORT_TVSHOWS_LIST

		self.add_video(self._('Reset search parameters'), cmd=self.advanced_search_cmd, sname=sname, c='reset')
		self.add_video('%s: %s' % (self._('Sort by'), self._(sort_list[data.get('sort', 0)][1])), cmd=self.advanced_search_cmd, sname=sname, c='sort')
		self.add_video('%s: %s' % (self._('Search word(s)'), data.get('keyword', '')), cmd=self.advanced_search_cmd, sname=sname, c='keyword')
		self.add_video('%s: %s' % (self._('Director'), data.get('director', '')), cmd=self.advanced_search_cmd, sname=sname, c='director')
		self.add_video('%s: %s' % (self._('Screenwriter'), data.get('screenwriter', '')), cmd=self.advanced_search_cmd, sname=sname, c='screenwriter')
		self.add_video('%s: %s' % (self._('Actor'), data.get('actor', '')), cmd=self.advanced_search_cmd, sname=sname, c='actor')
		self.add_video('%s: %s' % (self._('From year'), data.get('year_from', 1900)), cmd=self.advanced_search_cmd, sname=sname, c='year_from')
		self.add_video('%s: %s' % (self._('To year'), data.get('year_to', datetime.now().year)), cmd=self.advanced_search_cmd, sname=sname, c='year_to')
		self.add_video('%s: %s' % (self._('Genre'), self._(GENRE_LIST[data.get('genre', 0)][1])), cmd=self.advanced_search_cmd, sname=sname, c='genre')
		self.add_video('%s: %s' % (self._('Origin country'), self._(COUNTRY_LIST[data.get('origin', 0)][1])), cmd=self.advanced_search_cmd, sname=sname, c='origin')
		self.add_video('%s: %s' % (self._('Language'), self._(LANG_LIST[data.get('lang', 0)][1])), cmd=self.advanced_search_cmd, sname=sname, c='lang')
		self.add_video('%s: %s' % (self._('Quality'), self._(QUALITY_LIST[data.get('quality', 0)][1])), cmd=self.advanced_search_cmd, sname=sname, c='quality')
		self.add_dir(self._('Run search'), cmd=self.search_advanced, category=category)

	# #################################################################################################

	def search_advanced(self, category, page=1):
		sname = 'adv_search_' + category
		data = self.load_cached_data(sname)

		sort_list = SORT_LIST if category == 'movies' else SORT_TVSHOWS_LIST

		params = {
			'sort': sort_list[data.get('sort', 0)][0] or None,
			'keyword': data.get('keyword') or None,
			'director': data.get('director') or None,
			'screenwriter': data.get('screenwriter') or None,
			'actor': data.get('actor') or None,
			'year_from': data.get('year_from', 1900),
			'year_to': data.get('year_to', datetime.now().year),
			'genre': GENRE_LIST[data.get('genre', 0)][0] or None,
			'origin': COUNTRY_LIST[data.get('origin', 0)][0] or None,
			'lang': LANG_LIST[data.get('lang', 0)][0] or None,
			'quality': QUALITY_LIST[data.get('quality', 0)][0] or None,
		}

		if category == 'movies':
			result = self.sosac.search_advanced('movies', params, page)
			add_item = self.add_movie
		elif category == 'tvshows':
			result = self.sosac.search_advanced('serials', params, page)
			add_item = self.add_tvshow

		disable_adult = not self.get_setting('enable-adult')

		for item in result:
			if disable_adult and item['adult']:
				continue

			add_item(item)

		if len(result) >= self.sosac.PAGE_SIZE:
			self.add_next(cmd=self.search_advanced, category=category, page=page+1)

	# #################################################################################################

	def date_picker(self, title=None, reversed=False, page_len=14):
		start_date = datetime.now()
		now = start_date

		if reversed:
			page_start = page_len // 2
			page_end = -page_start
			page_inc = -1
			prev_next_elements = (self._("Next"), self._("Previous"),)
			selection = (page_len // 2) + 1
		else:
			page_start = -(page_len // 2)
			page_end = -page_start
			page_inc = 1
			prev_next_elements = (self._("Previous"), self._("Next"),)
			selection = (page_len // 2) + 1

		# this is needed to properly handle odd page_len
		page_len = page_end - page_start

		while True:
			lst = [prev_next_elements[0]]
			date_list = []

			for i in range(page_start, page_end, page_inc):
				d = start_date + timedelta(days=i)
				date_list.append(d)
				date_str = '{:02d}.{:02d}.{:04d}'.format(d.day, d.month, d.year)
				if d == now:
					lst.append('{} ({})'.format(_I(date_str), _I(self.days_of_week[d.weekday()])))
				else:
					lst.append('{} ({})'.format(date_str, _I(self.days_of_week[d.weekday()])))

			lst.append(prev_next_elements[1])

			i = self.get_list_input(lst, title if title else self._("Select date"), selection)
			if i == -1:
				raise AddonSilentExitException("User has not choosed any date")
			elif i == 0:
				start_date = start_date - (timedelta(days=page_len) * page_inc)
			elif i == len(lst)-1:
				start_date = start_date + (timedelta(days=page_len) * page_inc)
			else:
				return date_list[i-1]

			selection = 0

	# #################################################################################################

	def list_tvguide(self, day=None, page=1):
		if day == None:
			d = self.date_picker()
			day = '%04d-%02d-%02d' % (d.year, d.month, d.day)
#			self.update_last_command(self.list_tvguide, day=day, page=page)
#			self.refresh_screen(parent=True)

		disable_adult = not self.get_setting('enable-adult')

		result = self.sosac.get_tvguide(day, page)

		for item in result:
			if disable_adult and item['adult']:
				continue

			if item['type'] == 'movie':
				self.add_movie(item)
			elif item['type'] == 'episode':
				self.add_episode(item)
			elif item['type'] == 'tvshow':
				self.add_tvshow(item)
			elif item['type'] == 'dummy':
				continue
			else:
				self.log_error("Unknown item type: %s" % item['type'])

		if len(result) >= self.sosac.PAGE_SIZE:
			self.add_next(cmd=self.list_tvguide, day=day, page=page+1)

	# #################################################################################################

	def get_title(self, item, simple=False, red=False):
		def _title():
			item_title = item['title']
			for l in self.lang_list:
				if l in item_title:
					if isinstance(item_title[l], type([])):
						return item_title[l][0]
					else:
						return item_title[l]
			else:
				t = list(item_title.values())[0]
				if isinstance(t, type([])):
					return t[0]
				else:
					return t

		def _lang():
			def _up(i):
				x = i.split('+')

				if len(x) > 1:
					return x[0].upper() + '+' + '+'.join(x[1:])
				else:
					return x[0].upper()

			return ', '.join(_up(i) for i in item['lang'])

		if simple:
			return _C('red', _title()) if red else _title()
		else:
			if 'channel' in item:
				f = '{date} {title}{lang}{year} ({channel}){watched}'

				start = datetime.fromtimestamp(item['channel']['start'])
				d = '{}:{}'.format(_I('%02d') % start.hour, _I('%02d') % start.minute)
				channel = item['channel']['name']
			else:
				f = '{title}{lang}{year}{watched}'
				d=''
				channel=''

			if item['duration'] and item['watched']:
				if  item['watched'] > (item['duration'] * 0.85):
					watched = _B(' *')
				else:
					watched = ' *'
			else:
				watched = ''

			return f.format(
				date=d,
				title=_C('red', _title()) if red else _title(),
				lang=(' - %s' % _I(_lang())) if item['lang'] else '',
				year=(' (%d)' % item['year']) if item['year'] else '',
				channel=channel,
				watched=watched
			)

	# #################################################################################################

	def get_episode_title(self, item, simple=False, red=False, lang_info=True):
		def _title(item_tile):
			if not item_tile:
				return ''

			for l in self.lang_list:
				if l in item_tile:
					return item_tile[l]
			else:
				return list(item_tile.values())[0]

		def _lang():
			def _up(i):
				x = i.split('+')

				if len(x) > 1:
					return x[0].upper() + '+' + '+'.join(x[1:])
				else:
					return x[0].upper()

			return ', '.join(_up(i) for i in item['lang'])

		if item['duration'] and item['watched']:
			if  item['watched'] > (item['duration'] * 0.85):
				watched = _B(' *')
			else:
				watched = ' *'
		else:
			watched = ''

		if simple:
			title = _title(item['ep_title'] or item['title'])
			return '{title}{lang}{watched}'.format(
				title=_C('red', title) if red else title,
				lang=(' - %s' % _I(_lang())) if lang_info and item['lang'] else '',
				watched=watched
			)
		else:
			title = '%s: %s' % (_title(item['title']), _title(item['ep_title']))

			if 'channel' in item:
				f = '{date} {title}{lang}{year} ({channel}){watched}'

				start = datetime.fromtimestamp(item['channel']['start'])
				d = '{}:{}'.format(_I('%02d') % start.hour, _I('%02d') % start.minute)
				channel = item['channel']['name']
			else:
				f = '{title}{lang}{year}{watched}'
				d=''
				channel=''

			return f.format(
				date=d,
				title=_C('red', title) if red else title,
				lang=(' - %s' % _I(_lang())) if lang_info and item['lang'] else '',
				year=(' (%d)' % item['year']) if item['year'] else '',
				channel=channel,
				watched=watched
			)

	# #################################################################################################

	def manage_item(self, category, command, item):
		if command == 'playlist_add':
			self.sosac.watchlist_add(category, item['parent_id'] or item['id'])
		elif command == 'playlist_delete':
			self.sosac.watchlist_delete(category, item['parent_id'] or item['id'])
		elif command in ('watched', 'reset'):
			if command == 'reset':
				reset = True
			else:
				reset = False

			if category == 'serials':
				for season in self.sosac.get_tvshow_detail(item):
					for episode in season['episodes']:
						self.sosac.set_watching_time('episodes', episode['id'], 0 if reset else int(episode['duration']))
						episode['watched'] = int(episode['duration'])
			else:
				self.sosac.set_watching_time(category, item['id'], 0 if reset else int(item['duration']))
				item['watched'] = int(item['duration'])

		self.refresh_screen()

	# #################################################################################################

	def add_movie(self, item, in_playlist=False):
		if not self.lang_filter_passed(item):
			return

		if item['genre']:
			genre_prefix = '[' +  ' / '.join(item['genre']) + ']\n'
		else:
			genre_prefix = ''

		info_labels = {
			'title': self.get_title(item, True),
			'plot': genre_prefix + item['plot'],
			'duration': item['duration'],
			'genre': ', '.join(item['genre']),
			'year': item['year'],
			'rating': item['rating'],
			'adult': item['adult']
		}

		menu = self.create_ctx_menu()
		# TODO: Add watchlist items management
		if in_playlist:
			menu.add_menu_item(self._("Delete from playlist"), cmd=self.manage_item, category='movies', command='playlist_delete', item=item)
		else:
			menu.add_menu_item(self._("Add to playlist"), cmd=self.manage_item, category='movies', command='playlist_add', item=item)

		menu.add_menu_item(self._("Mark as watched"), cmd=self.manage_item, category='movies', command='watched', item=item)

		if item['watched']:
			menu.add_menu_item(self._("Reset watched time"), cmd=self.manage_item, category='movies', command='reset', item=item)

		self.add_video(self.get_title(item, red=item.get('stream_id') is None), item['img'], info_labels=info_labels, menu=menu, cmd=self.resolve_video_streams, item=item )


	# #################################################################################################

	def add_tvshow(self, item, in_playlist=False):
		if not self.lang_filter_passed(item):
			return

		if item['genre']:
			genre_prefix = '[' +  ' / '.join(item['genre']) + ']\n'
		else:
			genre_prefix = ''

		info_labels = {
			'title': self.get_title(item, True),
			'plot': genre_prefix + item['plot'],
			'duration': item['duration'],
			'genre': ', '.join(item['genre']),
			'year': item['year'],
			'rating': item['rating'],
			'adult': item['adult']
		}

		menu = self.create_ctx_menu()
		# TODO: Add watchlist items management
		if in_playlist:
			menu.add_menu_item(self._("Delete from playlist"), cmd=self.manage_item, category='serials', command='playlist_delete', item=item)
		else:
			menu.add_menu_item(self._("Add to playlist"), cmd=self.manage_item, category='serials', command='playlist_add', item=item)
		menu.add_menu_item(self._("Mark as watched"), cmd=self.manage_item, category='serials', command='watched', item=item)
		menu.add_menu_item(self._("Reset watched time"), cmd=self.manage_item, category='serials', command='reset', item=item)

		self.add_dir(self.get_title(item), item['img'], info_labels=info_labels, menu=menu, cmd=self.list_series, item=item )

	# #################################################################################################

	def add_episode(self, item, episode_number=False):
		if not self.lang_filter_passed(item):
			return

		if item.get('genre'):
			genre_prefix = '[' +  ' / '.join(item['genre']) + ']\n'
		else:
			genre_prefix = ''

		info_labels = {
			'title': self.get_title(item, True),
			'plot': genre_prefix + item['plot'],
			'genre': ', '.join(item.get('genre',[])),
			'year': item['year'],
			'duration': item['duration'],
			'rating': item['rating'],
			'adult': item['adult']
		}

		title = self.get_episode_title(item, simple=episode_number, red=item.get('stream_id') is None)

		if episode_number:
			title = '{}. {}'.format(_I('%02d') % int(item['episode']), title)

		if item.get('episode') and item.get('season'):
			info_labels['title'] = '%s %s (%d)' % (info_labels['title'], int_to_roman(item['season']), item['episode'])

		menu = self.create_ctx_menu()

		if not episode_number:
			tvshow_item = item.copy()
			tvshow_item['id'] = item['parent_id']
			tvshow_item['parent_id'] = None
			menu.add_menu_item(self._("Open TV Show"), cmd=self.list_series, item=tvshow_item)

		# TODO: Add watchlist items management
		menu.add_menu_item(self._("Add to playlist"), cmd=self.manage_item, category='serials', command='playlist_add', item=item)
		menu.add_menu_item(self._("Mark as watched"), cmd=self.manage_item, category='episodes', command='watched', item=item)

		if item['watched']:
			menu.add_menu_item(self._("Reset watched time"), cmd=self.manage_item, category='episodes', command='reset', item=item)

		self.add_video(title, item['img'], info_labels=info_labels, menu=menu, cmd=self.resolve_video_streams, item=item )


	# #################################################################################################

	def list_movies(self, stream, page=1, in_playlist=False, **kwargs):
		disable_adult = not self.get_setting('enable-adult')

		result = self.sosac.get_movies_list(stream, page, **kwargs)
		for item in result:
			if disable_adult and item['adult']:
				continue

			self.add_movie(item, in_playlist)

		if len(result) >= self.sosac.PAGE_SIZE:
			self.add_next(cmd=self.list_movies, stream=stream, page=page+1, **kwargs)

	# #################################################################################################

	def list_tvshows(self, stream, episodes=False, page=1, in_playlist=False, **kwargs):
		if episodes:
			result = self.sosac.get_episodes_list(stream, page, **kwargs)
		else:
			result = self.sosac.get_tvshow_list(stream, page, **kwargs)

		disable_adult = not self.get_setting('enable-adult')

		for item in result:
			if disable_adult and item['adult']:
				continue

			if episodes:
				self.add_episode(item)
			else:
				self.add_tvshow(item, in_playlist)

		if len(result) >= self.sosac.PAGE_SIZE:
			self.add_next(cmd=self.list_tvshows, stream=stream, episodes=episodes, page=page+1, **kwargs)

	# #################################################################################################

	def list_episodes_by_date(self, date_from=None, date_to=None):
		if not date_from:
			date_from = self.date_picker(self._("Select beginnig date"))
			date_from = '%04d-%02d-%02d' % (date_from.year, date_from.month, date_from.day)
#			self.update_last_command(self.list_episodes_by_date, date_from=date_from, date_to=date_to)
#			self.refresh_screen(parent=True)

		if not date_to:
			date_to = self.date_picker(self._("Select end date"))
			date_to = '%04d-%02d-%02d' % (date_to.year, date_to.month, date_to.day)
#			self.update_last_command(self.list_episodes_by_date, date_from=date_from, date_to=date_to)
#			self.refresh_screen(parent=True)

		return self.list_tvshows('by-date', True, date_from=date_from, date_to=date_to)

	# #################################################################################################

	def list_categories(self, stream, movies=True, page=1):
		enable_adult = self.get_setting('enable-adult')

		if stream == "a-z" :
			listvalue = [(l[0], l.upper(), False,) for l in LETTER_LIST]
			key_name = 'letter'
		elif stream == "by-genre" :
			listvalue = [(g[0], self._(g[1]), g[2],) for g in GENRE_LIST[1:]]
			key_name = 'genre'
		elif stream == "by-quality" :
			listvalue = [ (q[0], q[1], False,) for q in QUALITY_LIST[1:]]
			key_name = 'quality'
		elif stream == "by-year" :
			listvalue = [ (y, y, False,) for y in range(datetime.now().year, 1900, -1)]
			key_name = 'year'

		for val in listvalue:
			if val[2] and not enable_adult:
				continue

			if movies:
				self.add_dir(val[1], cmd=self.list_movies, stream=stream, **{key_name: val[0]} )
			else:
				self.add_dir(val[1], cmd=self.list_tvshows, stream=stream, **{key_name: val[0]} )

	# #################################################################################################

	def list_series(self, item):
		result = self.sosac.get_tvshow_detail(item)

		if len(result) == 1:
			# only one season
			self.list_episodes(result[0]['episodes'])
		else:
			for season in result:
				info_labels = {
					'title': '%s %s' % (self.get_title(item, True), int_to_roman(season['season']))
				}
				self.add_dir('%s %02d' % (self._("Season"), season['season']), info_labels=info_labels, cmd=self.list_episodes, data=season['episodes'])

	# #################################################################################################

	def list_episodes(self, data):
		for item in data:
			self.add_episode(item, True)

	# #################################################################################################

	def build_lang_lists(self):
		self.dubbed_lang_list = self.get_dubbed_lang_list()
		self.lang_list = self.dubbed_lang_list[:]
		if 'en' not in self.lang_list:
			self.lang_list.append('en')

	# #################################################################################################

	def search(self, keyword, search_id, page=1):
		if search_id == 'movies':
			result = self.sosac.search_simple('movies', keyword, page)
			add_item = self.add_movie
		elif search_id == 'tvshows':
			result = self.sosac.search_simple('serials', keyword, page)
			add_item = self.add_tvshow
		else:
			return

		disable_adult = not self.get_setting('enable-adult')

		for item in result:
			if disable_adult and item['adult']:
				continue

			add_item(item)

		if len(result) >= self.sosac.PAGE_SIZE:
			self.add_next(cmd=self.search, keyword=keyword, search_id=search_id, page=page+1)

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

	def lang_filter_passed(self, item):
		item_filter = self.get_setting('item-lang-filter')
		stream_filter = self.get_setting('stream-lang-filter').split('+')

		if item_filter == 'all':
			return True

		if stream_filter[0] == 'all':
			return True

		stream_filter = ['cz' if x == 'cs' else x for x in stream_filter]

		alangs = []
		subs = []
		for a in (item.get('lang') or []):
			ax = a.split('+')
			alangs.append(ax[0])

			if len(ax) > 1 and ax[1].endswith('tit'):
				subs.append(ax[1][:-3])

		alangs = list(set(alangs))
		subs = list(set(subs))

		if alangs:
#			self.log_debug("alangs: %s, stream_filter: %s" % (alangs, stream_filter))
			if item_filter in ('dub', 'dubsubs'):
				for l in stream_filter:
					if l in alangs:
						return True

#			self.log_debug("subs: %s, stream_filter: %s" % (subs, stream_filter))
			if item_filter == 'dubsubs':
				for l in stream_filter:
					if l in subs:
						return True
		else:
			self.log_debug("No lang info available for %s" % item)
			# no lang info available
			return True

		return False

	# ##################################################################################################################

	def filter_streams(self, streams):
		result = []
		min_quality = int(self.get_setting('min-quality'))
		max_quality = int(self.get_setting('max-quality'))
		item_lang_filter = self.get_setting('item-lang-filter')
		lang_filter = self.get_setting('stream-lang-filter')

		for strm in streams:
#			self.log_debug("Filtering stream [%s%s][%s][%s][%s]" % (strm.get('quality', '???'), strm.get('vinfo', '???'), strm.get('size', '???'), strm.get('lang', '???'), strm.get('ainfo', '???')[2:].replace('[', '').replace(']', '')))
			self.log_debug("Filtering stream: quality: %s, resolution: %s, lang: %s, sub_lang: %s" % (strm['quality'], strm['resolution'], strm['lang'], strm['sub_lang']))

			strm_quality = strm.get('resolution','').lower()
			if strm_quality:
				try:
					# convert string representing stream quality (720p, 1080i, 4k, ...) to vertical resolution
					if strm_quality.endswith('p') or strm_quality.endswith('i'):
						strm_quality = int(strm_quality[:-1])
					elif strm_quality.endswith('k'):
						strm_quality = int(strm_quality[:-1]) * 540
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
			avail_lang = strm.get('lang')

			if lang_filter != 'all' and avail_lang:
				if lang_filter == 'cs+sk': # CZ or SK
					ll = [ 'CZ', 'SK']
				elif lang_filter == 'cs': # CZ
					ll = [ 'CZ' ]
				elif lang_filter == 'sk': # SK
					ll = [ 'SK' ]
				elif lang_filter == 'en': # EN
					ll = [ 'EN' ]
				else:
					ll = []

				for l in ll:
					if l == avail_lang:
						break
				else:
					# configured lang not found in available languages

					# if show all items or show dubed or with subtitles is set, then check also if there are subtitles available
					if item_lang_filter == 'all' or item_lang_filter == 'dubsubs':
						# check if there are subtitles available
						if not strm.get('sub_lang'):
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

	def resolve_video_streams(self, item):
		if not item.get('stream_id'):
			return

		streams = self.sosac.get_streams(item['stream_id'])

		if not streams:
			return

		if len(streams) == 1:
			idx = 0
		else:
			use_subs = self.get_setting('subs-autostart') in ('always', 'undubbed')

			streams = sorted(streams, key=lambda x: (int(x['resolution'][:-1]), x['lang'] in ('SK', 'CZ'), use_subs and x['sub_lang'] != None,), reverse=True )

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
			title = "[%s][%s]%s" % (_I(strm['resolution']), _I(strm['lang']), '[%s tit]' % strm['sub_lang'] if strm['sub_lang'] else '')
			titles.append( title )

		if idx == None:
			idx = self.get_list_input(titles, self._('Please select a stream'))
			if idx == -1:
				return

		stream = streams[idx]
		subs_url = stream.get('sub_url')

		media_title = self.get_title(item, simple=True)

		duration = item.get('duration')
		info_labels = { 'title': media_title }
		settings = {}

		last_position = item['watched']

		if self.silent_mode == False and self.get_setting('save-last-play-pos') and last_position > 0 and (not duration or last_position < (duration * int(self.get_setting('last-play-pos-limit'))) // 100):
			settings['resume_time_sec'] = last_position

		settings['lang_priority'] = self.dubbed_lang_list
		if 'en' not in settings['lang_priority']:
			settings['lang_fallback'] = ['en']

		settings['subs_autostart'] = self.get_setting('subs-autostart') in ('always', 'undubbed')
		settings['subs_always'] = self.get_setting('subs-autostart') == 'always'
		settings['subs_forced_autostart'] = self.get_setting('forced-subs-autostart')

		play_params = {
			'info_labels': info_labels,
#			'trakt_item': trakt_info,
			'data_item': item,
			'settings': settings
		}

		playlist = self.add_playlist(media_title, variant=True)

		playlist.add_play(titles[idx], self.sosac.req_session.get(stream['url']).text, subs=subs_url, **play_params)

		for i in range(len(streams)):
			if i != idx:
				playlist.add_video(titles[i], cmd=self.simple_resolve, url=streams[i].get('url'), subs_url=streams[i].get('sub_url'), media_title=media_title, play_params=play_params, **play_params)

	# #################################################################################################

	def simple_resolve(self, media_title, url, subs_url, play_params={}):
		self.add_play(media_title, self.sosac.req_session.get(url).text, subs=subs_url, **play_params)

	# #################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		try:
			if action.lower() == 'end':
				if position and self.get_setting('save-last-play-pos'):
					self.sosac.set_watching_time('episodes' if data_item['parent_id'] else 'movies', data_item['id'], position)
					data_item['watched'] = position

		except:
			self.log_error("Stats processing failed")
			self.log_exception()

	# #################################################################################################
