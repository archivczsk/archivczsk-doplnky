# -*- coding: utf-8 -*-
from functools import partial
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.compat import quote
from datetime import date, timedelta, datetime
import sys

# ##################################################################################################################

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
}

# ##################################################################################################################

class TVLuxContentProvider(CommonContentProvider):
	PAGE_SIZE = 50
	ARCHIVE_PAGE_SIZE = 365

	def __init__(self):
		CommonContentProvider.__init__(self, 'TVLux')
		self.req_session = self.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.days_of_week = (self._('Monday'), self._('Tuesday'), self._('Wednesday'), self._('Thursday'), self._('Friday'), self._('Saturday'), self._('Sunday'))

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, headers=None, raw_response=False):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://www.tvlux.sk/archiv/' + endpoint

		req_headers = {
			'Accept-Encoding': 'identity',
		}
		if headers:
			req_headers.update(headers)

		try:
			if data:
				response = self.req_session.post(url, params=params, data=data, headers=req_headers)
			else:
				response = self.req_session.get(url, params=params, headers=req_headers)
		except Exception as e:
			raise AddonErrorException(self._('Request to remote server failed. Try to repeat operation.') + '\n%s' % str(e))

#		dump_json_request(response)

		if raw_response:
			return response

		if response.status_code == 200:
			return BeautifulSoup(response.content, "html.parser")
		else:
			raise AddonErrorException(self._('HTTP response code') + ': %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		if not bs4_available:
			self.show_info(self._("In order addon to work you need to install the BeautifulSoup4 using your package manager. Search for package with name:\npython{0}-beautifulsoup4 or python{0}-bs4)").format('3' if sys.version_info[0] == 3 else ''))
			return

		self.add_search_dir()
		self.add_video(self._('TV Lux live'), cmd=self.resolve_streams, video_title="TV Lux", url="https://stream.tvlux.sk/luxtv/luxtv-livestream/playlist.m3u8")
		self.add_dir(self._("All shows"), cmd=self.list_shows)
		self.add_dir(self._("By date"), cmd=self.list_date)

	# ##################################################################################################################

	def search(self, keyword, search_id='', day=''):
		params = {
			'q': quote(keyword),
			'relacia': '',
			'day': day,
			'day_submit': day
		}
		return self.list_episodes('hladat/', params, True)

	# ##################################################################################################################

	def list_date(self, page=0):
		for i in range(page * self.ARCHIVE_PAGE_SIZE, (page+1) * self.ARCHIVE_PAGE_SIZE):
			day = date.today() - timedelta(days=i)
			if i == 0:
				day_name = self._("Today")
			elif i == 1:
				day_name = self._("Yesterday")
			else:
				day_name = self.days_of_week[day.weekday()] + " " + day.strftime("%d.%m.%Y")

			self.add_dir(day_name, cmd=self.search, keyword='', day=day.strftime("%d.%m.%Y"))
		else:
			self.add_next(cmd=self.list_date, page=page+1)


	# ##################################################################################################################

	def list_shows(self):
		soup = self.call_api("abecedne/vsetko")

		for div in soup.findAll("div", class_="col-md-6 col-lg-3 rel-identification"):
			title = div.find("h3").text.strip()
			url = div.find("a")["href"].strip()
			img = div.find("img")["src"].strip()
			genre = div.find("div", class_="tag-blue").text.strip()

			info_labels = {
				'genre': genre,
				'plot': '[{}]'.format(genre)
			}

			self.add_dir(title, img, info_labels, cmd=self.list_episodes, url=url)

	# ##################################################################################################################

	def load_info_labels(self, url, video_date):
		soup = self.call_api(url)

		return {
			'plot': '[{}]\n{}'.format(video_date, soup.find("p").text.strip())
		}

	# ##################################################################################################################

	def list_episodes(self, url, params=None, full_title=False):
		soup = self.call_api(url, params=params)

		num = 0
		while True:
			for div in soup.findAll("div", class_="archive-item"):
				title = div.find("h4").text.strip()
				url = div.find("a")["href"]
				img = div.find("img")["src"]
				d = div.find("div", class_="tag dark").text.strip()

				if full_title:
					show_name = div.find("h5").text.strip()
					video_title = title + _I(' [{}]').format(show_name)
				else:
					video_title = title

				info_labels = partial(self.load_info_labels, url=url, video_date=d)
				self.add_video(video_title, img, info_labels, cmd=self.resolve_video, url=url, video_title=title)
				num += 1


			pages = soup.find("ul", class_="a-list")
			if pages is not None:
				next_button = pages.find("a", class_="chevronRight")

				if next_button is not None:
					next_button_url = next_button.get("href")
					if next_button_url:
						if num > self.PAGE_SIZE:
							self.add_next(cmd=self.list_episodes, url=next_button_url, full_title=full_title)
						else:
							soup = self.call_api(next_button_url)
							continue

			break

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

	# ##################################################################################################################

	def resolve_streams(self, video_title, url):
		for one in self.get_hls_streams(url, requests_session=self.req_session, max_bitrate=self.get_setting('max_bitrate')):
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			url = stream_key_to_hls_url(self.http_endpoint, {'url': one['playlist_url'], 'bandwidth': one['bandwidth'] })
			self.add_play(video_title, url, info_labels=info_labels)


	# ##################################################################################################################

	def resolve_video(self, video_title, url):
		soup = self.call_api(url)

		video_url = soup.find("source")["src"].strip()
		return self.resolve_streams(video_title, video_url)

	# ##################################################################################################################
