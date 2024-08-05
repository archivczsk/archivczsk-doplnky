# -*- coding: utf-8 -*-

import re
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import strip_accents
import ast

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

		return self.is_premium

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
			soup = self.call_api('hledej/' + quote(keyword.encode('utf-8')), params={'vp-page': page})

			for item in soup.find_all('div', attrs={'class': 'video__picture--container'}):
				title_and_link = item.find('a', attrs={'class': 'video video--small video--link'})
				size = item.find('div', attrs={'class': 'video__tag video__tag--size'})
				img = item.find('img', attrs={'data-next': '2'})
#				time = soup.find('div', attrs={'class': 'video__tag video__tag--size'})
				if title_and_link and size:
					videos.append({
						'title': title_and_link.get('title').strip(),
						'size': size.text.strip(),
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

	def get_js_data(self, data, pattern):
		'''
		Extracts piece of javascript data from data based on pattern and converts it to python object
		'''
		sources = re.compile(pattern, re.DOTALL)
		js_obj = sources.findall(data)[0]

		# remove all spaces not in double quotes
		js_obj = re.sub(r'\s+(?=([^"]*"[^"]*")*[^"]*$)', '', js_obj)

		# add double quotes around dictionary keys
		js_obj = re.sub(r'([{,]+)(\w+):', '\\1"\\2":', js_obj)

		# replace JS variables with python alternatives
		js_obj = re.sub(r'(["\']):undefined([,}])', '\\1:None\\2', js_obj)
		js_obj = re.sub(r'(["\']):null([,}])', '\\1:None\\2', js_obj)
		js_obj = re.sub(r'(["\']):NaN([,}])', '\\1:None\\2', js_obj)
		js_obj = re.sub(r'(["\']):true([,}])', '\\1:True\\2', js_obj)
		js_obj = re.sub(r'(["\']):false([,}])', '\\1:False\\2', js_obj)
		return ast.literal_eval('[' + js_obj + ']')

	# ##################################################################################################################

	def resolve_video(self, video_id):
		soup = self.call_api(video_id)

		pattern = re.compile('[{;\s]+var\s+sources\s+=\s+\[(.*?)\];.*', re.DOTALL)
		script = soup.find("script", text=pattern).string

		videos = []
		for v in self.get_js_data(script, '[{;\s]+var\s+sources\s+=\s+\[(.*?)\];.*'):
			videos.append({
				'url': v['file'],
				'quality': v['label'],
			})
		videos.sort(key=lambda x: int(x['quality'].replace('p', '').replace('i','')), reverse=True)

		subtitles = []
		for s in self.get_js_data(script, '[{;\s]+var\s+tracks\s+=\s+\[(.*?)\];.*'):
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
