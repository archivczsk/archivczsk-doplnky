# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.debug.http import dump_json_request
import sys
import requests
import re, json

try:
	from urllib import quote
except:
	from urllib.parse import quote

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
	'Referer': 'https://www.markiza.sk/',
}
REFERER_MEDIA = 'https://media.cms.markiza.sk'


def get_duration(dur):
	duration = 0
	l = dur.strip().split(":")
	for pos, value in enumerate(l[::-1]):
		duration += int(value) * 60 ** pos
	return duration


def img_res(url):
	if "314x175" in url:
		r = url.replace("314x175", "913x525")
	elif "275x153" in url:
		r = url.replace("275x153", "825x459")
	elif "276x383" in url:
		r = url.replace("276x383", "828x1149")
	else:
		r = url
	return r


class MarkizaContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'Markiza', settings=settings, data_dir=data_dir)
		self.login_optional_settings_names = ('username', 'password')
		self.req_session = requests.Session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.login_ok = False

	# ##################################################################################################################

	def login(self, silent):
		self.login_ok = False

		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing with free account")
			return True

		cks = self.get_settings_checksum(('username', 'password',))
		data = self.load_cached_data('login')

		votoken = data.get('session')

		if votoken and data.get('checksum') and data['checksum'] == cks:
			self.log_debug("Session data found in cache")
			self.req_session.cookies.set('votoken', data['session'], domain='.markiza.sk')
			if self.check_login():
				self.log_debug("Login check OK - continuing with loaded session")
				self.login_ok = True
				return True
		else:
			# fetch cookies
			self.check_login()

		self.log_debug("Don't have login session - trying fresh login")

		# not logged yet or check login failed
		payload = {
			'email': self.get_setting('username'),
			'password': self.get_setting('password'),
			'_do':'content1224-loginForm-form-submit'
		}

		self.call_api('prihlasenie', data=payload, raw_response=True)

		# check if login passed
		if not self.check_login():
			self.login_error("Prihlásenie zlyhalo - skontrolujte prihlasovacie meno a heslo")
			return False

		# get votoken cookie and store it
		data['session'] = self.req_session.cookies.get('votoken')

		if not data['session']:
			self.login_error("Nepodarilo sa vytvoriť prihlasovaciu session. Možno nastala zmena spôsobu prihásenia.")
			return False

		data['checksum'] = cks
		self.save_cached_data('login', data)
		self.log_debug("Login session authorized and stored")
		self.login_ok = True
		return True

	# ##################################################################################################################

	def check_login(self):
		response = self.call_api('uzivatelsky-profil', raw_response=True)
		if response.url.endswith('/prihlasenie'):
			return False
		else:
			return True

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, headers=None, raw_response=False):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://www.markiza.sk/' + endpoint

		req_headers = {
			'Accept-Encoding': 'identity',
		}
		if headers:
			req_headers.update(headers)
		
		if data:
			response = self.req_session.post(url, params=params, data=data, headers=req_headers)
		else:
			response = self.req_session.get(url, params=params, headers=req_headers)

#		dump_json_request(response)

		if raw_response:
			return response

		if response.status_code == 200:
			return BeautifulSoup(response.content, "html.parser")
		else:
			raise AddonErrorException('HTTP reponse code: %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		if not bs4_available:
			self.show_info("K fungovniu doplnku TV Markiza si musíte pomocou svojho správcu balíkov doinštalovať BeautifulSoup4. Hľadejte balík se menem:\npython{0}-beautifulsoup4 alebo python{0}-bs4".format('3' if sys.version_info[0] == 3 else ''))
			return

		if self.login_ok:
			self.add_video('Markíza Live', cmd=self.resolve_video, video_title="Markíza Live", url="live/1-markiza", download=False)

		self.add_dir("Posledné epizódy", cmd=self.list_recent_episodes)
		self.add_dir("TOP programy", cmd=self.list_shows_menu)

	# ##################################################################################################################

	def list_recent_episodes(self):
		soup = self.call_api("")

		dur = 0
		title = None
		show_title = None
		video = None

		article_hero = soup.find("div", {"class": "c-hero"})

		try:
			show_title = article_hero.find(
				"h2", {"class": "title"}).find("a").get_text()

			title = article_hero.find(
				"h3", {"class": "subtitle"}).find("a").get_text()

			dur = article_hero.find(
				"time", {"class": "duration"}).get_text()

			aired = article_hero.find("time", {"class": "date"})["datetime"]
			video = article_hero.find(
				"div", {"class": "actions"}).find("a")["href"]
		except:
			pass

		if video:
			video_title = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			img = img_res(article_hero.find("img")["data-src"])
			info_labels = {
				'duration': get_duration(re.sub(r"[a-z]", ':', (dur.replace(" ", "")))[:-1]) if dur else None
			}

			self.add_video(video_title, img, info_labels, cmd=self.resolve_video, video_title=video_title, url=video)

		articles = soup.find("div",
			{
				"class": "c-article-transformer-carousel swiper-container js-article-transformer-carousel"
			},
		).find_all("article")

		for article in articles:
			show_title = article["data-tracking-tile-show-name"]
			if not show_title:
				show_title = article.find("div", { 'class': 'content'}).find('a', {'class': 'category'}).get_text()
			title = article["data-tracking-tile-name"]
			dur = article.find("time", {"class": "duration"})
			show_url = article.find("a", {"class": "category"})["href"]

			video_title = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			img = img_res(article.find("picture").find("source")["data-srcset"])

			info_labels = {
				'duration': get_duration(dur.get_text()) if dur else None
			}

			menu = {}
			self.add_menu_item(menu, 'Prejsť na reláciu', cmd=self.list_episodes, url=show_url, category=True)
			self.add_video(video_title, img, info_labels, menu=menu, cmd=self.resolve_video, video_title=video_title, url=article.find("a", {"class": "img"})["href"])

	# ##################################################################################################################

	def list_shows_menu(self):
		self.add_dir('Nejlepšie', cmd=self.list_shows, selector='c-show-wrapper -highlight tab-pane fade show active')
		self.add_dir('Najnovšie', cmd=self.list_shows, selector='c-show-wrapper -highlight tab-pane fade')
		self.add_dir('Všetky', cmd=self.list_shows, selector='c-show-wrapper')

	# ##################################################################################################################

	def list_shows(self, selector):
		soup = self.call_api("relacie")

		articles = soup.find(lambda tag: tag.name == 'div' and ' '.join(tag.get('class', [])) == selector).find_all("a")

		for article in articles:
			title = article["data-tracking-tile-name"]
			img = img_res(article.div.img["data-src"])
			self.add_dir(title, img, cmd=self.list_episodes, url=article["href"], category=True)

	# ##################################################################################################################

	def list_episodes(self, url, category=False):
		list_voyo = self.get_setting('list-voyo')

		if category:
			self.add_dir("Kategórie", cmd=self.list_categories, url=url)
			url += "/videa/cele-epizody"

		soup = self.call_api(url)

		try:
			articles = soup.find(
				"div", "c-article-wrapper").find_all("article", "c-article")
		except:
			articles = []

		count = 0
		for article in articles:

			show_title = article["data-tracking-tile-show-name"]
			title = article["data-tracking-tile-name"]
			dur = article.find("time", {"class": "duration"})

			video_title = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			img = img_res(article.find("picture").find("source")["data-srcset"])

			info_labels = {
				'duration': get_duration(dur.get_text()) if dur else None
			}

			if '-voyo' in article['class']:
				if list_voyo:
					self.add_video(_I('* ') + video_title, img, info_labels)
			else:
				self.add_video(video_title, img, info_labels, cmd=self.resolve_video, video_title=video_title, url=article.find("a", {"class": "img"})["href"])

			count += 1

		next = soup.find("div", {"class": "js-load-more-trigger"})
		if next and count > 0:
			self.add_next(self.list_episodes, url=next.find("button")["data-href"])

	# ##################################################################################################################

	def list_categories(self, url):
		soup = self.call_api(url + "/videa")
		navs = soup.find("nav", "c-tabs")

		if navs:
			for nav in navs.find_all("a"):
				self.add_dir(nav.get_text(), cmd=self.list_episodes, url=nav['href'])

	# ##################################################################################################################

	def resolve_streams(self, url, max_bitrate=None):
		try:
			headers = {
				'referer': REFERER_MEDIA,
				'origin': REFERER_MEDIA
			}
			req = self.call_api(url, headers=headers, raw_response=True)
		except:
			self.log_exception()
			self.show_error("Problém při načítaním videa - URL neexistuje")
			return None

		if req.status_code != 200:
			self.show_error("Problém při načtení videa - neočekávaný návratový kód %d" % req.status_code)
			return None

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

		streams = []
#		self.log_info("Playlist data:\n%s" % req.text)
		for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', req.text, re.MULTILINE):
			stream_info = {}
			for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
				key, val = info.split('=', 1)
				stream_info[key.lower()] = val

			stream_url = m.group('chunk')

			if not stream_url.startswith('http'):
				if stream_url.startswith('/'):
					stream_url = url[:url[9:].find('/') + 9] + stream_url
				else:
					stream_url = url[:url.rfind('/') + 1] + stream_url

			stream_info['url'] = stream_url
			if int(stream_info['bandwidth']) <= max_bitrate:
				streams.append(stream_info)

		return sorted(streams, key=lambda i: int(i['bandwidth']), reverse=True)

	# ##################################################################################################################

	def resolve_video(self, video_title, url):
		resolved_url = None

		soup = self.call_api(url)
		try:
			embeded_url = soup.find("div", {"class": "js-login-player"}).find("iframe")["data-src"]
		except:
			try:
				embeded_url = soup.find("div", {"class": "js-player-detach-container"}).find("iframe")["src"]
			except:
				self.show_info("Video nebolo nájdené.")

#		self.log_info("Embedded url: %s" % embeded_url)
		embeded = self.call_api(embeded_url)

		try:
			json_data = json.loads(
				re.compile('{"tracks":(.+?),"duration"').findall(str(embeded))[0]
			)
		except:
			self.log_exception()
			json_data = None

		if json_data:
#			self.log_info("json_data: %s" % json_data)
			stream_data = json_data['HLS'][0]

			if not "drm" in stream_data:
				resolved_url = stream_data["src"]
		else:
			embeded_text = embeded.get_text()
#				self.log_info(embeded_text)
			if 'Error' in embeded_text:
				embeded_text = embeded_text.replace('Error', '').strip()
				if '\n' in embeded_text:
					embeded_text = embeded_text[embeded_text.rfind('\n'):]

				self.show_info("Nepodarilo sa prehrať video: %s" % embeded_text.replace('Error', '').strip())

		if resolved_url:
			stream_links = self.resolve_streams(resolved_url, self.get_setting('max_bitrate'))
		else:
			stream_links = []

		settings = {
			'user-agent': COMMON_HEADERS['User-Agent'],
			'extra-headers': {
				'referer': REFERER_MEDIA,
				'origin': REFERER_MEDIA
			}
		}

		for one in stream_links:
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, one['url'], info_labels=info_labels, settings=settings)

