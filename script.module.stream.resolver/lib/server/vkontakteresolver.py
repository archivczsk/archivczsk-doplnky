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
__name__ = 'vkontakte'
def supports(url):
	return not _regex(url) == None

def resolve(link):
	if not _regex(link) == None:
		data = util.request(link)
		data = util.substr(data,'div id=\"playerWrap\"','<embed>')
		if len(data) > 0:
			host = re.search('host=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			oid = re.search('oid=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			uid = re.search('uid=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			vtag = re.search('vtag=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			hd = re.search('hd_def=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			max_hd = re.search('hd=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			no_flv = re.search('no_flv=([^\&]+)',data,re.IGNORECASE | re.DOTALL).group(1)
			url = '%su%s/videos/%s' % (host,uid,vtag)
			if no_flv != '1':
				return [{'name':__name__,'quality':'???','url':url+'.flv','surl':link,'subs':''}]
			if no_flv == '1':
				res=int(hd)
				if max_hd:
					res=int(max_hd)
				if res < 0:
					return [{'name':__name__,'quality':'240p','url':url+'.flv','surl':link,'subs':''}]
				resolutions=['240','360','480','720','1080']
				ret = []
				for index,resolution in enumerate(resolutions):
					if index>res:
						return ret
					ret.append({'name':__name__,'quality':resolution+'p','url':url+'.'+resolution+'.mp4','surl':link,'subs':''})
				return ret

def _regex(data):
	return re.search('http\://(vkontakte.ru|vk.com)/(.+?)', data, re.IGNORECASE | re.DOTALL)
