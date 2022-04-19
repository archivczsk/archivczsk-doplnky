# -*- coding: utf-8 -*-
"""
	urlresolver XBMC Addon
	Copyright (C) 2011 t0mm0

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
# thanks to:
#	https://github.com/Eldorados

import re, sys, os
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


_UserAgent_ =  'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; .NET CLR 3.0.04506)'


def getUrlData(url):
	req = Request(url)
	req.add_header('User-Agent',_UserAgent_)
	response = urlopen(req)
	data=response.read()
	response.close()
	return data


def get_url(host, media_id):
	if 'movshare' in host:
		return 'http://www.movshare.net/video/%s' % media_id
	elif 'nowvideo' in host:
		return 'http://www.nowvideo.eu/video/%s' % media_id
	elif 'novamov' in host:
		return 'http://www.novamov.com/video/%s' % media_id
		
def get_host_and_id(url):
	if 'nowvideo' in url:
		r = re.search('http://(www.|embed.nowvideo.eu)/(?:video/|embed.php\?v=([0-9a-z]+)&width)', url) 
	if 'movshare' in url:
		r = re.search('//(www.movshare.net)/(?:video|embed)/([0-9a-z]+)', url)
	else:
		#r = re.search('//(?:embed.)?(.+?)/(?:video/|embed.php\?v=)' + '([0-9a-z]+)', url)
		r = re.search('//(?:embed.)?(.+?)/(?:video/|embed.php\?.*v=)' + '([0-9a-z]+)', url)
	if r:
		return r.groups()
	else:
		return False


def valid_url( url, host):
	return re.match('http://(www.|embed.)?no.+?/(video/|embed.php\?)', url) or 'novamov' in host or re.match('http://(?:www.)?movshare.net/(?:video|embed)/',url) or 'movshare' in host or re.match('http://(www.|embed.)?nowvideo.(?:eu)/(video/|embed.php\?)' +
						'(?:[0-9a-z]+|width)', url) or 'nowvideo' in host

		
def getURL(url):
	print( 'URL: '+url )
	host, media_id = get_host_and_id(url)
	web_url = get_url(host, media_id)
	
	try:
		html = getUrlData(web_url)
	except URLError as e:
		print ('novamov: got http error %d fetching %s' % (e.code, web_url))
		return False

	r = re.search('flashvars.file="(.+?)".+?flashvars.filekey="(.+?)"', html, re.DOTALL)
	if r:
		filename, filekey = r.groups()
		#print( "FILEBLOBS=%s  %s"%(filename,filekey) )
	else:
		r = re.search('file no longer exists',html)
		if r:
			print( 'novamov: This file no longer exists' )
			msg = 'Host: %s\n ID: %s' % (host,media_id)
			print( 'novamov: filename and filekey not found' )
		else:
			print('novamov: filename and filekey not found')
		return False
	
	#get stream url from api
	if 'movshare' in host:
		api = 'http://www.movshare.net/api/player.api.php?key=%s&file=%s' % (filekey, filename)
	elif 'nowvideo' in host:
		api = 'http://www.nowvideo.eu/api/player.api.php?key=%s&file=%s' % (filekey, filename)
	elif 'novamov' in host:
		#api = 'http://www.novamov.com/api/player.api.php?key=%s&file=%s' % (filekey, filename)
		api = 'http://www.novamov.com/api/player.api.php?key=%s&file=%s&pass=undefined&user=undefined&codes=1' % (filekey, filename)
	#print( api )
	try:
		html = getUrlData(api)
	except URLError as e:
		print('novamov: got http error %d fetching %s' % (e.code, api))
		return False

	r = re.search('url=(.+?)&title', html)
	if r:
		stream_url = r.group(1)
	else:
		r = re.search('file no longer exists',html)
		if r:
			print( 'novamov: This file no longer exists' )
			msg = 'Host: %s\n ID: %s' % (host,media_id)
			print('novamov: filename and filekey not found')
		else:
			print('novamov: filename and filekey not found')
		return False
		
	return stream_url