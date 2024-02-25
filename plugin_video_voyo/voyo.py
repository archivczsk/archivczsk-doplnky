# -*- coding: utf-8 -*-
#
# based on RobertSkorpil's KODI addon
#
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from uuid import uuid4
from hashlib import sha256
import base64
import time

try:
	from cookielib import DefaultCookiePolicy
except:
	from http.cookiejar import DefaultCookiePolicy

APP_VER='6.1.2'
APP_BUILD='2788'

COMMON_HEADERS = {
#	'User-Agent': 'Voyo/%s (net.cme.voyo.sk; build:%s; Android 14; Model:SM-S901B) okhttp/4.10.0' % (APP_VER, APP_BUILD),
	'X-DeviceType': 'mobile',
	'X-DeviceOS': 'Android',
	'X-DeviceOSVersion': '34',
	'X-DeviceManufacturer': 'samsung',
	'X-DeviceModel': 'SM-S901B',
#	'X-DeviceSubType': 'smartphone',
	'X-DeviceName': 'E2 Linux',
#	'X-Version': APP_VER,
#	'X-AppBuildNumber': APP_BUILD
}

DUMP_API_REQUESTS=False

# ##################################################################################################################

class Voyo(object):
	API_URL = {
		'sk': 'https://apivoyo.cms.markiza.sk/api/v1/',
		'cz': 'https://apivoyo.cms.nova.cz/api/v1/'
	}

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		# disable cookie handling - when cookies are enabled, then it make problems and some thinks doesn't work as expected
		# and native android app doesn't handle cookies too
		self.req_session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))

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
		return self.cp.get_settings_checksum(('login_type', 'username', 'password',))

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
			self.save_login_data()

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None, method=None, auto_refresh_token=True, ignore_error=False):
		if auto_refresh_token and self.check_access_token() == False:
			self.refresh_token()

		headers = COMMON_HEADERS.copy()
		headers['X-Device-Id'] = self.login_data['device_id']

		region = self.login_data.get('region', self.cp.get_setting('login_type').split('_')[0])
		api_url = self.API_URL[region]

		if self.login_data.get('access_token'):
			headers['Authorization'] = 'Bearer ' + self.login_data['access_token']

		url = api_url + endpoint
		if method == None:
			if data != None:
				method = 'POST'
			else:
				method = 'GET'

		resp = self.req_session.request(method=method, url=url, params=params, json=data, headers=headers)

		try:
			resp_json = resp.json()
		except:
			resp_json = {}

		if not resp.ok:
			if auto_refresh_token and resp.status_code == 401:
				self.refresh_token()
				return self.call_api(endpoint, params, data, method, auto_refresh_token=False)

			if ignore_error == False:
				if resp_json.get('message'):
					raise AddonErrorException(resp_json['message'])
				else:
					raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

		return resp_json

	# ##################################################################################################################

	def check_access_token(self):
		if not self.login_data.get('access_token'):
			return False

		return True

	# ##################################################################################################################

	def refresh_token(self):
		# TODO: dorobit auto refersh bez toho aby sa musel robit novy login
		self.login()

	# ##################################################################################################################

	def login_telekom(self):
		def get_oauth2_params():
			verifier = (str(uuid4()) + str(uuid4()) + str(uuid4()) + str(uuid4())).replace('-', '')

			sha256_val = sha256(verifier.encode('ascii')).digest()
			challenge = base64.urlsafe_b64encode(sha256_val).decode('utf-8')

			state = str(uuid4()).replace('-', '')[:30]
			return verifier, challenge.replace("+", "-").replace("/", "_").replace("=", ""), state

		oauth_info = None
		for pl in self.call_api('app-init', auto_refresh_token=False)['partnerLogins']:
			if pl['id'] == 'telekom':
				oauth_info = pl['oauth2']
				break
		else:
			raise AddonErrorException(self.cp._("Failed to find informations for login partner") + ': telekom')

		if oauth_info['oauth2Authorize']['codeChallengeMethod'] != 'S256':
			raise AddonErrorException(self.cp._("Unsupported oauth2 challenge method") + ': %s' % oauth_info['oauth2Authorize']['codeChallengeMethod'])

		verifier, challenge, state = get_oauth2_params()

		headers = {
			'User-Agent': 'Mozilla/5.0 (Linux; Android 14; SM-S901B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/121.0.6167.178 Mobile Safari/537.36',
			'X-Requested-With': 'net.cme.voyo.sk',
			'sec-ch-ua': '"Not A(Brand";v="99", "Android WebView";v="121", "Chromium";v="121"',
			'sec-ch-ua-mobile': '?1',
			'sec-ch-ua-platform': "Android",
			'Accept-Language': 'sk-SK,sk;q=0.9,en-US;q=0.8,en;q=0.7',
		}

		params = {
			'client_id': oauth_info['oauth2Authorize']['clientID'],
			'redirect_uri': oauth_info['oauth2Authorize']['redirectUri'],
			'scope': oauth_info['oauth2Authorize']['scopes'][0],
			'response_type': oauth_info['oauth2Authorize']['responseTypes'][0],
			'code_challenge': challenge,
			'code_challenge_method': 'S256',
			'state': state
		}

		login_session = self.cp.get_requests_session()
		resp = login_session.get(oauth_info['oauth2Authorize']['endpoint'], params=params, headers=headers)
		resp.raise_for_status()

		headers.update({
			'Origin': 'https://loginpage.magio.tv',
			'Referer': 'https://loginpage.magio.tv/',
		})

		data = {
			'loginOrNickname': self.cp.get_setting('username'),
			'password': self.cp.get_setting('password'),
			'client_id': oauth_info['oauth2Authorize']['clientID'],
			'language': 'SK'
		}

		resp = login_session.post('https://skgo-voyo-integration.magio.tv/oauth/internal/login', data=data, headers=headers)
		resp.raise_for_status()

		headers['Authorization'] = 'Bearer ' + resp.json()['accessToken']

		data = {
			'client_id': oauth_info['oauth2Authorize']['clientID'],
			'redirect_uri': oauth_info['oauth2Authorize']['redirectUri'],
			'scope': oauth_info['oauth2Authorize']['scopes'][0],
			'language': 'SK',
			'state': state,
			'code_challenge': challenge,
			'code_challenge_method': 'S256',
		}

		resp = login_session.post('https://skgo-voyo-integration.magio.tv/oauth/internal/authorize', data=data, headers=headers)
		resp.raise_for_status()

		auth_code = resp.json()['authorizationCode']

		data = {
			'client_id': oauth_info['oauth2Token']['clientID'],
			'code': auth_code,
			'code_verifier': verifier,
			'redirect_uri': oauth_info['oauth2Authorize']['redirectUri'],
			'grant_type': "authorization_code"
		}

		resp = login_session.post(oauth_info['oauth2Token']['endpoint'], data=data)
		resp.raise_for_status()

		data = {
			'partnerToken': resp.json()['access_token']
		}

		login_session.close()
		return self.call_api('users/partner-token/telekom', data=data, auto_refresh_token=False)

	# ##################################################################################################################

	def login_voyo(self):
		# this call can fail, but is realy needed ...
		self.call_api('app-init', auto_refresh_token=False, ignore_error=True)

		data = {
			'username': self.cp.get_setting('username'),
			'password': self.cp.get_setting('password')
		}

		return self.call_api('auth-sessions', data=data, auto_refresh_token=False)

	# ##################################################################################################################

	def login(self):
		self.login_data['access_token'] = None
		self.save_login_data()
		self.login_data['region'], self.login_data['login_type'] = self.cp.get_setting('login_type').split('_')

		try:
			if self.login_data['login_type'] == 'voyo':
				self.login_voyo()

			elif self.login_data['login_type'] == 'telekom':
				resp = self.login_telekom()

		except AddonErrorException as e:
			raise LoginException(str(e))
		except Exception as e:
			self.cp.log_exception()
			raise LoginException(str(e))

		self.login_data['access_token'] = resp['credentials']['accessToken']
		self.login_data['checksum'] = self.get_login_checksum()
		self.save_login_data()

		try:
			# this call always fails, but is realy needed ...
			self.call_api('app-init', params={'reason': 'user-changed'}, auto_refresh_token=False, ignore_error=True)

			time.sleep(1)
			resp = self.call_api('users/info', auto_refresh_token=False, ignore_error=True)

			if 'user' in resp:
				available_profiles = resp['user']['data']['profiles']['available']
			else:
				available_profiles = resp['additionalData']['profiles']['available']

			profile_id = self.login_data.get('profile_id')
			for profile in available_profiles:
				# check if stored profile exists
				if profile['id'] == profile_id:
					break
			else:
				# stored profile doesn't exists - select main profile
				for profile in available_profiles:
					if profile['isMain']:
						profile_id = profile['id']
						break
				else:
					# main profile not found - select first available one
					profile_id = resp['user']['data']['profiles']['available'][0]['id']

			self.call_api('users/profile/select/%s' % profile_id, auto_refresh_token=False, ignore_error=True)
			self.call_api('app-init', params={'reason': 'profile-changed'}, auto_refresh_token=False, ignore_error=True)
			self.login_data['profile_id'] = profile_id
			self.save_login_data()
		except:
			self.cp.log_exception()

	# ##################################################################################################################

	@staticmethod
	def get_image_url(url):
		return url.replace('{WIDTH}', '512').replace('{HEIGHT}', '512')

	# ##################################################################################################################

	def get_home(self):
		resp = self.call_api('overview')
		categories = []
		for jcat in resp['categories']:
			jcatcat = jcat['category']
			if jcatcat:
				categories.append({
					'id': jcatcat['id'],
					'title': jcatcat['name'],
					'type': jcatcat['type']
				})
		for s in resp['sections']:
			result = []
			for content in s['content'] or []:
				result.append({
					'id': content['content']['id'],
					'type': content['content']['type'],
					'image': self.get_image_url(content['content']['image']),
					'title': content['content']['title']
				})

			if len(result) > 0:
				categories.append({
					'title': s['name'],
					'type': s['type'],
					'items': result
				})


		return categories

	# ##################################################################################################################

	def get_categories(self):
		categories = []
		for jcat in self.call_api('overview')['categories']:
			jcatcat = jcat['category']
			if jcatcat:
				categories.append({
					'id': jcatcat['id'],
					'title': jcatcat['name'],
					'type': jcatcat['type']
				})
		return categories

	# ##################################################################################################################

	def list_category(self, id, page=1, sort='date-desc'):
		items = []
		params = {
			'category': id,
			'page': page,
			'sort': sort
		}
		for jitem in self.call_api('content', params=params)['items']:
			items.append({
				'id': jitem['id'],
				'title': jitem['title'],
				'type': jitem['type'],
				'image': self.get_image_url(jitem['image']),
			})
		return items

	# ##################################################################################################################

	def list_tvshow(self, id):
		resp = self.call_api('tvshow/' + str(id))
		ret = []
		alike_title = None

		for page in resp['subPages']:
			if page['type'] == 'alike':
				alike_title = page['name']
				break

		if alike_title:
			result = []
			for content in resp['alike']:
				result.append({
					'id': content['id'],
					'type': content['type'],
					'image': self.get_image_url(content['image']),
					'title': content['title']
				})

			ret.append({
				'title': alike_title,
				'type': 'alike',
				'items': result
			})

		if len(resp['seasons']) > 1:
			for jseason in resp['seasons']:
				ret.append({
					'id': jseason['id'],
					'showId': id,
					'title': jseason['name'],
					'type': 'season',
				})

		else:
			for s in resp['sections']:
				if s['id'] == 'episodes':
					for content in s['content']:
						ret.append({
							'id': content['id'],
							'type': content['type'],
							'image': self.get_image_url(content['image']),
							'title': content['title'],
							'length': content['stream']['length']
						})
					break

		return ret

	# ##################################################################################################################

	def list_tvshow_seasons(self, id):
		seasons = []
		resp = self.call_api('tvshow/' + str(id))
		img = self.get_image_url(resp['tvshow']['image']),
		description = self.get_image_url(resp['tvshow']['description']),

		for jseason in resp['seasons']:
			seasons.append({
				'id': jseason['id'],
				'showId': id,
				'title': jseason['name'],
				'type': 'season',
				'image': img,
				'description': description,
			})
		return seasons

	# ##################################################################################################################

	def list_season_episodes(self, showId, seasonId):
		episodes = []
		for jepisode in self.call_api('tvshow/' + str(showId), params = {'season': seasonId})['sections'][0]['content']:
			episodes.append({
				'id': jepisode['id'],
				'type': jepisode['type'],
				'image': self.get_image_url(jepisode['image']),
				'title': jepisode['title'],
				'length': jepisode['stream']['length'],
			})
		return episodes

	# ##################################################################################################################

	def list_live_channels(self):
		items = []
		for jitem in self.call_api('epg/onscreen')['channels']:
			items.append({
				'id': jitem['id'],
				'title': jitem['name'],
				'type': 'livetv',
				'image': self.get_image_url(jitem['logo']),
				'epg':{
					'title': jitem['current']['title'],
					'plot': jitem['current']['description'],
					'img': self.get_image_url(jitem['current']['image']),
				}
			})
		return items

	# ##################################################################################################################

	def get_search_result(self, pattern):
		result = []
		for rg in self.call_api('search', params={'query': pattern})['resultGroups']:
			for jres in rg['results']:
				content = jres['content']
				result.append({
					'id': content['id'],
					'type': content['type'],
					'image': self.get_image_url(content['image']),
					'title': content['title']
				})

		return result

	# ##################################################################################################################

	def get_item_info(self, type, id):
		res = self.call_api(type + '/' + str(id))
		if type == 'tvshow':
			content = res['tvshow']
		else:
			content = res['content']

		return {
			'plot': content['description'],
			'img': self.get_image_url(content['image']),
			'title': content['title'],
			'genre': ', '.join(g['title'] for g in content['genres'])
		}

	# ##################################################################################################################

	def get_content_info(self, id):
		params = {
			'acceptVideo': 'dash,drm-widevine'
		}
		resp = self.call_api('content/%s/plays' % str(id), params=params, method="POST")
		content = resp['content']
		result = {
			'id': id,
			'type': content['type'],
			'image': self.get_image_url(content['image']),
			'title': content['title'],
			'showTitle': content['parentShowTitle'],
			'description': content['description'],
			'videoUrl': resp['url'],
			'videoType': resp['videoType'],
		}
		if resp['drm']:
			drm = {
				'drm': resp['drm']['keySystem'] ,
				'licenseKey': resp['drm']['licenseRequestHeaders'][0]['value'],
				'licenseUrl': resp['drm']['licenseUrl']
			}
			result.update(drm)

		return result

	# ##################################################################################################################

	def get_profiles(self):
		resp = self.call_api('users/info', ignore_error=True)

		if 'user' in resp:
			available_profiles = resp['user']['data']['profiles']['available']
		else:
			available_profiles = resp['additionalData']['profiles']['available']

		ret = []
		for p in available_profiles:
			ret.append({
				'name': p['name'],
				'id': p['id'],
				'img': self.get_image_url(p['avatarUrl']),
				'is_main': p['isMain'],
				'is_child': p['settings']['isChild'],
				'this': p['id'] == self.login_data.get('profile_id')
			})

		return ret

	# ##################################################################################################################

	def switch_profile(self, profile_id):
		resp = self.call_api('users/info', ignore_error=True)

		if 'user' in resp:
			available_profiles = resp['user']['data']['profiles']['available']
		else:
			available_profiles = resp['additionalData']['profiles']['available']

		for profile in available_profiles:
			# check if stored profile exists
			if profile['id'] == profile_id:
				break
		else:
			return False

		self.call_api('users/profile/select/%s' % profile_id)
		self.call_api('app-init', params={'reason': 'profile-changed'}, ignore_error=True)
		self.login_data['profile_id'] = profile_id
		self.save_login_data()
		return True

	# ##################################################################################################################

	def get_account_info(self):
		resp = self.call_api('users/info')['user']
		user_id = resp['id']
		resp = resp['data']

		return {
			'id': user_id,
			'name': resp['shownUsername'],
			'from_partner': resp['isFromPartner'],
			'devices_count': resp['devices']['count'],
			'subscription_type': resp['subscriptionLevel']['type'],
			'subscription_name': resp['subscriptionLevel']['title'],
		}

	# ##################################################################################################################

	def get_devices(self):
		ret = []
		for d in self.call_api('users/devices')['devices']:
			ret.append({
				'id': d['id'],
				'name': d['name'],
				'this': d['isCurrent'],
				'last_profile': d['lastUsedBy']['name']
			})

		return ret

	# ##################################################################################################################

	def delete_device(self, device_id):
		self.call_api('users/devices/%s' % str(device_id), method='DELETE')

	# ##################################################################################################################

	def get_favorites(self):
		return self.call_api('favorites')

	# ##################################################################################################################

	def add_to_favorites(self, id):
		data = {
			'id': id
		}
		self.call_api('favorites', data=data)

	# ##################################################################################################################

	def remove_from_favorites(self, id):
		self.call_api('favorites/%s' % str(id), method="DELETE")

	# ##################################################################################################################
