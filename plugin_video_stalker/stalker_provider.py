# -*- coding: utf-8 -*-

import sys, os, traceback

import requests
import base64

try:
	from urllib.parse import quote
	is_py3 = True
except:
	from urllib import quote
	is_py3 = False
	
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Plugins.Extensions.archivCZSK.engine import client

import util
from provider import ContentProvider
import xbmcprovider
from datetime import datetime
from datetime import timedelta
import time
import json
from stalker import StalkerCache, get_cache_key
from Plugins.Extensions.archivCZSK.engine.tools.bouquet_generator import BouquetGeneratorTemplate
from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
from binascii import crc32

######### contentprovider ##########

__scriptid__ = 'plugin.video.stalker'
addon = ArchivCZSK.get_xbmc_addon(__scriptid__)


class StalkerBouquetGenerator(BouquetGeneratorTemplate):
	def __init__(self, name):
		# configuration to make this class little bit reusable also in other addons
		self.prefix = name.replace(' ', '_').replace(':', '').lower()
		self.name = name
		self.sid_start = 0xB000
		self.tid = 10
		self.onid = 1
		self.namespace = 0xE000000 + crc32(name.encode('utf-8')) & 0xFFFFFF
		BouquetGeneratorTemplate.__init__(self, archivCZSKHttpServer.getAddonEndpoint(__scriptid__))

# #################################################################################################

portal_supported_modules = [
	('tv', 'Live TV'),
	('vclub', 'Video club'),
	('sclub', 'Series club')
]

# #################################################################################################

class stalkerContentProvider(ContentProvider):
	
	def __init__(self, data_dir=None, session=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'stalker', '/', None, None, None, tmp_dir)
		self.data_dir = data_dir
		self.max_items_per_page = 200
		
#		from Plugins.Extensions.archivCZSK.engine.httpserver import archivCZSKHttpServer
#		self.http_endpoint = archivCZSKHttpServer.getAddonEndpoint( __scriptid__ )

	# #################################################################################################

	def capabilities(self):
		return ['login', 'categories', 'resolve', '!download']
	
	# #################################################################################################
	
#	def encode_url( self, url, prefix="" ):
#		if url.startswith("http"):
#			return self.http_endpoint + "/getm3u8/" + prefix + base64.b64encode( url.encode("utf-8") ).decode("utf-8")
#		else:
#			return url

	# #################################################################################################

	def login(self):
		return True
	
	# #################################################################################################
	
	def save_example_config(self):
		if not os.path.exists( '/etc/stalker.conf' ):
			with open('/etc/stalker.conf', 'w') as f:
				f.write( '# Priklad konfiguracie\n' \
						'# [Skvely portal]\n' \
						'# url=http://url_k_portalu.com:port\n' \
						'# mac=00:1a:79:xx:xx:xx\n' \
						'#\n' \
						'# [Este lepsi portal]\n' \
						'# url=http://url_k_portalu2.com:port/c\n' \
						'# mac=00:1a:79:xx:xx:xx\n'
				)
	
	# #################################################################################################
	
	def categories(self):
		result = []
		
		try:
			portals = StalkerCache.load_portals_cfg()
		except Exception as e:
			client.log.error('Error by reading stalker config file:\n' + str(e))
			client.showError('Konfiguračný súbor /etc/stalker.conf má nesprávny formát:\n' + str(e))
			return result

		if len(portals) > 0:		
			for portal in portals:
				result.append(self.dir_item(portal[0], "#portal_root#" + json.dumps( portal[1] ) ) )
		else:
			self.save_example_config()
			item = self.video_item('#')
			item['title'] = '[COLOR red]Nakonfigurujte prístupové údaje v /etc/stalker.conf![/COLOR]'
			result.append(item)
			
		return result

	# #################################################################################################

	def list(self, url):
		try:
			if url.startswith('#portal_root#'):
				return self.show_portal_root(url[13:])
			elif url.startswith('#portal_module#'):
				return self.show_portal_module(url[15:])
			elif url.startswith('#portal_tv_group#'):
				return self.show_portal_tv_group(url[17:])
			elif url.startswith('#portal_vod_cat#'):
				return self.show_portal_vod_category(url[16:])
			elif url.startswith('#portal_series_cat#'):
				return self.show_portal_series_category(url[19:])
			elif url.startswith('#portal_series#'):
				return self.show_portal_series(url[15:])
			elif url.startswith('#portal_episodes#'):
				return self.show_portal_episodes(url[17:])
			elif url.startswith('#create_userbouquet#'):
				return self.create_userbouquet(url[20:])
		except Exception as e:
			client.log.error("Stalker Addon ERROR:\n%s" % traceback.format_exc())
		
			if "Stalker: " in str(e):
				client.add_operation('SHOW_MSG', { 'msg': str(e), 'msgType': 'error', 'msgTimeout': 0, 'canClose': True, })
				item = self.video_item('#')
				item['title'] = "%s" % str(e)
				return [ item ]
			else:
				raise

		return []

	# #################################################################################################
	
	def show_portal_root(self, url ):
		portal_cfg = json.loads(url)
		
		s = StalkerCache.get( portal_cfg, self.data_dir, client.log.info )
		
		if s.need_handshake():
			if s.do_handshake() == False:
				item = self.video_item('#')
				item['title'] = '[COLOR red]Prihlásenie zlyhalo![/COLOR]'
				return [ item ]
		
		ck = get_cache_key( portal_cfg )
		
		portal_modules = s.get_modules()
		
		result = []
		for module in portal_supported_modules:
			if module[0] in portal_modules:
				item = self.dir_item(module[1], '#portal_module#' + json.dumps( [ck, module[0], 'number'] ) )
				
				if module[0] == 'tv':
					item['menu'] = {
						'Vytvoriť userbouquet': { 'list': '#create_userbouquet#' + json.dumps( [ck, ''] ) },
					}

				result.append(item)
		
		return result
	
	# #################################################################################################
	
	def show_portal_module(self, url ):
		ck, module, sortby = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []

		if module == 'tv':
			for group_name in s.get_channels_grouped():
				item = self.dir_item(group_name, '#portal_tv_group#' + json.dumps( [ck, group_name, 'number'] ) )
				
				if sortby == 'number':
					item['menu'] = {
						'Zoradiť podľa názvu': { 'list': '#portal_module#' + json.dumps( [ck, module, 'title'] ) },
						'Vytvoriť userbouquet': { 'list': '#create_userbouquet#' + json.dumps( [ck, group_name] ) },
					}
				elif sortby == 'title':
					item['menu'] = {
						'Zoradiť podľa čísla': { 'list': '#portal_module#' + json.dumps( [ck, module, 'number'] ) },
						'Vytvoriť userbouquet': { 'list': '#create_userbouquet#' + json.dumps( [ck, group_name] ) },
					}

				result.append(item)
			
			if sortby == 'title':
				result.sort(key=lambda x: x['title'])
				
		elif module == 'vclub':
			for cat in s.get_categories('vod'):
				item = self.dir_item(cat['title'], '#portal_vod_cat#' + json.dumps( [ck, cat['id'], 1, 'added'] ) )
				result.append(item)
			
		elif module == 'sclub':
			for cat in s.get_categories('series'):
				item = self.dir_item(cat['title'], '#portal_series_cat#' + json.dumps( [ck, cat['id'], 1, 'added'] ) )
				result.append(item)
		
		return result

	# #################################################################################################
		
	def create_userbouquet(self, url ):
		ck, group_name = json.loads(url)

		player_name = addon.getSetting('player_name')
		s = StalkerCache.get_by_key( ck )

		channels_grouped = s.get_channels_grouped()

		if group_name:
			groups = [ group_name ]
		else:
			groups = [ g for g in channels_grouped.keys() ]
				
		channels = []
		for g in groups:
			for channel in channels_grouped[g]:
				channels.append({
					'id': int(channel['id']),
					'key': json.dumps( [ ck, channel['cmd'], channel['use_tmp_link'] ] ),
					'name': channel['title'],
					'adult': False,
					'picon': None
				})
		
		if group_name:
			bq_name = '%s: %s' % (s.portal_cfg['name'], group_name)
		else:
			bq_name = '%s: %s' % (s.portal_cfg['name'], 'Live TV')
		
		bq_name = bq_name.replace('"','').replace("'",'').replace('/','')
		
		bg = StalkerBouquetGenerator(bq_name)
		bg.generate_bouquet(channels, player_name=player_name, user_agent=s.user_agent)
		
		item = self.video_item('#')
		item['title'] = '[COLOR yellow]Userbouquet %s vygenerovaný![/COLOR]' % bq_name

		return [ item ]

	# #################################################################################################
	
	def show_portal_tv_group(self, url ):
		ck, group_name, sortby = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		if addon.getSetting('enable_epg') == 'true':
			s.fill_epg_cache()

		result = []
		for channel in s.get_channels_grouped()[group_name]:
			epg = s.get_channel_current_epg(channel['id'])
			
			item = self.video_item('#portal_link#' + json.dumps( [ck, channel['cmd'], channel['use_tmp_link']] ) )
			item['title'] = channel['title']
			item['img'] = channel['img']
			
			if epg:
				item['title'] = item['title'] + ' [COLOR yellow]' + epg['title'] + '[/COLOR]'
				item['plot'] = '[' + datetime.fromtimestamp(epg['from']).strftime("%H:%M") + ' - ' + datetime.fromtimestamp(epg['to']).strftime("%H:%M") + ']\n' + epg['desc']
			
			if sortby == 'number':
				item['menu'] = {
					'Zoradiť podľa názvu': { 'list': '#portal_tv_group#' + json.dumps( [ck, group_name, 'title'] ) },
				}
			elif sortby == 'title':
				item['menu'] = {
					'Zoradiť podľa čísla': { 'list': '#portal_tv_group#' + json.dumps( [ck, group_name, 'number'] ) },
				}
	
			result.append(item)
	
		if sortby == 'title':
			result.sort(key=lambda x: x['title'])
	
		s.clean_epg_cache()
		return result
	
	# #################################################################################################

	def show_portal_vod_category(self, url ):
		ck, cat_id, page, sortby = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []

		i = 0
		while True:
			vod_data = s.get_vod_list('vod', cat_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.video_item('#portal_vod_link#' + json.dumps( [ck, vod_item['cmd'], -1] ) )
				item['title'] = vod_item['name']
				item['plot'] = vod_item['description']
				item['img'] = vod_item['screenshot_uri']
				
				if not item['img'].startswith('http'):
					item['img'] = ''
				
				if sortby == 'added':
					item['menu'] = {
						'Zoradiť podľa názvu': { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'name'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'rating'] ) }
					}
				elif sortby == 'name':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'added'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'rating'] ) }
					}
				elif sortby == 'rating':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'added'] ) },
						'Zoradiť podľa názvu': { 'list': '#portal_vod_cat#' + json.dumps( [ck, cat_id, 1, 'name'] ) },
					}
				
				result.append(item)
				i += 1
		
			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1
			
		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', '#portal_vod_cat#' + json.dumps( [ck, cat_id, page + 1, sortby] ) )
			item['type'] = 'next'
			result.append(item)
			
		return result
	
	# #################################################################################################

	def show_portal_series_category(self, url ):
		ck, cat_id, page, sortby = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		
		i = 0
		while True:
			vod_data = s.get_vod_list('series', cat_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.dir_item(vod_item['name'], '#portal_series#' + json.dumps( [ck, cat_id, vod_item['id'], 1, 'added'] ) )
				item['plot'] = vod_item['description']
				item['img'] = vod_item['screenshot_uri']
	
				if not item['img'].startswith('http'):
					item['img'] = ''
	
				if sortby == 'added':
					item['menu'] = {
						'Zoradiť podľa názvu': { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'name'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'rating'] ) }
					}
				elif sortby == 'name':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'added'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'rating'] ) }
					}
				elif sortby == 'rating':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'added'] ) },
						'Zoradiť podľa názvu': { 'list': '#portal_series_cat#' + json.dumps( [ck, cat_id, 1, 'name'] ) },
					}
	
				result.append(item)

			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1

		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', '#portal_series_cat#' + json.dumps( [ck, cat_id, page + 1, sortby] ) )
			item['type'] = 'next'
			result.append(item)
		
		return result
	
	# #################################################################################################

	def show_portal_series(self, url ):
		ck, cat_id, vod_id, page, sortby = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		
		i = 0
		while True:
			vod_data = s.get_vod_list('series', cat_id, vod_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.dir_item(vod_item['name'], '#portal_episodes#' + json.dumps( [ck, vod_item['cmd'], vod_item['series']] ) )
				item['plot'] = vod_item['description']
				item['img'] = vod_item['screenshot_uri']
				
				if not item['img'].startswith('http'):
					item['img'] = ''
	
				if sortby == 'added':
					item['menu'] = {
						'Zoradiť podľa názvu': { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'name'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'rating'] ) }
					}
				elif sortby == 'name':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'added'] ) },
						'Zoradiť podľa hodnotenia': { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'rating'] ) }
					}
				elif sortby == 'rating':
					item['menu'] = {
						'Zoradiť podľa dátumu pridania' : { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'added'] ) },
						'Zoradiť podľa názvu': { 'list': '#portal_series#' + json.dumps( [ck, cat_id, vod_id, 1, 'name'] ) },
					}
					
				result.append(item)
				
			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1


		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', '#portal_series#' + json.dumps( [ck, cat_id, vod_id, page + 1, sortby] ) )
			item['type'] = 'next'
			result.append(item)
		
		return result
	
	# #################################################################################################

	def show_portal_episodes(self, url ):
		ck, cmd, series = json.loads(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		
		for s in series:
			item = self.video_item('#portal_vod_link#' + json.dumps( [ck, cmd, s] ) )
			item['title'] = 'Epizóda ' + str(s)
			result.append(item)

		return result
	
	# #################################################################################################

	def resolve(self, item, captcha_cb=None, select_cb=None):
		url = item["url"]

		if url == '#':
			return None
		
		if url.startswith('#portal_link#'):
			ck, cmd, use_tmp_link = json.loads(url[13:])
			s = StalkerCache.get_by_key( ck )

			try:
				if use_tmp_link:
					url = s.create_video_link( cmd )
				else:
					url = s.cmd_to_url( cmd )
			except Exception as e:
				client.add_operation('SHOW_MSG', { 'msg': 'Chyba pri prehrávaní:\n' + str(e), 'msgType': 'error', 'msgTimeout': 3, 'canClose': True, })
				return None
			
			item['url'] = url
		elif url.startswith('#portal_vod_link#'):
			ck, cmd, series = json.loads(url[17:])
			s = StalkerCache.get_by_key( ck )
		
			if series == -1:
				series = None
				
			url = s.create_video_link( cmd, 'vod', series=series )
			
			item['url'] = url
		
		item['playerSettings'] = { 'user-agent' : s.user_agent }
		
		return item

# #################################################################################################
