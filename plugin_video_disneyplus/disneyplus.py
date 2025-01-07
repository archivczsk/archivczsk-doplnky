# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import lru_cache
from uuid import uuid4

from time import time

PAGE_SIZE_CONTENT = 60
PAGE_SIZE_SETS = 60

DUMP_API_REQUESTS = False

class DisneyPlus(object):
	CLIENT_ID = 'disney-svod-3d9324fc'
	CLIENT_VERSION = '9.7.0'
	EXPLORE_VERSION = 'v1.1'

	API_KEY = 'ZGlzbmV5JmFuZHJvaWQmMS4wLjA.bkeb0m230uUhv8qrAXuNu39tbE_mD5EEhM_NAcohjyA'
	CONFIG_URL = 'https://bam-sdk-configs.bamgrid.com/bam-sdk/v5.0/{}/android/v{}/google/tv/prod.json'.format(CLIENT_ID, CLIENT_VERSION)

	HEADERS = {
		'User-Agent': 'BAMSDK/v{} ({} 2.26.2-rc1.0; v5.0/v{}; android; tv)'.format(CLIENT_VERSION, CLIENT_ID, CLIENT_VERSION),
		'x-application-version': 'google',
		'x-bamsdk-platform-id': 'android-tv',
		'x-bamsdk-client-id': CLIENT_ID,
		'x-bamsdk-platform': 'android-tv',
		'x-bamsdk-version': CLIENT_VERSION,
	}

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(self.HEADERS)
		self.active_session = None
		self.active_profile = None
		self.basic_tier = True
		self.login_data = {}
		self.load_login_data()

		self.ERROR_MAP = {
			'not-entitled': self.cp._('You are not entitled to access this content. Check if your subscription is valid.'),
			'idp.error.identity.bad-credentials': self.cp._('Your login details are incorrect.'),
			'account.profile.pin.invalid': self.cp._('Incorrect PIN'),
		}

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
			self.cp.log_error("Cached login data checksum failed")
			# login data changed, so clean cached data to perform new fresh login
			self.reset_login_data()

		if not self.login_data.get('device_id'):
			self.login_data['device_id'] = str(uuid4())

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def call_api(self, endpoint, params={}, extra_params=None, data=None, method=None, headers={}, auto_refresh_token=True, ignore_error=False):
		if auto_refresh_token and self.check_access_token() == False:
			self.refresh_token()

		xheaders = {}
		if self.login_data.get('access_token'):
			xheaders['Authorization'] = 'Bearer ' + self.login_data['access_token']
			xheaders['x-bamsdk-transaction-id'] = self._transaction_id()

		xheaders.update(headers)

		if not isinstance(endpoint, (type([]), type(()),)):
			endpoint = (endpoint,'',)

		if endpoint[0].startswith('http'):
			url = endpoint[0]
		else:
			url = self.get_config()['services'][endpoint[0]]['client']['endpoints'][endpoint[1]]['href']
			url = url.format(**self.get_api_params(url, **params))

		if method == None:
			if data != None:
				method = 'POST'
			else:
				method = 'GET'

		resp = self.req_session.request(method=method, url=url, params=extra_params, json=data, headers=xheaders)
#		dump_json_request(resp)

		try:
			resp_json = resp.json()
		except:
			resp_json = {}

		self._check_errors(resp_json)
		if not resp.ok:
#			if auto_refresh_token and resp.status_code == 401 or resp_json.get('statusCode',0) == 401:
#				self.refresh_token()
#				return self.call_api(endpoint, params, data, method, headers, auto_refresh_token=False, ignore_error=ignore_error)

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
			self.cp.log_debug("Don't have access token or token expired")
			ret = False

		if checksum_check and self.get_login_checksum() != self.login_data.get('checksum'):
			self.cp.log_debug("Login data checksum failed")
			ret = False

		if ret == False:
			if 'access_token' in self.login_data:
				del self.login_data['access_token']

		return ret

	# ##################################################################################################################

	def refresh_token(self):
		self.cp.log_info("Refresh token requested")

		if self.login_data.get('refresh_token'):
			self.cp.log_info("Have refresh token token - using it to get new access token")
			payload = {
				'operationName': 'refreshToken',
				'variables': {
					'input': {
						'refreshToken': self.login_data.get('refresh_token'),
					},
				},
				'query': """mutation refreshToken($input:RefreshTokenInput!) { refreshToken(refreshToken:$input) { activeSession{sessionId} } }""",
			}

			try:
				endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['refreshToken']['href']
				data = self.req_session.post(endpoint, json=payload, headers={'authorization': self.API_KEY}).json()
				self._check_errors(data)
			except Exception as e:
				raise LoginException(e)

			self._set_auth(data['extensions']['sdk'])
		else:
			self.cp.log_info("Don't have refresh token token - doing fresh login using name and password")
			self.login()

	# ##################################################################################################################

	def register_device(self):
		payload = {
			'variables': {
				'registerDevice': {
					'applicationRuntime': 'android',
					'attributes': {
						'operatingSystem': 'Android',
						'operatingSystemVersion': '8.1.0',
					},
					'deviceFamily': 'android',
					'deviceLanguage': 'en',
					'deviceProfile': 'tv',
				}
			},
			'query': """mutation ($registerDevice: RegisterDeviceInput!) {registerDevice(registerDevice: $registerDevice) {__typename}}""",
		}

		endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['registerDevice']['href']
		data = self.req_session.post(endpoint, json=payload, headers={'authorization': self.API_KEY}).json()
		self._check_errors(data)
		return data['extensions']['sdk']['token']['accessToken']

	# ##################################################################################################################

	def check_email(self, token):
		payload = {
			'operationName': 'Check',
			'variables': {
				'email': self.cp.get_setting('username'),
			},
			'query': """query Check($email: String!) { check(email: $email) { operations nextOperation } }""",
		}

		endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['query']['href']
		data = self.req_session.post(endpoint, json=payload, headers={'authorization': token}).json()
		self._check_errors(data)
		return data['data']['check']['operations'][0]

	# ##################################################################################################################

	def _check_errors(self, data, raise_on_error=True):
		if not type(data) is dict:
			return

		error_msg = None
		if data.get('errors'):
			if 'extensions' in data['errors'][0]:
				code = data['errors'][0]['extensions'].get('code')
			else:
				code = data['errors'][0].get('code')

			error_msg = self.ERROR_MAP.get(code) or data['errors'][0].get('message') or data['errors'][0].get('description') or code
			error_msg = self.cp._("API request failed. Server Error: {msg}".format(msg=error_msg))

		elif data.get('error'):
			error_msg = self.ERROR_MAP.get(data.get('error_code')) or data.get('error_description') or data.get('error_code')
			error_msg = self.cp._("API request failed. Server Error: {msg}".format(msg=error_msg))

		elif data.get('status') == 400:
			error_msg = self.cp._("API request failed. Server Error: {msg}".format(msg=data.get('message')))

		if error_msg and raise_on_error:
			raise AddonErrorException(error_msg)

		return error_msg


	# ##################################################################################################################

	@lru_cache(10, timeout=3600)
	def get_config(self):
		return self.req_session.get(self.CONFIG_URL).json()

	# ##################################################################################################################

	@lru_cache(10, timeout=3600)
	def _transaction_id(self):
		return str(uuid4())

	# ##################################################################################################################

	def _set_auth(self, sdk):
		self.login_data['feature_flags'] = sdk['featureFlags']
		self.login_data['access_token'] = sdk['token']['accessToken']
		self.login_data['refresh_token'] = sdk['token']['refreshToken']
		self.login_data['expires']  = int(time() + sdk['token']['expiresIn'] - 15)
		self.login_data['checksum'] = self.get_login_checksum()
		self.save_login_data()

	# ##################################################################################################################

	def login(self):
		self.cp.log_info("Performing fresh login")
		self.reset_login_data()
		try:
			token = self.register_device()
			next_step = self.check_email(token)
		except Exception as e:
			raise LoginException(e)

		if next_step.lower() == 'register':
			raise LoginException(self.cp._("Login e-mail not found"))

		elif next_step.lower() == 'otp':
			raise LoginException(self.cp._("Login using OTP is not supported"))

		payload = {
			'operationName': 'loginTv',
			'variables': {
				'input': {
					'email': self.cp.get_setting('username'),
					'password': self.cp.get_setting('password'),
				},
			},
			'query': """mutation loginTv($input: LoginInput!) { login(login: $input) { __typename account { __typename ...accountGraphFragment } actionGrant activeSession { __typename ...sessionGraphFragment } }} fragment accountGraphFragment on Account { __typename id activeProfile { __typename id } profiles { __typename ...profileGraphFragment } parentalControls { __typename isProfileCreationProtected } flows { __typename star { __typename isOnboarded } } attributes { __typename email emailVerified userVerified locations { __typename manual { __typename country } purchase { __typename country } registration { __typename geoIp { __typename country } } } }}\nfragment profileGraphFragment on Profile { __typename id name maturityRating { __typename ratingSystem ratingSystemValues contentMaturityRating maxRatingSystemValue isMaxContentMaturityRating } isAge21Verified flows { __typename star { __typename eligibleForOnboarding isOnboarded } } attributes { __typename isDefault kidsModeEnabled groupWatch { __typename enabled } languagePreferences { __typename appLanguage playbackLanguage preferAudioDescription preferSDH subtitleLanguage subtitlesEnabled } parentalControls { __typename isPinProtected kidProofExitEnabled liveAndUnratedContent { __typename enabled } } playbackSettings { __typename autoplay backgroundVideo prefer133 } avatar { __typename id userSelected } }}\nfragment sessionGraphFragment on Session { __typename sessionId device { __typename id } entitlements experiments { __typename featureId variantId version } homeLocation { __typename countryCode } inSupportedLocation isSubscriber location { __typename countryCode } portabilityLocation { __typename countryCode } preferredMaturityRating { __typename impliedMaturityRating ratingSystem }}""",
		}

		try:
			endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['query']['href']
			data = self.req_session.post(endpoint, json=payload, headers={'authorization': token}).json()
			self._check_errors(data)
		except Exception as e:
			raise LoginException(e)

		self._set_auth(data['extensions']['sdk'])

		if not self.get_active_profile()[0]:
			self.select_default_profile()

	# ##################################################################################################################

	def select_default_profile(self):
		try:
			data = self.get_account_info()
			self.switch_profile(data['account']['profiles'][0]['id'])
		except:
			self.cp.log_exception()

	# ##################################################################################################################

	def get_account_info(self):
		payload = {
			'operationName': 'EntitledGraphMeQuery',
			'variables': {},
			'query': """query EntitledGraphMeQuery { me { __typename account { __typename ...accountGraphFragment } activeSession { __typename ...sessionGraphFragment } } } fragment accountGraphFragment on Account { __typename id activeProfile { __typename id } profiles { __typename ...profileGraphFragment } parentalControls { __typename isProfileCreationProtected } flows { __typename star { __typename isOnboarded } } attributes { __typename email emailVerified userVerified locations { __typename manual { __typename country } purchase { __typename country } registration { __typename geoIp { __typename country } } } } } fragment profileGraphFragment on Profile { __typename id name maturityRating { __typename ratingSystem ratingSystemValues contentMaturityRating maxRatingSystemValue isMaxContentMaturityRating } isAge21Verified flows { __typename star { __typename eligibleForOnboarding isOnboarded } } attributes { __typename isDefault kidsModeEnabled groupWatch { __typename enabled } languagePreferences { __typename appLanguage playbackLanguage preferAudioDescription preferSDH subtitleLanguage subtitlesEnabled } parentalControls { __typename isPinProtected kidProofExitEnabled liveAndUnratedContent { __typename enabled } } playbackSettings { __typename autoplay backgroundVideo prefer133 preferImaxEnhancedVersion} avatar { __typename id userSelected } } } fragment sessionGraphFragment on Session { __typename sessionId device { __typename id } entitlements experiments { __typename featureId variantId version } homeLocation { __typename countryCode } inSupportedLocation isSubscriber location { __typename countryCode } portabilityLocation { __typename countryCode } preferredMaturityRating { __typename impliedMaturityRating ratingSystem } }""",
		}

		endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['query']['href']
		return self.call_api(endpoint, data=payload)['data']['me']

	# ##################################################################################################################

	def get_active_profile(self):
		if not self.active_session or not self.active_profile:
			data = self.get_account_info()

			self.active_session = data['activeSession']
			self.basic_tier = 'DISNEY_PLUS_NO_ADS' not in self.active_session['entitlements']
			if data['account']['activeProfile']:
				for row in data['account']['profiles']:
					if row['id'] == data['account']['activeProfile']['id']:
						self.active_profile = row
						break

		return self.active_profile, self.active_session

	# ##################################################################################################################

	def switch_profile(self, profile_id, pin=None):
		payload = {
			'operationName': 'switchProfile',
			'variables': {
				'input': {
					'profileId': profile_id,
				},
			},
			'query': """mutation switchProfile($input: SwitchProfileInput!) { switchProfile(switchProfile: $input) { __typename account { __typename ...accountGraphFragment } activeSession { __typename ...sessionGraphFragment } } } fragment accountGraphFragment on Account { __typename id activeProfile { __typename id } profiles { __typename ...profileGraphFragment } parentalControls { __typename isProfileCreationProtected } flows { __typename star { __typename isOnboarded } } attributes { __typename email emailVerified userVerified locations { __typename manual { __typename country } purchase { __typename country } registration { __typename geoIp { __typename country } } } } } fragment profileGraphFragment on Profile { __typename id name maturityRating { __typename ratingSystem ratingSystemValues contentMaturityRating maxRatingSystemValue isMaxContentMaturityRating } isAge21Verified flows { __typename star { __typename eligibleForOnboarding isOnboarded } } attributes { __typename isDefault kidsModeEnabled groupWatch { __typename enabled } languagePreferences { __typename appLanguage playbackLanguage preferAudioDescription preferSDH subtitleLanguage subtitlesEnabled } parentalControls { __typename isPinProtected kidProofExitEnabled liveAndUnratedContent { __typename enabled } } playbackSettings { __typename autoplay backgroundVideo prefer133 } avatar { __typename id userSelected } } } fragment sessionGraphFragment on Session { __typename sessionId device { __typename id } entitlements experiments { __typename featureId variantId version } homeLocation { __typename countryCode } inSupportedLocation isSubscriber location { __typename countryCode } portabilityLocation { __typename countryCode } preferredMaturityRating { __typename impliedMaturityRating ratingSystem } }""",
		}

		if pin:
			payload['variables']['input']['entryPin'] = str(pin)

#		endpoint = self.get_config()['services']['orchestration']['client']['endpoints']['query']['href']
#		data = self._session.post(endpoint, json=payload).json()
#		self._check_errors(data)

		data = self.call_api(('orchestration', 'query'), data=payload)
		self._set_auth(data['extensions']['sdk'])

	# ##################################################################################################################

	def get_api_params(self, href, **kwargs):
		profile, session = self.get_active_profile()

		region = session['portabilityLocation']['countryCode'] if session['portabilityLocation'] else session['location']['countryCode']
		maturity = session['preferredMaturityRating']['impliedMaturityRating'] if session['preferredMaturityRating'] else 1850
		kids_mode = profile['attributes']['kidsModeEnabled'] if profile else False
		app_language = self.cp.dubbed_lang_list[0] or (profile['attributes']['languagePreferences']['appLanguage'] if profile else 'en-US')

		api_version = '6.1'
		if '/search/' in href:
			api_version = '5.1'

		_args = {
			'apiVersion': api_version,
			'region': region,
			'impliedMaturityRating': maturity,
			'kidsModeEnabled': 'true' if kids_mode else 'false',
			'appLanguage': app_language,
			'partner': 'disney',
		}
		_args.update(**kwargs)

		return _args

	# ##################################################################################################################

	def search(self, query):
		params = {
			'query': query,
			'queryType': 'ge',
			'pageSize': PAGE_SIZE_CONTENT
		}
		return self.call_api(('content', 'getSearchResults'), params=params )['data']['search']

	# ##################################################################################################################

	def avatar_by_id(self, ids):
		params = {
			'avatarIds': ','.join(ids)
		}
		return self.call_api(('content', 'getAvatars'), params=params )['data']['Avatars']

	# ##################################################################################################################

	def video_bundle(self, family_id):
		params = {
			'encodedFamilyId': family_id
		}
		return self.call_api(('content', 'getDmcVideoBundle'), params=params )['data']['DmcVideoBundle']

	# ##################################################################################################################

	def up_next(self, content_id):
		params = {
			'contentId': content_id
		}
		return self.call_api(('content', 'getUpNext'), params=params )['data']['UpNext']

	# ##################################################################################################################

	def continue_watching(self):
		return self.call_api(('content', 'getCWSet'))['data']['ContinueWatchingSet']

	# ##################################################################################################################

	def add_watchlist(self, ref_type, ref_id):
		params = {
			'refIdType': ref_type,
			'refId': ref_id
		}
		return self.call_api(('content', 'putItemInWatchlist'), method='PUT', params=params )

	# ##################################################################################################################

	def delete_watchlist(self, ref_type, ref_id):
		params = {
			'refIdType': ref_type,
			'refId': ref_id
		}
		return self.call_api(('content', 'deleteItemFromWatchlist'), method='DELETE', params=params )

	# ##################################################################################################################

	def collection_by_slug(self, slug, content_class, sub_type='StandardCollection'):
		params = {
			'collectionSubType': sub_type,
			'contentClass': content_class,
			'slug': slug
		}
		return self.call_api(('content', 'getCollection'), params=params )['data']['Collection']

	# ##################################################################################################################

	def set_by_id(self, set_id, set_type, page=1, page_size=PAGE_SIZE_SETS):
		if set_type == 'ContinueWatchingSet':
			endpoint = 'getCWSet'
		elif set_type == 'CuratedSet':
			endpoint = 'getCuratedSet'
		else:
			endpoint = 'getSet'

		params = {
			'setType': set_type,
			'setId': set_id,
			'pageSize': page_size,
			'page': page
		}
		return self.call_api(('content', endpoint), params=params )['data'][set_type]

	# ##################################################################################################################

	def video(self, content_id):
		params = {
			'contentId': content_id
		}
		return self.call_api(('content', 'getDmcVideo'), params=params )['data']['DmcVideo']

	# ##################################################################################################################

	def series_bundle(self, series_id):
		params = {
			'encodedSeriesId': series_id
		}
		return self.call_api(('content', 'getDmcSeriesBundle'), params=params )['data']['DmcSeriesBundle']

	# ##################################################################################################################

	def episodes(self, season_id, page=1):
		params = {
			'seasonId': season_id,
			'page': page,
			'pageSize': PAGE_SIZE_CONTENT
		}
		return self.call_api(('content', 'getDmcEpisodes'), params=params )['data']['DmcEpisodes']

	# ##################################################################################################################

	def update_resume(self, media_id, fguid, playback_time):
		payload = [{
			'server': {
				'fguid': fguid,
				'mediaId': media_id,
				# 'origin': '',
				# 'host': '',
				# 'cdn': '',
				# 'cdnPolicyId': '',
			},
			'client': {
				'event': 'urn:bamtech:api:stream-sample',
				'timestamp': str(int(time()*1000)),
				'play_head': playback_time,
				# 'playback_session_id': str(uuid.uuid4()),
				# 'interaction_id': str(uuid.uuid4()),
				# 'bitrate': 4206,
			},
		}]

		return self.call_api(('telemetry', 'postEvent'), data=payload)

	# ##################################################################################################################

	def explore_page(self, page_id):
		params = {
			'version': self.EXPLORE_VERSION,
			'pageId': page_id
		}
		extra_params = {
			'disableSmartFocus': 'true',
			'limit': 999,
			'enhancedContainersLimit': 0,
		}

		return self.call_api(('explore', 'getPage'), params=params, extra_params=extra_params)['data']['page']

	# ##################################################################################################################

	def explore_set(self, set_id, page=1):
		params = {
			'version': self.EXPLORE_VERSION,
			'setId': set_id
		}
		extra_params = {
			'limit': PAGE_SIZE_CONTENT,
			'offset': PAGE_SIZE_CONTENT * (page-1),
		}

		return self.call_api(('explore', 'getSet'), params=params, extra_params=extra_params)['data']['set']

	# ##################################################################################################################

	def explore_season(self, season_id):
		params = {
			'version': self.EXPLORE_VERSION,
			'seasonId': season_id
		}

		return self.call_api(('explore', 'getSeason'), params=params)['data']['season']

	# ##################################################################################################################

	def explore_search(self, query):
		params = {
			'version': self.EXPLORE_VERSION,
		}

		extra_params = {
			'query': query,
		}

		return self.call_api(('explore', 'search'), params=params, extra_params=extra_params)['data']['page']

	# ##################################################################################################################

	def playback_data(self, playback_url, wv_secure=False):
		headers = {
			'accept': 'application/vnd.media-service+json; version={}'.format(6 if self.basic_tier else 5),
			'x-dss-feature-filtering': 'true'
		}

		payload = {
			"playback": {
				"attributes": {
					"codecs": {
						'supportsMultiCodecMaster': False, #if true outputs all codecs and resoultion in single playlist
					},
					"protocol": "HTTP",
					#"ads": "",
					"frameRates": [60],
					"assetInsertionStrategy": "SGAI",
					"playbackInitializationContext": "ONLINE"
				},
			}
		}

		video_ranges = []
		audio_types = []

		if self.cp.get_setting('video_codec') == 'hvc1':
#			payload['playback']['attributes']['codecs'].update({'video': ['h264', 'h265']})
			payload['playback']['attributes']['codecs'].update({'video': ['h265']})

		if audio_types:
			payload['playback']['attributes']['audioTypes'] = audio_types

		if video_ranges:
			payload['playback']['attributes']['videoRanges'] = video_ranges

		if not wv_secure:
			payload['playback']['attributes']['resolution'] = {'max': ['1280x720']}

		scenario = 'ctr-high' if wv_secure else 'ctr-regular'
		endpoint = playback_url.format(scenario=scenario)
		return self.call_api(endpoint, headers=headers, data=payload)

	# ##################################################################################################################

	def explore_playback(self, resource_id, wv_secure=False):
		headers = {
			'accept': 'application/vnd.media-service+json',
			'x-dss-feature-filtering': 'true'
		}

		payload = {
			"playbackId": resource_id,
			"playback": {
				"attributes": {
					"codecs": {
						'supportsMultiCodecMaster': False, #if true outputs all codecs and resoultion in single playlist
					},
					"protocol": "HTTP",
				   # "ads": "",
					"frameRates": [60],
					"assetInsertionStrategy": "SGAI",
					"playbackInitializationContext": "ONLINE"
				},
			}
		}

		video_ranges = []
		audio_types = []

		if self.cp.get_setting('video_codec') == 'hvc1':
			payload['playback']['attributes']['codecs'].update({'video': ['h265']})

		if audio_types:
			payload['playback']['attributes']['audioTypes'] = audio_types

		if video_ranges:
			payload['playback']['attributes']['videoRanges'] = video_ranges

		if not wv_secure:
			payload['playback']['attributes']['resolution'] = {'max': ['1280x720']}

		params = {
			'scenario': 'ctr-high' if wv_secure else 'ctr-regular'
		}

		return self.call_api(('media', 'mediaPayload'), params=params, headers=headers, data=payload)

	# ##################################################################################################################

	def feature_flags(self):
		return self.login_data['feature_flags']

	# ##################################################################################################################
