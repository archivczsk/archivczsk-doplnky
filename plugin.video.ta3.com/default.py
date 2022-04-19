# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) Maros Ondrasek & Michal Novotny
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
import util
import re,json
import xbmcprovider
from datetime import datetime
from provider import ContentProvider
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Components.config import config
from Screens.MessageBox import MessageBox

try:
	from urllib2 import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urllib import quote_plus, addinfourl
	from urlparse import urljoin
except:
	from urllib.request import addinfourl, urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import quote_plus, urljoin


__scriptid__ = 'plugin.video.ta3.com'
__scriptname__ = 'ta3.com'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString

LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'ta3.log')

def writeLog(msg, type='INFO'):
		try:
				f = open(LOG_FILE, 'a')
				dtn = datetime.now()
				f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
				f.close()
		except:
				pass

def showInfo(msg, timeout=20):
	session.open(MessageBox, text=msg, timeout=timeout, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)

class TA3ContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'ta3.com', 'http://www.ta3.com/', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()
		self.cnt = 5

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def capabilities(self):
		return ['categories','resolve','search','!download']

	def categories(self):
		result = []
		item = self.video_item()
		item['title'] = 'Live'
		item['url'] = "live.html"
		result.append(item)
		result.append(self.dir_item(url=self.base_url + 'api/latest-episodes', type='new'))
		result.append(self.dir_item('Relácie', self.base_url + 'archiv'))
		result.append(self.dir_item('Slovensko', self.base_url + 'slovensko#w'))
		result.append(self.dir_item('Zahraničie', self.base_url + 'zahranicie#w'))
		result.append(self.dir_item('Ekonomika', self.base_url + 'ekonomika#w'))
		result.append(self.dir_item('Šport', self.base_url + 'sport#w'))
		result.append(self.dir_item('Spoločnosť', self.base_url + 'spolocnost#w'))
		result.append(self.dir_item('Tlačové besedy', self.base_url + 'tlacove-besedy#w'))
		result.append(self.dir_item('Regiony', self.base_url + 'regiony#w'))
		result.append(self.dir_item('Zdravie', self.base_url + 'zdravie#w'))
		return result

	def list(self, url):
		result = []

		if 'latest-episodes' in url:
			result.extend(self.list_latest(url))
			return result

		if 'archiv' in url:
			result.extend(self.list_categories(url))
			return result

		if '#w' in url:
			url = url.split("#")[0]
			result.extend(self.list_w(url))
			return result

		return self.list_videos(self._url(url))

	def search(self,keyword):
		result = []
		try:
			data = util.request(self.base_url + 'archiv?s=%s' % urllib.quote_plus(keyword))
			data = re.search(r'<section id="broadcast-categories-list">(.*?)</section>', data, re.S).group(1)
			for m in re.findall(r'<article.*?>(.*?)</article', data, re.DOTALL):
				try:
					url, title = re.search(r'<h3.*?>.*?<a href="(.*?)".*?>(.*?)</a>', m, re.S).groups()
					title = title.strip()
					try:
						img = re.search(r'<img.*?src="(.*?)".*>', m, re.S).group(1)
						dt = datetime.strptime(re.search(r'itemprop="date.*?>(.*?)</', m, re.S).group(1).strip().replace(",",""),'%d.%m.%Y %H:%M')
						title = '%s %s'%(dt.strftime("%d.%m.%y %H:%M"), title)
					except:
						pass
					item=self.video_item()
					item['url']=url
					item['title']=toString(title)
					item['img']=img
					item['plot']=toString(title)
					result.append(item)
				except:
					pass
		except:
			showInfo('Chyba vyhledávania.')
		return result

	def list_latest(self, url):
		result = []
		try:
			data = json.loads(util.request(url))
			for m in re.findall(r'<article.*?>(.*?)</article', data['html'], re.DOTALL):
				try:
					url, title = re.search(r'<h3.*?>.*?<a href="(.*?)".*?>(.*?)</a>', m, re.S).groups()
					title = title.strip()
					try:
						img = re.search(r'<img.*?src="(.*?)".*>', m, re.S).group(1)
						dt = datetime.strptime(re.search(r'itemprop="date.*?>(.*?)</', m, re.S).group(1).strip().replace(",",""),'%d.%m.%Y %H:%M')
						title = '%s %s'%(dt.strftime("%d.%m.%y %H:%M"), title)
					except:
						pass
					item=self.video_item()
					item['url']=url
					item['title']=toString(title)
					item['img']=img
					item['plot']=toString(title)
					result.append(item)
				except:
					pass
			if data['next_page_url']:
				self.cnt = self.cnt-1
				if self.cnt == 0:
					item = self.dir_item()
					item['type'] = 'next'
					item['url'] = data['next_page_url']
					self._filter(result, item)
				else:
					result.extend(self.list_latest(data['next_page_url']))
		except:
			showInfo('Chyba zpracovania.')
		return result

	def list_w(self, url):
		result = []
		try:
			data = util.request(url)
			# data = re.search(r'<section.*?id="articles-list">(.*?)</section', data, re.S).group(1)
			for m in re.findall(r'<article class="headline.*?>(.*?)</article', data, re.DOTALL):
				try:
					if not 'fa-video' in m: continue
					url, title = re.search(r'<h2.*?>.*?<a href="(.*?)".*?>(.*?)</a>', m, re.S).groups()
					title = title.strip()
					try:
						img = re.search(r'<img.*?src="(.*?)".*>', m, re.S).group(1)
						dt = datetime.strptime(re.search(r'itemprop="date.*?>(.*?)</', m, re.S).group(1).strip().replace(",",""),'%d.%m.%Y %H:%M')
						title = '%s %s'%(dt.strftime("%d.%m.%y %H:%M"), title)
					except:
						pass
					item=self.video_item()
					item['url']=url
					item['title']=toString(title)
					item['img']=img
					item['plot']=toString(title)
					result.append(item)
				except:
					pass
			pager_data = util.substr(data,'<div class="pagination-wrap"', '</div>')
			next_page_match = re.search(r'<a class="page-link" href="(?P<url>[^"]+)" rel="next"', pager_data)
			if next_page_match:
				item = self.dir_item()
				item['type'] = 'next'
				item['url'] = next_page_match.group('url').replace('&amp;','&')+"#w"
				self._filter(result, item)
		except:
			showInfo('Chyba zpracovania.')
		return result

	def list_categories(self, url):
		result = []
		try:
			page = util.request(url)
			if 'archiv' in url:
				start = '<section id="broadcast-categories-list">'
			else:
				self.error("_list_categories: unknown category url: %s" % url)
				return []
			data = util.substr(page, start, '</section>')
			for m in re.finditer('<a\ href=\"(?P<url>[^\"]+)\"\ title=\"(?P<title>[^\"]+)\"', data):
				item = self.dir_item()
				item['url'] = self.base_url + m.group('url') 
				item['title'] = m.group('title')
				self._filter(result, item)
			pager_data = util.substr(page,'<div class="pagination-wrap"', '</div>')
			next_page_match = re.search(r'<a class="page-link" href="(?P<url>[^"]+)" rel="next"', pager_data)
			if next_page_match:
				result.extend(self.list_categories(next_page_match.group('url').replace('&amp;','&')))
		except:
			showInfo('Chyba zpracovania.')
		return result

	def list_videos(self, url):
		result = []
		try:
			page = util.request(url)
			if '?page=' in url:
				data = util.substr(page, '<h4 class="archive-loop-title">Ďalšie v archíve</h4>','</main>')
			else:
				data = util.substr(page, '<main class="main"','</main>')
			for m in re.findall(r'<article.*?>(.*?)</article', data, re.DOTALL):
				try:
					url, title = re.search(r'<h2.*?>.*?<a href="(.*?)".*?>(.*?)</a>', m, re.S).groups()
					title = title.strip()
					try:
						img = re.search(r'<img.*?src="(.*?)".*>', m, re.S).group(1)
						dt = datetime.strptime(re.search(r'itemprop="date.*?>(.*?)</', m, re.S).group(1).strip().replace(",",""),'%d.%m.%Y %H:%M')
						title = '%s %s'%(dt.strftime("%d.%m.%y %H:%M"), title)
					except:
						pass
					item=self.video_item()
					item['url']=url
					item['title']=toString(title)
					item['img']=img
					item['plot']=toString(title)
					result.append(item)
				except:
					pass
			pager_data = util.substr(page,'<div class="pagination-wrap"', '</div>')
			next_page_match = re.search(r'<a class="page-link" href="(?P<url>[^"]+)" rel="next"', pager_data)
			if next_page_match:
				self.cnt = self.cnt-1
				if self.cnt == 0:
					item = self.dir_item()
					item['type'] = 'next'
					item['url'] = next_page_match.group('url').replace('&amp;','&')
					self._filter(result, item)
				else:
					result.extend(self.list_videos(next_page_match.group('url').replace('&amp;','&')))
		except:
			showInfo('Chyba zpracovania.')
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
	   item = item.copy()
	   if 'live.html' in item['url']:
		   result = self._resolve_live(item)
		   result = sorted(result, key=lambda x:x['quality'], reverse=True)
	   else:
		   result = self._resolve_vod(item)
	   if len(result) > 0 and select_cb:
		   return select_cb(result)
	   return result

	def _resolve_vod(self, item):
		resolved = []
		try:
			data = util.request(self._url(item['url']))
			video_id = re.search("LiveboxPlayer.archiv\(.+?videoId:\s*'([^']+)'", data, re.DOTALL).group(1)
			#print( "video_id: %s" % video_id )
			player_data = util.request("http://embed.livebox.cz/ta3_v2/vod-source.js", {'Referer':self._url(item['url'])})
			#print( "player_data: " % player_data )
			url_format = re.search(r'my.embedurl = \[\{"src" : "([^"]+)"', player_data).group(1)
			#print( "url_format: %s" % url_format )
			manifest_url = "https:" + url_format.format(video_id)
			#print( "manifest_url: %s" % manifest_url )
			manifest = util.request(manifest_url)
			print("manifest", manifest)
			for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+).*?(,RESOLUTION=(?P<resolution>\d+x\d+))?\s(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
				item = self.video_item()
				item['surl'] = item['title']
				item['quality'] = m.group('bandwidth')
				item['url'] = urljoin(manifest_url, m.group('chunklist'))
				resolved.append(item)
			resolved = sorted(resolved, key=lambda x:int(x['quality']), reverse=True)
			if len(resolved) == 3:
				qualities = ['720p', '480p', '360p']
				for idx, item in enumerate(resolved):
					item['quality'] = qualities[idx]
			else:
				for idx, item in enumerate(resolved):
					item['quality'] += 'b/s'
		except:
			showInfo('Chyba zpracovania videa.')
		return resolved

	def _resolve_live(self, item):
		resolved = []
		try:
			# data = util.request(self._url(item['url']))
			player_data = util.request("http://embed.livebox.cz/ta3_v2/live-source.js", {'Referer':self._url(item['url'])})
			#print( "player_data: " % player_data )
			for m_manifest in re.finditer(r'\{"src"\s*:\s*"([^"]+)"\s*\}', player_data, re.DOTALL):
				manifest_url = m_manifest.group(1)
				if manifest_url.startswith('//'):
				   manifest_url = 'http:'+ manifest_url
				#print( "manifest_url: %s" % manifest_url )
				req = Request(manifest_url)
				resp = urlopen(req)
				manifest = resp.read().decode('utf-8')
				resp.close()
				#print( "manifest: %s" % manifest )
				for m in re.finditer('RESOLUTION=\d+x(?P<resolution>\d+)\s*(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
					item = self.video_item()
					item['surl'] = item['title']
					item['quality'] = m.group('resolution') + 'p'
					item['url'] = resp.geturl().rsplit('/', 1)[0] + '/' + m.group('chunklist')
					resolved.append(item)
				# only first manifest url looks to be is valid
				break
		except:
			showInfo('Chyba zpracovania videa.')
		return resolved

settings = {'quality':__addon__.getSetting('quality')}

provider = TA3ContentProvider(tmp_dir='/tmp')

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
