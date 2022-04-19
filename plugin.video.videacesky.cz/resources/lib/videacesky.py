# -*- coding: UTF-8 -*-
# /*
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

import re, sys
from xml.etree.ElementTree import fromstring

#from demjson import demjson
import json

import util
import resolver
from provider import ResolveException
from provider import ContentProvider

try:
	from urllib2 import HTTPCookieProcessor, build_opener, install_opener
	import cookielib
	from urllib import quote
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.parse import quote


class VideaceskyContentProvider(ContentProvider):
	def __init__(self, username=None, password=None, filter=None,
				 tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'videacesky.cz',
								 'http://www.videacesky.cz',
								 username, password, filter, tmp_dir)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def list(self, url):
		if url.find('zebricky/') == 0:
			return self.list_top10(util.request(self.base_url+url))
		if url.find("#related#") == 0:
			return self.list_related(util.request(url[9:]))
		else:
			return self.list_content(util.request(self._url(url)), self._url(url))

	def search(self, keyword):
		return self.list('/hledat?q=' + quote(keyword))

	def mmss_to_seconds(self, mmss):
		minutes, seconds = [int(x) for x in mmss.split(':')]
		return (minutes * 60 + seconds)

	def categories(self):
		result = []
		item = self.dir_item()
		item['type'] = 'new'
		item['url'] = "?orderby=post_date"
		result.append(item)
		item = self.dir_item()
		item['title'] = 'Top of the month'
		item['url'] = "zebricky/mesic/vse"
		result.append(item)
		data = util.request(self.base_url)
		data = util.substr(data, '<ul class=\"nav categories m-b\">', '</div>')
		pattern = '<a href=\"(?P<url>[^\"]+)(.+?)>(?P<name>[^<]+)'
		for m in re.finditer(pattern, data, re.IGNORECASE | re.DOTALL):
			if m.group('url') == '/':
				continue
			item = self.dir_item()
			item['title'] = m.group('name')
			item['url'] = m.group('url')
			result.append(item)
		return result

	def list_top10(self, page):
		result = []
		data = util.substr(page,
						   '<div class=\"line-items no-wrapper no-padder',
						   '<div class=\"my-pagination>')
		pattern = '<article class=\"video-line.+?<a href=\"(?P<url>[^\"]+)\" *title=\"(?P<title>[^\"]+)\".+?<img src=\"(?P<img>[^\"]+)\".+?<div class=\"video-rating.+?\">(?P<rating>[^&]+).+?<small>(?P<votes>[^x]+)'
		for m in re.finditer(pattern, data, re.IGNORECASE | re.DOTALL):
			item = self.video_item()
			item['title'] = self.format_title(m)
			item['url'] = self.base_url[:-1] + m.group('url')
			item['img'] = m.group('img').strip()
			item['plot'] = self.format_rating(m)
			self._filter(result, item)
		return result

	def list_content(self, page, url=None):
		result = []
		if not url:
			url = self.base_url
		data = util.substr(page, '<div class=\"items no-wrapper no-padder', '<div class=\"my-pagination>')
		pattern = '<article class=\"video\".+?<a href=\"(?P<url>[^\"]+)\" *title=\"(?P<title>[^\"]+)\"(.+?)<img src=\"(?P<img>[^\"]+)\".+?<span class=\"duration\">(?P<duration>[^>]*)</span>.*?<span class="rating.+?>(?P<rating>[^&]+).+?<p>(?P<plot>[^<]+?)<\/p>.+?<li class=\"i-published\".+?title=\"(?P<date>[^\"]+)\".+?<i class=\"fa fa-eye\"></i><span class=\"value\">(?P<votes>[^<]+)'
		for m in re.finditer(pattern, data, re.IGNORECASE | re.DOTALL):
			item = self.video_item()
			item['title'] = self.format_title(m)
			item['img'] = m.group('img').strip()
			item['plot'] = self.decode_plot(m)
			item['year'] = re.search('[0-9]{4}', m.group('date')).group()
			item['url'] = self.base_url[:-1] + m.group('url')
			item['menu'] = {'$30060': {'list': '#related#' + item['url'],
									   'action-type': 'list'}}
			try:
				item['duration'] = self.mmss_to_seconds(m.group('duration'))
			except ValueError:
				pass
			self._filter(result, item)
		data = util.substr(page, '<ul class=\"my-pagination', '</div>')
		n = re.search('<li class=\"paginate_button previous *\"[^<]+<a href=\"(?P<url>[^\"]+)\">(?P<name>[^<]+)<', data)
		k = re.search('<li class=\"paginate_button next *\"[^<]+<a href=\"(?P<url>[^\"]+)\">(?P<name>[^<]+)<', data)
		if n is not None:
			item = self.dir_item()
			item['type'] = 'prev'
			# item['title'] = '%s - %s' % (m.group(1), n.group('name'))
			item['url'] = n.group('url')
			result.append(item)
		if k is not None:
			item = self.dir_item()
			item['type'] = 'next'
			# item['title'] = '%s - %s' % (m.group(1), k.group('name'))
			item['url'] = k.group('url')
			result.append(item)
		return result

	def list_related(self, page):
		result = []
		data = util.substr(page,
						   '<div class=\"similarSliderInner\"',
						   '<div class=\"comments-container\"')
		pattern = '<article class=\"videoSimple.+?<a href=\"(?P<url>[^\"]+)\" *title=\"(?P<title>[^\"]+)\".+?<img src=\"(?P<img>[^\"]+)\".+?<span class="rating.+?>(?P<rating>[^&]+)'
		for m in re.finditer(pattern, data, re.IGNORECASE | re.DOTALL):
			item = self.video_item()
			item['title'] = self.format_title(m)
			item['img'] = m.group('img')
			item['url'] = m.group('url')
			self._filter(result, item)
		return result

	def format_title(self, m):
		return "{0} - {1}%".format(m.group('title'), m.group('rating'))

	def format_rating(self, m):
		return "{0}%, {1}x".format(m.group('rating'), m.group('votes'))

	def decode_plot(self, m):
		p = m.group('plot')
		p = re.sub('<br[^>]*>', '', p)
		p = re.sub('<div[^>]+>', '', p)
		p = re.sub('<table.*', '', p)
		p = re.sub('</span>|<br[^>]*>|<ul>|</ul>|<hr[^>]*>', '', p)
		p = re.sub('<span[^>]*>|<p[^>]*>|<li[^>]*>', '', p)
		p = re.sub('<strong>|<a[^>]*>|<h[\d]+>', '[B]', p)
		p = re.sub('</strong>|</a>|</h[\d]+>', '[/B]', p)
		p = re.sub('</p>|</li>', '[CR]', p)
		p = re.sub('<em>', '[I]', p)
		p = re.sub('</em>', '[/I]', p)
		p = re.sub('<img[^>]+>', '', p)
		p = re.sub('\[B\]Edituj popis\[\/B\]', '', p)
		p = re.sub('\[B\]\[B\]', '[B]', p)
		p = re.sub('\[/B\]\[/B\]', '[/B]', p)
		p = re.sub('\[B\][ ]*\[/B\]', '', p)
		
		plot = util.decode_html(''.join(p))
		
		if sys.version_info[0] == 2:
			plot = plot.encode('utf-8')
			
		rating = self.format_rating(m)
		return "{0}\n{1}".format(rating, plot.strip())

	def resolve(self, item, captcha_cb=None, select_cb=None):
		def js2json( js_txt ):
			# strip white chars
			js_txt = re.sub( ' +', ' ', js_txt ).strip()
			
			# fix true/false properties
			js_txt = js_txt.replace( ': true ', ': "true" ')
			js_txt = js_txt.replace( ': false ', ': "false" ')
			
			# quote keys
			js_txt = re.sub(r'([\{\s,])(\w+)(:)(\s+["\'\[\{])', r'\1"\2"\3\4', js_txt)
			
			# replace single to double quotes
			js_txt = js_txt.replace("'", '"')
			# correct end of json
			if js_txt.endswith(','):
				js_txt = js_txt[:-1]
			
			# remove 'playlist:' keyword
			if js_txt.startswith('playlist:'):
				js_txt = js_txt[9:]
			return js_txt

		result = []
		resolved = []
		item = item.copy()
		url = self._url(item['url'])
		data = util.substr(util.request(url), 'async type', '</script>')
		print( 'data start ----' )
		print( data )
		print( 'data end ----' )
		playlist = re.search('''new mfJWPlayer.+?(?P<jsondata>playlist:.+?)events:''',
							 data, re.MULTILINE | re.DOTALL)
		print( 'playlist start ----' )
		print( playlist )
		print( 'playlist end ----' )
		jsondata = js2json( playlist.group('jsondata') )
		print( 'jsondata start ----' )
		print( jsondata )
		print( 'jsondata end ----' )

		jsondata = json.loads(jsondata)

		for playlist_item in jsondata:
			playlist_item['file'] = playlist_item['file'].replace('time_continue=1&', '')

			from Plugins.Extensions.archivCZSK.engine import client
			video_formats = client.getVideoFormats(playlist_item['file'])
			video_url = [video_formats[-1]]
			print( video_url )
			subs = playlist_item['tracks']
			if video_url and subs:
				for i in video_url:
					i['subs'] = self.base_url[:-1]+subs[0]['file']
			resolved += video_url[:]

			if not resolved:
				raise ResolveException('Video nenalezeno')

			for i in resolved:
				item = self.video_item()
				try:
					item['title'] = i['title']
				except KeyError:
					pass
				item['url'] = i['url']
				item['quality'] = i['format_note']
				item['subs'] = i['subs']
				item['headers'] = {}
				try:
					item['fmt'] = i['fmt']
				except KeyError:
					pass
				result.append(item)

		if len(result) > 0 and select_cb:
			return select_cb(result)
			
		return result

