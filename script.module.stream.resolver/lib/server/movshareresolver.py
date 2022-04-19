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
__name__='movshare'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def resolve(url):
	if not _regex(url) == None:
		data = util.substr(util.request(url),'<embed type=\"video/divx','>')
		stream = re.search('src=\"([^\"]+)',data,re.IGNORECASE | re.DOTALL).group(1)
		return [{'url':stream}]

def _regex(url):
	return re.search('movshare.net/(.+?)',url,re.IGNORECASE | re.DOTALL)
