# -*- coding: utf-8 -*-
import re,os,string,time,base64,datetime,json
from parseutils import *
from util import addDir, addLink, addSearch, getSearch
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import add_video
from Plugins.Extensions.archivCZSK.engine import client
from Screens.MessageBox import MessageBox

try:
	from urllib import unquote_plus
except:
	from urllib.parse import unquote_plus

import requests

__baseurl__ = 'http://novaplus.nova.cz'
__dmdbase__ = 'http://iamm.uvadi.cz/xbmc/voyo/'
_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'
addon =	 ArchivCZSK.get_xbmc_addon('plugin.video.novaplus')
profile = addon.getAddonInfo('profile')
__settings__ = addon
home = __settings__.getAddonInfo('path')
icon =	os.path.join( home, 'icon.png' )

def get_url(url,headers={}):
	headers['User-Agent'] = _UserAgent_
	
	response = requests.get( url, headers=headers, verify=False )

	if response.status_code == 200:
		return response.text
	
	return ''

class loguj(object):
	ERROR = 0
	INFO = 1
	DEBUG = 2
	mode = INFO

	logEnabled = True
	logDebugEnabled = False
	LOG_FILE = os.path.join(home,'novaplus.log')

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

def OBSAH():
	ch = {}
	html = get_url('https://novaplus.nova.cz/sledujte-zive/1-nova')
	sections = re.findall("class=\"js-channels-navigation-carousel(.*?)s-content-wrapper", html, re.S)
	for section in sections:
		chans = re.findall("img.*?alt=\"(.*?)\".*?<h4.*?>(.*?)</h4>.*?e-time-start\">(.*?)<.*?e-time-end\">(.*?)<", section, re.S)
		for chan in chans:
			ch[chan[0]] = ' (' + chan[1].replace("&nbsp;", " ") + ' ' + chan[2] + ' - ' + chan[3] + ')'
	addDir('ŽIVĚ - Nova'+ch.get('Nova',''),'nova-live',7,None,1)
	addDir('ŽIVĚ - TN Live'+re.compile('<.*?>').sub('', ch.get('TN LIVE','')),'tn-live-live',7,None,1)
	addDir('ŽIVĚ - Nova Cinema'+ch.get('Nova Cinema',''),'nova-cinema-live',7,None,1)
	addDir('ŽIVĚ - Nova Action'+ch.get('Nova Action',''),'nova-action-live',7,None,1)
	addDir('ŽIVĚ - Nova Fun'+ch.get('Nova Fun',''),'nova-fun-live',7,None,1)
	addDir('ŽIVĚ - Nova Lady'+ch.get('Nova Lady',''),'nova-lady-live',7,None,1)
	addDir('ŽIVĚ - Nova Gold'+ch.get('Nova Gold',''),'nova-gold-live',7,None,1)
	addDir('Úvodní stránka','http://novaplus.nova.cz/',6,None,1)
	addDir('Seriály a pořady','http://novaplus.nova.cz/porady/',5,None,1)
	addDir('Televizní noviny','http://novaplus.nova.cz/porad/televizni-noviny',2,None,1)
	addDir('Víkend','http://novaplus.nova.cz/porad/vikend',2,None,1)
	addDir('Koření','http://novaplus.nova.cz/porad/koreni',2,None,1)
	addDir('Střepiny','http://novaplus.nova.cz/porad/strepiny',2,None,1)


def HOMEPAGE(url,page):	 # new by MN
	html = get_url(url)

	# carousel
	sections = re.search("<section class=\"b-main-section\">.*?<div class=\"b-carousel\">.*?<a href=\"(.*?)\" title=\"(.*?)\">.*?<img.*?data-original=\"(.*?)\"", html, re.S)
	if sections != None:
		addDir(sections.group(2).replace('&nbsp;', ' '), sections.group(1), 3, sections.group(3), 1);

	# articles
	sections = re.findall("<h3 class=\"e-articles-title\">(.*?)</h3>(.*?)</section>", html, re.S)
	if sections != None:
		for section in sections:
			category = re.sub(r'<[^>]*?>', '',section[0]).replace('&nbsp;', ' ').replace('	',' ').replace('\n','').strip()
			articles = re.findall("<article(.*?)</article>", section[1], re.S)
			if category == "TOP POŘADY":
				Hmode = 2
			else:
				Hmode = 3
			if articles != None:
				for article in articles:
					url = re.search("<a href=\"(.*?)\"", article, re.S) or ""
					title = re.search("<a.*?title=\"(.*?)\"", article, re.S) or ""
					title = re.search("<span class=\"e-text\">(.*?)<\/span>", article, re.S) or title
					thumb = re.search("<img.*?data-original=\"(.*?)\"", article, re.S) or ""
					if url != "" and title != "":
						if thumb != "":
							addDir(category + " - " + title.group(1).replace('&nbsp;', ' '),url.group(1),Hmode,thumb.group(1),1)
						else:
							addDir(category + " - " + title.group(1).replace('&nbsp;', ' '),url.group(1),Hmode,None,1)
			else:
				session.open(MessageBox, text='Chyba načítání pořadů', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)
	else:
		session.open(MessageBox, text='Chyba načítání kategorie', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)

def CATEGORIES(url,page):  # rewrite by MN
	html = get_url(url)
	section = re.search("<div class=\"b-show-listing\".*?ady</h3>(.*?)</section>", html, re.S)
	if section != None:
		articles = re.findall("<article(.*?)</article>", section.group(1), re.S)
		if articles != None:
			for article in articles:
				url = re.search("<a href=\"(.*?)\"", article, re.S) or ""
				title = re.search("<a.*?title=\"(.*?)\"", article, re.S) or ""
				thumb = re.search("<img.*?data-original=\"(.*?)\"", article, re.S) or ""
				if url != "" and title != "":
					if thumb != "":
						addDir(title.group(1).replace('&nbsp;', ' '),url.group(1),2,thumb.group(1),1)
					else:
						addDir(title.group(1).replace('&nbsp;', ' '),url.group(1),2,None,1)
		else:
			session.open(MessageBox, text='Chyba načítání pořadů', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)
	else:
		session.open(MessageBox, text='Chyba načítání kategorie', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)

def EPISODES(url,name): # rewrite by MN
	html = get_url(url)

	# zalozky
	section = re.search("<nav class=\"navigation js-show-detail-nav\">(.*?)</nav>", html, re.S)
	if section != None:
		lis = re.findall("<li(.*?)</li>", section.group(1), re.S)
		if lis != None:
			for li in lis:
				url2 = re.search("<a href=\"(.*?)\"", li, re.S) or ""
				title = re.search("<a.*?title=\"(.*?)\"", li, re.S) or ""
				if url2 != "" and title != "":
					if url == url2.group(1):
						addDir('[I][COLOR yellow]' + title.group(1).replace('&nbsp;', ' ') + '[/COLOR][/I]',url2.group(1),2,None,1)
					else:
						addDir('[COLOR yellow]' + title.group(1).replace('&nbsp;', ' ') + '[/COLOR]',url2.group(1),2,None,1)

	# dalsi dily poradu
	prodId = re.search('<button data-href=.*?content=(.*?)&', html, re.S)
	if prodId and prodId.group(1):
		html = get_url('https://novaplus.nova.cz/api/v1/mixed/more?page=1&offset=0&content='+prodId.group(1)+'&limit=80')
	articles = re.findall("<article class=\"b-article-news m-layout-playlist\">(.*?)</article>", html, re.S)
	if articles != None:
		for article in articles:
			url = re.search("<a href=\"(.*?)\"", article, re.S) or ""
			if url != "" and url.group(1).find('voyo') == -1:
				title = re.search("<a.*?title=\"(.*?)\"", article, re.S) or ""
				thumb = re.search("<img.*?data-original=\"(.*?)\"", article, re.S) or ""
				if thumb != "":
					addDir(title.group(1).replace('&nbsp;', ' '),url.group(1),3,thumb.group(1),1)
				else:
					addDir(title.group(1).replace('&nbsp;', ' '),url.group(1),3,None,1)

def VIDEOLINK(url,name):	# rewrite by MN
	html = get_url(url)

	# nalezeni hlavniho article
	aarticle = re.search("<div class=\"b-article b-article-main\">(.*?)", html, re.S)

	# pokud hlavni article neexistuje, jsme na specialni strance se seznamem dilu a hledame odkaz
	if aarticle is None and html.find('property="og:url" content="http://voyo.nova.cz/') != -1:
		session.open(MessageBox, text='Video lze přehrát jen na voyo.nova.cz', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)
		return

	# pokud stale hlavni article neexistuje, chyba
	if aarticle is None:
		message = 'Na stránce nenalezena sekce s videi. Pravděpodpobně se jedná o placený obsah VOYO. '+url
		session.open(MessageBox, text=message, timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)
		return
	else:
		article = aarticle.group(1)

	# nazev
	aname = re.search("<h2 class=\"subtitle\">(.*?)</h2>", html, re.S)
	if aname is None:
		name = "Jméno pořadu nenalezeno"
	else:
		name = aname.group(1)

	# popis (nemusi byt vzdy uveden)
	adesc = re.search("<div class=\"e-description\">(.*?)</div>", article, re.S)
	if adesc is None:
		desc = ""
	else:
		desc = adesc.group(1).re.sub(r'<[^>]*?>', '', value).replace('&nbsp;', ' ')

	# nalezeni iframe
	iframe = re.search("<div class=\"video-holder\">.*?iframe src=\"(.*?)\"", html, re.S)
	if iframe != None:
		url = iframe.group(1)
	else:
		url = None

	# nacteni a zpracovani iframe
	httpdata = get_url( url ) 

	httpdata   = httpdata.replace("\r","").replace("\n","").replace("\t","")

	thumb = re.compile('<meta property="og:image" content="(.+?)">').findall(httpdata)
	thumb = thumb[0] if len(thumb) > 0 else ''

	re_src = re.compile('var src = \{(.*?)\}').findall(httpdata);
	if len(re_src) > 0:
		urls = re.compile('\"(.*?)\"\:\"(.*?)\"\,?').findall(re_src[0].replace(" ", ""))

		for num, url in enumerate(urls):
			addLink('[B]' + name.replace('&nbsp;', ' ') + '[/B]',url[1],thumb,desc.replace('&nbsp;', ' '))
	else:	# jeste zkusim najit mpd (MN)
		urls = re.search("\"src\":\"(.*?)\.m3u8\"",httpdata,re.M)
		if urls != None:
			addLink('[B]' + name.replace('&nbsp;', ' ') + '[/B]',urls.group(1).replace("\\","")+".m3u8",thumb,desc.replace('&nbsp;', ' '))
		else:
			session.open(MessageBox, text='Video bohužel nelze přehrát', timeout=20, type=MessageBox.TYPE_INFO, close_on_any_key=False, enable_input=True)

	# stranka poradu
	section = re.search("<h1 class=\"title\"><a href=\"(.*?)\">(.*?)</a>", html, re.S)
	if section != None:
		url = section.group(1)
		title = section.group(2)+' - stránka pořadu'
		thumb = None
		addDir(title.replace('&nbsp;', ' '),url,2,thumb,1)

def LIVE(url):
	text = get_url('https://media.cms.nova.cz/embed/'+url+'?autoplay=1', headers={"referer": "https://novaplus.nova.cz/"})
	data = re.search("processAdTagModifier\(\{(.*?)\}\)", text, re.S)
	if data != None:
		plr = json.loads('{'+data.group(1)+'}')
		url = plr["tracks"]["HLS"][0]["src"]
		add_video(name,url,live=True,settings={"user-agent":_UserAgent_,"extra-headers":{'referer':'https://media.cms.nova.cz/'}})

url=None
name=None
thumb=None
mode=None
page=None

try:
		url=unquote_plus(params["url"])
except:
		pass
try:
		name=unquote_plus(params["name"])
except:
		pass
try:
		mode=int(params["mode"])
except:
		pass
try:
		page=int(params["page"])
except:
		pass

if mode==None or url==None or len(url)<1:
		OBSAH()
elif mode==6:
		HOMEPAGE(url,page)
elif mode==5:
		CATEGORIES(url,page)
elif mode==2:
		EPISODES(url,page)
		#VIDEOLINK(url, page)
elif mode==3:
		VIDEOLINK(url,page)
elif mode==7:
		LIVE(url)