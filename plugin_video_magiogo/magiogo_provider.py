# -*- coding: utf-8 -*-

import re,sys,os,time,requests,traceback

import threading
import base64
import requests
from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from .magiogo import MagioGoCache
from tools_xbmc.contentprovider.provider import ContentProvider

try:
	from urllib import quote
	is_py3 = False
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')

except:
	from urllib.parse import quote
	is_py3 = True
	
	def py2_encode_utf8( text ):
		return text

__scriptid__ = 'plugin.video.magiogo'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class magiogoContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None
	
	# #################################################################################################
	
	def __init__(self, username=None, password=None, device_id=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'Magio GO', '/', None, None, filter, tmp_dir)
		
		self.session = session
		
		device_type = int(__addon__.getSetting('devicetype'))
		region = __addon__.getSetting('region')
		
		try:
			self.magiogo = MagioGoCache.get(region, username, password, device_id, device_type, data_dir, client.log.info)
		except Exception as e:
			client.log.error("Magio GO Addon ERROR:\n%s" % traceback.format_exc())
		
			if "Magio GO" in str(e):
				self.init_error_msg = str(e)
				self.magiogo = None
			else:
				raise


		ub_enable = __addon__.getSetting('enable_userbouquet') == "true"
		ub_player = __addon__.getSetting('player_name')
		if magiogoContentProvider.enable_userbouquet == None or magiogoContentProvider.userbuquet_player == None:
			magiogoContentProvider.enable_userbouquet = ub_enable
			magiogoContentProvider.userbuquet_player = ub_player
		
		if magiogoContentProvider.enable_userbouquet != ub_enable or magiogoContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			magiogoContentProvider.enable_userbouquet = ub_enable
			magiogoContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( ArchivCZSK.get_addon('plugin.video.magiogo'), 'userbouquet_gen' )
		
		from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
		self.http_endpoint = archivCZSKHttpServer.getAddonEndpoint( __scriptid__ )
			
	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	# #################################################################################################

	def categories(self):
		if not self.magiogo:
			item = self.video_item('#')
			
			if self.init_error_msg:
				client.add_operation('SHOW_MSG', { 'msg': self.init_error_msg, 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				item['title'] = "%s" % self.init_error_msg
			else:
				item['title'] = "Nie sú nastavené prihlasovacie údaje"
			return [ item ]
		
		result = []

		item = self.dir_item("TV Stanice", "#tv" )
		item['plot'] = "Tu nájdete zoznam zaplatených Live TV staníc"
		result.append(item)
	
		item = self.dir_item("Archív", "#archive" )
		item['plot'] = "Tu nájdete spätné prehrávanie vašich kanálov z archívu"
		result.append(item)
		
		if __addon__.getSetting('enable_extra') == "true":
			item = self.dir_item("Špeciálna sekcia", "#extra" )
			item['plot'] = "Špeciálna sekcia pre pokročilejších používateľov"
			result.append( item )

	
		return result
	
	# #################################################################################################

	def list(self, url):
		self.info('List URL: "%s"' % url)
		
		try:
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

		except Exception as e:
			client.log.error("Magio GO Addon ERROR:\n%s" % traceback.format_exc())
			
			if "Magio GO" in str(e):
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
			item['plot'] = "Tu si môžete zobraziť a prípadne vymazať/odregistrovať zbytočné zariadenia, aby ste sa mohli znova inde prihlásiť."
			result.append( item )
		elif section == '#devices':
			
			devices = self.magiogo.get_devices()
			for pdev in devices:
				title = pdev["name"] + "  -  " + pdev['cat']
				
				item = self.video_item('#')
				item['title'] = title
				if pdev['this']:
					item['title'] += " *"
				else:
					item['plot'] = 'V menu môžete zariadenie vymazať pomocou Zmazať zariadenie!'
					item['menu'] = {'Zmazať zariadenie!': {'list': '#extra#deldev#' + str(pdev["id"]), 'action-type': 'list'}}
					
				result.append(item)
				
		elif section.startswith('#deldev#'):
			dev_id = section[8:]
			ret, msg = self.magiogo.remove_device(dev_id)

			item = self.video_item('#')

			if ret:
				item['title'] = "[COLOR red]Zariadenie bolo vymazané![/COLOR]"
			else:
				item['title'] = "[COLOR red]Chyba: %s[/COLOR]" % msg
				
			result.append(item)

		return result

	# #################################################################################################
	
	def show_tv(self):
		channels = self.magiogo.get_channel_list(True)
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'

		result = []
		for channel in channels:
			if not enable_adult and channel.adult:
				continue

			item = self.video_item( '#live_video_link#' + channel.id )
			item['img'] = channel.preview
			
			if channel.epg_name and channel.epg_desc:
				item['title'] = channel.name+' [COLOR yellow]'+channel.epg_name+'[/COLOR]'
				item['plot'] = channel.epg_desc
			else:
				item['title'] = channel.name
			
			result.append(item)
			
		return(result)

	# #################################################################################################
	
	def show_archive(self):
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'
		channels = self.magiogo.get_channel_list()
		
		result = []
		for channel in channels:
			if not enable_adult and channel.adult:
				continue
			
			if channel.timeshift == None:
				continue
	
			if channel.timeshift > 0:
				tsd = int(channel.timeshift) // (24 * 3600)
				if tsd == 1:
					dtext=" deň"
				elif tsd < 5:
					dtext=" dni"
				else:
					dtext=" dní"
					
				item = self.dir_item( py2_encode_utf8(channel.name)+" [COLOR green]["+str(tsd)+dtext+"][/COLOR]", '#archive_channel#' + str(channel.id) + '|' + str(tsd) )
				item['img'] = channel.picon
				result.append(item)

		return result
	
	# #################################################################################################
	
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
				
			item = self.dir_item( den, '#archive_day#' + cid + '|' + day.strftime("%s") )
			result.append(item)
		
		return result

	# #################################################################################################

	def show_archive_day(self, url):
		cid,day = url.split("|")
		
		result = []
		for ch in self.magiogo.get_archiv_channel_programs(cid,day):
			item = self.video_item( '#archive_video_link#' + str(ch['id']) )
			item['title'] = ch['title']
			item['img'] = ch['image']
			item['plot'] = ch['plot']
			result.append(item)
		
		return result

	# #################################################################################################

	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		self.info("RESOLVE: %s" % item )
		url = item["url"]

		if url == '#':
			return None

		if url.startswith('#live_video_link#'):
			item['url'] = self.http_endpoint + '/playlive/' + base64.b64encode( url[17:].encode("utf-8") ).decode("utf-8") + '/index'
			return item
		elif url.startswith('#archive_video_link#'):
			item['url'] = self.http_endpoint + '/playarchive/' + base64.b64encode( url[20:].encode("utf-8") ).decode("utf-8") + '/index'
			return item
		
#		if url.startswith('#archive_video_link#'):
#			ch, fromts, tots = url[20:].split('|')
#			streams = self.telly.get_archive_video_link(int(ch), int(fromts), int(tots), __addon__.getSetting('enable_h265') == "true")

		return None
	
