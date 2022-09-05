# -*- coding: utf-8 -*-

import re,sys,os,time,requests,traceback,random
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import threading, json
from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from sledovanitv import SledovaniTvCache
import util
from provider import ContentProvider

try:
	from urllib import quote
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

	is_py3 = False
except:
	from urllib.parse import quote
	
	def py2_encode_utf8( text ):
		return text
	
	def py2_decode_utf8( text ):
		return text
	
	is_py3 = True


addon = ArchivCZSK.get_xbmc_addon('plugin.video.sledovanitv')

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class SledovaniTVContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None

	# #################################################################################################
	
	def __init__(self, username=None, password=None, pin=None, serialid=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'sledovani.tv', '/', username, password, filter, tmp_dir)
		
		self.session = session
		self.data_dir = data_dir

		if not username or not password or not serialid:
			self.error("No login data provided")
			self.sledovanitv = None
		else:
			self.sledovanitv = SledovaniTvCache.get(username, password, pin, serialid, data_dir, client.log.info )
			
		ub_enable = addon.getSetting('enable_userbouquet') == "true"
		ub_player = addon.getSetting('player_name')
		if SledovaniTVContentProvider.enable_userbouquet == None or SledovaniTVContentProvider.userbuquet_player == None:
			SledovaniTVContentProvider.enable_userbouquet = ub_enable
			SledovaniTVContentProvider.userbuquet_player = ub_player
		
		if SledovaniTVContentProvider.enable_userbouquet != ub_enable or SledovaniTVContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			SledovaniTVContentProvider.enable_userbouquet = ub_enable
			SledovaniTVContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( ArchivCZSK.get_addon('plugin.video.sledovanitv'), 'userbouquet_gen' )

	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', 'search', '!download']

	# #################################################################################################

	def categories(self):
		if not self.sledovanitv:
			item = self.video_item('#')
			item['title'] = "Nejsou nastaveny přihlašovací údaje"
			return [ item ]
		
		result = []
		item = self.dir_item("Úvodní stránka", '#home_page' )
		item['plot'] = "Vaše úvodní stránka"
		result.append(item)
		
		item = self.dir_item("Živě", "#channels" )
		item['plot'] = "Tady najdete živé vysílání televizních programů "
		result.append(item)
		
		item = self.dir_item("Rádia", "#radios")
		item['plot'] = "Tady najdete živé vysílání radiových programů"
		result.append(item)

		item = self.dir_item("Archiv", "#archive")
		item['plot'] = "Tady najdete zpětné vysílaní vašich programů"
		result.append(item)

		item = self.dir_item("Nahrávky","#recordings" )
		item['plot'] = "Tady nájdete vaše nahrávky"
		result.append(item)

		if addon.getSetting('enable_extra') == "true":
			item = self.dir_item("Speciálni sekce", "#extra" )
			item['plot'] = "Speciálni sekce pro pokročilé uživatele"
			result.append( item )

		return result
	
	# #################################################################################################
	
	def list(self, url):
		try:
			if url == '#home_page':
				return self.show_home()
			if url == '#channels':
				return self.show_channels()
			if url == '#radios':
				return self.show_channels('radio')
			elif url == '#archive':
				return self.show_archive()
			elif url == '#recordings':
				return self.show_recordings()
			elif url == '#future_recordings':
				return self.show_recordings(False)
			elif url == '#extra':
				return self.show_extra_menu()
			elif url.startswith( '#archive_days#' ):
				return self.show_archive_days(url[14:])
			elif url.startswith( '#future_days#' ):
				return self.show_future_days(url[13:])
			
			elif url.startswith( '#channel#' ):
				return self.show_channel(url[9:])
			elif url.startswith( '#future_program#' ):
				return self.show_future_program(url[16:])
			elif url.startswith( '#archive_program#' ):
				return self.show_archive_program(url[17:])
			elif url.startswith( '#add_recording#' ):
				return self.add_recording(url[15:])
			elif url.startswith( '#del_recording#' ):
				return self.delete_recording(url[15:])
	
			elif url.startswith( '#extra#' ):
				return self.show_extra_menu(url[6:])

		except Exception as e:
			client.log.error("Sledovani.tv Addon ERROR:\n%s" % traceback.format_exc())
			
			if "SLEDOVANI.TV" in str(e):
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				item = self.video_item('#')
				item['title'] = "Chyba"
				return [ item ]
			else:
				raise
			
		return []
	
	# #################################################################################################
	
	def show_extra_menu(self, section=None):
		result = []
		
		if section is None:
			item=self.dir_item( 'Zaregistrované zařízení', '#extra#devices')
			item['plot'] = "Tu si můžete zobrazit a případně vymazat/odregistrovat zbytečná zařízení, aby ste se mohli znova jinde přihlásit."
			result.append( item )
		elif section == '#devices':
			
			for pdev in self.sledovanitv.get_devices():
				title = 'ID: %d, %s: %s' % (pdev['deviceId'], pdev["typeName"], pdev['title']) 
				
				if pdev.get('self', False):
					title = '[COLOR yellow]' + title + '[/COLOR]'
				
				item = self.video_item('#')
				item['title'] = py2_encode_utf8(title)
				item['plot'] = 'V menu můžete zařízení vymazat pomocí Smazat zařízení!'
				item['menu'] = {'Smazat zařízení!': {'list': '#extra#deldev#' + str(pdev["deviceId"]), 'action-type': 'list'}}
				result.append(item)
				
		elif section.startswith('#deldev#'):
			dev_name = section[8:]
			self.sledovanitv.device_remove(dev_name)

			item = self.video_item('#')
#			item['title'] = "[COLOR red]Zařízení %s bylo vymazáno![/COLOR]" % dev_name
			item['title'] = "[COLOR red]Operace zatím není podporováná![/COLOR]"
			result.append(item)

		return result

	# #################################################################################################
	
	def search( self, query ):
		result = []
		
		if self.sledovanitv:
			events = self.sledovanitv.search(query)
		else:
			events = []
		
		for event in events:
			if event['availability'] != "timeshift":
				continue
				
			title = event["startTime"][8:10] + "." + event["startTime"][5:7] + ". " + event["startTime"][11:16] + "-" + event["endTime"][11:16] + " [" + event["channel"].upper() + "] " + event["title"]
			eventid = str(event['eventId'])

			item = self.video_item('#play_event#' + eventid )
			item['title'] = py2_encode_utf8( title )
			item['plot'] = event.get("description", '')
			item['img'] = event.get("poster")
			item['year'] = event.get("year")
			item['menu'] = { 'Nahrát pořad': { 'list': "#add_recording#" + eventid } }
			result.append(item)
		
		return result
	
	# #################################################################################################
	
	def show_home(self):
		channels = self.sledovanitv.get_home()

		result = []
		for channel in channels:
			item = self.video_item( '#play_event#' + channel['eventid'] )
			
			item['title'] = channel['title']
			item['img'] = channel.get('thumb')
			item['plot'] = channel.get('plot')
			item['duration'] = channel.get('duration')
			start_time = channel.get('start_time')

			if start_time and start_time > int(time.time()):
				item['title'] = '[COLOR grey]' + item['title'] + '[/COLOR]'
				item['url'] = '#'
			
			result.append(item)
		
		return result
		

	# #################################################################################################
	
	def show_channels(self, channel_type='tv'):
		channels = self.sledovanitv.get_channels_sorted(channel_type)
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'

		epg = self.sledovanitv.get_epg()
		
		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			epgdata = epg.get(channel['id'])
			item = self.video_item( '#play_' + channel_type + '#' + channel['id'] )
			
			if epgdata:
				epgdata = epgdata[0]
				
				epg_title = " (" + epgdata["title"] + " - " + epgdata["startTime"][-5:] + "-" + epgdata["endTime"][-5:] + ")"
				item['plot'] = epgdata.get('description')
				item['img'] = epgdata.get('poster')
				item['duration'] = epgdata.get('duration')*60
				item['year'] = epgdata.get('year')
				
				if channel['adult']:
					item['title'] = '[COLOR red]' + channel["name"] + epg_title + '[/COLOR]'
				else:
					item['title'] = channel["name"] + '[COLOR yellow]' + epg_title + '[/COLOR]'
			else:
				item['title'] = channel['name']
			
			result.append(item)
		
		return result

	# #################################################################################################
	
	def show_archive(self):
		channels = self.sledovanitv.get_channels_sorted('tv')
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'

		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			if channel["timeshift"] == 0:
				continue
			
			tsd = int(channel["timeshift"]/3600/24)
			if tsd == 1:
				dtext=" den"
			elif tsd < 5:
				dtext=" dny"
			else:
				dtext=" dní"

			item = self.dir_item( channel['name'] + " [COLOR green][" + str(tsd) + dtext + "][/COLOR]", '#archive_days#' + channel['id'] )
			result.append(item)
			
		return result


	# #################################################################################################
	
	def show_archive_days(self, channel_id):
		result = []
		channel = self.sledovanitv.get_channels().get( channel_id )
		
		if not channel:
			return []

		item = self.dir_item( 'Budoucí (nastavení nahrávek)', '#future_days#' + channel_id )
		result.append(item)

		for i in range(int(channel['timeshift'] / 3600 / 24)):
			day = date.today() - timedelta(days = i)
			if i == 0:
				day_name = "Dnes"
			elif i == 1:
				day_name = "Včera"
			else:
				if day.strftime("%A") in day_translation:
					day_name = day_translation[day.strftime("%A")] + " " + day.strftime("%d.%m.%Y")
				else:
					day_name = day.strftime("%A") + " " + day.strftime("%d.%m.%Y")

			if channel['timeshift'] < 1440:
				i = channel['timeshift']
				
			item = self.dir_item( py2_encode_utf8( day_name ), '#archive_program#' + str(i) + '#' + channel_id )
			result.append(item)
	
		return result

	# #################################################################################################

	def show_future_days(self, channel_id):
		result = []

		for i in range(7):
			day = date.today() + timedelta(days = i)
			if i == 0:
				day_name = "Dnes"
			elif i == 1:
				day_name = "Zítra"
			else:
				if day.strftime("%A") in day_translation:
					day_name = day_translation[day.strftime("%A")] + " " + day.strftime("%d.%m.%Y")
				else:
					day_name = day.strftime("%A") + " " + day.strftime("%d.%m.%Y")

			item = self.dir_item( py2_encode_utf8( day_name ), '#future_program#' + str(i) + '#' + channel_id )
			result.append(item)
	
		return result

	# #################################################################################################
	
	def show_future_program(self, channel_id):
		result = []
		
		day, channel_id = channel_id.split('#')
		day = int(day)
		
		if day == 0:
			from_datetime = datetime.now()
			duration_min = int((datetime.combine(date.today()+timedelta(days = 1), datetime.min.time()) - from_datetime).total_seconds() // 60) - 1
		else:
			from_datetime = datetime.combine(date.today()+timedelta(days = day), datetime.min.time())
			duration_min = 1439

		events = self.sledovanitv.get_epg( from_datetime, duration_min ).get(channel_id,[])
		
		for event in events:
			startts = self.sledovanitv.convert_time( event["startTime"] )
			start = datetime.fromtimestamp(startts)
			endts = self.sledovanitv.convert_time( event["endTime"] )
			end = datetime.fromtimestamp(endts)
			epg_id = event['eventId']

			if start.strftime("%A") in day_translation_short:
				title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["title"]
			else:
				title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["title"]
				
			plot = event.get('description')
			img = event.get('poster')
			
			item = self.dir_item( py2_encode_utf8( title ), "#add_recording#" + str(epg_id) )
			
			if plot:
				item['plot'] = plot
				
			if img:
				item['img'] = img
				
			item['menu'] = { 'Nahrát pořad': {'list': "#add_recording#" + str(epg_id) } }
			result.append(item)
			
			
		return result


	# #################################################################################################
	
	def show_archive_program(self, channel_id ):
		day_min, channel_id = channel_id.split('#')
		day_min = int(day_min)
		
		result = []
		
		if day_min > 30:
			from_datetime = datetime.now() - timedelta(minutes = day_min) 
			to_datetime = datetime.now()
		elif day_min == 0:
			from_datetime = datetime.combine(date.today(), datetime.min.time())
			to_datetime = datetime.now()
		else:
			from_datetime = datetime.combine(date.today(), datetime.min.time()) - timedelta(days = day_min)
			to_datetime = datetime.combine(from_datetime, datetime.max.time())
			
		from_ts = int(time.mktime(from_datetime.timetuple()))
		to_ts = int(time.mktime(to_datetime.timetuple()))
	
		events = self.sledovanitv.get_epg( from_datetime, int((to_datetime - from_datetime).total_seconds() // 60) ).get( channel_id, [] )
		
		for event in events:
			startts = self.sledovanitv.convert_time( event["startTime"] )
			start = datetime.fromtimestamp(startts)
			endts = self.sledovanitv.convert_time( event["endTime"] )
			end = datetime.fromtimestamp(endts)
			epg_id = event['eventId']

			if startts < from_ts:
				continue

			if to_ts <= int(endts):
				break
			
			if start.strftime("%A") in day_translation_short:
				title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["title"])
			else:
				title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["title"])
				
			plot = event.get('description')
			img = event.get('poster')
			
			item = self.video_item( "#play_event#" + str(epg_id))
			item['title'] = py2_encode_utf8( title )
			
			if plot:
				item['plot'] = plot
				
			if img:
				item['img'] = img
				
			item['menu'] = { 'Nahrát pořad': { 'list': "#add_recording#" + str(epg_id) } }
			result.append(item)
			
		return result
	
	# #################################################################################################
	
	def show_recordings(self, only_finished=True):
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'
		result = []
		recordings = {}

		if only_finished:
			item = self.dir_item("Budoucí nahrávky", '#future_recordings')
			result.append( item )
			
			def check_recording_state( s1, s2 ):
				return s1 == s2
		else:
			def check_recording_state( s1, s2 ):
				return s1 != s2
			

		for record in self.sledovanitv.get_recordings():
			if not enable_adult and record.get('channelLocked','') == 'pin':
				continue 
			
			if check_recording_state( record["enabled"], 1 ):
				event = record.get('event',{})
				
				desc = event.get("title", '')
				
				if 'expires' in record:
					desc += ' [expiruje ' + datetime.strptime(record["expires"],"%Y-%m-%d").strftime("%d.%m.%Y")+']'
					
				title = event["startTime"][8:10] + "." + event["startTime"][5:7] + ". " + event["startTime"][11:16] + "-" + event["endTime"][11:16] + " [" + record["channelName"] + "] [COLOR yellow]" + record["title"] + "[/COLOR]"
				
				item = self.video_item( "#play_recording#" + str(record["id"]))
				item['title'] = py2_encode_utf8( title )
				item['plot'] = desc + '\n' + event.get('description', '')
				item['img'] = event.get("poster", '')
				item['year'] = event.get("year", 0)
				item['length'] = record.get("eventDuration", 0) * 60
				item['menu'] = { 'Smazat nahrávku': { 'list': "#del_recording#" + str(record["id"]) } }
				
				if record["enabled"] != 1:
					item['url'] = '#'
	
				result.append(item)
	

		return result
	
	# #################################################################################################
	
	def add_recording(self, epg_id):
		ret = self.sledovanitv.add_recording(epg_id)
		item = self.video_item('#')
		item['title'] = "Nahrávka přidána" if ret else "Při přidávaní nahrávky nastala chyba"
		
		return [ item ]

	# #################################################################################################
	
	def delete_recording(self, rec_id):
		self.sledovanitv.delete_recording(rec_id)
		client.refresh_screen()
		return []
		
	# #################################################################################################

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
		
		try:
			if url.startswith('#play_tv#'):
				stream_links = self.sledovanitv.get_live_link( url[9:] )

			elif url.startswith('#play_radio#'):
				stream_links = [ { 'quality': '480p', 'url': self.sledovanitv.get_raw_link( url[12:] ) } ]

			elif url.startswith('#play_event#'):
				stream_links = self.sledovanitv.get_event_link( url[12:] )
				
			elif url.startswith('#play_recording#'):
				stream_links = self.sledovanitv.get_recording_link( url[16:] )
	
			else:
				stream_links = []
				
			if stream_links == None:
				stream_links = []
				
		except Exception as e:
			if "SLEDOVANI.TV" in str(e):
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				return None
			else:
				raise
			
		for one in stream_links:
			item = item.copy()
			item['url'] = one['url']
			item['quality'] = one['quality']
			result.append(item)
			
		if select_cb and len(result) > 0:
			return select_cb(result)

		return result
	