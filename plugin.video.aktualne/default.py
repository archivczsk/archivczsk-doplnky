# -*- coding: utf-8 -*-
#
# plugin.video.aktualne
#
# (c) Michal Novotny
#
# original at https://www.github.com/misanov/
#
# Free for non-commercial use under author's permissions
# Credits must be used

import re,os,time,datetime,json
import email.utils as eut
from Components.config import config
from parseutils import *
from util import addDir, addLink
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

try:
	from urllib2 import urlopen, Request
	from urllib import unquote_plus, quote_plus
except:
	from urllib.request import urlopen, Request
	from urllib.parse import unquote_plus, quote_plus



__baseurl__ = 'https://video.aktualne.cz/rss/'
_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'
addon =	 ArchivCZSK.get_xbmc_addon('plugin.video.aktualne')
profile = addon.getAddonInfo('profile')
__settings__ = addon
home = __settings__.getAddonInfo('path')
icon =	os.path.join( home, 'icon.png' )
fanart = os.path.join( home, 'fanart.jpg' )

def get_url(url):
	req = Request(url)
	req.add_header('User-Agent', _UserAgent_)
	response = urlopen(req)
	data=response.read()
	response.close()
	return data.decode('utf-8')

def listItems(offset):
	url = __baseurl__
	if offset > 0:
		url += '?offset=' + str(offset)
	html = get_url(url)
	articles = re.findall("<item>(.*?)</item>", html, re.S)
	if articles != None:
		for article in articles:
			infoLabels = {'plot': '', 'duration': 0}
			article = article.replace("&lt;","<").replace("&gt;",">").replace("&quot;","\"")
			try:
				url = re.search("<link>(.*?)</link>", article, re.S).group(1)
			except:
				url = ""
			try:
				category = re.search("<category.*?>(.*?)</category>", article, re.S).group(1) + " - "
				infoLabels['plot'] += category
			except:
				category = ""
			try:
				title = re.search("<title>(.*?)</title>", article, re.S).group(1)
				infoLabels['plot'] += title
			except:
				title = ""
			try:
				infoLabels['plot'] += '\n\n' + re.search("<description>(.*?)</description>", article, re.S).group(1)
			except:
				pass
			try:
				duration = re.search("duration=\"(.*?)\"", article, re.S).group(1).split(':')
				if len(duration) == 3:
					infoLabels['duration'] = (int(duration[0])*3600 + int(duration[1])*60 + int(duration[2]))
				else:
					infoLabels['duration'] = (int(duration[0])*60 + int(duration[1]))
			except:
				pass
			try:
				thumb = re.search("img.*?src=\"(.*?)\"", article, re.S).group(1)
			except:
				thumb = None
			try:
				pdate = re.search("<pubDate>(.*?)</pubDate>", article, re.S).group(1)
				pdats = re.sub('\s+',' ',pdate).strip()
				pdato = eut.parsedate(pdats)
				pdate = time.strftime('%d.%m. %H:%M',pdato) + " "
			except:
				pdate = ""
			if url != "" and title != "":
				addDir(pdate + category + title, url, 3, thumb, 1, infoLabels=infoLabels)
		o = offset + 30
		u = __baseurl__ + '?offset=' + quote_plus(str(o))
		addDir('Další', u, None, None, 1)
	else:
		addLink("[COLOR red]Chyba načítání pořadů[/COLOR]","#",None,"")

def videoLink(url):
	html = get_url(url)

	title = re.search('<meta property="og:title" content="(.*?)"', html, re.S).group(1) or ""
	image = re.search('<meta property="og:image" content="(.*?)"', html, re.S).group(1) or None
	descr = re.search('<meta property="og:description" content="(.*?)"', html, re.S).group(1) or None

	bbx = re.search('BBXPlayer.setup\((.*?)\)', html, re.S)
	bbxg = bbx.group(1)
	bbxj = json.loads(re.sub('\s+',' ',bbxg).strip())

	if bbxj['tracks']['MP4']:
		for version in bbxj['tracks']['MP4']:
			addLink(version['label'] + " " + title,version['src'],image,descr)


url=None
name=None
thumb=None
mode=None
page=None
offset=0

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
try:
		offset=int(urllib.unquote_plus(re.search('offset=([0-9]+)', url, re.S).group(1)))
except:
		pass

if mode==None or url==None or len(url)<1:
		listItems(offset)
elif mode==3:
		videoLink(url)
