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
import re,util,traceback
__name__ = 'koukejse.cz'
def supports(url):
	return not _regex(url) == None

def resolve(url):
	m = _regex(url)
	if not m == None:
		data = util.request(url)
		stream = re.search('_video_file = \'(?P<url>[^\']+)',data)
		if stream:
			return [{'name':__name__,'quality':'360p','url':stream.group('url'),'surl':url}]

def _regex(url):
	return re.search('koukejse\.cz/(.+?)',url,re.IGNORECASE | re.DOTALL)
