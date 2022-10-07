# -*- coding: utf-8 -*-

# This code is based on https://github.com/Saros72/kodirepo/tree/main/repo-19/plugin.video.autosalontv from saros
# Thank you!

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Plugins.Extensions.archivCZSK.engine import client

import re
try:
	from bs4 import BeautifulSoup
	bs4_available = True
except:
	bs4_available = False
	
import requests
import json
import util

from provider import ContentProvider
import xbmcprovider

def get_page(url):
	r = requests.get(
		url,
		headers={
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36"
		},
	)
	return BeautifulSoup(r.content, "html.parser")


# ##################################################################################################################

class autosalontvContentProvider(ContentProvider):

	def __init__(self, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'autosalon.tv', 'https://autosalon.tv/', None, None, filter, tmp_dir)

	# ##################################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']
	
	# ##################################################################################################################
	
	def categories(self):
		if not bs4_available:
			client.showInfo("K fungování doplňku Autosalon.TV si musíte pomocí svého správce balíku doinstalovat BeautifulSoup4. Hledejte balík se jménem:\npython{0}-beautifulsoup4 nebo python{0}-bs4".format( '3' if sys.version_info[0] == 3 else '' ))  
			return []
		
		result = []
		
		item = self.dir_item("Autosalon TV", '#autosalon_tv')
		item['img'] = 'http://saros.wz.cz/repo/repo-v19/plugin.video.autosalontv/logo.png'
		result.append(item)
		
		item = self.dir_item("Auto-salón SK", '#autosalon_sk')
		item['img'] = 'http://www.auto-salon.sk/images/_PRISPEVKY/LOGO.jpg'
		result.append(item)
		
		return result
	
	# ##################################################################################################################
	
	def list(self, url ):
		if url == '#autosalon_tv':
			return self.autosalon_tv_season()
		if url == '#autosalon_sk':
			return self.autosalon_sk_list('0')
		elif url.startswith('#autosalon_tv_list#'):
			return self.autosalon_tv_list(url[19:])
		elif url.startswith('#autosalon_sk_list#'):
			return self.autosalon_sk_list(url[19:])
		
		return []
	
	# ##################################################################################################################
	
	def autosalon_tv_season(self):
		result = []
		
		soup = get_page('https://autosalon.tv/epizody')
		items = soup.find_all('div',{'class':'container-fluid cards-container cards-container-seasons'},True)
		
		for item in items:
			for x in range(0, len(item) + 2):
				title = item.find_all('h3')[x].string + '/ ' + item.find_all('h4')[x].string
				year = item.find_all('h3')[x].string[-5:]
				url = "https://autosalon.tv" + item.find_all('a')[x].attrs['href']
				
				ritem = self.dir_item( title, '#autosalon_tv_list#' + url)
				ritem['year'] = year
				result.append(ritem)
		
		return result
	
	# ##################################################################################################################

	def autosalon_tv_list(self, url_link):
		result = []
		
		soup = get_page(url_link)
		items = soup.find_all('div',{'class':'container-fluid cards-container cards-container-episodes'},True)
		
		for item in items:
			for x in range(0, len(item)):
				try:
					title = item.find_all('div',{'class':'title'}, True)[x].text
					title = title[:-10] + " - " + title[-10:]
					
					if title:
						img = item.find_all('img')[x].attrs['src'].replace("small", "large")
						plot = item.find_all('div',{'class':'subtitle'},True)[x].text
						url = "https://autosalon.tv" + item.find_all('a')[x].attrs['href']
						
						ritem = self.video_item( '#autosalon_tv_play#' + url)
						ritem['title'] = title
						ritem['plot'] = plot
						ritem['img'] = img
						result.append(ritem)
				except Exception as e:
					self.info("ERROR: %s" % str(e))
					pass
				
		return result

	# ##################################################################################################################
	
	def autosalon_sk_list(self, pg):
		result = []

		soup = get_page("http://www.auto-salon.sk/tv-relacia?id=28&pg=" + str(pg))

		items = soup.find_all('table',{'class':'articles-list'},True)
		paging = soup.find_all('div',{'class':'paging-arrows'},True)[1].find_all('a')
		
		for item in items:
			for x in range(0, len(item) - 1):
				i = item.find_all('h2',{'class':'articles-list-title'}, True)[x]
				title = i.text
				url = i.find_all('a')[0].attrs['href']
	
				ritem = self.video_item( '#autosalon_sk_play#' + url)
				ritem['title'] = title
				ritem['img'] = 'http://www.auto-salon.sk/images/_PRISPEVKY/LOGO.jpg'
				result.append(ritem)
				
		if paging != []:
			ritem = self.dir_item( 'Další', '#autosalon_sk_list#' + str(int(pg)+1))
			ritem['type'] = 'next'
			result.append(ritem)

		return result
	
	# ##################################################################################################################
	
	def resolve_streams(self, url ):
#		self.info("Master playlist URL: %s" % url)
		
		try:
			req = requests.get(url)
		except:
			self.error("Problém při načtení videa - URL neexistuje")
			return None
		
		if req.status_code != 200:
			self.showError("Problém při načtení videa - neočekávaný návratový kód %d" % req.status_code)
			return None

		res = []
		base_url = url[:url.rfind('/')]

		for m in re.finditer('#EXT-X-STREAM-INF:.*?,NAME=(?P<resolution>[^\s]+)\s(?P<chunklist>[^\s]+)', req.text, re.DOTALL):
			itm = {}
			itm['url'] = base_url + '/' + m.group('chunklist')
			itm['quality'] = m.group('resolution')
			self.info("Resolved URL: %s" % itm['url'])
			res.append(itm)
			
		res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
		
		return res
	
	# ##################################################################################################################
	
	def autosalon_tv_play(self, url_link):
		html = requests.get(url_link, headers = {"referer": "https://www.autosalon.tv/"}).content
		sid=re.findall('sid=(.*?)"',str(html), re.DOTALL)[0]
		
		html = requests.get("https://video.onnetwork.tv/embed.php?sid=" + sid, headers = {"referer": "https://www.autosalon.tv/"}).content
		ver = re.findall('version":"(.*?)"',str(html), re.DOTALL)[0]
		mid = re.findall('mid":"(.*?)"',str(html), re.DOTALL)[0]
		
		html = requests.get("https://video.onnetwork.tv/frame" + ver + ".php?mid=" + mid, headers = {"referer": "https://www.autosalon.tv/"}).content
		
		urls = re.findall('"hls"(.*?)3u8',str(html), re.DOTALL)[0]
		url = re.findall('"url": "(.*?).m',str(urls), re.DOTALL)[-1]
		stream = url.replace("\\", "") + ".m3u8"
		
		return stream
	
	# ##################################################################################################################
	
	def autosalon_sk_play(self, url_link):
		result = []
		
		req = requests.get(url_link).text
		id = re.findall('https://www.youtube.com/embed/(.*?)"',str(req), re.DOTALL)[0]
		
		try:
			video_formats = client.getVideoFormats('https://youtube.com/watch?v=' + str(id))
		except Exception as e:
			self.error("Failed to extract youtube video link: %s" % str(e))
			video_formats = None
			
		if video_formats:
			for vf in video_formats:
				if vf.get('fmt', 0) not in [38, 44, 43, 45, 46, 100, 101, 102]:
					result.append( { 'url': vf['url'], 'quality': vf['format_note'] } )
				
		return result

	# ##################################################################################################################
	
	def resolve(self, item, captcha_cb=None, select_cb=None ):
		if item['url'] == '#':
			return None
		
		if item['url'].startswith('#autosalon_tv_play#'):
			resolved_url = self.autosalon_tv_play( item['url'][19:] )

			if resolved_url:
				stream_links = self.resolve_streams( resolved_url )
			else:
				stream_links = []
			
		elif item['url'].startswith('#autosalon_sk_play#'):
			stream_links = self.autosalon_sk_play( item['url'][19:] )

		result = []
		for one in stream_links:
			item = item.copy()
			item['url'] = one['url']
			item['quality'] = one['quality']
			result.append(item)
			
		if select_cb and len(result) > 0:
			return select_cb(result)

		return result
		

######### main ###########

__scriptid__	= 'plugin.video.autosalontv'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__	= __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

provider = autosalontvContentProvider()

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
