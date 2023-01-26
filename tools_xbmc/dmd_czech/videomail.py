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
#
# thanks to
#  http://code.google.com/p/xbmc-doplnky/

import re
try:
	import simplejson as json
except ImportError:
	import json

try:
	import cookielib
	from urllib2 import urlopen, HTTPError, URLError
	from urllib2 import Request as Request
	from urlparse import urlsplit, urlparse, parse_qsl
	from urllib import quote, unquote_plus, urlencode
except:
	from urllib.request import urlopen
	from urllib.request import Request as Request
	from urllib.parse import urlsplit, urlparse, quote, unquote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError, URLError
	import http.cookiejar as cookielib

__name__ = 'videomail'

referer='http://img.mail.ru/r/video2/uvpv3.swf?3'
cookie='VID=2SlVa309oFH4; mrcu=EE18510E964723319742F901060A; p=IxQAAMr+IQAA; video_key=203516; s='
UA='Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3'

def getData(url,headers={}):
	req = Request(url,headers=headers)
	response = urlopen(req)
	data=response.read()
	response.close()
	return data

def supports(url):
	return not _regex(url) == None

# returns the steam url
def getURL(url):
	m = _regex(url)
	if m:
		items = []
		headers = { "User-Agent":UA, "Referer":referer, "Cookie":cookie }
		# header "Cookie" with parameters need to be set for your download/playback
		quality = "???"
		vurl = m.group('url')
		vurl = re.sub('\&[^$]*','',vurl)
		data = getData('http://api.video.mail.ru/videos/' + vurl + '.json', headers)
		item = json.loads(data)
		for qual in item[u'videos']:
			if qual == 'sd':
				quality = "480p"
			elif qual == "hd":
				quality = "720p"
			else:
				quality = "???"
			link = item[u'videos'][qual]
			items.append({'quality':quality, 'url':link+'|Cookie='+cookie+'|Referer='+referer})
			
		# best quality
	resolved = sorted(items,key=lambda i:i['quality'])
	#resolved.reverse()
	return resolved[-1][u'url']

def _regex(url):
	return re.search('movieSrc=(?P<url>.+?)$', url, re.IGNORECASE | re.DOTALL)