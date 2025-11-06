# -*- coding: utf-8 -*-
import os, json, traceback
import functools
from time import time, mktime
from datetime import datetime
from hashlib import md5

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

# #################################################################################################


class MagioGOChannel(object):
	def __init__(self, channel_info):
		self.id = str(channel_info['channelId'])
		self.name = channel_info['name']
		self.type = channel_info['type']
		self.archive = channel_info.get('archive', 0) // (3600 * 1000) if channel_info.get('hasArchive', False) and channel_info.get('archiveSubscription', False) else 0
		self.timeshift = channel_info.get('timeshift', 0) if channel_info.get('hasTimeshift', False) else 0
		self.picon = channel_info['logoUrl'].replace('https', 'http')
		self.adult = False
		self.preview = None
		self.epg_name = None
		self.epg_desc = None
		self.epg_start = 0
		self.epg_stop = 0
		self.epg_year = None
		self.epg_duration = None
		self.epg_id = None

	# #################################################################################################

	def set_aditional(self, info):
		preview_urls = info.get('images',[])
		if preview_urls and len(preview_urls) > 0:
			for url in preview_urls:
				if 'VERT' in url:
					self.preview = url
					break
			else:
				self.preview = preview_urls[0]

		self.adult = info.get('adult', False)

# #################################################################################################

	def set_current_epg(self, info):
		ep = info.get('episodeTitle')
		if ep:
			self.epg_name = info.get('name') + ': ' + ep
		else:
			self.epg_name = info.get('name')
		self.epg_desc = info.get('longDescription')
		self.epg_start = (info.get('start') or 0) // 1000
		self.epg_stop = (info.get('end') or 0) // 1000
		self.epg_year = info.get('creationYear')
		self.epg_duration = int(info['runtimeMinutes']) * 60 if info.get('runtimeMinutes') else None
		self.epg_id = info.get('id')

# #################################################################################################

class MagioGO(object):
	magiogo_device_types = [
		("OTT_ANDROID", "Xiaomi Mi 11"),        # 0
		("OTT_IPAD", "iPad Pro"),               # 1
		("OTT_STB", "KSTB6077"),                # 2
		("OTT_TV_ANDROID", "XR-65X95J"),        # 3
		("OTT_SKYWORTH_STB", "Skyworth"),       # 4
		("OTT_LINUX", "Web Browser"),           # 5
		("OTT_WIN", "Web Browser"),             # 6
	]

	os_version = '12.0'
	app_version = '4.1.0'

	def __init__(self, content_provider):
		self.cp = content_provider
		self.username = self.cp.get_setting('username')
		self.password = self.cp.get_setting('password')
		self.device_id = self.cp.get_setting('deviceid')
		self.access_token = None
		self.refresh_token = None
		self.access_token_life = 0
		self.log_function = self.cp.log_info
		self._ = self.cp._
		self.device = MagioGO.magiogo_device_types[int(self.cp.get_setting('devicetype'))]
		self.app_version_last_check = 0
		self.devices = None
		self.settings = None
		self.data_dir = self.cp.data_dir
		self.region = self.cp.get_setting('region').lower()
		self.common_headers = {
			"Content-type": "application/json",
			"Host": self.region + "go.magio.tv",
			"User-Agent": "okhttp/4.8.2",
		}
		self.req_session = self.cp.get_requests_session()

		self.get_last_app_version()
		self.load_login_data()
		self.refresh_login_data()
		self.user_agent_playback = 'com.telekom.magiogo/%s (Linux;Android 6.0) ExoPlayerLib/2.18.1' % self.app_version

	# #################################################################################################
	@staticmethod
	def create_device_id():
		import uuid
		return str(uuid.uuid4())

	# #################################################################################################

	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}|{}|{}".format(self.password, self.username, self.device_id, self.device[0], self.region)
		return md5( data.encode('utf-8') ).hexdigest()

	# #################################################################################################

	def get_last_app_version(self):
		try:
			if self.app_version_last_check == 0 or (self.app_version_last_check + 7800) < int(time()):
				self.__get_last_app_version()
				self.app_version_last_check = int(time())
		except:
			self.log_function(traceback.format_exc())

	# #################################################################################################

	def __get_last_app_version(self):
		from bs4 import BeautifulSoup

		response = self.req_session.get('https://apps.apple.com/sk/app/magio-tv/id550426098')

		if response.status_code != 200:
			self.log_function("Failed to get last app version: response code = %d" % response.status_code )
			return

		ver_text = BeautifulSoup(response.content, "html.parser").find('section', {'id': 'mostRecentVersion'}).find('article', {'class': 'overview'}).find('h4').get_text()

		if ver_text and ver_text.startswith('Version '):
			self.app_version = ver_text.split(' ')[1]
			self.log_function("Detected last app version is: %s" % self.app_version)
		else:
			self.log_function("Last app version string is in wrong format. This addon needs update!")


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

						if self.login_data.get('app_version') != self.app_version:
							# after app version change, there is a needing for access token renew and registration of new version
							self.access_token_life = 0
					else:
						self.access_token = None
						self.refresh_token = None
						self.access_token_life = 0
						self.log_function("Not using cached login data - wrong checksum")
			except:
				self.access_token = None
				self.refresh_token = None
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
							'refresh_token': self.refresh_token,
							'access_token_life': self.access_token_life,
							'app_version': self.app_version,
							'checksum': self.get_chsum()
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass

	# #################################################################################################

	def showError(self, msg):
		self.log_function("Magio GO API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	# #################################################################################################

	def showLoginError(self, msg):
		self.log_function("Magio GO Login ERROR: %s" % msg)
		raise LoginException(msg)

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

			resp = self.req_session.request(method, url, data=data, params=params, headers=headers)
#			dump_json_request(resp)

			if resp.status_code == 200 or (resp.status_code > 400 and resp.status_code < 500):
				try:
					return resp.json()
				except:
					return {}
			else:
				err_msg = self._("Unexpected return code from server") + ": %d" % resp.status_code
		except Exception as e:
			self.log_function("Magio GO ERROR:\n"+traceback.format_exc())
			err_msg = str(e)

		if err_msg:
			self.log_function( "Magio GO error for URL %s: %s" % (url, traceback.format_exc()))
			self.log_function( "Magio GO: %s" % err_msg )
			self.showError(err_msg)

		return None

	# #################################################################################################

	def login(self, force=False):
		if not self.username or not self.password:
			raise LoginException(self._("Login data not set"))

		self.get_last_app_version()

		params = {
			"dsid": self.device_id,
			"deviceName": self.device[1],
			"deviceType": self.device[0],
			"osVersion": self.os_version,
			"appVersion": self.app_version,
			"language": "EN"
		}

		response = self.call_magiogo_api('v2/auth/init', params=params, auth_header=False )

		if response.get("success", False) == True:
			self.access_token = response["token"]["accessToken"]
		else:
			raise LoginException(response.get('errorMessage', self._('Unknown error')))

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
			raise LoginException(response.get('errorMessage', self._('Unknown error')))

	# #################################################################################################

	def refresh_login_data(self):
		if not self.access_token or not self.refresh_token:
			# we don't have access token - do fresh login using name/password
			self.login()
			return

		if self.access_token_life > int(time()):
			return

		if self.refresh_token:
			self.get_last_app_version()

			# access token expired - get new one
			data = {
				"refreshToken": self.refresh_token,
				"deviceName": self.device[1],
				"deviceType": self.device[0],
				"osVersion": self.os_version,
				"appVersion": self.app_version,
			}
			response = self.call_magiogo_api("v2/auth/tokens", data=data, auth_header=False)

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

		ret = self.call_magiogo_api("home/deleteDevice", method = "GET", params = params )

		return ret["success"], ret.get('errorMessage', '')

	# #################################################################################################

	def get_channel_list(self, fill_epg=False):
		self.refresh_login_data()

		params = {
			"list": "LIVE",
			"queryScope": "LIVE"
		}
		ret = self.call_magiogo_api("v2/television/channels", method="GET", params=params)

		if not ret or not ret.get('success'):
			return None

		channels = []
		for ch in (ret.get('items') or []):
			channel = MagioGOChannel(ch['channel'])
			channel.set_aditional(ch.get('live') or {})

			if fill_epg:
				channel.set_current_epg(ch.get('live') or {})

			channels.append(channel)

		return channels

	# #################################################################################################

	def get_stream_link(self, stream_id, service='LIVE', prof=None):
		self.refresh_login_data()

		if not prof:
			prof = 'p' + self.cp.get_setting('stream_profile')

		params = {
			"service": service,
			"name": self.device[1],
			"devtype": self.device[0],
			"id": stream_id,
#			"prof": 'p5',   # 'p4', 'p3'
			"prof": prof,
			"ecid": "",
			"drm": "verimatrix"
		}

		response = self.call_magiogo_api("v2/television/stream-url", method = "GET", params = params)

		if response["success"] == True:
			url = response["url"]
		else:
			self.cp.log_error("Failed to resolve stream url: %s" % response.get('errorMessage', response["errorCode"]))

			if response["errorCode"] == "NO_PACKAGE":
				url = None
			else:
				raise AddonErrorException( '%s' % response.get('errorMessage', response["errorCode"]))

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

	def get_archiv_channel_programs(self, channel_id, fromts, tots):
		epg_data = self.get_channels_epg( [int(channel_id)], fromts, tots)

		cur_time = int(time())

		for epg_item in epg_data:
			if int(channel_id) == epg_item.get('channel',{}).get('channelId'):
				for one in epg_item.get('programs',[]):
					one_startts = self.magioformat_to_timestamp(one["startTime"])

					if cur_time > one_startts:
						one_endts = self.magioformat_to_timestamp(one["endTime"])

						images = one['program'].get('images')
						if images != None and len(images) > 0:
							for url in images:
								if 'VERT' in url:
									img = url
									break
							else:
								img = images[0]
						else:
							img = None

						if one['program'].get("episodeTitle"):
							title = one['program']["title"] + ': ' + one['program']["episodeTitle"]
						else:
							title = one['program']["title"]

						yield {
							'title': title,
							'id': one['program']['programId'],
							'image': img,
							'plot': one['program']["description"],
							'start': one_startts,
							'stop': one_endts,
							'duration': one['duration'],
							'year': one['program'].get('programValue', {}).get('creationYear')
						}

				break

	# #################################################################################################

	def stream_type_by_device(self):
		return 'm3u8' if self.device[0] == 'OTT_IPAD' else 'mpd'

	# #################################################################################################
