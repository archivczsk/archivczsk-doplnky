# -*- coding: utf-8 -*-
#
# Modify: 2011-09-17, Ivo Brhel
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

user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3'

def geturl(url):
	req = Request(url)
	req.add_header('User-Agent', user_agent)
	req.add_header('Referer','http://www.24video.net/')
	response = urlopen(req)
	link=response.read()
	return link


def latin2text(word):
	dict_hex = {'&#xe1;' : 'á',
				'&#x10d;': 'č',
				'&#x10f;': 'ď',
				'&#xe9;' : 'é',
				'&#x11b;': 'ě',
				'&#xed;' : 'í',
				'&#xf1;' : 'ñ',
				'&#xf3;' : 'ó',
				'&#x159;': 'ř',
				'&#x161;': 'š',
				'&#x165;': 'ť',
				'&#xfa;' : 'ú',
				'&#xfc;' : 'ü',
				'&#xfd;' : 'ý',
				'&#x17e;': 'ž',
				}
	for key in list(dict_hex.keys()):
		word = word.replace(key,dict_hex[key])
	return word


def getURL( page_url ):
	print("[videonet.py] getURL(page_url='%s')" % page_url)

	data = latin2text(geturl(page_url))
	match=re.compile("<videos><video url=\'(.+?)[^ ] rating").findall(data)
   
	return match[0]