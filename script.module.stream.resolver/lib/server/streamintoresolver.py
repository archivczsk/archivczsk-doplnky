# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2013 Libor Zoubek
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
__name__ = 'streamin.to'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		data = util.request('http://streamin.to/'+m.group('url'))
		n = re.search('config:{file:\'(.+?)\'',data,re.IGNORECASE | re.DOTALL)
		k = re.search('streamer: \"(.+?)\"',data,re.IGNORECASE | re.DOTALL)
		quality = '???'
		q = re.search('x(\d+)\.html',url)
		if q:
			quality = q.group(1)+'p'
		if n and k:
			url = '%s playpath=%s' % (k.group(1).strip(),n.group(1).strip())
			return [{'quality':quality,'url':url}]

def _regex(url):
	return re.search('streamin\.to/(?P<url>.+?)$',url,re.IGNORECASE | re.DOTALL)
