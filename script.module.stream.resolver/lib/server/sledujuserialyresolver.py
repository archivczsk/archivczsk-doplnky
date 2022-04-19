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
import re,util,traceback
__name__ = 'zkouknito.cz'
def supports(url):
	return not _regex(url) == None

def resolve(url):
	m = _regex(url)
	if not m == None:
		data = util.request(url)
		if data.find('jwplayer(\'mediaplayer') > 0:
			video = re.search('\'file\'\: \'(?P<url>.+?[flv|mp4])\'',data)
			if video:
				
				item = {}
				item['url'] = video.group('url')
				subs = re.search('\'file\'\: \'(?P<url>.+?srt)',data)
				if subs:
					item['subs'] = _furl(subs.group('url'))
				print( item )
				return [item]

def _furl(url):
	if url.startswith('http'):
		return url
	url = url.lstrip('./')
	return 'http://www.sledujuserialy.cz/'+url

def _regex(url):
	return re.search('(www\.)?sledujuserialy.cz/(.+?)',url,re.IGNORECASE | re.DOTALL)
