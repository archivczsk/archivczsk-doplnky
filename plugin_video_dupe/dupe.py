# -*- coding: utf-8 -*-

import os, re
from tools_archivczsk.contentprovider.exception import AddonErrorException, LoginException
from tools_archivczsk.string_utils import strip_accents
from tools_archivczsk.parser.js import get_js_data
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.compat import urlparse, parse_qs, quote, urljoin, urlunparse
from .stream_provider import StreamProvider
import pickle

def dump_html_response(name, response):
	with open('/tmp/' + name + '.html', 'wb') as f:
		f.write(response.content)

# ##################################################################################################################

class Dupe(object):
	def __init__(self, content_provider):
		self.cp = content_provider

		self.user = None
		self.password = None
		self.req_session = self.cp.get_requests_session()
		self.beautifulsoup = self.cp.get_beautifulsoup()
		self.stream_provider = StreamProvider(content_provider)

		self.categories_loaded = False
		self.genres = []
		self.movie_categories = []
		self.series_categories = []

	# ##################################################################################################################

	def load_cookies(self):
		ret = False
		try:
			if self.cp.load_cached_data('login').get('checksum') == self.cp.get_settings_checksum(('username', 'password',)):
				with open(os.path.join(self.cp.data_dir, 'cookies.dat'), 'rb') as f:
					self.req_session.cookies.update(pickle.load(f))

				self.cp.log_info("Cookies loaded from cache")
				ret = True
		except:
			pass

		return ret

	# ##################################################################################################################

	def save_cookies(self):
		try:
			with open(os.path.join(self.cp.data_dir, 'cookies.dat'), 'wb') as f:
				pickle.dump(self.req_session.cookies, f)

			self.cp.save_cached_data('login', {'checksum': self.cp.get_settings_checksum(('username', 'password',))})
			self.cp.log_info("Cookies saved to cache")
		except:
			pass

	# ##################################################################################################################

	def call_api(self, url, params=None, data=None, raw=False, allow_redirects=True):
		url = urljoin('https://dupe.cz/', url)

		if data:
			response = self.req_session.post(url=url, params=params, data=data, allow_redirects=allow_redirects)
		else:
			response = self.req_session.get(url=url, params=params, allow_redirects=allow_redirects)

#		dump_json_request(response)

		if raw:
			return response

		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return self.beautifulsoup(response.content, 'html.parser')

	# ##################################################################################################################

	def login(self):
		user = self.cp.get_setting("username")
		password = self.cp.get_setting("password")

		if not user or not password:
			self.user = None
			self.password = None
			self.req_session.cookies.clear()
			self.cp.log_debug("No username or password provided - can't login")
			return False

		if user == self.user and password == self.password:
			self.cp.log_debug("User is already logged in")
			return True

		if self.load_cookies() and self.check_login():
			self.user = user
			self.password = password
			self.cp.log_info("Login data loaded from cache and valid")
			return True

		data = {
			"log": user,
			"pwd": password,
			'rememberme': 'forever',
			'wp-submit': 'Přihlásit se',
			'redirect_to': '/prihlaseni/?login_success=1',
			'wpv_login_form': 'on'
		}

		# load cookies
		self.cp.log_debug("Starting login procedure")
		self.req_session.cookies.clear()
		self.call_api('prihlaseni', raw=True)

		self.cp.log_debug("Sending login request")
		response = self.call_api('wp-login.php', data=data, raw=True)

		if response.status_code != 200:
			self.cp.log_error("Login failed with code %d" % response.status_code)
			raise LoginException(self.cp._("Login failed with response code {code}".format(code=response.status_code)))

		if not self.check_login():
			raise LoginException(self.cp._("Login failed - probably wrong username or password"))

		self.user = user
		self.password = password
		self.cp.log_info("Login successful")

		# save login cookies
		self.save_cookies()

		return True

	# ##################################################################################################################

	def check_login(self):
		soup = self.call_api('ucet')
		ret = soup.find('h1', class_='x-text-content-text-primary').get_text().strip() == 'Osobní Deník'

		if ret:
			self.cp.log_info("Login succesfully checked")
		else:
			self.cp.log_error("Login check failed - user is not logged in")

		return ret

	# ##################################################################################################################

	def is_logged_in(self):
		return self.user and self.password

	# ##################################################################################################################

	def load_categories(self):
		if self.categories_loaded:
			return

		soup = self.call_api('/')
		drop_down_menus = soup.find_all('ul', class_='sub-menu x-dropdown')

		menu = [x for x in drop_down_menus[0].find_all('a')]

		self.genres = [{'url': x['href'].split('?')[1], 'title': x.get_text()} for x in menu if '?zanr' in x['href']]
		self.movie_categories = [{'url': x['href'], 'title': x.get_text()} for x in menu if '/medaile/' in x['href']]

		menu = [x for x in drop_down_menus[2].find_all('a')]
		self.series_categories = [{'url': x['href'], 'title': x.get_text()} for x in menu if '/vyznamenani-serialu/' in x['href']]
		self.categories_loaded = True


	# ##################################################################################################################

	def get_genres(self):
		self.load_categories()
		return self.genres

	# ##################################################################################################################

	def get_movie_categories(self):
		self.load_categories()
		return self.movie_categories

	# ##################################################################################################################

	def get_series_categories(self):
		self.load_categories()
		return self.series_categories

	# ##################################################################################################################

	def get_movies(self, url='filmy/', page=1):
		if page > 1:
			u = urlparse(url)
			url = urlunparse( (u.scheme, u.netloc, u.path + 'page/{}'.format(page), u.params, u.query, u.fragment) )

		soup = self.call_api(url)
		div = soup.find('div', class_='x-row-inner')

		ret = []
		for a in div.find_all('a'):
			data = [x.get_text().strip() for x in a.find_all('div', class_='x-text')]
#			self.cp.log_debug("Movie data:\n%s" % data)

			year = data[0][4:]

			ret.append({
				'type': 'movie',
				'title': data[-1],
				'year': int(year) if year else None,
				'plot': data[-2],
				'img': a.find('img').get('src'),
				'url': a['href']
			})

		if soup.find('a', class_='next page-numbers') is not None:
			ret.append({
				'type': 'next'
			})

		return ret


	# ##################################################################################################################

	def get_series(self, url='serialy/', page=1):
		if page > 1:
			u = urlparse(url)
			url = urlunparse( (u.scheme, u.netloc, u.path + 'page/{}'.format(page), u.params, u.query, u.fragment) )

		soup = self.call_api(url)
		div = soup.find('div', class_='x-row-inner')

		ret = []
		for a in div.find_all('a'):
			data = [x.get_text().strip() for x in a.find_all('div', class_='x-text')]
#			self.cp.log_debug("Series data:\n%s" % data)

			year = data[0][6:]

			ret.append({
				'type': 'tvshow',
				'title': data[-1],
				'year': int(year) if year else None,
				'plot': data[-2],
				'img': a.find('img').get('src'),
				'url': a['href']
			})

		if soup.find('a', class_='next page-numbers') is not None:
			ret.append({
				'type': 'next'
			})

		return ret

	# ##################################################################################################################

	def get_episodes(self, url):
		soup = self.call_api(url)
#		dump_html_response('season_%s' % url.split('/')[-1], soup)

		def load_episodes(ep_div):
			name = None
			episodes = []
			for e in (ep_div or []):
				if e.name == 'label':
					name = e.get_text()
				elif e.name == 'div':
					episodes.append({
						'title': name,
						'streams': self.get_stream_providers(None, soup=e)
					})
			return episodes

		ret = []
		name = None
		for e in soup.find('div', class_='tabs'):
			if e.name == 'label':
				name = e.get_text()
			elif e.name == 'div':
				ep_list = load_episodes(e.find('div', class_='tabs'))

				if ep_list:
					ret.append({
						'title': name,
						'episodes': ep_list
					})

		return ret


	# ##################################################################################################################

	def get_stream_providers(self, url, soup=None):
		soup = soup or self.call_api(url)

		ret = []
		for a in soup.find_all('a'):
			if a['href'].startswith( ('https://dupe.cz/odkaz/', 'https://dupe.cz/odkaz-epizoda/',) ):
				data = [x.get_text() for x in a.find_all('span')]

				provider = data[1]
				if not self.stream_provider.is_supported(provider):
					self.cp.log_error("Unsupported stream provider: %s - ignoring" % provider)
					continue

				ret.append({
					'url': a['href'],
					'provider': provider,
					'quality': data[2] if len(data) > 2 else '',
					'lang': a.find('strong').get_text()
				})

		return ret

	# ##################################################################################################################

	def get_stream_info(self, provider_name, url):
		soup = self.call_api(url)
#		dump_html_response('get_stream_info' + provider_name, soup)

		self.cp.log_info("Searching for player URL for provider %s" % provider_name)

		if provider_name == 'SKTOR':
			# the simplest one ...
			return {
				'type': 'mp4',
				'url': (soup.find('video') or {}).get('src')
			}

		provider_url = (soup.find('iframe') or {}).get('src')
		if provider_url and provider_url.startswith('//'):
			provider_url = 'https:' + provider_url

		if not provider_url:
			self.cp.log_error("No player URL found for provider %s" % provider_name)
#			dump_html_response('get_stream_info_' + provider_name, self.call_api(url, raw=True))
			return {}

		stream_info = self.stream_provider.resolve(provider_name, provider_url)

		return stream_info

	# ##################################################################################################################

	def search(self, keyword):
		data = {
			'action': 'ajaxsearchpro_search',
			'aspp': keyword,
			'asid': 2,
			'asp_inst_id': '2_1',
			'options': 'filters_initial=1&filters_changed=0&qtranslate_lang=0'
		}

		soup = self.call_api('/wp-admin/admin-ajax.php', data=data)

		ret = []
		for item in soup.find_all('div', class_='asp_content'):
			asp_res_url = item.find('a', class_='asp_res_url')
			url = asp_res_url['href']

			item_type = urlparse(url).path.split('/')[1]

			if item_type in ('filmy', 'serialy'):
				text_div = item.find('div', class_='asp_res_text')
				orig_title = text_div.find('span').get_text().strip()

				title = asp_res_url.get_text().strip()
				title_type = asp_res_url.find('span').get_text().strip()
				title = title[:-len(title_type)-1].strip()

				try:
					year = title_type.split(' ')[1][:-1]
				except:
					year = None

				ret.append({
					'type': 'movie' if item_type == 'filmy' else 'tvshow',
					'title': title,
					'img': item.find('div', class_='asp_image')['data-src'],
					'plot': text_div.get_text().strip()[len(orig_title)+3:].strip(),
					'year': year,
					'url': url
				})

		return ret

	# ##################################################################################################################
