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

LETTERS = ['A','B','C','Č','D','Ď','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','Ř','S','Š','T','Ť','U','V','W','X','Y','Z','Ž']
import re,sys,os,traceback
import util
from threading import Lock
from provider import ContentProvider
from provider import ResolveException
import resolver

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urllib import quote
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import quote

class PohadkarContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None,tmp_dir='.'):
		ContentProvider.__init__(self,'pohadkar.cz','http://www.pohadkar.cz/',username,password,filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)
		self.tmp_dir = tmp_dir

	def capabilities(self):
		return ['resolve','cagegories','!download']

	def search(self,keyword):
		return self.list('hledej?hledej='+quote(keyword))

	def categories(self):
		result = []
		#item = self.dir_item()
		#item['url'] = '#list-all#'
		#item['title'] = 'Všechny pohádky'
		#result.append(item)
		for index,letter in enumerate(LETTERS):
			item = self.dir_item()
			item['title'] = letter
			item['url'] = '#list#%d' % index
			result.append(item)
		return result

	def list(self,url):
		if url.find('#list-all#') == 0:
			return self.list_all()
		if url.find('#list#') == 0:
			return self.list_letter(url[6:])
		else:
			return self.parse_page(util.request(self._url(url)),self._url(url))

	def list_all(self):
		result = []
		for index,letter in enumerate(LETTERS):
			result = result + self.list_letter(index)
		return result

	def parse_page(self,page,url):
		data = util.substr(page,'<div class=\"vypis','<div class=\"right')
		pattern = '<div class=\"tale_char_div\"(.+?)<img(.+?)src=\"(?P<img>[^\"]+)(.+?)<a(.+?)href=\"(?P<url>[^\"]+)[^>]+>(?P<name>[^<]+)<(.+?)<p[^>]*>(?P<plot>[^<]+)'
		result = []
		for m in re.finditer(pattern, data, re.IGNORECASE | re.DOTALL):
			item = self.video_item()
			item['title'] = m.group('name')
			item['url'] = m.group('url')
			item['img'] = m.group('img')
			item['plot'] = m.group('plot')
			self._filter(result,item)
		data = util.substr(page,'<p class=\"p_wrapper','</p>')
		index =	 url.find('?')
		if index > 0:
			url = url[:index]
		n = re.search('<a(.+?)href=\"(?P<url>[^\"]+)\"[^>]*>&gt;<',data)
		if n:
			item = self.dir_item()
			item['type'] = 'next'
			item['url'] = self._url(url+n.group('url'))
		return result

	def list_letter(self,index):
		def fill_list_parallel(list, matches):
			def process_match(m):
				image,plot = self._get_meta(m.group('name'),self._url(m.group('url')))
				item = self.dir_item()
				item['title'] = m.group('name')
				item['url'] = m.group('url')+'video/'
				item['img'] = image
				item['plot'] = plot
				with lock:
					self._filter(list, item)
			lock = Lock()
			util.run_parallel_in_threads(process_match, matches)
			
		letter = LETTERS[int(index)]
		data = util.request(self.base_url+'system/load-vypis/?znak='+letter+'&typ=1&zar=hp')
		pattern = '<a href=\"(?P<url>[^\"]+)[^>]+>(?P<name>[^<]+)'
		result = []
		matches = []
		for m in re.finditer(pattern,data,re.IGNORECASE | re.DOTALL ):
			matches.append((m,))
		fill_list_parallel(result, matches)
		result = sorted(result,key=lambda x:x['title'])
		return result

	def _get_meta(self,name,link):
		# load meta from disk or download it (slow for each tale, thatswhy we cache it)
		# not neccesary anymore its quite quick now,,
		data = util.request(link)
		return self._get_image(data),self._get_plot(data)

	def _get_plot(self,data):
		data = util.substr(data,'<div id=\"tale_description\"','<div class=\"cleaner')
		p = data
		p = re.sub('<div[^>]+>','',p)
		p = re.sub('<table.*','',p)
		p = re.sub('</span>|<br[^>]*>|<ul>|</ul>|<hr[^>]*>','',p)
		p = re.sub('<span[^>]*>|<p[^>]*>|<li[^>]*>','',p)
		p = re.sub('<strong>|<a[^>]*>|<h[\d]+>','[B]',p)
		p = re.sub('</strong>|</a>|</h[\d]+>','[/B]',p)
		p = re.sub('</p>|</li>','[CR]',p)
		p = re.sub('<em>','[I]',p)
		p = re.sub('</em>','[/I]',p)
		p = re.sub('<img[^>]+>','',p)
		p = re.sub('\[B\]Edituj popis\[\/B\]','',p)
		p = re.sub('\[B\]\[B\]','[B]',p)
		p = re.sub('\[/B\]\[/B\]','[/B]',p)
		p = re.sub('\[B\][ ]*\[/B\]','',p)
		return util.decode_html(''.join(p)).encode('utf-8')


	def _get_image(self,data):
		m = re.search('<img id=\"tale_picture\" src=\"(?P<img>[^\"]+)', data, re.IGNORECASE | re.DOTALL)
		if not m == None:
			img = self._url(m.group('img'))
			return img

	def resolve(self,item,captcha_cb=None,select_cb=None):
		page = util.request(self._url(item['url']))
		data = util.substr(page,'<div id=\"video','<div id=\"controller')
		data = re.sub('youtube-nocookie.com','youtube.com',data)
		resolved = resolver.findstreams(data,['<embed( )src=\"(?P<url>[^\"]+)','<object(.+?)data=\"(?P<url>[^\"]+)','<iframe(.+?)src=\"(?P<url>[^\"]+)'])
		result = []
		if not resolved:
			raise ResolveException('Video nenalezeno')
		for i in resolved:
			item = self.video_item()
			item['title'] = i['title']
			item['url'] = i['url']
			item['quality'] = i['quality']
			item['surl'] = i['surl']
			item['headers'] = i['headers']
			result.append(item)
		result = sorted(result,key=lambda x:x['title'])
		if len(result)==1:
			return result[0]
		elif len(result) > 1 and select_cb:
			return select_cb(result)
