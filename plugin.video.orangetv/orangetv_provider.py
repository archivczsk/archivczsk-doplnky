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

import re,sys,os,time,requests,traceback
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import threading
from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from orangetv import OrangeTV
from lameDB import lameDB
import util
from provider import ContentProvider

try:
	from urllib import quote
	is_py3 = False
except:
	from urllib.parse import quote
	is_py3 = True


__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.orangetv')

proxy_url = "http://127.0.0.1:18081"
PROXY_VER='1'


def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output


# bouquet generator funcions based on AntikTV addon

def download_picons( picons ):
	if not os.path.exists( '/usr/share/enigma2/picon' ):
		os.mkdir('/usr/share/enigma2/picon')
		
	for ref in picons:
		if not picons[ref].endswith('.png'):
			continue
		
		fileout = '/usr/share/enigma2/picon/' + ref + '.png'
		
		if not os.path.exists(fileout):
			try:
				r = requests.get( picons[ref].replace('https://', 'http://').replace('64x64','220x220'), timeout=3 )
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


def generate_bouquet(channels, enable_adult=True):
	# if epg generator is disabled, then try to create service references based on lamedb
	if __addon__.getSetting('enable_xmlepg').lower() == 'true':
		lamedb = None
	else:
		lamedb = lameDB("/etc/enigma2/lamedb")
	
	player_name = __addon__.getSetting('player_name')
	
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
	picons_enabled = __addon__.getSetting('enable_picons').lower() == 'true'
	
	with open( "/etc/enigma2/" + file_name, "w" ) as f:
		f.write( "#NAME Orange TV\n")
		
		for channel in channels:
			if not enable_adult and channel.adult:
				continue
			
			channel_name = _to_string( channel.name )
			url = proxy_url + '/playlive/' + _to_string(channel.channel_key)
			url = quote( url )
			
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
	src_file = os.path.dirname(__file__) + '/orangetv_proxy.sh'
	
	for i in range(3):
		try:
			response = requests.get( proxy_url + '/info', timeout=2 )
			
			if response.text.startswith("orangetv_proxy"):
				if response.text == "orangetv_proxy" + PROXY_VER:
					# current running version match
					return True
				else:
					os.chmod( src_file, 0o755 )
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


day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class orangetvContentProvider(ContentProvider):
	orangetv = None
	orangetv_init_params = None

	
	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'orangetv', '/', username, password, filter, tmp_dir)
		
		self.username = username
		self.password = password
		self.device_id = device_id
		self.session = session
		
		if orangetvContentProvider.orangetv and orangetvContentProvider.orangetv_init_params == (username, password, device_id):
			self.info("OrangeTV already loaded")
		else:
			orangetvContentProvider.orangetv = OrangeTV(username, password, device_id, data_dir, self.info )
			orangetvContentProvider.orangetv_init_params = (username, password, device_id)
			orangetvContentProvider.orangetv.loadEpgCache()
			self.info("New instance of OrangeTV initialised")
		
		self.orangetv = orangetvContentProvider.orangetv

	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	def categories(self):
		result = []
		item = self.dir_item("TV Stanice", "#tv" )
		item['plot'] = "Prvýkrát sa vďaka kešovania EPG načíta dlhšiu dobu, potom bude už načítať rýchlejšie podľa času v Nastavenie, ktorý si môžete zmeniť (defaultne 24 hodín)."
		result.append(item)
		
		item = self.dir_item("Archív", "#archive" )
		item['plot'] = "Tu nájdete spätné prehrávanie vašich kanálov, pokiaľ máte zaplatenú službu archívu."
		result.append(item)
		
		if __addon__.getSetting('enable_extra') == "true":
			item = self.dir_item("Špeciálna sekcia", "#extra" )
			item['plot'] = "Špeciálna sekcia pre pokročilejších používateľov"
			result.append( item )

		return result

	def list(self, url):
		self.info('List URL: "%s"' % url)
		
		if url == '#tv':
			return self.show_tv()
		elif url == '#archive':
			return self.show_archive()
		elif url == '#extra':
			return self.show_extra_menu()
		elif url.startswith( '#archive_channel#' ):
			return self.show_archive_channel(url[17:])
		elif url.startswith( '#archive_day#' ):
			return self.show_archive_day(url[13:])
		elif url.startswith( '#extra#' ):
			return self.show_extra_menu(url[6:])

		return []
	
	def show_extra_menu(self, section=None):
		result = []
		
		if section is None:
			item = self.video_item( "#extra#bouquet_tv" )
			item['title'] = "Vygenerovať userbouquet pre živé vysielanie"
			item['plot'] = 'Tímto sa vytvorí userbouquet pre Orange live TV.'
			result.append( item )
	
			item=self.dir_item( 'Zaregistrované zariadenia', '#extra#devices')
			item['plot'] = "Tu si môžete zobraziť a prípadne vymazať/odregistrovať zbytočná zariadenia, aby ste sa mohli znova inde prihlásiť."
			result.append( item )
		elif section == '#devices':
			
			self.orangetv.refresh_configuration(True)
			for pdev in self.orangetv.devices:
				title = _to_string(pdev["deviceName"]) + " - " + datetime.fromtimestamp(int(pdev["lastLoginTimestamp"]/1000)).strftime('%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + _to_string(pdev["deviceId"])
				
				item = self.video_item('#')
				item['title'] = title
				item['plot'] = 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'
				item['menu'] = {'Zmazať zariadenie!': {'list': '#extra#deldev#' + pdev["deviceId"], 'action-type': 'list'}}
				result.append(item)
				
		elif section == '#bouquet_tv':
			msg = generate_bouquet(self.orangetv.live_channels(), __addon__.getSetting('enable_adult').lower() == 'true')
			msg = ""
			if install_orangetv_proxy():
				msg += "\nOrangeTV proxy funguje."
			else:
				msg += "\nZlyhalo spustenie OrangeTV proxy servera"
			return msg
		elif section.startswith('#deldev#'):
			dev_name = section[8:]
			self.orangetv.device_remove(dev_name)

			item = self.video_item('#')
			item['title'] = "[COLOR red]Zariadenie %s bolo vymazané![/COLOR]" % dev_name
			result.append(item)

		return result

	def show_tv(self):
		channels = self.orangetv.live_channels()
		show_epg = __addon__.getSetting('showliveepg').lower() == 'true'
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'
		cache_hours = int(__addon__.getSetting('epgcache'))
		enable_xmlepg = __addon__.getSetting('enable_xmlepg').lower() == 'true'
		
		if show_epg:
			# reload EPG cache if needed
			ret = self.orangetv.loadEpgCache()
			
			# ret == True -> there already exist cache file 
			if ret and enable_xmlepg:
				# if there exists already cache file and xmlepg is enabled, then cache file
				# is managed by orangetv_proxy, so disable epg refresh here
				cache_hours = 0
		
		result = []
		for channel in channels:
			if not enable_adult and channel.adult:
				continue

			item = self.video_item( channel.channel_key+"|||" )
			item['img'] = channel.logo_url
			
			if show_epg:
				epg = self.orangetv.getChannelCurrentEpg(channel.channel_key, cache_hours )
			else:
				epg = None
				
			if epg:
				item['title'] = _to_string(channel.name)+' [COLOR yellow]'+epg["title"]+'[/COLOR]'
				item['plot'] = epg['desc']
			else:
				item['title'] = _to_string(channel.name)
			
			result.append(item)
			
		self.orangetv.saveEpgCache()
		return(result)

	def show_archive(self):
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'
		channels = self.orangetv.live_channels()
		
		result = []
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
					
				item = self.dir_item( _to_string(channel.name)+" [COLOR green]["+str(tsd)+dtext+"][/COLOR]", '#archive_channel#' + channel.channel_key+'|'+str(tsd) )
				item['img'] = channel.logo_url
				result.append(item)

		return result
	
	def show_archive_channel(self, url):
		cid,days = url.split("|")
	#	addDir('Budoucí (nastavení nahrávek)', get_url(action='future_days', cid=cid), 1, None)
	
		result = []
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
				
			item = self.dir_item( den, '#archive_day#' + cid+'|'+day.strftime("%s") )
			result.append(item)
		
		return result

	def show_archive_day(self, url):
		cid,day = url.split("|")
		
		result = []
		for ch in self.orangetv.getArchivChannelPrograms(cid,day):
			item = self.video_item( ch['url'] )
			item['title'] = ch['title']
			item['img'] = ch['image']
			item['plot'] = ch['plot']
			result.append(item)
		
		return result


	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		self.info("RESOLVE: %s" % item )
		url = item["url"]

		if url == '#':
			return None
		
		if url.startswith('#extra'):
			msg = self.show_extra_menu(url[6:])
			if msg:
				client.add_operation('SHOW_MSG', { 'msg': msg, 'msgType': 'info', 'msgTimeout': 0, 'canClose': True, })
			return None

		for one in self.orangetv.getVideoLink( url ):
			item = item.copy()
			item['url'] = one['url']
			item['quality'] = one['quality']
			result.append(item)
		
		if select_cb:
			return select_cb(result)

		return result
	