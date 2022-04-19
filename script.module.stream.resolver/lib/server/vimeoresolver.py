# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2014 mx3L
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

import re
import random
import decimal

import util

__name__='vimeo'

def supports(url):
	return not _regex(url) == None

def resolve(url):
	m = _regex(url)
	if m:
		ret = []
		data = util.request("http://player.vimeo.com/v2/video/%s/config?type=moogaloop&referrer=&player_url=player.vimeo.com&v=1.0.0&cdn_url=http://a.vimeocdn.com"%m.group('id'))
		data = util.json.loads(data)
		h264 = data["request"]["files"]["h264"]
		for quality in h264.keys():
			item = {}
			item['title'] = data['video']['title']
			item['length'] = data['video']['duration']
			item['quality'] = quality == 'hd' and '720p' or '480p'
			item['url'] = h264[quality]['url']
			ret.append(item)
		return ret

def _regex(url):
	return re.search('player.vimeo.com/video/(?P<id>\d+)',url,re.IGNORECASE | re.DOTALL)
