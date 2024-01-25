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

from . import util
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from ..resolver.resolver import rslog

try:
	from htmlentitydefs import name2codepoint as n2cp
	import cookielib
	from urllib2 import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib import urlencode
	is_py3 = False

	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')

except:
	from html.entities import name2codepoint as n2cp
	from urllib.request import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlencode
	import http.cookiejar as cookielib
	is_py3 = True
	unicode = str
	unichr = chr
	basestring = str

	def py2_decode_utf8( text ):
		return text

	def py2_encode_utf8( text ):
		return text

try:
	from Plugins.Extensions.archivCZSK.settings import USER_AGENT
	UA = USER_AGENT
except:
	UA = 'Mozilla/6.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.5) Gecko/2008092417 Firefox/3.0.3'
	pass

__lang__ = ArchivCZSK.get_xbmc_addon('tools.xbmc').getLocalizedString

client_version = 0
if hasattr(client,'getVersion'):
	client_version = client.getVersion()
# compatibility for older version
if isinstance(client_version, basestring):
	client_version = 1

##
# initializes urllib cookie handler
def init_urllib():
	cj = cookielib.LWPCookieJar()
	opener = build_opener(HTTPCookieProcessor(cj))
	install_opener(opener)

def request(url, headers={}):
	debug('request: %s' % url)
	req = Request(url, headers=headers)
	response = urlopen(req)
	data = response.read()
	response.close()
	debug('len(data) %s' % len(data))
	return data

def post(url, data):
	postdata = urlencode(data)
	if isinstance( postdata, str ):
		postdata = postdata.encode('utf-8')
	req = Request(url, postdata)
	req.add_header('User-Agent', UA)
	response = urlopen(req)
	data = response.read()
	response.close()
	return data

def icon(name):
	return 'https://github.com/lzoubek/xbmc-doplnky/raw/dharma/icons/' + name

def substr(data, start, end):
	i1 = data.find(start)
	i2 = data.find(end, i1)
	return data[i1:i2]

def save_to_file(url, file):
	try:
		f = open(file, 'w')
		f.write(request(url))
		f.close()
		return True
	except:
		client.log.error(traceback.format_exc())


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
	try:
		if is_py3 == False and not isinstance(data, unicode):
			data = unicode(data, 'utf-8', errors='ignore')
		entity_re = re.compile(r'&(#?)(x?)(\w+);')
		return entity_re.subn(_substitute_entity, data)[0]
	except:
		client.log.error(traceback.format_exc())
		#print( [data] )
		return data

def debug(text):
	text = "xbmc_doplnky: debug " + (str([text]))
	rslog.logDebug(text)
	client.log.debug(text)

def info(text):
	text = "xbmc_doplnky: info " + (str([text]))
	rslog.logInfo(info)
	client.log.info(text)

def error(text):
	text = "xbmc_doplnky: error" + (str([text]))
	rslog.logError(error)
	client.log.error(text)


def get_searches(addon, server, maximum=10):
	local = addon.get_info('data_path')
	if not os.path.exists(local):
		os.makedirs(local)
	local = os.path.join(local, server)
	if not os.path.exists(local):
		return []
	try:
		with open(local, 'r') as f:
			searches = json.load(f)
	except:
		searches = []

	remove = len(searches) - maximum
	if remove > 0:
		for i in range(remove):
			searches.pop()

		with open(local, 'w') as f:
			json.dump(searches, f)

	return searches


def add_search(addon, server, search, maximum):
	searches = []
	local = addon.get_info('data_path')
	if not os.path.exists(local):
		os.makedirs(local)
	local = os.path.join(local, server)
	if os.path.exists(local):
		try:
			with open(local, 'r') as f:
				searches = json.load(f)
		except:
			searches = []

	if search in searches:
		searches.remove(search)
	searches.insert(0, search)
	remove = len(searches) - maximum
	if remove > 0:
		for i in range(remove):
			searches.pop()

	with open(local, 'w') as f:
		json.dump(searches, f)


def remove_search(addon, server, search):
	local = addon.get_info('data_path')
	if not os.path.exists(local):
		return
	local = os.path.join(local, server)
	if os.path.exists(local):
		try:
			with open(local, 'r') as f:
				searches = json.load(f)
		except:
			searches = []
		searches.remove(search)
		with open(local, 'w') as f:
			json.dump(searches, f)


def edit_search(addon, server, search, replacement):
	local = addon.get_info('data_path')
	if not os.path.exists(local):
		return
	local = os.path.join(local, server)
	if os.path.exists(local):
		try:
			with open(local, 'r') as f:
				searches = json.load(f)
		except:
			searches = []

		searches.remove(search)
		searches.insert(0, replacement)
		with open(local, 'w') as f:
			json.dump(searches, f)


def add_search_item(name, params, logo=None, infoLabels={}, menuItems={}):
	name = decode_html(name)
	for key in list(params.keys()):
		value = decode_html(params[key])
		value = py2_encode_utf8( value )
		params[key] = value
	if not 'title' in infoLabels:
		infoLabels['title'] = name
	client.add_dir(name, params, image=logo, infoLabels=infoLabels, menuItems=menuItems, search_item=True)

def add_search_folder(name, params, logo=None, infoLabels={}, menuItems={}):
	name = decode_html(name)
	for key in list(params.keys()):
		value = decode_html(params[key])
		value = py2_encode_utf8( value )
		params[key] = value
	if not 'title' in infoLabels:
		infoLabels['title'] = name
	client.add_dir(name, params, image=logo, infoLabels=infoLabels, menuItems=menuItems, search_folder=True)

def add_dir(name, params, logo=None, infoLabels={}, menuItems={}, addonDataItem=None, traktItem=None):
	name = decode_html(name)
	for key in list(params.keys()):
		value = decode_html(params[key])
		value = py2_encode_utf8( value )
		params[key] = value
	if not 'title' in infoLabels:
		infoLabels['title'] = name
	#client.add_dir(name, params, image=logo, infoLabels=infoLabels, menuItems=menuItems)
	try:
		client.add_dir(name, params, logo, infoLabels=infoLabels, menuItems=menuItems, dataItem=addonDataItem, traktItem=traktItem)
	except:
		# back compatibility
		client.add_dir(name, params, logo, infoLabels=infoLabels, menuItems=menuItems )

def add_video(name, params={}, logo=None, infoLabels={}, menuItems={}, addonDataItem=None, traktItem=None):
	name = decode_html(name)
	for key in list(params.keys()):
		value = decode_html(params[key])
		value = py2_encode_utf8( value )
		params[key] = value
	try:
		client.add_dir(name, params, logo, infoLabels=infoLabels, menuItems=menuItems, video_item=True, dataItem=addonDataItem, traktItem=traktItem)
	except:
		# back compatibility
		try:
			client.add_dir(name, params, logo, infoLabels=infoLabels, menuItems=menuItems, video_item=True)
		except:
			add_dir(name, params, logo=logo, infoLabels=infoLabels, menuItems=menuItems)

def add_play(title, provider_name, quality, url, subs=None, filename=None, image=None, infoLabels={}, menuItems={},headers={}, lang=None, resolveTitle=None, customTitle=None, customFname=None, addonDataItem=None, player_settings=None, traktItem=None):

	if customTitle:
		title = customTitle
	if customFname:
		filename = customFname

	infoLabels['title'] = replace_diacritic2(title)

	settings = {"extra-headers":headers}

	if player_settings:
		settings.update( player_settings )

	title = replace_diacritic2(title)
	quality = replace_diacritic2(quality)
	provider_name = replace_diacritic2(provider_name)
	if lang:
		lang = replace_diacritic2(lang)
	if client_version != 0:
		if client_version > 1:
			if addonDataItem is None:
				client.add_video(title, url, subs=subs, quality = quality, provider_name = provider_name, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings, lang=lang, traktItem=traktItem)
			else: # back compatibility
				try:
					client.add_video(title, url, subs=subs, quality = quality, provider_name = provider_name, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings, lang=lang, dataItem=addonDataItem, traktItem=traktItem)
				except: # old version archiv using
					client.add_video(title, url, subs=subs, quality = quality, provider_name = provider_name, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings, lang=lang)
		else:
			if resolveTitle:
				name = replace_diacritic2(resolveTitle)
			else:
				if lang:
					name = '[%s][%s] %s - %s'%(quality, lang, provider_name, title)
				else:
					name = '[%s] %s - %s' % (quality,provider_name, title)

			if addonDataItem is None:
				client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings, traktItem=traktItem)
			else: # back compatibility
				try:
					client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings, dataItem=addonDataItem, traktItem=traktItem)
				except:
					client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings)
	else:
		if resolveTitle:
			name = replace_diacritic2(resolveTitle)
		else:
			if lang:
					name = '[%s][%s] %s - %s'%(quality, lang, provider_name, title)
			else:
				name = '[%s] %s - %s' % (quality, provider_name, title)
		if addonDataItem is None:
			client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, traktItem=traktItem)
		else: # back compatibility
			try:
				client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, dataItem=addonDataItem, traktItem=traktItem)
			except:
				client.add_video(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems)

def create_play_it(title, provider_name, quality, url, subs=None, filename=None, image=None, infoLabels={}, menuItems={},headers={}):
	name = '%s - %s[%s]' % (decode_html(title), decode_html(provider_name), decode_html(quality))
	if not 'title' in infoLabels:
		infoLabels['title'] = name
	settings = {"extra-headers":headers}
	return client.create_video_it(name, url, subs=subs, filename=filename, image=image, infoLabels=infoLabels, menuItems=menuItems, settings=settings)

def add_playlist(name,playlist):
	client.add_playlist(name,playlist)

_diacritic_replace2 = {
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
u'\u017d':'Z'
}

def replace_diacritic2(string):
	try:
		tmp = decode_html(string)
		ret = []
		for char in tmp:
			if char in _diacritic_replace2:
				ret.append(_diacritic_replace2[char])
			else:
				ret.append(char)
		return ''.join(ret)
	except:
		#log
		client.log.error( "replace_diacritic2 failed.\n%s" % traceback.format_exc() )
		return string
