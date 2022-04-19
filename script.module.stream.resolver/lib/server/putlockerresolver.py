# -*- coding: UTF-8 -*-
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
# *
# */

# thanks to:
#	https://github.com/Eldorados

import re,util,os

try:
	from urllib2 import URLError
except:
	from urllib.error import URLError

__name__ = 'putlocker'


def supports(url):
	return not _regex(url) == None

			
def get_host_and_id(url):
	r = re.search('//(.+?)/(?:file|embed)/([0-9A-Z]+)', url)
	if r:
			return r.groups()
	else:
			return False
				
def get_host(host,media_id):
	#host,media_id=get_host_and_id(url)
	if 'putlocker' in host:
		host = 'www.putlocker.com'
	else:
		host = 'www.sockshare.com'
	return 'http://%s/file/%s' % (host, media_id)
				
			

def login_stale():
	url = 'http://www.putlocker.com/cp.php'
	if not os.path.exists(cookie_file):
		return True
	#self.net.set_cookies(cookie_file)
	source =  util.request(url)
	if re.search('(?:<span class=pro_user>\( Pro \)</span>|<span class="free_user">\( Free \)</span>)', source):
			print('Putlocker account appears to be logged in.')
			return False
	else:
			return True

				
				
# returns the steam url
def url(url):
	if supports(url):
	
		'''
		if self.get_setting('login') == 'true':
			if login_stale():
				login()
		#self.net.set_cookies(cookie_file)
		'''
		
		host,media_id=get_host_and_id(url)
		web_url = get_host(host,media_id)

		#find session_hash
		try:
			html = util.request(web_url)
		except URLError as e:
			print('putlocker: got http error %d fetching %s' % (e.code, web_url))
			return False
		
		#Shortcut for logged in users
		pattern = '<a href="(/.+?)" class="download_file_link" style="margin:0px 0px;">Download File</a>'
		link = re.search(pattern, html)
		if link:
			print( 'Direct link found: %s' %link.group(1) )
			return 'http://www.putlocker.com%s' %link.group(1)

		r = re.search('value="([0-9a-f]+?)" name="hash"', html)
		if r:
			session_hash = r.group(1)
		else:
			print('putlocker: session hash not found')
			return False

		#post session_hash
		try:
			html = util.post(web_url, {'hash': session_hash,'confirm': 'Continue as Free User'})
		except URLError as e:
			print('putlocker: got http error %d posting %s' %(e.code, web_url))
			return False
		
		#find playlist code	 
		r = re.search('\?stream=(.+?)\'', html)
		if r:
			playlist_code = r.group(1)
		else:
			r = re.search('key=(.+?)&',html)
			playlist_code = r.group(1)
		
		#find download link
		#q = self.get_setting('quality')
		q = '1'
		
		#Try to grab highest quality link available
		if q == '1':
			#download & return link.
			if 'putlocker' in host:
				Avi = "http://putlocker.com/get_file.php?stream=%s&original=1"%playlist_code
				html = util.request(Avi)
				final=re.compile('url="(.+?)"').findall(html)[0].replace('&amp;','&')
				return [final]
			else:
				Avi = "http://sockshare.com/get_file.php?stream=%s&original=1"%playlist_code
				html = util.request(Avi)
				final=re.compile('url="(.+?)"').findall(html)[0].replace('&amp;','&')
				return [final]

		#Else grab standard flv link
		else:
			xml_url = re.sub('/(file|embed)/.+', '/get_file.php?stream=', web_url)
			xml_url += playlist_code
			try:
				html = util.request(xml_url)
			except URLError as e:
				pritn ('putlocker: got http error %d fetching %s'(e.code, xml_url))
				return False
	
			r = re.search('url="(.+?)"', html)
			if r:
				flv_url = r.group(1)
			else:
				print('putlocker: stream url not found')
				return False
			
			return [flv_url.replace('&amp;','&')]
				
				
def resolve(u):
	stream = url(u)
	if stream:
		return [{'name':__name__,'quality':'360p','url':stream[0],'surl':u}]
				
				
def _regex(url):
	return re.search('http://(www.)?(putlocker|sockshare).com/' +  '(file|embed)/[0-9A-Z]+', url,re.IGNORECASE | re.DOTALL) 
