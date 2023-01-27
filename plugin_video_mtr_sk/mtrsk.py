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

import re,os

import xml.etree.ElementTree as ET
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	import cookielib
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib


class MtrSkContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None):
		ContentProvider.__init__(self,'mtr.sk','http://www.mtr.sk/rss/',username,password,filter)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['resolve','categories']

	def categories(self):
		
		def media_tag(tag):
			return str( ET.QName('http://search.yahoo.com/mrss/', tag) )

		result = []
		item = self.video_item()
		item['title'] = '[B]Sledovat online[/B]'
		item['url'] = 'rtmp://kdah.mtr.sk/oflaDemo/livestream live=true'
		result.append(item)
		xml = ET.fromstring(util.request(self.base_url))
		for i in xml.find('channel').findall('item'):
			item = self.video_item()
			item['title'] = '%s (%s)' % (i.find('title').text,i.find('description').text)
			item['img'] = i.find(media_tag('thumbnail')).attrib['url']
			item['url'] = i.find(media_tag('content')).attrib['url']
			result.append(item)
		return result

	def resolve(self,item,captcha_cb=None,select_cb=None):
		return self.video_item(url=item['url'].replace('https://', 'http://'))
