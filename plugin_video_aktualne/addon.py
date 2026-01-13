# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) 2022 Michal Novotny https://github.com/misanov
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
import re,json

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util
from tools_xbmc.compat import XBMCCompatInterface

try:
	import cookielib
	from urllib2 import HTTPCookieProcessor, HTTPError, build_opener, install_opener
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	from urllib.error import HTTPError
	import http.cookiejar as cookielib

BASE = 'https://video.aktualne.cz'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36', 'Referer': BASE}

class VideoAktualneContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp', session=None):
		ContentProvider.__init__(self, 'video.aktualne.cz', BASE, username, password, filter, tmp_dir)
		self.session = session
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def search(self,keyword):
		result = []
		html = util.request(BASE + "/vyhledavani?q="+keyword+"&sort=revised_and_published_at_desc&tab=Video+%C4%8Dl%C3%A1nky", headers=HEADERS)
		items = re.findall('<article .*?<img .*?src="(.*?)".*?e-web-aktualne-articles-badge__content">(.*?)<.*?<a .*?href="(.*?)".*?>(.*?)</a>.*?e-web-aktualne-articles-card-horizontal__perex.*?>(.*?)<.*?</article>', html)
		for (mimg, mtime, murl, mtitle, mperex) in items:
			itm = self.video_item()
			if not murl.startswith('http'): murl = BASE + murl
			if mimg.startswith('//'): mimg = 'https:' + mimg
			itm['url'] = murl
			itm['img'] = mimg
			itm['title'] = re.sub('<[^<]+?>', '', mtitle).strip()
			itm['plot'] = "(" + mtime + ") - " + mperex
			result.append(itm)
		mnext = re.search(r'<a(?=[^>]*aria-label\s*=\s*"next")(?=[^>]*href\s*=\s*"([^"]+)")[^>]*>', html)
		if mnext:
			result.append(self.dir_item('další', BASE + mnext.group(1)))
		return result

	def categories(self, url=None):
		result = []
		if not url: url = BASE + "/?page=1"
		html = util.request(url, headers=HEADERS)
		items = re.findall('<article .*?<img .*?src="(.*?)".*?<a .*?href="(.*?)".*?>(.*?)</a>.*?&quot;type&quot;:&quot;(.*?)&quot;.*?&quot;section&quot;:&quot;(.*?)&quot;.*?&quot;published&quot;:&quot;(.*?)&quot;.*?</article>', html)
		for (mimg, murl, mtitle, mtype, msection, mpub) in items:
			itm = self.video_item()
			if not murl.startswith('http'): murl = BASE + murl
			if mimg.startswith('//'): mimg = 'https:' + mimg
			itm['url'] = murl
			itm['img'] = mimg
			itm['title'] = re.sub('<[^<]+?>', '', mtitle).strip()
			itm['plot'] = " [" + msection.strip() + "] (" + mpub.strip() + ") - " + re.sub('<[^<]+?>', '', mtitle).strip()
			result.append(itm)
		mnext = re.search(r'<a(?=[^>]*aria-label\s*=\s*"next")(?=[^>]*href\s*=\s*"([^"]+)")[^>]*>', html)
		if mnext:
			result.append(self.dir_item('další', BASE + mnext.group(1)))
		return result

	def list(self, url):
		return self.categories(url)

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		self.info("URL: %s" % item['url'] )
		html = util.request(item['url'], headers=HEADERS)
		mp4 = re.search('"MP4":\[\{"src":"(.*?)","type":"video/mp4","label":"1080p"\}', html)
		if not mp4:
			mp4 = re.search('"contentUrl":"(.*?)"', html)
		if not mp4:
			iframe = re.search('iframe_url: "(.*?)"', html)
			if iframe:
				html = util.request("https:" + iframe.group(1), headers=HEADERS)
				mp4 = re.search('"MP4":\[\{"src":"(.*?)","type":"video/mp4","label":"1080p"\}', html)
		if mp4:
			self.info("MP4: %s" % mp4.group(1) )
			itm = self.video_item()
			itm['title'] = item['title']
			itm['surl'] = item['title']
			itm['url'] = mp4.group(1)
			itm['headers'] = HEADERS
			result.append(itm)
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

def video_aktualne_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality')}

	provider = VideoAktualneContentProvider(session=session)
	XBMCMultiResolverContentProvider(provider, settings, addon, session).run(params)

# #################################################################################################

def main(addon):
	return XBMCCompatInterface(video_aktualne_run, addon)

# #################################################################################################
