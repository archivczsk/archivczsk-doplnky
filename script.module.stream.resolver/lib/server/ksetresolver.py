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
import re, util, decimal, random, base64

try:
	from urllib import urlencode
except:
	from urllib.parse import urlencode


__name__ = 'kset'
def supports(url):
	return not _regex(url) == None

def gen_random_decimal(i, d):
	return decimal.Decimal('%d.%d' % (random.randint(0, i), random.randint(0, d)))

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		id = int(m.group('id'))
		headers = {
				   "Referer":"http://st.kset.kz/pl/pl.swf"
				   }
		
		params = {
				  'id':id,
				  'ref':'http://kset.kz/video_frame.php?id=%d' % id,
				  'r':gen_random_decimal(0, 99999999999999)
				  }
		quality = "480p"
		data = util.request("http://kset.kz/v.php?" + urlencode(params), headers=headers)
		item = util.json.loads(base64.decodestring(data))
		return [{'quality':quality, 'url':item[u'file']}]
	
	
def _regex(url):
	m = re.search('http://kset\.kz/video_frame\.php\?id=(?P<id>[0-9]+)', url, re.IGNORECASE | re.DOTALL)
	return m
	
