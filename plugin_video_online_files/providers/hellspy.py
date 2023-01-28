# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2012 Libor Zoubek
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
import re, random, sys, os, traceback
from base64 import b64decode
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util

try:
	from urllib2 import HTTPError, HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urllib import quote
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	from urllib.error import HTTPError
	import http.cookiejar as cookielib
	from urllib.parse import quote

class HellspyContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None,site_url='http://hellspy.cz/'):
		ContentProvider.__init__(self,'hellspy.cz',site_url,username,password,filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['login','search','resolve','categories']

	def search(self,keyword):
		return self.list('search/?usrq='+quote(keyword))

	def login(self):
		if self.username and self.password and len(self.username)>0 and len(self.password)>0:
			page = util.request(self.base_url+'?do=loginBox-loginpopup')
			if page.find('href="/?do=loginBox-logout') > 0:
				self.info('Already logged in')
				return True
			data = util.substr(page,'<td class=\"popup-lef','</form')
			m = re.search('<form action=\"(?P<url>[^\"]+)',data,re.IGNORECASE | re.DOTALL)
			if m:
				login_url = self._url(m.group('url')).replace('&amp;','&')
				data = util.post(login_url,{'username':self.username,'password':self.password,'pernament_login':'on','login':'1','redir_url':self.base_url+'?do=loginBox-login'})
				if data.find('href="/?do=loginBox-logout') > 0:
					return True
		return False

	def list_favourites(self,url):
		url = self._url(url)
		page = util.request(url)
		data = util.substr(page,'<div class=\"file-list file-list-vertical','<div id=\"layout-push')
		result = []
		for m in re.finditer('<div class=\"file-entry.+?<div class="preview.+?<div class=\"data.+?</div>',data, re.IGNORECASE|re.DOTALL):
			entry = m.group(0)
			item = self.video_item()
			murl = re.search('<[hH]3><a href=\"(?P<url>[^\"]+)[^>]+>(?P<name>[^<]+)',entry)
			item['url'] = murl.group('url')
			item['title'] = murl.group('name')
			mimg = re.search('<img src=\"(?P<img>[^\"]+)',entry)
			if mimg:	
				item['img'] = mimg.group('img')
			msize = re.search('<span class=\"file-size[^>]+>(?P<size>[^<]+)',entry)
			if msize:
				item['size'] = msize.group('size').strip()
			mtime = re.search('<span class=\"duration[^>]+>(?P<time>[^<]+)',entry)
			if mtime:
				item['length'] = mtime.group('time').strip()
			self._filter(result,item)
		return result

	def list(self,url,filter=None):
		if url.find('ucet/favourites') >= 0 and self.login():
			return self.list_favourites(url)
		url = self._url(url)
		util.init_urllib()
		page = util.request(url)
		data = util.substr(page,'<div class=\"file-list file-list-horizontal','<div id=\"layout-push')
		result = []
		for m in re.finditer('<div class=\"file-entry.+?<div class="preview.+?<div class=\"data.+?</div>',data, re.IGNORECASE|re.DOTALL):
			entry = m.group(0)
			item = self.video_item()
			murl = re.search('<[hH]3><a href=\"(?P<url>[^\"]+)[^>]+>(?P<name>[^<]+)',entry)
			item['url'] = murl.group('url')
			item['title'] = murl.group('name')
			mimg = re.search('<img src=\"(?P<img>[^\"]+)',entry)
			if mimg:	
				item['img'] = mimg.group('img')
			msize = re.search('<span class=\"file-size[^>]+>(?P<size>[^<]+)',entry)
			if msize:
				item['size'] = msize.group('size').strip()
			mtime = re.search('<span class=\"duration[^>]+>(?P<time>[^<]+)',entry)
			if mtime:
				item['length'] = mtime.group('time').strip()
			self._filter(result,item)
		# page navigation
		data = util.substr(page,'<div class=\"paginator','</div')
		mprev = re.search('<li class=\"prev[^<]+<a href=\"(?P<url>[^\"]+)',data)
		if mprev:
			item = self.dir_item()
			item['type'] = 'prev'
			item['url'] = mprev.group('url')
			result.append(item)
		mnext = re.search('<li class=\"next[^<]+<a href=\"(?P<url>[^\"]+)',data)
		if mnext:
			item = self.dir_item()
			item['type'] = 'next'
			item['url'] = mnext.group('url').replace('&amp;','&')
			result.append(item)
		return result

	def categories(self):
		result = []
		page = util.request(self.base_url)
		data = util.substr(page,'<div id=\"layout-menu','</div')
		index = 0
		for m in re.finditer('<a href=\"(?P<url>[^\"]+)[^>]+>(?P<title>[^<]+)',data):
			if index > 0 and index <= 3:
				item = self.dir_item()
				item['title'] = m.group('title')
				item['url'] = m.group('url')
				result.append(item)
			index +=1
		return result

	def resolve(self,item,captcha_cb=None,select_cb=None):
		item = item.copy()
		url = self._url(item['url'])
		if not self.login():
			util.error('[hellspy] login failed, unable to resolve')
		if url.find('?') > 0:
			url+='&download=1'
		else:
			url+='?download=1'
		data = util.request(url)
		if data.find('Soubor nenalezen') > 0:
			util.error('[hellspy] - page with movie was not found on server')
			return
		m = re.search('launchFullDownload\(\'(?P<url>[^\']+)',data)
		if m:	
			item['url'] = m.group('url')
			item['surl'] = url
			return item

	def to_downloads(self,url):
		if not self.login():
			util.error('[hellspy] login failed, unable to add to downloads')
		util.info('adding to downloads')
		try:
			util.request(self._url(url+'&do=downloadControl-favourite'))
		except HTTPError:
			traceback.print_exc()
			util.error('[hellspy] failed to add to downloads')
			return
		util.info('added, DONE')
