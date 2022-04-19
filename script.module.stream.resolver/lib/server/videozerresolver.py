# *		Copyright (C) 2011 Libor Zoubek
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
# thanks to Lynx187 and his fix in https://github.com/t0mm0/xbmc-urlresolver

import re,util,base64

from base64 import b64decode
from binascii import unhexlify
__name__ = 'videozer'
def supports(url):
	return not _regex(url) == None

def _regex(url):
	return	re.search('videozer.com/embed/(?P<id>[_\-\w\d]+)',url,re.IGNORECASE | re.DOTALL)

def resolve(url):
	m = _regex(url)
	if not m == None:
		stream = None
		data = util.request('http://www.videozer.com/player_control/settings.php?v=%s&em=TRUE&fv=v1.1.12' % m.group('id'))
		json = data.replace('false','False').replace('true','True').replace('null','None')
		aData = eval('('+json+')')
		max_res = 99999
		r = re.finditer('"l".*?:.*?"(.+?)".+?"u".*?:.*?"(.+?)"', json)
		chosen_res = 0
		stream_url_part1 = False
		if r:
			for match in r:
				res, url = match.groups()
				if (res == 'LQ' ): res = 240
				elif (res == 'SD') : res = 480
			else: 
				res = 720
				if res > chosen_res and res <= max_res:
					stream_url_part1 = url.decode('base-64')
					chosen_res = res
		else:
			return
		if not stream_url_part1:
			return

	# Decode the link from the json data settings.
		spn_ik = unhexlify(__decrypt(aData["cfg"]["login"]["spen"], aData["cfg"]["login"]["salt"], 950569)).split(';')
		spn = spn_ik[0].split('&')
		ik = spn_ik[1]

		for item in ik.split('&') :
			temp = item.split('=')
			if temp[0] == 'ik' : 
				key = __get_key(temp[1])

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

		return [{'url':sMediaLink}]

def __decrypt(str, k1, k2, p4 = 11, p5 = 77213, p6 = 81371, p7 = 17, p8 = 92717, p9 = 192811):
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
	if x < 0:
		return '-' + bin(-x)
	out = []
	if x == 0: out.append('0')
	while x > 0:
		out.append('01'[x & 1])
		x >>= 1
		pass
	try:
		return '0b' + ''.join(reversed(out))
	except NameError as ne2:
		out.reverse()
	return '0b' + ''.join(out)

def __get_key(nbr):
	if nbr == '1': return 215678
	elif nbr == '2': return 516929
	elif nbr == '3': return 962043
	elif nbr == '4': return 461752
	elif nbr == '5': return 141994
	else: return False
