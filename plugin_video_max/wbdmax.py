# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
import uuid
from time import time
import json

class Status204(Exception):
	pass

# ##################################################################################################################

DUMP_API_REQUESTS = False

json_num = 0

def dump_json(obj, name ):
	if not DUMP_API_REQUESTS:
		return

	global json_num
	json_num += 1

	with open('/tmp/processed_{:03d}_'.format(json_num) + name.replace('/', '_') + '.json', 'w') as f:
		json.dump(obj, f)

# ##################################################################################################################

class WBDMax(object):
	BASE_URL = 'https://default.any-any.prd.api.discomax.com'
	CLIENT_ID = 'b6746ddc-7bc7-471f-a16c-f6aaf0c34d26'
	SITE_ID = 'beam'
	BRAND_ID = 'beam'
	REALM = 'bolt'
	APP_VERSION = '4.0.1'
	PAGE_SIZE = 100

	HEADERS = {
		'x-disco-client': 'ANDROIDTV:9:{}:{}'.format(SITE_ID, APP_VERSION),
		'x-disco-params': 'realm={},bid={},features=ar'.format(REALM, BRAND_ID),
		'user-agent': 'androidtv {}/{} (android/9; en-NZ; SHIELD Android TV-NVIDIA; Build/1)'.format(SITE_ID, APP_VERSION),
	}

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(self.HEADERS)
		self.login_data = {}
		self.config = {}
		self.temp_access_token = None
		self.next_config_update = 0
		self.load_login_data()

		if DUMP_API_REQUESTS:
			# patch requests to dump requests/responses send to API
			self.req_session.request_orig = self.req_session.request
			def request_and_dump(*args, **kwargs):
				response = self.req_session.request_orig(*args, **kwargs)
				dump_json_request(response)
				return response

			self.req_session.request = request_and_dump

	# ##################################################################################################################

	def reset_login_data(self):
		self.login_data = {
			'device_id': self.login_data.get('device_id')
		}
		self.save_login_data()

	# ##################################################################################################################

	def load_login_data(self):
		self.login_data = self.cp.load_cached_data('login')

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def need_login(self):
		return self.login_data.get('access_token') == None

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, method=None, headers={}, ignore_error=False, ignore_204=True):
		if not self.login_data.get('device_id'):
			self.login_data['device_id'] = str(uuid.uuid1())

		xheaders = {
			'x-device-info': '{}/{} (NVIDIA/SHIELD Android TV; android/9-mdarcy-userdebug; {}/{})'.format(self.SITE_ID, self.APP_VERSION, self.login_data['device_id'], self.CLIENT_ID),
		}

		access_token = self.login_data.get('access_token') or self.temp_access_token
		if access_token:
			xheaders['Authorization'] = 'Bearer ' + access_token

		xheaders.update(headers)

		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = self._endpoint(endpoint)

		if method == None:
			if data != None:
				method = 'POST'
			else:
				method = 'GET'

		resp = self.req_session.request(method=method, url=url, params=params, json=data, headers=xheaders)

		try:
			resp_json = resp.json()
		except:
			if resp.status_code == 204:
				if ignore_204:
					resp_json = {}
				else:
					raise Status204()
			else:
				raise AddonErrorException(self.cp._("No response received from server."))

		if isinstance(resp_json, type({})) and resp_json.get('errors',[{}])[0].get('code') == 'invalid.token':
			self.reset_login_data()
			raise LoginException(self._("Login data expired. Do new pairing of this device with your account."))

		if not resp.ok:
			if ignore_error == False:
				msg = resp_json.get('errors',[{}])[0].get('detail')

				if not msg and resp_json.get('type') == 'Error':
					msg = data.get('message')

				if msg:
					raise AddonErrorException(msg)
				else:
					raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

		return resp_json

	# ##################################################################################################################

	def update_config(self, force=False):
		if self.need_login() and self.temp_access_token == None:
			data = self.call_api(self.BASE_URL + '/token', params={ 'realm': self.REALM }, headers = {'Authorization': None})
			self.temp_access_token = data['data']['attributes']['token']

		if force or (self.next_config_update < int(time())):
			self.config = self.call_api(self.BASE_URL + '/session-context/headwaiter/v1/bootstrap', data={})
			self.next_config_update = int(time()) + 1800

	# ##################################################################################################################

	def _endpoint(self, path='/'):
		self.update_config()

		matches = []
		for row in self.config['endpoints']:
			kwargs = {}
			for key in self.config['routing']:
				kwargs[key] = self.config['routing'][key]
			base_url = self.config['apiGroups'][row['apiGroup']]['baseUrl'].format(**kwargs)

			if path.lower() == row['path'].lower():
				return base_url + path
			elif path.startswith(row['path']):
				matches.append([row['path'], base_url])

		if not matches:
			raise Exception('No base url found for "{}"'.format(path))

		matches = sorted(matches, key=lambda x: len(x[0]), reverse=True)
		return matches[0][1] + path

	# ##################################################################################################################

	def get_device_code(self, provider=False):
		if provider:
			payload = {
				"gauthPayload": {
					"brandId": self.BRAND_ID,
				},
				"providers": True,
				"signup": False,
			}
		else:
			payload = {}

		data = self.call_api('/authentication/linkDevice/initiate', data=payload)
		return data['data']['attributes']['targetUrl'], data['data']['attributes']['linkingCode']

	# ##################################################################################################################

	def device_login(self):
		try:
			data = self.call_api('/authentication/linkDevice/login', data={}, ignore_error=True, ignore_204=False)
		except Status204:
			return False

		access_token = data.get('data',{}).get('attributes',{}).get('token')

		if not access_token:
			return False

		self.login_data['access_token'] = access_token
		self.temp_access_token = None
		self.update_config(True)

		data = self.call_api('/users/me')
		self.login_data['user_id'] = data['data']['id']
		self.login_data['profile_id'] = data['data']['attributes']['selectedProfileId']
		self.save_login_data()
		return True

	# ##################################################################################################################

	def _process_data(self, data):
		linked = {}
		for row in data.get('included', []):
			if row['type'] == 'package':
				continue
			linked[row['id']] = row

		processed = {}
		def _process_row(row):
			if row['id'] in processed:
				return processed[row['id']]
			new_row = {'id': row['id'], 'meta': row.get('meta',{})}
			new_row.update(row.get('attributes', {}))
			processed[row['id']] = new_row
			for name in row.get('relationships', []):
				related = row['relationships'][name]['data']
				if isinstance(related, list):
					new_row[name] = [_process_row(linked[x['id']]) if x['id'] in linked else x for x in related]
				elif related['id'] in linked:
					new_row[name] = _process_row(linked[related['id']])
				else:
					new_row[name] = related
			return new_row

		new_data = []
		if isinstance(data['data'], dict):
			data['data'] = [data['data']]
		for row in data['data']:
			new_data.append(_process_row(row))

		return new_data

	# ##################################################################################################################

	def get_profiles(self):
		data = self.call_api('/users/me/profiles')
		return self._process_data(data)

	# ##################################################################################################################

	def get_active_profile_id(self):
		return self.login_data.get('profile_id')

	# ##################################################################################################################

	def switch_profile(self, profile_id, pin=None):
		payload = {
			'data': {
				'attributes': {
					'selectedProfileId': profile_id
				},
				'id': self.login_data.get('user_id'),
				'type': 'user'
			}
		}

		if pin:
			payload['data']['attributes']['profilePin'] = pin

		self.call_api('/users/me/profiles/switchProfile', data=payload)
		self.login_data['profile_id'] = profile_id
		self.save_login_data()

	# ##################################################################################################################

	def get_collection(self, collection_id, page=1):
		params = {
			'include': 'default',
			'decorators': 'viewingHistory,badges,isFavorite,contentAction',
			'page[items.number]': page,
			'page[items.size]': self.PAGE_SIZE,
		}
		data = self.call_api('/cms/collections/{}'.format(collection_id), params=params)
		ret = self._process_data(data)[0]

		dump_json(ret, 'collection_{}'.format(collection_id))

		return ret

	# ##################################################################################################################

	def get_route(self, route, page=1):
		params = {
			'include': 'default',
			'decorators': 'viewingHistory,isFavorite,contentAction,badges',
			'page[items.number]': page,
			'page[items.size]': self.PAGE_SIZE,
		}
		data = self.call_api('/cms/routes/{}'.format(route), params=params)
		ret = self._process_data(data)[0]['target']
		dump_json(ret, 'route_{}'.format(route))
		return ret

	# ##################################################################################################################

	def get_series(self, series_id):
		params = {
			'include': 'default',
			'decorators': 'viewingHistory,badges,isFavorite,contentAction',
			'page[items.size]': self.PAGE_SIZE,
		}
		data = self.call_api('/cms/routes/show/{}'.format(series_id), params=params)
		data = self._process_data(data)[0]['target']['primaryContent']
		dump_json(data, '/cms/routes/show/{}'.format(series_id))
		return data

	# ##################################################################################################################

	def get_season(self, series_id, season_num, page=1):
		params = {
			'include': 'default',
			'decorators': 'viewingHistory,badges,isFavorite,contentAction',
			'pf[show.id]': series_id,
			'pf[seasonNumber]': season_num,
			'page[items.number]': page,
		}
		data = self.call_api('/cms/collections/generic-show-page-rail-episodes-tabbed-content', params=params)
		data = self._process_data(data)[0]
		dump_json(data, '/cms/collections/generic-show-page-rail-episodes-tabbed-content')
		return data

	# ##################################################################################################################

	def get_edit_id(self, item_id, data_item=None):
		params = {
			'include': 'edit',
			'decorators': 'viewingHistory'
		}

		data = self.call_api('/content/videos/{}/activeVideoForShow'.format(item_id), params=params)
		data = self._process_data(data)[0]
		dump_json(data, '/content/videos/{}/activeVideoForShow'.format(item_id))

		return data['edit']['id'], self.fill_data_item(data, data_item)

	# ##################################################################################################################

	def fill_data_item(self, src_data, data_item=None):
		if data_item != None:
			data_item.update({
				"programId": src_data['id'],
				"editId": src_data['edit']['id'],
				"showId": src_data.get('show',{}).get('id',""),
				"mainContentDurationSec": int(src_data['edit'].get('duration', 0) // 1000),
				"runtimeSec": int(src_data['edit'].get('duration', 0) // 1000),
				"videoType": src_data['videoType'].lower(),
			})

		return src_data.get('viewingHistory', {}).get('position')

	# ##################################################################################################################

	# currently not used
	def watch_video(self, show_id, edit_id):
		params = {
			'include': 'default',
			'decorators': 'viewingHistory,isFavorite,contentAction,badges',
			'page[items.size]': self.PAGE_SIZE
		}

		data = self.call_api('/cms/routes/video/watch/{}/{}'.format(show_id, edit_id), params=params)
		data = self._process_data(data)[0]
		dump_json(data, '/cms/routes/video/watch/{}/{}'.format(show_id, edit_id))

		return data

	# ##################################################################################################################

	def search(self, query, page=1):
		def get_collection_id():
			params = {'include': 'default'}
			data = self.call_api('/cms/routes/search/result', params=params)
			return self._process_data(data)[0]['target']['items'][0]['collection']['id']

		params = {
			'include': 'default',
			'decorators': 'viewingHistory,badges,isFavorite,contentAction',
			'pf[query]': query,
			'page[items.number]': page,
			'page[items.size]': self.PAGE_SIZE,
		}

		data = self.call_api('/cms/collections/{}'.format(get_collection_id()), params=params)
		return self._process_data(data)[0]

	# ##################################################################################################################

	def play(self, edit_id, data_item=None):

		playback_session_id = str(uuid.uuid4())
		app_session_id = str(uuid.uuid1())

		if data_item:
			data_item.update({
				"playbackSessionId": playback_session_id,
				"appSessionId": app_session_id
			})

		payload = {
			'appBundle': 'com.wbd.stream',
			'applicationSessionId': app_session_id,
			'capabilities': {
				'codecs': {
					'audio': {
						'decoders': [{
							'codec': 'aac',
							'profiles': ['lc', 'he', 'hev2', 'xhe']
						},{
							'codec': 'eac3',
							'profiles': ['atmos']
						}]
					},
					'video': {
						'decoders': [{
							'codec': 'h264',
							'levelConstraints': {
								'framerate': {
									'max': 960,
									'min': 0
								},
								'height': {
									'max': 2176,
									'min': 48
								},
								'width': {
									'max': 3840,
									'min': 48
								}
							},
							'maxLevel': '5.2',
							'profiles': ['baseline', 'main', 'high']
						}, {
							'codec': 'h265',
							'levelConstraints': {
								'framerate': {
									'max': 960,
									'min': 0
								},
								'height': {
									'max': 2176,
									'min': 144
								},
								'width': {
									'max': 3840,
									'min': 144
								}
							},
							'maxLevel': '5.1',
							'profiles': ['main', 'main10']
						}],
						'hdrFormats': ['hdr10','hdr10plus','dolbyvision','dolbyvision5','dolbyvision8','hlg'],
					}
				},
				'contentProtection': {
					'contentDecryptionModules': [{
						'drmKeySystem': 'widevine',
						'maxSecurityLevel': 'L3'
					}]
				},
				'manifests': {
					'formats': {
						'dash': {}
					}
				}
			},
			'consumptionType': 'streaming',
			'deviceInfo': {
				'player': {
					'mediaEngine': {
						'name': '',
						'version': ''
					},
					'playerView': {
						'height': 2176,
						'width': 3840
					},
					'sdk': {
						'name': '',
						'version': ''
					}
				}
			},
			'editId': edit_id,
			'firstPlay': False,
			'gdpr': False,
			'playbackSessionId': playback_session_id,
			'userPreferences': {
				#'uiLanguage': 'en'
			}
		}

		return self.call_api('/playback-orchestrator/any/playback-orchestrator/v1/playbackInfo', data=payload)

	# ##################################################################################################################

	def logout(self):
		self.call_api('/logout', method='POST')
		self.reset_login_data()

	# ##################################################################################################################

	def add_watchlist(self, idem_id):
		self.call_api('/my-list/show/{}'.format(idem_id), data={})

	# ##################################################################################################################

	def del_watchlist(self, item_id):
		self.call_api('/my-list/show/{}'.format(item_id), method='DELETE')

	# ##################################################################################################################

	def set_marker(self, data_item, position):
		if data_item:
			payload = {
				'creationTimeEpochMs': int(time()) * 1000,
				'positionSec': position,
			}
			payload.update(data_item)
			self.call_api('/markers/any/markers/v1/markers', data=payload)

	# ##################################################################################################################

	def watchlist(self):
		ret = self.get_route('my-stuff')
		dump_json(ret, 'watchlist')
		return ret

	# ##################################################################################################################

	def watchtime_reset(self, item_id, show_id):
		collection_id = '170978312149821667450710537300541032725'
		self.call_api('/cms/collection/{collection_id}/video/{item_id}/show/{show_id}'.format(collection_id=collection_id, item_id=item_id, show_id=show_id), method='DELETE')

	# ##################################################################################################################

	def get_devices(self):
		ret = []

		for x in self.call_api('/users/me/tokens')['data']:
			item = x['attributes']
			item['id'] = x['id']
			item['isMe'] = item['deviceId'] == self.login_data['device_id']
			ret.append(item)

		return ret

	# ##################################################################################################################

	def delete_device(self, device_id ):
		self.call_api('/users/me/tokens/{}'.format(device_id), method='DELETE')

	# ##################################################################################################################
