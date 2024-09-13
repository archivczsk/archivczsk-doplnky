# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
import sys
import re, json

try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False

COMMON_HEADERS = {
	'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36',
	'Referer': 'https://tv.nova.cz/',
}
REFERER_MEDIA = 'https://media.cms.nova.cz'


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


class TVNovaContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'TV Nova', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.login_optional_settings_names = ('username', 'password')
		self.req_session = self.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.scache = SimpleAutokeyExpiringCache()
		self.login_ok = False

	# ##################################################################################################################

	def login(self, silent):
		self.login_ok = False
		self.req_session.cookies.clear()

		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing with free account")
			return True

		cks = self.get_settings_checksum(('username', 'password',))
		data = self.load_cached_data('login')

		votoken = data.get('session')

		if votoken and data.get('checksum') and data['checksum'] == cks:
			self.log_debug("Session data found in cache")
			self.req_session.cookies.set('votoken', data['session'], domain='.nova.cz')
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
			'_do':'content574-loginForm-form-submit'
		}

		self.call_api('prihlaseni', data=payload, raw_response=True)

		# check if login passed
		if not self.check_login():
			self.login_error(self._("Login failed - check login name and password"))
			return False

		# get votoken cookie and store it
		data['session'] = self.req_session.cookies.get('votoken')

		if not data['session']:
			self.login_error(self._("Failed to create login session. Maybe login page has changed."))
			return False

		data['checksum'] = cks
		self.save_cached_data('login', data)
		self.log_debug("Login session authorized and stored")
		self.login_ok = True
		return True

	# ##################################################################################################################

	def check_login(self):
		response = self.call_api('uzivatelsky-profil', raw_response=True)
		if response.url.endswith('/prihlaseni'):
			return False
		else:
			return True

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, headers=None, raw_response=False):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://tv.nova.cz/' + endpoint

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

		if self.login_ok:
			self.add_video('Nova Live', cmd=self.resolve_video, video_title="Nova Live", url="sledujte-zive/1-nova", download=False)

		self.add_video('TN Live', cmd=self.resolve_video, video_title="TN Live", url="#live#tn-live-live", download=False)

		self.add_dir(self._("Latest episodes"), cmd=self.list_recent_episodes)
		self.add_dir(self._("TOP programs"), cmd=self.list_shows_menu)

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
			self.add_menu_item(menu, self._('Go to show'), cmd=self.list_episodes, url=show_url, category=True)
			self.add_video(video_title, img, info_labels, menu=menu, cmd=self.resolve_video, video_title=video_title, url=article.find("a", {"class": "img"})["href"])

	# ##################################################################################################################

	def list_shows_menu(self):
		self.add_dir(self._('Best'), cmd=self.list_shows, selector='c-show-wrapper -highlight tab-pane fade show active')
		self.add_dir(self._('Latest'), cmd=self.list_shows, selector='c-show-wrapper -highlight tab-pane fade')
		self.add_dir(self._('All'), cmd=self.list_shows, selector='c-show-wrapper')

	# ##################################################################################################################

	def list_shows(self, selector):
		soup = self.call_api("porady")

		articles = soup.find(lambda tag: tag.name == 'div' and ' '.join(tag.get('class', [])) == selector).find_all("a")

		for article in articles:
			title = article["data-tracking-tile-name"]
			img = img_res(article.div.img["data-src"])
			self.add_dir(title, img, cmd=self.list_episodes, url=article["href"], category=True)

	# ##################################################################################################################

	def list_episodes(self, url, category=False):
		list_voyo = self.get_setting('list-voyo')
		soup = None
		url_orig = url

		if category:
			self.add_dir(self._("Categories"), cmd=self.list_categories, url=url)
			url += "/videa/cele-dily"

		try:
			soup = self.call_api(url)
			articles = soup.find(
				"div", "c-article-wrapper").find_all("article", "c-article")
		except:
			if category:
				# cele-dily is not available, so jump directly to main page
				return self.list_episodes(url_orig)

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

		next = soup.find("div", {"class": "js-load-more-trigger"}) if soup else None
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

	def get_hls_info(self, stream_key):
		cache_data = self.scache.get(stream_key['ck'])

		return {
			'url': cache_data['playlist_url'],
			'bandwidth': stream_key['bandwidth'],
			'headers': {
				'referer': REFERER_MEDIA,
				'origin': REFERER_MEDIA
			}
		}

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		cache_data = self.scache.get(stream_key['ck'])
		drm = cache_data.get('drm')

		ret = {
			'url': cache_data['playlist_url'],
			'bandwidth': stream_key['bandwidth'],
			'headers': {
				'referer': REFERER_MEDIA,
				'origin': REFERER_MEDIA
			},
		}

		if drm:
			ret.update({
				'drm' : {
					'licence_url': drm["serverURL"],
					'headers': { h['name']: h['value'] for h in drm["headers"] }
				}
			})

		return ret

	# ##################################################################################################################

	def resolve_streams(self, url, max_bitrate=None, drm=None):
		headers = {
			'referer': REFERER_MEDIA,
			'origin': REFERER_MEDIA
		}

		cached_data = {}
		ret = []
		cache_key = self.scache.put(cached_data)

		if drm:
			streams = self.get_dash_streams(url, headers=headers, requests_session=self.req_session, max_bitrate=max_bitrate)
			cached_data.update({
				'playlist_url': streams[0]['playlist_url'] if streams else None,
				'drm': drm
			})

			for stream in streams:
				ret.append({
					'url': stream_key_to_dash_url(self.http_endpoint, {'ck': cache_key, 'bandwidth': stream['bandwidth']}),
					'bandwidth': stream['bandwidth'],
					'quality': stream['height'] + 'p' if stream.get('height') else "720p"
				})
		else:
	#		self.log_debug("HLS master url: %s" % url)
			streams = self.get_hls_streams(url, headers=headers, requests_session=self.req_session, max_bitrate=max_bitrate)
			cached_data.update({
				'playlist_url': streams[0]['playlist_url'] if streams else None
			})

			for stream in (streams or []):
				ret.append({
					'url': stream_key_to_hls_url(self.http_endpoint, {'ck': cache_key, 'bandwidth': stream['bandwidth']}),
					'bandwidth': stream['bandwidth'],
					'quality': stream.get('resolution', 'x???').split('x')[1] + 'p'
				})

		return ret

	# ##################################################################################################################

	def resolve_video(self, video_title, url):
		resolved_url = None
		drm = None

		if url.startswith('#live#'):
			url = url[6:]
			response = self.call_api('https://media.cms.nova.cz/embed/' + url + '?autoplay=1', raw_response=True)

			if response.status_code == 200:
				data = re.search("processAdTagModifier\(\{(.*?)\}\)", response.text, re.S)

				if data:
					plr = json.loads('{' + data.group(1) + '}')
					resolved_url = plr["tracks"]["HLS"][0]["src"]
		else:
			soup = self.call_api(url)

			script_element = soup.find("script", type="application/ld+json", string=re.compile(r"embedUrl"))
			embeded_url = None

			if script_element is not None:
				json_stream = json.loads(script_element.string)
				if "video" in json_stream:
					embeded_url = json_stream["video"]["embedUrl"]
				elif "embedUrl" in json_stream:
					embeded_url = json_stream["embedUrl"]

			if not embeded_url:
				self.show_info(self._("Video not found."))

			self.log_debug("Embedded url: %s" % embeded_url)
			embeded = self.call_api(embeded_url)

			try:
				json_data = json.loads(
					re.compile('{"tracks":(.+?),"duration"').findall(str(embeded))[0]
				)
			except:
				self.log_exception()
				json_data = None

			if json_data:
				self.log_info("json_data: %s" % json.dumps(json_data))

				stream_data = json_data['HLS'][0]

				if not "drm" in stream_data:
					resolved_url = stream_data["src"]
					self.log_info("Found unprotected HLS stream: %s" % resolved_url)
				else:
					# drm protected content
					stream_data = json_data['DASH'][0]
					for d in stream_data['drm']:
						if d['keySystem'] == 'com.widevine.alpha':
							drm = d
							break
					else:
						self.show_error(self._("No supported DRM protection system found"))

					resolved_url = stream_data["src"]
					self.log_info("Found DRM protected DASH stream: %s" % resolved_url)
			else:
				self.log_error("Player configuration not found - trying to extract error message")

				embeded_text = embeded.get_text()
#				self.log_info(embeded_text)

				if 'Error' in embeded_text:
					embeded_text = embeded_text.replace('Error', '').strip()
					if '\n' in embeded_text:
						embeded_text = embeded_text[embeded_text.rfind('\n'):]
				else:
					embeded_text = self._("Format of page has changed")

				self.show_info(self._("Failed to play video") + ": %s" % embeded_text.replace('Error', '').strip())

		if resolved_url:
			stream_links = self.resolve_streams(resolved_url, self.get_setting('max_bitrate'), drm)
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
				'quality': one['quality']
			}
			self.add_play(video_title, one['url'], info_labels=info_labels, settings=settings)
