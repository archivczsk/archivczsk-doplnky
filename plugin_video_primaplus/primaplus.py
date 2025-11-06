# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.date_utils import iso8601_to_timestamp
import time
from datetime import datetime, timedelta
import hashlib
import hmac
import json

COMMON_HEADERS = {
	'Origin': 'https://www.iprima.cz/',
	'Referer': 'https://www.iprima.cz/',
}

DUMP_API_REQUESTS=False

# ##################################################################################################################

class PrimaPlus(object):
	DEVICE_TYPE='WEB'
	DEVICE_NAME='Linux E2'
	RECOMBEE_TOKEN=b'syGAjIijTmzHy7kPeckrr8GBc8HYHvEyQpuJsfjV7Dnxq02wUf3k5IAzgVTfCtx6'

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.watchlist = None
		self.subscription = None
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

	def call_recombee_api(self, scenario, count=100, data_filter=None, next_id=None):
		post = {
			"cascadeCreate":True,
			"returnProperties":True,
			"includedProperties": ["xFrontendMetadata"],
			"expertSettings":
			{
				"returnedInteractionTypes": ["viewPortion", "purchase"]
			},
			"scenario": scenario,
			"count": count,
			"filter": "'type' in {\"movie\", \"series\", \"episode\"}"
		}

		if data_filter:
			post['filter'] += ' AND {}'.format(data_filter)

		if next_id:
			uri = '/ftv-prima-cross-domain/recomms/next/items/' + next_id
		else:
			uri = '/ftv-prima-cross-domain/recomms/users/' + self.login_data.get('profile_id') + '/items/'

		uri += '?frontend_timestamp=' + str(int(time.time()) + 10)
		uri += '&frontend_sign=' + hmac.new(self.RECOMBEE_TOKEN, uri.encode('utf-8'), hashlib.sha1).hexdigest()

		response = self.req_session.post( 'https://client-rapi-prima.recombee.com' + uri, json=post)

		response.raise_for_status()

		data = response.json()
		items = []
		for item in data.get('recomms', []):
			meta = item.get('values',{}).get('xFrontendMetadata')
			if meta:
				items.append(json.loads(meta))

		return {'items': items, 'next': data.get('recommId') if len(data.get('recomms', [])) == count else None  }

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
		# fetch cookies
		response = self.req_session.get('https://ucet.iprima.cz/ucet/prihlaseni')

		data = {
			'email' : self.cp.get_setting('username'),
			'password' : self.cp.get_setting('password'),
			'deviceName': self.DEVICE_NAME
		}
		response = self.req_session.post('https://ucet.iprima.cz/api/session/create', json=data)
		if not response.ok:
			raise LoginException(self.cp._('Wrong login response. Probably wrong login name/password combination.'))

		response_data = response.json()
		token_data = response_data.get('accessToken')

		if token_data:
			self.login_data['access_token'] = token_data['value']
			self.login_data['valid_to'] = iso8601_to_timestamp(token_data['expiresAt'].split('+')[0])
			self.login_data['checksum'] = self.get_login_checksum()

			# not needed to call anymore
#			if self.login_data.get('device') == None:
#				self.register_device()

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
			status_message = response_data.get('statusMessage')
			if status_message == 'Incorrect credentials':
				raise LoginException(self.cp._("Incorrect login username or password"))
			elif status_message == 'User not found':
				raise LoginException(self.cp._("Login user name not found"))
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

	def clear_subscription(self):
		self.subscription = None

	# ##################################################################################################################

	def get_subscription(self):
		if not self.subscription:
			self.subscription = self.get_account_info().get('primaPlay',{}).get('userLevelShort', 'free').lower()

		return self.subscription

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
			'deviceType': self.DEVICE_TYPE,
			'pageSlug' : layout,
			'userLevel': self.get_subscription()
		}

		for strip in self.call_rpc_api('layout.layout.serve', params).get('layoutBlocks', []):
			strip = strip.get('stripData',{})
			if strip.get('recombeeDataSource'):
				ret.append({
					'type': 'recombee',
					'title': strip['title'],
					'method': strip['recombeeDataSource']['method'],
					'scenario': strip['recombeeDataSource']['scenario']
				})
			elif strip.get('apiDataSource'):
				ret.append({
					'type': 'api',
					'method': strip['apiDataSource']['method'],
					'title': strip['title'],
				})
			elif strip.get('technicalDataSource'):
				ret.append({
					'type': 'technical',
					'title': strip['title'],
					'subtype': strip['technicalDataSource']['type'],
					'scenario': strip['technicalDataSource']['scenario']
				})
			else:
				self.cp.log_error("Unsupported strip:\n%s" % str(strip))

		return ret

	# ##################################################################################################################

	def get_recombee_data(self, scenario, data_filter=None):
		data = self.call_recombee_api(scenario, data_filter=data_filter)
		items = data['items']

		while data['next']:
			data = self.call_recombee_api(scenario, data_filter=data_filter, next_id=data['next'])
			items.extend(data['items'])

		return items

	# ##################################################################################################################

	def get_genres(self):
		ret = []

		for genre in self.call_rpc_api('vdm.frontend.genre.list'):
			ret.append({
				'title': genre['title'],
				'data_filter': '"{}" in \'xGenres\''.format(genre['title'])
			})

		return ret

	# ##################################################################################################################

	def get_seasons(self, series_id):
		params = {
			'id' : series_id,
			'pager': {
				'limit': 200,
				'offset': 0
			},
			'profileId' : self.login_data['profile_id']
		}
		data = self.call_rpc_api('vdm.frontend.season.list.hbbtv', params)

		return data

	# ##################################################################################################################

	def get_episodes(self, season_id):
		params = {
			'id' : season_id,
			'pager': {
				'limit': 200,
				'offset': 0
			},
			'ordering': {
				"field": "episodeNumber",
				"direction": "asc"
			},
			'profileId' : self.login_data['profile_id']
		}
		data = self.call_rpc_api('vdm.frontend.episodes.list.hbbtv', params)

		return data['episodes']

	# ##################################################################################################################

	def get_channels(self):
		channels = []
		for item in (self.call_rpc_api('epg.channel.list') or []):
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

			if item['slotId'] == self.login_data.get('device'):
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
