# -*- coding: UTF-8 -*-
#/*
# *      Copyright (C) 2013 Libor Zoubek
# *      Update 2022 jastrab
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */
import re,os

import xml.etree.ElementTree as ET
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util
from collections import OrderedDict
import requests

def loadurl(url, req, headers):
	response = requests.post(url, data=req, headers=headers)
	response.raise_for_status()
	return response.content

class MtrSkContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None):
		ContentProvider.__init__(self,'mtr.sk','https://www.mtr.sk/rss/',username,password,filter)

		self.getVideoArchiv()
		self.headers = {'User-Agent': 'Mozilla/5.0'}


	def capabilities(self):
		return ['resolve','categories', '!download']

	#Archiv z webu => list poloziek
	def getVideoArchiv(self):
		s = util.request('https://www.mtr.sk/videoarchiv/')
		s = re.sub('([\n\r])', '', s)
		a = re.finditer('(<select id=\"(?P<id>[^"]+)".*?</select>)', s)
		data = OrderedDict()
		for aa in a:
			t = aa.group(1)
			c = re.finditer('<option value=\"(?P<value>[^"]+)">(?P<text>[^<]+)', t)
			cast = OrderedDict()
			for cc in c:
				cast [cc.group('text')] = cc.group('value')
			data [aa.group('id')] = cast

		self.data_videoarchiv = data



	def categories(self):

		def media_tag(tag):
			return str( ET.QName('http://search.yahoo.com/mrss/', tag) )

		result = []

		item = self.dir_item()
		item['title'] = '[I]Video archív[/I]'
		item['url'] = '#relacie'
		item['img'] = 'https://www.mtr.sk/video/12750_big.jpg'
		item['plot'] = 'Videoarchív:\n' + (', '.join(list(self.data_videoarchiv.get('relacie').keys())[1:]))
		result.append(item)

		item = self.video_item()
		item['title'] = '[COLOR grey]Sledovať online[/COLOR]'
		item['url'] = 'https://cdnsk003.panaccess.com/local/Ruzomberok/index.m3u8'
		item['img'] = 'https://www.mtr.sk/video/10942_big.jpg'
		item['plot'] = 'Sleduj online Mestská TV Ružomberok'
		result.append(item)

		xml = ET.fromstring(util.request(self.base_url))
		for i in xml.find('channel').findall('item'):
			item = self.video_item()
			#item['title'] = '%s (%s)' % (i.find('title').text,i.find('description').text)
			item['title'] = i.find('title').text
			plot = i.find('description').text
			if plot:
				item['plot'] = plot
			item['img'] = i.find(media_tag('thumbnail')).attrib['url']
			item['url'] = i.find(media_tag('content')).attrib['url']
			result.append(item)
		return result

	def getVideo(self, _id):
		data = {'video' : _id}
		r = loadurl('https://www.mtr.sk/forms/playlist.php', data, headers = self.headers)
		r = r[1:-1]
		return r

	def getVideoMulti(self, _ids):
		data_post = {"temp_array" : _ids}
		s = loadurl('https://www.mtr.sk/forms/video_new.php', data_post, headers = self.headers)
		s = re.finditer('background-size: 53px;">(?P<text>[^<]+)<', s.decode())
		data = OrderedDict()
		idxs = _ids[1:].split(':')
		i = 0
		for ss in s:
			data[ idxs[i] ] = ss.group('text')
			i += 1
		return data


	def list_cast(self, url):
		data = self.getVideoMulti(url)
		result = []
		for k, v in data.items():
			item = self.video_item()
			item['url'] = ':' + k
			icon = 'https://www.mtr.sk/video/{}_big.jpg'.format(k)
			item['img'] = icon
			item['title'] = v
			result.append(item)
		return result

	def list(self, url):
		_id = url[1:]
		if url[0] == ':':
			return self.list_cast( url )

		if len(_id) < 3:
			_id = 'termin'+_id

		result = []
		i = 0
		for k, v in self.data_videoarchiv.get(_id).items():
			i += 1
			if i == 1:
				continue
			if ':' == v[0]:
				if len(v) < 8:
					item = self.video_item()
					item['url'] = v
					icon = 'https://www.mtr.sk/video/{}_big.jpg'.format(v[1:])
					item['img'] = icon

				else:
					item = self.dir_item()
					item['url'] = v
					item['menu'] = {'$30070':{'list':item['url'], 'action-type':'list'}}

			else:
				item = self.dir_item()

				item['url'] = '#'+v
				item['menu'] = {'$30070':{'list':item['url'], 'action-type':'list'}}
			item['title'] = k
			result.append(item)
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		url = item['url']
		_id = url[1:]
		if url[0] == ':':
			url = b'https://mtr.ruzomberok.sk/videoarchiv/' +  self.getVideo(_id)
		return self.video_item( url = url)
