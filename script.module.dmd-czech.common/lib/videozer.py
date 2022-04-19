# -*- coding: utf-8 -*-
#------------------------------------------------------------
# 
# https://github.com/Lynx187
#
#------------------------------------------------------------

import re
import os
from binascii import unhexlify
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


_VALID_URL = r'^((?:http://)?(?:\w+\.)?videozer\.com/(?:(?:e/|embed/|video/)|(?:(?:flash/|f/)))?)?([0-9A-Za-z_-]+)(?(1).+)?$'
_UserAgent_ =  'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; .NET CLR 3.0.04506)'

def getURL(url):
	
	code = Extract_id(url)

	curi = "http://www.videozer.com/player_control/settings.php?v=%s&em=TRUE&fv=v1.1.12" %code
	
	req = Request(curi)
	req.add_header('User-Agent', _UserAgent_)
	response = urlopen(req)
	datajson=response.read()
	response.close()
		
	datajson = datajson.replace("false","False").replace("true","True")
	datajson = datajson.replace("null","None")
	aData = eval("("+datajson+")")

	max_res = 99999
	r = re.finditer('"l".*?:.*?"(.+?)".+?"u".*?:.*?"(.+?)"', datajson)
	chosen_res = 0
	stream_url = False
	
	if r:
		for match in r:
			res, url = match.groups()
			if (res == 'LQ' ): res = 240
			elif (res == 'SD') : res = 480
			else : res = 720
			if res > chosen_res and res <= max_res:
				stream_url_part1 = url.decode('base-64')
				chosen_res = res
	else:
		print( "videozer: stream url part1 not found" )
		return False	
	

	# Decode the link from the json data settings.
	spn_ik = unhexlify(__decrypt(aData["cfg"]["login"]["spen"], aData["cfg"]["login"]["salt"], 950569)).split(';')
	spn = spn_ik[0].split('&')
	ik = spn_ik[1]

	for item in ik.split('&') :
		temp = item.split('=')
		if temp[0] == 'ik' : 
			key = __getKey(temp[1])

	sLink = ""
	for item in spn :
		item = item.split('=')
		if(int(item[1])==1):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["info"]["sece2"], aData["cfg"]["environment"]["rkts"], key) + '&'	 #decrypt32byte
		elif(int(item[1]==2)):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["ads"]["g_ads"]["url"],aData["cfg"]["environment"]["rkts"], key) + '&'	
		elif(int(item[1])==3):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["ads"]["g_ads"]["type"],aData["cfg"]["environment"]["rkts"], key,26,25431,56989,93,32589,784152) + '&'	
		elif(int(item[1])==4):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["ads"]["g_ads"]["time"],aData["cfg"]["environment"]["rkts"], key,82,84669,48779,32,65598,115498) + '&'
		elif(int(item[1])==5):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["login"]["euno"],aData["cfg"]["login"]["pepper"], key,10,12254,95369,39,21544,545555) + '&'
		elif(int(item[1])==6):
			sLink = sLink + item[0]+ '=' + __decrypt(aData["cfg"]["login"]["sugar"],aData["cfg"]["ads"]["lightbox2"]["time"], key,22,66595,17447,52,66852,400595) + '&'			
	
	sLink = sLink + "start=0"
	
	sMediaLink = stream_url_part1 + '&' + sLink

	return sMediaLink


def Extract_id(url):
	# Extract video id from URL
	mobj = re.match(_VALID_URL, url)
	if mobj is None:
		print( 'ERROR: invalid URL: %s' % url )
		
		return ""
	id = mobj.group(2)
	return id


def __decrypt( str, k1, k2, p4 = 11, p5 = 77213, p6 = 81371, p7 = 17, p8 = 92717, p9 = 192811):
	tobin = hex2bin(str,len(str)*4)
	tobin_lenght = len(tobin)
	keys = []
	index = 0
	
	while (index < tobin_lenght*3):
		k1 = ((int(k1) * p4) + p5) % p6
		k2 = ((int(k2) * p7) + p8) % p9
		keys.append((int(k1) + int(k2)) % tobin_lenght)
		index += 1

	index = tobin_lenght*2

	while (index >= 0):
		val1 = keys[index]
		mod	 = index%tobin_lenght
		val2 = tobin[val1]
		tobin[val1] = tobin[mod]
		tobin[mod] = val2
		index -= 1

	index = 0
	while(index < tobin_lenght):
		tobin[index] = int(tobin[index]) ^ int(keys[index+(tobin_lenght*2)]) & 1
		index += 1
		decrypted = bin2hex(tobin)
	return decrypted
	
def hex2bin(val,fill):
	bin_array = []
	string =  bin(int(val, 16))[2:].zfill(fill)
	for value in string:
		bin_array.append(value)
	return bin_array

def bin2hex(val):
	string = str("")
	for char in val:
		string+=str(char)
	return "%x" % int(string, 2)
		
def bin( x):
	'''
	bin(number) -> string

	Stringifies an int or long in base 2.
	'''
	if x < 0: return '-' + bin(-x)
	out = []
	if x == 0: out.append('0')
	while x > 0:
		out.append('01'[x & 1])
		x >>= 1
		pass
	try: return '0b' + ''.join(reversed(out))
	except NameError as ne2: out.reverse()
	return '0b' + ''.join(out)
		
def __getKey( nbr):
	if nbr == '1': return 215678
	elif nbr == '2': return 516929
	elif nbr == '3': return 962043
	elif nbr == '4': return 461752
	elif nbr == '5': return 141994
	else: return False