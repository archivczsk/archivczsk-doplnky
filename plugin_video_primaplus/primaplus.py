# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
import re
import time
from datetime import datetime, timedelta

try:
	from urllib.parse import parse_qs, urlparse
except ImportError:
	from urlparse import parse_qs, urlparse


COMMON_HEADERS = {
	'Origin': 'https://www.iprima.cz/',
	'Referer': 'https://www.iprima.cz/',
}

DUMP_API_REQUESTS=False

# ##################################################################################################################

class PrimaPlus(object):
	DEVICE_TYPE='WEB'
	DEVICE_NAME='Linux E2'

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.watchlist = None
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
			from uuid import uuid4
			self.login_data['device_id'] = 'd-' + str(uuid4())
			self.save_login_data()

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def call_rpc_api(self, method, params={}):
		if self.check_access_token() == False:
			self.refresh_token()

		data = {
			'id' : '1',
			'jsonrpc' : '2.0',
			'method' : method,
			'params': {
				'_accessToken' : self.login_data['access_token'],
				'deviceType' : self.DEVICE_TYPE,
				'deviceId' : self.login_data['device_id'],
			}
		}
		data['params'].update(params)

		resp = self.req_session.post('https://gateway-api.prod.iprima.cz/json-rpc/', json=data)

		if not resp.ok:
			raise AddonErrorException(self.cp._("Unexpected return code from Prima RPC server") + ": %d" % resp.status_code)

		resp_json = resp.json()

		if 'error' in resp_json:
			raise AddonErrorException(self.cp._("Error by calling Prima RPC API") + ": %s" % resp_json['error'].get('message',''))

		return resp_json.get('result',{}).get('data', {})


	# ##################################################################################################################

	def call_api(self, url, params=None, data=None):
		if self.check_access_token() == False:
			self.refresh_token()

		if self.login_data.get('access_token'):
			headers = {
				'Authorization' : 'Bearer ' + self.login_data['access_token'],
				'X-OTT-Access-Token' : self.login_data['access_token'],
				'X-OTT-CDN-Url-Type' : self.DEVICE_TYPE
			}
			if self.login_data.get('device'):
				headers['X-OTT-Device'] = self.login_data['device']

			if self.login_data.get('profile_id'):
				headers['X-OTT-User-SubProfile'] = self.login_data['profile_id']
		else:
			headers = {}

		if data != None:
			resp = self.req_session.post(url, params=params, json=data, headers=headers)
		else:
			resp = self.req_session.get(url, params=params, headers=headers)

		try:
			resp_json = resp.json()
		except:
			resp_json = {}

		if not resp.ok:
			if 'errorCode' in resp_json and 'userMessage' in resp_json:
				raise AddonErrorException(resp_json['userMessage'])
			else:
				raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

		return resp_json

	# ##################################################################################################################

	def check_access_token(self):
		if not self.login_data.get('access_token') or self.login_data.get('valid_to', 0) < int(time.time()):
			return False

		return True

	# ##################################################################################################################

	def refresh_token(self):
		# TODO: dorobit auto refersh bez toho aby sa musel robit novy login
		self.login()

	# ##################################################################################################################

	def login(self):
		response = self.req_session.get('https://auth.iprima.cz/oauth2/login')

		try:
			# try to get crfs token using regexp, because not all images have BeautifulSoup 4
			csrf_token = re.search('name="_csrf_token".*value="(.*)"', response.text).group(1)
		except:
			# failed - try with BeautifulSoup 4
			self.cp.log_exception()
			try:
				from bs4 import BeautifulSoup
				soup = BeautifulSoup(response.content, 'html.parser')
				csrf_token = soup.find('input', {'name' : '_csrf_token'}).get('value')
			except:
				self.cp.log_exception()
				raise LoginException(self.cp._('Failed to get csrf token needed for login'))

		data = {
			'_email' : self.cp.get_setting('username'),
			'_password' : self.cp.get_setting('password'),
			'_csrf_token' : csrf_token
		}
		response = self.req_session.post('https://auth.iprima.cz/oauth2/login', json=data)
		if not response.ok:
			raise LoginException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		auth_url = parse_qs(urlparse(response.url).query)
		if 'code' not in auth_url:
			raise LoginException(self.cp._('Failed to get auth code. Probably wrong login name/password combination.'))

		data = {
			'scope' : 'openid+email+profile+phone+address+offline_access',
			'client_id' : 'prima_sso',
			'grant_type' : 'authorization_code',
			'code' : auth_url['code'][0],
			'redirect_uri' : 'https://auth.iprima.cz/sso/auth-check'
		}

		response = self.req_session.post('https://auth.iprima.cz/oauth2/token', json=data)

		if not response.ok:
			raise LoginException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		token_data = response.json()

		if 'access_token' in token_data:
			self.login_data['access_token'] = token_data['access_token']
			self.login_data['valid_to'] = int(time.time()) + int(token_data['expires_in'])
			self.login_data['checksum'] = self.get_login_checksum()

			if self.login_data.get('device') == None:
				self.register_device()

			profiles = self.get_profiles()

			if self.login_data.get('profile_id') == None:
				# load list of profiles and get id of the first one
				self.login_data['profile_id'] = profiles[0]['ulid']
			else:
				for p in profiles:
					if self.login_data['profile_id'] == p['ulid']:
						break
				else:
					# stored profile ID not found -> select first one as default
					self.login_data['profile_id'] = profiles[0]['ulid']

			self.save_login_data()
		else:
			raise LoginException(self.cp._("Access token not found in response data from server"))

	# ##################################################################################################################

	def register_device(self):
		params = {
			'deviceSlotType' : self.DEVICE_TYPE,
			'deviceSlotName' : self.DEVICE_NAME,
			'deviceUid' : self.login_data['device_id']
		}
		resp = self.call_rpc_api('user.device.slot.add', params)
		self.login_data['device'] = resp.get('slotId')

	# ##################################################################################################################

	def get_subscription(self):
		return self.get_account_info().get('primaPlay',{}).get('userLevelShort', 'free').lower()

	# ##################################################################################################################

	def get_account_info(self):
		return self.call_rpc_api('user.user.info.byAccessToken')

	# ##################################################################################################################

	def get_profiles(self):
		profiles = self.get_account_info().get('profiles',[])

		for p in profiles:
			if p['ulid'] == self.login_data.get('profile_id'):
				p['this'] = True
			else:
				p['this'] = False

		return profiles

	# ##################################################################################################################

	def switch_profile(self, profile_id):
		for p in self.get_profiles():
			if p['ulid'] == profile_id:
				self.login_data['profile_id'] = profile_id
				self.save_login_data()
				break

	# ##################################################################################################################

	def get_layout(self, layout):
		ret = []
		params = {
			'layout' : layout
		}

		for strip in self.call_rpc_api('strip.layout.serve.vdm', params):
			if strip['type'] == 'strip' and strip['stripData']['layoutType'] in ('portraitStrip', 'landscapeStrip'):
				ret.append({
					'title': strip['stripData']['title'],
					'strip_id':  strip['stripData']['id']
				})

		return ret

	# ##################################################################################################################

	def get_strip(self, strip_id, strip_filter = None):
		limit = 100
		page = 1
		last = False
		items = []

		method = 'strip.strip.items.vdm'
		params = {
			'stripId' : strip_id,
			'limit' : limit,
			'profileId' : self.login_data['profile_id']
		}

		while last == False:
			if page > 1:
				method = 'strip.strip.nextItems.vdm'
				params.update({
					'offset' : int(page) * limit,
					'recommId' : recommId,
				})

			if strip_filter != None:
				params['filter'] = strip_filter

			data = self.call_rpc_api(method, params)
			if data.get('items') == None:
				last = True
			else:
				items += data['items']
				page += 1
				recommId = data['recommId']
				if data['isNextItems'] == False:
					last = True

		return items

	# ##################################################################################################################

	def get_genres(self):
		ret = []

		for genre in self.call_rpc_api('vdm.frontend.genre.list'):
			ret.append({
				'title': genre['title'],
				'strip_id': '8138baa8-c933-4015-b7ea-17ac7a679da4',
				'strip_filter': [{'type' : 'genre', 'value' : genre['title']}]
			})

		return ret

	# ##################################################################################################################

	def get_series(self, slug):
		params = {
			'slug' : slug,
			'limit' : 200,
			'profileId' : self.login_data['profile_id']
		}
		data = self.call_rpc_api('vdm.frontend.title', params)

		return data['title']['seasons']

	# ##################################################################################################################

	def get_channels(self):
		params = {
			'stripId' : '4e0d6d10-4183-4424-8795-2edc47281e9e',
			'profileId' : self.login_data['profile_id']
		}

		channels = []
		for item in self.call_rpc_api('strip.strip.items.vdm', params).get('items',[]):
			channels.append({
				'id': item['id'],
				'play_id': item['playId'],
				'title': item['title'],
				'img': item['additionals']['logoColorPng'],
			})

		return channels

	# ##################################################################################################################

	def get_channel_epg(self, channel_id, day_offset):
		start_date = datetime.today() + timedelta(days = int(day_offset))
		params = {
			'date': {
				'date': start_date.strftime('%Y-%m-%d'),
			},
			'channelIds': [channel_id]
		}

		epg = []
		for item in self.call_rpc_api('epg.program.bulk.list', params):
			if item['channelVdmId'] == channel_id:
				epg = item['items']
				break

		return epg

	# ##################################################################################################################

	def get_current_epg(self, channel_ids):
		params = {
			'channelIds': channel_ids
		}

		epg = {}
		for item in self.call_rpc_api('epg.program.bulk.current', params):
			epg[item['channelVdmId']] = item['items'][0]

		return epg

	# ##################################################################################################################

	def get_streams(self, play_id):
		data = self.call_api('https://api.play-backend.iprima.cz/api/v1/products/id-%s/play' % str(play_id))
		if len(data.get('streamInfos',[])) == 0:
			raise AddonErrorException(self.cp._("No stream informations returned from server"))

		ret = []
		for stream in data['streamInfos']:
			if 'url' not in stream:
				continue

			if stream.get('type', 'NONE') not in ('HLS', 'DASH'):
				continue

			if stream['type'] == 'HLS' and stream.get('drmProtectionType', 'NONE') not in ('NONE', 'AES'):
				continue

			drm_info = None
			for drminfo in stream.get('drmInfo',{}).get('modularDrmInfos',[]):
				if drminfo['keySystem'] == 'com.widevine.alpha':
					drm_info = {
						'licence_url': drminfo['licenseServerUrl'],
						'licence_key': drminfo['token']
					}

			ret.append({
				'type': stream['type'],
				'url': stream['url'],
				'lang': stream['lang']['key'],
				'drm_info': drm_info
			})

		return ret

	# ##################################################################################################################

	def watchlist_add(self, video_id):
		params = {
			'profileUlid': self.login_data['profile_id'],
			'videoId': video_id
		}
		self.watchlist = None
		return self.call_rpc_api('user.user.profile.watchlist.add', params).get('videoId') == video_id


	# ##################################################################################################################

	def watchlist_remove(self, video_id):
		params = {
			'profileUlid': self.login_data['profile_id'],
			'videoId': video_id
		}
		self.watchlist = None
		return self.call_rpc_api('user.user.profile.watchlist.remove', params).get('isRemoved', False)

	# ##################################################################################################################

	def watchlist_reload(self):
		params = {
			'profileUlid': self.login_data['profile_id'],
		}

		self.watchlist = {}
		for item in self.call_rpc_api('user.user.profile.watchlist.list', params):
			self.watchlist[item['videoId']] = True

	# ##################################################################################################################

	def watchlist_search(self, video_id):
		if self.watchlist == None:
			self.watchlist_reload()
		return self.watchlist.get(video_id, False)

	# ##################################################################################################################

	def search(self, keyword):
		params = {
			'term' : keyword,
			'profileId': self.login_data['profile_id'],
		}

		data = self.call_rpc_api('search.search.search', params)
		return data.get('movie',[]) + data.get('series',[]) + data.get('episode',[])

	# ##################################################################################################################

	def get_devices(self):
		ret = []
		data = self.call_rpc_api('user.device.slot.list')
		for item in data:
			if item['deleted'] or item['deletedByAdmin']:
				continue

			if item['slotId'] == self.login_data['device']:
				item['this'] = True
			else:
				item['this'] = False
			ret.append(item)

		return ret

	# ##################################################################################################################

	def delete_device(self, slot_id):
		params = {
			'slotId': slot_id
		}
		self.call_rpc_api('user.device.slot.remove', params)

	# ##################################################################################################################
