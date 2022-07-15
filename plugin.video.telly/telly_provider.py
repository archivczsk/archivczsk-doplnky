# -*- coding: utf-8 -*-

import re,sys,os,time,requests,traceback
try:
	sys.path.append( os.path.dirname(__file__) )
except:
	pass

import threading
from datetime import date, timedelta, datetime
from Plugins.Extensions.archivCZSK.engine import client

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

from telly import TellyCache
import util
from provider import ContentProvider

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


__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.telly')

day_translation = {"Monday": "Pondelok", "Tuesday": "Utorok", "Wednesday": "Streda", "Thursday": "Štvrtok", "Friday": "Piatok", "Saturday": "Sobota", "Sunday": "Nedeľa"}
day_translation_short = {"Monday": "Po", "Tuesday": "Ut", "Wednesday": "St", "Thursday": "Št", "Friday": "Pi", "Saturday": "So", "Sunday": "Ne"}


class tellyContentProvider(ContentProvider):
	enable_userbouquet = None
	userbuquet_player = None
	
	# #################################################################################################
	
	def __init__(self, username=None, password=None, data_dir=None, session=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'telly', '/', None, None, filter, tmp_dir)
		
		self.session = session
		self.telly = TellyCache.get(data_dir, client.log.info)

		ub_enable = __addon__.getSetting('enable_userbouquet') == "true"
		ub_player = __addon__.getSetting('player_name')
		if tellyContentProvider.enable_userbouquet == None or tellyContentProvider.userbuquet_player == None:
			tellyContentProvider.enable_userbouquet = ub_enable
			tellyContentProvider.userbuquet_player = ub_player
		
		if tellyContentProvider.enable_userbouquet != ub_enable or tellyContentProvider.userbuquet_player != ub_player:
			# configuration options for userbouquet generator changed - call service to rebuild or remove userbouquet
			tellyContentProvider.enable_userbouquet = ub_enable
			tellyContentProvider.userbuquet_player = ub_player
			client.sendServiceCommand( ArchivCZSK.get_addon('plugin.video.telly'), 'userbouquet_gen' )
			
	# #################################################################################################

	def capabilities(self):
		return ['categories', 'resolve', '!download']

	# #################################################################################################

	def categories(self):
		result = []
		
		if not self.telly.device_token:
			item = self.video_item('#pair_device')
			item['title'] = 'Spárovať toto zariadenie s Telly účtom'
			item['plot'] = 'Toto umožní spárovať toto zariadenie s vašim Telly účtom. Budete potrebovať párovací kód, ktorý získate na https://moje.telly.cz'
			result.append(item)
		else:
			item = self.dir_item("TV Stanice", "#tv" )
			item['plot'] = "Tu nájdete zoznam zaplatených Live TV staníc"
			result.append(item)
		
			item = self.dir_item("Archív", "#archive" )
			item['plot'] = "Tu nájdete spätné prehrávanie vašich kanálov z archívu"
			result.append(item)
		
		return result
	
	# #################################################################################################

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

		return []
	
	# #################################################################################################
	
	def show_tv(self):
		channels = self.telly.get_channel_list()
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'
		cache_hours = int(__addon__.getSetting('epgcache'))
		enable_xmlepg = __addon__.getSetting('enable_xmlepg').lower() == 'true' and __addon__.getSetting('enable_userbouquet').lower() == 'true'

		# reload EPG cache if needed
		ret = self.telly.load_epg_cache()
		
		# ret == True -> there already exist cache file 
		if ret and enable_xmlepg:
			# if there exists already cache file and xmlepg is enabled, then cache file
			# is managed by telly service, so disable epg refresh here
			cache_hours = 0

		self.telly.fill_epg_cache([channel.epg_id for channel in channels], cache_hours)
		result = []
		for channel in channels:
			if not enable_adult and channel.adult:
				continue

			item = self.video_item( channel.stream_url )
			item['img'] = channel.preview
			
			epg = self.telly.get_channel_current_epg(channel.epg_id)

			if epg:
				item['title'] = channel.name+' [COLOR yellow]'+epg["title"]+'[/COLOR]'
				item['plot'] = epg['desc']
			else:
				item['title'] = channel.name
			
			result.append(item)
			
		return(result)

	# #################################################################################################
	
	def show_archive(self):
		enable_adult = __addon__.getSetting('enable_adult').lower() == 'true'
		channels = self.telly.get_channel_list()
		
		result = []
		for channel in channels:
			if not enable_adult and channel.adult:
				continue
			
			if channel.timeshift == None:
				continue
	
			if channel.timeshift > 0:
				tsd = int(channel.timeshift) // 24
				if tsd == 1:
					dtext=" den"
				elif tsd < 5:
					dtext=" dny"
				else:
					dtext=" dní"
					
				item = self.dir_item( py2_encode_utf8(channel.name)+" [COLOR green]["+str(tsd)+dtext+"][/COLOR]", '#archive_channel#' + str(channel.id) + '|' + str(channel.epg_id)+'|' + str(tsd) )
				item['img'] = channel.picon
				result.append(item)

		return result
	
	# #################################################################################################
	
	def show_archive_channel(self, url):
		cid,epg_id,days = url.split("|")
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
				
			item = self.dir_item( den, '#archive_day#' + cid + '|' + epg_id + '|' + day.strftime("%s") )
			result.append(item)
		
		return result

	# #################################################################################################

	def show_archive_day(self, url):
		cid,epg_id,day = url.split("|")
		
		result = []
		for ch in self.telly.get_archiv_channel_programs(cid,epg_id,day):
			item = self.video_item( ch['url'] )
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

		if url == '#pair_device':
			code = client.getTextInput(self.session, 'Zadajte párovací kód')
			
			if code:
				if self.telly.get_device_token_by_code(code):
					client.add_operation('SHOW_MSG', { 'msg': 'Zariadenie bolo úspešne spárované s vašim Telly účtom', 'msgType': 'info', 'msgTimeout': 0, 'canClose': True, })
				else:
					client.add_operation('SHOW_MSG', { 'msg': 'Párovanie zariadenia s vašim Telly účtom zlyhalo.\nSkontrolujte správnosť párovacieho kódu a skúste to znava.', 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
			
			return None
		
		if url == '#':
			return None
		
		if url.startswith('#archive_video_link#'):
			ch, fromts, tots = url[20:].split('|')
			streams = self.telly.get_archive_video_link(int(ch), int(fromts), int(tots), __addon__.getSetting('enable_h265') == "true")
		else:
			streams = self.telly.get_video_link( url, __addon__.getSetting('enable_h265') == "true" )

		if streams == None:
			return None

		max_bitrate = __addon__.getSetting('max_bitrate')
		if 'Mbit' in max_bitrate:
			max_bitrate = int(max_bitrate.split(' ')[0]) * 1000
		else:
			max_bitrate = 100000
		
		for one in streams:
			if one['bitrate'] > max_bitrate:
				continue
			
			item = item.copy()
			item['url'] = one['url']
			item['quality'] = one['quality']
			result.append(item)
		
		if len(result) == 0:
			# no stream passed max bitrate setting - choose the worst one
			one = streams[-1]
			item = item.copy()
			item['url'] = one['url']
			item['quality'] = one['quality']
			result.append(item)
			
		if select_cb:
			return select_cb(result)
		
		return result
	