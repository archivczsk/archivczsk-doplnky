# -*- coding: utf-8 -*-
import re, sys, os, string, base64, json, requests
import functools
from time import time
from uuid import getnode as get_mac
from hashlib import md5
from datetime import datetime
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

_COMMON_HEADERS = {
	"X-NanguTv-Platform-Id": "b0af5c7d6e17f24259a20cf60e069c22",
	"X-NanguTv-Device-size": "normal",
	"X-NanguTv-Device-Name": "Nexus 7",
	"X-NanguTv-App-Version": "Android#7.6.3-release",
	"X-NanguTv-Device-density": "440",
	"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; Nexus 7 Build/LMY47V)",
}

def _log_dummy(message):
	print('[ORANGETV]: ' + message )
	pass

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
		
		self.load_login_data()
		self.req_session = requests.Session()
		self.req_session.request = functools.partial(self.req_session.request, timeout=10) # set timeout for all session calls

	# #################################################################################################
	@staticmethod
	def create_device_id():
		hexed = hex((get_mac() * 7919) % (2 ** 64))
		return ('0000000000000000' + hexed[2:-1])[16:]

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
						self.log_function("Login data loaded from cache")
					else:
						self.access_token = None
						self.access_token_life = 0
						self.log_function("Not using cached login data - wrong checksum")
			except:
				self.access_token = None
				self.access_token_life = 0
				
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
							'checksum': self.get_chsum()
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass

	# #################################################################################################
	
	def call_api(self, endpoint, params=None, headers=None, add_auth=True):
		if endpoint.startswith('http'):
			# full URL
			url = endpoint
		else:
			url = 'http://app01.gtm.orange.sk/sws/' + endpoint

		if headers:
			req_headers = _COMMON_HEADERS.copy()
			req_headers.update(headers)
		else:
			req_headers = _COMMON_HEADERS

		if add_auth:
			cookies = {
				"access_token": self.access_token,
				"deviceId": self.device_id
			}
		else:
			cookies = None

		response = self.req_session.get(url, params=params, headers=req_headers, cookies=cookies)
#		dump_json_request(response)
		
		if response.status_code != 200:
			self.log_function('HTTP response status code: %d\n%s' % (response.status_code, response.text))
			raise AddonErrorException('HTTP response status code: %d' % req.status_code)

		return response.json()

	# #################################################################################################
	
	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}".format(self.password, self.username, self.device_id)
		return md5( data.encode('utf-8') ).hexdigest()

	# #################################################################################################
			
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

	# #################################################################################################

	def saveEpgCache(self):
		if self.data_dir and self.cache_need_save:
			with open(self.data_dir + '/epg_cache.json', 'w') as f:
				json.dump(self.epg_cache, f)
				self.log_function("EPG saved to cache")
				self.cache_need_save = False

	# #################################################################################################

	def get_access_token_password(self):
		self.log_function('Getting Token via password...')
		
		if not self.username or not self.password:
			self.log_function('No username or password provided...')
			self.save_login_data()
			raise LoginException("No username and password provided")
		
		headers = _COMMON_HEADERS.copy()
		headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"

		data = {
			'grant_type': 'password',
			'client_id': 'orangesk-mobile',
			'client_secret': 'e4ec1e957306e306c1fd2c706a69606b',
			'isp_id': '5',
			'username': self.username,
			'password': self.password,
			'platform_id': 'b0af5c7d6e17f24259a20cf60e069c22',
			'custom': 'orangesk-mobile',
			'response_type': 'token'
		}

		response = self.req_session.post('https://oauth01.gtm.orange.sk/oauth/token', data=data, headers=headers, verify=False)

		j = response.json()
		if 'error' in j:
			error = j['error']
			self.save_login_data()
			if error == 'authentication-failed':
				self.log_function('Authentication Error')

			raise LoginException("Failed to autentificate - probably wrong username/password")
			
		self.access_token = j["access_token"]
		self.refresh_token = j["refresh_token"]
		self.access_token_life = (int(time()) +  int(j["expires_in"] / 1000)) - 3600
		self.save_login_data()

	# #################################################################################################

	def refresh_access_token(self):
		if not self.access_token or self.access_token_life < int(time()):
			self.access_token = None
			self.get_access_token_password()

	# #################################################################################################

	def device_remove(self, did):
		if not did:
			return

		self.refresh_access_token()

		params = {
			"deviceId": did
		}

		response = self.call_api('subscription/settings/remove-device.json', params=params)

	# #################################################################################################

	def refresh_configuration(self, force_reload=False):
		self.refresh_access_token()
		
		if not force_reload and self.subscription_code:
			# configuration already loaded
			return
		
		response = self.call_api('subscription/settings/subscription-configuration.json')

		if 'errorMessage' in response:
			raise Exception('Err: ' + response['errorMessage'])

		self.subscription_code = str(response["subscription"])
		self.offer = response["billingParams"]["offers"]
		self.tariff = response["billingParams"]["tariff"]
		self.locality = response["locality"]
		self.devices = response["pairedDevices"]

	# #################################################################################################

	def get_live_channels(self):
		self.refresh_configuration()
		
		channels = []

		params = {
			"locality": self.locality,
			"tariff": self.tariff ,
			"isp": "5",
			"imageSize": "LARGE",
			"language": "slo",
			"deviceType": "PC",
			"liveTvStreamingProtocol": "HLS",
			"offer": self.offer
		}

		response = self.call_api('server/tv/channels.json', params=params)
		purchased_channels = response['purchasedChannels']

		for channel in response['channels'].values():
			channel_key = channel['channelKey']
			
			if channel_key not in purchased_channels:
				continue

			if channel['timeShiftDuration']:
				timeshift = int(channel['timeShiftDuration']) // 60	# pocet hodin zpetneho prehravani
			else:
				timeshift = 0

			snapshot = channel['screenshots'][0].replace('https://', 'http://')
			if not snapshot.startswith('http://'):
				snapshot = 'http://app01.gtm.orange.sk/' + snapshot

			channels.append({
				'id': channel['channelId'],
				'key': channel_key,
				'name': channel['channelName'],
				'adult': channel.get('audience', '').upper() == 'INDECENT',
				'snapshot': snapshot,
				'logo': channel['logo'].replace('https://', 'http://').replace('64x64', '220x220'),
				'timeshift': timeshift,
				'number': channel['channelNumber'],
			})

		return sorted(channels, key=lambda ch: ch['number'])

	# #################################################################################################

	def getChannelEpg(self, ch, fromts, tots):
		self.refresh_configuration()

		params = {
			"channelKey": ch,
			"fromTimestamp": fromts * 1000,
			"imageSize": "LARGE",
			"language": "ces",
			"offer": self.offer,
			"toTimestamp": tots * 1000
		}

		try:
			return self.call_api('server/tv/channel-programs.json', params=params)
		except:
			return []

	# #################################################################################################

	def timestamp_to_str(self, ts, format='%H:%M'):
		return datetime.fromtimestamp(ts / 1000).strftime(format)

	# #################################################################################################

	def fillChannelEpgCache(self, ch, epg, last_timestamp = 0):
		ch_epg = []

		last_timestamp *= 1000

		for one in epg:
			ch_epg.append({
				"start": one["startTimestamp"] / 1000,
				"end": one["endTimestamp"] / 1000,
				"title": str(one["name"]),
				"desc": '%s - %s\n%s' % (self.timestamp_to_str(one["startTimestamp"]), self.timestamp_to_str(one["endTimestamp"]), one["shortDescription"]),
				'img': one.get('picture')
			})
			
			if last_timestamp and one["startTimestamp"] > last_timestamp:
				break

		self.epg_cache[ch] = ch_epg
		self.cache_need_save = True
	
	# #################################################################################################

	def getChannelCurrentEpg(self,ch,cache_hours=0):
		fromts = int(time())
		tots = (int(time()) + (cache_hours * 3600) + 60)
		title = ""
		desc = ""
		img = None
		del_count = 0
		
		if ch in self.epg_cache:
			for epg in self.epg_cache[ch]:
				if epg["end"] < fromts:
					# cleanup old events
					del_count += 1
				
				if epg["start"] < fromts and epg["end"] > fromts:
					title = epg["title"]
					desc = epg["desc"]
					img = epg.get("img")
					break
		
		if del_count:
			# save some memory - remove old events from cache
			del self.epg_cache[ch][:del_count]
			self.log_function("Deleted %d old events from EPG cache for channell %s" % (del_count, ch))
			
		# if we haven't found event in cache and epg refresh is enabled (cache_hours > 0)
		if title == "" and cache_hours > 0:
			# event not found in cache, so request fresh info from server (can be slow)
			self.log_function("Requesting EPG for channel %s from %d to %d" % (ch, fromts, tots))
			
			j = self.getChannelEpg(ch,fromts,tots)
			self.fillChannelEpgCache(ch, j)
			
			# cache already filled with fresh entries, so the first one is current event
			title = self.epg_cache[ch][0]['title']
			desc = self.epg_cache[ch][0]['desc']
			img = self.epg_cache[ch][0].get('img')
		
		if title == "":
			return None
		
		return {"title": title, "desc": desc, 'img': img}

	# #################################################################################################

	def getArchivChannelPrograms(self, channel_key, ts_from, ts_to):
		self.refresh_configuration()
		
		params = {
			"channelKey": channel_key,
			"fromTimestamp": ts_from * 1000,
			"imageSize": "LARGE",
			"language": "ces",
			"offer": self.offer,
			"toTimestamp": ts_to * 1000
		}

		act_time = int(time())*1000

		for program in self.call_api('server/tv/channel-programs.json', params=params):
			if act_time > program["startTimestamp"]:
				yield {
					'title': str(program["name"]),
					'epg_id': program["epgId"],
					'img': program["picture"],
					'plot': program["shortDescription"],
					'start': program["startTimestamp"] // 1000,
					'stop': program["endTimestamp"] // 1000,
				}

	# #################################################################################################

	def get_live_link(self, channel_key, max_bitrate=None):
		self.refresh_configuration()
		params = {
			"serviceType": "LIVE_TV",
			"subscriptionCode": self.subscription_code,
			"channelKey": channel_key,
			"deviceType": self.quality
		}

		return self.__get_streams(params, max_bitrate)

	def get_archive_link(self, channel_key, epg_id, ts_from, ts_to, max_bitrate=None):
		self.refresh_configuration()
		params = {
			"serviceType": "TIMESHIFT_TV",
			"contentId": epg_id,
			"subscriptionCode": self.subscription_code,
			"channelKey": channel_key,
			"deviceType": self.quality,
			"fromTimestamp": ts_from * 1000,
			"toTimestamp": ts_to * 1000
		}
		return self.__get_streams(params, max_bitrate)

	def __get_streams(self, params, max_bitrate=None):
		playlist = None
		while self.access_token:
			json_data = self.call_api('server/streaming/uris.json', params=params)
			
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

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

		result = []
		r = self.req_session.get(playlist, headers=_COMMON_HEADERS).text
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+),AUDIO="\d+"\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
			bandwidth = int(m.group('bandwidth'))

			if bandwidth > max_bitrate:
				continue

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

	
