# -*- coding: utf-8 -*-
#------------------------------------------------------------
# pelisalacarta - XBMC Plugin
# Conector para videoweed
# http://blog.tvalacarta.info/plugin-xbmc/pelisalacarta/
#
#
# Modify: 2011-10-19 Ivo Brhel
#
#------------------------------------------------------------

import re
import os
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

def getURL(url):
	data = getUrlData(url)
	patronvideos  = 'flashvars\.domain="(.+?)"[\s|\S]*?flashvars\.file="(.+?)"[\s|\S]*?flashvars\.filekey="(.+?)";'
	match = re.compile(patronvideos,re.DOTALL).findall(data)
	#print( match )
	result = "";
	if len(match) > 0:
		data = getUrlData('%s/api/player.api.php?file=%s&key=%s&user=undefined&codes=undefined&pass=undefined'% (match[0][0],match[0][1],match[0][2]))
		match = re.compile("url=(.+?[^\&]+)").findall(data)
		if len(match) > 0:
			result=match[0]
	return result
