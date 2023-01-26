# -*- coding: utf-8 -*-
#------------------------------------------------------------
# pelisalacarta - XBMC Plugin
# Megavideo server connector
# http://blog.tvalacarta.info/plugin-xbmc/pelisalacarta/
#------------------------------------------------------------
# Python Video Decryption and resolving routines.
# Courtesy of Voinage, Coolblaze.
#------------------------------------------------------------
# Modify: 2011-10-09, by Ivo Brhel
#------------------------------------------------------------

import os
import re
try:
	import cookielib
	from urllib2 import urlopen, HTTPError, URLError
	from urllib2 import Request as Request
	from urlparse import urlsplit, urlparse, parse_qsl
	from urllib import quote, unquote_plus, urlencode
except:
	from urllib.request import urlopen
	from urllib.request import Request as Request
	from urllib.parse import urlsplit, urlparse, quote, unquote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError, URLError
	import http.cookiejar as cookielib


DEBUG = False

_UserAgent_ =  'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.14) Gecko/20080404 Firefox/2.0.0.14'



def getcode(mega):
	if mega.startswith('http://www.megavideo.com/?v='):
		mega = mega[-8:]
	if mega.startswith('http://wwwstatic.megavideo.com'):
		mega = re.compile('.*v=(.+?)$').findall(mega)
		mega = mega[0]
	if mega.startswith('http://www.megavideo.com/v/'):
		mega = re.compile('.*/v/(.+?)$').findall(mega)
		mega = mega[0][0:8]
	return mega
	
def geturl(url):	
	req = Request(url)
	req.add_header('User-Agent', _UserAgent_)
	req.add_header('Referer', 'http://www.megavideo.com/')
	page = urlopen(req);response=page.read();page.close()
	return response

# Returns an array of possible video url's from the page_url, supporting premium user account and password protected video
def getURL( page_url , premium = False , user="" , password="", video_password="" ):
	print("[megavideo.py] getURL( page_url='%s' , user='%s' , password='%s', video_password=%s)" % (page_url , user , "**************************"[0:len(password)] , video_password) )

	video_urls = []

	# If user has premium account, retrieve the cookie_id from the cookie store and passes to the request as parameter "u"
	if premium:
		#megavideo_cookie_id = get_megavideo_cookie_id(user, password)
		megavideo_cookie_id = login(user, password)
		if megavideo_cookie_id == "":
			print("[megavideo.py] No hay cookie de Megavideo válida (error en login o password?)")
			premium = False

	if premium:
		account_type = "(Premium) [megavideo.com]"
	else:
		account_type = "(Free) [megavideo.com]"

	'''
		video_urls.append( [ "SD (Free)"		  , get_sd_video_url(page_url,premium,user,password,video_password) ] )
	else:
		do_login(premium,user,password)
		video_urls.append( [ "SD (Premium)"		  , get_sd_video_url(page_url,premium,user,password,video_password) ] )
		video_urls.append( [ "Original (Premium)" , get_original_video_url(page_url,premium,user,password,video_password) ] )
	'''

	# Extract vídeo code from page URL
	# http://www.megavideo.com/?v=ABCDEFGH -> ABCDEFGH
	#megavideo_video_id = extract_video_id(page_url)
	megavideo_video_id = page_url
	
	if megavideo_video_id=="":
		print("[megavideo.py] Megavideo URL not valid, or video not available")
		return video_urls


	# Base URL for obtaining Megavideo URL
	url = "http://www.megavideo.com/xml/videolink.php?v="+megavideo_video_id

	if premium:
		url = url + "&u="+megavideo_cookie_id

	# If video is password protected, it is sent with the request as parameter "password"
	if video_password!="":
		url = url + "&password="+video_password

	# Perform the request to Megavideo
	print("[megavideo.py] calling Megavideo")
	#data = scrapertools.cache_page( url , headers=[['User-Agent','Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.14) Gecko/20080404 Firefox/2.0.0.14'],['Referer', 'http://www.megavideo.com/']] , )
	data = geturl(url)
	

	# Search for an SD link
	print("[megavideo.py] SD Link")
	try:
		s = re.compile(' s="(.+?)"').findall(data)
		k1 = re.compile(' k1="(.+?)"').findall(data)
		k2 = re.compile(' k2="(.+?)"').findall(data)
		un = re.compile(' un="(.+?)"').findall(data)
		video_url = "http://www" + s[0] + ".megavideo.com/files/" + decrypt(un[0], k1[0], k2[0]) + "/?.flv"
		video_urls.append( ["SD "+account_type , video_url ])
	# Video is not available
	except:
		import sys
		for line in sys.exc_info():
			print( "%s" % line )
		print("[megavideo.py] Megavideo URL not valid, or video not available")		 
		return []

	# Search for an HD link if it exists
	print("[megavideo.py] HD Link")
	hd = re.compile(' hd="(.+?)"').findall(data)
	if len(hd)>0 and hd[0]=="1":
		s = re.compile(' hd_s="(.+?)"').findall(data)
		k1 = re.compile(' hd_k1="(.+?)"').findall(data)
		k2 = re.compile(' hd_k2="(.+?)"').findall(data)
		un = re.compile(' hd_un="(.+?)"').findall(data)
		video_url = "http://www" + s[0] + ".megavideo.com/files/" + decrypt(un[0], k1[0], k2[0]) + "/?.flv"
		video_urls.append( ["HD "+account_type , video_url ])

	# If premium account, search for the original video link
	if premium:
		print("[megavideo.py] ORIGINAL Link")
		url = "http://www.megavideo.com/xml/player_login.php?u="+megavideo_cookie_id+"&v="+megavideo_video_id+"&password="+video_password
		#data2 = scrapertools.cache_page( url , headers=[['User-Agent','Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.14) Gecko/20080404 Firefox/2.0.0.14'],['Referer', 'http://www.megavideo.com/']] , )
		data2 = geturl(url)
		#print data2
	
		patronvideos  = 'downloadurl="([^"]+)"'
		matches = re.compile(patronvideos,re.DOTALL).findall(data2)
		video_url = matches[0].replace("%3A",":").replace("%2F","/").replace("%20"," ")
		video_urls.append( ["ORIGINAL "+video_url[-4:]+" [megavideo]" , video_url ])

	# Truco http://www.protegerurl.com.es/v9v/00Z8VNVZ.flv
	#if not premium:
	#	 print("[megavideo.py] SIN LIMITE Link")
	#	 video_urls.append( ["SIN LIMITE [megavideo]" , "http://www.protegerurl.com.es/v9v/"+megavideo_video_id+".flv" ])

	# Search for error conditions
	errortext = re.compile(' errortext="(.+?)"').findall(data)	
	if len(errortext)>0:
		password_required = re.compile('password_required="(.*?)"').findall(data)
		if len(password_required) > 0:
			# Launches an exception to force the user to input the password
			raise PasswordRequiredException()

	print("[megavideo.py] Ended with %d links" % len(video_urls))

	return video_urls

# Extract vídeo code from page URL
# http://www.megavideo.com/?v=ABCDEFGH -> ABCDEFGH
def extract_video_id( page_url ):
	print("[megavideo.py] extract_video_id(page_url="+page_url+")")
	
	if page_url.startswith('http://www.megavideo.com/?v='):
		patron = 'http://www.megavideo.com.*\?v\=([A-Z0-9a-z]{8})'
		matches = re.compile(patron,re.DOTALL).findall(page_url)
		video_id = matches[0]
	elif page_url.startswith('http://www.megavideo.com/?d='):
		patron = 'http://www.megavideo.com.*\?d\=([A-Z0-9a-z]{8})'
		matches = re.compile(patron,re.DOTALL).findall(page_url)
		video_id = matches[0]
		import megaupload
		video_id = megaupload.convertcode(video_id)
	else:
		video_id = page_url

	print("[megavideo.py] video_id="+video_id)
	return video_id

# Get the Megavideo user ID (cookie) from the user and password credentials
def login(user, password):
	print("[megavideo.py] login(user="+user+", password="+"**************************"[0:len(password)]+")")

	url = "http://www.megavideo.com/?c=login"
	post = "login=1&redir=1&username="+user+"&password="+quote(password)
	headers = [ ['User-Agent','Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3'],['Referer','http://www.megavideo.com/?s=signup'] ]
	#data = scrapertools.cache_page(url=url, post=post)
	
	return get_megavideo_cookie_id()
	
def get_megavideo_cookie_id():
	
	cookie_data = config.get_cookie_data()
	print("cookie_data="+cookie_data)
	
	lines = cookie_data.split("\n")
	for line in lines:
		print("line="+line)
	
		if "megavideo.com" in line:
			print("[megavideo.py] patron1")
			patron = 'user="([^"]+)"'
			matches = re.compile(patron,re.DOTALL).findall(line)
		
			if len(matches)>0:
				cookie = matches[0]
				break
			else:
				print("[megavideo.py] patron2")
				patron = 'user=([^\;]+);'
				matches = re.compile(patron,re.DOTALL).findall(line)
				if len(matches)>0:
					cookie = matches[0]
					break
				else:
					print("[megavideo.py] No se ha encontrado la cookie de Megavideo")
					cookie=""
	
	print("cookie="+cookie)
		
	return cookie
	
# Megavideo decryption routines
def ajoin(arr):
	strtest = ''
	for num in range(len(arr)):
		strtest = strtest + str(arr[num])
	return strtest

def asplit(mystring):
	arr = []
	for num in range(len(mystring)):
		arr.append(mystring[num])
	return arr
		
def decrypt(str1, key1, key2):

	__reg1 = []
	__reg3 = 0
	while (__reg3 < len(str1)):
		__reg0 = str1[__reg3]
		holder = __reg0
		
		# Optimización de aabilio@gmail.com :)
		for i in range(16):

			if i == 0:
				tmp = holder
			else:
				tmp = __reg0

			if tmp == hex(i).split("x")[1]:
				__reg1.append("".join([str((i >> y) & 1) for y in range(3, -1, -1)]))
				break

		__reg3 = __reg3 + 1

	mtstr = ajoin(__reg1)
	__reg1 = asplit(mtstr)
	__reg6 = []
	__reg3 = 0
	while (__reg3 < 384):
	
		key1 = (int(key1) * 11 + 77213) % 81371
		key2 = (int(key2) * 17 + 92717) % 192811
		__reg6.append((int(key1) + int(key2)) % 128)
		__reg3 = __reg3 + 1
	
	__reg3 = 256
	while (__reg3 >= 0):

		__reg5 = __reg6[__reg3]
		__reg4 = __reg3 % 128
		__reg8 = __reg1[__reg5]
		__reg1[__reg5] = __reg1[__reg4]
		__reg1[__reg4] = __reg8
		__reg3 = __reg3 - 1
	
	__reg3 = 0
	while (__reg3 < 128):
	
		__reg1[__reg3] = int(__reg1[__reg3]) ^ int(__reg6[__reg3 + 256]) & 1
		__reg3 = __reg3 + 1

	__reg12 = ajoin(__reg1)
	__reg7 = []
	__reg3 = 0
	while (__reg3 < len(__reg12)):

		__reg9 = __reg12[__reg3:__reg3 + 4]
		__reg7.append(__reg9)
		__reg3 = __reg3 + 4
		
	
	__reg2 = []
	__reg3 = 0
	while (__reg3 < len(__reg7)):
		__reg0 = __reg7[__reg3]
		holder2 = __reg0

		# Optimización de aabilio@gmail.com :)
		for i in range(16):
			if i == 0:
				tmp = holder2
			else:
				tmp = __reg0

			if tmp == "".join([str((i >> y) & 1) for y in range(3, -1, -1)]):
				__reg2.append(hex(i).split("x")[1])
				break

		__reg3 = __reg3 + 1

	endstr = ajoin(__reg2)
	return endstr