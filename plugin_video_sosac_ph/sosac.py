# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.exception import AddonErrorException, AddonInfoException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache
from collections import OrderedDict

try:
	from urllib import urlencode
except:
	from urllib.parse import urlencode

from hashlib import md5
from datetime import datetime

# ##################################################################################################################

class Sosac(object):
	PAGE_SIZE = 100

	CFG_ADDRESS = [
		"https://kodi-api.sosac.to/settings",
		"https://tv.sosac.ph/settings.json",
		"https://sosac.eu/settings.json",
    	"https://tv.prehraj.net/settings.json",
		"https://tv.pustsi.me/settings.json",
		"https://www.tvserialy.net/settings.json",
        "http://178.17.171.217/settings.json"
	]

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.configuration = {}
		self.cache = ExpiringLRUCache(30, 1800)
		self.username = None
		self.password = None
		self.streaming_username = None
		self.streaming_password = None
		self.login_checksum = None
		self.streaming_checksum = None

	# ##################################################################################################################

	def _(self, s):
		return self.cp._(s)

	# ##################################################################################################################

	def request_configuration(self):
		cfg = None

		for addr in self.CFG_ADDRESS:
			try:
				resp = self.req_session.get(addr)
				resp.raise_for_status()

				cfg = resp.json()
				if cfg['domain'] and cfg['streaming_provider']:
					self.configuration = cfg
					break
			except:
				self.cp.log_exception()

		if cfg:
			self.api_address = 'http%s://%s/' % ('s' if self.cp.get_setting('use_https') else '', cfg['domain'])
			self.api_label = cfg['domain_label']
			self.streaming_address = 'http%s://%s/' % ('s' if self.cp.get_setting('use_https') else '', cfg['streaming_provider'])
			self.streaming_label = cfg['streaming_provider_label']
			self.news = (self._("News from {sosac_label}").format(sosac_label=self.api_label) + ':\n' + cfg['news']) if cfg.get('news') else None
		else:
			raise AddonErrorException(self._("Failed to load configuration from remote server. Check your internet connection."))

	# ##################################################################################################################

	def check_login_change(self):
		login_checksum = self.login_checksum
		msg = self.check_login()

		if login_checksum != self.login_checksum:
			self.cp.login_msg = msg
			if msg:
				self.cp.show_info(msg, noexit=True)

	# ##################################################################################################################

	def check_login(self):
		self.cp.log_debug("Checking user login status")
		login_checksum = self.cp.get_settings_checksum( ('sosac_user', 'sosac_pass',) )

		if self.login_checksum == login_checksum:
			self.cp.log_debug("Check login result: login status already checked")
			return None

		username = self.cp.get_setting('sosac_user')
		password = self.cp.get_setting('sosac_pass')
		archivczsk_help='archivczsk.' + self.api_label.lower()
		self.login_checksum = login_checksum

		if not username or not password:
			self.username = None
			self.password = None
			self.login_checksum = None
			self.cp.log_debug("Check login result: no username or password provided")
			return self._("No sosac login credentials are set in addon settings. Create a free registration on {sosac_label} and enter login details in addon's settings to enable all functionality. More info on {archivczsk_help}.").format(sosac_label=self.api_label, archivczsk_help=archivczsk_help)

		self.username = username
		self.password = md5((md5(('%s:%s' % (username, password)).encode('utf-8')).hexdigest() + 'EWs5yVD4QF2sshGm22EWVa').encode('utf-8')).hexdigest()

		try:
			resp = self.call_api('movies/lists/queue', params = {'pocet': 1, 'stranka': 1}, ignore_status_code=True, check_login=False)
		except:
			self.cp.log_debug("Check login result: movies/lists/queue raised exception")
			self.username = None
			self.password = None
			raise

		if isinstance(resp, dict) and resp.get('code') == 401:
			self.cp.log_debug("Check login result: movies/lists/queue returned 401")
			self.username = None
			self.password = None

			return self._('Login name/password for sosac are wrong. Only base functionality will be available. More info on {archivczsk_help}.').format(archivczsk_help=archivczsk_help)

		self.cp.log_debug("Check login result: username/password combination is correct")

		return None

	# ##################################################################################################################

	def reset_streaming_login(self):
		self.streaming_password = None

	# ##################################################################################################################

	def check_streaming_login(self, silent=False):
		streaming_checksum = self.cp.get_settings_checksum( ('streamujtv_user', 'streamujtv_pass',) )

		if self.streaming_password and self.streaming_checksum == streaming_checksum:
			return

		username = self.cp.get_setting('streamujtv_user')
		password = self.cp.get_setting('streamujtv_pass')

		if not username or not password:
			if not silent:
				self.cp.show_info(self._('No {streaming_label} login credentials are set in addon settings. In order to play content you need to have a valid {streaming_label} subscription and login credentials need to be set in addon settings.').format(streaming_label=self.streaming_label), noexit=True)
			return

		self.streaming_username = username
		self.streaming_password = md5(password.encode('utf-8')).hexdigest()
		self.streaming_checksum = streaming_checksum

		try:
			resp = self.call_streaming_api('check-user')
		except:
			self.streaming_username = None
			self.streaming_password = None
			raise

		if resp.get('result') == 0:
			self.streaming_username = None
			self.streaming_password = None
			self.cp.set_setting('streamujtv_exp', '')

			if not silent:
				self.cp.show_info(self._('Login name/password for {streaming_label} are wrong.').format(streaming_label=self.streaming_label), noexit=True)
		elif resp.get('result') == 1:
			self.streaming_username = None
			self.streaming_password = None
			self.cp.set_setting('streamujtv_exp', 'expired')

			if not silent:
				self.cp.show_info(self._("You don't have valid premium subscription for {streaming_label}.").format(streaming_label=self.streaming_label), noexit=True)
		elif resp.get('result') == 2:
			self.cp.log_info("Premium subscription for streamuj.tv is valid.")
			self.cp.set_setting('streamujtv_exp', resp.get('expiration', '?'))
		else:
			self.cp.log_error("Unsupported return data returned from server: %s" % str(resp))

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, ignore_status_code=False, use_cache=True, check_login=True):
		if check_login:
			self.check_login_change()

		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = self.api_address + endpoint

		default_params = {}

		if self.password:
			default_params.update({
				'username': self.username,
				'password': self.password
			})

		if params:
			default_params.update(params)

		headers = {
			'User-Agent': 'ArchivCZSK/%s (plugin.video.sosac/%s)' % (self.cp.get_engine_version(), self.cp.get_addon_version()),
		}

		if data != None:
			resp = self.req_session.post(url, json=data, params=default_params, headers=headers)
		else:
			rurl = url + '?' + urlencode(sorted(default_params.items(), key=lambda val: val[0]))

			if use_cache:
				resp = self.cache.get(rurl)
				if resp:
					self.cp.log_debug("Request found in cache")
					return resp

			resp = self.req_session.get(url, params=default_params, headers=headers)
#		dump_json_request(resp)

		if resp.status_code == 200 or ignore_status_code:
			resp = resp.json()

			if use_cache and data == None:
				self.cache.put(rurl, resp, 3600)

			return resp
		else:
			self.cp.log_error("Remote server returned status code %d" % resp.status_code)

			if resp.status_code == 401:
				raise AddonInfoException(self._("You don't have access to this content! Set correct login username and password for sosac in addon's settings to enable all functionality."))
			else:
				raise AddonErrorException(self._("Unexpected return code from server") + ": %d" % resp.status_code)

	# ##################################################################################################################

	def make_paging_params(self, page):
		if page is not None:
			return {
				'pocet': self.PAGE_SIZE,
				'stranka': page
			}
		else:
			return {}

	# ##################################################################################################################

	def next_page_available(self, result):
		# ugly workaround - server sometimes doesn't return full page size
		if len(result) > (self.PAGE_SIZE - 10):
			return True

		return False

	# ##################################################################################################################

	def convert_rating(self, item):
		ret = OrderedDict()

		def _set_rating(name, key):
			if item.get(key):
				rating = [item[key]]

				if item.get(key + 'p'):
					n = item[key + 'p']
					if n > 1000000:
						n = '%.1f M' % (n / 1000000.0)
					elif n > 1000:
						n = '%.1f k' % (n / 1000.0)
					rating.append(' (%s)' % n)

				ret[name] = rating

		_set_rating('CSFD', 'c')
		_set_rating('IMDB', 'm')

		return ret

	# ##################################################################################################################

	def convert_movie_item(self, item, parent_item={}):
		ret = {
			'id': item['_id'],
			'parent_id': item.get('id') or parent_item.get('id'),
			'title': item['n'] or {'en': ['! Not provided'], 'cs': ['! Neuvedeno']},
			'ep_title': item.get('ne'),
			'img': item['i'],
			'rating': self.convert_rating(item),
			'plot': item['p'],
			'duration': item.get('dl'),
			'year': int(item['y']) if item.get('y') else None,
			'genre': item.get('g') or [],
			'lang': item['d'],
			'stream_id': item.get('l'),
			'watched': item.get('w') if self.password else 0,
			'adult': u'Erotické' in (item.get('g') or []),
			'season': item.get('s'),
			'episode': item.get('ep'),
		}

		if parent_item and not ret['ep_title']:
			ret['ep_title'] = ret['title']
			ret['title'] = parent_item['title']

		return ret

	# ##################################################################################################################

	def get_movies_list(self, stream, page, letter=None, genre=None, year=None, quality=None):
		result = []

		params = self.make_paging_params(page)

		if letter is not None:
			params.update({'l': letter})

		if genre is not None:
			params.update({'g': genre})

		if year is not None:
			params.update({'y': year})

		if quality is not None:
			params.update({'q': quality})


		for item in self.call_api('movies/lists/' + stream, params=params, use_cache=(stream not in ('queue', 'unfinished', 'finished'))):
			result.append(self.convert_movie_item(item))

		return result

	# ##################################################################################################################

	def get_tvshow_list(self, stream, page, letter=None, genre=None, year=None):
		result = []

		params = self.make_paging_params(page)

		if letter is not None:
			params.update({'l': letter})

		if genre is not None:
			params.update({'g': genre})

		if year is not None:
			params.update({'y': year})

		for item in self.call_api('serials/lists/' + stream, params=params, use_cache=(stream not in ('queue', 'unfinished', 'finished'))):
			result.append(self.convert_movie_item(item))

		return result

	# ##################################################################################################################

	def get_episodes_list(self, stream, page, date_from=None, date_to=None):
		result = []

		params = self.make_paging_params(page)

		if date_from is not None:
			params.update({'f': date_from})

		if date_to is not None:
			params.update({'t': date_to})

		for item in self.call_api('episodes/lists/' + stream, params=params, use_cache=(stream not in ('queue', 'unfinished', 'finished'))):
			result.append(self.convert_movie_item(item))

		return result

	# ##################################################################################################################

	def get_tvshow_detail(self, item):
		result = []

		for season_name, season_data in self.call_api('serials/' + str(item['id'])).items():
			if season_name == 'info':
				continue

			episodes = []
			result.append({
				'season': int(season_name),
				'episodes': episodes
			})

			for episode_name, episode_data in sorted(season_data.items(), key=lambda i: int(i[0])):
				movie_item = self.convert_movie_item(episode_data, item)
				movie_item['episode'] = int(episode_name)
				movie_item['season'] = int(season_name)
				episodes.append(movie_item)

			episodes.sort(key=lambda i: i['episode'])

		return sorted(result, key=lambda i: i['season'])

	# ##################################################################################################################

	def search_simple(self, category, keyword, page):
		result = []

		params = self.make_paging_params(page)

		params.update({'q': keyword})

		for item in self.call_api(category + '/simple-search', params=params):
			result.append(self.convert_movie_item(item))

		return result

	# ##################################################################################################################

	def search_advanced(self, category, search_params, page):
		result = []

		params = self.make_paging_params(page)

		params.update({
			'k': search_params.get('keyword'),
			'y': '%s,%s' % (search_params.get('year_from',1900), search_params.get('year_to', datetime.now().year)),
			'g': search_params.get('genre'),
			'q': search_params.get('quality'),
			'c': search_params.get('origin'),
			'l': search_params.get('lang'),
			'd': search_params.get('director'),
			's': search_params.get('screenwriter'),
			'a': search_params.get('actor'),
			'o': search_params.get('sort'),
		})

		for item in self.call_api(category + '/advanced-search', params=params):
			result.append(self.convert_movie_item(item))

		return result

	# ##################################################################################################################

	def get_tvguide(self, day, page):
		result = []

		params = self.make_paging_params(page)

		params.update({'d': day})

		for item in self.call_api('tv/program', params=params):
			if item.get('movie'):
				media_item = item['movie']
				media_type = 'movie'
			elif item.get('episode'):
				media_item = item['episode']
				media_type = 'episode'
			elif item.get('serial'):
				media_item = item['serial']
				media_type = 'tvshow'
			else:
				# workaround for empty data - without that paging will not work
				media_type = 'dummy'
				media_item = {}

			if media_item:
				ritem = self.convert_movie_item(media_item)
			else:
				ritem = {}

			ritem.update({
				'channel': {
					'name': item['stanice'],
					'start': int(item['start'])
				},
				'type': media_type
			})
			result.append(ritem)

		return result

	# ##################################################################################################################

	def call_streaming_api(self, action, params=None):
		url = self.streaming_address + 'json_api_player.php'

		default_params = {
			'action': action
		}

		if self.streaming_password:
			default_params.update({
				'login': self.streaming_username,
				'password': self.streaming_password,
				'passwordinmd5': 1
			})

		if params:
			default_params.update(params)

		headers = {
			'User-Agent': 'ArchivCZSK/%s (plugin.video.sosac/%s)' % (self.cp.get_engine_version(), self.cp.get_addon_version()),
		}

		resp = self.req_session.get(url, params=default_params, headers=headers)
#		dump_json_request(resp)

		if resp.status_code == 200:
			return resp.json()
		else:
			self.cp.log_error("Remote server returned status code %d" % resp.status_code)

			if resp.status_code == 401:
				raise AddonInfoException(self._("You don't have access to this content!"))
			else:
				raise AddonErrorException(self._("Unexpected return code from server") + ": %d" % resp.status_code)

	# ##################################################################################################################

	def get_streams(self, item_id):
		qual_dict = {"UHD":"2160p","FHD":"1080p","HD":"720p","SD":"480p"}

		self.check_streaming_login()

		location = self.cp.get_setting('streamujtv_location')

		params = {
			'link': item_id,
			'location': 1 if location == '0' else location,
			'd': 15 # client type identification
		}

		result = self.call_streaming_api('get-video-links', params)

		if result.get('errormessage'):
			if result.get('result') == 0:
				raise AddonErrorException(result['errormessage'])
			else:
				self.cp.show_info(result['errormessage'], noexit=True)

		ret = []

		for lang, data in result.get('URL',{}).items():
			for quality, url in data.items():
				if quality == 'subtitles':
					continue

				ret.append({
					'url': url,
					'quality': quality,
					'resolution': qual_dict.get(quality, 'unknown'),
					'lang': lang.upper(),
					'sub_lang': None,
					'sub_url': None
				})

				for sub_lang, sub_url in data.get('subtitles', {}).items():
					ret.append({
						'url': url,
						'quality': quality,
						'resolution': qual_dict.get(quality, 'unknown'),
						'lang': lang.upper(),
						'sub_lang': sub_lang.upper(),
						'sub_url': sub_url
					})

		return ret

	# ##################################################################################################################

	def watchlist_add(self, category, item_id):
		if self.password:
			return self.call_api('%s/%s/into-queue' % (category, item_id), data={})
		else:
			return None

	# ##################################################################################################################

	def watchlist_delete(self, category, item_id):
		if self.password:
			return self.call_api('%s/%s/off-queue' % (category, item_id), data={}, ignore_status_code=True)
		else:
			return None

	# ##################################################################################################################

	def set_watching_time(self, category, item_id, seconds):
		if self.password:
			params = {
				'd': 15 # client type identification
			}

			data = {
				'time': seconds
			}
			return self.call_api('%s/%s/watching-time' % (category, item_id), params=params, data=data)
		else:
			return None

	# ##################################################################################################################
