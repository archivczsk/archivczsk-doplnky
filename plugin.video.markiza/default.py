# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) 2020 Michal Novotny https://github.com/misanov
# *	 based on https://github.com/rywko/plugin.video.markiza.sk for KODI
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
import resolver
import time
from datetime import date
import util
from provider import ContentProvider
from provider import ResolveException
import xbmcprovider

try:
	from urllib2 import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib import urlencode
	import cookielib
except:
	from urllib.request import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib.request import ssl as rssl
	from urllib.parse import urlencode
	import http.cookiejar as cookielib
	
######### contentprovider ##########

_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'
loginurl = 'https://moja.markiza.sk/'

#handle Sectigo CA cert missing in cacerts - disable SSL checks
try:
	import ssl
	
	def my_ssl_context(*args, **kwargs):
		ctx = ssl._create_unverified_context( *args, **kwargs )
		
		# this is needed for ssl with seclevel2 - too high for markiza
		ctx.set_ciphers( 'TLS13-AES-256-GCM-SHA384:TLS13-CHACHA20-POLY1305-SHA256:TLS13-AES-128-GCM-SHA256:ECDH+AESGCM:ECDH+CHACHA20:DH+AESGCM:DH+CHACHA20:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:DH+HIGH:RSA+AESGCM:RSA+AES:RSA+HIGH:!aNULL:!eNULL:!MD5:!3DES' )
		return ctx
		
	ssl._create_default_https_context = my_ssl_context #ssl._create_unverified_context
except:
	pass
	
def fetchUrl(url, opener=None, ref=None):
		httpdata = ''				
		req = Request(url)
		req.add_header('User-Agent', _UserAgent_)
		if ref:
			req.add_header('Referer', ref)
		if opener:
			resp = opener.open(req)
		else:
			resp = urlopen(req)
		httpdata = resp.read().decode('utf-8')
		resp.close()
		return httpdata

class markizaContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'markiza.sk', 'https://videoarchiv.markiza.sk/', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()

	def init_urllib(self):
		opener = build_opener(self.cp)
		self.opener = opener
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', '!download']
			
	def categories(self):
		result = []
		result.append(self.dir_item('Relácie a seriály A-Z', self.base_url + 'relacie-a-serialy'))
		result.append(self.dir_item('Televízne noviny', self.base_url + 'video/televizne-noviny'))
		result.append(self.dir_item('TOP relácie', 'top' ))
		result.append(self.dir_item('Najnovšie epizódy', 'new' ))
 
		item = self.video_item()
		item['title'] = 'Live Markiza'
		item['url'] = self.base_url + "live/1-markiza"
		item['img'] = "DefaultVideo.png"
		result.append(item)
		item = self.video_item()
		item['title'] = 'Live Doma'
		item['url'] = self.base_url + "live/3-doma"
		item['img'] = "DefaultVideo.png"
		result.append(item)
		item = self.video_item()
		item['title'] = 'Live Dajto'
		item['url'] = self.base_url + "live/2-dajto"
		item['img'] = "DefaultVideo.png"
		result.append(item)
		return result

	def list(self, url):
		self.info("list %s" % url)
		if 'relacie-a-serialy' in url:
			return self.list_show(url, list_series=True)
		elif 'top' == url:
			return self.list_top(self.base_url)
		elif 'new' == url:
			return self.list_new(self.base_url)
		return self.list_show(url, list_episodes=True)
	
	def list_top(self, url):
		result = []
		httpdata = util.request(url)
		reSection = re.search('TOP RELÁCIE(.*?)</section', httpdata, re.DOTALL)
		if not reSection:
			return []
		data = reSection.group(1)
		pattern = re.compile('<article.*?href="(.*?)".*?title="(.*?)".*?data-original="(.*?)"', re.DOTALL)
		it = re.finditer(pattern,data)
		for item in it:
			link,title,img = item.groups()
			item = self.dir_item()
			item['url'] = link
			item['title'] = title
			item['img'] = img
			result.append(item)
		return result

	def list_new(self, url):
		result = []
		httpdata = util.request(url)
		reSection = re.search('NAJNOVŠIE EPIZÓDY(.*?)</section', httpdata, re.DOTALL)
		if not reSection:
			return []
		data = reSection.group(1)
		pattern = re.compile(u'<article.*?href="(.*?)".*?data-original="(.*?)".*?"e-title">(.*?)<', re.DOTALL)
		it = re.finditer(pattern,data)
		for item in it:
			link,img,title = item.groups()
			item = self.video_item()
			item['url'] = link
			item['title'] = title
			item['img'] = img
			result.append(item)
		return result

	def list_show(self, url, list_series=False, list_episodes=False):
		result = []
		self.info("list_show %s"%(url))
		print('list_series: %s' % list_series)
		print('list_episodes: %s' % list_episodes)
		try:
			httpdata = util.request(url)
		except:
			raise ResolveException('CHYBA 404: STRÁNKA NEBOLA NÁJDENÁ')
			return

		if list_series:
			pattern = re.compile(u'<article.*?href="(.*?)".*?title="(.*?)".*?data-original="(.*?)"', re.DOTALL)
			it = re.finditer(pattern,httpdata)
			for item in it:
				link,title,img = item.groups()
				item = self.dir_item()
				item['url'] = link
				item['title'] = title
				item['img'] = img
				result.append(item)

		if list_episodes:
			pattern = re.compile(u'<article class="b-article b-article-text b-article-inline.*?href="(.*?)".*?title="(.*?)".*?data-original="(.*?)".*?b-content">(.*?)</div>', re.DOTALL)
			it = re.finditer(pattern,httpdata)
			for item in it:
				link,title,img,bcont = item.groups()
				reBcont = re.search('"e-title">(.*?)<.*?"e-date">(.*?)$', bcont, re.DOTALL)
				if reBcont:
					title = reBcont.group(1)+" - "+re.sub('<[^<]+?>', '', reBcont.group(2))
				item = self.video_item()
				item['url'] = link
				if self.base_url not in item['url']: # video neni na markize
					continue
				item['title'] = title
				item['img'] = img
				result.append(item)
			pattern = re.compile(u'<section class="b-main-section(.*?)</section', re.DOTALL)
			secit = re.finditer(pattern,httpdata)
			for gdata in secit:
				data = gdata.group(1)
				reSectionTitle = re.search('<h3 class="e-articles-title">(.*?)</h3>', data, re.DOTALL)
				sectionTitle = reSectionTitle.group(1)+" - " if reSectionTitle else ""
				pattern = re.compile(u'<article .*?href="(.*?)".*?title="(.*?)".*?data-original="(.*?)"', re.DOTALL)
				it = re.finditer(pattern,data)
				for item in it:
					link,title,img = item.groups()
					if 'voyo' in link: # video je na voyo
						title = "VOYO: "+title
					elif self.base_url not in link: # video neni na markize
						continue
					item = self.video_item()
					item['url'] = link
					item['title'] = sectionTitle+title
					item['img'] = img
					result.append(item)
				reDalsi = re.search('<div class="text-center">.*?href="(.*?)".*?js-load-next.*?>(.*?)</a>', data, re.DOTALL)
				if reDalsi:
					item = self.dir_item()
					item['url'] = reDalsi.group(1)
					item['title'] = reDalsi.group(2)
					result.append(item)

		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		item = item.copy()
		if 'markiza.sk/live/' in item['url']:
			result = self._resolve_live(item)
		else:
			result = self._resolve_vod(item)
		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

	def _resolve_vod(self, item):
		resolved = []
		httpdata = util.request(item['url'])
		reIframe = re.search('<main.*?<iframe src="(.*?)"', httpdata, re.DOTALL)
		if not reIframe:
			raise ResolveException('Platnost tohoto videa už vypršala')
			return
		url = reIframe.group(1)
		httpdata = fetchUrl(url)
		httpdata = httpdata.replace("\r","").replace("\n","").replace("\t","")
		if '<title>Error</title>' in httpdata:
			error=re.search('<h2 class="e-title">(.*?)</h2>', httpdata).group(1) #Video nie je dostupné vo vašej krajine
			raise ResolveException(error)
			return

		url = re.search('\"HLS\":\[{\"src\":\"(.+?)\"', httpdata)
		url = url.group(1).replace('\/','/')
		 
		thumb = re.search('<meta property="og:image" content="(.+?)">', httpdata)
		thumb = thumb.group(1) if thumb else ''
		name = re.search('<meta property="og:title" content="(.+?)">', httpdata)
		name = name.group(1) if name else '?'
		desc = re.search('<meta name="description" content="(.+?)">', httpdata)
		desc = desc.group(1) if desc else name

		httpdata = fetchUrl(url)

		streams = re.compile('RESOLUTION=\d+x(\d+).*\n([^#].+)').findall(httpdata) 
		url = url.rsplit('/', 1)[0] + '/'
		for (bitrate, stream) in streams:
			item = self.video_item()
			item['surl'] = item['title']
			item['quality'] = bitrate.replace('432','480')
			item['url'] = url + stream
			item['img'] = thumb
			resolved.append(item)
		resolved = sorted(resolved, key=lambda x:int(x['quality']), reverse=True)
		for idx, item in enumerate(resolved):
			item['quality'] += 'p'
		return resolved

	def _resolve_live(self, item, relogin=False):
		resolved = []
		if not (self.username and self.password):
			raise ResolveException('Nastavte prosím moja.markiza.sk konto')
			return
		if relogin:
			httpdata = fetchUrl(loginurl, self.opener)
			token = re.search(r'name=\"_token_\" value=\"(\S+?)\">',httpdata).group(1)
			logindata = urlencode({'email': self.username, 'password': self.password	 , '_token_': token, '_do': 'content1-loginForm-form-submit' }) + '&login=Prihl%C3%A1si%C5%A5+sa'
			req = Request(loginurl, logindata)
			httpdata = self.opener.open(req)
			
		httpdata = fetchUrl(item['url'], self.opener)
		url = re.search(r'<iframe src=\"(https:\/\/videoarchiv\S+?)\"',httpdata).group(1) #https://videoarchiv.markiza.sk/api/v1/user/live
		url = url.replace('&amp;','&')	
		httpdata = fetchUrl(url, self.opener)
		if '<iframe src=\"' not in httpdata:	#handle expired cookies
			if relogin:
			  raise ResolveException('Skontrolujte prihlasovacie údaje')
			  return 
			else:
			  return self._resolve_live(item, relogin=True) 
	 
		referer=url
		url = re.search(r'<iframe src=\"(https:\/\/media\S+?)\"',httpdata).group(1) #https://media.cms.markiza.sk/embed/
		httpdata = fetchUrl(url,self.opener,referer) 
		if '<title>Error</title>' in httpdata:
			error=re.search('<h2 class="e-title">(.*?)</h2>', httpdata).group(1) #Video nie je dostupné vo vašej krajine
			raise ResolveException(error)
			return 
		url = re.search(r'\"src\":\"(\S+?)\"',httpdata).group(1).replace('\/','/') #https:\/\/cmesk-ott-live-sec.ssl.cdn.cra.cz
		httpdata = fetchUrl(url,self.opener,'https://media.cms.markiza.sk/')
 
		streams = re.compile('RESOLUTION=\d+x(\d+).*\n([^#].+)').findall(httpdata)	
		url = url.rsplit('/', 1)[0] + '/'
		for (bitrate, stream) in streams:
			item = self.video_item()
			item['surl'] = item['title']
			item['quality'] = bitrate.replace('432','480').replace('640','720')	#adjust to predefined 360p, 480p and 720p
			item['url'] = url + stream + '|Referer=https://media.cms.markiza.sk/'
			resolved.append(item)
		resolved = sorted(resolved, key=lambda x:int(x['quality']), reverse=True)
		for idx, item in enumerate(resolved):
			item['quality'] += 'p'
		return resolved

######### main ###########

__scriptid__	= 'plugin.video.markiza'
__scriptname__ = 'markiza.sk'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__	= __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

provider = markizaContentProvider(username=__addon__.getSetting('markiza_user'), password=__addon__.getSetting('markiza_pass'))

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
