# -*- coding: utf-8 -*-
#
import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime, timedelta 
from datetime import date
import threading, traceback

import base64
from hashlib import md5

try:
	from urllib import quote
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from urllib.parse import quote

	def py2_encode_utf8( text ):
		return text
	
	def py2_decode_utf8( text ):
		return text

__debug_nr = 1

def writeDebugRequest(url, data, params, response ):
	global __debug_nr
	
	name = "/tmp/%03d_request_%s" % (__debug_nr, url[8:].replace('/','_'))
	
	with open(name, "w") as f:
		f.write( json.dumps({'data': data, 'params': params } ))

	name = "/tmp/%03d_response_%s" % (__debug_nr, url[8:].replace('/','_'))
	
	with open(name, "w") as f:
		f.write( json.dumps(response))
		
	__debug_nr += 1

############### init ################

def _log_dummy(message):
	print('[REBIT.TV]: ' + message )
	pass

class RebitTvCache:
	rebittv = None
	rebittv_init_params = None

	# #################################################################################################
	
	@staticmethod
	def get(username=None, password=None, device_name=None, data_dir=None, log_function=_log_dummy):
		if RebitTvCache.rebittv and RebitTvCache.rebittv_init_params == (username, password):
#			log_function("rebittv already loaded")
			pass
		else:
			RebitTvCache.rebittv = RebitTV(username, password, device_name, data_dir, log_function )
			RebitTvCache.rebittv_init_params = (username, password)
			log_function("New instance of rebit.tv initialised")
		
		return RebitTvCache.rebittv

class RebitTV:
	def __init__(self, username, password, device_name, data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self.device_name = device_name
		self.access_token = None
		self.access_token_life = 0
		self.refresh_token = None
		self.user_id = None
		self.client_id = None
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
		
		self.common_headers = {
			"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 OPR/92.0.0.0",
			"Origin": "https://rebit.tv",
			"Referer": "https://rebit.tv",
			'Accept-language': 'sk',
		}

		self.load_login_data()
		
		self.channels = {}
		self.channels_next_load = 0
		
		self.check_login()
		
	# #################################################################################################

	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}".format(self.password, self.username, self.device_name)
		return md5( data.encode('utf-8') ).hexdigest()
	
	# #################################################################################################
	
	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)
					
					if self.get_chsum() == login_data.get('checksum'):
						self.access_token = login_data['access_token']
						self.access_token_life = login_data['access_token_life']
						self.refresh_token = login_data['refresh_token']
						self.user_id = login_data['user_id']
						self.client_id = login_data['client_id']
						self.log_function("Login data loaded from cache")
					else:
						self.access_token = None
						self.access_token_life = 0
						self.refresh_token = None
						self.user_id = None
						self.client_id = None
						self.log_function("Not using cached login data - wrong checksum")
			except:
				self.access_token = None
		
	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				if self.access_token:
					# save access token
					with open(self.data_dir + '/login.json', "w") as f:
						data = {
							'access_token': self.access_token,
							'access_token_life': self.access_token_life,
							'refresh_token': self.refresh_token,
							'user_id': self.user_id,
							'client_id': self.client_id,
							'checksum': self.get_chsum()
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass
			
	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("REBIT.TV API ERROR: %s" % msg )
		raise Exception("REBIT.TV: %s" % msg)

	# #################################################################################################

	def call_api(self, url, method='AUTO', params=None, data=None, enable_retry=True, auth_header=True, pin_header=False ):
		err_msg = None
		
		log_file = url
		
		if not url.startswith('http'):
			url = 'https://bbxnet.api.iptv.rebit.sk/' + url

		headers = self.common_headers
				
		if auth_header:
			headers['authorization'] = "Bearer " + self.access_token
		else:
			if 'authorization' in headers:
				del headers['authorization']

		if pin_header:
			headers['x-child-lock-code'] = "0000"
			
		if method == 'AUTO':
			if data:
				method = 'POST'
			else:
				method = 'GET'

		if data:
			# convert data to json
			req_data = json.dumps(data, separators=(',', ':'))
			headers["Content-type"] = "application/json;charset=utf-8"
		else:
			req_data = None
		
		if self.client_id:
			headers["X-Television-Client-Id"] = self.client_id
		
		try:
			resp = requests.request( method, url, params=params, data=req_data, headers=headers )
			
			try:
				debug_resp_data = resp.json()
			except:
				debug_resp_data = {}
				
#			writeDebugRequest( url, data, params, debug_resp_data)
			
			if resp.status_code >= 200 and resp.status_code <= 210:
				try:
					if resp.status_code == 204:
						return {}
					
					ret = resp.json()
					
					if auth_header and enable_retry and (ret.get('code') == 403 or ret.get('message') == 'The access token is invalid.'):
						if enable_retry:
							old_access_token = self.access_token
							self.load_login_data()
							
							if old_access_token == self.access_token:
								# we don't have newer access_token, so try to re-login
								self.refresh_login()
								enable_retry = False
							
							return self.call_api( url, method, params, data, enable_retry, auth_header, pin_header )
					
					return ret

				except:
					self.log_function(traceback.format_exc())
					return {}
			else:
				try:
					err_msg = resp.json()['message']
				except:
					err_msg = "Neočekávaný návratový kód zo servera: %d" % resp.status_code
				
		except Exception as e:
			self.log_function(traceback.format_exc())
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "Rebit.tv error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError( "%s" % err_msg )

	# #################################################################################################

	def check_login(self):
		if self.access_token:
			if self.client_id:
				data = {
					'headers': {
						'X-Television-Client-ID': self.client_id
					}
				}
			else:
				data = None
				
			data = self.call_api('television/client/heartbeat', method='POST', data=data)

		if self.access_token and data == {}:
			return True
		else:
			if self.login():
				return True
		
		return False

	# #################################################################################################
	
	def login(self):
		data = {
			"username": self.username,
			"password": self.password
		}
		
		data = self.call_api('auth/auth', data=data, enable_retry=False, auth_header=False)
		
		if 'data' not in data:
			self.access_token = None
			self.refresh_token_token = None
			self.access_token_life = 0
			self.user_id = None
			self.save_login_data()
			self.showError("Problém pri prihlásení: %s" % data.get('message',''))
			return False
	
		data = data['data']
		self.access_token = data['access_token']
		self.access_token_life = int(time.time()) + int(data['expire_in'])
		self.refresh_token = data['refresh_token']
		self.user_id = data['user_id']
		self.save_login_data()
		
		return self.pair()
		
	# #################################################################################################
	
	def refresh_login(self):
		if not self.refresh_token:
			self.access_token = None
			return False
		
		self.access_token = self.refresh_token
		data = self.call_api('auth/auth', method='POST', enable_retry=False)
		
		if 'data' not in data:
			self.access_token = None
			self.refresh_token_token = None
			self.access_token_life = 0
			self.user_id = None
			self.save_login_data()
			self.showError("Problém pri obnove prihlasovacieho tokenu: %s" % data.get('message',''))
			return False
	
		data = data['data']
		self.access_token = data['access_token']
		self.access_token_life = int(time.time()) + int(data['expire_in'])
		self.refresh_token = data['refresh_token']
		self.user_id = data['user_id']
		self.save_login_data()
		
		return True

	# #################################################################################################
		
	def logout(self):
		if not self.refresh_token:
			self.access_token = None
			self.save_login_data()
			return True
		
		self.device_remove(self.client_id)
		
		self.call_api('auth/auth', method='DELETE', enable_retry=False)
		
		self.access_token = None
		self.refresh_token_token = None
		self.client_id = None
		self.save_login_data()
		
		return True
		
	# #################################################################################################
	
	def pair(self):
		data = {
			'title': self.device_name,
			'type': 'computer',
			'child-lock-code': '0000'
		}
		
		data = self.call_api('television/client', data=data)
		
		if 'data' not in data:
			self.showError("Problém pri párovaní zariadenia: %s" % data.get('message',''))
			return False
	
		data = data['data']
		self.client_id = data['id']
		self.save_login_data()
		
		return True
		
	# #################################################################################################

	def get_devices(self):
		if not self.check_login():
			return []
		
		data = self.call_api('television/clients')
		
		return data.get('data', [])

	# #################################################################################################

	def device_remove(self, client_id):
		if not self.check_login():
			return
		
		data = {
			'title': self.device_name,
			'type': 'computer',
			'child-lock-code': '0000'
		}

		self.call_api('television/clients/' + client_id, method='DELETE', data=data)
		
		if self.client_id == client_id:
			self.client_id = None

	# #################################################################################################

	def get_current_epg(self):
		data = self.call_api('television/programmes/current')
		
		epgdata = {}
		for ch in data.get('data',[]):
			epgdata[ch['channel_id']] = ch
			
		return epgdata
		
	# #################################################################################################

	def get_epg(self, channel_id, time_from, time_to ):
		time_from = datetime.utcfromtimestamp(time_from).strftime('%Y-%m-%dT%H:%M:%S.000Z')
		time_to = datetime.utcfromtimestamp(time_to).strftime('%Y-%m-%dT%H:%M:%S.000Z')
		
		params = {
			'filter[stop][ge]': time_from,
			'filter[start][le]': time_to
		}
		
		data = self.call_api('television/channels/' + channel_id + '/programmes', params=params )
		
		if 'data' not in data:
			self.showError("Problém s načítaním EPG: %s" % data.get('message',''))
			return []

		return sorted(data['data'], key=lambda x: x['start'])

	# #################################################################################################
	
	def get_channels(self, refresh_channels_data=False):
		if refresh_channels_data or not self.channels or self.channels_next_load < int(time.time()):
			data = self.call_api('television/channels' )
			
			if 'data' not in data:
				self.showError("Problém s načítaním zoznamu programov: %s" % data.get('message',''))
				return []
			
			channels = {}
			
			for channel in data['data']:
				
				channels[channel['id']] = {
					'id': str(channel['id']),
					'name': channel['title'],
					'slug': channel['slug'],
					'has_epg': channel['guide'],
					'adult': channel['protected'],
					'number': channel['channel'],
					'picon': channel.get('icon'),
					'timeshift': channel['archive'] if channel.get('archive') else 0
				}
			
				self.channels = channels
				self.channels_next_load = int(time.time()) + 3600
			
		return self.channels

	# #################################################################################################

	def get_channels_sorted(self, refresh_channels_data=False):
		self.get_channels(refresh_channels_data)
		
		result = []
		
		for ch in self.channels.values():
			result.append(ch)
		
		return sorted(result, key=lambda _channel: _channel['number'])

	# #################################################################################################
	
	def resolve_streams(self, url ):
		try:
			req = requests.get(url)
		except:
			self.log_function("%s" % traceback.format_exc())
			self.showError("Nastal problém pri načítení videa.")
			return None
		
		if req.status_code != 200:
			self.showError("Nastal problém pri načítení videa: http response code: %d" % req.status_code)
			return None

		res = []
		streams = []

		for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', req.text, re.MULTILINE):
			stream_info = {}
			for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
				key, val = info.split('=', 1)
				stream_info[key.lower()] = val
			
			stream_url = m.group('chunk')
			
			if not stream_url.startswith('http'):
				if stream_url.startswith('/'):
					stream_url = url[:url[9:].find('/') + 9] + stream_url
				else:
					stream_url = url[:url.rfind('/') + 1] + stream_url
				
			stream_info['url'] = stream_url
			streams.append( stream_info )
		
		return sorted(streams,key=lambda i: int(i['bandwidth']), reverse = True)
	
	# #################################################################################################

	def get_live_link(self, channel_key, event_id=None ):
		req_url = 'television/channels/' + channel_key + '/play'
		if event_id:
			req_url += '/' + event_id

		data = self.call_api(req_url, pin_header=True)
		
		if 'data' not in data:
			self.showError("Nastal problém so získaním adresy streamu: %s" % data.get('message',''))
			return None
		
		data = data['data']
		
		if 'protocol' in data and data['protocol'] != 'http-live-stream':
			self.showError("Nepodporovaný typ stream protokolu: %s" % data['protocol'])
			return None
		
		if 'quality' in data and data['quality'] == 'adaptive':
			return self.resolve_streams(data['link'].replace('https://', 'http://'))
		
		return [{ 'url': data['link'], 'resolution': '1280x720', 'bandwidth': 1}]

	# #################################################################################################
	