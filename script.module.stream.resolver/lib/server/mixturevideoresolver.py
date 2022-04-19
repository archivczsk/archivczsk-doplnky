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
import re,util,traceback,resolver

try:
	import cookielib
	from urllib2 import urlopen, Request, HTTPRedirectHandler, HTTPCookieProcessor, build_opener, install_opener
except:
	from urllib.request import urlopen, Request, HTTPRedirectHandler, HTTPCookieProcessor, build_opener, install_opener


__name__ = 'mixturecloud'

def supports(url):
	return not _regex(url) == None

class MyHTTPRedirectHandler(HTTPRedirectHandler):

	def http_error_302(self, req, fp, code, msg, headers):
		self.location = headers.getheader('Location')
		return HTTPRedirectHandler.http_error_302(self, req, fp, code, msg, headers)

# returns the steam url
def resolve(url):
	m = _regex(url)
	if m:
		defrhandler = HTTPRedirectHandler
		cookieprocessor = HTTPCookieProcessor()
		redirecthandler = MyHTTPRedirectHandler()
		opener = build_opener(redirecthandler, cookieprocessor)
		install_opener(opener)
		req = Request(url)
		response = urlopen(req)
		response.close()
		install_opener(build_opener(defrhandler,cookieprocessor))
		# mixturevideo uses REDIRECT to 'secret url' ;-)
		url = redirecthandler.location
		item = resolver.item()
		item['surl'] = url
		item['name'] = __name__
		try:
			ishd = re.search('hd\.state=([^\&]+)',url).group(1)
			streamer = re.search('streamer=([^$]+)',url).group(1)+'&start=0&'
			if ishd == 'true':
				item['url'] = streamer + 'hd.file=' +re.search('hd\.file=([^\&]+)',url).group(1)
				item['quality'] = 'hd'
			else:
				item['url'] = streamer + 'file=' +re.search('file=([^\&]+)',url).group(1)
			return [item]
		except:
			traceback.print_exc()
			pass

def _regex(url):
	return re.search('player\.mixturecloud\.com',url,re.IGNORECASE | re.DOTALL)

