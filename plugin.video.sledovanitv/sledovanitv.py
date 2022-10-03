# -*- coding: utf-8 -*-
#
import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime, timedelta 
from datetime import date
import threading, traceback

import base64

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

############### init ################

_HEADERS = {
	"User-Agent": "okhttp/3.12.0"
}

def _log_dummy(message):
	print('[SLEDOVANI.TV]: ' + message )
	pass

class SledovaniTvCache:
	sledovanitv = None
	sledovanitv_init_params = None

	# #################################################################################################
	
	@staticmethod
	def get(username=None, password=None, pin=None, serialid=None, data_dir=None, log_function=_log_dummy):
		if SledovaniTvCache.sledovanitv and SledovaniTvCache.sledovanitv_init_params == (username, password, pin, serialid):
#			log_function("sledovanitv already loaded")
			pass
		else:
			SledovaniTvCache.sledovanitv = SledovaniTV(username, password, pin, serialid, data_dir, log_function )
			SledovaniTvCache.sledovanitv_init_params = (username, password, pin, serialid )
			log_function("New instance of sledovani.tv initialised")
		
		return SledovaniTvCache.sledovanitv

class SledovaniTV:
	def __init__(self, username, password, pin, serialid, data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self.pin = pin
		self.serialid = serialid
		self.sessionid = None
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
		self.headers = _HEADERS
	
		self.load_access_token()
		
		self.channels = {}
		self.channels_next_load = 0
		
		self.check_pairing()

	# #################################################################################################

	def load_access_token(self):
		if self.data_dir:
			try:
				# load access token
				with open(os.path.join(self.data_dir, 'login.json'), "r") as file:
					login_data = json.load(file)
					self.sessionid = login_data['token']
					self.log_function("Login data loaded from cache")
			except:
				pass

	# #################################################################################################
	
	def save_access_token(self):
		if self.data_dir and self.sessionid:
			with open( os.path.join(self.data_dir, 'login.json'), "w") as file:
				login_data = {
					'token': self.sessionid,
				}
				json.dump( login_data, file )

	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("SLEDOVANI.TV API ERROR: %s" % msg )
		raise Exception("SLEDOVANI.TV: %s" % msg)

	# #################################################################################################

	def call_api(self, url, data=None, params=None, enable_retry=True ):
		err_msg = None
		
		log_file = url
		
		if not url.startswith('http'):
			url = 'https://sledovanitv.cz/api/' + url
		
		try:
			if data:
				resp = requests.post( url, data=data, params=params, headers=self.headers )
			else:
				resp = requests.get( url, params=params, headers=self.headers )
			
#			self.log_function( "URL: %s (%s)" % (url, data or params or "none") )
#			self.log_function( "RESPONSE: %s" % resp.text )
			
			if resp.status_code == 200:
				try:
					ret = resp.json()
					
					if "status" not in ret or ret['status'] is 0:
						if ret['error'] == 'not logged' and enable_retry:
							old_sessionid = self.sessionid
							self.load_access_token()
							
							if old_sessionid == self.sessionid:
								# we don't have newer sessionid, so try to re-login
								self.pair_device()
								self.pin_unlock()
								enable_retry = False
							
							if params != None and 'PHPSESSID' in params:
								params['PHPSESSID'] = self.sessionid

							if data != None and 'PHPSESSID' in data:
								data['PHPSESSID'] = self.sessionid
							
							return self.call_api( url, data, params, enable_retry )
					
					return ret

				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód ze serveru: %d" % resp.status_code
		except Exception as e:
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "Sledovani.tv error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError( "%s" % err_msg )

	# #################################################################################################

	def check_pairing(self):
		if self.sessionid:
			data = self.call_api('content-home', params = { 'PHPSESSID': self.sessionid } )

		if not self.sessionid or "status" not in data or data['status'] is 0:
			if self.pair_device():
				self.pin_unlock()
				return True
		else:
			return True
		
		return False

	# #################################################################################################
	
	def pin_unlock(self):
		params = {
			'PHPSESSID' : self.sessionid
		}
		
		data = self.call_api("is-pin-locked", params = params )
		
		if data.get('pinLocked', 0) == 1 and self.pin != "":
			params = {
				'pin': str(self.pin),
				'whiteLogo': True,
				'PHPSESSID': self.sessionid
			}
			
			data = self.call_api( "pin-unlock", params = params )
			
			if data.get('error'):
				self.showError("Špatný PIN")
				return False
			
		return True

	# #################################################################################################
	
	def pair_device(self):
		params = {
			'username': self.username,
			'password': self.password,
			'type': 'androidportable',
			'serial': self.serialid,
			'product': 'Xiaomi Redmi+Note+7',
			'unit': 'default',
			'checkLimit': 1,
		}
		
		data = self.call_api("create-pairing", params = params, enable_retry=False)
		
		if "status" not in data or data['status'] is 0:
			self.showError("Problém při přihlášení: %s" % data['error'])
			return False
	
		if 'deviceId' in data and 'password' in data:
			params = {
				'deviceId': data['deviceId'],
				'password': data['password'],
				'version': '2.7.4',
				'lang': 'cs',
				'unit': 'default',
			}
			
			data = self.call_api("device-login", params = params, enable_retry=False )
			if "status" not in data or data['status'] is 0:
				self.showError("Problém při přihlášení: %s" % data['error'])
				return False
	
			if "PHPSESSID" in data:
				self.sessionid = data["PHPSESSID"]
				self.save_access_token()
				
				params = {
					"PHPSESSID": self.sessionid
				}
				
				self.call_api("keepalive", params = params, enable_retry=False )
			else:
				self.showError("Problém s příhlášením: no session")
				return False
		else:
			self.showError("Problém s příhlášením: no deviceid")
			return False
		
		return True

	# #################################################################################################
	
	def get_devices(self):
		params = {
			'PHPSESSID': self.sessionid,
		}
		
		data = self.call_api('get-devices', params = params )
		
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s načtením seznamu zařízení: %s" % data['error'])
			return []
		
		return data.get('devices', [])

	# #################################################################################################
	
	def get_time(self):
		data = self.call_api('time' )
		
		timestamp = data.get("timestamp")
		zone = data.get("zone")
		
		return (timestamp, zone)

	# #################################################################################################
	
	def compare_time(self, t):
		d = (t.replace(" ", "-").replace(":", "-")).split("-")
		now = datetime.now()
		start_time = now.replace(year=int(d[0]), month=int(d[1]), day=int(d[2]), hour=int(d[3]), minute=int(d[4]), second=0, microsecond=0)
		return start_time < now

	# #################################################################################################

	def convert_time(self, t):
		d = (t.replace(" ", "-").replace(":", "-")).split("-")
		now = datetime.now()
		start_time = now.replace(year=int(d[0]), month=int(d[1]), day=int(d[2]), hour=int(d[3]), minute=int(d[4]), second=0, microsecond=0)
		return time.mktime(start_time.timetuple())

	# #################################################################################################
	
	def get_home(self):
		params = {
			'category': 'box-homescreen',
			'detail': 'events,subcategories',
			'eventCount': 1,
			'PHPSESSID': self.sessionid,
		}
		
		data = self.call_api("show-category", params = params )
		
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s načtením kanálů: %s" % data['error'])
			return False
		
		channels = []
		if 'info' in data and 'items' in data['info']:
			catitle = "["+data['info']['title']+"] " if 'title' in data['info'] else ""
			for item in data['info']['items']:
				if item['events'][0]['availability'] != "timeshift":
					continue
				
				title = item['events'][0]["startTime"][8:10] + "." + item['events'][0]["startTime"][5:7] + ". " + item['events'][0]["startTime"][11:16] + "-" + item['events'][0]["endTime"][11:16] + " [" + item['events'][0]["channel"].upper() + "] " + item["title"]
				desc = item["description"] if 'description' in item else ""
				thumb = item["poster"] if 'poster' in item else None
				
				channels.append({
					'title': title,
					'eventid':  item['events'][0]['eventId'],
					'thumb': thumb,
					'plot': catitle+desc,
				})
				
	
		if 'subcategories' in data:
			for category in data['subcategories']:
				catitle = "["+category['title']+"] " if 'title' in category else ""
				if 'items' in category:
					for item in category['items']:
						if item['events'][0]['availability'] != "timeshift":
							continue
						
						title = item['events'][0]["startTime"][8:10] + "." + item['events'][0]["startTime"][5:7] + ". " + item['events'][0]["startTime"][11:16] + "-" + item['events'][0]["endTime"][11:16] + " [" + item['events'][0]["channel"].upper() + "] " + item["title"]
						desc = item.get("description","")
						thumb = item.get("poster")
						duration = item['events'][0].get('duration')
						
						channels.append({
							'title': title,
							'eventid':  item['events'][0]['eventId'],
							'thumb': thumb,
							'plot': catitle+desc,
							'duration': duration,
							'start_time': self.convert_time( item["events"][0]["startTime"] ),
						})

		return channels

	# #################################################################################################
	
	def device_remove(self, did):
		params = {
			'deviceId': did,
			'PHPSESSID': self.sessionid
		}

		# WRONG API - NEED TO INVESTIGATE
#		data = self.call_api("device-remove", params=params)
		
		return { 'status': 0 }

	# #################################################################################################

	def search(self, query ):
		params = {
			'query': query,
			'detail': 'description,poster',
			'allowOrder': True,
			'PHPSESSID': self.sessionid
		}
		
		epgdata = self.call_api("epg-search", params=params)
		
		if "status" not in epgdata or epgdata['status'] is 0:
			self.showError("Problém s načtením EPG: %s"%epgdata['error'])
			epgdata = []

		return epgdata.get('events', [])
	
	# #################################################################################################
	
	def get_epg(self, time_start=None, duration_min=60):
		
		if time_start == None:
			time_start = datetime.now()
		
		params = {
			'time': time_start.strftime("%Y-%m-%d %H:%M"),
			'duration': duration_min,
			'detail': 'description,poster',
			'allowOrder': True,
			'PHPSESSID': self.sessionid
		}
		
		epgdata = self.call_api("epg", params=params)
		
		if "status" not in epgdata or epgdata['status'] is 0:
			self.showError("Problém s načtením EPG: %s"%epgdata['error'])
			epgdata = {}
		
		return epgdata.get('channels',{})

	# #################################################################################################
	
	def get_channels(self, refresh_channels_data=False):
		if refresh_channels_data or not self.channels or self.channels_next_load < int(time.time()):
			 
			params = {
				'uuid': self.serialid,
				'format': 'm3u8',
				'quality': 40,
				'drm': 'widevine',
				'capabilities': 'adaptive2',
				'cast': 'chromecast',
				'PHPSESSID': self.sessionid,
			}
			
			data = self.call_api("playlist", params=params )
			
			if "status" not in data or data['status'] is 0:
				self.showError("Problém s načtením kanálů: %s"%data['error'])
				return []
			
			channels = {}
			number = 0
			
			for channel in data.get('channels',[]):
				if channel['locked'] != 'none' and channel['locked'] != 'pin':
					continue
				
				number += 1
				channels[channel['id']] = {
					'id': channel['id'],
					'name': channel['name'],
					'url': channel['url'],
					'adult': channel['locked'] == 'pin',
					'number': number,
					'type': channel['type'],
					'picon': channel['logoUrl'],
					'timeshift': channel['timeshiftDuration']
				}
			
				self.channels = channels
				self.channels_next_load = int(time.time()) + 3600
			
		return self.channels

	# #################################################################################################

	def get_channels_sorted(self, channel_type='tv', refresh_channels_data=False):
		self.get_channels(refresh_channels_data)
		
		result = []
		
		for ch in self.channels.values():
			if ch['type'] == channel_type:
				result.append(ch)
		
		return sorted(result, key=lambda _channel: _channel['number'])

	# #################################################################################################

	def get_recordings(self):
		params = {
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('get-pvr', params = params )
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s načtením nahrávek: %s" % data['error'])
			return None

		return data.get('records', [])

	# #################################################################################################

	def delete_recording( self, recordid ):
		params = {
			'recordId': recordid,
			'do': 'delete',
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('delete-record', params = params )
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s smazáním nahrávky: %s" % data['error'])
			return False
		
		return True
	# #################################################################################################

	def add_recording( self, eventid ):
		params = {
			'eventId': eventid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('record-event', params = params )
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s nastavením nahrávky: %s" % data['error'])
			return False
		
		return True

	# #################################################################################################
	
	def resolve_streams(self, url ):
		try:
			req = requests.get(url)
		except:
			self.showError("Problém při načtení videa. Pokud je červené, zadejte v nastavení správný PIN!")
			return
		
		if req.status_code != 200:
			self.showError("Problém při načtení videa")
			return

		res = []

		for m in re.finditer('#EXT-X-STREAM-INF:.*?,RESOLUTION=(?P<resolution>[^\s]+)\s(?P<chunklist>[^\s]+)', req.text, re.DOTALL):
			itm = {}
			itm['quality'] = m.group('resolution')
			itm['url'] = m.group('chunklist')
			res.append(itm)
			
		res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
		
		return res
	
	# #################################################################################################
	
	def get_raw_link(self, channel_key ):
		self.get_channels()
		
		channel = self.channels.get(channel_key)
		
		if not channel:
			return None
		
		return channel['url'].replace('https://', 'http://')

	# #################################################################################################

	def get_live_link(self, channel_key ):
		url = self.get_raw_link( channel_key )

		if not url:
			return None
		
		return self.resolve_streams(url)

	# #################################################################################################

	def get_event_link(self, eventid ):
		params = {
			'format': 'm3u8',
			'eventId': eventid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('event-timeshift', params = params )
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s načtením nahrávky: %s" % data['error'])
			return None
		
		return self.resolve_streams(data['url'])

	# #################################################################################################

	def get_recording_link(self, recordid ):
		params = {
			'format': 'm3u8',
			'recordId': recordid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('record-timeshift', params = params )
		if "status" not in data or data['status'] is 0:
			self.showError("Problém s načtením nahrávky: %s" % data['error'])
			return None
		
		return self.resolve_streams(data['url'])

	# #################################################################################################
