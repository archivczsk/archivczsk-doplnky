# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from uuid import uuid4

from time import time

try:
	from urllib import quote
except:
	from urllib.parse import quote

DUMP_API_REQUESTS = False

class HboMax(object):
	DEVICE_MODEL = 'androidtv'

	VERSION = '100.35.0.280'

	HEADERS = {
		'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 8.1.0; SHIELD Android TV Build/LMY47D)',
		'X-Hbo-Device-Name': DEVICE_MODEL,
		'X-Hbo-Client-Version': 'Hadron/{0} android/{0} (SHIELD/8.1.0)'.format(VERSION),
		'X-Hbo-Device-Os-Version': '8.1.0',
		'Accept': 'application/vnd.hbo.v9.full+json',
	}

	CLIENT_ID = 'c8d75990-06e5-445c-90e6-d556d7790998' #androidtv

	LANG_CODE = {
		'sk': 'sk-SK',
		'cs': 'cs-CZ'
	}
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(self.HEADERS)
		self.login_data = {}
		self.client_config = {}
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

	def get_login_checksum(self):
		return self.cp.get_settings_checksum(('username', 'password',))

	# ##################################################################################################################

	def reset_login_data(self):
		self.login_data = {
			'device_id': self.login_data.get('device_id')
		}
		self.save_login_data()

	# ##################################################################################################################

	def load_login_data(self):
		self.login_data = self.cp.load_cached_data('login')
		if self.login_data.get('access_token') and self.login_data.get('checksum') != self.get_login_checksum():
			# login data changed, so clean cached data to perform new fresh login
			self.reset_login_data()

		if not self.login_data.get('device_id'):
			self.login_data['device_id'] = str(uuid4())

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, method=None, headers={}, auto_refresh_token=True, ignore_error=False):
		if auto_refresh_token and self.check_access_token() == False:
			self.refresh_token()

		xheaders = {}
		if self.login_data.get('access_token'):
			xheaders['Authorization'] = 'Bearer ' + self.login_data['access_token']

		xheaders.update(headers)

		if not isinstance(endpoint, (type([]), type(()),)):
			endpoint = (endpoint,'',)

		if endpoint[0].startswith('http'):
			url = endpoint[0]
		else:
			url = 'https://{endpoint}{userSubdomain}.{domain}.hbo.com'.format(endpoint=endpoint[0], **self.client_config['routeKeys']) + endpoint[1]

		if method == None:
			if data != None:
				method = 'POST'
			else:
				method = 'GET'

		resp = self.req_session.request(method=method, url=url, params=params, json=data, headers=xheaders)

		try:
			resp_json = resp.json()
		except:
			raise LoginException(self.cp._("No response received from server. Maybe is your IP blocked by HBO."))

		if not resp.ok or (isinstance(resp_json, type({})) and resp_json.get('statusCode',0) > 400):
			if auto_refresh_token and resp.status_code == 401 or resp_json.get('statusCode',0) == 401:
				self.refresh_token()
				return self.call_api(endpoint, params, data, method, headers, auto_refresh_token=False, ignore_error=ignore_error)

			if ignore_error == False:
				if resp_json.get('message') or resp_json.get('code'):
					raise AddonErrorException(resp_json.get('message') or resp_json.get('code'))
				else:
					raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

		return resp_json

	# ##################################################################################################################

	def check_access_token(self, checksum_check=False):
		ret = True
		if not self.login_data.get('access_token') or self.login_data.get('expires',0) < int(time()):
			ret = False

		if checksum_check and self.get_login_checksum() != self.login_data.get('checksum'):
			ret = False

		if ret == False:
			if 'access_token' in self.login_data:
				del self.login_data['access_token']

		if not self.client_config:
			self.refresh_client_config()

		return ret

	# ##################################################################################################################

	def refresh_token(self):
		if self.login_data.get('refresh_token'):
			payload = {
				'refresh_token': self.login_data['refresh_token'],
				'grant_type': 'refresh_token',
				'scope': 'browse video_playback device',
			}

			if 'access_token' in self.login_data:
				del self.login_data['access_token']

			self.get_oauth_token(payload)
		else:
			self.login()

	# ##################################################################################################################

	def refresh_client_config(self, force=False):
		if not force and self.client_config.get('__validity',0) > int(time()):
			return

		if not self.login_data.get('access_token'):
			self.cp.log_debug("GUEST CONFIG")
			self.login_guest()
		else:
			self.cp.log_debug("USER CONFIG")

		payload = {
			'contract': 'hadron:1.1.2.0',
			'preferredLanguages': ['en-US'],
		}

		self.client_config = self.call_api('https://sessions.api.hbo.com/sessions/v1/clientConfig', data=payload, auto_refresh_token=False)
		self.client_config['__validity'] = int(time()) + 1800

		# check for available languages and fix LANG list
		if False:
			available_langs = {}
			for l in self.get_languages():
				self.cp.log_debug("Available lang: %s (%s)" % (l['endonym'], l['code']))
				available_langs[l['code']] = True

			del_keys = []
			for k,v in self.LANG_CODE.items():
				if v not in available_langs:
					del_keys.append(k)

			for k in del_keys:
				del self.LANG_CODE[k]

	# ##################################################################################################################

	def login_guest(self):
		payload = {
			'client_id': self.CLIENT_ID,
			'client_secret': self.CLIENT_ID,
			'scope': 'browse video_playback_free account_registration',
			'grant_type': 'client_credentials',
			'deviceSerialNumber': self.login_data['device_id'],
			'clientDeviceData': {
				'paymentProviderCode': 'google-play'
			}
		}

		data = self.call_api('https://oauth.api.hbo.com/auth/tokens', data=payload, auto_refresh_token=False)
		if data.get('code') == 'invalid_credentials':
			raise LoginException(self.cp._("Failed to perform anonymous login. Your IP is maybe blocked by HBO."))

		self.login_data['access_token'] = data['access_token']

	# ##################################################################################################################

	def login(self):
		payload = {
			'username': self.cp.get_setting('username'),
			'password': self.cp.get_setting('password'),
			'grant_type': 'user_name_password',
			'scope': 'browse video_playback device elevated_account_management',
		}
		self.get_oauth_token(payload)

		profile_id = self.login_data.get('profile_id')
		available_profiles = self.get_profiles()
		for profile in available_profiles:
			# check if stored profile exists
			if profile['profileId'] == profile_id:
				break
		else:
			# stored profile doesn't exists - select main profile
			for profile in available_profiles:
				if profile['isMe']:
					profile_id = profile['profileId']
					break
			else:
				# main profile not found - select first available one
				profile_id = available_profiles['profileId']

		self.login_data['profile_id'] = profile_id
		self.set_profile(profile_id)

	# ##################################################################################################################

	def get_oauth_token(self, payload):
		data = self.call_api( ('oauth', '/auth/tokens'), data=payload, auto_refresh_token=False)
		self.login_data['access_token'] = data['access_token']
		self.login_data['expires'] = int(time() + data['expires_in'] - 15)

		if 'refresh_token' in data:
			self.login_data['refresh_token'] = data['refresh_token']

		self.login_data['checksum'] = self.get_login_checksum()
		self.save_login_data()
		self.refresh_client_config(True)

	# ##################################################################################################################

	def get_languages(self):
		headers = {
			'x-hbo-headwaiter': self._headwaiter(),
		}
		return [x for x in self.call_api(('sessions', '/sessions/v1/enabledLanguages'), headers=headers) if x.get('disabledForCurrentRegion') != True]

	# ##################################################################################################################

	def _headwaiter(self):
		self.refresh_client_config()

		headwaiter = ''
		for key in sorted(self.client_config['payloadValues']):
			headwaiter += '{}:{},'.format(key, self.client_config['payloadValues'][key])

		return headwaiter.rstrip(',')

	# ##################################################################################################################

	def get_profiles(self):
		return self.content([{'id': 'urn:hbo:profiles:mine'}])['urn:hbo:profiles:mine']['profiles']

	# ##################################################################################################################

	def get_devices(self):
		return self.content([{'id': 'urn:hbo:devices:mine'}])['urn:hbo:devices:mine']['devices']

	# ##################################################################################################################

	def set_profile(self, profile_id):
		payload = {
			'grant_type': 'user_refresh_profile',
			'profile_id': profile_id,
			'refresh_token': self.login_data.get('refresh_token'),
		}

		self.get_oauth_token(payload)

	# ##################################################################################################################

	def entitlements(self):
		return self.content([{"id":"urn:hbo:entitlement-status:mine"}])['urn:hbo:entitlement-status:mine']

	# ##################################################################################################################

	def get_express_content(self, slug):
		headers = {
			'x-hbo-headwaiter': self._headwaiter(),
			'accept-language': self.LANG_CODE.get(self.cp.dubbed_lang_list[0], 'en-US'),
		}
		params = {
			'language': self.LANG_CODE.get(self.cp.dubbed_lang_list[0], 'en-US'),
		}

		entitlements = self.entitlements()
		if entitlements['outOfTerritory']:
			raise AddonErrorException(self.cp._("You don't have access to this content"))

		data = self.call_api(('comet', '/express-content/{}?{}'.format(slug, entitlements['expressContentParams'])), params=params, headers=headers)

		_data = {}
		for row in data:
			_data[row['id']] = row['body']

		return _data

	# ##################################################################################################################

	def process_express_content_data(self, data, slug, tab=None):
		return self._process(data, tab or slug)

	# ##################################################################################################################

	def express_content(self, slug, tab=None):
		headers = {
			'x-hbo-headwaiter': self._headwaiter(),
			'accept-language': self.LANG_CODE.get(self.cp.dubbed_lang_list[0], 'en-US'),
		}
		params = {
			'language': self.LANG_CODE.get(self.cp.dubbed_lang_list[0], 'en-US'),
		}

		entitlements = self.entitlements()
		if entitlements['outOfTerritory']:
			raise AddonErrorException(self.cp._("You don't have access to this content"))

		data = self.call_api(('comet', '/express-content/{}?{}'.format(slug, entitlements['expressContentParams'])), params=params, headers=headers)

		_data = {}
		for row in data:
			_data[row['id']] = row['body']

		return self._process(_data, tab or slug)

	# ##################################################################################################################

	def content(self, payload):
		headers = {
			'x-hbo-headwaiter': self._headwaiter(),
			'accept-language': self.LANG_CODE.get(self.cp.dubbed_lang_list[0], 'en-US'),
		}

		data = self.call_api(('comet', '/content'), data=payload, headers=headers)

		if isinstance(data, dict):
			return data

		_data = {}
		for row in data:
			_data[row['id']] = row['body']

		return _data

	# ##################################################################################################################

	def marker(self, id):
		markers = self.markers([id,])
		return list(markers.values())[0] if markers else None

	# ##################################################################################################################

	def markers(self, ids):
		if not ids:
			return {}

		if len(ids) == 1:
			#always have at least 2 markers so api returns a list
			ids.append(ids[0])

		params = {
			'limit': len(ids),
		}

		try:
			markers = {}
			for row in self.call_api(('markers', '/markers/{}'.format(','.join(ids))), params=params):
				markers[row['id']] = {'position': row['position'], 'runtime': row['runtime']}
			return markers
		except:
			return {}

	# ##################################################################################################################

	def update_marker(self, url, cut_id, runtime, playback_time):
		headers = {
			'x-hbo-headwaiter': self._headwaiter()
		}

		payload = {
			#'appSessionId': session_id,
			#'videoSessionId': video_session,
			'creationTime': int(time()*1000),
			'cutId': cut_id,
			'position': playback_time,
			'runtime': runtime,
		}

		resp = self.call_api(url, data=payload, headers=headers)
		return resp.get('status') == 'Accepted'

	# ##################################################################################################################

	def add_watchlist(self, slug):
		self.call_api(('comet', '/watchlist/{}'.format(slug)), method='PUT')

	# ##################################################################################################################

	def delete_watchlist(self, slug):
		self.call_api(('comet', '/watchlist/{}'.format(slug)), method='DELETE')

	# ##################################################################################################################

	def watchlist(self):
		data = self.content([{'id': 'urn:hbo:query:mylist'}])
		data = self._process(data, 'urn:hbo:query:mylist')

		payload = []
		items = {}
		order = []
		for row in reversed(data['items']):
			order.append(row['id'])
			if not row.get('contentType'):
				payload.append({'id': row['id']})
			else:
				items[row['id']] = row

		def chunks(lst, n):
			for i in range(0, len(lst), n):
				yield lst[i:i + n]

		for chunk in chunks(payload, 32):
			data = self.content(chunk)
			for key in data:
				items[key] = self._process(data, key)

		ordered = []
		for id in order:
			if id in items:
				ordered.append(items[id])

		return ordered

	# ##################################################################################################################

	def continue_watching(self):
		data = self.content([{'id': 'urn:hbo:continue-watching:mine'}])
		return self._process(data, 'urn:hbo:continue-watching:mine')

	# ##################################################################################################################

	def search(self, query):
		key = 'urn:hbo:flexisearch:{}'.format(quote(query))
		data = self.content([{'id': key}])

		for key in data:
			if key.startswith('urn:hbo:grid:search') and key.endswith('-all'):
				return self._process(data, key)

		return None

	# ##################################################################################################################

	def _process(self, data, slug):
		main = data[slug]
		if len(data) == 1 and 'message' in main:
			raise AddonErrorException(main['message'])

		def process(element):
			if element.get('processed', False):
				return

			element['processed'] = True
			element['items'] = []
			element['tabs'] = []
			element['edits'] = []
			element['previews'] = []
			element['seasons'] = []
			element['extras'] = []
			element['similars'] = []
			element['episodes'] = []
			element['target'] = None

			for key in element.get('references', {}):
				if key in ('items', 'tabs', 'edits', 'seasons', 'previews', 'extras', 'similars', 'episodes'):
					for id in element['references'][key]:
						if id == '$dataBinding':
							continue

						item = {'id': id}
						if id in data:
							item.update(data[id])
						process(item)
						element[key].append(item)
				else:
					element[key] = element['references'][key]

			element.pop('references', None)

		process(main)
		return main

	# ##################################################################################################################

	def get_play_languages(self, slug):
		content_data = self.express_content(slug)
		edits = content_data.get('edits', [])
		return edits or []

	# ##################################################################################################################

	def play(self, slug):
		content_data = self.express_content(slug)
		edits = content_data.get('edits', [])
		if not edits:
			raise AddonErrorException(self.cp._("Video not found"))

		edit = None
		for row in edits:
			edit = row

		payload = [{
			'id': edit['video'],
			'headers' : {
				'x-hbo-preferred-blends': 'DASH_WDV,HSS_PR',
				'x-hbo-video-mlp': True, #multi-language
			}
		}]

		data = self.content(payload).get(edit['video'])

		for row in data.get('manifests', []):
			if row['type'] == 'urn:video:main':
				return row, content_data, edit

		raise AddonErrorException(self.cp._("Video not found"))
