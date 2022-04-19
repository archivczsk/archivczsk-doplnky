# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Libor Zoubek
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

import re,os,shutil,traceback
import util,resolver
from provider import ContentProvider, cached

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	from urllib import quote_plus
	from HTMLParser import HTMLParser
	import cookielib
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import quote_plus
	from html.parser import HTMLParser
	import http.cookiejar as cookielib


HDRS = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:38.0) Gecko/20100101 Firefox/38.0"}

class BefunContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None):
		ContentProvider.__init__(self,'befun.cz','http://befun.cz/',username,password,filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)
		self.order_by = ''
		self.strict_search = False

	def capabilities(self):
		return ['categories','resolve','search']

	def search(self,keyword):
		keyword = quote_plus(keyword)
		def strict_filter(item):
			if item['type'] == 'dir' and item['title'].lower().find(keyword.lower()) < 0:
				self.info('skip '+ item['title'])
				return False
			return True
 
		if self.strict_search:
			self.filter = strict_filter

		return self.list_page(util.request(self._url('vyhledat/results?q='+keyword+'&c=filmy')),'<h2>Výsledky vyhledávání</h2>','</section')

	def list(self,url):
		if url.find(self.order_by) < 0:
			if url.find('?') > 0:
				url+='&'+self.order_by
			else:
				url+='?'+self.order_by
		if url.find('#movie#') == 0:
			url = url[7:]
			return self.list_movie(util.request(self._url(url)),url)
		if url.find('#cat#') == 0:
			url = url[5:]
			return self._categories(util.request(self._url(url)),url)
		if url.find('#show#') == 0:
			url = url[6:]
			return self.list_episodes(util.request(self._url(url)))
		return self.list_page(util.request(self._url(url)),'<!-- Movies','</section')

	def list_episodes(self,page):
		page = util.substr(page,'<h3>Epizody','</article>')
		result = []
		for m in re.finditer('<li class=\"controls[^<]+<a href=\"(?P<url>[^\"]+)[^>]+>(?P<name>[^<]+)',page,re.IGNORECASE|re.DOTALL):
			item = self.video_item()
			item['url'] = m.group(1)
			item['title'] = m.group('name')
			self._filter(result,item)
		return result

	def list_movie(self,page,url):
		item = self.video_item()
		item['url'] = url
 
		data = util.substr(page,'<ul class=\"bread','</ul>')
		title = re.search('<li class=\"active\">([^<]+)',data)
		item['title'] = title.group(1).strip()

		data = util.substr(util.substr(page,'<article','<!-- Page footer'),'<div class=\"content','</p>') + '</p>'
		plot = re.search('<p>(.+?)</p>',data)
		if plot:
			item['plot'] = plot.group(1)

		data = util.substr(page,'<div class=\"img','</div>')
		img = re.search('<img src=\"([^\"]+)',data)
		if img:
			item['img'] = self._url(img.group(1))

		return [item]

	def list_page(self,page,start,end):
		next = re.search('<a href=\"(?P<url>[^\"]+)\" class=\"ajax\">Další',page)
		page = util.substr(page,start,end)
		result = []
		for m in re.finditer('<article[^>]+(.+?)</article>',page,re.IGNORECASE|re.DOTALL):
			data =	m.group(1)
			url = re.search('<a href=\"([^\"]+)',data)
			img = re.search('<div class=\"img[^<]+<img src=\"(?P<img>[^\"]+).+?alt=\"(?P<name>[^\"]+)',data)
			if img and url:
				item = self.dir_item()
				item['url'] = '#movie#' + url.group(1)
				item['img'] = self._url(img.group('img'))
				item['title'] = img.group('name')
				self._filter(result,item)
		if next:
			item = self.dir_item()
			item['type'] = 'next'
			item['url'] = next.group('url').replace('&amp;','&')
			result.append(item)
		return result

	def _categories(self,page,url):
		data = util.substr(page,'<ul id=\"menu_kategorie','</ul')
		prefix = ''
		mask = '[B]%s[/B]'
		if url.find('serialy') >= 0:
			prefix = '#show#'
			mask = '%s'
		result = []
		for m in re.finditer('<a href=\"(?P<url>[^\"]+)[^<]+<span[^>]*>(?P<name>[^<]+)',data,re.IGNORECASE | re.DOTALL ):
			item = self.dir_item()
			item['title'] = mask % m.group('name')
			item['url'] = prefix+m.group('url')
			result.append(item)
		# sort this
		result = sorted(result,key=lambda i:i['title'])
		if prefix == '':
			# when listing movie categories, we also list movies on 'main' page
			return result + self.list_page(page,'<!-- Movies','</section')
		return result

	def categories(self):
		result = []
		item = self.dir_item()
		item['title'] = 'Filmy'
		item['url'] = '#cat#filmy/'
		result.append(item)
		item = self.dir_item()
		item['title'] = 'Seriály'
		item['url'] = '#cat#serialy/'
		result.append(item)
		return result

	def resolve(self,item,captcha_cb=None,select_cb=None):
		item = item.copy()
		url = self._url(item['url'])
		data = util.request(self._url(item['url']))
		data = util.substr(data,'<div class=\"video','</div')
		sosac = re.search('\"(http\://[\w]+\.sosac\.[^\"]+)',data,re.DOTALL)
		if sosac:
			sosac = HTMLParser().unescape(sosac.group(1))
			self.info("Reading sosac URL "+sosac)
			data = util.request(sosac, headers = HDRS)
		result = self.findstreams(data,[
			'<embed( )*flashvars=\"file=(?P<url>[^\"]+)',
			'<embed( )src=\"(?P<url>[^\"]+)',
			'<object(.+?)data=\"(?P<url>[^\"]+)',
			'<iframe(.+?)src=[\"\' ](?P<url>.+?)[\'\" ]',
			'<object.*?data=(?P<url>.+?)</object>'
			])
		if len(result)==1:
			return result[0]
		elif len(result) > 1 and select_cb:
			return select_cb(result)
