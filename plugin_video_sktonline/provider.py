# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.debug.http import dump_json_request
import requests
import re

try:
	from urllib import quote
except:
	from urllib.parse import quote

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
	'Referer': 'https://online.sktorrent.eu/',
}


class SkTContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'SkTonline', settings=settings, data_dir=data_dir)
		self.login_optional_settings_names = ('username', 'password')
		self.req_session = requests.Session()
		self.req_session.headers.update(COMMON_HEADERS)

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing with free account")
			return True

		cks = self.get_settings_checksum(('username', 'password',))
		data = self.load_cached_data('login')

		avs = data.get('session')

		if avs and data.get('checksum') and data['checksum'] == cks:
			self.log_debug("Session data found in cache")
			self.req_session.cookies.set('AVS', data['session'], domain='online.sktorrent.eu')
			if self.check_login():
				self.log_debug("Login check OK - continuing with loaded session")
				return True

		self.log_debug("Don't have login session - trying fresh login")

		# not logged yet or check login failed
		payload = {
			'username': self.get_setting('username'),
			'password': self.get_setting('password'),
			'submit_login':''
		}

		self.call_api('login', data=payload, raw_response=True)
		# check if login passed
		if not self.check_login():
			self.login_error("Prihlásenie zlyhalo - skontrolujte prihlasovacie meno a heslo")
			return False

		# get AVS cookie and store it
		data['session'] = self.req_session.cookies.get('AVS')

		if not data['session']:
			self.login_error("Nepodarilo sa vytvoriť prihlasovaciu session. Možno nastala zmena spôsobu prihásenia.")
			return False

		data['checksum'] = cks
		self.save_cached_data('login', data)
		self.log_debug("Login session authorized and stored")
		return True

	def check_login(self):
		response = self.call_api('user', raw_response=True)
		if response.url.endswith('/login'):
			return False
		else:
			return True

	def call_api(self, endpoint, params=None, data=None, raw_response=False):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://online.sktorrent.eu/' + endpoint

		headers = {
			'Accept-Encoding': 'identity',
		}
		
		if data:
			response = self.req_session.post(url, params=params, data=data, headers=headers)
		else:
			response = self.req_session.get(url, params=params, headers=headers)

		dump_json_request(response)

		if raw_response:
			return response

		if response.status_code == 200:
			return response.text
		else:
			raise AddonErrorException('HTTP reponse code: %d' % response.status_code)

	def search(self, keyword, search_id):
		return self.list_videos('search/videos?t=a&o=mr&type=public&search_query=' + quote(keyword))

	def root(self):
		self.add_search_dir('Vyhľadať')
		httpdata = self.call_api('categories')

		for link, img, name, count in re.compile('col-sm-6.*?href="(.*?)".*?class="thumb-overlay.*?img src="(.*?)".*?title="(.*?)".*?pull-right.*?span.*?>([0-9]*?)<', re.DOTALL).findall(httpdata):
			self.add_dir(name + " (" + count + ")", cmd=self.list_videos, url=link[1:] + "?t=a&o=mr&type=public")

	def list_videos(self, url):
		httpdata = self.call_api(url)

		for link, img, name, duration in re.compile('href=".*?/video/([0-9]*?)/.*?thumb-overlay.*?img src="(.*?)".*?title="(.*?)".*?duration">(.*?)<', re.DOTALL).findall(httpdata):
			info_labels = {
				'plot': duration.strip(),
			}
			name = decode_html(name)
			self.add_video(name, img, info_labels, cmd=self.resolve, name=name, url="video/" + link + "/")

		nextpage = re.compile('<a href="([^"]*?)" class="prevnext">&raquo;</a>', re.DOTALL).findall(httpdata)
		if nextpage and nextpage[0]:
			self.add_next(cmd=self.list_videos, url=nextpage[0])

	def resolve(self, name, url):
		httpdata = self.call_api(url)

		links = []
		for link, res in re.compile('source src="(.*?)".*?res=\'(.*?)\'', re.DOTALL).findall(httpdata):
			links.append((link, res,))

		settings = {
			'user-agent': COMMON_HEADERS['User-Agent'],
			'extra-headers': {
				'Referer': 'https://online.sktorrent.eu/',
			}
		}

		for link, res in sorted(links, key=lambda x: int(x[1]), reverse=True):
			info_labels = {
				'quality': str(res) + 'p'
			}
			self.add_play(name, link, info_labels, settings=settings)


