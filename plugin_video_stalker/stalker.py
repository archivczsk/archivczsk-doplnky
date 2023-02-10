# -*- coding: utf-8 -*-
import re,sys,os,string,base64,datetime,json,requests,traceback
from time import time, mktime
from datetime import datetime
import threading
import uuid
from hashlib import sha1, md5
from collections import OrderedDict

try:
	from urllib import quote
except:
	from urllib.parse import quote

try:
	from ConfigParser import ConfigParser
except:
	from configparser import ConfigParser

from tools_archivczsk.debug.http import dump_json_request

# #################################################################################################

def _log_dummy(message):
	print('[STALKER]: ' + message )
	pass

# #################################################################################################

def get_cache_key( portal_cfg ):
	values = []
	for key in ('url', 'mac', 'username', 'password', 'device_id', 'device_id2', 'signature', 'serial'):
		values.append( portal_cfg.get(key,'') )

	data = '|'.join(values)		
	return md5( data.encode('utf-8') ).hexdigest()

# #################################################################################################

class StalkerCache:
	portal_cache = {}

	# #################################################################################################
	
	@staticmethod
	def get(portal_cfg, data_dir=None, log_function=_log_dummy):
		key = get_cache_key( portal_cfg )
		
		if key not in StalkerCache.portal_cache:
			s = Stalker( portal_cfg, data_dir, log_function )
			StalkerCache.portal_cache[key] = s
			
		return StalkerCache.portal_cache[key]

	# #################################################################################################
	
	@staticmethod
	def get_by_key( key ):
		return StalkerCache.portal_cache.get(key)
	
	# #################################################################################################
	
	@staticmethod
	def load_portals_cfg():
		portals = []
		keys = ('url', 'mac', 'username', 'password', 'device_id', 'device_id2', 'signature', 'serial')
		
		def_values = {}
		for key in keys:
			def_values[key] = ''
			
		def_values['serial'] = '3'
		cp = ConfigParser(def_values)
		
		cp.read('/etc/stalker.conf')
		
		for s in cp.sections():
			portal_cfg = {}
			
			for key in keys:
				portal_cfg[key] = cp.get(s, key)
			
			if portal_cfg['url'] and portal_cfg['mac']:
				portal_cfg['url'] = portal_cfg['url'].lower()
				portal_cfg['name'] = s
				portals.append( (s, portal_cfg) )
		
		return portals

	
# #################################################################################################

class Stalker:
	def __init__(self, portal_cfg=None, data_dir=None, log_function=None ):
		url = portal_cfg['url']
		
		if not url.endswith('/'):
			url = url + '/'
		
		self.url = url
		self.mac = portal_cfg['mac']
		self.name = portal_cfg['name']
		self.portal_cfg = portal_cfg
		self.endpoint = 'server/load.php'
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
		self.channel_list = None
		self.channel_list_load_time = 0
		self.epg = None
		self.epg_load_time = 0
		self.access_token = None
		self.access_token_checked = False
		self.lang = "en_GB.utf8"
#		self.lang = "en"
		self.time_zone = "Europe/Berlin"
		self.user_agent = 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3'
		self.load_login_data()
		
	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("Stalker API ERROR: %s" % msg )
		raise Exception("Stalker: %s" % msg)
	
	# #################################################################################################
	
	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)
					
					ck = get_cache_key( self.portal_cfg )
					
					self.access_token = login_data.get(ck)
					
					if self.access_token:
						self.log_function("Login data loaded from cache")
					else:
						self.log_function("Login data not found in cache")
			except:
				pass
		
	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				# load all login data
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)
			except:
				login_data = {}
			
			ck = get_cache_key( self.portal_cfg )
			
			if self.access_token:
				# save access token to cache file
				login_data[ck] = self.access_token
			else:
				# remove access token from cache file
				if ck in login_data:
					del login_data[ck]
			
			# save access token
			with open(self.data_dir + '/login.json', "w") as f:
				json.dump( login_data, f )

	# #################################################################################################
	
	def load_epg_data(self):
		if self.data_dir:
			try:
				ck = get_cache_key( self.portal_cfg )
				name = self.data_dir + '/' + ck + '.epg'
				
				with open(name, "r") as f:
					self.epg = json.load(f)
					
				self.epg_load_time = os.path.getmtime(name)
			except:
				pass
			
	# #################################################################################################

	def save_epg_data(self):
		if self.data_dir:
			ck = get_cache_key( self.portal_cfg )
			name = self.data_dir + '/' + ck + '.epg'
			
			try:
				os.remove( name )
			except:
				pass
			
			with open(name, "w") as f:
				json.dump(self.epg, f)
			
	# #################################################################################################
    
	def call_stalker_api(self, params=None, auth_header=True ):
		err_msg = None

		url = self.url
		if url.endswith('/c/'):
			url = url[:-2]
		
		url = url + self.endpoint
		
		headers = {
			"Cookie" : "mac=%s; stb_lang=%s, timezone=%s" % (quote(self.mac), self.lang, quote(self.time_zone)),
			"User-Agent": self.user_agent,
			"X-User-Agent": "Model: MAG250; Link: WiFi",
			'Accept-Encoding': 'gzip',
			'Referer': self.url
		}
		
		if auth_header:
			headers['Authorization'] = "Bearer " + self.access_token

		try:
			resp = requests.get( url, params=params, headers=headers )
#			dump_json_request(resp)

			if resp.status_code == 200:
				try:
					return resp.json().get('js',{})
				except:
					return None
			else:
				err_msg = "Neočekávaný návratový kód zo servera: %d" % resp.status_code
				self.log_function( "HTTP %d: %s" % (resp.status_code, resp.text) )
				
		except Exception as e:
			self.log_function("Stalker ERROR:\n"+traceback.format_exc())
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "Stalker error for URL %s: %s" % (url, traceback.format_exc()))
			self.log_function( "Stalker: %s" % err_msg )
			self.showError( "%s" % err_msg )

		return None
	
	# #################################################################################################
	
	def need_handshake(self):
		if self.access_token:
			if self.access_token_checked:
				return False
			
			#check if access token is still valid
			try:
				params = {
					'type': 'account_info',
					'action': 'get_main_info',
					'mac': self.mac,
#					'JsHttpRequest': '1-xml'
				}
				
				ret = self.call_stalker_api(params)
				self.log_function("Account info response: %s" % str(ret) )
				
				if ret != None:
					self.access_token_checked = True
					return False
				
			except Exception as e:
				pass

		return True
	
	# #################################################################################################
	
	def do_handshake(self):
		
		# do handshake
		params = {
			'type': 'stb',
			'action': 'handshake',
			'token': '',
#			'JsHttpRequest': '1-xml'
		}
		
		ret = self.call_stalker_api( params, False)
		
		if ret:
			self.access_token = ret.get('token')
			if self.access_token:
				# second login step
				self.get_profile(True)
			
				if self.portal_cfg.get('username') and self.portal_cfg.get('password'):
					ret = self.do_auth()
					
				self.save_login_data()
				
				if self.need_handshake():
					return False
				else:
					return True

		return False
		
	# #################################################################################################
	
	def get_profile(self, auth_second_step=False):
		params = {
			'type': 'stb',
			'action': 'get_profile',
			"stb_type" : "MAG250",
			"ver" : "ImageDescription: 0.2.16-250; " \
					"ImageDate: 18 Mar 2013 19:56:53 GMT+0200; " \
					"PORTAL version: 4.9.9; " \
					"API Version: JS API version: 328; " \
					"STB API version: 134; " \
					"Player Engine version: 0x566",
			"device_id" : self.portal_cfg.get('device_id', ''), #optional
			"device_id2" : self.portal_cfg.get('device_id2', ''), #optional
			"signature" : self.portal_cfg.get('signature', ''), #optional
			"not_valid_token" : False, #required
			"auth_second_step" : auth_second_step, #required
			"hd" : True, #required
			"num_banks" : 1, #required
			"image_version" : 216, #required
			"hw_version" : "1.7-BD-00", #required
			"sn": self.portal_cfg.get('serial', 3),
		}
		
		ret = self.call_stalker_api( params )
		
	# #################################################################################################
	
	def do_auth(self):
		params = {
			'type': 'stb',
			'action': 'do_auth',
			'login': self.portal_cfg['username'],
			'password': self.portal_cfg['password'],
			'device_id' : self.portal_cfg.get('device_id', ''), # optional
			'device_id2' : self.portal_cfg.get('device_id2', ''), # optional
		}

		return self.call_stalker_api( params )

	# #################################################################################################

	def get_modules(self):
		if self.need_handshake():
			return None
		
		params = {
			'type': 'stb',
			'action': 'get_modules',
		}

		ret = self.call_stalker_api( params )
		
		modules = ret.get('all_modules', [])
		
		for m in ret.get('disabled_modules', []):
			try:
				modules.remove(m)
			except:
				pass

		return modules
		
	# #################################################################################################
	
	def get_all_channels(self):
		if self.need_handshake():
			return None
		
		params = {
			'type': 'itv',
			'action': 'get_all_channels',
		}
	
		return self.call_stalker_api( params ).get('data')
	
	# #################################################################################################
	
	def get_genres(self):
		if self.need_handshake():
			return None
		
		params = {
			'type': 'itv',
			'action': 'get_genres',
		}

		return self.call_stalker_api( params )
	
	# #################################################################################################
	
	def get_channels_grouped(self, force_reload=False):
		if force_reload:
			channel_cache_life = 0
		else:
			channel_cache_life = 3600
		
		if not self.channel_list or (int(time()) - self.channel_list_load_time) > channel_cache_life:
			genres = {}
			for genre in self.get_genres():
				try:
					genre_id = int(genre['id'])
				except:
					continue
				
				genres[genre['id']] = genre['title']
			
			
			channels = OrderedDict()
			
			for channel in self.get_all_channels():
				group_id = channel.get('tv_genre_id')
				
				if group_id:
					group_name = genres.get(group_id)
				else:
					group_name = None
					
				if not group_name:
					group_name = 'Nezaradene'
					
				if group_name not in channels:
					channels[group_name] = []
					
				try:
					use_tmp_link = int(channel['use_http_tmp_link'])
					use_tmp_link = True if use_tmp_link == 1 else False
				except:
					use_tmp_link = False
					
					
				channels[group_name].append( {
					'id': channel['id'],
					'title': str(channel['name']),
					'cmd': channel['cmd'],
					'use_tmp_link': use_tmp_link,
					'img': channel['logo']
				})
			
			self.channel_list = channels
			self.channel_list_load_time = int(time())
			
		return self.channel_list
			
	# #################################################################################################
	
	def create_video_link(self, cmd, link_type='itv', series=None ):
		if self.need_handshake():
			return None
		
		params = {
			'type': link_type,
			'action': 'create_link',
			"cmd" : cmd, #required
			"forced_storage" : "undefined", #optional
			"disable_ad" : 0, #optional
		}

		if series:
			params['series'] = series
			
		ret = self.call_stalker_api( params )
		
		return self.cmd_to_url(ret.get('cmd'))
		
	# #################################################################################################
	
	def cmd_to_url(self, cmd):
		url = None
		if cmd:
			cmd = str(cmd).split(' ')
			if len(cmd) > 1:
				url = cmd[1]
			else:
				url = cmd[0]
				
		return url
		
	# #################################################################################################
	
	def get_epg_info(self, period=1 ):
		if self.need_handshake():
			return None
		
		params = {
			'type': 'itv',
			'action': 'get_epg_info',
			"period" : period
		}

		ret = self.call_stalker_api( params )

		return ret.get('data',{})

	# #################################################################################################
	
	def get_utc_offset(self):
		ts = int(time())
		utc_offset = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
		
		return int( utc_offset.total_seconds() )
	
	# #################################################################################################
	
	def fill_epg_cache(self):
		epg_cache_hours = 12
		
		if self.epg == None:
			self.load_epg_data()
		
		if self.epg != None and int(time()) < self.epg_load_time + (epg_cache_hours*3600):
			return
		
		self.epg = {}
		utc_offset = 0
#			utc_offset = self.get_utc_offset()
		
		epg_info = self.get_epg_info(epg_cache_hours)
		if len(epg_info) > 0:
			for epg_id, epg_list in epg_info.items():
				el = []
				
				for epg_data in epg_list:
					el.append({
						'from': epg_data['start_timestamp'] - utc_offset,
						'to': epg_data['stop_timestamp'] - utc_offset,
						'title': epg_data['name'],
						'desc': epg_data['descr']
					})
				
#					self.log_function("Saving %d epg entires for channel %s" % (len(el), epg_id))
				self.epg[epg_id] = el
		self.epg_load_time = int(time())
		self.save_epg_data()
	
	# #################################################################################################
	
	def clean_epg_cache(self):
		self.epg = None
		self.epg_load_time = 0
		
	# #################################################################################################

	def get_channel_current_epg(self, ch_id):
		if self.need_handshake():
			return None
		
		epg_data = self.epg.get(ch_id, [])
		self.log_function("%d epg data found for channel %s" % (len(epg_data), ch_id))
		
		cur_time = int(time())
		
		for epg_item in epg_data:
			self.log_function("%d - %d - %s" % (epg_item['from'], epg_item['to'], epg_item['title']))
			if cur_time > epg_item['from'] and cur_time < epg_item['to']:
				return epg_item
		
		return None
			
	# #################################################################################################
	
	def get_categories(self, type='vod'):
		if self.need_handshake():
			return None
		
		params = {
			'type': type,
			'action': 'get_categories',
		}

		return self.call_stalker_api( params )
	
	# #################################################################################################
	
	def get_vod_list(self, type='vod', cat_id=0, movie_id=0, season_id=0, episode_id=0, page=0, sortby='added'):
		if self.need_handshake():
			return None
		
		params = {
			'type': type,
			'action': 'get_ordered_list',
			'category': cat_id,
			'movie_id': movie_id,
			'season_id': season_id,
			'episode_id': episode_id,
			'p': page,
			'sortby': sortby # added, name, rating
		}

		return self.call_stalker_api( params )
	
	# #################################################################################################
