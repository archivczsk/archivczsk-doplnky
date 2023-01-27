# -*- coding: utf-8 -*-

# This code is based on https://github.com/xbmc-kodi-cz/plugin.video.novaplus.cz from wombat
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

_baseurl = "https://tv.nova.cz/"

def get_duration(dur):
	duration = 0
	l = dur.strip().split(":")
	for pos, value in enumerate(l[::-1]):
		duration += int(value) * 60**pos
	return duration


def img_res(url):
	if "314x175" in url:
		r = url.replace("314x175", "913x525")
	elif "275x153" in url:
		r = url.replace("275x153", "825x459")
	elif "276x383" in url:
		r = url.replace("276x383", "828x1149")
	else:
		r = url
	return r

def get_page(url):
	r = requests.get(
		url,
		headers={
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36"
		},
	)
	return BeautifulSoup(r.content, "html.parser")


# ##################################################################################################################

class novatvContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, list_voyo=True, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'tv.nova.cz', 'https://tv.nova.cz/', username, password, filter, tmp_dir)
		self.list_voyo = list_voyo

	# ##################################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']
	
	# ##################################################################################################################
	
	def categories(self):
		if not bs4_available:
			client.showInfo("K fungování doplňku TV Nova si musíte pomocí svého správce balíku doinstalovat BeautifulSoup4. Hledejte balík se jménem:\npython{0}-beautifulsoup4 nebo python{0}-bs4".format( '3' if sys.version_info[0] == 3 else '' ))  
			return []
		
		result = []
		
		item = self.video_item("#live#tn-live-live")
		item['title'] = 'TN Live'
		result.append(item)

		item = self.dir_item("Poslední epizody", '#list-recent-episodes')
		result.append(item)
		
		item = self.dir_item("TOP pořady", '#list-shows-menu')
		result.append(item)
		
		return result
	
	# ##################################################################################################################
	
	def list(self, url ):
		if url == '#list-recent-episodes':
			return self.list_recent_episodes()
		elif url == '#list-shows-menu':
			return self.list_shows_menu()
		elif url.startswith('#list-episodes#'):
			return self.list_episodes(url[15:])
		elif url.startswith('#list-episodes-with-cat#'):
			return self.list_episodes(url[24:], True)
		elif url.startswith('#list-categories#'):
			return self.list_episodes(url[17:])
		elif url.startswith('#list-shows#'):
			return self.list_shows(url[12:])
		
		return []
	
	# ##################################################################################################################
	
	def list_recent_episodes(self):
		result = []
		
		soup = get_page(_baseurl)
		
		dur = 0
		title = None
		show_title = None
		video = None

		article_hero = soup.find("div", {"class": "c-hero"})
		
		try:
			show_title = article_hero.find(
				"h2", {"class": "title"}).find("a").get_text()
				
			title = article_hero.find(
				"h3", {"class": "subtitle"}).find("a").get_text()
			
			dur = article_hero.find(
				"time", {"class": "duration"}).get_text()

			aired = article_hero.find("time", {"class": "date"})["datetime"]
			video = article_hero.find(
				"div", {"class": "actions"}).find("a")["href"]
		except:
			pass

		if video:
			item = self.video_item(video)
			item['title'] = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			item['img'] = img_res(article_hero.find("img")["data-src"])

			if dur:
				item['duration'] = get_duration( re.sub(r"[a-z]", ':', (dur.replace(" ", "")))[:-1])
			
			result.append(item)
		
		articles = soup.find( "div",
			{
				"class": "c-article-transformer-carousel swiper-container js-article-transformer-carousel"
			},
		).find_all("article")
		
		for article in articles:
			menuitems = []
	
			show_title = article["data-tracking-tile-show-name"]
			title = article["data-tracking-tile-name"]
			dur = article.find("time", {"class": "duration"})
			show_url = article.find("a", {"class": "category"})["href"]
	
			item = self.video_item( article.find("a", {"class": "img"})["href"] )
			item['title'] = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			item['img'] = img_res(article.find("picture").find("source")["data-srcset"])
			
			if dur:
				item['duration'] = get_duration(dur.get_text())
			
			item['menu'] = { 'Přejít na pořad': { 'list': '#list-episodes-with-cat#' + show_url }}
			
			result.append(item)
			
		return result

	# ##################################################################################################################
	
	def list_shows_menu(self):
		result = []
		
		item = self.dir_item('Nejlepší', '#list-shows#0' )
		result.append(item)

		item = self.dir_item('Nejnovější', '#list-shows#1' )
		result.append(item)

		item = self.dir_item('Všechny', '#list-shows#2' )
		result.append(item)

		return result
	
	# ##################################################################################################################
	
	def list_shows(self, show_type):
		result = []
		
		soup = get_page(_baseurl + "porady")
		
		if show_type == '0':
			selector = 'c-show-wrapper -highlight tab-pane fade show active'
		elif show_type == '1':
			selector = 'c-show-wrapper -highlight tab-pane fade'
		else:
			selector = 'c-show-wrapper'
			
		articles = soup.find("div", {"class": selector}).find_all("a")
	
		for article in articles:
			title = article["data-tracking-tile-name"]
			
			item = self.dir_item(title, '#list-episodes-with-cat#' + article["href"] )
			item['img'] = img_res(article.div.img["data-src"])
			result.append(item)
	
		return result
	
	# ##################################################################################################################
	
	def list_categories(self, url):
		result = []
		
		listing = []
		soup = get_page(url + "/videa")
		navs = soup.find("nav", "c-tabs")
		
		if navs:
			for nav in navs.find_all("a"):
				item = self.dir_item(nav.get_text(), '#list-episodes#' + nav['href'])
				result.append(item)
		
		return result

	# ##################################################################################################################
	
	def list_episodes(self, url, category=False):
		result = []
		listing = []
		
		if category:
			item = self.dir_item("Kategorie", '#list-categories#' + url)
			result.append(item)
			url += "/videa/cele-dily"
			
		soup = get_page(url)
		
		try:
			articles = soup.find(
				"div", "c-article-wrapper").find_all("article", "c-article")
		except:
			articles = []
			
		count = 0
		for article in articles:
			
			show_title = article["data-tracking-tile-show-name"]
			title = article["data-tracking-tile-name"]
			dur = article.find("time", {"class": "duration"})
	
			item = self.video_item( article.find("a", {"class": "img"})["href"] )
			item['title'] = "{0} - [COLOR yellow]{1}[/COLOR]".format(show_title, title)
			item['img'] = img_res(article.find("picture").find("source")["data-srcset"])
			
			if dur:
				item['duration'] = get_duration(dur.get_text())
			
			if '-voyo' in article['class']:
				if self.list_voyo:
					item['title'] = '* ' + item['title']
					item['url'] = '#'
					result.append(item)
			else:
				result.append(item)
			
			count += 1
				
		next = soup.find("div", {"class": "js-load-more-trigger"})
		if next and count > 0:
			item = self.dir_item( 'Další', '#list-episodes#' + next.find("button")["data-href"] )
			item['type'] = 'next'
			result.append(item)

		return result
	
	# ##################################################################################################################
	
	def resolve_streams(self, url ):
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

		for m in re.finditer('#EXT-X-STREAM-INF:.*?,RESOLUTION=(?P<resolution>[^\s]+)\s(?P<chunklist>[^\s]+)', req.text, re.DOTALL):
			itm = {}
			itm['url'] = base_url + '/' + m.group('chunklist')
			itm['quality'] = m.group('resolution')
			self.info("Resolved URL: %s" % itm['url'])
			res.append(itm)
			
		res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
		
		return res
	
	# ##################################################################################################################
	
	def resolve(self, item, captcha_cb=None, select_cb=None ):
		resolved_url = None
		
		if item['url'] == '#':
			return None
		
		if item['url'].startswith('#live#'):
			url = item['url'][6:]
			response = requests.get('https://media.cms.nova.cz/embed/'+url+'?autoplay=1', verify=False, headers={"referer": "https://tv.nova.cz/"})
			
			if response.status_code == 200:
				data = re.search("processAdTagModifier\(\{(.*?)\}\)", response.text, re.S)
	
				if data:
					plr = json.loads('{'+data.group(1)+'}')
					resolved_url = plr["tracks"]["HLS"][0]["src"]
		else:
			soup = get_page(item['url'])
			embeded_url = soup.find("div", {"class": "js-login-player"}).find("iframe")["data-src"]
#			self.info("Embedded url: %s" % embeded_url)
			embeded = get_page( embeded_url )
			
			try:
				json_data = json.loads(
					re.compile('{"tracks":(.+?),"duration"').findall(str(embeded))[0]
				)
			except:
				json_data = None
		
			if json_data:
#				self.info("json_data: %s" % json_data)
				stream_data = json_data['HLS'][0]
		
				if not "drm" in stream_data:
					resolved_url = stream_data["src"]
			else:
				embeded_text = embeded.get_text()
#				self.info(embeded_text)
				if 'Error' in embeded_text:
					embeded_text = embeded_text.replace('Error', '').strip()
					if '\n' in embeded_text:
						embeded_text = embeded_text[embeded_text.rfind('\n'):]
						
					client.showInfo("Nepodařilo se přehrát video: %s" % embeded_text.replace('Error', '').strip())

		if resolved_url:
			stream_links = self.resolve_streams( resolved_url )
		else:
			stream_links = []
		
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

__scriptid__	= 'plugin.video.novaplus'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__	= __addon__.getLocalizedString

settings = {'quality':__addon__.getSetting('quality')}

provider = novatvContentProvider(username=__addon__.getSetting('username'), password=__addon__.getSetting('password'), list_voyo=__addon__.getSetting('list-voyo')=='true')

xbmcprovider.XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
