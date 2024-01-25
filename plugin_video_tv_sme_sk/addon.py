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
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Plugins.Extensions.archivCZSK.engine import client

import re
import time
from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ContentProvider, ResolveException
from tools_xbmc.tools import util
from tools_xbmc.compat import XBMCCompatInterface

from xml.etree import ElementTree as ET
from email.utils import parsedate_tz, mktime_tz

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urlparse import urljoin
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import urljoin


class TVSMEContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp', session=None):
		ContentProvider.__init__(self, 'TV SME.sk', 'https://video.sme.sk/', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()
		self.session = session

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	def categories(self):
		result = []
		result.append(self.dir_item('Najnovšie videá', self.base_url+'rss'))
		result.append(self.dir_item('Spravodajstvo', self.base_url+'r/7026/spravodajstvo.html'))
		result.append(self.dir_item('Publicistika', self.base_url+'r/7028/publicistika.html'))
		result.append(self.dir_item('Zábava', self.base_url+'r/7031/zabava.html'))
		result.append(self.dir_item('Zoznam relácií', self.base_url+'relacie/'))
		result.append(self.dir_item('Hledat', self.base_url+'search?'))
		return result

	def list(self, url):
		result = []
		# najnovsie
		if 'rss' in url:
			xml = ET.fromstring(util.request(url))
			for i in xml.find('channel').findall('item'):
				item = self.video_item()
				item['title'] = toString(i.find('title').text).strip().replace('(video)','')
				item['url'] = i.find('link').text
				item['img'] = i.find('enclosure').attrib['url']
				item['plot'] = time.strftime('%d.%m.%Y %H:%M:%S',time.localtime(mktime_tz(parsedate_tz(i.find('pubDate').text)))) + ' - ' + i.find('description').text
				self._filter(result, item)
			return result

		# hledat
		if 'search?' in url:
			query = client.getTextInput(self.session, "Hledat")
			if len(query) == 0:
#				showError("Je potřeba zadat vyhledávaný řetězec")
#				result.append(self.video_item('Je potřeba zadat vyhledávaný řetězec','#'))
				return []
			httpdata = util.request(self.base_url+'search?q='+query+'&period=180&order=date')
			items = re.compile(u'<div class=\".+?media-two-cols\">.+?<a href="(.+?)">(.+?)</a>.+?<img src="(.+?)".+?alt="(.*?)"', re.DOTALL).findall(httpdata)
			for link,name,img,plot in items:
				print( "link: %s, name: %s, img: %s, plot: %s" % (link, name, img, plot) )
				item = self.video_item()
				item['title'] = name
				item['url'] = link
				item['img'] = img
				item['plot'] = plot
				result.append(item)
			return result

		# zoznam relacii
		if 'relacie' in url:
			httpdata = util.request(url)
			items = re.compile(u'<div class=\"col-sm col-3-sm px-s px-m-mo\">.+?<a href="(.+?)" title="(.+?)" class="tvshows-item">.+?<img src="(.+?)"', re.DOTALL).findall(httpdata)
			for link,name,img in items:
				result.append(self.dir_item(name,link))
			return result

		# episody
		httpdata = util.request(url)
		beg_idx=httpdata.find('class="video-row')
		end_idx=httpdata.find('id="js-paging"')
		data=httpdata[beg_idx:end_idx]
		pattern = re.compile('data-deep-tags=\"position-[0-9]+\" class=\"video-box-tile\".+?href=\"(.+?)\">.+?<img class=\"video-box-tile-img\" src=\"(.+?)\".+?>.+?<h2.*?>(.+?)</h2>.+?<span class=\"media-box-author.*?>(.+?)</span>.+?(?:(?:<time datetime=\"(.+?)\">)|(?:</a>.+?<a))', re.DOTALL)
		it = re.finditer(pattern,data)
		for item in it:
			link,img,title,authors,duration = item.groups()
			item = self.video_item()
			item['title'] = toString(title.strip().replace('(video)',''))
			item['url'] = link
			item['img'] = img
			item['plot'] = duration
			self._filter(result, item)
		nextlink=re.compile('<link rel=\"next\" href=\"(.+?)\">', re.DOTALL).search(httpdata)
		if nextlink:
			if not nextlink.group(1).startswith('http'):
				url=self.base_url+nextlink.group(1)[1:]
			else:
				url=nextlink.group(1)
			result.append(self.dir_item('Nasledujúce články',url))
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		item = item.copy()
		result = []
		data = util.request(self._url(item['url']))
		try:
			video_id = re.search("//cdn.jwplayer.com/players/([a-zA-Z0-9]*)", data, re.DOTALL).group(1)
		except:
			match = re.compile(r'<iframe src=\"//www\.youtube\.com/embed/(.+?)\"', re.DOTALL).search(data)
			if match:
				return self._getYT('https://www.youtube.com/watch?v='+match.group(1))
			else:
				match = re.compile(r'<iframe src=\"//(.*?sme\.sk/vp/.+?)\"', re.DOTALL).search(data)
				if match:
					data = util.request(self._url('http://'+match.group(1)))
					match = re.compile(r'<iframe src=\"//www\.youtube\.com/embed/(.+?)\"', re.DOTALL).search(data)
					if match:
						return self._getYT('https://www.youtube.com/watch?v='+match.group(1))
					else:
						raise ResolveException('Video nenalezeno')
				else:
					raise ResolveException('Video nenalezeno')
		manifest_url = "http://cdn.jwplayer.com/manifests/" + video_id + ".m3u8"
		manifest = util.request(manifest_url)
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+),RESOLUTION=\d+x(?P<resolution>\d+),.*?\s(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
			item = self.video_item()
			item['surl'] = item['title']
			item['quality'] = m.group('resolution')
			item['url'] = urljoin(manifest_url, m.group('chunklist'))
			result.append(item)
		result = sorted(result, key=lambda x:int(x['quality']), reverse=True)
		for idx, item in enumerate(result):
			item['quality'] += "p"
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

	def _getYT(self, url):
		print( "url: %s" % url )
		result = []
		video_formats = client.getVideoFormats(url)
		if video_formats and len(video_formats) > 0:
			video_url = [video_formats[-1]]
			print( 'videourl: %s' % video_url[:] )
		else:
			raise ResolveException('Video nenalezeno')
		i = video_url[:][0]
		item = self.video_item()
		try:
			item['title'] = i['title']
		except KeyError:
			pass
		item['url'] = i['url']
		item['quality'] = i['format_note']
		item['headers'] = {}
		try:
			item['fmt'] = i['fmt']
		except KeyError:
			pass
		result.append(item)
		return result


def sme_run(session, params, addon):
	settings = {'quality':addon.getSetting('quality')}
	provider = TVSMEContentProvider(tmp_dir='/tmp', session=session)
	XBMCMultiResolverContentProvider(provider, settings, addon, session).run(params)

def main(addon):
	return XBMCCompatInterface(sme_run, addon)
