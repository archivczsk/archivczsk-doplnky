# -*- coding: utf-8 -*-

import json
from datetime import datetime
from .lang_lists import country_to_country_code, country_code_to_country

# ##################################################################################################################

class SCC_Sort(object):
	def __init__(self, content_provider):
		self.lang_list = content_provider.get_dubbed_lang_list()[:]
		if 'en' not in self.lang_list:
			self.lang_list.append('en')
		self._ = content_provider._

	def title(self, desc=False):
		ll = [l for l in self.lang_list]
		ll.extend(['_', '_', '_'])

		# - SCC api doesn't have api to properly sort by title - unbelievable!
		# - the next problem is, that there is a mess in SCC database, so we need to be creative here
		# - this search script gets as params lang list sorted by lang priority - ex. ['cs', 'sk', 'en'] (max. list length is hardcoded to 3 - more langs are ignored)
		# - it will get title field from i18n_info_labels for each lang, then it checks if there is at least one ascii char in title and when yes, then it uses it as sort source
		# - previous step doesn't return any result (yes, that happens too ...), then info_labels.originaltitle is used

		sort_config = [{
			"_script": {
				"type": "string",
				"script": {
					"source": "boolean hpa(String x){if(x!=null){for(int i=0;i<x.length();i++){char c=x.charAt(i);if((c>=48&&c<=57)||(c>=65&&c<=90)||(c>=97&&c<=122)){return true;}}}return false;}def a=null,b=null,c=null;for(l in params['_source']['i18n_info_labels']){if(l['lang']=='%s'&&hpa(l['title']))a=l['title'];if(l['lang']=='%s'&&hpa(l['title']))b=l['title'];if(l['lang']=='%s'&&hpa(l['title']))c=l['title'];}def d=params['_source']['info_labels']['originaltitle'];return a!=null?a:b!=null?b:c!=null?c:d!=null?d:'';" % (ll[0], ll[1], ll[2]),
				},
				"order": "desc" if desc else "asc",
			}
		}]

		return json.dumps(sort_config)

	@staticmethod
	def _simple_sort(field, desc=False):
		sort_config = [{
			field: {
				"order": "desc" if desc else "asc",
			}
		}]
		return json.dumps(sort_config)

	@staticmethod
	def year(desc=False):
		return SCC_Sort._simple_sort("info_labels.year", desc)

	@staticmethod
	def play_count(desc=False):
		return SCC_Sort._simple_sort("play_count", desc)

	@staticmethod
	def date_added(desc=False):
		return SCC_Sort._simple_sort("info_labels.dateadded", desc)

	@staticmethod
	def premiered(desc=False):
		return SCC_Sort._simple_sort("info_labels.premiered", desc)

	@staticmethod
	def popularity(desc=False):
		return SCC_Sort._simple_sort("popularity", desc)

	@staticmethod
	def trending(desc=False):
		return SCC_Sort._simple_sort("trending", desc)

	@staticmethod
	def rating(desc=False):
		return SCC_Sort._simple_sort("ratings.overall.rating", desc)

	@staticmethod
	def rating_csfd(desc=False):
		return SCC_Sort._simple_sort("ratings.csfd.rating", desc)

	@staticmethod
	def rating_tmdb(desc=False):
		return SCC_Sort._simple_sort("ratings.tmdb.rating", desc)

	@staticmethod
	def rating_imdb(desc=False):
		return SCC_Sort._simple_sort("ratings.imdb.rating", desc)

	@staticmethod
	def rating_tvdb(desc=False):
		return SCC_Sort._simple_sort("ratings.tvdb.rating", desc)

	@staticmethod
	def rating_metacritic(desc=False):
		return SCC_Sort._simple_sort("ratings.Metacritic.rating", desc)

	@staticmethod
	def rating_rotten_tomatoes(desc=False):
		return SCC_Sort._simple_sort("ratings.Rotten Tomatoes.rating", desc)

	def get_sort_list(self):
		return [
			(self.title, self._("Title"),),
			(self.year, self._("Year"),),
			(self.play_count, self._("Play count"),),
			(self.date_added, self._("Date added"),),
			(self.premiered, self._("Premiered"),),
			(self.popularity, self._("Popularity"),),
			(self.trending, self._("Trending"),),
			(self.rating, self._("Rating overall"),),

			(self.rating_csfd, self._("Rating CSFD"),),
			(self.rating_tmdb, self._("Rating TMDB"),),
			(self.rating_imdb, self._("Rating IMDB"),),
			(self.rating_tvdb, self._("Rating TVDB"),),
			(self.rating_metacritic, self._("Rating Metacritic"),),
			(self.rating_rotten_tomatoes, self._("Rating Rotten Tomatoes"),),
		]

	def sort_method_by_name(self, name):
		return {
			'year': self.year,
			'trending': self.trending,
			'popularity': self.popularity,
			'playCount': self.play_count,
			'dateAdded': self.date_added,
			'langDateAdded': self.date_added,
			'lastChildPremiered': self.premiered,

			"_script": self.title,
			"info_labels.year": self.year,
			"play_count": self.play_count,
			"info_labels.dateadded": self.date_added,
			"info_labels.premiered": self.premiered,
			"popularity": self.popularity,
			"trending": self.trending,
			"ratings.overall.rating": self.rating,
			"ratings.csfd.rating": self.rating_csfd,
			"ratings.tmdb.rating": self.rating_tmdb,
			"ratings.imdb.rating": self.rating_imdb,
			"ratings.tvdb.rating": self.rating_tvdb,
			"ratings.Metacritic.rating": self.rating_metacritic,
			"ratings.Rotten Tomatoes.rating": self.rating_rotten_tomatoes
		}.get(name, self.date_added)

# ##################################################################################################################

class SCC_Query(object):
	def __init__(self, content_provider):
		self.lang_list = content_provider.get_dubbed_lang_list()
		self.cp = content_provider
		self._ = content_provider._

	@staticmethod
	def parse_filter_query(filter_name, params):
		ret = {}

		if filter_name == 'custom':
			# we support only queries, that we have been builded - other queries will not work
			configSort = json.loads(params['sortConfig'])
			sort_name = list(configSort[0].keys())[0]

			ret['of'] = sort_name
			ret['od'] = configSort[0][sort_name]['order']

			config = json.loads(params['config'])

			must = config.get('bool',{}).get('must', [])
			must_not = config.get('bool',{}).get('must_not', [])

			for item in must:
				term_item = item.get('term')
				range_item = item.get('range')
				bool_item = item.get('bool')
				query_string_item = item.get('query_string')

				if term_item:
					if 'info_labels.mediatype' in term_item:
						ret['type'] = term_item['info_labels.mediatype']
					elif 'streams_format_info.hdr' in term_item:
							ret['HDR'] = 1 if term_item['streams_format_info.hdr'] else 0
					elif 'info_labels.genre' in term_item:
						if 'mu' not in ret:
							ret['mu'] = []

						ret['mu'].append(term_item['info_labels.genre'])
					elif 'info_labels.studio' in term_item:
						ret['s'] = term_item['info_labels.studio']
					elif 'languages' in term_item:
						ret['l'] = term_item['languages']
					elif 'info_labels.year' in term_item:
						ret['y'] = '={}'.format(term_item['info_labels.year'])

				elif range_item:
					if 'info_labels.year' in range_item:
						for k,v in range_item['info_labels.year'].items():
							sign_str = {
									'lte': '<=',
									'lt':  '<',
									'gte': '>=',
									'gt':  '>',
									'eq':  '=',
								}.get(k, '=')
							ret['y'] = '{}{}'.format(sign_str, v)
					elif 'ratings.overall.rating' in range_item:
						ret['r'] = range_item['ratings.overall.rating']['gte']
					elif 'stream_info.video.height' in range_item:
						ret['q'] = range_item['stream_info.video.height']['gt']

				elif bool_item:
					for should_item in bool_item.get('should', []):
						term_item2 = should_item.get('term',{})
						if 'available_streams.languages.audio.map' in term_item2:
							ret['dub'] = 1
						elif 'available_streams.languages.subtitles.map' in term_item2:
							ret['tit'] = 1
						elif 'info_labels.country' in term_item2:
							if 'co' not in ret:
								ret['co'] = []

							country = term_item2['info_labels.country']
							if len(country) == 2:
								country = country_code_to_country.get(country.lower(), country)

							if country not in ret['co']:
								ret['co'].append(country)
				elif query_string_item:
					if query_string_item.get('type') == 'phrase_prefix':
						ret['sws'] = query_string_item['query'][:-1]

			for item in must_not:
				term_item = item.get('term')
				bool_item = item.get('bool')

				if term_item:
					if 'info_labels.genre' in term_item:
						if 'nmu' not in ret:
							ret['nmu'] = []

						ret['nmu'].append(term_item['info_labels.genre'])

				if bool_item:
					for should_item in bool_item.get('should', []):
						term_item2 = should_item.get('term',{})
						if 'info_labels.country' in term_item2:
							if 'nco' not in ret:
								ret['nco'] = []

							country = term_item2['info_labels.country']
							if len(country) == 2:
								country = country_code_to_country.get(country.lower(), country)

							if country not in ret['nco']:
								ret['nco'].append(country)

		else:
			# classic query

			if 'order' in params:
				ret['od'] = params['order']

			if 'sort' in params:
				ret['of'] = params['sort']

			if 'type' in params:
				ret['type'] = params['type']

			if 'days' in params:
				ret['y'] = '>={:d}'.format( datetime.now().year - int(round(params['days'] / 365)))

			if filter_name == 'newsDubbed':
				ret['dub'] = 1
			elif filter_name == 'newsSubs':
				ret['tit'] = 1
			elif filter_name == 'genre':
				ret['mu'] = [params['value']]
			elif filter_name == 'country':
				ret['co'] = [params['value']]
			elif filter_name == 'year':
				ret['y'] = '=' + params['value']
			elif filter_name == 'studio':
				ret['s'] = params['value']
			elif filter_name == 'language':
				ret['l'] = params['value']
			elif filter_name == 'startsWithSimple':
				ret['sws'] = params['value']

		return ret


	@staticmethod
	def media_type(media_type):
		if media_type:
			return {
				'term': {
					'info_labels.mediatype': media_type
				}
			}
		else:
			return {}

	@staticmethod
	def year(sign, year):
		sign_str = {
				'<=': 'lte',
				'<':  'lt',
				'>=': 'gte',
				'>':  'gt',
				'=':  'eq',
			}.get(sign, 'eq')

		if sign_str == 'eq':
			return {
				'term': {
					'info_labels.year': year
				}
			}
		else:
			return {
				'range': {
					'info_labels.year': {
						sign_str: year
					}
				}
			}

	def dub(self):
		config = {
			'bool': {
				'must': [],
				'must_not': [],
				'should': [],
				"minimum_should_match": 0,
				"boost": 1.0
			}
		}

		for l in self.lang_list:
			config['bool']['should'].append(
				{
					'term': {
						'available_streams.languages.audio.map': l
					}
				},
			)
		return config

	def tit(self):
		config = {
			'bool': {
				'must': [],
				'must_not': [],
				'should': [],
				"minimum_should_match": 0,
				"boost": 1.0
			}
		}

		for l in self.lang_list:
			config['bool']['should'].append(
				{
					'term': {
						'available_streams.languages.subtitles.map': l
					}
				},
			)
		return config

	@staticmethod
	def genre(genre):
		return {
			'term': {
				'info_labels.genre': genre
			}
		}

	@staticmethod
	def country(country):
		return {
			'bool': {
				'must': [],
				'must_not': [],
				'should': [
					{
						'term': {
							'info_labels.country': country
						}
					},
					{
						'term': {
							'info_labels.country': country_to_country_code.get(country, '').upper()
						}
					},
				],
				"minimum_should_match": 0,
				"boost": 1.0
			}
		}

	@staticmethod
	def rating(rating):
		return {
			'range': {
				'ratings.overall.rating': {
					'gte': (rating // 10)
				}
			}
		}

	@staticmethod
	def quality(quality):
		return {
			'range': {
				'stream_info.video.height': {
					'gt': quality,
				}
			}
		}

	@staticmethod
	def hdr():
		return {
			'term': {
				'streams_format_info.hdr': True
			}
		}

	@staticmethod
	def language(language):
		return {
			'term': {
				'languages': language
			}
		}

	@staticmethod
	def studio(studio):
		return {
			'term': {
				'info_labels.studio': studio
			}
		}

	@staticmethod
	def startswith(s):
		return {
			'query_string': {
				'type': "phrase_prefix",
				'fields': [
					"i18n_info_labels.title",
				],
				"query": s + '*'
			}
		}

	@staticmethod
	def build_query(must, must_not):
		config = {
			"bool": {
				"must": [x for x in must if x],
				"must_not": [x for x in must_not if x],
				"should": [],
				"minimum_should_match": 0,
				"boost": 1.0
			}
		}
		return json.dumps(config)


# ##################################################################################################################
