# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Ivo Brhel
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

import re,os
import util,resolver

from provider import ContentProvider

try:
	import cookielib
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib

class JaksetodelaContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None):
		ContentProvider.__init__(self,'jaksetodela.cz','https://www.jaksetodela.cz/',username,password,filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['resolve','categories','search']
		

	def search(self,keyword):
				return self.film(util.request(self._url('search/?search_id='+keyword+'&search_type=search_videos&submit=Hledej')))
		
			
	def substr(self,data,start,end):
		i1 = data.find(start)
		i2 = data.find(end,i1+1)
		return data[i1:i2]
			
	def film(self,page):
		result=[]


		data = self.substr(page,'<span class="pagingnav">1</span>','<span class="pagingnav">1</span>')
		im = data.find('thumb_position_v')
		if im > 0:
			pattern='\t<a href="(?P<url>.+?)".+?title=\'(?P<name>.+?)\'.?>[\s|\S]*?<img.*?src="(?P<img>.+?)" id='
		else:
			pattern='<a href="(?P<url>.+?)".?>(?P<name>.+?)</a>'
		for m in re.finditer(pattern,data,re.IGNORECASE | re.DOTALL ):
			item = self.video_item()
			try:
				item['img'] = self._url(m.group('img'))
			except:
				pass
			item['url'] = self._url(m.group('url'))
			item['title'] = m.group('name')
			#item['plot']= m.group('info')
			result.append(item)
			
		return result

	def cat(self,page):
		result = []
		
		data = util.substr(page,'<a href="/kategorie" >Kategorie</a>','<a href="/vase-rady-tipy"')
		pattern='a href=\'(?P<url>.+?)\'>(?P<name>.+?)</a>'
		for m in re.finditer(pattern,data,re.IGNORECASE | re.DOTALL ):
			item = self.dir_item()
			item['title']=m.group('name')
			item['url'] = '#catl2#'+self._url(m.group('url'))
			result.append(item)
		return result

	def catl2(self,page):
		result = []
		
		data = util.substr(page,'<div id="kategorie_obsahf">','</ul>')
		pattern='a href=\'(?P<url>.+?)\'>(?P<name>.+?)</a>'
		for m in re.finditer(pattern,data,re.IGNORECASE | re.DOTALL ):
			item = self.dir_item()
			item['title']=m.group('name')
			item['url'] = '#film#'+self._url(m.group('url'))
			result.append(item)
		return result

	def catl3(self,page):
		result = []
		
		data = self.substr(page,'<span class="pagingnav">1</span>','<span class="pagingnav">1</span>')
		pattern='\s<a href="(?P<url>.+?)".+?title=\'(?P<name>.+?)\'.?>[\s|\S]*?<img.*?src="(?P<img>.+?)" id='
		for m in re.finditer(pattern,data,re.IGNORECASE | re.DOTALL ):
			item = self.video_item()
			item['img'] = m.group('img')
			item['title'] = m.group('name')
			#item['url'] = '#film#'+self._url(m.group('url'))
			item['url'] = self._url(m.group('url'))
			result.append(item)
		return result
		
	
	def categories(self):
		result = []
		
		item = self.dir_item()
		item['type'] = 'new'
		item['url']	 = '#last#'+self._url('videos/basic/mr')
		result.append(item)
		result.extend(self.cat(util.request(self._url('videos'))))
		
		return result
	
	
	def list(self,url):
		if url.find('#film#') == 0:
			return self.film(util.request(self._url(url[6:])))
		if url.find('#cat#') == 0:
			return self.cat(util.request(self._url(url[5:])))
		if url.find('#catl2#') == 0:
			return self.catl2(util.request(self._url(url[7:])))
		if url.find('#last#') == 0:
			return self.film(util.request(self._url(url[6:])))
		else:
			raise Expception("Invalid url, I do not know how to list it :"+url)

			
	
	def resolve(self,item,captcha_cb=None,select_cb=None):
		item = item.copy()
		url = self._url(item['url'])
		print( 'URL: ' + url )
		hdata = util.request(url)
		
		data = util.substr(hdata,'<div id="player"','<div id="other" class="domtab">')
		pattern = 'videoId: \'(?P<vid>.+?)\','
		m = re.search(pattern, data, re.IGNORECASE | re.DOTALL)
		if not m == None:
			url = 'http://www.youtube.com/watch?v='+m.group('vid')
		print(url)
		
		resolved = resolver.findstreams(url,['(?P<url>http://www.youtube.com/watch\?v='+m.group('vid')+')'])
		result = []
		try:
			for i in resolved:
				item = self.video_item()
				item['title'] = i['name']
				item['url'] = i['url']
				item['quality'] = i['quality']
				item['surl'] = i['surl']
				result.append(item)	 
		except:
			print( '===Unknown resolver===' )
			
		if len(result)==1:
			return result[0]
		elif len(result) > 1 and select_cb:
			return select_cb(result)
