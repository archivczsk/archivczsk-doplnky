# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) 2020 Michal Novotny https://github.com/misanov
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
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Plugins.Extensions.archivCZSK.engine import client
import re

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util
from tools_xbmc.compat import XBMCCompatInterface

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urllib import quote
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import quote

class SKTContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'SkTonline', 'https://online.sktorrent.eu/', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def search(self, keyword):
		return self.list(self.base_url+'search/videos?t=a&o=mr&type=public&search_query='+quote(keyword))

	def categories(self):
		result = []
		httpdata = util.request(self.base_url+'categories')
		items = re.compile('col-sm-6.*?href="(.*?)".*?class="thumb-overlay.*?img src="(.*?)".*?title="(.*?)".*?pull-right.*?span.*?>([0-9]*?)<', re.DOTALL).findall(httpdata)
		for link,img,name,count in items:
			result.append(self.dir_item(name+" ("+count+")", self.base_url+link[1:]+"?t=a&o=mr&type=public"))
		return result

	def list(self, url):
		result = []
		if '/videos' in url:
			headers = {"referer": self.base_url}
			httpdata = util.request(url, headers=headers)
			items = re.compile('href=".*?/video/([0-9]*?)/.*?thumb-overlay.*?img src="(.*?)".*?title="(.*?)".*?duration">(.*?)<', re.DOTALL).findall(httpdata)
			for link,img,name,duration in items:
				item = self.video_item()
				item['title'] = name
				item['url'] = self.base_url+"video/"+link+"/"
				item['img'] = img
				item['plot'] = duration.strip()
				result.append(item)
			nextpage = re.compile('<a href="([^"]*?)" class="prevnext">&raquo;</a>', re.DOTALL).findall(httpdata)
			if nextpage and nextpage[0]:
				result.append(self.dir_item(__language__(30100), nextpage[0]))
			return result
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		item = item.copy()
		result = []
		headers = {"referer": self.base_url}
		httpdata = util.request(item['url'], headers=headers)
		items = re.compile('source src="(.*?)".*?res=\'(.*?)\'', re.DOTALL).findall(httpdata)
		for link,res in items:
			item = self.video_item()
			item['surl'] = item['title']
			item['quality'] = res
			item['headers'] = {"referer": self.base_url}
			item['url'] = link
			result.append(item)
		result = sorted(result, key=lambda x:int(x['quality']), reverse=True)
		for idx, item in enumerate(result):
			item['quality'] += "p"
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

__scriptid__ = 'plugin.video.sktonline'
__scriptname__ = 'SkTonline'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString


def sktonline_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}

	provider = SKTContentProvider()
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	return XBMCCompatInterface(sktonline_run)
