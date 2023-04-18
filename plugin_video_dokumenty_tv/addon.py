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

BASE = 'http://dokumenty.tv/'
SORT = 'orderby='
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36', 'Referer': BASE}
LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'dokumentytv.log')
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

class DokumentyTVContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp', session=None):
		ContentProvider.__init__(self, 'Dokumenty.tv', 'https://dokumenty.tv', username, password, filter, tmp_dir)
		self.session = session
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def parseHtml(self,html):
		result = []
		items = re.compile('<div id="post-([0-9]+)".*?class="clip-link".*?title="(.*?)".*?href="(.*?)".*?<img.*?src="(.*?)".*?datetime="(.*?)".*?class="entry-summary">(.*?)<', re.DOTALL).findall(html)
		for (id, title, iurl, img, dt, desc) in items:
			dt = datetime.datetime.strptime(dt.split("T")[0],'%Y-%m-%d').strftime('%d.%m.%Y')
			itm = self.dir_item()
			itm['url'] = iurl
			itm['img'] = img
			itm['title'] = title.replace('-dokument', '')
			itm['title'] = re.sub(CLEANR, '', itm['title']).strip()
			itm['plot'] = dt + " - " + desc.strip()
			result.append(itm)
		return result

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def search(self,keyword):
		result = []
		html = util.request(self.base_url+"?s="+keyword, headers=HEADERS)
		result = self.parseHtml(html)
		return result

	def categories(self):
		result = []
		result.append(self.dir_item(__addon__.getLocalizedString(30201), 'cat#'))
		result.append(self.dir_item(__addon__.getLocalizedString(30202), 'cat#category/historie/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30203), 'cat#category/katastroficke/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30204), 'cat#category/konspirace/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30205), 'cat#category/krimi/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30206), 'cat#category/mysleni/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30207), 'cat#category/prirodovedny-dokument/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30208), 'cat#category/technika/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30209), 'cat#category/vesmir/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30210), 'cat#category/zahady/'))
		result.append(self.dir_item(__addon__.getLocalizedString(30211), 'cat#category/zivotni-styl/'))
		return result

	def list(self, url):
		result = []
		if 'cat#' in url:
			tmp, cat = url.split("#")
			html = util.request(self.base_url+cat, headers=HEADERS)
			result = self.parseHtml(html)
			page = re.search('page/([0-9]+)', url, re.DOTALL)
			if page:
				result.append(self.dir_item('další',re.sub(r'page\/\d+\/','page/%s/' % (int(page.group(1))+1), url)))
			else:
				result.append(self.dir_item('další',url + 'page/2/'))
		else:
			try:
				html = util.request(url, headers=HEADERS)
			except HTTPError as e:
				if e.code == 403: showInfo(self.session, 'Toto video není dostupné.')
				return []
			items = re.compile('<iframe.*?src="(.*?)"', re.DOTALL).findall(html)
			for (url) in items:
				if url.startswith('//'): url = 'https:' + url
				if 'ok.ru' in url:
					html = util.request(url, headers=HEADERS)
					item = re.search('data-options="(.*?)"', html, re.DOTALL)
					if item:
						jsn = json.loads(item.group(1).replace('&quot;','"'))
						md = json.loads(jsn['flashvars']['metadata'])
						itm = self.video_item()
						itm['url'] = md['movie']['url']
						itm['img'] = md['movie']['poster']
						itm['title'] = md['movie']['title'].replace('-dokument', '')
						itm['title'] = re.sub(CLEANR, '', itm['title']).strip()
						result.append(itm)
				else:
					result.append(self.dir_item('None',''))
					showInfo(self.session, 'Nepodporovany poskytovatel: %s' % url)
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		self.info("URL: %s" % item['url'] )
		
		if 'ok.ru' in item['url']:
			html = util.request(item['url'], headers=HEADERS)
			item = re.search('data-options="(.*?)"', html, re.DOTALL)
			self.info("ITEM: %s" % item )
			if item:
				jsn = json.loads(item.group(1).replace('&quot;','"'))
				md = json.loads(jsn['flashvars']['metadata'])
				for i in md['videos']:
					name = i['name']
					itm = self.video_item()
					itm['title'] = name
					itm['surl'] = name
					if name == 'mobile':
						itm['quality']="144p"
					elif name == 'lowest':
						itm['quality']="240p"
					elif name=='low':
						itm['quality']="360p"
					elif name=='sd':
						itm['quality']="480p"
					elif name=='hd':
						itm['quality']="720p"
					elif name=='full':
						itm['quality']="1080p"
					else:
						itm['quality']="0p"
					itm['url']=i['url']
					itm['headers'] = HEADERS
					result.append(itm)
		else:
			showInfo(self.session, 'Nepodporovaný poskytovatel: %s' % item['url'])
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.dokumenty.tv')
addon_userdata_dir = __addon__.getAddonInfo('profile')

def dokumenty_tv_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}

	provider = DokumentyTVContentProvider(session=session)
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)

# #################################################################################################

def main(addon):
	return XBMCCompatInterface(dokumenty_tv_run)

# #################################################################################################
