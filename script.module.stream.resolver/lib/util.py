# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2011 Libor Zoubek
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
import os, re, sys, traceback, time, socket
try:
	import simplejson as json
except ImportError:
	import json

import threading

try:
	from htmlentitydefs import name2codepoint as n2cp
	import Queue
	import cookielib
	from urllib2 import urlopen, Request, HTTPError, HTTPCookieProcessor, build_opener, install_opener
	from urllib import urlencode
	is_py3 = False
except:
	import queue as Queue
	from urllib.request import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlencode
	from urllib.error import HTTPError
	import http.cookiejar as cookielib
	from html.entities import name2codepoint as n2cp
	is_py3 = True
	unicode = str

from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

LOG = 2

sys.path.append(os.path.join(os.path.dirname(__file__), 'contentprovider'))
sys.path.append( os.path.join ( os.path.dirname(__file__),'crypto') )

try:
	from Plugins.Extensions.archivCZSK.settings import USER_AGENT
	UA = USER_AGENT
except:
	UA = 'Mozilla/6.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.5) Gecko/2008092417 Firefox/3.0.3'
	pass

_cookie_jar = None

CACHE_COOKIES = 'cookies'


class _StringCookieJar(cookielib.LWPCookieJar):
	def __init__(self, string=None, filename=None, delayload=False, policy=None):
		cookielib.LWPCookieJar.__init__(self, filename, delayload, policy)
		if string and len(string) > 0:
			self._cookies = pickle.loads(string)

	def dump(self):
		return pickle.dumps(self._cookies)

def init_urllib(cache=None):
	"""
	Initializes urllib cookie handler
	"""
	global _cookie_jar
	data = None
	if cache is not None:
		data = cache.get(CACHE_COOKIES)
	_cookie_jar = _StringCookieJar(data)
	opener = build_opener(HTTPCookieProcessor(_cookie_jar))
	install_opener(opener)

def cache_cookies(cache):
	"""
	Saves cookies to cache
	"""
	global _cookie_jar
	if _cookie_jar:
		cache.set(CACHE_COOKIES, _cookie_jar.dump())

#def request(url, headers={}):
#	 debug('request: %s' % url)
#	 req = urllib2.Request(url, headers=headers)
#	 req.add_header('User-Agent', UA)
#	 response = urllib2.urlopen(req)
#	 data = response.read()
#	 response.close()
#	 debug('len(data) %s' % len(data))
#	 return data

def _solve_http_errors(url, err):
	global _cookie_jar
	import cloudflare
	data = err.read()
	if err.code == 503 and 'cf-browser-verification' in data:
		data = cloudflare.solve(url, _cookie_jar, UA)
		err.close()
	else:
		err.close() # throw exception
		raise err
	
	return data
def request(url, headers={}, binary=False):
	try:
		debug('request: %s' % url)
		req = Request(url, headers=headers)
		req.add_header('User-Agent', UA)
		if _cookie_jar is not None:
			_cookie_jar.add_cookie_header(req)
		response = urlopen(req)
		data = response.read()
		if not binary and not isinstance( data, str ):
			data = data.decode('utf-8')
		response.close()
		debug('len(data) %s' % len(data))
		
	except HTTPError as err:
		debug('Request error (%s)\n%s' % (err.code,traceback.format_exc()))
		data = _solve_http_errors(url, err)
		debug('len(data) %s' % len(data))
	return data

def post(url, data, headers={}, binary=False):
	postdata = urlencode(data)
	if isinstance( postdata, str ):
		postdata = postdata.encode('utf-8')
	req = Request(url, postdata, headers)
	req.add_header('User-Agent', UA)
	response = urlopen(req)
	data = response.read()
	if not binary and not isinstance( data, str ):
		data = data.decode('utf-8')
	response.close()
	return data

def post_json(url,data,headers={}, binary=False):
	postdata = json.dumps(data)
	headers['Content-Type'] = 'application/json'
	if isinstance( postdata, str ):
		postdata = postdata.encode('utf-8')
	req = Request(url,postdata,headers)
	req.add_header('User-Agent',UA)
	response = urlopen(req)
	data = response.read()
	if not binary and not isinstance( data, str ):
		data = data.decode('utf-8')
	response.close()
	return data

def run_parallel_in_threads(target, args_list):
	result = Queue.Queue()
	# wrapper to collect return value in a Queue
	def task_wrapper(*args):
		result.put(target(*args))
	threads = [threading.Thread(target=task_wrapper, args=args) for args in args_list]
	for t in threads:
		t.start()
	for t in threads:
		t.join()
	return result

def icon(name):
	return 'https://github.com/lzoubek/xbmc-doplnky/raw/dharma/icons/' + name

def substr(data, start, end):
	i1 = data.find(start)
	i2 = data.find(end, i1)
	return data[i1:i2]

def save_to_file(url, file):
	try:
		return save_data_to_file(request(url, binary=True), file)
	except:
		traceback.print_exc()

def save_data_to_file(data, file):
	try:
		f = open(file, 'wb')
		f.write(data)
		f.close()
		return True
	except:
		traceback.print_exc()
def read_file(file):
	if not os.path.exists(file):
		return ''
	f = open(file, 'r')
	data = f.read()
	f.close()
	return data

def _substitute_entity(match):
		ent = match.group(3)
		if match.group(1) == '#':
			# decoding by number
			if match.group(2) == '':
				# number is in decimal
				return unichr(int(ent))
			elif match.group(2) == 'x':
				# number is in hex
				return unichr(int('0x' + ent, 16))
		else:
			# they were using a name
			cp = n2cp.get(ent)
			if cp: return unichr(cp)
			else: return match.group()

def decode_html(data):
	if not isinstance(data, str):
		return data
	try:
		if is_py3 == False and not isinstance(data, unicode):
			data = unicode(data, 'utf-8', errors='ignore')
		entity_re = re.compile(r'&(#?)(x?)(\w+);')
		return entity_re.subn(_substitute_entity, data)[0]
	except:
		traceback.print_exc()
		print( data )
		return data

def debug(text):
		
		text = "xbmc_doplnky: debug " + (str([text]))
		print( "############## RESOLVER ############## [DEBUG] %s" % text )
		client.log.debug(text)

def info(text):
		text = "xbmc_doplnky: info " + (str([text]))
		print( "############## RESOLVER ############## [INFO] %s" % text )
		client.log.info(text)

def error(text):
		text = "xbmc_doplnky: error" + (str([text]))
		print( "############## RESOLVER ############## [ERROR] %s" % text )
		client.log.error(text)


_diacritic_replace= {
u'\u00f3':'o',
u'\u00d3':'O',
u'\u00f4':'o',
u'\u00d4':'O',
u'\u0213':'O',
u'\u00e1':'a',
u'\u00c1':'A',
u'\u00e4':'a',
u'\u00C4':'A',
u'\u010d':'c',
u'\u010c':'C',
u'\u010f':'d',
u'\u010e':'D',
u'\u00e9':'e',
u'\u011b':'e',
u'\u011a':'E',
u'\u00c9':'E',
u'\u00ed':'i',
u'\u00cd':'I',
u'\u013e':'l',
u'\u013d':'L',
u'\u0148':'n',
u'\u0147':'N',
u'\u0159':'r',
u'\u0158':'R',
u'\u0160':'S',
u'\u0161':'s',
u'\u0165':'t',
u'\u0164':'T',
u'\u016f':'u',
u'\u016e':'U',
u'\u00fa':'u',
u'\u00da':'U',
u'\u00fd':'y',
u'\u00dd':'Y',
u'\u017e':'z',
u'\u017d':'Z',
u'\xed':'i',
u'\xe9':'e',
u'\xe1':'a',
}

def replace_diacritic(string):
	ret = []
	for char in string:
		if char in _diacritic_replace:
			ret.append(_diacritic_replace[char])
		else:
			ret.append(char)
	return ''.join(ret)


def int_to_base(number, base):
	digs = string.digits + string.letters
	if number < 0:
		sign = -1
	elif number == 0:
		return digs[0]
	else:
		sign = 1
	number *= sign
	digits = []
	while number:
		digits.append(digs[number % base])
		number /= base
	if sign < 0:
		digits.append('-')
	digits.reverse()
	return ''.join(digits)


def extract_jwplayer_setup(data):
	"""
	Extracts jwplayer setup configuration and returns it as a dictionary.

	:param data: A string to extract the setup from
	:return: A dictionary containing the setup configuration
	"""
	data = re.search(r'<script.+?}\(\'(.+)\',\d+,\d+,\'([\w\|]+)\'.*</script>', data, re.I | re.S)
	if data:
		replacements = data.group(2).split('|')
		data = data.group(1)
		for i in reversed(range(len(replacements))):
			if len(replacements[i]) > 0:
				data = re.sub(r'\b%s\b' % int_to_base(i, 36), replacements[i], data)
		data = re.search(r'\.setup\(([^\)]+?)\);', data)
		if data:
			return json.decode(data.group(1).decode('string_escape'))
	return None
