# -*- coding: utf-8 -*-

import sys, os, traceback

import requests
import base64

from Plugins.Extensions.archivCZSK.engine import client
from datetime import datetime
from datetime import timedelta
import time
import json
from stalker import StalkerCache, get_cache_key
from binascii import crc32

# #################################################################################################

portal_supported_modules = [
	('tv', 'Live TV'),
	('vclub', 'Video club'),
	('sclub', 'Series club')
]

# #################################################################################################

def _e( data ):
	return base64.b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')

def _d( data ):
	return json.loads(base64.b64decode(data.encode('utf-8')).decode('utf-8'))

class stalkerHttpProvider():
	
	def __init__(self, endpoint, data_dir=None):
		self.data_dir = data_dir
		self.endpoint = endpoint
		self.max_items_per_page = 200
		
	# #################################################################################################
	
	def dir_item(self, name, url ):
		return '<a href="{endpoint}/list/{item_url}">{item_name}</a><br>'.format(endpoint=self.endpoint, item_url=url, item_name=name)
		
	# #################################################################################################

	def video_item(self, name, url ):
		return '<a href="{endpoint}/playlive/{item_url}.m3u8">{item_name}</a><br>'.format(endpoint=self.endpoint, item_url=url, item_name=name)

	# #################################################################################################

	def playlist_item(self, name, url, group=None, logo=None ):
		if group:
			group = ' group-title="%s"' % group
		else:
			group = ''
			
		if logo:
			logo = ' tvg=logo="%s"' % logo
		else:
			logo = ''
		
		return '#EXTINF:-1{logo}{group} tvg-name="{name}",{name}\n{endpoint}/playlive/{url}'.format(name=name, group=group, logo=logo, url=url, endpoint=self.endpoint)
		
	# #################################################################################################

	def handle_html(self, url ):
		if url == '':
			return self.categories()
		elif url.startswith('list/'):
			return self.list( url[5:] )
		else:
			return None
		
	# #################################################################################################

	def handle_m3u8(self, url ):
		if url.startswith('list/'):
			return self.list_m3u8( url[5:] )
		else:
			return None, None
		
	# #################################################################################################
	
	
	def categories(self):
		try:
			portals = StalkerCache.load_portals_cfg()
		except Exception as e:
			portals = []

		result = []
		
		if len(portals) > 0:		
			for portal in portals:
				result.append(self.dir_item(portal[0], "portal_root/" + _e(portal[1]) ))
			
		return result

	# #################################################################################################

	def list(self, url):
		if url.startswith('portal_root/'):
			return self.show_portal_root(url[12:])
		elif url.startswith('portal_module/'):
			return self.show_portal_module(url[14:])
		elif url.startswith('portal_tv_group/'):
			return self.show_portal_tv_group(url[16:])
		elif url.startswith('portal_vod_cat/'):
			return self.show_portal_vod_category(url[15:])
		elif url.startswith('portal_series_cat/'):
			return self.show_portal_series_category(url[18:])
		elif url.startswith('portal_series/'):
			return self.show_portal_series(url[14:])
		elif url.startswith('portal_episodes/'):
			return self.show_portal_episodes(url[16:])

		return None

	# #################################################################################################
	
	def list_m3u8(self, url):
		if url.startswith('portal_tv_group/'):
			return self.show_portal_tv_group_m3u8(url[16:])
		elif url.startswith('portal_vod_cat/'):
			return self.show_portal_vod_category_m3u8(url[15:])
		elif url.startswith('portal_series/'):
			return self.show_portal_series_m3u8(url[14:])

		return None, None

	# #################################################################################################
	
	def show_portal_root(self, url ):
		portal_cfg = _d(url)
		
		s = StalkerCache.get( portal_cfg, self.data_dir, client.log.info )
		
		if s.need_handshake():
			if s.do_handshake() == False:
				return '<html><h2>Login to portal failed!</h2></html>'
		
		ck = get_cache_key( portal_cfg )
		
		portal_modules = s.get_modules()
		
		result = []
		for module in portal_supported_modules:
			if module[0] in portal_modules:
				item = self.dir_item(module[1], 'portal_module/' + _e([ck, module[0], 'number']) )

				result.append(item)
		
		return result
	
	# #################################################################################################
	
	def show_portal_module(self, url ):
		ck, module, sortby = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []

		if module == 'tv':
			result.append(self.dir_item('Stiahnuť kompletný playlist', 'portal_tv_group/' + _e( [ck, None, 'number'] ) + '.m3u8'))
			result.append('<br>')

			for group_name in s.get_channels_grouped():
				item = self.dir_item(group_name, 'portal_tv_group/' + _e( [ck, group_name, 'number'] ) )
				result.append(item)
		elif module == 'vclub':
			for cat in s.get_categories('vod'):
				item = self.dir_item(cat['title'], 'portal_vod_cat/' + _e( [ck, cat['id'], 1, 'added', cat['title']] ) )
				result.append(item)
			
		elif module == 'sclub':
			for cat in s.get_categories('series'):
				item = self.dir_item(cat['title'], 'portal_series_cat/' + _e( [ck, cat['id'], 1, 'added'] ) )
				result.append(item)
		
		return result

	# #################################################################################################
		
	def show_portal_tv_group_m3u8(self, url ):
		ck, group_name, sortby = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		if group_name:
			group_names = [ group_name ]
			file_name = 'LiveTV_' + group_name
		else:
			group_names = [ g for g in s.get_channels_grouped() ]
			file_name = 'LiveTV'
		
		result = []
		for group_name in group_names:
			for channel in s.get_channels_grouped()[group_name]:
				item = self.playlist_item(channel['title'], _e( [ck, channel['cmd'], channel['use_tmp_link'], 'itv', channel['title'], -1] ), group_name, channel['img'])
				result.append(item)
	
		return result, '%s_%s' % (s.name, file_name)

	# #################################################################################################
	
	def show_portal_tv_group(self, url ):
		ck, group_name, sortby = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		result.append(self.dir_item('Stiahnuť kompletný playlist', 'portal_tv_group/' + url + '.m3u8'))
		result.append('<br>')
		
		for channel in s.get_channels_grouped()[group_name]:
			item = self.video_item(channel['title'], _e( [ck, channel['cmd'], channel['use_tmp_link'], 'itv', channel['title'], -1] ) )
			result.append(item)
	
		return result
	
	# #################################################################################################

	def show_portal_vod_category_m3u8(self, url ):
		ck, cat_id, page, sortby, title = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []

		while True:
			vod_data = s.get_vod_list('vod', cat_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.playlist_item(vod_item['name'], _e( [ck, vod_item['cmd'], True, 'vod', vod_item['name'], -1] ))
				result.append(item)
		
			if vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1
			
		return result, '%s_VOD_%s' % (s.name, title)
	
	# #################################################################################################
	
	def show_portal_vod_category(self, url ):
		ck, cat_id, page, sortby, title = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		result.append(self.dir_item('Stiahnuť kompletný playlist', 'portal_vod_cat/' + url + '.m3u8'))
		result.append('<br>')

		i = 0
		while True:
			vod_data = s.get_vod_list('vod', cat_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.video_item(vod_item['name'], _e( [ck, vod_item['cmd'], True, 'vod', vod_item['name'], -1] ) )
				result.append(item)
				i += 1
		
			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1
			
		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', 'portal_vod_cat/' + _e( [ck, cat_id, page + 1, sortby] ) )
			result.append(item)
			
		return result
	
	# #################################################################################################

	def show_portal_series_category(self, url ):
		ck, cat_id, page, sortby = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		
		i = 0
		while True:
			vod_data = s.get_vod_list('series', cat_id, page=page, sortby=sortby)

			for vod_item in vod_data['data']:
				item = self.dir_item(vod_item['name'], 'portal_series/' + _e( [ck, cat_id, vod_item['id'], 1, 'added', vod_item['name']] ) )
				result.append(item)

			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1

		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', 'portal_series_cat/' + _e( [ck, cat_id, page + 1, sortby] ) )
			result.append(item)
		
		return result
	
	# #################################################################################################

	def show_portal_series_m3u8(self, url ):
		ck, cat_id, vod_id, page, sortby, title = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []

		while True:
			vod_data = s.get_vod_list('series', cat_id, vod_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				for e in vod_item['series']:
					episode_name = vod_item['name'] + ' Episode ' + str(e)
					item = self.playlist_item(episode_name, _e( [ck, vod_item['cmd'], True, 'vod', episode_name, e] ), vod_item['name'])
					result.append(item)

			if vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1

		return result, '%s_SERIES_%s' % (s.name, title)
	
	# #################################################################################################

	def show_portal_series(self, url ):
		ck, cat_id, vod_id, page, sortby, title = _d(url)
		
		s = StalkerCache.get_by_key( ck )
		
		result = []
		result.append(self.dir_item('Stiahnuť kompletný playlist', 'portal_series/' + url + '.m3u8'))
		result.append('<br>')

		i = 0
		while True:
			vod_data = s.get_vod_list('series', cat_id, vod_id, page=page, sortby=sortby)
			
			for vod_item in vod_data['data']:
				item = self.dir_item(vod_item['name'], 'portal_episodes/' + _e( [ck, vod_item['cmd'], vod_item['series'], vod_item['name']] ) )
				result.append(item)
				
			if i > self.max_items_per_page or vod_data['max_page_items'] * page >= vod_data['total_items']:
				break
			
			page += 1

		if vod_data['max_page_items'] * page < vod_data['total_items']:
			item = self.dir_item('Ďalšie', 'portal_series/' + _e( [ck, cat_id, vod_id, page + 1, sortby] ) )
			result.append(item)
		
		return result
	
	# #################################################################################################

	def show_portal_episodes(self, url ):
		ck, cmd, series, title = _d(url)
		
		result = []
		
		for s in series:
			episode_name = title + ' Episode ' + str(s)
			item = self.video_item(episode_name, _e( [ck, cmd, True, 'vod', episode_name, s] ) )
			result.append(item)

		return result
	
# #################################################################################################
