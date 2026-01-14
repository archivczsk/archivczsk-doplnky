# -*- coding: utf-8 -*-
import os
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, decode_html, strip_accents
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.compat import quote
import re

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
	'Referer': 'https://online.sktorrent.eu/',
}

class SkTContentProvider(CommonContentProvider):
	LOGIN_INFO_URL='https://t.ly/S3hh8'

	def __init__(self):
		CommonContentProvider.__init__(self, 'SkTonline')
		self.req_session = self.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.avs = None

	def load_avs(self):
		avs = None
		try:
			with open(os.path.join(self.data_dir, 'avs.txt'), "r") as f:
				avs = f.read().strip()
		except:
			# fallback for users, that have cached AVS when it was possible to get it using name/password
			avs = self.load_cached_data('login').get('session')

		return avs

	def check_login(self):
		avs = self.load_avs() or None

		if avs == self.avs:
			return

		self.req_session.cookies.clear()
		self.req_session.cookies.set('AVS', avs, domain='online.sktorrent.eu')

		response = self.call_api('user', raw_response=True)
		if response.url.endswith('/login'):
			self.req_session.cookies.clear()
			self.avs = None
			self.show_error(self._('Login with provided AVS cookie failed. Visit {url} for instructions how to provide valid login cookie.').format(url=self.LOGIN_INFO_URL), noexit=True)
		else:
			self.avs = avs

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

#		dump_json_request(response)

		if raw_response:
			return response

		if response.status_code == 200:
			return response.text
		else:
			raise AddonErrorException(self._('HTTP reponse code') + ': %d' % response.status_code)

	def search(self, keyword, search_id):
		keyword = strip_accents(keyword)
		return self.list_videos('search/videos?t=a&o=mr&type=public&search_query=' + quote(keyword))

	def root(self):
		self.check_login()
		self.add_search_dir()
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

		if len(links) == 0 and not self.avs:
			self.show_info(self._("For starting playback you need to set valid AVS cookie. Visit {url} for instructions how to do so.").format(url=self.LOGIN_INFO_URL))
			return

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
