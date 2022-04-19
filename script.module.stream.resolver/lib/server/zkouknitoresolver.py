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
__name__ = 'zkouknito'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	m = _regex(url)
	f=None
	if not m is None:
		try:
			data = util.request('http://www.zkouknito.cz/player/scripts/videoinfo_externi.php?id=%s' % m.group('id'))
			f = re.search('<file>([^<]+)', data, re.IGNORECASE | re.DOTALL)
		except Exception:
			data = util.request(url)
			f = re.search("\'file\':.*?'([^']+)", data, re.IGNORECASE | re.DOTALL)
		if f:
			return [{'url':f.group(1)}] 


def _regex(url):
	m1 = re.search('(www\.)zkouknito.cz/(.+?)vid=(?P<id>[\d]+)', url, re.IGNORECASE | re.DOTALL)
	m2 = re.search('(www\.)zkouknito.cz/(.+?)', url, re.IGNORECASE | re.DOTALL)
	return m1 or m2
