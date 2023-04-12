# -*- coding: utf-8 -*-

import requests
import re
from tools_archivczsk.contentprovider.exception import AddonErrorException
try:
	from bs4 import BeautifulSoup
except:
	BeautifulSoup = None

try:
	from urllib import urlencode, quote
except:
	from urllib.parse import urlencode, quote

# ##################################################################################################################

__debug_nr = 0
import os

def dump_request(response):
	global __debug_nr
	__debug_nr += 1

	request = response.request

	file_name = request.url.replace('/', '_')

	with open(os.path.join('/tmp/', '%03d_%s' % (__debug_nr, file_name)), 'w') as f:
		f.write(response.text)


class PrehrajTo(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		
		self.user = None
		self.password = None
		self.is_premium = False

		self.timeout = int(self.cp.get_setting('loading_timeout'))
		if self.timeout == 0:
			self.timeout = None
		
		self.req_session = requests.Session()
		self.req_session.headers.update({
			'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 OPR/92.0.0.0'
		})

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, raw=False, allow_redirects=True):
		if not endpoint.startswith('http'):
			endpoint = 'https://prehraj.to/' + endpoint

		if data:
			response = self.req_session.post(url=endpoint, params=params, data=data, timeout=self.timeout, allow_redirects=allow_redirects)
		else:
			response = self.req_session.get(url=endpoint, params=params, timeout=self.timeout, allow_redirects=allow_redirects)

#		dump_request(response)

		if raw:
			return response

		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return BeautifulSoup(response.content, 'html.parser')

	# ##################################################################################################################
	
	def login(self):
		user = self.cp.get_setting("ptouser")
		password = self.cp.get_setting("ptopass")

		if not user or not password:
			self.is_premium = False
			return

		if user == self.user and password == self.password:
			return

		data = {
			"email": self.cp.get_setting("ptouser"),
			"password": self.cp.get_setting("ptopass"),
			'_submit': 'Přihlásit+se',
			'remember': 'on',
			'do': 'login-loginForm-submit'
		}
		soup = self.call_api('', data=data)

		title = soup.find('div',attrs={'class': 'user-panel'})
		if title:
			title = title.find('span',attrs={'class': 'color-positive'})
			
		if title == None:
			self.is_premium = False
			self.cp.log_error("Prehraj.to premium account is inactive")
		else:
			self.cp.log_info("Prehraj.to premium account activated")
			self.is_premium = True

		self.user = user
		self.password = password
	
	# ##################################################################################################################

	def search(self, keyword, limit=100):
		if BeautifulSoup == None:
			return []

		page = 1
		videos = []
		while True:
			soup = self.call_api('hledej/' + quote(keyword.encode('utf-8')), params={'vp-page': page})

			for item in soup.find_all('div', attrs={'class': 'column'}):
				title = item.find('h2', attrs={'class': 'video-item-title'})
				size = item.find('strong', attrs={'class': 'video-item-info-size'})
				img = item.find('img', attrs={'data-next': '2'})
#				time = soup.find('strong', attrs={'class': 'video-item-info-time'})
				link = item.find('a', {'class': 'video-item video-item-link'})
				if title and size and link:
					videos.append({
						'title': title.text.strip(),
						'size': size.text.strip(),
						'img': img.get('src') if img else None,
						'id': link['href'].lstrip('./')
					})

			page += 1
			if soup.find('div', {'class': 'pagination-more'}) == None or len(videos) > limit:
				break
		
		return videos

	# ##################################################################################################################
	
	def resolve_video(self, video_id):
		soup = self.call_api(video_id)

		pattern = re.compile('.*var sources = (.*?);.*', re.DOTALL)
		script = soup.find("script", text=pattern).string

		src = re.compile('.*src: "(.*?)".*', re.DOTALL)
		video_url = src.findall(pattern.findall(script)[0])[0]

		try:
			pattern = re.compile('.*var tracks = (.*?);.*', re.DOTALL)
			script = soup.find("script", text=pattern).string
			subs_url = src.findall(pattern.findall(script)[0])[0]
		except:
			subs_url = None

		if self.is_premium:
			response = self.call_api(video_id, params={'do': 'download'}, raw=True, allow_redirects=False)
			if response.status_code > 300 and response.status_code < 310:
				video_url = response.headers['Location']

		return video_url, subs_url

	# ##################################################################################################################
