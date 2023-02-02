# -*- coding: UTF-8 -*-
# /*
# *		 Copyright (C) 2015 Libor Zoubek + jondas
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */

import hashlib
import sys
import json

from tools_xbmc.contentprovider.provider import ContentProvider, cached, ResolveException
from tools_xbmc.tools import util

try:
	from urllib2 import urlopen, Request, HTTPCookieProcessor, HTTPRedirectHandler, build_opener, install_opener
	import cookielib
	from urllib import quote_plus, addinfourl
except:
	from urllib.request import addinfourl, urlopen, Request, HTTPCookieProcessor, HTTPRedirectHandler, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import quote_plus


#sys.setrecursionlimit(10000)

MOVIES_BASE_URL = "http://movies.prehraj.me"
TV_SHOW_FLAG = "#tvshow#"
ISO_639_1_CZECH = "cs"

# JSONs
URL = "http://tv.sosac.to"
J_MOVIES_A_TO_Z_TYPE = "/vystupy5981/souboryaz.json"
J_MOVIES_GENRE = "/vystupy5981/souboryzanry.json"
J_MOVIES_MOST_POPULAR = "/vystupy5981/moviesmostpopular.json"
J_MOVIES_RECENTLY_ADDED = "/vystupy5981/moviesrecentlyadded.json"
# hack missing json with a-z series
J_TV_SHOWS_A_TO_Z_TYPE = "/vystupy5981/tvpismenaaz/"
J_TV_SHOWS = "/vystupy5981/tvpismena/"
J_SERIES = "/vystupy5981/serialy/"
J_TV_SHOWS_MOST_POPULAR = "/vystupy5981/tvshowsmostpopular.json"
J_TV_SHOWS_RECENTLY_ADDED = "/vystupy5981/tvshowsrecentlyadded.json"
J_SEARCH = "/jsonsearchapi.php?q="
STREAMUJ_URL = "http://www.streamuj.tv/video/"
IMAGE_URL = "http://movies.sosac.tv/images/"
IMAGE_MOVIE = IMAGE_URL + "75x109/movie-"
IMAGE_SERIES = IMAGE_URL + "558x313/serial-"
IMAGE_EPISODE = URL

RATING = 'r'
LANG = 'd'
QUALITY = 'q'


class SosacContentProvider(ContentProvider):
	ISO_639_1_CZECH = None
	par = None

	def __init__(self, username=None, password=None, filter=None, reverse_eps=False):
		ContentProvider.__init__(self, name='sosac.ph', base_url=MOVIES_BASE_URL, username=username,
								 password=password, filter=filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)
		self.reverse_eps = reverse_eps
		self.streamujtv_user = None
		self.streamujtv_pass = None
		self.streamujtv_location = None


	def on_init(self):
		kodilang = self.lang or 'cs'
		if kodilang == ISO_639_1_CZECH or kodilang == 'sk':
			self.ISO_639_1_CZECH = ISO_639_1_CZECH
		else:
			self.ISO_639_1_CZECH = 'en'

	def capabilities(self):
		return ['resolve', 'categories', 'search']

	def categories(self):
		result = []
		for title, url in [
			("Movies", URL + J_MOVIES_A_TO_Z_TYPE),
			("TV Shows", URL + J_TV_SHOWS_A_TO_Z_TYPE),
			("Movies - by Genres", URL + J_MOVIES_GENRE),
			("Movies - Most popular", URL + J_MOVIES_MOST_POPULAR),
			("TV Shows - Most popular", URL + J_TV_SHOWS_MOST_POPULAR),
			("Movies - Recently added", URL + J_MOVIES_RECENTLY_ADDED),
			("TV Shows - Recently added", URL + J_TV_SHOWS_RECENTLY_ADDED)]:
			item = self.dir_item(title=title, url=url)
#			 if title == 'Movies' or title == 'TV Shows' or title == 'Movies - Recently added':
#				 item['menu'] = {"[B][COLOR red]Add all to library[/COLOR][/B]": {
#					 'action': 'add-all-to-library', 'title': title}}
			result.append(item)
		return result

	def search(self, keyword):
		if len(keyword) < 3 or len(keyword) > 100:
			return [self.dir_item(title="Search query must be between 3 and 100 characters long!", url="fail")]
		return self.list_search(URL + J_SEARCH + quote_plus(keyword))

	def a_to_z(self, url):
		result = []
		for letter in ['0-9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'e', 'h', 'i', 'j', 'k', 'l', 'm',
					   'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']:
			item = self.dir_item(title=letter.upper())
			item['url'] = URL + url + letter + ".json"
			result.append(item)
		return result

	@staticmethod
	def remove_flag_from_url(url, flag):
		return url.replace(flag, "", count=1)

	@staticmethod
	def particular_letter(url):
		return "a-z/" in url

	def has_tv_show_flag(self, url):
		return TV_SHOW_FLAG in url

	def remove_flags(self, url):
		return url.replace(TV_SHOW_FLAG, "", 1)

	def list(self, url):
		util.info("Examining url " + url)
		if J_MOVIES_A_TO_Z_TYPE in url:
			return self.load_json_list(url)
		if J_MOVIES_GENRE in url:
			return self.load_json_list(url)
		if J_MOVIES_MOST_POPULAR in url:
			return self.list_videos(url)
		if J_MOVIES_RECENTLY_ADDED in url:
			return self.list_videos(url)
		if J_TV_SHOWS_A_TO_Z_TYPE in url:
			return self.a_to_z(J_TV_SHOWS)
		if J_TV_SHOWS in url:
			return self.list_series_letter(url)
		if J_SERIES in url:
			return self.list_episodes(url)
		if J_TV_SHOWS_MOST_POPULAR in url:
			return self.list_series_letter(url)
		if J_TV_SHOWS_RECENTLY_ADDED in url:
			return self.list_recentlyadded_episodes(url)
		return self.list_videos(url)

	def load_json_list(self, url):
		result = []
		data = util.request(url)
		json_list = json.loads(data)
		for key, value in json_list.items():
			item = self.dir_item(title=self.upper_first_letter(key))
			item['url'] = value
			result.append(item)

		return sorted(result, key=lambda i: i['title'])

	def list_videos(self, url):
		result = []
		data = util.request(url)
		json_video_array = json.loads(data)
		for video in json_video_array:
			item = self.video_item()
			item['title'] = self.get_video_name(video)
			item['img'] = IMAGE_MOVIE + video['i']
			item['url'] = video['l'] if video['l'] else ""
			if RATING in video:
				item['rating'] = video[RATING]
			if LANG in video:
				item['lang'] = video[LANG]
			if QUALITY in video:
				item['quality'] = video[QUALITY]
			result.append(item)
		return result

	def list_series_letter(self, url):
		result = []
		data = util.request(url)
		json_list = json.loads(data)
		for serial in json_list:
			item = self.dir_item()
			item['title'] = self.get_localized_name(serial['n'])
			item['img'] = IMAGE_SERIES + serial['i']
			item['url'] = serial['l']
			result.append(item)
		return result

	def list_episodes(self, url):
		result = []
		data = util.request(url)
		json_series = json.loads(data)
		for series in json_series:
			for series_key, episode in series.items():
				for episode_key, video in episode.items():
					item = self.video_item()
					item['title'] = series_key + "x" + episode_key + " - " + video['n']
					if video['i'] is not None: item['img'] = IMAGE_EPISODE + video['i']
					item['url'] = video['l'] if video['l'] else ""
					result.append(item)
		if not self.reverse_eps:
			result.reverse()
		return result

	def list_recentlyadded_episodes(self, url):
		result = []
		data = util.request(url)
		json_series = json.loads(data)
		for episode in json_series:
			item = self.video_item()
			item['title'] = self.get_episode_recently_name(episode)
			item['img'] = IMAGE_EPISODE + episode['i']
			item['url'] = episode['l']
			result.append(item)
		return result

	def get_video_name(self, video):
		name = self.get_localized_name(video['n'])
		year = (" (" + video['y'] + ") ") if video['y'] else " "
		quality = ("- " + video[QUALITY].upper()) if video[QUALITY] else ""
		return name + year + quality

	def get_episode_recently_name(self, episode):
		serial = self.get_localized_name(episode['t']) + ' '
		series = episode['s'] + "x"
		number = episode['e'] + " - "
		name = self.get_localized_name(episode['n'])
		return serial + series + number + name

	def add_video_flag(self, items):
		flagged_items = []
		for item in items:
			flagged_item = self.video_item()
			flagged_item.update(item)
			flagged_items.append(flagged_item)
		return flagged_items

	def add_directory_flag(self, items):
		flagged_items = []
		for item in items:
			flagged_item = self.dir_item()
			flagged_item.update(item)
			flagged_items.append(flagged_item)
		return flagged_items
	
	def get_localized_name(self, names):
		return names[self.ISO_639_1_CZECH] if self.ISO_639_1_CZECH in names else names[ISO_639_1_CZECH]

	@cached(ttl=24)
	def get_data_cached(self, url):
		return util.request(url)

	def add_flag_to_url(self, item, flag):
		item['url'] = flag + item['url']
		return item

	def add_url_flag_to_items(self, items, flag):
		subs = self.get_subs()
		for item in items:
			if item['url'] in subs:
				item['title'] = '[B][COLOR yellow]*[/COLOR][/B] ' + item['title']
			self.add_flag_to_url(item, flag)
		return items

	def _url(self, url):
		# DirtyFix nefunkcniho downloadu: Neznam kod tak se toho zkusenejsi chopte
		# a prepiste to lepe :)
		if '&authorize=' in url:
			return url
		else:
			return self.base_url + "/" + url.lstrip('./')

	def list_tv_shows_by_letter(self, url):
		util.info("Getting shows by letter " + url)
		shows = self.list_by_letter(url)
		util.info("Resolved shows " + str(shows))
		shows = self.add_directory_flag(shows)
		return self.add_url_flag_to_items(shows, TV_SHOW_FLAG)

	def list_movies_by_letter(self, url):
		movies = self.list_by_letter(url)
		util.info("Resolved movies " + str(movies))
		return self.add_video_flag(movies)

	def resolve(self, item, captcha_cb=None, select_cb=None):
		def probeHTML5(result):

			class NoRedirectHandler(HTTPRedirectHandler):

				def http_error_302(self, req, fp, code, msg, headers):
					infourl = addinfourl(fp, headers, req.get_full_url())
					infourl.status = code
					infourl.code = code
					return infourl
				http_error_300 = http_error_302
				http_error_301 = http_error_302
				http_error_303 = http_error_302
				http_error_307 = http_error_302

			if result is not None:
				opener = build_opener(NoRedirectHandler())
				install_opener(opener)

				r = urlopen(Request(result['url'], headers=result['headers']))
				if r.code == 200:
					result['url'] = r.read().decode('utf-8')
			return result

		data = item['url']
		if not data:
			raise ResolveException('Video is not available.')
		result = self.findstreams([STREAMUJ_URL + data])
		if len(result) == 1:
			return probeHTML5(self.set_streamujtv_info(result[0]))
		elif len(result) > 1 and select_cb:
			return probeHTML5(self.set_streamujtv_info(select_cb(result)))

	def set_streamujtv_info(self, stream):
		if stream:
			if len(self.streamujtv_user) > 0 and len(self.streamujtv_pass) > 0:
				# set streamujtv credentials
				m = hashlib.md5()
				m.update(self.streamujtv_pass.encode('utf-8'))
				h = m.hexdigest()
				m = hashlib.md5()
				m.update(h.encode('utf-8'))
				stream['url'] = stream['url'] + \
					"&pass=%s:::%s" % (self.streamujtv_user, m.hexdigest())
			if self.streamujtv_location in ['1', '2']:
				stream['url'] = stream['url'] + "&location=%s" % self.streamujtv_location
		return stream


	def get_subs(self):
		return self.parent.get_subs()

	def list_search(self, url):
		return self.list_videos(url)

	def upper_first_letter(self, name):
		return name[:1].upper() + name[1:]
