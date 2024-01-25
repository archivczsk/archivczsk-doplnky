# -*- coding: utf-8 -*-
#
# plugin.video.mall.tv
#
# (c) Michal Novotny
#
# original at https://www.github.com/misanov/
#
# Free for non-commercial use under author's permissions
# Credits must be used

import os, re, datetime, requests
from Plugins.Extensions.archivCZSK.engine.tools.util import unescapeHTML
from Plugins.Extensions.archivCZSK.engine.client import add_video, add_dir, getTextInput, show_message

try:
	from urllib import unquote_plus, quote
except:
	from urllib.parse import unquote_plus, quote

_UserAgent_ = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'

def mall_tv_run(addon, session, params):
	lang = 'sk' if addon.get_setting('country') is '1' else 'cz'
	baseurl = 'https://sk.mall.tv' if lang is 'sk' else 'https://www.mall.tv'
	icon =	os.path.join( addon.get_info('path'), 'icon.png' )

	def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
		params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
		add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)

	def get_url(url):
		headers = {'User-Agent': _UserAgent_, 'Set-Cookie': '_selectedLanguage=' + lang}
		result = requests.get(url, headers=headers, timeout=15, verify=False)
		if result.status_code != 200:
			show_message(session, 'Chyba nacitani dat', msg_type='error', timeout=10)
			return ""
		return result.text

	def OBSAH():
		addDir('Hledat', "#", 5, icon, 10002)
		addDir('Živá vysílání', "#", 7, icon, 2)
		addDir('SlowTV - Nonstop živě', "#", 7, icon, 4)
		addDir('Odvysílaná živá vysílání', "#", 7, icon, 3)
		addDir('Připravovaná živá vysílání', "#", 7, icon, 1)
		addDir('Nejnovější', "#", 5, icon, 10001)
		addDir('Kategorie', "#", 2, icon, 1)
		addDir('Pořady', "#", 3, icon, 1)

	def ZIVE(sid):
		strana = 0
		pocet = 0
		celkem = 0
		while True:
			html = get_url(baseurl + '/Live/LiveSectionVideos?sectionId=' + str(sid) + '&page=' + str(strana))
			if not html:
				break
			if sid != 3: data = re.findall('<div.*?video-card.*?<a.*?href=(.*?) .*?title="(.*?)".*?data-img=(.*?) .*?_info', html, re.S)
			else: data = re.findall('video-card .*?href=(.*?) .*?title="(.*?)".*?data-img=(.*?) .*?video-duration.*?>(.*?)<.*?video-card__info .*?title="(.*?)".*?video-card__info-timestamp.*?>(.*?)<', html, re.S)
			if data:
				for item in data:
					if sid != 3: addDir(unescapeHTML(item[1]), item[0], 9, item[2], 1)
					else: addDir(unescapeHTML(item[1]), item[0], 9, item[2], 1, infoLabels={'plot':item[5] + ' ' + item[4] + ' (' + item[3] + ')'})
					pocet += 1
			temp = re.search('slider-total=(.*?) ', html, re.S)
			if temp:
				celkem = int(temp.group(1))
			if pocet >= celkem:
				break
			strana += 1
			if strana > 10:
				break

	def KATEGORIE():
		html = get_url(baseurl + '/kategorie')

		hlavni = re.findall('<div.*?video-card.*?<a.*?href=(.*?) .*?data-src=(.*?)>.*?<h2.*?>(.*?)</h2>', html, re.S)
		if hlavni:
			hlavni.pop()
			for item in hlavni:
				addDir(unescapeHTML(item[2]), baseurl + item[0], 6, item[1], 1)
		vedlejsi = re.findall('col-sm-auto.*?href=(.*?) class="badge.*?>(.*?)</a>', html, re.S)
		if vedlejsi:
			for item in vedlejsi:
				addDir(unescapeHTML(item[1]), baseurl + item[0], 6, icon, 1)

	def PODKATEGORIE(url):
		if baseurl not in url:
			url = baseurl + url
		html = get_url(url)

		data = re.search('<section.*?isSerie(.*?)</section>', html, re.S)
		if data:
			hlavni = re.findall('<div.*?video-card.*?<a.*?href=(.*?) .*?data-src=(.*?)>.*?<h4.*?>(.*?)</h4>', data.group(1), re.S)
			if hlavni:
				for item in hlavni:
					addDir(unescapeHTML(item[2]), baseurl + item[0], 4, item[1], 1)

	def PORADY():
		strana = 0
		pocet = 0
		celkem = 0
		while True:
			html = get_url(baseurl + '/Serie/CategorySortedSeries?categoryId=0&sortType=1&page=' + str(strana))
			if not html:
				break
			data = re.findall('data-src=(.*?)>.*?href=(.*?) .*?<h4.*?>(.*?)</h4>', html, re.S)
			if data:
				for item in data:
					addDir(unescapeHTML(item[2]), item[1], 4, item[0], 1)
					pocet += 1
			temp = re.search('slider-total=(.*?) ', html, re.S)
			if temp:
				celkem = int(temp.group(1))
			if pocet >= celkem:
				break
			strana += 1

	def VYBERY(url):
		if baseurl not in url:
			url = baseurl + url
		html = get_url(url)

		# zalozky TODO
		section = re.search('<ul class="mall_categories-list(.*?)</ul>', html, re.S)
		if section:
			lis = re.findall('<li data-id=(.*?) .*?>([^<]+)', section.group(1), re.S)
			if lis != None:
				for li in lis:
					if int(li[0]) > 0:
						addDir(unescapeHTML(li[1]), '#', 5, None, li[0])

	def VIDEA(sid):
		strana = 0
		celkem = 10 # max stran pro jistotu, aby se nezacyklil a u nejnovejsich a popularnich jsou to tisice!
		if sid==10002: # hledat
			query = getTextInput(session, "Hledat")
			if len(query) == 0:
				show_message(session, "Je potřeba zadat vyhledávaný řetězec", msg_type='error', timeout=4)
				return
		while True:
			url = '/Serie/Season?seasonId=' + str(sid) + '&sortType=3&' # sekce dle data id
			if sid == 10001: # nejnovejsi
				url = '/sekce/nejnovejsi?' if lang is 'cz' else '/sekcia/najnovsie?'
			if sid == 10002: # hledat
				url = '/Search/Videos?q=' + quote(query) + '&sortType=3&'
			html = get_url(baseurl + url + 'page=' + str(strana))
			if not html:
				break
	#		 data = re.findall('video-card .*?href=(.*?) .*?title="(.*?)".*?data-img=(.*?) ', html, re.S)
			data = re.findall('video-card .*?href=(.*?) .*?title="(.*?)".*?data-img=(.*?) .*?video-duration.*?>(.*?)<.*?video-card__info .*?title="(.*?)".*?video-card__info-timestamp.*?>(.*?)<', html, re.S)
			if data:
				for item in data:
	#				 addDir(unescapeHTML(item[1]),item[0],9,item[2],1)
					addDir(unescapeHTML(item[1]), item[0], 9, item[2], 1, infoLabels={'plot':item[5] + ' ' + item[4] + ' (' + item[3] + ')'})
			if strana >= celkem:
				break
			strana += 1

	def VIDEOLINK(url):
		if baseurl not in url:
			url = baseurl + url
		html = get_url(url)

		try:
			title = re.search('<meta property=og:title content=["]*(.*?)["]* />', html, re.S).group(1)
		except:
			title = ""
		try:
			image = re.search('<meta property=og:image content=["]*(.*?)["]* />', html, re.S).group(1)
		except:
			image = None
		try:
			descr = re.search('<meta property=og:description content=["]*(.*?)["]* />', html, re.S).group(1).replace("\n", "").replace("\r", "")
		except:
			descr = ""
		try:
			src = re.search('VideoSource":"(.*?)"', html, re.S).group(1)
			if src == '':
				add_video("[COLOR red]Video zatím neexistuje[/COLOR]", "#", None, None)
			else:
				if src[0:2] == '//':
					src = 'http:' + src

				if not src.endswith('.m3u8'):
					src = src + '.m3u8'
				add_video(title, src, None, image, infoLabels={'plot':descr}, settings={ 'resolve_hls_master': False })
		except:
			add_video("[COLOR red]Video nelze načíst[/COLOR]", "#", None, None)

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

	if mode == None or url == None or len(url) < 1:
		OBSAH()
	elif mode == 2:
		KATEGORIE()
	elif mode == 3:
		PORADY()
	elif mode == 4:
		VYBERY(url)
	elif mode == 5:
		VIDEA(page)
	elif mode == 6:
		PODKATEGORIE(url)
	elif mode == 7:
		ZIVE(page)
	elif mode == 9:
		VIDEOLINK(url)

def main(addon):
	return mall_tv_run
