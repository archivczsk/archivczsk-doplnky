# -*- coding: UTF-8 -*-
# /*
# *		 Copyright (C) 2013 Maros Ondrasek
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

import re
import os

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	from HTMLParser import HTMLParser
	import cookielib
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	from html.parser import HTMLParser
	import http.cookiejar as cookielib

from Plugins.Extensions.archivCZSK.engine.tools.util import unescapeHTML
import util, resolver
from provider import ContentProvider


CATEGORIES_START = '<a title="Titulky"'
CATEGORIES_END = '<a title="Ostatní"'
CATEGORIES_ITER_RE = r'<li.+?href="(?P<url>[^"]+)">(?P<title>[^<]+)'

LISTING_START = '<div id="primary" class="content-area">'
LISTING_END = '<div id="secondary"'



class GordonUraParser(HTMLParser):
	POS_NONE, POS_TITLE, POS_URL, POS_SUBS = range(-1, 3)

	def __init__(self):
		HTMLParser.__init__(self)
		self.in_table = False
		self.in_td = False
		self.pos_td = self.POS_NONE
		self.data = ""
		self.table_count = 0
		self.current_item = None
		self.episodes_list = []

	def is_episodes_table(self):
		return self.in_table and self.table_count % 2 == 0

	def get_episodes_list(self, data):
		self.feed(data)
		return self.episodes_list

	def handle_charref(self, name):
		if self.is_episodes_table() and self.in_td and self.pos_td == self.POS_TITLE:
			if int(name) == 215:
				self.data += "x"
			elif int(name) == 8211:
				self.data += "-"

	def handle_starttag(self, tag, attrs):
		if tag == 'table':
			self.in_table = True
			self.table_count += 1
		elif tag == 'td':
			self.in_td = True
			if self.is_episodes_table():
				self.pos_td += 1
		elif tag == 'a' and self.is_episodes_table() and self.in_td and self.pos_td == self.POS_URL:
				for k, v in attrs:
					if k == 'href':
						self.current_item['url'] = v

	def handle_endtag(self, tag):
		if tag == 'table':
			self.in_table = False
		elif tag == 'tr':
			if self.is_episodes_table():
				self.pos_td = self.POS_NONE
				if self.current_item.get('url'):
					self.episodes_list.append(self.current_item)
				self.current_item = None
		elif tag == 'td':
			self.in_td = False
			if self.is_episodes_table() and self.pos_td == self.POS_TITLE:
				self.current_item = {}
				self.current_item['title'] = self.data
				self.data = ""

	def handle_data(self, data):
		if self.is_episodes_table():
			if self.pos_td == 0:
				if data != "\n":
					self.data += data.strip()


class GordonUraContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None):
		ContentProvider.__init__(self, 'gordon.ura.cz', 'http://gordon.ura.cz/', username, password, filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve']

	def categories(self):
		result = []
		page = util.request(self.base_url)
		page = util.substr(page, CATEGORIES_START, CATEGORIES_END)
		for m in re.finditer(CATEGORIES_ITER_RE, page, re.DOTALL):
			item = self.dir_item()
			item['title'] = unescapeHTML(m.group('title'))
			item['url'] = m.group('url')
			result.append(item)
		return result

	def list(self, url):
		result = []
		page = util.request(self._url(url))
		page = util.substr(page, LISTING_START, LISTING_END)
		episodes = GordonUraParser().get_episodes_list(page)
		for e in episodes:
			item = self.video_item()
			item['title'] = e['title']
			item['url'] = e['url']
			result.append(item)
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		item = item.copy()
		page = util.request(self._url(item['url']))
		for m in re.finditer(r'dailymotion.com/embed/video/.+?"', page, re.DOTALL):
			resolved = resolver.findstreams([m.group(0)])
			return select_cb(resolved)

		for m in re.finditer(r'jwplayer\("([^"]+)"\)\.setup\((.+?)\)', page, re.DOTALL):
			jw_title, jw_data = m.group(1), m.group(2)
			vurl_match = re.search(r'file:\s*"([^"]+)', jw_data, re.DOTALL)
			subs_match = re.search(r'tracks:\s*\[\{\s*file:\s*"([^"]+)', jw_data, re.DOTALL)
			if vurl_match:
				vurl = re.sub(r'youtu.be/', r'www.youtube.com/watch?v=', vurl_match.group(1))
				resolved = resolver.findstreams([vurl])
				if resolved:
					for i in resolved:
						item = self.video_item()
						item['title'] = i['title']
						item['url'] = i['url']
						item['quality'] = i['quality']
						item['surl'] = i['surl']
						if subs_match:
							item['subs'] = self._url(subs_match.group(1))
						item['headers'] = i['headers']
						try:
							item['fmt'] = i['fmt']
						except KeyError:
							pass
						result.append(item)
		if len(result) == 1:
			return result[0]
		elif len(result) >= 1:
			if select_cb is not None:
				return select_cb(result)
			return result[0]
		return None
