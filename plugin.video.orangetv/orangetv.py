# -*- coding: utf-8 -*-
import re,sys,os,string,base64,datetime,json,requests
from time import time

_COMMON_HEADERS = {
	"X-NanguTv-Platform-Id": "b0af5c7d6e17f24259a20cf60e069c22",
	"X-NanguTv-Device-size": "normal",
	"X-NanguTv-Device-Name": "Nexus 7",
	"X-NanguTv-App-Version": "Android#7.6.3-release",
	"X-NanguTv-Device-density": "440",
	"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; Nexus 7 Build/LMY47V)",
	"Connection": "keep-alive"
}

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

_orangetv = None
_orangetv_init_params = None

def get_orangetv( device_id, username, password, quality, epg_cache_file=None, log_function=None ):
	global _orangetv
	global _orangetv_init_params
	
	if _orangetv and _orangetv_init_params == (device_id, username, password, quality):
		return _orangetv
	
	_orangetv = OrangeTV( device_id, username, password, quality, epg_cache_file, log_function )
	_orangetv_init_params = (device_id, username, password, quality)
	
	return _orangetv

class OrangeTV:

	def __init__(self, device_id, username, password, quality, data_dir=None, log_function=None):	# JiRo - doplněn parametr kvality
		self.username = username
		self.password = password
		self._live_channels = {}
		self.access_token = None
		self.access_token_life = 0
		self.subscription_code = None
		self.locality = None
		self.offer = None
		self.device_id = device_id
		self.quality = quality	# JiRo - doplněn parametr kvality
		self.log_function = log_function if log_function else _log_dummy
		self.devices = None
		self.epg_cache = {}
		self.data_dir = data_dir
		self.cache_need_save = False
		
		if self.data_dir:
			try:
				# load epg_cache
				with open(self.data_dir + '/epg_cache.json', "r") as file:
					self.epg_cache = json.load(file)
					self.log_function("EPG loaded from cache")
			except:
				pass
			
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
					live = item['liveTvPlayable']
					live = True # reseni nekterych nezobrazovanych kanalu?
					if item['timeShiftDuration']:
						timeshift = int(item['timeShiftDuration'])/60/24	# pocet dni zpetneho prehravani
					if live:
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
	
	def getChannelPrograms(self,ch,cache_hours=0):
		fromts = int(time())*1000
		tots = (int(time()) + (cache_hours * 3600) + 60) * 1000
		title = ""
		desc = ""
		
		if ch in self.epg_cache:
			for epg in self.epg_cache[ch]:
				if epg["start"] < fromts and epg["end"] > fromts:
					title = epg["title"]
					desc = epg["desc"]
					break
			
		if title == "":
			self.refresh_configuration()

			headers = _COMMON_HEADERS
			cookies = {"access_token": self.access_token, "deviceId": self.device_id}
			params = {"channelKey": ch, "fromTimestamp": fromts, "imageSize": "LARGE", "language": "ces", "offer": self.offer, "toTimestamp": tots}
			req = requests.get('https://app01.gtm.orange.sk/sws/server/tv/channel-programs.json', params=params, headers=headers, cookies=cookies)
			j = req.json()
			self.epg_cache[ch] = []
			for one in j:
				title = _to_string(one["name"]) + " - " + datetime.datetime.fromtimestamp(one["startTimestamp"]/1000).strftime('%H:%M') + "-" + datetime.datetime.fromtimestamp(one["endTimestamp"]/1000).strftime('%H:%M')
				self.epg_cache[ch].append({"start": one["startTimestamp"], "end": one["endTimestamp"], "title": title, "desc": one["shortDescription"]})
			title = _to_string(j[0]["name"]) + " - " + datetime.datetime.fromtimestamp(j[0]["startTimestamp"]/1000).strftime('%H:%M') + "-" + datetime.datetime.fromtimestamp(j[0]["endTimestamp"]/1000).strftime('%H:%M')
			desc = _to_string(j[0]["shortDescription"])
			self.cache_need_save = True
			
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
	
	def getVideoLink(self, name, url):
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
			result.append( {"url": url,"title": '['+quality+'] ' + name, 'bandwidth': bandwidth } )
		
		result = sorted( result, key=lambda r: r['bandwidth'], reverse=True )
		return result
