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

from orangetv import OrangeTVcache
import util
from provider import ContentProvider

try:
	from urllib import quote
	is_py3 = False
except:
	from urllib.parse import quote
	is_py3 = True


__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.orangetv')

def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output


day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class orangetvContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None
	
	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'orangetv', '/', username, password, filter, tmp_dir)
		
		self.session = session
		self.orangetv = OrangeTVcache.get(username, password, device_id, data_dir, client.log.info )

		ub_enable = __addon__.getSetting('enable_userbouquet') == "true"
		ub_player = __addon__.getSetting('player_name')
		if orangetvContentProvider.enable_userbouquet == None or orangetvContentProvider.userbuquet_player == None:
			orangetvContentProvider.enable_userbouquet = ub_enable
			orangetvContentProvider.userbuquet_player = ub_player
		
		if orangetvContentProvider.enable_userbouquet != ub_enable or orangetvContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			orangetvContentProvider.enable_userbouquet = ub_enable
			orangetvContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( ArchivCZSK.get_addon('plugin.video.orangetv'), 'userbouquet_gen' )

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
		enable_xmlepg = __addon__.getSetting('enable_xmlepg').lower() == 'true' and __addon__.getSetting('enable_userbouquet').lower() == 'true'
		
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
	