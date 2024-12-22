# -*- coding: utf-8 -*-
#
# plugin.video.idnestv
#
# (c) Michal Novotny
#
# original at https://www.github.com/misanov/
#
# Free for non-commercial use under author's permissions
# Credits must be used

import re,sys,os,datetime,json
from Components.config import config

from tools_xbmc.dmd_czech.util import addDir, addLink, addSearch, getSearch

try:
	from urllib2 import urlopen, Request
	from urllib import unquote_plus
except:
	from urllib.request import urlopen, Request
	from urllib.parse import unquote_plus

__baseurl__ = 'https://tv.idnes.cz/'
_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'

def idnes_run(addon, session, params):

	class loguj(object):
		ERROR = 0
		INFO = 1
		DEBUG = 2
		mode = INFO

		logEnabled = True
		logDebugEnabled = False
		LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(), 'idnestv.log')

		@staticmethod
		def logDebug(msg):
			if loguj.logDebugEnabled:
				loguj.writeLog(msg, 'DEBUG')

		@staticmethod
		def logInfo(msg):
			loguj.writeLog(msg, 'INFO')

		@staticmethod
		def logError(msg):
			loguj.writeLog(msg, 'ERROR')

		@staticmethod
		def writeLog(msg, type):
			try:
				if not loguj.logEnabled:
					return
				f = open(loguj.LOG_FILE, 'a')
				dtn = datetime.datetime.now()
				f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
				f.close()
			except:
				pass

	def get_url(url, encoding='windows-1250'):
		req = Request(url)
		req.add_header('User-Agent', _UserAgent_)
		req.add_header('Cookie', 'mafra=1111,all=1,reklama=1,part=0,cpex=1,google=1,gemius=1,id5=1,next=0000,onlajny=0000,jenzeny=0000,databazeknih=0000,autojournal=0000,skodahome=0000,skodaklasik=0000,groupm=1,piano=1,seznam=1,geozo=0,czaid=1,click=1,verze=2,')
		response = urlopen(req)
		data = response.read()
		response.close()
		return data.decode(encoding)

	def OBSAH():
		html = get_url(__baseurl__)
		menu = re.search("<menu .*?(.*?)</menu>", html, re.S)
		if menu:
			menuitems = re.findall('<li.*?href="//(.*?)".*?>(.*?)</a>', menu.group(1), re.S)
			if menuitems:
				for item in menuitems:
					addDir(item[1], 'https://' + item[0], 2, None, 1)
		CATEGORY(html, __baseurl__)

	def CATEGORY(html, url):
		#loguj.logInfo('CURL: '+str(url))
		if html is "":
			html = get_url(url)
		articles = re.findall('<a.*?class="art-link.*?href="(.*?)".*?>(.*?)</a>', html, re.S)
		articleskino = re.findall('<a.*?class="video-art.*?href="(.*?)".*?>.*?<img.*?src="(.*?)".*?alt="(.*?)"', html, re.S)
		articleskinoepizody = re.findall('<li >.*?href="(.*?)" class="video-art".*?<img.*?src="(.*?)".*?<span>(.*?)</span>', html, re.S)
		if articles:
			for article in articles:
				src = article[0]
				typ = 2
				if re.search('art-info', article[1], re.S): # kdyz je info, pak je to video
					typ = 4
				try:
					title = re.search('<h3>(.*?)</h3>', article[1], re.S).group(1).strip()
				except:
					title = ""
				try:
					desc = title + "[CR][CR]Vydano: " + re.search('class="time".*?>(.*?)<', article[1], re.S).group(1).strip() + "[CR]Delka: " + re.search('<span class="length">(.*?)</span>', article[1], re.S).group(1).strip()
				except:
					desc = ""
				try:
					thumb = 'https:' + re.search("background-image:url\('(.*?)'\)", article[1], re.S).group(1)
				except:
					thumb = None
				addDir(title, src, typ, thumb, 1, desc)
		else: ### zkusime jestli to neni kino
			if articleskino:
				for article in articleskino:
					if article[2]:
						addDir(article[2].strip(), 'https:' + article[0], 2, article[1], "")
			if articleskinoepizody:
				for article in articleskinoepizody:
					if article[2]:
						addDir(article[2].strip(), article[0], 4, 'https:' + article[1], "")
	#		 addLink("[COLOR red]Chyba načítání pořadů[/COLOR]","#",None,"")

		try:
			urlnext = re.search('class="next-art.*?href.*?"(.*?)">', html, re.S).group(1)
			if __baseurl__ not in urlnext:
				urlnext = url + urlnext
			addDir("[COLOR blue]Další strana >>>[/COLOR]", urlnext, 2, None, 1, "Přejít na další stránku")
		except:
			pass

	def VIDEOLINK(url):
		html = get_url(url)

		try:
			title = re.search('<meta property="og:title" content="(.*?)"', html, re.S).group(1)
		except:
			title = ""
		try:
			image = re.search('<meta property="og:image" content="(.*?)"', html, re.S).group(1)
		except:
			image = None
		try:
			descr = re.search('<meta property="og:description" content="(.*?)"', html, re.S).group(1)
		except:
			descr = ""

		try:
			idv = re.search('<base href=.*?idvideo=(.*?)"', html, re.S).group(1)
			html = get_url('https://servix.idnes.cz/media/video.aspx?idvideo=' + idv + '&type=js', 'utf-8')
			json_payload = re.search(r'VideoPlayer.data\("", (.*)\);', html).group(1)
			jsondata = json.loads(json_payload)
			name = jsondata['items'][1]['title']
			thumb = jsondata['items'][1]['image']
			for item in jsondata['items'][1]['video']:
				if item['format'] == 'apple' or item['format'] == 'mp4':
					if item['quality'] == 'high':
						item['quality'] = '720'
					if item['quality'] == 'middle':
						item['quality'] = '360'
					addLink('[' + item['quality'] + '] ' + name, item['file'].replace('https', 'http'), thumb, descr)
		except:
			addLink("[COLOR red]Video nelze načíst[/COLOR]", "#", None, None)

	name = None
	url = None
	mode = None
	thumb = None
	page = None
	desc = None

	try:
			url = unquote_plus(params["url"])
	except:
			pass
	try:
			name = unquote_plus(params["name"])
	except:
			pass
	try:
			mode = int(params["mode"])
	except:
			pass
	try:
			page = int(params["page"])
	except:
			pass
	try:
			thumb = unquote_plus(params["thumb"])
	except:
			pass

	#loguj.logInfo('URL: '+str(url))
	#loguj.logInfo('NAME: '+str(name))
	#loguj.logInfo('MODE: '+str(mode))
	#loguj.logInfo('PAGE: '+str(page))
	#loguj.logInfo('IMG: '+str(thumb))

	if mode == None or url == None or len(url) < 1:
			OBSAH()
	elif mode == 2:
			CATEGORY("", url)
	elif mode == 4:
			VIDEOLINK(url)


def main(addon):
	return idnes_run
