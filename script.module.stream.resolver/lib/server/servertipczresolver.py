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
__name__ = 'servertip'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	if supports(url):
		data = util.request(url)
		data = util.substr(data,'<div id=\"player_code','</div')
		try:
			video_id = re.search('flv\|\|([^\|]+)',data).group(1)
			return [{'url':'http://servertip.cz/cgi-bin/dl.cgi/%s/video.flv' % video_id}]
		except:
			pass

def _regex(url):
	return re.search('servertip\.cz',url,re.IGNORECASE | re.DOTALL)

