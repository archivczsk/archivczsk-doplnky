# -*- coding: utf-8 -*-
#
import time, json, re
from datetime import datetime
import traceback

from hashlib import md5
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

############### init ################

_HEADERS = {
	"User-Agent": "okhttp/3.12.0"
}

class SledovaniTV:
	def __init__(self, content_provider):
		self.cp = content_provider
		self.username = self.cp.get_setting('username')
		self.password = self.cp.get_setting('password')
		self.pin = self.cp.get_setting('pin')
		self.serialid = self.cp.get_setting('serialid')
		self.sessionid = None
		self.data_dir = self.cp.data_dir
		self.log_function = self.cp.log_info
		self._ = self.cp._
		self.headers = _HEADERS

		self.load_login_data()
		self.req_session = self.cp.get_requests_session()

	# #################################################################################################
	@staticmethod
	def create_serialid():
		import random
		return ''.join(random.choice('0123456789abcdef') for n in range(40))

	# #################################################################################################

	def get_chsum(self):
		if not self.username or not self.password or len(self.username) == 0 or len( self.password) == 0:
			return None

		data = "{}|{}|{}".format(self.password, self.username, self.serialid)
		return md5( data.encode('utf-8') ).hexdigest()

	# #################################################################################################

	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)

					if self.get_chsum() == login_data.get('checksum'):
						self.sessionid = login_data['access_token']
						self.log_function("Login data loaded from cache")
					else:
						self.sessionid = None
						self.log_function("Not using cached login data - wrong checksum")
			except:
				self.sessionid = None

	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				if self.sessionid:
					# save access token
					with open(self.data_dir + '/login.json', "w") as f:
						data = {
							'access_token': self.sessionid,
							'checksum': self.get_chsum()
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass

	# #################################################################################################

	def showError(self, msg):
		self.log_function("SLEDOVANI.TV API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	# #################################################################################################

	def showLoginError(self, msg):
		self.log_function("SLEDOVANI.TV Login ERROR: %s" % msg)
		raise LoginException(msg)

	# #################################################################################################

	def call_api(self, url, data=None, params=None, enable_retry=True ):
		err_msg = None

		log_file = url

		if not url.startswith('http'):
			url = 'https://sledovanitv.cz/api/' + url

		try:
			if data:
				resp = self.req_session.post(url, data=data, params=params, headers=self.headers)
			else:
				resp = self.req_session.get(url, params=params, headers=self.headers)

#			dump_json_request(resp)

			if resp.status_code == 200:
				ret = resp.json()

				if "status" not in ret or ret['status'] == 0:
					if ret['error'] == 'not logged' and enable_retry:
						self.pair_device()
						self.pin_unlock()
						enable_retry = False

						if params != None and 'PHPSESSID' in params:
							params['PHPSESSID'] = self.sessionid

						if data != None and 'PHPSESSID' in data:
							data['PHPSESSID'] = self.sessionid

						return self.call_api(url, data, params, enable_retry)

				return ret
			else:
				err_msg = self._('Unexpected return code from server') + ': %d' % resp.status_code
		except Exception as e:
			err_msg = str(e)

		if err_msg:
			self.log_function("Sledovani.tv error for URL %s:\n%s" % (url, traceback.format_exc()))
			self.showError(err_msg)

	# #################################################################################################

	def check_pairing(self):
		if self.sessionid:
			data = self.call_api('content-home', params = { 'PHPSESSID': self.sessionid } )

		if not self.sessionid or "status" not in data or data['status'] == 0:
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
				self.showLoginError(self._("Wrong PIN code"))
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

		if "status" not in data or data['status'] == 0:
			self.sessionid = None
			self.save_login_data()
			self.showLoginError(self._("Login failed") + ": %s" % data['error'])
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
			if "status" not in data or data['status'] == 0:
				self.sessionid = None
				self.save_login_data()
				self.showLoginError(self._("Login failed") + ": %s" % data['error'])
				return False

			if "PHPSESSID" in data:
				self.sessionid = data["PHPSESSID"]
				self.save_login_data()

				params = {
					"PHPSESSID": self.sessionid
				}

				self.call_api("keepalive", params = params, enable_retry=False )
			else:
				self.sessionid = None
				self.save_login_data()
				self.showLoginError(self._("Login failed") + ": no session")
				return False
		else:
			self.sessionid = None
			self.save_login_data()
			self.showLoginError(self._("Login failed") + ": no deviceid")

			return False

		return True

	# #################################################################################################

	def get_devices(self):
		params = {
			'PHPSESSID': self.sessionid,
		}

		data = self.call_api('get-devices', params = params )

		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading list of devices") + ": %s" % data['error'])
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

		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading channel list") + ": %s" % data['error'])
			return False

		channels = []
		if 'info' in data and 'items' in data['info']:
			catitle = "["+data['info']['title']+"] " if 'title' in data['info'] else ""
			for item in data['info']['items']:
				if item['events'][0]['availability'] != "timeshift":
					continue

				desc = item["description"] if 'description' in item else ""
				thumb = item["poster"] if 'poster' in item else None

				channels.append({
					'title': item["title"],
					'channel': item['events'][0]["channel"].upper(),
					'start': self.convert_time(item['events'][0]["startTime"]),
					'end': self.convert_time(item['events'][0]["endTime"]),
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

						desc = item.get("description","")
						thumb = item.get("poster")
						duration = item['events'][0].get('duration')

						channels.append({
							'title': item["title"],
							'channel': item['events'][0]["channel"].upper(),
							'start': self.convert_time(item['events'][0]["startTime"]),
							'end': self.convert_time(item['events'][0]["endTime"]),
							'eventid':  item['events'][0]['eventId'],
							'thumb': thumb,
							'plot': catitle+desc,
							'duration': duration,
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

		if "status" not in epgdata or epgdata['status'] == 0:
			self.showError(self._("Error by loading EPG") + ": %s" % epgdata['error'])
			epgdata = []

		return epgdata.get('events', [])

	# #################################################################################################

	def epg_event_is_garbage(self, event):
		tr = event['startTime'][11:] + ' - ' + event['endTime'][11:]

		return event['title'] in ('Vysílání', 'Vysielanie', 'Vysílání ' + tr, 'Vysielanie ' + tr, tr)

	# #################################################################################################

	def get_epg(self, ts_from=None, ts_to=None):

		if ts_from == None:
			ts_from = int(time.time())

		if ts_to == None:
			ts_to = ts_from + 3600

		params = {
			'time': datetime.fromtimestamp(ts_from).strftime("%Y-%m-%d %H:%M"),
			'duration': int((ts_to - ts_from) // 60),
			'detail': 'description,poster',
			'allowOrder': True,
			'PHPSESSID': self.sessionid
		}

		epgdata = self.call_api("epg", params=params)

		if "status" not in epgdata or epgdata['status'] == 0:
			self.showError(self._("Error by loading EPG") + ": %s" % epgdata['error'])
			epgdata = {}

		return epgdata.get('channels',{})

	# #################################################################################################

	def get_channels(self):
		params = {
			'uuid': self.serialid,
			'format': 'm3u8',
			'quality': 40,
			'drm': 'widevine',
			'capabilities': 'adaptive2',
			'cast': 'chromecast',
			'PHPSESSID': self.sessionid,
		}

		data = self.call_api("playlist", params=params)

		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading channel list") + ": %s" % data['error'])
			return []

		channels = []

		for channel in data.get('channels', []):
			if channel['locked'] != 'none' and channel['locked'] != 'pin':
				continue

			channels.append({
				'id': channel['id'],
				'name': channel['name'],
				'url': channel['url'].replace('https://', 'http://'),
				'adult': channel['locked'] == 'pin',
				'type': channel['type'],
				'picon': channel['logoUrl'],
				'timeshift': channel['timeshiftDuration'] // 3600 if channel.get('timeshiftDuration') else 0
			})

		return channels

	# #################################################################################################

	def get_recordings(self):
		params = {
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('get-pvr', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading recordings") + ": %s" % data['error'])
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
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by deleting recording") + ": %s" % data['error'])
			return False

		return True
	# #################################################################################################

	def add_recording( self, eventid ):
		params = {
			'eventId': eventid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('record-event', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by setting recording") + ": %s" % data['error'])
			return False

		return True

	# #################################################################################################

	def resolve_streams(self, url, max_bitrate=None ):
		try:
			req = self.req_session.get(url)
		except:
			self.showError(self._("Error by loading video. If it's red, the check PIN code."))
			return

		if req.status_code != 200:
			self.showError(self._("Error by loading video"))
			return

		streams = []

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

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
			stream_info['quality'] = stream_info.get('resolution', 'x720').split('x')[1] + 'p'
			if int(stream_info['bandwidth']) <= max_bitrate:
				streams.append(stream_info)

		return sorted(streams, key=lambda i: int(i['bandwidth']), reverse=True)

	# #################################################################################################

	def get_live_link(self, url, max_bitrate=None):
		return self.resolve_streams(url, max_bitrate)

	# #################################################################################################

	def get_event_link(self, eventid, max_bitrate=None):
		params = {
			'format': 'm3u8',
			'eventId': eventid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('event-timeshift', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading event") + ": %s" % data['error'])
			return None

		return self.resolve_streams(data['url'], max_bitrate)

	# #################################################################################################

	def get_recording_link(self, recordid, max_bitrate=None):
		params = {
			'format': 'm3u8',
			'recordId': recordid,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('record-timeshift', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading recording") + "%s" % data['error'])
			return None

		return self.resolve_streams(data['url'], max_bitrate)

	# #################################################################################################
