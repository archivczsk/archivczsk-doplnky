# -*- coding: utf-8 -*-
import re,sys,os,string,base64,datetime,json,requests,traceback
from time import time, mktime
from datetime import datetime
import threading
import uuid
from hashlib import sha1, md5

try:
	from urllib import quote
	from urlparse import urlparse, urlunparse, parse_qsl
	is_py3 = False

	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')

except:
	from urllib.parse import quote, urlparse, urlunparse, parse_qsl
	is_py3 = True
	
	def py2_encode_utf8( text ):
		return text

def device_id():
	mac_str = ':'.join(("%012X" % uuid.getnode())[i:i+2] for i in range(0, 12, 2))
	return sha1( mac_str.encode("utf-8") ).hexdigest()

def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output

# #################################################################################################

class MagioGoChannel:
	def __init__(self, channel_info):
		self.id = str(channel_info['channelId'])
		self.name = py2_encode_utf8(channel_info['name'])
		self.type = channel_info['type']
		self.timeshift = channel_info.get('archive', 0) // 1000 if channel_info.get('hasArchive', False) and channel_info.get('archiveSubscription', False) else 0
		self.picon = channel_info['logoUrl'].replace('https', 'http')
		self.adult = False
		self.preview = None

	# #################################################################################################
	
	def set_aditional(self, info):
		preview_urls = info.get('images',[])
		if preview_urls:
			self.preview = preview_urls[0]
			
		self.adult = info.get('adult', False)

# #################################################################################################

class ChannelIsNotBroadcastingError(BaseException):
	pass

class AuthenticationError(BaseException):
	pass

class TooManyDevicesError(BaseException):
	pass

# JiRo - doplněna kontrola zaplacené služby
class NoPurchasedServiceError(BaseException):
	pass

def _log_dummy(message):
	print('[Magio GO]: ' + message )
	pass

# #################################################################################################

__debug_nr = 1

def writeDebugRequest(url, params, data, response ):
	global __debug_nr
	
	name = "/tmp/%03d_request_%s" % (__debug_nr, url[8:].replace('/','_'))
	
	with open(name, "w") as f:
		f.write( json.dumps({'params': params, 'data': data } ))

	name = "/tmp/%03d_response_%s" % (__debug_nr, url[8:].replace('/','_'))
	
	with open(name, "w") as f:
		f.write( json.dumps(response))
		
	__debug_nr += 1
	
# #################################################################################################

class MagioGoCache:
	magiogo = None
	magiogo_init_params = None

	# #################################################################################################
	
	@staticmethod
	def get(region=None, username=None, password=None, device_id=None, device_type = None, data_dir=None, log_function=_log_dummy):
		if MagioGoCache.magiogo and MagioGoCache.magiogo_init_params == (region, username, password, device_id, device_type):
			log_function("Magio GO already loaded")
			pass
		else:
			MagioGoCache.magiogo = MagioGo(region, username, password, device_id, device_type, data_dir, log_function )
			MagioGoCache.magiogo_init_params = (region, username, password, device_id, device_type)
			log_function("New instance of Magio GO initialised")
		
		return MagioGoCache.magiogo
	
# #################################################################################################

class MagioGo:
	magiogo_device_types = [
		("OTT_ANDROID", "Xiaomi Mi 11"),        # 0
		("OTT_IPAD", "iPad Pro"),               # 1
		("OTT_STB", "KSTB6077"),                # 2
#		("OTT_TV_WEBOS", "LGG50UP7500"),        # 3
		("OTT_TV_ANDROID", "XR-65X95J"),        # 3
		("OTT_SKYWORTH_STB", "Skyworth"),       # 4
	]

	def __init__(self, region = None, username=None, password=None, device_id=None, device_type = None, data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self.device_id = device_id
		self.channel_list = None
		self.access_token = None
		self.refresh_token = None
		self.access_token_life = 0
		self.log_function = log_function if log_function else _log_dummy
		self.device = MagioGo.magiogo_device_types[device_type]
		self.devices = None
		self.settings = None
		self.data_dir = data_dir
		self.epg_cache = {}
		self.cache_need_save = False
		self.cache_mtime = 0
		self.region = region.lower()
		self.common_headers = {
			"Content-type": "application/json",
			"Host": self.region + "go.magio.tv",
			"User-Agent": "okhttp/3.12.12",
		}

		self.load_login_data()
		self.refresh_login_data()

	# #################################################################################################
	
	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}|{}|{}".format(self.password, self.username, self.device_id, self.device[0], self.region)
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
						self.refresh_token = login_data['refresh_token']
						self.access_token_life = login_data['access_token_life']
						self.log_function("Login data loaded from cache")
					else:
						self.access_token = None
						self.refresh_token = None
						self.access_token_life = 0
						self.log_function("Not using cached login data - wrong checksum")
			except:
				pass
		
	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				if self.access_token:
					# save access token
					with open(self.data_dir + '/login.json', "w") as f:
						data = {
							'access_token': self.access_token,
							'refresh_token': self.refresh_token,
							'access_token_life': self.access_token_life,
							'checksum': self.get_chsum()
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass
	# #################################################################################################
	
	def load_epg_cache(self):
		try:
			try:
				cache_file_mtime = int(os.path.getmtime(self.data_dir + '/epg_cache.json'))
			except:
				cache_file_mtime = 0
			
			if cache_file_mtime > self.cache_mtime:
				with open(self.data_dir + '/epg_cache.json', "r") as file:
					self.epg_cache = json.load(file)
					self.log_function("EPG loaded from cache")
				
				self.cache_mtime = cache_file_mtime
				self.cache_need_save = False
		except:
			pass
		
		return True if self.cache_mtime else False
	
	# #################################################################################################
	
	def save_epg_cache(self):
		if self.data_dir and self.cache_need_save:
			with open(self.data_dir + '/epg_cache.json', 'w') as f:
				json.dump( self.epg_cache, f)
				self.log_function("EPG saved to cache")
				self.cache_need_save = False
				
	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("Magio GO API ERROR: %s" % msg )
		raise Exception("Magio GO: %s" % msg)
	
	# #################################################################################################

	def call_magiogo_api(self, endpoint, method='POST', data=None, params=None, auth_header=True ):
		err_msg = None
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = "https://" + self.region + "go.magio.tv/" + endpoint
		
		headers = self.common_headers
		
		if auth_header:
			headers['authorization'] = "Bearer " + self.access_token
		else:
			if 'authorization' in headers:
				del headers['authorization']
			
		try:
			if data:
				data = json.dumps(data, separators=(',', ':'))
				
			resp = requests.request( method, url, data=data, params=params, headers=headers )
			
#			writeDebugRequest( url, params, data, resp.json())
			if resp.status_code == 200 or resp.status_code == 401 or resp.status_code == 417:
				try:
					return resp.json()
				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód zo servera: %d" % resp.status_code
		except Exception as e:
			self.log_function("Magio GO ERROR:\n"+traceback.format_exc())
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "Magio GO error for URL %s: %s" % (url, traceback.format_exc()))
			self.log_function( "Magio GO: %s" % err_msg )
			self.showError( "%s" % err_msg )

		return None
	
	# #################################################################################################
	
	def login(self, force=False):
		if not self.username or not self.password:
			raise Exception("Magio GO: Nezadané prihlasovacie údaje")
		
		params = {
			"dsid": self.device_id,
			"deviceName": self.device[1],
			"deviceType": self.device[0],
			"osVersion": "0.0.0",
			"appVersion": "0.0.0",
			"language": "EN"
		}
		
		response = self.call_magiogo_api('v2/auth/init', params=params, auth_header=False )
		self.access_token = response["token"]["accessToken"]
		
		params = {
			"loginOrNickname": self.username,
			"password": self.password
		}
		
		response = self.call_magiogo_api("v2/auth/login", data=params )
		
		if response.get("success", False) == True:
			self.access_token = response["token"]["accessToken"]
			self.refresh_token = response["token"]["refreshToken"]
			self.access_token_life = response["token"]["expiresIn"] // 1000
			self.save_login_data()
		else:
			raise Exception("Magio GO: Prihlásenie zlyhalo: %s" % response.get('errorMessage', 'Neznáma chyba'))
	
	# #################################################################################################
	
	def refresh_login_data(self):
		if not self.access_token or not self.refresh_token:
			# we don't have access token - do fresh login using name/password
			self.login()
			return
		
		if self.access_token_life > int(time()):
			return

		# check if we have newer access token cached by another process
		self.load_login_data()
		if self.access_token_life > int(time()):
			return
		
		if self.refresh_token:
			# access token expired - get new one
			response = self.call_magiogo_api("v2/auth/tokens", data = { "refreshToken": self.refresh_token }, auth_header=False)
			
			if response.get("success", False) == True:
				self.access_token = response["token"]["accessToken"]
				self.refresh_token = response["token"]["refreshToken"]
				self.access_token_life = response["token"]["expiresIn"] // 1000
				self.save_login_data()
				return True
		
		# we don't have valid tokens - try fresh login using name/password
		self.login()

	# #################################################################################################
	
	def get_devices(self):
		self.refresh_login_data()
		
		ret = self.call_magiogo_api("v2/home/my-devices", method = "GET" )

		if not ret['success']:
			return []
				
		devices = []
		
		device = ret.get("thisDevice")
		
		if device:
			devices.append( { 'name': device['name'], 'id': device['id'], 'cat': device['category'], 'this': True } )

		for device in ret.get("smallScreenDevices",[]):
			devices.append( { 'name': device['name'], 'id': device['id'], 'cat': device['category'], 'this': False } )

		for device in ret.get("stbAndBigScreenDevices",[]):
			devices.append( { 'name': device['name'], 'id': device['id'], 'cat': device['category'], 'this': False } )

		return devices

	# #################################################################################################

	def remove_device(self, device_id):
		self.refresh_login_data()
		
		params = {
			'id': device_id
		}
		
		ret = self.call_magiogo_api("v2/home/deleteDevice", method = "GET", params = params )
		
		return req["success"], ret.get('errorMessage', '')

	# #################################################################################################

	def get_channel_list(self):
			
		if not self.channel_list or (int(time()) - self.channel_list_load_time) > 3600: 
			self.refresh_login_data()
			
			params = {
				"list": "LIVE",
				"queryScope": "LIVE"
			}
			ret = self.call_magiogo_api("v2/television/channels", method = "GET", params = params )

			if not ret or not ret.get('success'):
				return None
			
			channels = []
			self.channels = {}
			for ch in ret.get('items', []):
				channel = MagioGoChannel(ch['channel'])
				channel.set_aditional( ch.get('live',{}) )
				channels.append(channel)
				self.channels[channel.id] = channel
				
			self.channel_list = channels
			self.channel_list_load_time = int(time())
		
		return self.channel_list

	# #################################################################################################
	
	def get_stream_link(self, stream_id, service='LIVE'):
		self.refresh_login_data()
		
		params = {
			"service": service,
			"name": self.device[1],
			"devtype": self.device[0],
			"id": stream_id,
			"prof": 'p5',   # 'p4', 'p3'
			"ecid": "",
			"drm": "verimatrix"
		}

		response = self.call_magiogo_api("v2/television/stream-url", method = "GET", params = params)
		if response["success"] == True:
			url = response["url"]
		else:
			if response["errorCode"] == "NO_PACKAGE":
				url = None
			else:
				raise Exception( 'Magio GO: %s' % response['errorMessage'])
		
#		self.log_function("Stream URL for channel %s: %s" % (channel_id, url))
		
		return url
	
	# #################################################################################################
	
	def timestamp_to_magioformat(self, ts):
		ts_date = datetime.fromtimestamp(ts)
		return ts_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
	
	# #################################################################################################

	def magioformat_to_timestamp(self, magioformat):
		d = (magioformat.replace("T", "-").replace(":", "-")).split("-")
		now = datetime.now()
		start_time = now.replace(year=int(d[0]), month=int(d[1]), day=int(d[2]), hour=int(d[3]), minute=int(d[4]), second=int(d[5]), microsecond=0)
		return mktime(start_time.timetuple())
	
	# #################################################################################################
	
	def get_channels_epg(self, epg_ids, fromts, tots ):
		self.refresh_login_data()
		
		filter_str = 'channel.id=in=(' + ','.join(str(i) for i in epg_ids) + ');endTime=ge=' + self.timestamp_to_magioformat(fromts) + ';startTime=le=' + self.timestamp_to_magioformat(tots)
		
		params = {
			'filter': filter_str,
			'offset': 0,
			'limit': len(epg_ids),
			'lang': self.region.upper()
		}
		
		ret = self.call_magiogo_api( 'v2/television/epg', method='GET', params=params )
		
		if not ret["success"]:
			return None
		
		return ret.get('items')
		
	# #################################################################################################
	
	def fill_epg_cache(self, channel_ids, cache_hours=0, epg_data=None, auto_save=True ):
		if cache_hours == 0:
			return

		fromts = int(time())
		tots = (int(time()) + (cache_hours * 3600) + 60)

		if not epg_data:
			if self.cache_mtime and self.cache_mtime < tots - 3600:
				# no need to refill epg cache
				return
			
			epg_data = self.get_channels_epg( channel_ids, fromts, tots )
		
		if not epg_data:
			self.log_function("Failed to get EPG for channels from Mago GO server")
			return
		
		for epg_item in epg_data:
			channel_id = epg_item.get('channel',{}).get('channelId')
			
			if not channel_id:
				continue

			ch_epg = []
				
			for one in epg_item.get('programs',[]):
				
				title = py2_encode_utf8(one['program']["title"]) + " - " + one["startTime"][11:16] + "-" + one["endTime"][11:16]
				one_startts = self.magioformat_to_timestamp(one["startTime"])
				one_endts = self.magioformat_to_timestamp(one["endTime"])
				
				ch_epg.append({"start": one_startts, "end": one_endts, "title": title, "desc": one['program']["description"]})
				
				if one_startts > tots:
					break
				
			self.epg_cache[str(channel_id)] = ch_epg
			self.cache_need_save = True
			
		if auto_save:
			self.save_epg_cache()
		
	# #################################################################################################

	def get_channel_current_epg(self, epg_id):
		fromts = int(time())
		title = ""
		desc = ""
		del_count = 0
		
		epg_id = str(epg_id)
		if epg_id in self.epg_cache:
			for epg in self.epg_cache[epg_id]:
				if epg["end"] < fromts:
					# cleanup old events
					del_count += 1
				
				if epg["start"] < fromts and epg["end"] > fromts:
					title = epg["title"]
					desc = epg["desc"]
					break
		
		if del_count:
			# save some memory - remove old events from cache
			del self.epg_cache[epg_id][:del_count]
			self.log_function("Deleted %d old events from EPG cache for channell %s" % (del_count, epg_id))
			
		if title == "":
			return None
		
		return {"title": title, "desc": desc}

	# #################################################################################################

	def get_archiv_channel_programs(self, channel_id, day):
		fromts = int(day)
		tots = (int(day)+86400)
		
		epg_data = self.get_channels_epg( [int(channel_id)], fromts, tots)
		
		response = []
		cur_time = int(time())

		for epg_item in epg_data:
			if int(channel_id) == epg_item.get('channel',{}).get('channelId'):
				for one in epg_item.get('programs',[]):
					one_startts = self.magioformat_to_timestamp(one["startTime"])
					
					if cur_time > one_startts:
						title = py2_encode_utf8(one['program']["title"]) + " - [COLOR yellow]" + one["startTime"][11:16] + "-" + one["endTime"][11:16] + "[/COLOR]"
						one_endts = self.magioformat_to_timestamp(one["endTime"])
						
						p = {
							'title': title,
							'id': one['program']['programId'],
							'image': one['program'].get('images', [None])[0],
							'plot': one['program']["description"]
						}

						response.append(p)
					
				break

		return response
	
	# #################################################################################################
	
	def get_archive_video_link(self, ch, fromts, tots, enable_h265=False ):
		if not self.device_token:
			return None
		
		params = {
			'device_token': self.device_token,
			'channel_id': ch,
			'start': fromts,
			'end': tots
		}
		
		ret = self.call_telly_api( 'contentd/api/device/getContent', params=params)
		
		if not ret or ret.get('success') != True:
			return None
		
		return self.get_video_link( ret['stream_uri'], enable_h265)

# #################################################################################################
