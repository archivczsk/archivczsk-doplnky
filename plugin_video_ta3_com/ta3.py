# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import json
import re

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0',
	'Referer': 'https://www.ta3.com/',
}

# ##################################################################################################################

class TA3(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session() if self.cp != None else requests.Session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.base_url = 'https://www.ta3.com'

	# ##################################################################################################################

	def call_api(self, url, params=None):
		if not url.startswith('http'):
			url = self.base_url + '/' + url

		response = self.req_session.get(url, params=params)

		if response.status_code == 200:
			return BeautifulSoup(response.content, "html.parser")
		else:
			raise Exception('HTTP response code: %d for page %s' % (response.status_code, url))

	def call_apiXXX(self, url, params=None):
		with open(url, 'r') as f:
			return BeautifulSoup(f.read(), "html.parser")

	# ##################################################################################################################

	def get_img_url(self, section, element):
		if element == None:
			return None
		url = element['src']
		if url and not url.startswith('http'):
			if url.startswith('/'):
				url = self.base_url + url
			else:
				url = self.base_url + '/' + section + '/' + url

		return url

	# ##################################################################################################################

	def get_articles(self, section, page=1):
		ret = []
		max_page = None
		soup = self.call_api(section, params={'page': page})
		for a in soup.find_all('article', {"class": lambda x: x in ("article--main--hybrid", "article--side",) }):
			if a.find('span', {'class': 'article_videolabel'}) != None:
				headline = a.find('div', {'class': 'article_headline'})
				name_element = headline.find('h4')
				if name_element == None:
					name_element = headline.find('h2')
				name = name_element.find('a').get_text().strip(),
				ret.append({
					'name': name[0],
					'url': a.find('a')['href'],
					'img': self.get_img_url(section, a.find('picture').find('img')),
					'desc': '[' + headline.find('span', {'class': 'article_date'}).get_text().strip() + ']\n' + name[0],
				})

		p = soup.find('div', { 'class': 'section_pagination' })
		if p != None:
			p = p.find('span')
			if p != None:
				_, max_page = p.get_text().split('/')
				max_page = int(max_page.strip())

		return ret, max_page

	# ##################################################################################################################

	def get_programs(self):
		section = 'archiv'
		ret = []
		soup = self.call_api(section)
		div = soup.find("div", {"class": "tvshows_listing_results tvshows_results"})
		for a in div.find_all('a', {"class": "tvshows_listing_item"}):
			ret.append({
				'name': a.find('h4').get_text().strip(),
				'url': a['href'],
				'img': self.get_img_url(section, a.find('img')),
				'desc': a.find('p').get_text().strip(),
			})

		return ret

	# ##################################################################################################################

	def get_episodes(self, url, page=1):
		ret = []
		max_page = None
		soup = self.call_api(url, params={'page': page})

		div = soup.find('div', {'class': 'episode_listing_grid'})
		for a in div.find_all('article', {"class": "article--main"}):
			headline = a.find('div', {'class': 'article_headline'})
			name = headline.find('h2').find('a').get_text().strip()
			ret.append({
				'name': name,
				'url': headline.find('h2').find('a')['href'],
				'img': self.get_img_url(url, a.find('picture').find('img')),
				'desc': '[' + headline.find('span', {'class': 'article_date'}).get_text().strip() + ']\n' + name
			})

		p = soup.find('div', { 'class': 'section_pagination' })
		if p != None:
			p = p.find('span')
			if p != None:
				_, max_page = p.get_text().split('/')
				max_page = int(max_page.strip())

		return ret, max_page

	# ##################################################################################################################

	def get_video_url(self, article):
		# get videoID
		soup = self.call_api(article)
		s = soup.find('div', { 'class': 'detail_text_item_livebox' }).find('script')
		video_id = re.search(r'"videoId"[\s]*:[\s]*"(.+?)".*', str(s), re.DOTALL).group(1)
		video_name = re.search(r'"title"[\s]*:[\s]*"(.+?)".*', str(s), re.DOTALL).group(1)

		# get URL pattern
		resp = self.req_session.get("http://embed.livebox.cz/ta3_v2/vod-source.js")
		url_config = json.loads(re.search(r'my\.embedurl[\s]*=[\s]*(\[.+\])', resp.text, re.DOTALL).group(1))

		url_pattern = url_config[0]['src']
		if url_pattern.startswith('//'):
			url_pattern = 'http:' + url_pattern

		return url_pattern.format(video_id), video_name

	# ##################################################################################################################

	def get_live_video_url(self, section='live'):
		resp = self.req_session.get("http://embed.livebox.cz/ta3_v2/%s-source.js" % section)
		url_config = json.loads(re.search(r'my\.embedurl[\s]*=[\s]*(\[.+\])', resp.text, re.DOTALL).group(1))

		url = url_config[0]['src']
		if url.startswith('//'):
			url = 'http:' + url

		return url

	# ##################################################################################################################
