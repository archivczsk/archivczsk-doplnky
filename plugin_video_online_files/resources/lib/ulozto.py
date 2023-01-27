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
import re,random,util,sys,os,traceback
try:
	import simplejson as json
except ImportError:
	import json
from base64 import b64decode
from provider import ContentProvider
from provider import ResolveException

try:
	from urllib2 import urlopen, Request, HTTPError, HTTPCookieProcessor, HTTPRedirectHandler, build_opener, install_opener, OpenerDirector, HTTPHandler, UnknownHandler
	import cookielib
	from urllib import quote, unquote, urlencode
	string_escape = 'string_escape'
except:
	from urllib.request import urlopen, Request, HTTPCookieProcessor, HTTPRedirectHandler, build_opener, install_opener, OpenerDirector, HTTPHandler, UnknownHandler
	from urllib.error import HTTPError
	import http.cookiejar as cookielib
	from urllib.parse import quote, unquote, urlencode
	string_escape = 'unicode_escape'


class UloztoContentProvider(ContentProvider):

	def __init__(self,username=None,password=None,filter=None):
		ContentProvider.__init__(self,'ulozto.cz','https://www.ulozto.cz/',username,password,filter)
		self.search_type=''
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.rh = UloztoHTTPRedirectHandler()
		self.rh.throw = False
		self.rh.location = None
		self.init_urllib()

	def init_urllib(self):	
		opener = build_opener(self.cp,self.rh)
		install_opener(opener)

	def capabilities(self):
		return ['login','search','resolve','categories']

	def categories(self):
		result = []
		if not self.login():
			return result
		data = util.request(self.base_url+'m/'+self.username)
		fav = re.search('<li id=\"fmFavoritesFolder.+?href=\"(?P<url>[^\"]+)[^>]*>(?P<title>[^<]+)',data,re.IGNORECASE|re.DOTALL)
		if fav:
			item = self.dir_item()
			item['url'] = '#fm#'+fav.group('url')
			item['title'] = fav.group('title')
			result.append(item)
		myfiles = re.search('<a class=\"fmHomeFolder.+?href=\"(?P<url>[^\"]+)[^>]*>(?P<title>[^<]+)',data,re.IGNORECASE|re.DOTALL)
		if myfiles:
			item = self.dir_item()
			item['url'] = '#fm#' + myfiles.group('url')
			item['title'] = myfiles.group('title')
			result.append(item)
		return result

	def search(self,keyword):
		return self.list(self.base_url+'hledej/?'+self.search_type+'q='+quote(keyword))

	def login(self):
		if self.username and self.password and len(self.username)>0 and len(self.password)>0:
			self.info('Login user=%s, pass=*****' % self.username)
			self.rh.throw = False
			page = util.request(self.base_url+'login?key=logreg')
			if page.find('href="/?do=web-logout') > 0:
				self.info('Already logged in')
				return True
			data = util.substr(page,'<li class=\"menu-username','</li')
			m = re.search('key=(?P<key>[^\"]+)\"',data,re.IGNORECASE | re.DOTALL)
			token = re.search('<input type=\"hidden\" name=\"_token_\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
			if m and token:
				login_url = self.base_url+'login?key='+m.group('key')+'&do=loginForm-submit'
				data = util.post(login_url,{'username':self.username,'password':self.password,'remember':'on','login':'Prihlasit','_token_':token.group(1)})
				if data.find('href="/?do=web-logout') > 0:
					self.info('Login successfull')
					return True
			self.info('Login failed')
		return False

	def list_folder(self,url):
		self.login()
		result = []
		page = util.request(self._url(url))
		page = util.substr(page,'<div id=\"fmItems','</ul')
		for m in re.finditer('<div class=\"fmFolder(.+?)</em',page,re.IGNORECASE | re.DOTALL):
			data = m.group(1)
			item = self.dir_item()
			item['url'] = '#fm#' + re.search('data-href=\"([^\"]+)',data).group(1)
			item['title'] = re.search('data-name=\"([^\"]+)',data).group(1)
			item['img'] = re.search('<img src=\"([^\"]+)',data).group(1)
			result.append(item)
		for m in re.finditer('<div class=\"fmFile(.+?)</em>',page,re.IGNORECASE | re.DOTALL):
			data = m.group(1)
			item = self.video_item()
			item['url'] = re.search('data-href=\"([^\"]+)',data).group(1)
			item['title'] = '%s.%s' % (re.search('data-name=\"([^\"]+)',data).group(1),re.search('data-ext=\"([^\"]+)',data).group(1))
			item['img'] = re.search('<img src=\"([^\"]+)',data).group(1)
			result.append(item)
		return result

	def list(self,url):
		if url.find('#fm#') == 0:
			return self.list_folder(url[5:])
		url = self._url(url)
		page = util.request(url,headers={'X-Requested-With':'XMLHttpRequest','Referer':url,'Cookie':'uloz-to-id=1561277170;'}, binary=True).decode(string_escape)
		script = util.substr(page,'var kn','</script>')
		keymap = None
		key = None
		k = re.search(r'({.+?})',script)
		if k:
			keymap = util.json.loads(k.group(1))
		j = re.search(r'ad.push\(\[kn, kn\["([^"]+)', script)
		if j:
			key = j.group(1)
		if not (j and k):
			self.error('error parsing page - unable to locate keys')
			return []
		burl = b64decode('I2h0dHA6Ly9kZWNyLWNlY2gucmhjbG91ZC5jb20vZGVjcnlwdC8/a2V5PSVzJnZhbHVlPSVz')
		murl = b64decode('aHR0cDovL2RlY3ItY2VjaC5yaGNsb3VkLmNvbS9kZWNyeXB0Lw==')
		result = []
		req = {'seed':keymap[key],'values':keymap}
		decr = json.loads(util.post_json(murl,req))
		for li in re.finditer('<div data-icon=\"(?P<key>[^\"]+)',page, re.IGNORECASE |	re.DOTALL):
			body = unquote(b64decode(decr[li.group('key')]))
			div_name = util.substr(body, '<div class="name"', '</div>')
			title_url_match = re.search(r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)', div_name)

			if not title_url_match:
				continue
			item = self.video_item()
			item['title'] = title_url_match.group('title')
			item['url'] = title_url_match.group('url')

			div_media = util.substr(body, 'div class="media"', '<div class="tools">')
			img_match = re.search(r'img src="([^"]+)', div_media)
			if img_match:
				item['img'] = "http:" + img_match.group(1)
			time_match = re.search(r'<span>Čas</span>(.+)', div_media)
			if time_match:
				item['length'] = time_match.group(1).strip()
			size_match = re.search(r'<span>Velikost</span>([^<]+)', div_media)
			if size_match:
				item['size'] = size_match.group(1).strip()
			self._filter(result,item)
		# page navigation
		data = util.substr(page,'<div class=\"paginator','</div')
		mnext = re.search('<a href=\"(?P<url>[^\"]+)\" class="next',data)
		if mnext:
			item = self.dir_item()
			item['type'] = 'next'
			item['url'] = util.decode_html(mnext.group('url'))
			result.append(item)
		return result

	def decr_url(self,url):
		if url.startswith('#'):
			ret = json.loads(util.request(url[1:]))
			if 'result' in ret:
				url = b64decode(ret['result'])
				url = self._url(url)
		return url

	def resolve(self,item,captcha_cb=None):
		item = item.copy()
		url = item['url']
		if url.startswith('http://www.ulozto.sk'):
			url = self.base_url + url[20:]
		url = self.decr_url(url)
		url = self._url(url)
		if url.startswith('#'):
			util.error('[uloz.to] - url was not correctly decoded')
			return
		self.init_urllib()
		self.login()
		self.info('Resolving %s'% url)
		if 'vip' not in item:
			item['vip'] = False
		vip = item['vip']
		if vip:
			page = util.request(url)
		else:
			try:
				request = Request(url)
				response = urlopen(request)
				page = response.read().decode('utf-8')
				response.close()
			except HTTPError as e:
				traceback.print_exc()
				return
		if page.find('Stránka nenalezena!') > 0:
			self.error('page with movie was not found on server')
			return

		if vip:
			data = util.substr(page,'<h3>Neomezené stahování</h3>','</div')
			m = re.search('<a(.+?)href=\"(?P<url>[^\"#]+)\"',data,re.IGNORECASE | re.DOTALL)
			if m:
				try:
					self.rh.throw = True
					resp = urlopen(Request(self._url(m.group('url'))))
				except RedirectionException:
					# this is what we need, our redirect handler raises this
					pass
				except HTTPError:
					# this is not OK, something went wrong
					traceback.print_exc()
					self.error('Cannot resolve stream url, server did not redirected us')
					self.info('POST url:'+post_url)
					return
				stream = self.rh.location
				item['url'] = self._fix_stream_url(stream)
				item['surl'] = url
				return item

		else:
			m = re.search('<form action="(?P<action>[^"]+)[^>]+class="jsFreeDownloadForm"', page)
			if m:
				self.rh.throw = True
				stream_url = self._get_file_url_anonymous(page,self._url(m.group('action')),response.headers,captcha_cb)
				if stream_url:
					item['url'] = stream_url
					item['surl'] = url
					return item

	def _get_file_url_anonymous(self,page,post_url,headers,captcha_cb):

		data = util.request(self._url('reloadXapca.php'))
		capdata = json.loads(data)
		captcha = capdata['image']
		if not captcha.startswith('http'):
			captcha = 'http:' + captcha
		sound = capdata['sound']
		if not sound.startswith('http'):
			sound = 'http:' + sound
		# ask callback to provide captcha code
		self.info('Asking for captcha img %s' % captcha)
		code = captcha_cb({'id':captcha,'img': captcha,'snd':sound})
		if not code:
			self.info('Captcha not provided, done')
			return

		ts = re.search('<input type=\"hidden\" name=\"ts\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
		cid = re.search('<input type=\"hidden\" name=\"cid\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
		sign = re.search('<input type=\"hidden\" name=\"sign\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
		sign_a = re.search('<input type=\"hidden\" name=\"sign_a\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
		has = capdata['hash']
		salt = capdata['salt']
		timestamp = capdata['timestamp']
		token = re.search('<input type=\"hidden\" name=\"_token_\".+?value=\"([^\"]+)"',page,re.IGNORECASE | re.DOTALL)
		if not (sign and ts and cid and has and token):
			util.error('[uloz.to] - unable to parse required params from page, plugin needs fix')
			return
		request = {
			'captcha_type':'xapca',
			'hash':has,
			'salt':salt,
			'timestamp':timestamp,
			'ts':ts.group(1),
			'cid':'',
			'sign':sign.group(1),
			'sign_a':sign_a.group(1),
			'captcha_value':code,
			'_do':'download-freeDownloadTab-freeDownloadForm-submit',
			'_token_':token.group(1),
			'adi':'f'
		}
		req = Request(post_url,urlencode(request))
		req.add_header('User-Agent',util.UA)
		req.add_header('Referer',post_url)
		req.add_header('Accept','application/json')
		req.add_header('X-Requested-With','XMLHttpRequest')
		sessid=[]
		for cookie in re.finditer('(ULOSESSID=[^\;]+)',headers.get('Set-Cookie'),re.IGNORECASE | re.DOTALL):
			sessid.append(cookie.group(1))
		req.add_header('Cookie','nomobile=1; uloztoid='+cid.group(1)+'; uloztoid2='+cid.group(1)+'; '+sessid[-1])
		util.info(req.headers)
		util.info(request)
		try:
			resp = urlopen(req)
			page = resp.read()
			headers = resp.headers
		except HTTPError:
			# this is not OK, something went wrong
			traceback.print_exc()
			util.error('[uloz.to] cannot resolve stream url, server did not redirected us')
			util.info('[uloz.to] POST url:'+post_url)
			return
		try:
			result = json.loads(page)
		except:
			raise ResolveException('Unexpected error, addon needs fix')
		if not 'status' in list(result.keys()):
			raise ResolveException('Unexpected error, addon needs fix')
		if result['status'] == 'ok':
			return self._fix_stream_url(result['url'])
		elif result['status'] == 'error':
			# the only known state is wrong captcha for now
			util.error('Captcha validation failed, please try playing/downloading again')
			util.error(result)
			raise ResolveException('Captcha failed, try again')


	def _fix_stream_url(self,stream):	
		index = stream.rfind('/')
		if index > 0:
			fn = stream[index:]
			index2 = fn.find('?')
			if index2 > 0:
				fn = quote(fn[:index2])+fn[index2:]
			else:
				fn = quote(fn)
			stream = stream[:index]+fn
		return stream



def _regex(url):
	return re.search('(#(.*)|ulozto\.cz|uloz\.to)',url,re.IGNORECASE | re.DOTALL)

class UloztoHTTPRedirectHandler(HTTPRedirectHandler):

	def http_error_302(self, req, fp, code, msg, headers):
		if self.throw:
			self.location = headers.getheader('Location')
			raise RedirectionException()
		else:
			return HTTPRedirectHandler.http_error_302(self,req,fp,code,msg,headers)

class RedirectionException(Exception):
	pass

