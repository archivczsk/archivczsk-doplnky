# -*- coding: utf-8 -*-
#-----------------------------------------------------------------------------
#
# Modify: 2012-11-28,  Ivo Brhel, 
#
# based on vk resolver from http://code.google.com/p/xbmc-doplnky/
#
#------------------------------------------------------------------------------

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


def substr(data,start,end):
	i1 = data.find(start)
	i2 = data.find(end,i1)
	return data[i1:i2]


def getData(url):
	req = Request(url)
	req.add_header('User-Agent', 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3')
	response = urlopen(req)
	data=response.read()
	return data


	
def getURL(page_url):
	print("[vk.py] getURL(page_url='%s')" % page_url)
	data = getData(page_url)
	data = substr(data,'div id=\"playerWrap\"','<embed>')
	if len(data) > 0:
		host = re.search('host=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		oid = re.search('oid=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		uid = re.search('uid=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		vtag = re.search('vtag=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		hd = re.search('hd_def=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		max_hd = re.search('hd=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		no_flv = re.search('no_flv=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		url = '%su%s/videos/%s' % (host,uid,vtag)
		print("[vk.py] %s" % (url))
		if no_flv != '1':
			return [url+'.flv']
		if no_flv == '1':
			res=int(hd)
			if max_hd:
				res=int(max_hd)
			if res < 0:
				return [url+'.flv']
			resolutions=['240','360','480','720','1080']
			ret = []
			for index,resolution in enumerate(resolutions):
				if index>res:
					return ret[-1]
				ret.append(url+'.'+resolution+'.mp4')
				print("[vk.py] %s - %s" % (resolution+'p',url+'.'+resolution+'.mp4'))
