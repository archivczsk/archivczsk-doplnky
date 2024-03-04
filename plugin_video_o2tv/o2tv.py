# -*- coding: utf-8 -*-
#
# based on waladir's KODI addon
#

import os, time, json
import traceback

import base64
from hashlib import md5

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

############### init ################

CLIENT_TAG = '9.40.0-PC'
API_VERSION = '5.4.0'
PARTNER_ID = 3201

class O2TV(object):
	def __init__(self, cp):
		self.cp = cp
		self._ = cp._
		self.base_api_url = 'https://%d.frp1.ott.kaltura.com' % PARTNER_ID
		self.deviceid = None
		self.session_data = {}
		self.services = []
		self.active_service = None

		self.req_session = self.cp.get_requests_session()

		self.load_login_data()

	# #################################################################################################

	def load_login_data(self):
		login_data = self.cp.load_cached_data('login2')
		self.deviceid = login_data.get('device_id', self.create_device_id())

		if self.get_chsum() == login_data.get('checksum'):
			self.session_data = login_data.get('session_data',{})
			self.services = login_data.get('services', [])
			self.active_service = login_data.get('active_service')
			self.cp.log_info("Login data loaded from cache")
		else:
			self.session_data = {}
			self.cp.log_info("Not using cached login data - wrong checksum")

	# #################################################################################################

	def save_login_data(self):
		# save access token
		data = {
			'device_id': self.deviceid
		}

		if self.session_data:
			data.update({
				'session_data': self.session_data,
				'services': self.services,
				'active_service': self.active_service,
				'checksum': self.get_chsum()
			})
		self.cp.save_cached_data('login2', data)

	# #################################################################################################

	def reset_login_data(self):
		self.deviceid = self.create_device_id()
		self.session_data = {}
		self.save_login_data()

	# #################################################################################################

	@staticmethod
	def create_device_id():
		import random, string
		return 'e2' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))

	# #################################################################################################

	def get_chsum(self):
		return self.cp.get_settings_checksum(('username', 'password',), self.deviceid)

	# #################################################################################################

	def showError(self, msg):
		self.cp.log_error("O2TV API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	# #################################################################################################

	def showLoginError(self, msg):
		self.cp.log_error("O2TV Login ERROR: %s" % msg)
		raise LoginException(msg)

	# #################################################################################################

	def call_o2_api(self, url, data=None, params=None, header=None, recover_ks=True):
		def is_auth_error(json_response):
			try:
				return json_response.get('result', {}).get('error', {}).get('code') == '500016'
			except:
				return False

		if recover_ks:
			self.refresh_configuration()

		err_msg = None
		headers = {
			"User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0',
			'Accept' : '*/*',
			'Content-Type' : 'application/json;charset=UTF-8',
		}

		if header != None:
			headers.update(header)

		if params == None:
			params = {
				'format': 1,
				'clientTag': CLIENT_TAG
			}

		if not url.startswith('http'):
			if url.startswith('/'):
				url = self.base_api_url + url
			else:
				url = self.base_api_url + '/api_v3/service/' + url

				# api_v3 endpoint always needs this fields in post data
				if data != None:
					if 'apiVersion' not in data:
						data['apiVersion'] = API_VERSION
					if 'clientTag' not in data:
						data['clientTag'] = CLIENT_TAG

		try:
			if data:
				resp = self.req_session.post(url, params=params, json=data, headers=headers)
			else:
				resp = self.req_session.get(url, params=params, headers=headers)

#			try:
#				dump_json_request(resp)
#			except:
#				pass

			if resp.status_code >= 200 and resp.status_code < 400:
				try:
					json_response = resp.json()
				except:
					self.cp.log_exception()
					json_response = {}

				# check for 'ks expired' error and recover if possible
				if recover_ks and '/api_v3/' in url and is_auth_error(json_response):
					self.refresh_configuration(True)

					# fill new ks in request data
					if 'ks' in data:
						data['ks'] = self.get_active_service_ks()

					return self.call_o2_api(url, data, params, header, False)
				else:
					return json_response

			else:
				return { 'err': self._("Unexpected return code from server") + ": %d" % resp.status_code }

		except Exception as e:
			self.cp.log_exception()
			err_msg = str(e)

		if err_msg:
			self.cp.log_error( "O2TV 2.0 API error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError(err_msg)

	# #################################################################################################

	def get_access_token(self):
		post = {
			'language' : '*',
			'partnerId' : PARTNER_ID,
		}

		response = self.call_o2_api( 'ottuser/action/anonymousLogin', data=post, recover_ks=False)

		# request Kaltura session ID
		if 'err' in response or response.get('result',{}).get('objectType') != 'KalturaLoginSession':
			raise LoginException(response.get('err', self._('Failed to get login session')))

		self.session_data['ks'] = response['result']['ks'] # store Kaltura session ID
		self.session_data['ks_expiry'] = response['result']['expiry']

		# login to O2
		post = {
			'username' : self.cp.get_setting('username'),
			'password' : self.cp.get_setting('password'),
			'udid' : self.deviceid,
			'service' : 'https://www.new-o2tv.cz/'
		}

		response = self.call_o2_api('https://login-a-moje.o2.cz/cas-external/v1/login', params={}, data=post, recover_ks=False)
		if 'err' in response or not 'jwt' in response or not 'refresh_token' in response:
			raise LoginException(self._("Login to O2 TV 2.0 failed. Have you been already migrated?"))

		self.session_data['jwt'] = response['jwt']
		self.save_login_data()

	# #################################################################################################

	def login_to_service(self, service):
		post = {
			'language' : 'ces',
			'ks' : self.session_data.get('ks'),
			'partnerId' : PARTNER_ID,
			'username' : 'NONE',
			'password' : 'NONE',
			'extraParams' : {
				'token' : {
					'objectType' : 'KalturaStringValue',
					'value' : self.session_data.get('jwt')
				},
				'loginType' : {
					'objectType' : 'KalturaStringValue',
					'value' : 'accessToken'
				},
				'brandId' : {
					'objectType' : 'KalturaStringValue',
					'value' : '22'
				},
				'externalId' : {
					'objectType' : 'KalturaStringValue',
					'value' : service['id']
				}
			},
			'udid' : self.deviceid,
		}
		response = self.call_o2_api('ottuser/action/login', data=post, recover_ks=False)

		if 'err' in response or response.get('result', {}).get('objectType') != 'KalturaLoginResponse' or not 'loginSession' in response.get('result', {}):
			raise LoginException("Failed to login to {service_name} service".format(service_name=service['name']))

		login_session = response['result']['loginSession']

		service['ks_expiry'] = login_session['expiry']
		service['ks_refresh_token'] = login_session['refreshToken']
		service['ks'] = login_session['ks']

		post = {
			'appToken':{
				'objectType': 'KalturaAppToken'
			},
			'language' : 'ces',
			'ks' : login_session['ks']
		}
		response = self.call_o2_api('apptoken/action/add', data=post, recover_ks=False)

		if 'err' in response or response.get('result', {}).get('objectType') != 'KalturaAppToken':
			raise LoginException("Failed to register access token for {service_name} service".format(service_name=service['name']))

		service['token'] = response['result']['token']

		return service

	# #################################################################################################

	def refresh_configuration(self, force_refresh=False, iter=0):
		try:
			if not self.session_data.get('jwt') or not self.session_data.get('ks') or self.session_data.get('ks_expiry', 0) < int(time.time()):
				self.get_access_token()

			need_save = False
			for service in self.services:
				if service['id'] == self.active_service:
					if service.get('ks_expiry', 0) < int(time.time()):
						self.login_to_service(service)
						need_save = True
					break

			if need_save:
				self.save_login_data()

			if not self.services or force_refresh:
				self.services = []
				# load available services
				try:
					post = {
						"intent":"Service List",
						"adapterData": [
							{
								"_allowedEmptyArray":[],
								"_allowedEmptyObject":[],
								"_dependentProperties":{},
								"key":"access_token",
								"value":self.session_data.get('jwt'),
								"relatedObjects":{}
							},
							{
								"_allowedEmptyArray":[],
								"_allowedEmptyObject":[],
								"_dependentProperties":{},
								"key":"pageIndex",
								"value":"0",
								"relatedObjects":{}
							},
							{
								"_allowedEmptyArray":[],
								"_allowedEmptyObject":[],
								"_dependentProperties":{},
								"key":"pageSize",
								"value":"100",
								"relatedObjects":{}
							}
						],
						"ks": self.session_data.get('ks'),
					}
					response = self.call_o2_api('/api/p/%d/service/CZ/action/Invoke' % PARTNER_ID, data=post, recover_ks=False)

					if 'err' in response or not 'service_list' in response.get('result', {}).get('adapterData', {}):
						raise LoginException("Failed to get service list")

				except:
					if iter == 0:
						# something failed - try once more
						self.session_data = {}
						return self.refresh_configuration(force_refresh, iter + 1)
					else:
						raise
				else:
					services = json.loads(response['result']['adapterData']['service_list']['value'])

					# store services and get access token for each one
					for one in services['ServicesList']:
						for service_name, service_id in one.items():
							if len(service_name) > 0:
								self.services.append({
									'name': service_name,
									'id': service_id,
								})

				if len(self.services) > 0:
					for i, service in enumerate(self.services):
						if service['id'] == self.active_service:
							self.login_to_service(self.services[i])
							break
					else:
						# we don't have specified active service - choose the first one ...
						service = self.services[0]
						self.active_service = service['id']
						self.login_to_service(service)

				self.save_login_data()

		except Exception as e:
			self.cp.log_exception()
			self.showLoginError(str(e))


	# #################################################################################################

	def activate_service(self, service_id):
		if service_id == self.active_service:
			return

		for service in self.services:
			if service['id'] == service_id:
				self.active_service = service_id
				self.refresh_configuration(True)
				break

	# #################################################################################################

	def call_list_api(self, filter_data, additional_data=None):
		result = []

		pager = {
			"objectType":"KalturaFilterPager",
			"pageSize":500,
			"pageIndex":1
		}

		post = {
			"language":"ces",
			"ks": self.get_active_service_ks(),
			"filter" : filter_data,
			"pager": pager
		}

		if additional_data:
			post.update(additional_data)

		fetch = True
		while fetch == True:
			response = self.call_o2_api('asset/action/list', data=post)
			if 'err' in response or not 'result' in response or not 'totalCount' in response['result']:
				fetch = False
			else:
				total_count = response['result']['totalCount']
				if total_count > 0:
					for object in response['result']['objects']:
						result.append(object)
					if total_count == len(result):
						fetch = False
					else:
						pager['pageIndex'] = pager['pageIndex'] + 1
						post['pager'] = pager
				else:
					fetch = False
		return result

	# #################################################################################################

	def get_devices(self):
		post = {
			"language":"ces",
			"ks": self.get_active_service_ks(),
		}

		response = self.call_o2_api('household/action/get', data=post)

		ret = []
		for dev_family in response.get('result', {}).get('deviceFamilies', []):
			for device in dev_family['devices']:
				ret.append({
					'name': device['name'],
					'type': dev_family['name'],
					'id': device['udid'],
					'activatedOn': device['activatedOn'],
					'this_one': device['udid'] == self.deviceid
				})

		return ret


	# #################################################################################################

	def device_remove(self, did):
		if not did:
			return

		post = {
			"language":"ces",
			"ks": self.get_active_service_ks(),
			"udid": did
		}

		response = self.call_o2_api('householddevice/action/delete', data=post)

		return response.get('result', False)

	# #################################################################################################

	def search(self, query ):
		filer_data = {
			"objectType":"KalturaChannelFilter",
			"orderBy":"NAME_ASC",
			"kSql":"(and name^'" + query +  "')",
			"idEqual":355960
		}

		ret = []
		for one in self.call_list_api(filer_data):
			if 'linearAssetId' in one:
				epg = self.convert_epg_entry(one)
				if epg != None:
					ret.append(epg)

		return ret

	# #################################################################################################

	def get_channel_epg(self, channel_id, fromts, tots):
		filer_data = {
			"objectType": "KalturaSearchAssetFilter",
			"orderBy": "START_DATE_ASC",
			"kSql": "(and linear_media_id:'%s' end_date >= '%s' start_date  <= '%s' asset_type='epg' auto_fill= true)" % (channel_id, str(fromts), str(tots)),
		}

		try:
			resp = self.call_list_api(filer_data)
		except:
			self.cp.log_exception()
			resp = []

		ret = []
		for one in resp:
			epg = self.convert_epg_entry(one)
			if epg != None:
				ret.append(epg)

		return ret

	# #################################################################################################

	def get_current_epg(self, channels=None):
		cur_ts = int(time.time())

		if channels:
			channels_query = '(or ' + ' '.join(['linear_media_id: %d' % int(ch) for ch in channels]) + ')'
		else:
			channels_query = ''

		filer_data = {
			"objectType": "KalturaSearchAssetFilter",
			"orderBy": "START_DATE_ASC",
			"kSql": "(and %s start_date <= '%s' end_date  >= '%s' asset_type='epg' auto_fill= true)" % (channels_query, str(cur_ts), str(cur_ts)),
		}

		try:
			resp = self.call_list_api(filer_data)
		except:
			self.cp.log_exception()
			resp = []


		ret = {}
		for one in resp:
			epg = self.convert_epg_entry(one)
			if epg != None:
				ret[one['linearAssetId']] = epg

		return ret

	# #################################################################################################

	def get_channels(self):
		self.refresh_configuration()

		channels = []
		service = self.get_service_by_id(self.active_service)

		filer_data = {
			"objectType":"KalturaSearchAssetFilter",
			"kSql":"(and asset_type='607' (or entitled_assets='entitledSubscriptions' entitled_assets='free') )"
		}

		for channel in self.call_list_api(filer_data):
			if 'ChannelNumber' in channel['metas']:
				if 'tags' in channel and len(channel['tags']) > 0 and 'Genre' in channel['tags'] and len(channel['tags']['Genre']) > 0 and channel['tags']['Genre']['objects'][0]['value'] == 'radio':
					continue

				logo = None
				picon = None
				for i in channel.get('images', []):
					if i.get('ratio') == '2x3':
						logo = i.get('url','') + '/height/720/width/480'

					if i.get('ratio') == '16x9':
						picon = i.get('url')
						if picon and not picon.endswith('.png'):
							picon = picon + '.png'

				channels.append({
					'key': str(channel['id']),
					'id': channel['id'],
					'service': service['id'],
					'number' : int(channel['metas']['ChannelNumber']['value']),
					'name' : channel['name'],
					'type' : 'TV',
					'adult' : channel['metas']['Adult']['value'],
					'picon' : picon,
					'timeshift': 7 * 24,
					'logo': logo
				})

		return sorted(channels, key=lambda ch: ch['number'])

	# #################################################################################################

	def get_recordings(self):
		additional_data = {
			"responseProfile": {
				"objectType":"KalturaOnDemandResponseProfile",
				"relatedProfiles": [
					{
						"objectType": "KalturaDetachedResponseProfile",
						"name": "group_result",
						"filter": {
							"objectType": "KalturaAggregationCountFilter"
						}
					}
				]
			}
		}

		filter_data = {
			"objectType": "KalturaSearchAssetFilter",
			"orderBy": "START_DATE_DESC",
			"kSql": "(and asset_type='recording' start_date <'0' end_date < '-900')",
			"groupBy": [
				{
					"objectType": "KalturaAssetMetaOrTagGroupBy",
					"value":"SeriesID"
				}
			],
			"groupingOptionEqual": "Include"
		}

		return self.call_list_api(filter_data, additional_data)

	# #################################################################################################

	def get_future_recordings(self):
		filer_data = {
			"objectType":"KalturaScheduledRecordingProgramFilter",
			"orderBy":"START_DATE_ASC",
			"recordingTypeEqual":"single"
		}

		return self.call_list_api(filer_data)

	# #################################################################################################

	def delete_recording( self, rec_id, future=False ):
		post = {
			"language": "ces",
			"ks": self.get_active_service_ks(),
			"id": int(rec_id)
		}

		if future:
			action = 'cancel'
		else:
			action = 'delete'

		response = self.call_o2_api('recording/action/' + action, data = post)
		return response.get('result',{}).get('status') in ('DELETED', 'CANCELED')

	# #################################################################################################

	def add_recording( self, epg_id ):
		post = {
			"language": "ces",
			"ks": self.get_active_service_ks(),
			"recording": {
				"objectType": "KalturaRecording",
				"assetId": epg_id
			}
		}

		response = self.call_o2_api('recording/action/add', data = post)
		return response.get('result',{}).get('status') in ('SCHEDULED', 'RECORDED')


	# #################################################################################################

	def get_service_by_id(self, service_id=None):
		for service in self.services:
			if service['id'] == service_id:
				return service

		return None

	# #################################################################################################

	def get_active_service_ks(self):
		service = self.get_service_by_id(self.active_service)

		if service:
			return service.get('ks')

		return None

	# #################################################################################################

	def pin_validate(self, pin):
		post = {
			"language":"ces",
			"ks": self.get_active_service_ks(),
			"pin":str(pin),
			"type":"parental",
		}

		response = self.call_o2_api('pin/action/validate', data=post)
		if response.get('result', False) != True:
			return False

		return True

	# #################################################################################################

	def get_stream_url(self, asset_id, asset_type, context):
		post = {
			"assetId":asset_id,
			"assetType":asset_type,
			"contextDataParams":{
				"objectType":"KalturaPlaybackContextOptions",
				"context":context,
				"streamerType":"mpegdash",
				"urlType":"DIRECT"
			},
			"ks":self.get_active_service_ks()
		}

		data = self.call_o2_api('asset/action/getPlaybackContext',data=post)

		if 'sources' not in data.get('result', {}):
			raise Exception("Failed to resolve stream address")

		sources = data['result']['sources']

		stream_types = []
		url = None
		for source in sources:
			if source['type'] == 'DASH':
				url = source['url']
				break
			else:
				stream_types.append(source['type'])
		else:
			raise AddonErrorException(self._("Unsupported stream type") + ': %s' % ', '.join(stream_types) )

		return url

	# #################################################################################################

	def get_proxy_live_link(self, channel_key):
		url = self.cp.http_endpoint + '/playlive/' + base64.b64encode(str(channel_key).encode("utf-8")).decode("utf-8") + '/index.mpd'
		return url

	# #################################################################################################

	def get_live_link(self, channel_key):
		return self.get_stream_url(int(channel_key), 'media', 'PLAYBACK')

	# #################################################################################################

	def get_proxy_archive_link(self, epg_id):
		url = self.cp.http_endpoint + '/playarchive/' + base64.b64encode(str(epg_id).encode("utf-8")).decode("utf-8") + '/index.mpd'
		return url

	# #################################################################################################

	def get_archive_link(self, epg_id):
		return self.get_stream_url(int(epg_id), 'epg', 'CATCHUP')

	# #################################################################################################

	def get_proxy_startover_link(self, channel_key):
		url = self.cp.http_endpoint + '/playstartover/' + base64.b64encode(str(channel_key).encode("utf-8")).decode("utf-8") + '/index.mpd'
		return url

	# #################################################################################################

	def get_startover_link(self, channel_key):
		channel_id = int(channel_key)
		epg = self.get_current_epg([channel_id])

		return self.get_stream_url(epg[channel_id]['id'], 'epg', 'START_OVER')

	# #################################################################################################

	def get_proxy_recording_link(self, rec_id):
		url = self.cp.http_endpoint + '/playrec/' + base64.b64encode(str(rec_id).encode("utf-8")).decode("utf-8") + '/index.mpd'
		return url

	# #################################################################################################

	def get_recording_link(self, rec_id):
		return self.get_stream_url(int(rec_id), 'recording', 'PLAYBACK')

	# #################################################################################################

	def convert_epg_entry(self, epg_entry):
		img = None
		if epg_entry.get("startDate") == None or epg_entry.get("endDate") == None:
			self.cp.log_error("Invalid epg_entry: %s" % str(epg_entry))
			return None

		for i in epg_entry.get('images', []):
			img = i.get('url')

			if i.get('ratio') == '2x3':
				img = i.get('url','') + '/height/720/width/480'
				break

		mosaic_id = None
		mosaic_name = None
		for mitem in epg_entry.get('tags',{}).get('MosaicInfo',{}).get('objects',[]):
			if 'MosaicProgramExternalId' in mitem['value']:
				mosaic_id = mitem['value'].replace('MosaicProgramExternalId=', '')
				break


		return {
			"start": epg_entry["startDate"],
			"end": epg_entry["endDate"],
			"title": str(epg_entry.get("name", '')),
			"desc": epg_entry.get("description",''),
			'img': img,
			'id': epg_entry['id'],
			'channel_id': epg_entry['linearAssetId'],
			'mosaic_id': mosaic_id
		}

	# #################################################################################################

	def get_mosaic_info(self, mosaic_id, live=False):
		filer_data = {
			"objectType":"KalturaSearchAssetFilter",
			"orderBy": "START_DATE_ASC",
			"kSql":"(and IsMosaicEvent='1' MosaicInfo='mosaic' (or externalId='" + str(mosaic_id) + "'))"
		}

		for epg_entry in self.call_list_api(filer_data):
			ret = self.convert_epg_entry(epg_entry)
			if ret == None:
				continue

			ret['mosaic_info'] = []
			for minfo in epg_entry.get('tags',{}).get('MosaicChannelsInfo',{}).get('objects',[]):
				title = None
				prog_ext_id = None
				ch_ext_id = None
				for item in minfo['value'].split(','):
					key, val = item.split('=')
					if key == 'Title':
						title = val
					elif key == 'ChannelExternalId' and live:
						ch_ext_id = val
					elif key == 'ProgramExternalID' and not live:
						prog_ext_id = val

				epg_id = self.get_external_resource_info(ch_ext_id or prog_ext_id).get('id')

				if title and epg_id:
					ret['mosaic_info'].append({
						'title': title,
						'id': epg_id
					})

			return ret

		return {}

	#################################################################################################

	def get_external_resource_info(self, ext_id):
		filer_data = {
			"objectType":"KalturaSearchAssetFilter",
			"orderBy":"START_DATE_ASC",
			"kSql":"(or externalId='" + str(ext_id) + "')"
		}

		for epg_entry in self.call_list_api(filer_data):
			return epg_entry

		return {}

	#################################################################################################
