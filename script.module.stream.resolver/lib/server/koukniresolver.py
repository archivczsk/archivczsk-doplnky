# -*- coding: UTF-8 -*-
# /*
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
import re, util, traceback
__name__ = 'koukni.cz'
def supports(url):
	return not _regex(url) == None

# returns the steam url
def url(url):
	m = _regex(url)
	if not m == None:
		iframe = _iframe(url)
		if iframe:
			return iframe[0]['url']

def resolve(url):
	m = _regex(url)
	if not m == None:
		try:
			iframe = _iframe(url)
		except:
			traceback.print_exc()
			return
		if iframe:
			return iframe
		# else:
		#	 return [{'name':__name__,'quality':'720p','url':url,'surl':url}]

def _furl(url):
	if url.startswith('http'):
		return url
	url = url.lstrip('./')
	return 'http://www.koukni.cz/' + url

def _iframe(url):
	index = url.find('&')
	if index > 0:
		url = url[:index]
	iframe = re.search('(\d+)$', url, re.IGNORECASE | re.DOTALL)
	if iframe:
		data = util.request(url)
		ress = re.search('var api = flowplayer\(\),\s+resolutions = \{([^\}]+)\}', data, re.IGNORECASE | re.DOTALL)
		valid_ress = re.compile("<span[^>]*>([^<]+)</span>", re.IGNORECASE | re.DOTALL).findall(data)
		subs = re.search('<track.+?src=\"(?P<url>[^\"]+)', data, re.IGNORECASE | re.DOTALL)
		if ress:
			ret = []
			ress = ress.group(1).strip().split(',')
			for r in ress:
				r = r.replace('"', '').split(':')
				res = r[0].strip()
				vurl = _furl(r[1].strip())
				if res in valid_ress:
					v = {'name':__name__, 'url':vurl, 'quality':res, 'surl':url,'subs':''}
					if subs:
						v['subs'] = _furl(subs.group('url'))
					ret.append(v)
			if len(ret)>0:
				return ret
		video = re.search('url\: \'(?P<url>mp4[^\']+)', data, re.IGNORECASE | re.DOTALL)
		subs = re.search('captionUrl\: \'(?P<url>[^\']+)', data, re.IGNORECASE | re.DOTALL)
		if video:
			ret = {'name':__name__, 'quality':'720p', 'surl':url}
			ret['url'] = 'rtmp://koukni.cz/mp4 playpath=%s' % video.group('url')
			if subs:
				ret['subs'] = _furl(subs.group('url'))
			return [ret]

def _regex(url):
	return re.search('(www\.)?koukni.cz/(.+?)', url, re.IGNORECASE | re.DOTALL)
