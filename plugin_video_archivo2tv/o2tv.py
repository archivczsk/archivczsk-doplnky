# -*- coding: utf-8 -*-
#
# addon based on misanov's addon based on waladir plugin :-)
#

import os, time, json, requests, re
from datetime import datetime, date, timedelta
import traceback

import base64
from hashlib import md5

try:
	from urllib import quote
except:
	from urllib.parse import quote

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

############### init ################

_HEADER_UNITY = {
	"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0",
	"Content-Type":"application/json"
}

_HEADER = {
	"X-NanguTv-App-Version" : "Android#6.4.1",
	"User-Agent" : "Dalvik/2.1.0",
	"Accept-Encoding" : "gzip",
	"Content-Type" : "application/x-www-form-urlencoded;charset=UTF-8",
}

def _log_dummy(message):
	print('[O2TV]: ' + message )
	pass

class O2TV:
	def __init__(self, username, password, deviceid, devicename="tvbox", data_dir=None, log_function=None ):
		self.username = username
		self.password = password
		self.deviceid = deviceid
		self.devicename = devicename
		self.data_dir = data_dir
		self.log_function = log_function if log_function else _log_dummy
		self.devices = None
		self.access_token = None
		self.access_token_life = 0
		self.sdata = None
		self.tariff = None
		self.header_unity = _HEADER_UNITY
		self.header = _HEADER
		self.header["X-NanguTv-Device-Id"] = self.deviceid
		self.header["X-NanguTv-Device-Name"] = self.devicename
		self.epg_cache = {}
		self.cache_need_save = False
		self.cache_mtime = 0

		self.load_login_data()
		
		if self.access_token:
			self.header_unity["x-o2tv-access-token"] = self.access_token
			self.header["X-NanguTv-Access-Token"] = self.access_token

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
				json.dump(self.epg_cache, f)
				self.log_function("EPG saved to cache")
				self.cache_need_save = False

	# #################################################################################################

	@staticmethod
	def create_device_id():
		import random, string
		return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))

	# #################################################################################################

	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}|{}".format(self.password, self.username, self.deviceid, self.devicename)
		return md5( data.encode('utf-8') ).hexdigest()

	# #################################################################################################
	
	def showError(self, msg):
		self.log_function("O2TV API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	# #################################################################################################

	def showLoginError(self, msg):
		self.log_function("O2TV Login ERROR: %s" % msg)
		raise LoginException(msg)

	# #################################################################################################

	def call_o2_api(self, url, data=None, params=None, header=None):
		err_msg = None
		
		try:
			if data:
				resp = requests.post( url, data=data, headers=header )
			else:
				resp = requests.get( url, params=data, headers=header )
			
#			dump_json_request(resp)
			
			if resp.status_code == 200:
				try:
					return resp.json()
				except:
					return {}
			else:
				err_msg = "Neočekávaný návratový kód ze serveru: %d" % resp.status_code
		except Exception as e:
			err_msg = str(e)
		
		if err_msg:
			self.log_function( "O2API error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError(err_msg)

	# #################################################################################################

	def get_access_token(self):
		if '@' in self.username:
			post = { "username" : self.username, "password" : self.password }
			data = self.call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/login", data=post, header=self.header)
		
			if "services" in data and "remote_access_token" in data and len(data["remote_access_token"]) > 0 and "service_id" in data["services"][0] and len(data["services"][0]["service_id"]) > 0:
				remote_access_token = data["remote_access_token"]
				service_id = data["services"][0]['service_id']
		
				post = {"service_id" : service_id, "remote_access_token" : remote_access_token}
				data = self.call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/loginChoiceService", data=post, header = self.header)
		
				post = {
					"grant_type" : "remote_access_token",
					"client_id" : "tef-web-portal-etnetera",
					"client_secret" : "2b16ac9984cd60dd0154f779ef200679",
					"platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0",
					"language" : "cs",
					"remote_access_token" : str(remote_access_token),
					"authority" : "tef-sso",
					"isp_id" : "1"
				}
				
				data = self.call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data=post, header=self.header)

				self.access_token = data["access_token"]
				self.access_token_life = (int(time.time()) +  int(data["expires_in"] / 1000)) - 3600
		else:
			post = {
				"grant_type" : "password",
				"client_id" : "tef-web-portal-etnetera",
				"client_secret" : "2b16ac9984cd60dd0154f779ef200679",
				"platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0",
				"language" : "cs",
				"username" : self.username,
				"password" : self.password
			}
			
			data = self.call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data=post, header=self.header)
			
			self.access_token = data["access_token"]
			self.access_token_life = (int(time.time()) +  int(data["expires_in"] / 1000)) - 3600

		self.save_login_data()

	# #################################################################################################
	
	def refresh_configuration(self, force_refresh=False, iter=0):
		try:
			if not self.access_token or self.access_token_life < int(time.time()):
				self.get_access_token()
				self.header_unity["x-o2tv-access-token"] = self.access_token
				self.header["X-NanguTv-Access-Token"] = self.access_token
				
			if not self.tariff or force_refresh:
				try:
					data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/subscription-configuration.json", header=self.header)
				except:
					if iter == 0:
						# something failed - try once more with new access toknen
						self.access_token = None
						return self.refresh_configuration(force_refresh, iter + 1)
					else:
						raise
					
				if "isp" in data and len(data["isp"]) > 0 and "locality" in data and len(data["locality"]) > 0 and "billingParams" in data and len(data["billingParams"]) > 0 and "offers" in data["billingParams"] and len(data["billingParams"]["offers"]) > 0 and "tariff" in data["billingParams"] and len(data["billingParams"]["tariff"]) > 0:
					self.subscription = data["subscription"]
					self.isp = data["isp"]
					self.locality = data["locality"]
					self.offers = data["billingParams"]["offers"]
					self.tariff = data["billingParams"]["tariff"]
					self.devices = data["pairedDevices"]
				else:
					raise Exception( "Získávaní konfigurace selhalo" )
		except Exception as e:
			self.showLoginError(str(e))
			
	# #################################################################################################
	
	def device_remove(self,did):
		self.refresh_configuration()
		if did:
			post = {"deviceId": did}
			self.call_o2_api('https://app.o2tv.cz/sws/subscription/settings/remove-device.json', data=post, header=self.header )

	# #################################################################################################
	
	def search(self, query ):
		self.refresh_configuration()
		
		max_ts = int(time.mktime(datetime.now().timetuple()))
		
		data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/search/tv/depr/?groupLimit=1&maxEnd=" + str(max_ts*1000) + "&q=" + quote(query), header=self.header_unity)
		
		if "groupedSearch" in data and "groups" in data["groupedSearch"] and len(data["groupedSearch"]["groups"]) > 0:
			return data["groupedSearch"]["groups"]

		return []
	
	# #################################################################################################
	
	def get_channel_epg(self, ch, fromts, tots):
		self.refresh_configuration()

		post = {
			"channelKey": ch,
			"fromTimestamp": fromts * 1000,
			"imageSize": "LARGE",
			"language": "ces",
			"offer": self.offers,
			"toTimestamp": tots * 1000
		}
		
		try:
			resp = self.call_o2_api('https://app.o2tv.cz/sws/server/tv/channel-programs.json', data=post, header=self.header)
		except:
			resp = []
		
		return resp

	# #################################################################################################
	
	def get_channels(self):
		self.refresh_configuration()
		
		channels = []
			
		post = {
			"locality": self.locality,
			"tariff": self.tariff,
			"isp": self.isp,
			"language": "ces",
			"deviceType": "STB",
			"liveTvStreamingProtocol": "HLS",
			"offer": self.offers
		}
		data = self.call_o2_api(url="https://app.o2tv.cz/sws/server/tv/channels.json", data=post, header=self.header)

		purchased_channels = data['purchasedChannels']

		self.update_channels_data(data['channels'])

		for item in data["channels"].values():
			if item['channelKey'] in purchased_channels:
				if item['channelType'] != 'TV':
					continue

				picon = item['logo'].replace('https://', 'http://').replace('64x64', '220x220').replace('38x38', '220x220')
				channels.append({
						'key': item['channelKey'],
						'id': item['channelId'],
						'number': item['channelNumber'],
						'name': item['channelName'],
						'type': item['channelType'],
						'weight': item['weight'],
						'adult': 'audience' in item and item['audience'].upper() == 'INDECENT',
						'picon': picon,
						'timeshift': int(item['timeShiftDuration'] // 60) if item['timeShiftDuration'] else 0,
						'screenshot': item['screenshots'][0] if len(item['screenshots']) > 0 else None,
						'logo': item.get('logo_hi', picon),
#						'live': item.get('live')
					})
	
		return sorted(channels, key=lambda ch: ch['number'])
	
	# #################################################################################################
	
	def update_channels_data(self, channels):
		data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", header=self.header_unity)
		
		if "result" in data and len(data["result"]) > 0:
			for channel in data["result"]:
				try:
					ch = channels[ channel["channel"]['channelKey'] ]
				except:
					continue
				
				ch['logo_hi'] = "https://www.o2tv.cz/" + channel["channel"]["images"]["color"]["url"]
#				if 'live' in channel:
#					ch['live'] = channel['live']
#					ch['live']['start'] = int(ch['live']['start'] / 1000)
#					ch['live']['end'] = int(ch['live']['end'] / 1000)
#				else:
#					ch['live'] = None
	
	# #################################################################################################
	
	def get_epg_detail(self, epg_id ):
		self.refresh_configuration()
		
		epgdata = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epg_id) + "/", header=self.header_unity)

		img = None;
		if "images" in epgdata and len(epgdata["images"]) > 0:	
			img = "https://www.o2tv.cz/" + epgdata["images"][0]["cover"]
		else:
			img = None
		
		return {
			'img' : img,
			'name': epgdata.get("name"),
			'long' : epgdata.get("longDescription"),
			'short' : epgdata.get("shortDescription"),
			'start' : int(epgdata['start'] / 1000),
			'end' : int(epgdata['end'] / 1000)
		}
		
	# #################################################################################################
	
	def get_user_channel_lists(self):
		self.refresh_configuration()
		
		data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/get-user-pref.json?name=nangu.channelListUserChannelNumbers", header=self.header)
		
		result = {}
		if "listUserChannelNumbers" in data and len(data["listUserChannelNumbers"]) > 0:
			data = data["listUserChannelNumbers"]
			for list_name in data:
				result[list_name.replace('user::', '')] = list(x[0] for x in sorted(data[list_name].items(), key=lambda x : x[1]))
		
		return result
	
	# #################################################################################################
	
	def get_recordings(self):
		self.refresh_configuration()
		
		header_unity2 = self.header_unity.copy()
		header_unity2["x-o2tv-device-id"] = self.deviceid
		header_unity2["x-o2tv-device-name"] = self.devicename
		
		if not self.sdata:
			data = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/user/profile/", header = header_unity2)
			self.sdata = str(data['sdata'])
		
		header_unity2["x-o2tv-sdata"] = self.sdata
	
		data_pvr = self.call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/recordings/", header = header_unity2)
		
		return data_pvr

	# #################################################################################################
	
	def delete_recording( self, pvrProgramId ):
		self.refresh_configuration()
		
		post = {"pvrProgramId" : int(pvrProgramId)}
		
		try:
			data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-remove-program.json", data = post, header = self.header)
		except:
			return False
		
		return True

	# #################################################################################################
	
	def add_recording( self, epg_id ):
		self.refresh_configuration()
		
		post = {"epgId" : int(epg_id) }
		try:
			data = self.call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-add-program.json", data = post, header=self.header)
		except:
			return False
		
		return True

	# #################################################################################################
	
	def resolve_streams(self, post, max_bitrate=None):
		data = self.call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data=post, header=self.header)
	
		playlist = None
		url = ""
		if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
			playlist = ""
			for uris in data["uris"]:
				if uris["resolution"] == "HD":
					playlist = uris["uri"]
					break

			if playlist == "":
				playlist = data["uris"][0]["uri"]

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

		result = []
		if playlist:
			r = requests.get(playlist, headers=_HEADER).text
			for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+)\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
				bandwidth = int(m.group('bandwidth'))

				if bandwidth > max_bitrate:
					continue

				quality = ""
				if bandwidth < 1400000:
					quality = "180p"
				elif bandwidth < 2450000:
					quality = "360p"
				elif bandwidth < 4100000:
					quality = "540p"
				elif bandwidth < 6000000:
					quality = "720p"
				else:
					quality = "1080p"
				url = m.group('chunklist')
				result.append( {"url": url, "quality": quality, 'bandwidth': bandwidth } )
			
			result = sorted( result, key=lambda r: r['bandwidth'], reverse=True )
		return result
	
	# #################################################################################################
	
	def get_video_link(self, channel_key, start, end, epg_id, max_bitrate=None):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "TIMESHIFT_TV",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"channelKey" : channel_key,
			"fromTimestamp" : start,
			"toTimestamp" : end,
			"id" : epg_id,
			"encryptionType" : "NONE"
		}
		
		return self.resolve_streams(post, max_bitrate)
	
	# #################################################################################################
	
	def get_live_link(self, channel_key, max_bitrate=None):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "LIVE_TV",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"channelKey" : channel_key,
			"encryptionType" : "NONE"
		}

		return self.resolve_streams(post, max_bitrate)

	# #################################################################################################

	def get_recording_link(self, pvrProgramId, max_bitrate=None):
		self.refresh_configuration()
		
		post = {
			"serviceType" : "NPVR",
			"deviceType" : "STB",
			"streamingProtocol" : "HLS",
			"subscriptionCode" : self.subscription,
			"contentId" : pvrProgramId,
			"encryptionType" : "NONE"
		}
		
		return self.resolve_streams(post, max_bitrate)

	# #################################################################################################

	def timestamp_to_str(self, ts, format='%H:%M'):
		return datetime.fromtimestamp(ts / 1000).strftime(format)

	# #################################################################################################

	def fill_channel_epg_cache(self, ch, epg, last_timestamp=0):
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

	def get_channel_current_epg(self, ch, cache_hours=0):
		fromts = int(time.time())
		tots = fromts + (cache_hours * 3600) + 60
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
					img = epg['img']
					break

		if del_count:
			# save some memory - remove old events from cache
			del self.epg_cache[ch][:del_count]
			self.log_function("Deleted %d old events from EPG cache for channel %s" % (del_count, ch))

		# if we haven't found event in cache and epg refresh is enabled (cache_hours > 0)
		if title == "" and cache_hours > 0:
			# event not found in cache, so request fresh info from server (can be slow)
			self.log_function("Requesting EPG for channel %s from %d to %d" % (ch, fromts, tots))

			j = self.get_channel_epg(ch, fromts, tots)
			self.fill_channel_epg_cache(ch, j)

			# cache already filled with fresh entries, so the first one is current event
			title = self.epg_cache[ch][0]['title']
			desc = self.epg_cache[ch][0]['desc']
			img = self.epg_cache[ch][0]['img']

		if title == "":
			return None

		return {"title": title, "desc": desc, 'img': img}
