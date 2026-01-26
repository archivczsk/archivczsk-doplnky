# -*- coding: utf-8 -*-
#
import time, json, re, os
from datetime import datetime
import traceback

from hashlib import md5
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.compat import quote, urljoin
from base64 import b64encode

############### init ################

_HEADERS = {
	"User-Agent": "okhttp/4.12.0"
}

class SledovaniTV(object):
	APP_VERSION = '2.133.0'
	PLAYER_CAPABILITIES = 'vast,clientvast,alerts,people,normalize_id,category,webvtt,adaptive2'

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
		self.wv_license_url = None

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

		data = "{}|{}|{}|{}".format(self.password, self.username, self.serialid, self.APP_VERSION)
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

		if not url.startswith('http'):
			url = urljoin('https://sledovanitv.cz/api/', url)

		try:
			if data:
				resp = self.req_session.post(url, json=data, params=params, headers=self.headers)
			else:
				resp = self.req_session.get(url, params=params, headers=self.headers)

#			dump_json_request(resp)

			if resp.status_code == 200:
				ret = resp.json()

				if ret.get('data') == None and ("status" not in ret or ret['status'] == 0):
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

	def call_graphql(self, operation_name, query, variables={}):
		data = {
			'operationName': operation_name,
			'query': query.replace('\t', '').replace('\n', ' '),
			'variables': variables,
		}

		data = self.call_api('graphql', params = { 'PHPSESSID': self.sessionid }, data=data)

		for result in data.get('data',{}).values():
			return result
		else:
			return None

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

	def register_drm(self):
		params = {
			'type': 'widevine',
			'PHPSESSID': self.sessionid,
		}

		data = self.call_api('drm-registration', params = params )

		if "status" in data and data['status'] == 1:
			self.wv_license_url = data.get('info',{}).get('licenseUrl')

			if self.wv_license_url:
				if '{streamURL|base64}' not in self.wv_license_url:
					self.cp.log_error("Widevine license URL is in unsupported format - ignoring")
					self.wv_license_url = None
				else:
					self.wv_license_url = self.wv_license_url.replace('{streamURL|base64}', '{streamURL}')

	# #################################################################################################

	def get_wv_license_url(self, stream_url):
		if self.wv_license_url:
			return self.wv_license_url.format(streamURL=quote(b64encode(stream_url.encode('utf-8')).decode('utf-8')))

		return None

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
				'version': self.APP_VERSION,
				'lang': 'cs',
				'unit': 'default',
				'capabilities': self.PLAYER_CAPABILITIES
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
			'capabilities': self.PLAYER_CAPABILITIES,
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

	def get_event_link(self, eventid):
		params = {
			'format': 'm3u8',
			'eventId': eventid,
			'capabilities': self.PLAYER_CAPABILITIES,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('event-timeshift', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading event") + ": %s" % data['error'])
			return None

		return data['url'], data.get('drm') == 1

	# #################################################################################################

	def get_recording_link(self, recordid):
		params = {
			'format': 'm3u8',
			'recordId': recordid,
			'capabilities': self.PLAYER_CAPABILITIES,
			'PHPSESSID': self.sessionid
		}

		data = self.call_api('record-timeshift', params = params )
		if "status" not in data or data['status'] == 0:
			self.showError(self._("Error by loading recording") + "%s" % data['error'])
			return None

		return data['url']

	# #################################################################################################

	def get_vod_categories(self):
		query = '''query VodCategories
		{
			content(id: "vod")
			{
				subItems
				{
					__typename
					...VodCategoryContentList
				}
			}
		}
		fragment VodCategoryContentList on ContentList
		{
			nodes
			{
				id
				title
			}
		}'''

		result = self.call_graphql("VodCategories", query)
		return result['subItems']['nodes']

	# #################################################################################################

	def get_vod_category(self, category_id):
		variables = {
			"categoryId": category_id,
			"timeFrom": int(time.time()),
			"timeTo": int(time.time()),
			"posterSize": 512,
			"backdropSize":1280,
			"quality":40,
			"capabilities": self.PLAYER_CAPABILITIES,
			"format":"m3u8",
			"drmType":"widevine",
			"overrun":True
		}

		query = '''query Category($categoryId: ID!, $timeFrom: Float!, $timeTo: Float!, $posterSize: Int!, $backdropSize: Int!, $quality: Int!, $capabilities: String!, $format: String!, $drmType: String!, $overrun: Boolean!)
		{
			content(id: $categoryId)
			{
				id
				title
				subItems
				{
					__typename
					...CategoryContentList
				}
				type
			}
		}
		fragment CategoryContentList on ContentList
		{
			pageInfo
			{
				offset
				hasNextPage
			}
			nodes
			{
				__typename
				id
				type
				view
				title
				poster(format: { size: $posterSize } )
				{
					url
				}
				backdrop(format: { size: $backdropSize } )
				{
					url
				}
				availability
				{
					accessFrom
					accessTo
					accessProblem
				}
				adultRating
				{
					obsolete_forAdult
				}
				actions
				{
					id
					type
				}
				... on PvrRecording
				{
					epgTitle
				}
				... on IRecording
				{
					recordingMeta
					{
						channel
						{
							id
							title
							adultRating
							{
								obsolete_forAdult
							}
						}
						obsolete_event
						{
							id
							type
						}
					}
				}
				... on ChannelEvent
				{
					epgTitle
					start
					end
					channel
					{
						id
						type
						title
						poster(format: { size: $posterSize } )
						{
							url
						}
						adultRating
						{
							obsolete_forAdult
						}
					}
				}
				... on Channel
				{
					events(from: $timeFrom, to: $timeTo)
					{
						nodes
						{
							__typename
							... on ChannelEvent
							{
								title
								start
								end
							}
						}
					}
				}
				... on IPlayable
				{
					stream(ops: { quality: $quality format: $format capabilities: $capabilities drmType: $drmType overrun: $overrun } )
					{
						__typename
						... on StorageStream
						{
							position
							timeFrom
							timeTo
							duration
						}
					}
					watched
					{
						position
					}
				}
				... on IShow
				{
					showMeta
					{
						mdbTitleID
					}
				}
			}
		}'''

		response = self.call_graphql("Category", query, variables)
		return response['subItems']['nodes']

	# #################################################################################################

	def get_vod_item_detail(self, vod_id):
		variables = {
			"id": vod_id,
			"posterSize":512,
			"backdropSize":1280,
			"quality":40,
			"format":"m3u8",
			"capabilities": self.PLAYER_CAPABILITIES,
			"drmType":"widevine",
			"overrun":True,
			"includeMoreInfo":True
		}

		query = '''query DetailItemBasic($id: ID!, $posterSize: Int!, $backdropSize: Int!, $quality: Int!, $format: String!, $capabilities: String!, $drmType: String!, $overrun: Boolean!, $includeMoreInfo: Boolean!)
		{
			content(id: $id)
			{
				__typename
				id
				type
				view
				title
				description
				poster(format: { size: $posterSize } )
				{
					url
				}
				backdrop(format: { size: $backdropSize } )
				{
					url
				}
				availability
				{
					accessProblem
					accessFrom
					accessTo
				}
				... on IPlayable
				{
					stream(ops: { quality: $quality format: $format capabilities: $capabilities drmType: $drmType overrun: $overrun } )
					{
						__typename
						... on StorageStream
						{
							position
							timeFrom
							timeTo
							duration
							audioLangs
							{
								title
							}
							subtitleLangs
							{
								title
							}
						}
					}
					watched
					{
						position
					}
				}
				... on ChannelEvent
				{
					epgTitle
					channel
					{
						id
						title
						poster(format: { size: $posterSize } )
						{
							url
						}
						adultRating
						{
							obsolete_forAdult
						}
						type
					}
					start
					end
				}
				... on PvrRecording
				{
					epgTitle
				}
				... on IRecording
				{
					recordingMeta
					{
						channel
						{
							id
							title
							adultRating
							{
								obsolete_forAdult
							}
						}
						start
						end
						obsolete_event
						{
							id
						}
					}
				}
				... on IShow
				{
					showMeta
					{
						year
						ratingStars
						duration
						shortTitle
						genres
						{
							nodes
							{
								title
							}
						}
						mdbTitleID
						origins @include(if: $includeMoreInfo)
						{
							nodes
							{
								title
							}
						}
						actors @include(if: $includeMoreInfo)
						{
							nodes
							{
								title
							}
						}
						directors @include(if: $includeMoreInfo)
						{
							nodes
							{
								title
							}
						}
					}
				}
				subItems
				{
					nodes
					{
						__typename
						id
						... on IShow
						{
							showMeta
							{
								shortTitle
							}
						}
					}
				}
				actions
				{
					id
					title
					type
					arguments
					{
						name
						value
					}
				}
			}
		}'''

		return self.call_graphql("DetailItemBasic", query, variables)

	# #################################################################################################

	def get_vod_info(self, vod_id):
		params = {
			'entryId': vod_id,
			'detail': "events,creators,order,related,comments,categories",
			'PHPSESSID': self.sessionid,
		}

		return self.call_api('/vod-api/get-entry', params=params)['entry']

	# #################################################################################################

	def get_vod_stream(self, event_id=None, vod_id=None):
		if event_id == None:
			params = {
				'entryId': vod_id,
				'detail': "events",
				'PHPSESSID': self.sessionid,
			}

			for event in self.call_api('/vod-api/get-entry', params=params)['events']:
				event_id = event['id']
				break

		params = {
			'eventId': event_id,
			'format': 'm3u8',
			'drm': 1,
			'capabilities': self.PLAYER_CAPABILITIES,
			'quality': 40,
			'PHPSESSID': self.sessionid,
		}

		data = self.call_api('/vod-api/get-event-stream', params=params)['stream']
		return data['url'], data['drm'] == 1

	# #################################################################################################

	def get_vod_season_item(self, vod_id):
		variables = {
			"id": vod_id,
			"posterSize":512,
			"backdropSize":1280,
			"quality":40,
			"format":"m3u8",
			"capabilities":self.PLAYER_CAPABILITIES,
			"drmType":"widevine",
			"overrun":True
		}
		query = '''query SeasonItem($id: ID!, $posterSize: Int!, $backdropSize: Int!, $quality: Int!, $format: String!, $capabilities: String!, $drmType: String!, $overrun: Boolean!)
		{
			content(id: $id)
			{
				__typename id
				... on IShow
				{
					showMeta
					{
						shortTitle
					}
				}
				subItems
				{
					__typename
					...EpisodeContentListDetail
				}
			}
		}
		fragment EpisodeContentListDetail on ContentList
		{
			nodes
			{
				__typename
				id
				type
				view
				title
				description
				poster(format: { size: $posterSize } )
				{
					url
				}
				backdrop(format: { size: $backdropSize } )
				{
					url
				}
				availability
				{
					accessFrom
					accessTo
					accessProblem
				}
				... on ChannelEvent
				{
					epgTitle
					channel
					{
						id
						title
						adultRating
						{
							obsolete_forAdult
						}
					}
					start
					end
				}
				... on PvrRecording
				{
					epgTitle
				}
				... on IRecording
				{
					recordingMeta
					{
						channel
						{
							id
							title
							adultRating
							{
								obsolete_forAdult
							}
						}
						start
						end
						obsolete_event
						{
							id
						}
					}
				}
				... on IShow
				{
					showMeta
					{
						duration
						shortTitle
						episodeNo
						seasonNo
						mdbTitleID
					}
				}
				... on IPlayable
				{
					stream(ops: { quality: $quality format: $format capabilities: $capabilities drmType: $drmType overrun: $overrun } )
					{
						__typename
						... on StorageStream
						{
							position
							timeFrom
							duration
						}
					}
				}
				shortActions
				{
					id
					title
					type
					arguments
					{
						name
						value
					}
				}
			}
		}'''

		return self.call_graphql("SeasonItem", query, variables)

	# #################################################################################################
