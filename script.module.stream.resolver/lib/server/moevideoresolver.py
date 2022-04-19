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
__name__ = 'moevideo'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def url(url):
	m = _regex(url)
	if m:
		id = m.group('id')
		post = {'r':'["tVL0gjqo5",["preview/flv_image",{"uid":"'+id+'"}],["preview/flv_link",{"uid":"'+id+'"}]]'}
		data = util.post('http://api.letitbit.net',post)
		data = data.replace('\\','')
		print( data )
		link = re.search('link\"\:\"(?P<link>[^\"]+)',data)
		if link:
			return [{'url':link.group('link')}]

def _regex(url):
	return re.search('moevideo.net/video\.php\?file=(?P<id>[^\&]+)',url,re.IGNORECASE | re.DOTALL)
