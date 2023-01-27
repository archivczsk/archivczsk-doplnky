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

from o2tv import O2tvCache
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


addon = ArchivCZSK.get_xbmc_addon('plugin.video.archivo2tv')

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class O2tvContentProvider(ContentProvider):
	favourites = None
	enable_userbouquet = None
	userbuquet_player = None

	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'o2tv', '/', username, password, filter, tmp_dir)
		
		self.session = session
		self.data_dir = data_dir
		self.favourites = None

		if not username or not password or not device_id:
			self.error("No login data provided")
			self.o2tv = None
		else:
			self.o2tv = O2tvCache.get(username, password, device_id, addon.getSetting('devicename'), data_dir, client.log.info )
			
		if O2tvContentProvider.favourites:
			# load cached favourites from global cache
			self.favourites = O2tvContentProvider.favourites
		else:
			# load favourites from disc and save it to global cache
			self.load_favourites()
			O2tvContentProvider.favourites = self.favourites

		ub_enable = addon.getSetting('enable_userbouquet') == "true"
		ub_player = addon.getSetting('player_name')
		if O2tvContentProvider.enable_userbouquet == None or O2tvContentProvider.userbuquet_player == None:
			O2tvContentProvider.enable_userbouquet = ub_enable
			O2tvContentProvider.userbuquet_player = ub_player
		
		if O2tvContentProvider.enable_userbouquet != ub_enable or O2tvContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			O2tvContentProvider.enable_userbouquet = ub_enable
			O2tvContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( ArchivCZSK.get_addon('plugin.video.archivo2tv'), 'userbouquet_gen' )

	# #################################################################################################

	def load_favourites(self):
		if self.favourites != None:
			return
		
		result = []
		
		try:
			with open( os.path.join(self.data_dir, 'favourites.txt'), 'r' ) as f:
				for line in f.readlines():
					result.append( line.rstrip() )
		except:
			pass
		
		self.favourites = result
		
	# #################################################################################################

	def save_favourites(self):
		with open( os.path.join(self.data_dir, 'favourites.txt'), 'w' ) as f:
			for fav in self.favourites:
				f.write( fav + '\n')
		
	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', 'search', '!download']

	# #################################################################################################

	def categories(self):
		if not self.o2tv:
			item = self.video_item('#')
			item['title'] = "Nejsou nastaveny přihlašovací údaje"
			return [ item ]
		
		result = []
		item = self.dir_item("Všechny kanály", "#channels" )
		item['plot'] = "Seznam předplacených kanálů včetně archivu"
		result.append(item)

		item = self.dir_item("Moje seznamy kanálů", "#my_lists" )
		item['plot'] = "Moje seznamy kanálů"
		result.append(item)
		
		item = self.dir_item("Nahrávky", "#recordings" )
		item['plot'] = "Tu nájdete nahrávky z vašich kanálov"
		result.append(item)
		
		if addon.getSetting('enable_extra') == "true":
			item = self.dir_item("Speciálni sekce", "#extra" )
			item['plot'] = "Speciálni sekce pro pokročilé uživatele"
			result.append( item )

		return result
	
	# #################################################################################################
	
	def list(self, url):
		try:
			if url == '#channels':
				return self.show_channels()
			elif url == '#my_lists':
				return self.show_my_lists()
			elif url == "#favourites":
				return self.show_favourites()
			elif url == '#recordings':
				return self.show_recordings()
			elif url == '#future_recordings':
				return self.show_recordings(False)
			elif url == '#extra':
				return self.show_extra_menu()
			elif url.startswith( '#channel#' ):
				return self.show_channel(url[9:])
			elif url.startswith( '#future_program#' ):
				return self.show_future_program(url[16:])
			elif url.startswith( '#archive_program#' ):
				return self.show_archive_program(url[17:])
			elif url.startswith( '#add_recording#' ):
				return self.add_recording(int(url[15:]))
			elif url.startswith( '#del_recording#' ):
				return self.delete_recording(int(url[15:]))
			elif url.startswith( '#my_list#' ):
				return self.show_my_list(url[9:])
			elif url.startswith( '#add_fav#' ):
				return self.add_fav(url[9:])
			elif url.startswith( '#del_fav#' ):
				return self.del_fav(url[9:])
	
			elif url.startswith( '#extra#' ):
				return self.show_extra_menu(url[6:])

		except Exception as e:
			client.log.error("O2TV Addon ERROR:\n%s" % traceback.format_exc())
			
			if "O2TVAPI" in str(e):
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
			
			self.o2tv.refresh_configuration(True)
			for pdev in self.o2tv.devices:
				title = py2_encode_utf8(pdev["deviceName"]) + " - " + datetime.fromtimestamp(int(pdev["lastLoginTimestamp"]/1000)).strftime('%d.%m.%Y %H:%M') + " - " + pdev["lastLoginIpAddress"] + " - " + py2_encode_utf8(pdev["deviceId"])
				
				item = self.video_item('#')
				item['title'] = title
				item['plot'] = 'V menu můžete zařízení vymazat pomocí Smazat zařízení!'
				item['menu'] = {'Smazat zařízení!': {'list': '#extra#deldev#' + pdev["deviceId"], 'action-type': 'list'}}
				result.append(item)
				
		elif section.startswith('#deldev#'):
			dev_name = section[8:]
			self.o2tv.device_remove(dev_name)

			item = self.video_item('#')
			item['title'] = "[COLOR red]Zařízení %s bylo vymazáno![/COLOR]" % dev_name
			result.append(item)

		return result

	# #################################################################################################
	
	def search( self, query ):
		result = []
		
		if self.o2tv:
			search_items = self.o2tv.search(query)
		else:
			search_items = []
		
		if len( search_items ) == 0:
			return []
		
		channels = self.o2tv.get_channels()
		
		for programs in search_items:
			programs = programs["programs"][0]

			if programs["channelKey"] not in channels:
				continue # nezobrazovat nezakoupene kanaly

			startts = programs["start"]
			start = datetime.fromtimestamp(startts/1000)
			endts = programs["end"]
			end = datetime.fromtimestamp(endts/1000)
			epg_id = programs["epgId"]
			
			if start.strftime("%A") in day_translation_short:
				title = py2_encode_utf8(programs["name"]) + " (" + py2_encode_utf8(programs["channelKey"]) + " | " + day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"
			else:
				title = py2_encode_utf8(programs["name"]) + " (" + py2_encode_utf8(programs["channelKey"]) + " | " + start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"
				
			item = self.video_item( "#play_video#" + json.dumps( { 'key': programs["channelKey"], "from" : startts, "to": endts, "epg_id" : epg_id }))
			item['title'] = title
			
			plot = programs.get('shortDescription', '')
			if len(plot) > 0:
				item['plot'] = plot

			if 'picture' in programs:				 
				item['img'] = 'https://o2tv.cz' + programs['picture']
				
			item['menu'] = { 'Nahrát pořad': { 'list': "#add_recording#" + str(epg_id) } }
			result.append(item)

		return result
	
	# #################################################################################################
	
	def show_my_lists(self):
		user_lists = self.o2tv.get_user_channel_lists()

		result = []

		item = self.dir_item( "Favoritní", '#favourites' )
		result.append(item)
		
		for name in user_lists:
			item = self.dir_item( py2_encode_utf8(name), '#my_list#' + json.dumps( user_lists[name]) )
			result.append(item)
		
		return result
	
	# #################################################################################################

	def show_my_list(self, json_names ):
		channels = self.o2tv.get_channels()
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'
		
		result = []
		for name in json.loads(json_names):
			try:
				channel = channels[name]
			except:
				continue
		
			if not enable_adult and channel['adult']:
				continue

			item = self.dir_item( py2_encode_utf8( channel['name'] ), '#channel#' + channel['key'] )
			if 'logo' in channel:
				item['img'] = channel['logo']
			
			result.append(item)

		return result
	
	# #################################################################################################
	
	def add_fav(self, key ):
		item = self.video_item('#')
		
		if key not in self.favourites:
			self.favourites.append(key)
			self.save_favourites()
			item['title'] = 'Přidáno do favoritních'
		else:
			item['title'] = 'Kanál už je ve favoritních'
		
		return [ item ]
		
	# #################################################################################################
	
	def del_fav(self, key ):
		if key in self.favourites:
			self.favourites.remove(key)
			self.save_favourites()
			client.refresh_screen()

		return []
		
	# #################################################################################################

	def show_favourites(self):
		self.load_favourites()
		channels = self.o2tv.get_channels()
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'
		
		
		result = []
		for name in self.favourites:
			name = py2_decode_utf8( name )
			try:
				channel = channels[name]
			except:
				continue
		
			if not enable_adult and channel['adult']:
				continue

			item = self.dir_item( py2_encode_utf8( channel['name'] ), '#channel#' + channel['key'] )
			if 'logo' in channel:
				item['img'] = channel['logo']
			
			item['menu'] = { "Odstranit z favoritních" : { 'list' : '#del_fav#' + channel['key'] } }
			
			result.append(item)

		return result
	
	# #################################################################################################
	
	def show_channels(self):
		channels = self.o2tv.get_channels_sorted()
		enable_adult = addon.getSetting('enable_adult').lower() == 'true'
		
		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			item = self.dir_item( py2_encode_utf8( channel['name'] ), '#channel#' + channel['key'] )
			if 'logo' in channel:
				item['img'] = channel['logo']
			
			item['menu'] = { "Přidat do favoritních" : { 'list' : '#add_fav#' + channel['key'] } }
			
			result.append(item)
		
		return result

	# #################################################################################################
	
	def show_channel(self, channel_key ):
		channel_key = py2_decode_utf8(channel_key)
		
		channel = self.o2tv.get_channels()[channel_key]
		
		result = []
		
		try:
			epg_id = channel['live']['epgId']
		except:
			epg_id = 0
	
		if epg_id != 0:
			epgdata = self.o2tv.get_epg_detail( epg_id )
#			epgdata = channel['live']

			start = datetime.fromtimestamp(epgdata["start"])
			end = datetime.fromtimestamp(epgdata["end"])
			title = "Živě: " + py2_encode_utf8(epgdata["name"]) + " (" + start.strftime("%H:%M") + " - " + end.strftime("%H:%M") + ")"
		else:
			epgdata = None
			title = "Živě"
	
		item = self.video_item( '#play_live#' + channel_key )
		item['title'] = title
		if epgdata:
			if 'img' in epgdata:
				item['img'] = epgdata['img']
			
			plot = epgdata.get('long', "")
			if not plot or len(plot) == 0:
				plot = epgdata.get('short', "")
			
			if plot and len(plot) > 0:
				item['plot'] = plot
				
			if "ratings" in epgdata and len(epgdata["ratings"]) > 0:
				for _, rating_value in list(epgdata["ratings"].items()):
					item['rating'] = rating_value/10
					break
		
		result.append(item)
		
	   
		if channel['timeshift']:
			item = self.dir_item( 'Budoucí (nastavení nahrávek)', '#future_program#' + channel_key )
			result.append(item)

			for i in range(7):
				if (i * 60 * 24) > channel['timeshift']:
					break
				
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
					
				item = self.dir_item( py2_encode_utf8( day_name ), '#archive_program#' + str(i) + '#' + channel_key )
				result.append(item)
		
		return result

	# #################################################################################################

	def show_future_program(self, channel_key):
		result = []
		
		from_datetime = datetime.now()
		from_ts = int(time.mktime(from_datetime.timetuple()))
		to_ts = from_ts
		
		for i in range(7):
			from_ts = to_ts
			to_ts = from_ts + 24*3600
			
			events = self.o2tv.get_channel_epg( channel_key, from_ts * 1000, to_ts * 1000 )
			
			for event in events:
				startts = event["startTimestamp"]
				start = datetime.fromtimestamp(startts/1000)
				endts = event["endTimestamp"]
				end = datetime.fromtimestamp(endts/1000)
				epg_id = event['epgId']

				if start.strftime("%A") in day_translation_short:
					title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["name"]
				else:
					title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + event["name"]
					
				plot = event['shortDescription'] if 'shortDescription' in event else None
				img = event['picture'] if 'picture' in event else None
				
				item = self.dir_item( py2_encode_utf8( title ), "#add_recording#" + str(epg_id) )
				
				if plot:
					item['plot'] = plot
					
				if img:
					item['img'] = img
					
				item['menu'] = { 'Nahrát pořad': {'list': "#add_recording#" + str(epg_id) } }
				result.append(item)
				
		return result


	# #################################################################################################
	
	def show_archive_program(self, channel_key ):
		day_min, channel_key = channel_key.split('#')
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
	
		events = self.o2tv.get_channel_epg( channel_key, from_ts * 1000, to_ts * 1000 )
		
		for event in events:
			startts = event["startTimestamp"]
			start = datetime.fromtimestamp(startts/1000)
			endts = event["endTimestamp"]
			end = datetime.fromtimestamp(endts/1000)
			epg_id = event['epgId']

			if startts < from_ts:
				continue

			if to_ts <= int(endts/1000):
				break
			
			if start.strftime("%A") in day_translation_short:
				title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["name"])
			else:
				title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["name"])
				
			plot = event['shortDescription'] if 'shortDescription' in event else None
			img = event['picture'] if 'picture' in event else None
			
			item = self.video_item( "#play_video#" + json.dumps( { 'key': channel_key, "from" : startts, "to": endts, "epg_id" : epg_id }))
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
			

		data_pvr = self.o2tv.get_recordings()
	
		if "result" in data_pvr and len(data_pvr["result"]) > 0:
			for program in data_pvr["result"]:
				if check_recording_state( program["state"], "DONE" ):
					pvrProgramId = program["pvrProgramId"]
					epgId = program["program"]["epgId"]
					if "ratings" in program["program"] and len(program["program"]["ratings"]) > 0:
						ratings = program["program"]["ratings"]
					else:
						ratings = {}
					if "longDescription" in program["program"] and len(program["program"]["longDescription"]) > 0:
						plot = program["program"]["longDescription"]
					else:
						plot = None
					if "images" in program["program"] and len(program["program"]["images"]) > 0 and "cover" in program["program"]["images"][0]:
						img = program["program"]["images"][0]["cover"]
					else:
						img = None
					recordings.update({program["program"]["start"]+random.randint(0,100) : {"pvrProgramId" : pvrProgramId, "name" : program["program"]["name"], "channelKey" : program["program"]["channelKey"], "start" : datetime.fromtimestamp(program["program"]["start"]/1000).strftime("%d.%m %H:%M"), "end" : datetime.fromtimestamp(program["program"]["end"]/1000).strftime("%H:%M"), "plot" : plot, "img" : img, "ratings" : ratings}}) 
		
			for recording in sorted(list(recordings.keys()), reverse = True):
				title = recordings[recording]["name"] + " (" + recordings[recording]["channelKey"] + " | " + recordings[recording]["start"] + " - " + recordings[recording]["end"] + ")"

				thumb = "https://www.o2tv.cz/" + recordings[recording]["img"]
				rating = None
				for _, rating_value in list(recordings[recording]["ratings"].items()):
					rating = rating_value/10
					break
				
				if only_finished:
					url = '#play_recording#' + str(recordings[recording]["pvrProgramId"])
				else:
					url = '#'
					
				item = self.video_item( url )
				item['title'] = py2_encode_utf8(title)
				if plot:
					item['plot'] = plot
					
				if img:
					item['img'] = thumb
					
				if rating:
					item['rating'] = rating
				
				item['menu'] = {'Smazat nahrávku': { 'list': '#del_recording#' + str(recordings[recording]["pvrProgramId"]) } }
				result.append(item)

		return result
	
	# #################################################################################################
	
	def add_recording(self, epg_id):
		ret = self.o2tv.add_recording(epg_id)
		item = self.video_item('#')
		item['title'] = "Nahrávka přidána" if ret else "Při přidávaní nahrávky nastala chyba"
		
		return [ item ]

	# #################################################################################################
	
	def delete_recording(self, rec_id):
		self.o2tv.delete_recording(rec_id)
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
			if url.startswith('#play_live#'):
				stream_links = self.o2tv.get_live_link( url[11:] )
	
			elif url.startswith('#play_video#'):
				video_data = json.loads( url[12:] )
				video_data['to'] += (int(addon.getSetting("offset"))*60*1000)
				stream_links = self.o2tv.get_video_link( video_data['key'], video_data['from'], video_data['to'], video_data['epg_id'] )
	
			elif url.startswith('#play_recording#'):
				stream_links = self.o2tv.get_recording_link( int(url[16:]) )
	
			else:
				stream_links = []
		except Exception as e:
			if "O2TVAPI" in str(e):
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
	