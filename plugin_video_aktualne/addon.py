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
import os
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client
import re,datetime,json
from Components.config import config

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
SORT = 'orderby='
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36', 'Referer': BASE}
LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'video-aktualne.log')
CLEANR = re.compile('<.*?>|&lt;.*?&gt;')

def writeLog(msg, type='INFO'):
	try:
		with open(LOG_FILE, 'a') as f:
			dtn = datetime.datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
	except:
		pass

def showInfo(session, mmsg):
	client.show_message(session, mmsg, msg_type='info', timeout=4)

def showError(session, mmsg):
	client.show_message(session, mmsg, msg_type='error', timeout=4)

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
		html = util.request(self.base_url+"hledani/?query="+keyword+"&time=time&section=b:site:video", headers=HEADERS)
		items = re.compile('data-ga4-type="article".*?data-ga4-section="(.*?)".*?data-ga4-title="(.*?)".*?class="timeline__label">(.*?)<.*?href="(.*?)".*?img src="(.*?)".*? fa-play.*?</span>(.*?)<', re.DOTALL).findall(html)
		for (msection, mtitle, mpublished, murl, mimg, mtime) in items:
			itm = self.video_item()
			if not murl.startswith('http'): murl = BASE + murl
			if mimg.startswith('//'): mimg = 'https:' + mimg
			itm['url'] = murl
			itm['img'] = mimg
			itm['title'] = mtitle
			itm['plot'] = mpublished.strip() + " [" + msection + "] (" + mtime.strip() + ") - " + mtitle
			result.append(itm)
		return result

	def categories(self, url=None):
		result = []
		if not url: url = self.base_url+"?offset=1"
		html = util.request(url, headers=HEADERS)
		items = re.compile('class="third-box">.*?<.*?__section.*?>(.*?)</.*?>.*?<a href="(.*?)".*?<img src="(.*?)".*? fa-play.*?</span>(.*?)<.*?<h3 .*?>(.*?)<', re.DOTALL).findall(html)
		for (msection, murl, mimg, mtime, mtitle) in items:
			itm = self.video_item()
			if not murl.startswith('http'): murl = BASE + murl
			if mimg.startswith('//'): mimg = 'https:' + mimg
			itm['url'] = murl
			itm['img'] = mimg
			itm['title'] = mtitle.strip()
			itm['plot'] = " [" + msection.strip() + "] (" + mtime.strip() + ") - " + mtitle.strip()
			result.append(itm)
		mnext = re.search('btn--right.*?href="/\?offset=([0-9]+)', html, re.DOTALL)
		if mnext:
			result.append(self.dir_item('další', re.sub(r'offset=\d+', 'offset=%s' % (int(mnext.group(1))), self.base_url + "?offset=1")))
		return result

	def list(self, url):
		return self.categories(url)

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []

		self.info("URL: %s" % item['url'] )

		item['url'] = "https://video.aktualne.cz/embed_iframe/%s" % item['url'].split('/', 3)[3]

		html = util.request(item['url'], headers=HEADERS)

		# title = re.search('<meta property="og:title" content="(.*?)"', html, re.S).group(1) or ""
		# image = re.search('<meta property="og:image" content="(.*?)"', html, re.S).group(1) or None
		# descr = re.search('<meta property="og:description" content="(.*?)"', html, re.S).group(1) or None

		bbx = re.search('setup: Object.assign\((.*?)autoplay: BBX', html, re.S)
		# bbx = re.search('BBXPlayer.setup\((.*?)\);', html, re.S)
		bbxg = bbx.group(1)
		bbxg = bbxg.rsplit(',', 1)[0];
		bbxj = json.loads(re.sub('\s+',' ',bbxg).strip())
		title = bbxj['title']

		if bbxj['tracks']['MP4']:
			for version in bbxj['tracks']['MP4']:
				itm = self.video_item()
				itm['title'] = title
				itm['surl'] = title
				itm['quality'] = version['label']
				itm['url'] = version['src']
				itm['headers'] = HEADERS
				result.append(itm)
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.aktualne')
addon_userdata_dir = __addon__.getAddonInfo('profile')

def video_aktualne_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}

	provider = VideoAktualneContentProvider(session=session)
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)

# #################################################################################################

def main(addon):
	return XBMCCompatInterface(video_aktualne_run)

# #################################################################################################
