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

__name__ = 'publicvideohost'
def supports(url):
	return not _regex(url) == None

def gen_random_decimal(i, d):
	return decimal.Decimal('%d.%d' % (random.randint(0, i), random.randint(0, d)))

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		id = int(m.group('v'))
		params = {
				  'v':id,
				  }
		quality = "480p"
		data = util.request("http://embed.publicvideohost.org/v.php?" + urlencode(params))
		vurl = re.search('file\:(.*?)\"(?P<url>[^"]+)',data, re.IGNORECASE | re.DOTALL).group('url')
		return [{'quality':quality, 'url':vurl}]
	
	
def _regex(url):
	m = re.search('http://embed\.publicvideohost\.org/v\.php\?(.+?)v=(?P<v>[0-9]+)', url, re.IGNORECASE | re.DOTALL)
	return m
	
