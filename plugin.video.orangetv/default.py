# -*- coding: utf-8 -*-
#
# plugin.video.orangetv
# based od o2tvgo by Stepan Ort
#
# (c) Michal Novotny
#
# original at https://www.github.com/misanov/
#
# free for non commercial use with author credits
#

import re,sys,os,string,time,base64,datetime,json,requests
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import threading
from uuid import getnode as get_mac
from datetime import date, timedelta
from Components.config import config
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.engine.client import add_video

from util import addDir, addLink, addSearch, getSearch
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from orangetv import get_orangetv
from lameDB import lameDB

try:
	from urllib import quote_plus, unquote_plus
	is_py3 = False
except:
	from urllib.parse import quote_plus, unquote_plus
	is_py3 = True


addon =	 ArchivCZSK.get_xbmc_addon('plugin.video.orangetv')
profile = addon.getAddonInfo('profile')
home = addon.getAddonInfo('path')
icon =	os.path.join( home, 'icon.png' )
getquality = "1080p"
otvusr = addon.getSetting('orangetvuser')
otvpwd = addon.getSetting('orangetvpwd')
_deviceid = addon.getSetting('deviceid')
_quality = 'MOBILE'

proxy_url = "http://127.0.0.1:18081"
PROXY_VER='1'

def device_id():
	mac = get_mac()
	hexed	= hex((mac * 7919) % (2 ** 64))
	return ('0000000000000000' + hexed[2:-1])[16:]

def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output

def _log(message):
	try:
		f = open(os.path.join(config.plugins.archivCZSK.logPath.getValue(),'orange.log'), 'a')
		dtn = datetime.datetime.now()
		f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " %s\n" % message)
		f.close()
	except:
		pass

orangetv = get_orangetv(_deviceid, otvusr, otvpwd, _quality, profile, _log)

# bouquet generator funcions based on AntikTV addon

def download_picons( picons ):
	if not os.path.exists( '/usr/share/enigma2/picon' ):
		os.mkdir('/usr/share/enigma2/picon')
		
	for ref in picons:
		fileout = '/usr/share/enigma2/picon/' + ref + '.png'
		
		if not os.path.exists(fileout):
			try:
				r = requests.get( picons[ref].replace('https://', 'http://'), timeout=3 )
				if r.status_code == 200:
					with open(fileout, 'wb') as f:
						f.write( r.content )
			except:
				pass

def build_service_ref( service, player_id ):
	return player_id + ":0:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0:".format( service.ServiceType, service.ServiceID, service.Transponder.TransportStreamID, service.Transponder.OriginalNetworkID, service.Transponder.DVBNameSpace )
				
def service_ref_get( lamedb, channel_name, player_id, channel_id ):
	
	skylink_freq = [ 11739, 11778, 11856, 11876, 11934, 11954, 11973, 12012, 12032, 12070, 12090, 12110, 12129, 12168, 12344, 12363 ]
	antik_freq = [ 11055, 11094, 11231, 11283, 11324, 11471, 11554, 11595, 11637, 12605 ]
	
	def cmp_freq( f, f_list ):
		f = int(f/1000)
		
		for f2 in f_list:
			if abs( f - f2) < 5:
				return True
	
		return False

	if lamedb != None:
		try:
			services = lamedb.Services[ lamedb.name_normalise( channel_name ) ]
			
			# try position 23.5E first
			for s in services:
				if s.Transponder.Data.OrbitalPosition == 235 and cmp_freq( s.Transponder.Data.Frequency, skylink_freq ):
					return build_service_ref(s, player_id)
	
			# then 16E
			for s in services:
				if s.Transponder.Data.OrbitalPosition == 160 and cmp_freq( s.Transponder.Data.Frequency, antik_freq ):
					return build_service_ref(s, player_id)
	
			for s in services:
				if s.Transponder.Data.OrbitalPosition == 235:
					return build_service_ref(s, player_id)
	
			# then 16E
			for s in services:
				if s.Transponder.Data.OrbitalPosition == 160:
					return build_service_ref(s, player_id)
	
			# then 0,8W
			for s in services:
				if s.Transponder.Data.OrbitalPosition == -8:
					return build_service_ref(s, player_id)
	
			# then 192
			for s in services:
				if s.Transponder.Data.OrbitalPosition == 192:
					return build_service_ref(s, player_id)
	
			# take the first one
			for s in services:
				return build_service_ref(s, player_id)
	
		except:
			pass
	
	return player_id + ":0:1:%X:0:0:E020000:0:0:0:" % channel_id


def generate_bouquet(enable_adult=True):
	# if epg generator is disabled, then try to create service references based on lamedb
	if addon.getSetting('enable_xmlepg').lower() == 'true':
		lamedb = None
	else:
		lamedb = lameDB("/etc/enigma2/lamedb")
	
	player_name = addon.getSetting('player_name')
	
	if player_name == "1": # gstplayer
		player_id = "5001"
	elif player_name == "2": # exteplayer3
		player_id = "5002"
	elif player_name == "3": # DMM
		player_id = "8193"
	elif player_name == "4": # DVB service (OE >=2.5)
		player_id = "1"
	else:
		player_id = "4097" # system default

	file_name = "userbouquet.orangetv.tv"
	
	picons = {}
	picons_enabled = addon.getSetting('enable_picons').lower() == 'true'
	
	channels = orangetv.live_channels()
	
	with open( "/etc/enigma2/" + file_name, "w" ) as f:
		f.write( "#NAME Orange TV\n")
		
		for channel in channels:
			if not enable_adult and channel.adult:
				continue
			
			channel_name = _to_string( channel.name )
			url = proxy_url + '/playlive/' + _to_string(channel.channel_key)
			url = quote_plus( url )
			
			service_ref = service_ref_get( lamedb, channel_name, player_id, channel.id )
				
			f.write( "#SERVICE " + service_ref + url + ":" + channel_name + "\n")
			f.write( "#DESCRIPTION " + channel_name + "\n")
			
			try:
				if picons_enabled and service_ref.endswith(':E020000:0:0:0:'):
					picons[ service_ref[:-1].replace(':', '_') ] = channel.picon
			except:
				pass
	
	first_export = True
	with open( "/etc/enigma2/bouquets.tv", "r" ) as f:
		for line in f.readlines():
			if file_name in line:
				first_export = False
				break
	
	if first_export:
		with open( "/etc/enigma2/bouquets.tv", "a" ) as f:
			f.write( '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + file_name + '" ORDER BY bouquet' + "\n" )

	try:
		requests.get("http://127.0.0.1/web/servicelistreload?mode=2")
	except:
		pass
	
	if picons_enabled:
		threading.Thread(target=download_picons,args=(picons,)).start()
	
	
	return "OrangeTV userbouquet vygenerovaný"

def install_orangetv_proxy():
	for i in range(3):
		try:
			response = requests.get( proxy_url + '/info', timeout=2 )
			
			if response.text.startswith("orangetv_proxy"):
				if response.text == "orangetv_proxy" + PROXY_VER:
					# current running version match
					return True
				else:
					# wrong runnig version - restart it and try again
					os.system('/etc/init.d/orangetv_proxy.sh stop')
					time.sleep(2)
					os.system('/etc/init.d/orangetv_proxy.sh start')
					time.sleep(2)
			else:
				# incorrect response - install new orangetv proxy
				break
		except:
			# something's wrong - we will try again
			pass
	
	src_file = os.path.dirname(__file__) + '/orangetv_proxy.sh'
	os.chmod( src_file, 0o755 )
	try:
		os.symlink( src_file, '/etc/init.d/orangetv_proxy.sh' )
	except:
		pass
	
	try:
		os.system('update-rc.d orangetv_proxy.sh defaults')
		os.system('/etc/init.d/orangetv_proxy.sh start')
		time.sleep(1)
	except:
		pass

	for i in range(5):
		try:
			response = requests.get( proxy_url + '/info', timeout=1 )
		except:
			response = None
			time.sleep(1)
			pass
		
		if response != None and response.text == "orangetv_proxy" + PROXY_VER:
			return True		
	
	return False


#### MAIN

authent_error = 'AuthenticationError'
toomany_error = 'TooManyDevicesError'
nopurch_error = 'NoPurchasedServiceError'

def OBSAH():
	addDir("Naživo", 'live', 1, None, infoLabels={'plot':"Prvýkrát sa vďaka kešovania EPG načíta dlhšiu dobu, potom bude už načítať rýchlejšie podľa času v Nastavenie, ktorý si môžete zmeniť (defaultne 24 hodín)."})
	addDir("Archív", 'archiv', 2, None, infoLabels={'plot':"Tu nájdete spätné prehrávanie vašich kanálov, pokiaľ máte zaplatenú službu archívu."})
	if addon.getSetting('enable_extra').lower() == 'true':
		addDir("Špeciálna sekcia", 'extra_menu', 10, None, infoLabels={'plot':"Špeciálna sekcia pre pokročilejších používateľov"})
		
def EXTRA_MENU():
	addDir("Vygenerovať userbouquet pre živé vysielanie", 'playlist', 5, None, infoLabels={'plot':"Tímto sa vytvorí userbouquet pre Orange live TV."})
	addDir("Zariadenia", 'devices', 9, None, infoLabels={'plot':"Tu si môžete zobraziť a prípadne vymazať/odregistrovať zbytočná zariadenia, aby ste sa mohli znova inde prihlásiť."})
	
def DEVICES():
	orangetv.refresh_configuration(True)
	for pdev in orangetv.devices:
		title = _to_string(pdev["deviceName"]) + " - " + datetime.datetime.fromtimestamp(int(pdev["lastLoginTimestamp"]/1000)).strftime('%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + _to_string(pdev["deviceId"])
		addDir(title, 'device', 0, None, menuItems={'Zmazať zariadenie!': {'url': 'deldev', 'name': pdev["deviceId"]}}, infoLabels={'plot':"V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!"})

def DEVICEREMOVE(did):
	orangetv.device_remove(did)
	addLink("[COLOR red]Zariadenie vymazané[/COLOR]","#",None,"")

def ARCHIV():
	enable_adult = addon.getSetting('enable_adult').lower() == 'true'
	channels = orangetv.live_channels()
	for channel in channels:
		if not enable_adult and channel.adult:
			continue

		if channel.timeshift > 0:
			tsd = int(channel.timeshift)
			if tsd == 1:
				dtext=" den"
			elif tsd < 5:
				dtext=" dny"
			else:
				dtext=" dní"
			addDir(_to_string(channel.name)+" [COLOR green]["+str(tsd)+dtext+"][/COLOR]",channel.channel_key+'|'+str(tsd),3,channel.logo_url,1)

def ARCHIVDAYS(url):
	cid,days = url.split("|")
#	addDir('Budoucí (nastavení nahrávek)', get_url(action='future_days', cid=cid), 1, None)
	for i in range(int(days)+1):
		day = date.today() - timedelta(days = i)
		if i == 0:
			den = "Dnes"
		elif i == 1:
			den = "Včera"
		else:
			if day.strftime("%A") in day_translation:
				den = day_translation[day.strftime("%A")] + " " + day.strftime("%d.%m.%Y")
			else:
				den = day.strftime("%A") + " " + day.strftime("%d.%m.%Y")
			
			if not is_py3:
				den = den.decode("utf-8")
			
		addDir(den, cid+'|'+day.strftime("%s"), 4, None, 1)

def ARCHIVVIDEOS(url):
	cid,day = url.split("|")
	for ch in orangetv.getArchivChannelPrograms(cid,day):
		addDir( ch['title'], ch['url'], 8, ch['image'], 1, infoLabels={'plot':ch['plot'] } )

def LIVE():
	channels = orangetv.live_channels()
	show_epg = addon.getSetting('showliveepg').lower() == 'true'
	enable_adult = addon.getSetting('enable_adult').lower() == 'true'
	
	for channel in channels:
		if not enable_adult and channel.adult:
			continue
		
		if show_epg:
			epg=orangetv.getChannelPrograms(channel.channel_key, int(addon.getSetting('epgcache')) * 24 )
			addDir(_to_string(channel.name)+' [COLOR yellow]'+epg["title"]+'[/COLOR]',channel.channel_key+"|||",8,channel.logo_url,1, infoLabels={'plot':epg["desc"]})
		else:
			addDir(_to_string(channel.name),channel.channel_key+"|||",8,channel.logo_url,1)

	orangetv.saveEpgCache()

def PLAYLIST():
	msg = generate_bouquet(addon.getSetting('enable_adult').lower() == 'true')
	if install_orangetv_proxy():
		msg += "\nOrangeTV proxy funguje."
	else:
		msg += "\nZlyhalo spustenie OrangeTV proxy servera"
		
	client.showInfo( msg )


def VIDEOLINK(name, url):
	for one in orangetv.getVideoLink( name, url ):
		add_video(one["title"], one["url"])


name=None
url=None
mode=None
thumb=None
page=None
desc=None

# _log(str(params))

try:
		url=unquote_plus(params["url"])
except:
		pass
try:
		name=unquote_plus(params["name"])
except:
		pass
try:
		mode=int(params["mode"])
except:
		pass
try:
		page=int(params["page"])
except:
		pass
try:
		thumb=unquote_plus(params["thumb"])
except:
		pass

if _deviceid == "":
	_deviceid = device_id()
	if _deviceid == "":
		_deviceid = 'Nexus7'
	addon.setSetting('deviceid',_deviceid)

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}

if otvusr == "" or otvpwd == "":
	client.add_operation("SHOW_MSG", {'msg': 'Prosim, vlozte nejdrive prihlasovaci udaje', 'msgType': 'error', 'msgTimeout': 30, 'canClose': True})
elif url=='deldev' and name!='':
	DEVICEREMOVE(name)
elif mode==None or url==None or len(url)<1:
	OBSAH()
elif mode==1:
	LIVE()
elif mode==2:
	ARCHIV()
elif mode==3:
	ARCHIVDAYS(url)
elif mode==4:
	ARCHIVVIDEOS(url)
elif mode==5:
	PLAYLIST()
elif mode==9:
	DEVICES()
elif mode==8:
	VIDEOLINK(name, url)
elif mode==10:
	EXTRA_MENU()

if len(client.GItem_lst[0]) == 0:
	addDir('','',1,None)
