# -*- coding: utf-8 -*-

import time, traceback

from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from tools_xbmc.contentprovider.provider import ContentProvider
from .rebittv import RebitTvCache

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

__scriptid__ = 'plugin.video.rebittv'
addon = ArchivCZSK.get_addon(__scriptid__)

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class RebitTVContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None

	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_name=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'rebit.tv', '/', username, password, filter, tmp_dir)
		
		self.session = session
		self.data_dir = data_dir
		self.init_error_msg = None

		if not username or not password or not device_name:
			self.error("No login data provided")
			self.rebittv = None
		else:
			try:
				self.rebittv = RebitTvCache.get(username, password, device_name, data_dir, client.log.info )
			except Exception as e:
				client.log.error("Rebit.tv Addon ERROR:\n%s" % traceback.format_exc())
			
				if "REBIT.TV" in str(e):
					self.init_error_msg = str(e)
					self.rebittv = None
				else:
					raise
			
		ub_enable = addon.get_setting('enable_userbouquet')
		ub_player = addon.get_setting('player_name')
		if RebitTVContentProvider.enable_userbouquet == None or RebitTVContentProvider.userbuquet_player == None:
			RebitTVContentProvider.enable_userbouquet = ub_enable
			RebitTVContentProvider.userbuquet_player = ub_player
		
		if RebitTVContentProvider.enable_userbouquet != ub_enable or RebitTVContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			RebitTVContentProvider.enable_userbouquet = ub_enable
			RebitTVContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( addon, 'userbouquet_gen' )

	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	# #################################################################################################

	def categories(self):
		if not self.rebittv:
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
	
			elif url.startswith( '#extra#' ):
				return self.show_extra_menu(url[6:])

		except Exception as e:
			client.log.error("Rebit.tv Addon ERROR:\n%s" % traceback.format_exc())
			
			if "REBIT.TV" in str(e):
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
			
			for pdev in self.rebittv.get_devices():
				
				dev_added = datetime.fromtimestamp(int(pdev["created_at"])).strftime('%d.%m.%Y %H:%M')
				title = 'Model: %s, Typ: %s, Pridané: %s' % (pdev['title'], pdev["type"], dev_added) 
				
				item = self.video_item('#')
				item['title'] = py2_encode_utf8(title)
				item['plot'] = 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'
				item['menu'] = {'Zmazať zariadenie!': {'list': '#extra#deldev#' + str(pdev["id"]), 'action-type': 'list'}}
				result.append(item)
				
		elif section.startswith('#deldev#'):
			dev_name = section[8:]
			self.rebittv.device_remove(dev_name)

			item = self.video_item('#')
			item['title'] = "[COLOR red]Zariadenie %s bolo vymazané![/COLOR]" % dev_name
			result.append(item)

		return result

	# #################################################################################################

	def show_channels(self):
		channels = self.rebittv.get_channels_sorted()
		enable_adult = addon.get_setting('enable_adult')

		epg = self.rebittv.get_current_epg()
		
		result = []
		for channel in channels:
			if not enable_adult and channel['adult']:
				continue
			
			epgdata = epg.get(channel['id'])
				
			item = self.video_item( '#play_tv#' + channel['id'] )
			
			if epgdata:
				epg_title = epgdata['title']
				
				if epgdata.get('subtitle'):
					epg_title += ': ' + epgdata['subtitle']
				
				epg_title = " (" + epg_title + " - " + datetime.fromtimestamp(int(epgdata["start"])).strftime('%H:%M') + "-" + datetime.fromtimestamp(int(epgdata["stop"])).strftime('%H:%M') + ")"
				item['img'] = channel.get('picon')
				
				item['title'] = channel["name"] + ' [COLOR yellow]' + epg_title + '[/COLOR]'
			else:
				item['title'] = channel['name']
			
			result.append(item)
		
		return result

	# #################################################################################################
	
	def show_archive(self):
		channels = self.rebittv.get_channels_sorted()
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
		channel = self.rebittv.get_channels().get( channel_id )
		
		if not channel:
			return []

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
	
		events = self.rebittv.get_epg( channel_id, from_ts, to_ts )
		
		for event in events:
			startts = event["start"]
			start = datetime.fromtimestamp(startts)
			endts = event["stop"]
			end = datetime.fromtimestamp(endts)
			epg_id = event['id']

			if startts < from_ts:
				continue

			if to_ts <= int(startts):
				break
			
			if start.strftime("%A") in day_translation_short:
				title = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["title"])
			else:
				title = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + str(event["title"])
				
			plot = event.get('description')
			
			item = self.video_item( "#play_event#" + channel_id + '#' + str(epg_id))
			item['title'] = py2_encode_utf8( title )
			
			if plot:
				item['plot'] = plot
				
			result.append(item)
			
		return result
	
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
				stream_links = self.rebittv.get_live_link( url[9:] )

			elif url.startswith('#play_event#'):
				channel_id, epg_id = url[12:].split('#')
				stream_links = self.rebittv.get_live_link( channel_id, epg_id )
			else:
				stream_links = []
				
			if stream_links == None:
				stream_links = []
				
		except Exception as e:
			if "REBIT.TV" in str(e):
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				return None
			else:
				raise
			
		for one in stream_links:
			item = item.copy()
			self.debug("%s STREAM URL: %s" % (one['resolution'], one['url']) )
			item['url'] = one['url']
			item['quality'] = one['resolution']
			result.append(item)
			
		if select_cb and len(result) > 0:
			return select_cb(result)

		return result
	
