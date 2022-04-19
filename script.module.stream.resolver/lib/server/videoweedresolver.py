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
__name__ = 'videoweed'
def supports(data):
	return not _regex(data) == None

def resolve(url):
	if not _regex(url) == None:
		data = util.request(url.replace('&#038;','&'))
		data = util.substr(data,'flashvars','params')
		domain = re.search('flashvars\.domain=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		file = re.search('flashvars\.file=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		key = re.search('flashvars\.filekey=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		data = util.request('%s/api/player.api.php?key=%s&file=%s&user=undefined&codes=undefined&pass=undefined'% (domain,key,file))
		m = re.search('url=(?P<url>[^\&]+)',data,re.IGNORECASE | re.DOTALL)
		if not m == None:
			return [{'url':m.group('url')}]

def _regex(data):
	return re.search('http\://embed.videoweed.com(.+?)', data, re.IGNORECASE | re.DOTALL)
