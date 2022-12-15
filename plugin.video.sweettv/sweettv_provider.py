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

from sweettv import SweetTvCache
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

__scriptid__ = 'plugin.video.sweettv'
addon = ArchivCZSK.get_addon(__scriptid__)

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class SweetTVContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None

	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'sweet.tv', '/', username, password, filter, tmp_dir)
		
		self.session = session
		self.data_dir = data_dir
		self.init_error_msg = None

		if not username or not password or not device_id:
			self.error("No login data provided")
			self.sweettv = None
		else:
			try:
				self.sweettv = SweetTvCache.get(username, password, device_id, data_dir, client.log.info )
			except Exception as e:
				client.log.error("Sweet.tv Addon ERROR:\n%s" % traceback.format_exc())
			
				if "SWEET.TV" in str(e):
					self.init_error_msg = str(e)
					self.sweettv = None
				else:
					raise
			
		ub_enable = addon.get_setting('enable_userbouquet')
		ub_player = addon.get_setting('player_name')
		if SweetTVContentProvider.enable_userbouquet == None or SweetTVContentProvider.userbuquet_player == None:
			SweetTVContentProvider.enable_userbouquet = ub_enable
			SweetTVContentProvider.userbuquet_player = ub_player
		
		if SweetTVContentProvider.enable_userbouquet != ub_enable or SweetTVContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			SweetTVContentProvider.enable_userbouquet = ub_enable
			SweetTVContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( addon, 'userbouquet_gen' )

	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', 'search', '!download']

	# #################################################################################################

	def categories(self):
		if not self.sweettv:
			item = self.video_item('#')
			
			if self.init_error_msg:
				client.add_operation('SHOW_MSG', { 'msg': self.init_error_msg, 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				item['title'] = "%s" % self.init_error_msg
			else:
				item['title'] = "Nie sú nastavené prihlasovacie údaje"
			return [ item ]
		
		result = []
		
		item = self.dir_item("Live TV", "#channels" )
		item['plot'] = "Živé vysielanie televíznych programov"
		result.append(item)
		
		item = self.dir_item("Archiv", "#archive")
		item['plot'] = "Tu nájdete spätné prehrávanie vašich programov"
		result.append(item)

		item = self.dir_item("Filmy", "#movies")
		item['plot'] = "Tu nájdete zoznamy filmov dostupných pre vaše predplatné"
		result.append(item)

		if addon.get_setting('enable_extra'):
			item = self.dir_item("Špeciálna sekcia", "#extra" )
			item['plot'] = "Špeciálna sekcia pre pokročilých používateľov"
			result.append( item )

		return result
	
	# #################################################################################################
	
	def list(self, url):
		try:
			if url == '#home_page':
				return self.show_home()
			if url == '#channels':
				return self.show_channels()
			elif url == '#archive':
				return self.show_archive()
			elif url == '#movies':
				return self.show_movies_root()
			elif url == '#extra':
				return self.show_extra_menu()
			elif url.startswith( '#archive_days#' ):
				return self.show_archive_days(url[14:])
			elif url.startswith( '#archive_program#' ):
				return self.show_archive_program(url[17:])
			elif url.startswith('#movies#'):
				return self.show_movies_root(url[8:])
			elif url.startswith('#movie_genre#'):
				return self.show_movies_genre(url[13:])
			elif url.startswith('#movie_collection#'):
				return self.show_movies_collection(url[18:])
	
			elif url.startswith( '#extra#' ):
				return self.show_extra_menu(url[6:])

		except Exception as e:
			client.log.error("Sweet.tv Addon ERROR:\n%s" % traceback.format_exc())
			
			if "SWEET.TV" in str(e):
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
			item=self.dir_item( 'Zaregistrované zariadenia', '#extra#devices')
			item['plot'] = "Tu si môžete zobraziť a prípadne vymazať/odregistrovať zbytočné zariadenia, aby ste se mohli znova inde prihlásiť."
			result.append( item )
		elif section == '#devices':
			
			for pdev in self.sweettv.get_devices():
				dev_added = datetime.fromtimestamp(int(pdev["date_added"])).strftime('%d.%m.%Y %H:%M')
				title = 'Model: %s, Typ: %s, Pridané: %s' % (pdev['model'], pdev["type"], dev_added) 
				
				item = self.video_item('#')
				item['title'] = py2_encode_utf8(title)
				item['plot'] = 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'
				item['menu'] = {'Zmazať zariadenie!': {'list': '#extra#deldev#' + str(pdev["token_id"]), 'action-type': 'list'}}
				result.append(item)
				
		elif section.startswith('#deldev#'):
			dev_name = section[8:]
			self.sweettv.device_remove(dev_name)

			item = self.video_item('#')
			item['title'] = "[COLOR red]Zariadenie %s bolo vymazané![/COLOR]" % dev_name
			result.append(item)

		return result

	# #################################################################################################

	def search( self, query ):
		self.sweettv.check_login()
		events = self.sweettv.search(query)
		
		result = self._process_movie_data( events['movies'] )

		for event in events['events']:
			item = self.video_item('#play_event#' + event['channel_id'] + '#', event['event_id'])
			item['title'] = py2_encode_utf8( event['title'] + ' [COLOR yellow]' + event['time'] + '[/COLOR]')
			item['img'] = event['poster']
			result.append(item)
			
		return result
	
	# #################################################################################################
	# XXX
	def show_home(self):
		channels = self.sweettv.get_home()

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
	
	def show_channels(self):
		channels = self.sweettv.get_channels_sorted()
		enable_adult = addon.get_setting('enable_adult')

		epg = self.sweettv.get_epg()
		
		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			epgdata = epg.get(channel['id'])
			item = self.video_item( '#play_tv#' + channel['id'] )
			
			if epgdata:
				epgdata = epgdata[0]

				
				epg_title = " (" + epgdata["text"] + " - " + datetime.fromtimestamp(int(epgdata["time_start"])).strftime('%H:%M') + "-" + datetime.fromtimestamp(int(epgdata["time_stop"])).strftime('%H:%M') + ")"
				item['img'] = epgdata.get('preview_url')
#				item['duration'] = epgdata.get('duration')*60
#				item['year'] = epgdata.get('year')
				
				item['title'] = channel["name"] + ' [COLOR yellow]' + epg_title + '[/COLOR]'
			else:
				item['title'] = channel['name']
			
			result.append(item)
		
		return result

	# #################################################################################################
	
	def show_archive(self):
		channels = self.sweettv.get_channels_sorted()
		enable_adult = addon.get_setting('enable_adult')

		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue

			if channel["timeshift"] == 0:
				continue
			
			tsd = int(channel["timeshift"])
			if tsd == 1:
				dtext=" deň"
			elif tsd < 5:
				dtext=" dni"
			else:
				dtext=" dní"

			item = self.dir_item( channel['name'] + " [COLOR green][" + str(tsd) + dtext + "][/COLOR]", '#archive_days#' + channel['id'] )
			result.append(item)
			
		return result


	# #################################################################################################
	
	def show_archive_days(self, channel_id):
		result = []
		channel = self.sweettv.get_channels().get( int(channel_id) )
		
		if not channel:
			return []

#		item = self.dir_item( 'Budoucí (nastavení nahrávek)', '#future_days#' + channel_id )
#		result.append(item)

		for i in range(int(channel['timeshift'])):
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

			item = self.dir_item( py2_encode_utf8( day_name ), '#archive_program#' + str(i) + '#' + channel_id )
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
	
		events = self.sweettv.get_epg( from_ts, 100, [ channel_id ] ).get( channel_id, [] )
		
		for event in events:
			startts = event["time_start"]
			start = datetime.fromtimestamp(startts)
			endts = event["time_stop"]
			end = datetime.fromtimestamp(endts)
			epg_id = event['id']

			if startts < from_ts:
				continue

			if to_ts <= int(endts):
				break
			
			if start.strftime("%A") in day_translation_short:
				title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["text"])
			else:
				title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["text"])
				
#			plot = event.get('description')
			plot = None
			img = event.get('preview_url')
			
			item = self.video_item( "#play_event#" + channel_id + '#' + str(epg_id))
			item['title'] = py2_encode_utf8( title )
			
			if plot:
				item['plot'] = plot
				
			if img:
				item['img'] = img
				
#			item['menu'] = { 'Nahrát pořad': { 'list': "#add_recording#" + str(epg_id) } }
			result.append(item)
			
		return result
	
	# #################################################################################################

	def show_movies_root(self, root=None):
		result = []
		
		if root == None:
			item = self.dir_item( 'Podľa žánru', '#movies#genres' )
			result.append(item)
	
			item = self.dir_item( 'Podľa kolekcie', '#movies#collections' )
			result.append(item)
			return result
		
		data = self.sweettv.get_movie_configuration()
		
		if root == 'collections':
			data = data['collections'] + self.sweettv.get_movie_collections()
			prefix = '#movie_collection#'
		elif root == 'genres':
			data = data['genres']
			prefix = '#movie_genre#'
		else:
			data = {}

		for one in data:
			item = self.dir_item( one['title'], prefix + str(one['id']) )
			result.append(item)
	
		return result


	# #################################################################################################
	
	def _process_movie_data(self, data):
		result = []
		show_paid = addon.get_setting('show_paid_movies')
		
		for movie in data:
			if movie['available']:
				url = '#play_movie#' + movie['id'] + '#' + movie['owner_id']
				title = movie['title']
			else:
				# this is a PPV movie
				if not show_paid:
					continue
				
				if movie['trailer']:
					try:
						url = '#play_raw#' + self.sweettv.resolve_streams(movie['trailer'])[0]['url']
					except:
						url = '#'
				else:
					url = '#'
				title = "[COLOR yellow]*[/COLOR] " + movie['title']
			
			item = self.video_item(url)
			item['title'] = title
			item['plot'] = movie['title']
			item['plot'] = movie['plot']
			item['img'] = movie['poster']
			item['duration'] = movie['duration']
			item['year'] = movie['year']
			result.append(item)

			if movie['rating']:
				item['rating'] = movie['rating']
			
		return result

	# #################################################################################################

	def show_movies_collection(self, collection_id ):
		data = self.sweettv.get_movie_collection( collection_id )
		return self._process_movie_data(data)	

	# #################################################################################################

	def show_movies_genre(self, genre_id ):
		data = self.sweettv.get_movie_genre( genre_id )
		return self._process_movie_data(data)

	# #################################################################################################
	
	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
#		self.info("RESOLVE: %s" % item )
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
				stream_links = self.sweettv.get_live_link( url[9:] )

			elif url.startswith('#play_event#'):
				channel_id, epg_id = url[12:].split('#')
				stream_links = self.sweettv.get_live_link( channel_id, epg_id )
				
			elif url.startswith('#play_movie#'):
				movie_id, owner_id = url[13:].split('#')
				stream_links = self.sweettv.get_movie_link( movie_id, owner_id )

			elif url.startswith('#play_raw#'):
				stream_links = [ { 'url': url[10:], 'quality': 1, 'name': '???' } ]
	
			else:
				stream_links = []
				
			if stream_links == None:
				stream_links = []
				
		except Exception as e:
			if "SWEET.TV" in str(e):
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				return None
			else:
				raise
			
		for one in stream_links:
			item = item.copy()
			self.debug("%s STREAM URL: %s" % (one['name'], one['url']) )
			item['url'] = one['url']
			item['quality'] = one['name']
			result.append(item)
			
		if select_cb and len(result) > 0:
			return select_cb(result)

		return result
	