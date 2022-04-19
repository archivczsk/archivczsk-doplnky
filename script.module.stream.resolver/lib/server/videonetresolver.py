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
import re,util
__name__ = '24video'
def supports(url):
	return not _regex(url) == None

	
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
	
	
	
# returns the steam url
def url(url):
	m = _regex(url)
	if not m == None:
		data = latin2text(util.request('%s%s%s?mode=play' % (m.group('url') ,m.group('html'),m.group('id'))))
		f = re.search('<videos><video url=\'(.+?)[^ ] rating',data,re.IGNORECASE | re.DOTALL)
		if f:
			return [f.group(1)]

def resolve(u):
	stream = url(u)
	if stream:
		return [{'name':__name__,'quality':'480p','url':stream[0],'surl':u}]
			
			
def _regex(url):
	return re.search('id=(?P<id>.+?)&idHtml=(?P<html>.+?)&.*rootUrl=(?P<url>.+?)&',url,re.IGNORECASE | re.DOTALL)
