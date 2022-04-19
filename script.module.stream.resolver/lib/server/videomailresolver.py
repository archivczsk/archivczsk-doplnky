# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 mx3L
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
import re, util

try:
	from urllib2 import urlopen, Request
except:
	from urllib.request import urlopen, Request

__name__ = 'videomail'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		items = []
		quality = "???"
		vurl = m.group('url')
		vurl = re.sub('\&[^$]*','',vurl)
		req = Request('http://api.video.mail.ru/videos/' + vurl + '.json')
		resp = urlopen(req)
		data = resp.read()
		vkey = []
		for cookie in re.finditer('(video_key=[^\;]+)',resp.headers.get('Set-Cookie'),re.IGNORECASE | re.DOTALL):
			vkey.append(cookie.group(1))
		headers = {'Cookie':vkey[-1]}
		item = util.json.loads(data)
		for qual in item[u'videos']:
			if qual == 'sd':
				quality = "480p"
			elif qual == "hd":
				quality = "640p"
			else:
				quality = "???"
			link = item[u'videos'][qual]
			items.append({'quality':quality, 'url':link, 'headers':headers})
		return items

def _regex(url):
	m1 = re.search('http://.+?mail\.ru.+?<param.+?value=\"movieSrc=(?P<url>[^\"]+)', url, re.IGNORECASE | re.DOTALL)
	m2 = re.search('http://video\.mail\.ru\/(?P<url>.+?)\.html', url, re.IGNORECASE | re.DOTALL)
	return m1 or m2
