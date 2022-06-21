# -*- coding: utf-8 -*-
import re,sys,os,string,base64,datetime,json,requests
from time import time
from uuid import getnode as get_mac
import threading

try:
	from urllib import quote
	is_py3 = False
except:
	from urllib.parse import quote
	is_py3 = True

_COMMON_HEADERS = {
	"X-NanguTv-Platform-Id": "b0af5c7d6e17f24259a20cf60e069c22",
	"X-NanguTv-Device-size": "normal",
	"X-NanguTv-Device-Name": "Nexus 7",
	"X-NanguTv-App-Version": "Android#7.6.3-release",
	"X-NanguTv-Device-density": "440",
	"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; Nexus 7 Build/LMY47V)",
	"Connection": "keep-alive"
}

def device_id():
	mac = get_mac()
	hexed	= hex((mac * 7919) % (2 ** 64))
	return ('0000000000000000' + hexed[2:-1])[16:]

def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output

class LiveChannel:
	def __init__(self, channel_key, name, logo_url, weight, quality, timeshift, number, id, picon, adult):
		self.channel_key = channel_key
		self.name = name
		self.weight = weight
		self.logo_url = logo_url
		self.quality = quality
		self.timeshift = timeshift
		self.number = number
		self.id = id
		self.picon = picon
		self.adult = adult


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
	print('[ORANGETV]: ' + message )
	pass

# #################################################################################################

class OrangeTVcache:
	orangetv = None
	orangetv_init_params = None

	# #################################################################################################
	
	@staticmethod
	def get(username=None, password=None, device_id=None, data_dir=None, log_function=_log_dummy):
		if OrangeTVcache.orangetv and OrangeTVcache.orangetv_init_params == (username, password, device_id):
			log_function("OrangeTV already loaded")
		else:
			OrangeTVcache.orangetv = OrangeTV(username, password, device_id, data_dir, log_function )
			OrangeTVcache.orangetv_init_params = (username, password, device_id)
			OrangeTVcache.orangetv.loadEpgCache()
			log_function("New instance of OrangeTV initialised")
		
		return OrangeTVcache.orangetv
	
# #################################################################################################

class OrangeTV:

	def __init__(self, username, password, device_id='Nexus7', data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self._live_channels = {}
		self.access_token = None
		self.access_token_life = 0
		self.subscription_code = None
		self.locality = None
		self.offer = None
		self.device_id = device_id
		self.quality = 'MOBILE'
		self.log_function = log_function if log_function else _log_dummy
		self.devices = None
		self.epg_cache = {}
		self.data_dir = data_dir
		self.cache_need_save = False
		self.cache_mtime = 0
		
		if not self.device_id or len( self.device_id ) == 0:
			# if not device id is provided, then create one
			self.device_id = device_id()
		
		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as file:
					login_data = json.load(file)
					self.access_token = login_data['token']
					self.access_token_life = login_data['expires']
					
					self.log_function("Login data loaded from cache")
			except:
				pass
				
	def __del__(self):
		self.saveEpgCache()
		
	def loadEpgCache(self):
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
	
	def saveEpgCache(self):
		if self.data_dir and self.cache_need_save:
			with open(self.data_dir + '/epg_cache.json', 'w') as f:
				json.dump( self.epg_cache, f)
				self.log_function("EPG saved to cache")
				self.cache_need_save = False

	def get_access_token_password(self):
		self.log_function('Getting Token via password...')
		
		if not self.username or not self.password:
			self.log_function('No username or password provided...')
			raise AuthenticationError()
		
		headers = _COMMON_HEADERS
		headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
		data = {'grant_type': 'password',
				'client_id': 'orangesk-mobile',
				'client_secret': 'e4ec1e957306e306c1fd2c706a69606b',
				'isp_id': '5',
				'username': self.username,
				'password': self.password,
				'platform_id': 'b0af5c7d6e17f24259a20cf60e069c22',
				'custom': 'orangesk-mobile',
				'response_type': 'token'
				}
		req = requests.post('https://oauth01.gtm.orange.sk/oauth/token', data=data, headers=headers, verify=False)
		self.log_function('Access token response:\n%s' % req.text)

		j = req.json()
		if 'error' in j:
			error = j['error']
			if error == 'authentication-failed':
				self.log_function('Authentication Error')
				return None
			else:
				raise Exception(error)
		self.access_token = j["access_token"]
		self.access_token_life = (int(time()) +  int(j["expires_in"] / 1000)) - 3600
		
		if self.data_dir:
			with open(self.data_dir + '/login.json', "w") as file:
				login_data = {
					'token': self.access_token,
					'expires': self.access_token_life
				}
				json.dump( login_data, file )

		self.log_function('Token OK')
		return self.access_token

	def refresh_access_token(self):
		if not self.access_token or self.access_token_life < int(time()):
			self.access_token = None
			self.get_access_token_password()
		if not self.access_token:
			self.log_function('Authentication Error (failed to get token)')
			raise AuthenticationError()
		return self.access_token

	def device_remove(self,did):
		self.refresh_access_token()
		headers = _COMMON_HEADERS
		cookies = {"access_token": self.access_token, "deviceId": self.device_id}
		if did is None:
			did = ''
		params = {"deviceId": did}
		req = requests.get('https://app01.gtm.orange.sk/sws/subscription/settings/remove-device.json', params=params, headers=headers, cookies=cookies)
		j = req.json()

	def refresh_configuration(self, force_reload=False):
		self.refresh_access_token()
		
		if not force_reload and self.subscription_code:
			# configuration already loaded
			return
		
		headers = _COMMON_HEADERS
		cookies = {"access_token": self.access_token, "deviceId": self.device_id}
		req = requests.get('https://app01.gtm.orange.sk/sws//subscription/settings/subscription-configuration.json', headers=headers, cookies=cookies)
		j = req.json()
		if 'errorMessage' in j:
			raise Exception('Err: ' + j['errorMessage'])
		self.subscription_code = _to_string(j["subscription"])
		self.offer = j["billingParams"]["offers"]
		self.tariff = j["billingParams"]["tariff"]
		self.locality = j["locality"]
		self.devices = j["pairedDevices"]

	def live_channels(self):
		self.refresh_configuration()
		
		timeshift = 0
		
		if len(self._live_channels) == 0:
			channels = {}
			headers = _COMMON_HEADERS
			cookies = {
				"access_token": self.access_token,
				"deviceId": self.device_id
			}
			params = {
				"locality": self.locality,
				"tariff": self.tariff ,
				"isp": "5",
				"imageSize": "LARGE",
				"language": "slo",
				"deviceType": "PC",
				"liveTvStreamingProtocol": "HLS",
				"offer": self.offer
			}	# doplněn parametr kvality
			
			req = requests.get('http://app01.gtm.orange.sk/sws/server/tv/channels.json', params=params, headers=headers, cookies=cookies)
			
			j = req.json()
			purchased_channels = j['purchasedChannels']
			if len(purchased_channels) == 0:  # JiRo - doplněna kontrola zaplacené služby
				raise NoPurchasedServiceError()	 # JiRo - doplněna kontrola zaplacené služby
			
			items = j['channels']
			for channel_id, item in items.items():
				if channel_id in purchased_channels:
					if item['timeShiftDuration']:
						timeshift = int(item['timeShiftDuration'])/60/24	# pocet dni zpetneho prehravani
					else:
						timeshift = 0

					channel_key = _to_string(item['channelKey'])
					logo = _to_string(item['screenshots'][0]).replace('https://', 'http://')
					if not logo.startswith('http://'):
						logo = 'http://app01.gtm.orange.sk/' + logo
					name = _to_string(item['channelName'])
					adult = 'audience' in item and item['audience'].upper() == 'INDECENT'
					channels[channel_key] = LiveChannel(channel_key, name, logo, item['weight'], self.quality, timeshift, item['channelNumber'], item['channelId'], item['logo'], adult)
						
			self._live_channels = sorted(list(channels.values()), key=lambda _channel: _channel.number)
			done = False
			offset = 0

		return self._live_channels

	def getChannelEpg(self, ch, fromts, tots):
		self.refresh_configuration()

		headers = _COMMON_HEADERS
		cookies = {"access_token": self.access_token, "deviceId": self.device_id}
		params = {"channelKey": ch, "fromTimestamp": fromts, "imageSize": "LARGE", "language": "ces", "offer": self.offer, "toTimestamp": tots}
		req = requests.get('https://app01.gtm.orange.sk/sws/server/tv/channel-programs.json', params=params, headers=headers, cookies=cookies)
		
		if req.status_code == 200:
			return req.json()
		
		return []

	def fillChannelEpgCache(self, ch, epg, last_timestamp = 0):
		ch_epg = []

		for one in epg:
			title = _to_string(one["name"]) + " - " + datetime.datetime.fromtimestamp(one["startTimestamp"]/1000).strftime('%H:%M') + "-" + datetime.datetime.fromtimestamp(one["endTimestamp"]/1000).strftime('%H:%M')
			ch_epg.append({"start": one["startTimestamp"], "end": one["endTimestamp"], "title": title, "desc": one["shortDescription"]})
			
			if last_timestamp and one["startTimestamp"] > last_timestamp:
				break
				

		self.epg_cache[ch] = ch_epg
		self.cache_need_save = True
	
	def getChannelCurrentEpg(self,ch,cache_hours=0):
		fromts = int(time())*1000
		tots = (int(time()) + (cache_hours * 3600) + 60) * 1000
		title = ""
		desc = ""
		del_count = 0
		
		if ch in self.epg_cache:
			for epg in self.epg_cache[ch]:
				if epg["end"] < fromts:
					# cleanup old events
					del_count += 1
				
				if epg["start"] < fromts and epg["end"] > fromts:
					title = epg["title"]
					desc = epg["desc"]
					break
		
		if del_count:
			# save some memory - remove old events from cache
			del self.epg_cache[ch][:del_count]
			self.log_function("Deleted %d old events from EPG cache for channell %s" % (del_count, ch))
			
		# if we haven't found event in cache and epg refresh is enabled (cache_hours > 0)
		if title == "" and cache_hours > 0:
			# event not found in cache, so request fresh info from server (can be slow)
			self.log_function("Requesting EPG for channel %s from %d to %d" % (ch, fromts/1000, tots/1000) )
			
			j = self.getChannelEpg(ch,fromts,tots)
			self.fillChannelEpgCache(ch, j)
			
			# cache already filled with fresh entries, so the first one is current event
			title = self.epg_cache[ch][0]['title']
			desc = self.epg_cache[ch][0]['desc']
		
		if title == "":
			return None
		
		return {"title": title, "desc": desc}

	def getArchivChannelPrograms(self,ch,day):
		self.refresh_configuration()
		
		fromts = int(day)*1000
		tots = (int(day)+86400)*1000
		headers = _COMMON_HEADERS
		cookies = {"access_token": self.access_token, "deviceId": self.device_id}
		params = {"channelKey": ch, "fromTimestamp": fromts, "imageSize": "LARGE", "language": "ces", "offer": self.offer, "toTimestamp": tots}
		req = requests.get('https://app01.gtm.orange.sk/sws/server/tv/channel-programs.json', params=params, headers=headers, cookies=cookies)
		j = req.json()
		
		response = []
		for program in j:
			if int(time())*1000 > program["startTimestamp"]:
				title = _to_string(program["name"]) + " - [COLOR yellow]" + datetime.datetime.fromtimestamp(program["startTimestamp"]/1000).strftime('%H:%M') + "-" + datetime.datetime.fromtimestamp(program["endTimestamp"]/1000).strftime('%H:%M') + "[/COLOR]"
				
				p = {
					'title': title,
					'url': ch+"|"+str(program["epgId"])+"|"+str(program["startTimestamp"])+"|"+str(program["endTimestamp"]),
					'image': program["picture"],
					'plot': program["shortDescription"]
				}
				# (name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
				response.append(p)

		return response
	
	def getVideoLink(self, url):
		channel_key,pid,fts,tts = url.split("|")
		
		self.refresh_configuration()
			
		playlist = None
		while self.access_token:
			if pid:
				params = {
					"serviceType": "TIMESHIFT_TV",
					"contentId": pid,
					"subscriptionCode": self.subscription_code,
					"channelKey": channel_key,
					"deviceType": self.quality,
					"fromTimestamp": fts,
					"toTimestamp": tts
				}
			else:
				params = {
					"serviceType": "LIVE_TV",
					"subscriptionCode": self.subscription_code,
					"channelKey": channel_key,
					"deviceType": self.quality
				}
			headers = _COMMON_HEADERS
			cookies = {"access_token": self.access_token, "deviceId": self.device_id}
			req = requests.get('http://app01.gtm.orange.sk/sws/server/streaming/uris.json', params=params, headers=headers, cookies=cookies)
			json_data = req.json()
			access_token = None
			
			if 'statusMessage' in json_data:
				status = json_data['statusMessage']
				if status == 'bad-credentials':
					self.access_token = None
					self.refresh_access_token()
				else:
					raise Exception("Err: "+status)
			else:
				playlist = ""
				for uris in json_data["uris"]:
					if uris["resolution"] == "HD":
						playlist = uris["uri"]
						break

				if playlist == "":
					playlist = json_data["uris"][0]["uri"]
				break
			
		result = []
		r = requests.get(playlist, headers=_COMMON_HEADERS).text
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+),AUDIO="\d+"\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
			bandwidth = int(m.group('bandwidth'))
			quality = ""
			if bandwidth < 2000000:
				quality = "480p"
			elif bandwidth < 3000000:
				quality = "576p"
			elif bandwidth < 6000000:
				quality = "720p"
			else:
				quality = "1080p"
			url = m.group('chunklist')
			result.append( {"url": url, "quality": quality, 'bandwidth': bandwidth } )
		
		result = sorted( result, key=lambda r: r['bandwidth'], reverse=True )
		return result

# #################################################################################################

class OrangeTvBouquetGenerator:
	def __init__(self, endpoint):
		# configuration to make this class little bit reusable also in other addons
		self.proxy_url = endpoint
		self.prefix = "orangetv"
		self.name = "Orange TV"
		self.sid_start = 0x100
		self.tid = 4
		self.onid = 3
		self.namespace = 0xE020000
	
	# bouquet generator funcions based on AntikTV addon
	@staticmethod
	def download_picons(picons):
		if not os.path.exists( '/usr/share/enigma2/picon' ):
			os.mkdir('/usr/share/enigma2/picon')
			
		for ref in picons:
			if not picons[ref].endswith('.png'):
				continue
			
			fileout = '/usr/share/enigma2/picon/' + ref + '.png'
			
			if not os.path.exists(fileout):
				try:
					r = requests.get( picons[ref].replace('https://', 'http://').replace('64x64','220x220'), timeout=3 )
					if r.status_code == 200:
						with open(fileout, 'wb') as f:
							f.write( r.content )
				except:
					pass
	
	def build_service_ref( self, service, player_id ):
		return player_id + ":0:{:X}:{:X}:{:X}:{:X}:{:X}:0:0:0:".format( service.ServiceType, service.ServiceID, service.Transponder.TransportStreamID, service.Transponder.OriginalNetworkID, service.Transponder.DVBNameSpace )


	def service_ref_get( self, lamedb, channel_name, player_id, channel_id ):
		
		skylink_freq = [ 11739, 11778, 11856, 11876, 11934, 11954, 11973, 12012, 12032, 12070, 12090, 12110, 12129, 12168, 12344, 12363 ]
		antik_freq = [ 11055, 11094, 11231, 11283, 11324, 11471, 11554, 11595, 11637, 12605 ]
		
		def cmp_freq( f, f_list ):
			f = int(f/1000)
			
			for f2 in f_list:
				if abs( f - f2) < 5:
					return True
		
			return False
	
		if lamedb != None:
			try:
				services = lamedb.Services[ lamedb.name_normalise( channel_name ) ]
				
				# try position 23.5E first
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 235 and cmp_freq( s.Transponder.Data.Frequency, skylink_freq ):
						return self.build_service_ref(s, player_id)
		
				# then 16E
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 160 and cmp_freq( s.Transponder.Data.Frequency, antik_freq ):
						return self.build_service_ref(s, player_id)
		
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 235:
						return self.build_service_ref(s, player_id)
		
				# then 16E
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 160:
						return self.build_service_ref(s, player_id)
		
				# then 0,8W
				for s in services:
					if s.Transponder.Data.OrbitalPosition == -8:
						return self.build_service_ref(s, player_id)
		
				# then 192
				for s in services:
					if s.Transponder.Data.OrbitalPosition == 192:
						return self.build_service_ref(s, player_id)
		
				# take the first one
				for s in services:
					return self.build_service_ref(s, player_id)
		
			except:
				pass
		
		return player_id + ":0:1:%X:%X:%X:%X:0:0:0:" % (self.sid_start + channel_id, self.tid, self.onid, self.namespace)
	
	
	def generate_bouquet(self, channels, enable_adult=True, enable_xmlepg=False, enable_picons=False, player_name="0"):
		# if epg generator is disabled, then try to create service references based on lamedb
		if enable_xmlepg:
			lamedb = None
		else:
			lamedb = lameDB("/etc/enigma2/lamedb")
		
		if player_name == "1": # gstplayer
			player_id = "5001"
		elif player_name == "2": # exteplayer3
			player_id = "5002"
		elif player_name == "3": # DMM
			player_id = "8193"
		elif player_name == "4": # DVB service (OE >=2.5)
			player_id = "1"
		else:
			player_id = "4097" # system default
	
		file_name = "userbouquet.%s.tv" % self.prefix
		
		picons = {}
		
		service_ref_uniq = ':%X:%X:%X:0:0:0:' % (self.tid, self.onid, self.namespace)
		
		with open( "/etc/enigma2/" + file_name, "w" ) as f:
			f.write( "#NAME %s\n" % self.name )
			
			for channel in channels:
				if not enable_adult and channel['adult']:
					continue
				
				channel_name = channel['name']
				url = self.proxy_url + '/playlive/' + base64.b64encode( channel['key'].encode('utf-8') ).decode('utf-8')
				url = quote( url )
				
				service_ref = self.service_ref_get( lamedb, channel_name, player_id, channel['id'] )
					
				f.write( "#SERVICE " + service_ref + url + ":" + channel_name + "\n")
				f.write( "#DESCRIPTION " + channel_name + "\n")
				
				try:
					if enable_picons and service_ref.endswith( service_ref_uniq ):
						picons[ service_ref[:-1].replace(':', '_') ] = channel['picon']
				except:
					pass
		
		first_export = True
		with open( "/etc/enigma2/bouquets.tv", "r" ) as f:
			for line in f.readlines():
				if file_name in line:
					first_export = False
					break
		
		if first_export:
			with open( "/etc/enigma2/bouquets.tv", "a" ) as f:
				f.write( '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "' + file_name + '" ORDER BY bouquet' + "\n" )
	
		try:
			requests.get("http://127.0.0.1/web/servicelistreload?mode=2")
		except:
			pass
		
		if enable_picons:
			threading.Thread(target=OrangeTvBouquetGenerator.download_picons,args=(picons,)).start()
	