# -*- coding: utf-8 -*-

import re
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import strip_accents
from tools_archivczsk.parser.js import get_js_data
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.compat import urlparse, parse_qs


try:
	from bs4 import BeautifulSoup
except:
	BeautifulSoup = None

try:
	from urllib import quote
except:
	from urllib.parse import quote

# ##################################################################################################################

class PrehrajTo(object):
	def __init__(self, content_provider):
		self.cp = content_provider

		self.user = None
		self.password = None
		self.is_premium = False
		self.req_session = self.cp.get_requests_session()

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, raw=False, allow_redirects=True):
		if not endpoint.startswith('http'):
			endpoint = 'https://prehraj.to/' + endpoint

		if data:
			response = self.req_session.post(url=endpoint, params=params, data=data, allow_redirects=allow_redirects)
		else:
			response = self.req_session.get(url=endpoint, params=params, allow_redirects=allow_redirects)

#		dump_json_request(response)

		if raw:
			return response

		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return BeautifulSoup(response.content, 'html.parser')

	# ##################################################################################################################

	def login(self):
		user = self.cp.get_setting("username")
		password = self.cp.get_setting("password")

		if not user or not password:
			self.is_premium = False
			return False

		if user == self.user and password == self.password:
			return True

		data = {
			"email": user,
			"password": password,
			'_do': 'homepageLoginForm-loginForm-submit',
			'login': 'Přihlásit+se'
		}

		params={
			'frm': 'homepageLoginForm-loginForm'
		}

		# load cookies
		self.call_api('', raw=True)
		response = self.call_api('', data=data, params=params, raw=True)

		try:
			if parse_qs(urlparse(response.url).query).get('afterLogin',['0'])[0] == '1':
				# login OK - check premium
				if self.check_premium():
					self.cp.log_info("Prehraj.to premium account activated")
					self.is_premium = True
				else:
					self.cp.log_error("Prehraj.to premium account is inactive")
					self.is_premium = False
			else:
				self.cp.log_error("Prehraj.to login failed - wrong username/password or login procedure has been changed")
				self.is_premium = False
		except:
			self.cp.log_error("Login procedure crashed")
			self.cp.log_exception()
			self.is_premium = False

		self.user = user
		self.password = password

		return self.is_premium

	# ##################################################################################################################

	def check_premium(self):
		response = self.call_api('profil', raw=True)

		if urlparse(response.url).path == '/':
			self.cp.log_error("Failed to load user profile")
			# wrong login
			return False

		soup = BeautifulSoup(response.content, 'html.parser')
		for div in soup.find_all('div', {'class': 'section__content section__content--border'}):
			p = div.find('p', {'class': 'text-medium margin-bottom-0'})
			if p != None and 'PREMIUM' in p.get_text():
				premium_text = div.find('div', {'class': 'cell small-6 text-right'}).find('p', {'class': 'text-medium margin-bottom-0'}).get_text().strip()
				if premium_text.startswith("Vyprší za"):
					self.cp.log_info("Premium status: %s" % premium_text)
					return True

		return False

	# ##################################################################################################################

	def search(self, keyword, limit=100, page=1):
		if BeautifulSoup == None:
			return [], None

		if not keyword:
			return [], None

		next_page = None
		videos = []

		keyword = strip_accents(keyword)

		while True:
			soup = self.call_api('hledej/' + quote(keyword.encode('utf-8')), params={'videoListing-visualPaginator-page': page})

			for item in soup.find_all('div', attrs={'class': 'video__picture--container'}):
				title_and_link = item.find('a', attrs={'class': 'video video--small video--link'})
				size = item.find('div', attrs={'class': 'video__tag video__tag--size'}) or item.find('div', attrs={'class': 'video__tag video__tag--size video__tag--size-alone'})
				img = item.find('img', attrs={'data-next': '2'})
#				time = soup.find('div', attrs={'class': 'video__tag video__tag--size'})
				if title_and_link:
					videos.append({
						'title': title_and_link.get('title').strip(),
						'size': '?' if size == None else size.text.strip(),
						'img': img.get('src') if img else None,
						'id': title_and_link.get('href').strip().lstrip('./')
					})

			page += 1
			if soup.find('a', {'title': 'Zobrazit další'}) == None:
				next_page = None
				break
			else:
				next_page = page

			if len(videos) > limit:
				break

		return videos, next_page

	# ##################################################################################################################

	def resolve_video(self, video_id):
		soup = self.call_api(video_id)

		pattern = re.compile('[{;\s]+var\s+sources\s+=\s+\[(.*?)\];.*', re.DOTALL)
		script = soup.find("script", text=pattern).string

		videos = []
		for v in get_js_data(script, '[{;\s]+var\s+sources\s+=\s+(\[.*?\]);.*'):
			videos.append({
				'url': v['file'],
				'quality': v['label'],
			})
		videos.sort(key=lambda x: int(x['quality'].replace('p', '').replace('i','')), reverse=True)

		subtitles = []
		for s in get_js_data(script, '[{;\s]+var\s+tracks\s+=\s+(\[.*?\]);.*'):
			lang = s['label'].split('-')
			if len(lang) == 3:
				lang = lang[2]
			else:
				lang = s['label']

			subtitles.append({
				'url': s['file'],
				'lang': lang.strip(),
			})

		if self.is_premium:
			response = self.call_api(video_id, params={'do': 'download'}, raw=True, allow_redirects=False)
			if response.status_code > 300 and response.status_code < 310:
				video_url = response.headers['Location']
				videos.insert(0,{
					'url': video_url,
					'quality': 'PREMIUM',
				})

		return videos, subtitles

	# ##################################################################################################################
