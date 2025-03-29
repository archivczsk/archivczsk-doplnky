# -*- coding: utf-8 -*-
#
# based on waladir's KODI addon
#

import os, time, json
import traceback

import uuid
from datetime import datetime, timedelta

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.date_utils import iso8601_to_timestamp

from tools_archivczsk.websocket import create_connection

############### init ################

class Oneplay(object):
	APP_VERSION = '1.0.25'

	def __init__(self, cp):
		self.cp = cp
		self._ = cp._
		self.deviceid = None

		self.accounts = []
		self.account_id = None

		self.profiles = []
		self.profile_id = None
		self.access_token = None
		self.device_id = None

		self.need_interactive_login = False

		self.req_session = self.cp.get_requests_session()
		self.current_epg = {}
		self.channel_id_to_order = {}
		self.load_login_data()

	# #################################################################################################

	def load_login_data(self):
		login_data = self.cp.load_cached_data('login')
		self.device_id = login_data.get('device_id', self.create_device_id())

		if self.get_chsum() == login_data.get('checksum'):
			self.account_id = login_data.get('account_id')
			self.profile_id = login_data.get('profile_id')
			self.access_token = login_data.get('access_token')
			self.cp.log_info("Login data loaded from cache")
		else:
			self.account_id = None
			self.profile_id = None
			self.access_token = None
			self.cp.log_info("Not using cached login data - wrong checksum")

	# #################################################################################################

	def save_login_data(self):
		# save access token
		data = {
			'device_id': self.device_id
		}

		if self.access_token:
			data.update({
				'account_id': self.account_id,
				'profile_id': self.profile_id,
				'access_token': self.access_token,
				'checksum': self.get_chsum()
			})
		self.cp.save_cached_data('login', data)

	# #################################################################################################

	def reset_login_data(self):
		self.device_id = self.create_device_id()
		self.account_id = None
		self.profile_id = None
		self.access_token = None
		self.need_interactive_login = False
		self.save_login_data()

	# #################################################################################################

	@staticmethod
	def create_device_id():
		return 'e2-aczsk-' + str(uuid.uuid4()).split('-')[0]

	# #################################################################################################

	def get_chsum(self):
		return self.cp.get_settings_checksum(('username', 'password',), self.device_id)

	# #################################################################################################

	def showError(self, msg):
		self.cp.log_error("Oneplay API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	# #################################################################################################

	def showLoginError(self, msg):
		self.cp.log_error("Oneplay Login ERROR: %s" % msg)
		raise LoginException(msg)

	# #################################################################################################

	def call_api(self, endpoint, payload={}, extra_data=None):
		headers = {
			"User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/128.0',
			'Accept' : '*/*',
			'Content-Type' : 'application/json;charset=UTF-8',
		}

		if self.access_token:
			headers['Authorization'] = 'Bearer ' + self.access_token

		url = 'https://http.cms.jyxo.cz/api/v3/' + endpoint

		request_id = str(uuid.uuid4())
		client_id = str(uuid.uuid4())

		timeout = int(self.cp.get_setting('loading_timeout'))
		ws = create_connection('wss://ws.cms.jyxo.cz/websocket/' + client_id, timeout=None if timeout == 0 else timeout)
		ws_data = json.loads(ws.recv())

		data = {
			"deviceInfo": {
				"deviceType":"web",
				"appVersion": self.APP_VERSION,
				"deviceManufacturer":"Unknown",
				"deviceOs":"Linux"
			},
			 "capabilities":{
			 	"async":"websockets"
			},
			"context": {
				"requestId": request_id,
			 	"clientId": client_id,
			 	"sessionId": ws_data['data']['serverId'],
			 	"serverId": ws_data['data']['serverId']
			}
		}

		if payload:
			data['payload'] = payload

		if extra_data:
			data.update(extra_data)

		resp = self.req_session.post(url, json=data, headers=headers)

		try:
			resp.raise_for_status()
		except:
			ws.close()
			raise

		try:
			json_response = resp.json()
		except:
			self.cp.log_exception()
			json_response = {}

		if json_response.get('result',{}).get('status') != 'OkAsync':
			ws.close()
			self.cp.log_error("Wrong response received:\n%s" % resp.text)
			self.showError(self._("Received wrong response from server"))

		while True:
			json_response = json.loads(ws.recv())
			if json_response.get('schema') != 'Ping':
				break

		ws.close()

#		dump_json_request(resp, json_response)
		result = json_response.get('response',{}).get('result',{})
		if result.get('status') == 'Error':
			if result.get('code') == '5029':
				msg = self._("This content is not available")
			else:
				msg = '{}\n{}'.format(result.get('message',''), result.get('description',''))
			msg = msg.strip()
			if not msg:
				msg = '{}: {}'.format(self._("Server returned error response"), result.get('customError',{}).get('schema',result.get('code', '?')))

			self.showError(msg.strip())

		if result.get('status') != 'Ok' or json_response.get('response',{}).get('context',{}).get('requestId') != request_id:
			self.cp.log_error("Wrong websocket response received:\n%s\n%s" % (resp.text, str(json_response)))
			self.showError(self._("Received wrong websocket response from server"))

		resp_data = json_response.get('response',{}).get('data')
		return resp_data

	# #################################################################################################

	def fill_accounts(self, accounts):
		self.cp.log_debug("Filling available accounts")

		self.accounts = []
		for a in accounts:
			self.accounts.append({
				'provider': a['accountProvider'],
				'id': a['accountId'],
				'name': a['name'],
			})

		# check if we have at least one account marked as active - if not - select the first one
		for a in self.accounts:
			if a['id'] == self.account_id:
				break
		else:
			for a in self.accounts:
				if a['provider'] == 'O2':
					self.account_id = a['id']
					break
			else:
				for a in self.accounts:
					self.account_id = a['id']
					break

	# #################################################################################################

	def is_logged_in(self):
		return self.access_token != None

	# #################################################################################################

	def refresh_login(self, account_choose_cbk=None):
		# check access token validity

		if self.is_logged_in():
			return True

		return self.login(account_choose_cbk)

	# #################################################################################################

	def login(self, account_choose_cbk=None):
		if account_choose_cbk == None and self.need_interactive_login:
			self.cp.log_error("Canceling login request - interactive login is needed")
			return False

		self.cp.log_debug("Starting login with credentials")
		payload = {
			"command":
			{
				"schema":"LoginWithCredentialsCommand",
				"email": self.cp.get_setting('username'),
				"password": self.cp.get_setting('password')
			}
		}

		try:
			response = self.call_api('user.login.step', payload)
		except AddonErrorException as e:
			raise LoginException(str(e))

		if response.get('step', {}).get('schema') == 'ShowAccountChooserStep':
			if account_choose_cbk == None:
				self.cp.log_error("Canceling login request - interactive login is needed")
				self.need_interactive_login = True
				return False

			self.cp.log_debug("Starting login with account command")
			self.fill_accounts(response['step']['accounts'])

			account_num = account_choose_cbk(['{}: {}'.format(a['provider'], a['name']) for a in self.accounts])

			if account_num == None:
				self.cp.log_error("User hasn't choosen any account - canceling login")
				return False

			self.account_id = self.accounts[account_num]['id']

			payload = {
				"command": {
					"schema":"LoginWithAccountCommand",
					"accountId": self.account_id,
					"authCode": response['step']['authToken']
				}
			}

			response = self.call_api('user.login.step', payload)


		self.cp.log_debug("Checking for access token")
		self.access_token = response.get('step', {}).get('bearerToken')
		if not self.access_token:
			self.cp.log_error("No access token in response data:\n%s" % str(response))
			raise LoginException(self._("Login failed - no access token in response data received"))

		self.cp.log_debug("Changing device")
		device_id = response['step']['currentUser']['currentDevice']['id']
		payload = {
			"id": device_id,
			"name": self.device_id
		}
		self.call_api('user.device.change', payload)

		payload = {
			"screen":"devices"
		}

		self.cp.log_debug("Requesting display setting")
		response = self.call_api('setting.display', payload)

		self.cp.log_debug("Checking registered devices")
		for device in response['screen']['userDevices']['devices']:
			if device['id'] != device_id and device['name'] == self.device_id:
				self.cp.log_debug("Removing old registered device")
				self.device_remove(device['id'])

		self.save_login_data()
		self.select_profile()

		return True

	# #################################################################################################

	def select_profile(self, profile_id=None):
		if not profile_id:
			self.cp.log_debug("Filling available profiles")
			self.fill_profiles()
			profile_id = self.profile_id

		payload = {
			"profileId": profile_id
		}

		self.cp.log_debug("Selecting user profile %s" % profile_id)
		response = self.call_api('user.profile.select', payload)
		self.access_token = response['bearerToken']
		self.save_login_data()

	# #################################################################################################

	def fill_profiles(self):
		response = self.call_api('user.profiles.display')

		profiles = []

		for profile in response['availableProfiles']['profiles']:
			profiles.append({
				'id': profile['profile']['id'],
				'name': profile['profile']['name'],
				'img': profile['profile']['avatarUrl'],
			})

		for p in profiles:
			if p['id'] == self.profile_id:
				break
		else:
			for p in profiles:
				self.profile_id = p['id']
				break

		self.profiles = profiles

	# #################################################################################################

	def get_active_profile_data(self):
		response = self.call_api('user.profiles.display')

		for profile in response['availableProfiles']['profiles']:
			if profile['profile']['id'] == self.profile_id:
				return {
					'name': profile['profile']['name'],
					'profileId': profile['profile']['id'],
					'setting': profile['setting']
				}

		return None

	# #################################################################################################

	def get_device_limit_info(self):
		payload = {
			"screen":"devices"
		}

		response = self.call_api('setting.display', payload)
		return response['screen']['deviceLimit']['name']

	# #################################################################################################

	def get_devices(self):
		payload = {
			"screen":"devices"
		}

		response = self.call_api('setting.display', payload)

		ret = []
		for device in response['screen']['userDevices']['devices']:
			ret.append({
				'name': device['name'],
				'type': device['deviceType'],
				'id': device['id'],
				'last_used': device['lastUsedAtFormatted'],
				'this_one': device['isCurrent'],
				'is_streaming': device['isStreaming']
			})

		return ret


	# #################################################################################################

	def device_remove(self, did):
		if not did:
			return

		payload = {
			"criteria": {
				"schema": "UserDeviceIdCriteria",
				"id": did
			}
		}
		self.call_api('user.device.remove', payload)
		return True

	# #################################################################################################

	def search(self, query ):
		payload = {
			"query":query
		}

		response = self.call_api('page.search.display', payload)
		ret = []

		for block in response.get('layout',{}).get('blocks',[]):
			if block['schema'] == 'CarouselBlock':
				if block['template'] == 'searchPortrait':
					for carousel in block['carousels']:
						for item in carousel['tiles']:
							if item['action']['params']['schema'] == 'PageContentDisplayApiAction':
								item_type = item['action']['params']['contentType']

								if item_type in ('show', 'movie', 'epgitem'):
									ret.append({
										'type': 'series' if item_type == 'show' else 'video',
										'id': item['action']['params']['payload']['contentId'],
										'title':  item['title'],
										'img': self._get_img(item),
									})

		return ret

	# #################################################################################################

	def get_channel_epg(self, channel_id, channel_number, fromts, tots):
		date_from = datetime.utcfromtimestamp(fromts) - timedelta(hours=4)
		date_to = datetime.utcfromtimestamp(tots)

		payload = {
			"criteria": {
				"channelSetId":"channel_list.1",
				"viewport":{
					"channelRange":{
						"from": channel_number - 1,
						"to": channel_number
					},
					"timeRange":{
						"from":date_from.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z',
						"to":date_to.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z'
					},
					"schema":"EpgViewportAbsolute"
				}
			},
			"requestedOutput": {
				"channelList":"none",
				"datePicker":False,
				"channelSets":False
			}
		}

		ret = []
		response = self.call_api('epg.display', payload)
		for channel in response['schedule']:
			if channel['channelId'] == channel_id:
				for item in channel['items']:
					item = self.convert_epg_entry(item)
					if item and item['end'] > fromts and item['start'] < tots:
						ret.append(item)

				break

		return ret

	# #################################################################################################

	def get_channel_current_epg(self, channel_id, allow_refill=True):
		epg = self.current_epg.get(channel_id,[])

		if not epg and self.current_epg:
			# this channel don't have EPG
			return {}

		cur_time = int(time.time())

		for epg_item in epg:
			if epg_item['start'] < cur_time and epg_item['end'] > cur_time:
				return epg_item

		if allow_refill:
			self.fill_current_epg()
			return self.get_channel_current_epg(channel_id, False)

		return {}

	# #################################################################################################

	def fill_current_epg(self):
		now = datetime.now()
		date_from = now - timedelta(hours=4)
		date_to = now

		payload = {
			"criteria": {
				"channelSetId":"channel_list.1",
				"viewport":{
					"channelRange":{
						"from":0,
						"to":200
					},
					"timeRange":{
						"from":date_from.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z',
						"to":date_to.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z'
					},
					"schema":"EpgViewportAbsolute"
				}
			},
			"requestedOutput": {
				"channelList":"none",
				"datePicker":False,
				"channelSets":False
			}
		}

		cur_time = int(time.time())
		ret = {}
		response = self.call_api('epg.display', payload)
		for channel in response['schedule']:
			for item in channel['items']:
				epg_item = self.convert_epg_entry(item)

				if epg_item and epg_item['end'] > cur_time:
					if channel['channelId'] not in ret:
						ret[channel['channelId']] = []

					ret[channel['channelId']].append(epg_item)

		self.current_epg = ret

	# #################################################################################################

	def _get_img(self, data, width=300, height=400):
		logo = None
		if isinstance(data, dict) and 'image' in data:
			if isinstance( data['image'], dict):
				logo = data['image'].get('small')
			else:
				logo = data['image']
		else:
			logo = data

		logo = logo or ''
		if len(logo) > 1:
			return logo.replace('{WIDTH}', str(width)).replace('{HEIGHT}', str(height))

		return None

	# #################################################################################################

	def _get_logo(self, data, width=300, height=400):
		logo = data.get('logo') or data.get('logoTransparent')

		logo = logo or ''
		if len(logo) > 1:
			return logo.replace('{WIDTH}', str(width)).replace('{HEIGHT}', str(height))

		return None

	# #################################################################################################

	def add_fav_channel(self, channel_id):
		payload = self.get_active_profile_data()

		if not payload['setting']['favoriteChannels'].get('channels'):
			payload['setting']['favoriteChannels']['channels'] = []

		if channel_id not in payload['setting']['favoriteChannels']['channels']:
			payload['setting']['favoriteChannels']['channels'].append(channel_id)
			self.call_api('user.profile.modify', payload)

	# #################################################################################################

	def remove_fav_channel(self, channel_id):
		payload = self.get_active_profile_data()

		if not payload['setting']['favoriteChannels'].get('channels'):
			payload['setting']['favoriteChannels']['channels'] = []

		if channel_id in payload['setting']['favoriteChannels']['channels']:
			payload['setting']['favoriteChannels']['channels'].remove(channel_id)
			self.call_api('user.profile.modify', payload)

	# #################################################################################################

	def get_channel_sets(self):
		payload = {
			'requestedOutput':{
				'channelSchedule': False,
				'datePicker': False,
			}
		}

		result = self.call_api('epg.display', payload)
		ret = []
		for item in result['channelSets']['sets']:
			ret.append({
				'title': item['label']['name'],
				'id': item['id']
			})

		return ret

	# #################################################################################################

	def get_channels_by_set(self, set_id):
		payload = {
			"criteria": {
				"channelSetId": set_id,
			},
			'requestedOutput':{
				'channelSchedule': False,
				"datePicker": False,
				"channelSets": False
			}
		}

		result = self.call_api('epg.display', payload)

		channels = []

		for channel in result['channelList']:
			picon = self._get_logo(channel, 220, 132)
			logo = self._get_logo(channel)

			channels.append({
				'key': str(channel['id']),
				'id': channel['id'],
				'number' : int(channel['order']),
				'name' : channel['name'],
				'adult' : channel['adult'],
				'picon' : picon,
				'timeshift': (7 * 24) if 'liveOnly' not in channel.get('flags', []) else 0,
				'logo': logo,
				'fav': channel['favorite']
			})

		return sorted(channels, key=lambda ch: (ch['number'], ch['name']))


	# #################################################################################################

	def get_channels(self):
		payload = {
			'profileId': self.profile_id
		}

		result = self.call_api('epg.channels.display', payload)

		channels = []

		for channel in result['channelList']:
			picon = self._get_logo(channel, 220, 132)
			logo = self._get_logo(channel)

			channels.append({
				'key': str(channel['id']),
				'id': channel['id'],
				'number' : int(channel['order']),
				'name' : channel['name'],
				'adult' : channel['adult'],
				'picon' : picon,
				'timeshift': (7 * 24) if 'liveOnly' not in channel.get('flags', []) else 0,
				'logo': logo,
			})

		return sorted(channels, key=lambda ch: (ch['number'], ch['name']))

	# #################################################################################################

	def mylist_remove( self, content_id):
		payload = {
			"contentId": content_id
		}
		self.call_api('user.mylist.remove', payload)
		return None

	# #################################################################################################

	def mylist_add( self, content_id ):
		payload = {
			"contentId": content_id
		}
		response = self.call_api('user.mylist.add', payload)
		return response.get('referenceId') == content_id

	# #################################################################################################

	def get_stream_url(self, content_id, start_mode=None, is_md=False):
		if is_md:
			payload = {
				"criteria":{
					"schema":"MDPlaybackCriteria",
					"contentId": content_id,
					"position": 0
				}
			}
		else:
			payload = {
				"criteria":{
					"schema":"ContentCriteria",
					"contentId": content_id
				}
			}

		if start_mode:
			payload['startMode'] = start_mode

		extra_data = {
			'playbackCapabilities': {
				"protocols":["dash","hls"],
				"drm":["widevine"] if not start_mode else [],
				"altTransfer":"Unicast",
				"subtitle":{
					"formats":["vtt"],
					"locations":["InstreamTrackLocation","ExternalTrackLocation"]
				},
				"liveSpecificCapabilities": {
					"protocols":["dash","hls"],
					"drm":["widevine"] if not start_mode else [],
					"altTransfer":"Unicast",
					"multipleAudio":True
				}
			}
		}

		pin = self.cp.get_setting('pin')
		if pin:
			extra_data['authorization'] = [
				{
					"schema":"PinRequestAuthorization",
					"pin": pin,
					"type":"parental"
				}
			]

		response = self.call_api('content.play', payload, extra_data)

		# handle multidimension
		md_items = []
		for item in response.get('playerControl',{}).get('liveControl',{}).get('mosaic',{}).get('items',[]):
			md_items.append({
				'title': item['title'],
				'id': item['play']['params']['payload']['criteria']['contentId'],
				'start_mode': start_mode
			})

		dash = {}
		dash_drm = {}
		hls = {}

		for asset in response.get('media', {}).get('stream', {}).get('assets', []):
			if asset['protocol'] == 'dash':
				if 'drm' in asset:
					dash_drm = {
						'url': asset['src'],
						'type': 'dash',
						'drm': {
							'licence_url': asset['drm'][0]['licenseAcquisitionURL'],
							'licence_key': asset['drm'][0]['drmAuthorization']['value']
						}
					}
				else:
					dash = {
						'url': asset['src'],
						'type': 'dash'
					}
			elif asset['protocol'] == 'hls':
				if 'drm' not in asset:
					hls = {
						'url': asset['src'],
						'type': 'hls'
					}


		if self.cp.get_setting('stream_type') == 'HLS' and start_mode:
			ret = hls or dash or dash_drm
		else:
			ret = dash or hls or dash_drm

		if is_md == False and md_items:
			ret['md'] = md_items

		ret['id'] = content_id
		ret['start_mode'] = start_mode
		return ret


	# #################################################################################################

	def get_live_link(self, channel_key):
		return self.get_stream_url('channel.' + channel_key, 'live')

	# #################################################################################################

	def get_archive_link(self, epg_id):
		if not epg_id.startswith('epgitem.'):
			try:
				payload = {
					"contentId":epg_id
				}
				response = self.call_api('page.content.display', payload)

				for block in response['layout']['blocks']:
					if block['schema'] == 'ContentHeaderBlock':
						epg_id = block.get('mainAction',{}).get('action',{}).get('params',{}).get('payload',{}).get('criteria',{}).get('contentId') or epg_id
						break
			except Exception as e:
				self.cp.log_error("Failed to get content ID from %s using page.content.display: %s" % (epg_id, str(e)))

		return self.get_stream_url(epg_id)

	# #################################################################################################

	def get_startover_link(self, channel_key):
		return self.get_stream_url('channel.' + channel_key, 'start')

	# #################################################################################################

	def convert_epg_entry(self, epg_entry):
		if epg_entry.get("startAt") == None or epg_entry.get("endAt") == None:
			self.cp.log_error("Invalid epg_entry: %s" % str(epg_entry))
			return None

		epg_id = None
		for e in epg_entry.get('actions',[]):
			if e.get('params',{}).get('schema') == 'PageContentDisplayApiAction':
				if e['params']['contentType'] in ('show', 'movie'):
					epg_id = e['params']['payload']['deeplink']['epgItem']
				else:
					epg_id = e['params']['payload']['contentId']

		if not epg_id:
			return None

		return {
			"start": iso8601_to_timestamp(epg_entry["startAt"][:19]) + time.timezone,
			"end": iso8601_to_timestamp(epg_entry["endAt"][:19]) + time.timezone,
			"title": str(epg_entry.get("title", '')),
			"desc": epg_entry.get("description",''),
			'img': self._get_img(epg_entry),
			'id': epg_id,
		}

	# #################################################################################################

	def get_categories(self):
		payload = {
			'reason': 'start'
		}

		response = self.call_api('app.init', payload)

		ret = []
		for group in response.get('menu',{}).get('groups',[]):
			if group['position'] == 'top':
				for item in group['items']:
					if item['action']['call'] == 'page.category.display':
						ret.append({
							'title': item['title'],
							'id': item['action']['params']['payload']['categoryId']
						})

		return ret

	# #################################################################################################

	def get_category_items(self, category_id, carousel_id=None, criteria=None):
		payload = {
			'categoryId': category_id
		}

		if criteria:
			payload['criteria'] = { 'filterCriterias': criteria }

		response = self.call_api('page.category.display', payload)

		ret = []
		for block in response.get('layout',{}).get('blocks',[]):
			if block['schema'] == 'BreadcrumbBlock':
				for item in block['menu']['groups'][0]['items']:
					if item['schema'] == 'SubMenu':
						ret.append({
							'type': 'filter',
							'title': item['title'],
							'id' : category_id,
							'filters': item['id']
						})

			elif block['schema'] == 'CarouselBlock':
				if carousel_id is None and criteria is None:
					ret.append({
						'type': 'category',
						'title': block['header']['title'],
						'id': category_id,
						'carousel_id': block['id']
					})

				elif block['id'] == carousel_id or criteria is not None:
					for carousel in block['carousels']:
						for item in carousel['tiles']:
							if item['action']['params']['schema'] == 'PageContentDisplayApiAction':
								item_type = item['action']['params']['contentType']

								if item_type in ('show', 'movie', 'epgitem'):
									ret.append({
										'type': 'series' if item_type == 'show' else 'video',
										'id': item['action']['params']['payload']['contentId'],
										'title':  item['title'],
										'img': self._get_img(item),
									})

							elif item['action']['params']['schema'] == 'PageCategoryDisplayApiAction':
								ret.append({
									'type': 'category',
									'title': item['title'],
									'img': self._get_img(item),
									'id': item['action']['params']['payload']['categoryId'],
									'carousel_id': block['id'],
									'criteria': criteria
								})

							elif item['action']['params']['schema'] == 'ContentPlayApiAction':
								ret.append({
									'type': 'video',
									'id': item['action']['params']['payload']['criteria']['contentId'],
									'title':  item['title'],
									'img': self._get_img(item),
								})

							else:
								self.cp.log_error("Unsupported item type: %s" % item['action']['params']['schema'])

						if carousel['paging']['next'] == True:
							ret.append({
								'type': 'next',
								'subtype': 'carousel',
								'id': carousel['id'],
								'criteria': criteria,
								'page': 1
							})
			elif block['schema'] == 'TabBlock':
				for tab in block['tabs']:
					ret.append({
						'type': 'tab',
						'id': tab['id'],
						'title': tab['label']['name'],
						'img': self._get_img(tab['label']['style']['iconUrl']),
						'mylist':  block.get("template") == "myList"
					})
			else:
				self.cp.log_error("Unsupported block schema: %s - ignoring" % block['schema'])

		return ret

	# #################################################################################################

	def get_tab_items(self, tab_id):
		payload = {
			'tabId': tab_id
		}

		response = self.call_api('tab.display', payload)
		ret = []

		for block in response['layout']['blocks']:
			for carousel in block['carousels']:
				for item in carousel['tiles']:
					if item['action']['params']['schema'] == 'PageContentDisplayApiAction':
						ret.append({
							'type': 'series' if item['action']['params']['contentType'] == 'show' else 'video',
							'title': item['title'],
							'img': self._get_img(item),
							'id': item['action']['params']['payload']['contentId'],
						})

		return ret

	# #################################################################################################

	def get_carousel_items(self, carousel_id, criteria, page=0):
		payload = {
			"carouselId":carousel_id,
			"paging": {
				"count":24,
				"position": (24 * page) + 1
			},
			"criteria":{
				"filterCriterias":criteria,
				"sortOption":"sorting-date-desc"
			}
		}

		response = self.call_api('carousel.display', payload)
		ret = []

		for item in response['carousel']['tiles']:
			if 'contentId' in item['action']['params']['payload']:
				item_type = item['action']['params']['contentType']

				ret.append({
					'type': 'series' if item_type == 'show' else 'video',
					'id': item['action']['params']['payload']['contentId'],
					'title':  item['title'],
					'img': self._get_img(item),
				})

		if response['carousel']['paging']['next'] == True:
			ret.append({
				'type': 'next',
				'subtype': 'carousel',
				'id': carousel_id,
				'criteria': criteria,
				'page': page+1
			})

		return ret

	# #################################################################################################

	def get_filter_items(self, category_id, filters):
		payload = {
			"categoryId": category_id
		}

		response = self.call_api('page.category.display', payload)

		ret = []
		for block in response['layout']['blocks']:
			if block['schema'] == 'BreadcrumbBlock':
				for item in block['menu']['groups'][0]['items']:
					if item['schema'] == 'SubMenu' and item['id'] == filters:
						for filter in item['groups'][0]['items']:
							if 'categoryId' in filter['action']['params']['payload']:
								ret.append({
									'type': 'category',
									'title': filter['title'],
									'id': filter['action']['params']['payload']['categoryId'],
									'criteria': filter['action']['params']['payload'].get('criteria',{}).get('filterCriterias')
								})

		return ret

	# #################################################################################################

	def get_series_items(self, series_id):
		payload = {
			"contentId": series_id
		}

		response = self.call_api('page.content.display', payload)

		for block in response['layout']['blocks']:
			if block['schema'] == 'TabBlock' and block['template'] == 'tabs':
				for tab in block['tabs']:
					if tab['label']['name'] == 'Celé díly':
						if tab['isActive'] == True:
							response = block
						else:
							payload = {
								"tabId": tab['id']
							}
							response = self.call_api('tab.display', payload)

		ret = []
		for block in response['layout']['blocks']:
			if block['schema'] == 'CarouselBlock' and block['template'] in ['list','grid']:
				for carousel in block['carousels']:
					season_select = False
					for criteria in carousel.get('criteria',[]):
						if criteria['schema'] == 'CarouselGenericFilter' and criteria['template'] == 'showSeason':
							for item in criteria['items']:
								ret.append({
									'type': 'season',
									'title': item['label'],
									'id': carousel['id'],
									'criteria': item['criteria'],
								})
								season_select = True

					if season_select == False:
						for item in carousel['tiles']:
							item_id = item.get('action', {}).get('params',{}).get('payload',{}).get('criteria',{}).get('contentId') or item.get('action', {}).get('params',{}).get('payload',{}).get('contentId')
							if item_id:
								ret.append({
									'type': 'video',
									'id': item_id,
									'title':  item['title'],
									'subtitle': item.get('subTitle'),
									'img': self._get_img(item)
								})

		return ret

	# #################################################################################################

	def get_season_items(self, carousel_id, criteria):
		page = 0
		ret = []

		while True:
			payload = {
				"carouselId": carousel_id,
				"paging":{
					"count": 12,
					"position": (12*page)+1
				},
				"criteria":{
					"filterCriterias": criteria,
					"sortOption":"DESC"
				}
			}

			response = self.call_api('carousel.display', payload)

			for item in response['carousel']['tiles']:
				if 'params' in item['action'] and 'contentId' in item['action']['params']['payload']['criteria']:
					ret.append({
						'type': 'video',
						'id': item['action']['params']['payload']['criteria']['contentId'],
						'title':  item['title'],
						'subtitle': item.get('subTitle'),
						'img': self._get_img(item)
					})

			if not response['carousel']['paging']['next']:
				break

			page += 1

		return ret


	# #################################################################################################

	def get_item_detail(self, content_id):
		def _process_duration(value):
			if not value:
				return None

			d = 0
			for part in value.split(' '):
				suffix = part[-1]
				if suffix == 'h':
					d += (int(part[:-1]) * 3600)
				elif suffix == 'm':
					d += (int(part[:-1]) * 60)
				elif suffix == 's':
					d += int(part[:-1])

			return d


		if not content_id or content_id.startswith('channel.'):
			return {}

		payload = {
			"contentId": content_id
		}

		response = self.call_api('page.content.display', payload)

		item_detail = {}

		for block in response.get('layout', {}).get('blocks', []):
			if block['schema'] == 'OnAirContentInfoBlock' and block['template'] == 'fullInfo':
				item_detail['plot'] = block.get('description')

				for item in block.get('additionalContentData', {}).get('lists', []):
					name = item['label']['name'].replace(':','')
					value = [v['name'] for v in item['valueList']]

					if name == 'Hrají':
						item_detail['cast'] = value
					elif name == 'Režie':
						item_detail['directors'] = value
					elif name == 'Žánr':
						item_detail['genre'] = value
					elif name == 'Původní název':
						item_detail['original'] = value[0] if value else None
					elif name == 'Rok':
						item_detail['year'] = value[0] if value else None
					elif name == 'Země původu':
						item_detail['country'] = value
					elif name == 'Hodnocení':
						try:
							item_detail['rating'] = float(value[0].split('%')[0]) / 10.0
						except:
							self.cp.log_exception()
					elif name == 'Délka':
						try:
							item_detail['duration'] = _process_duration(value[0])
						except:
							self.cp.log_exception()
			elif block['schema'] == 'ContentHeaderBlock':
				for action in block.get('actions', []):
					if action.get('action',{}).get('call') == 'user.mylist.remove':
						item_detail['mylist'] = True
					elif action.get('action',{}).get('call') == 'user.mylist.add':
						item_detail['mylist'] = False

				item_detail['playable'] = block.get('mainAction',{}).get('action',{}).get('params',{}).get('schema') == 'ContentPlayApiAction'
				bon = block.get('cwElement',{}).get('broadcastedOn',{})
				if bon:
					bon_msg = '{} {} {}'.format(bon.get('label',{}).get('name',''), bon['name'], bon.get('additionalText',{}).get('name', ''))
					item_detail['playable_msg'] = bon_msg.strip()
				elif block.get('customLabel'):
					bon_msg = '{}: {}'.format(self._("Available from"), block['customLabel']['name'])
					item_detail['playable_msg'] = bon_msg.strip()


		return item_detail

	# #################################################################################################

	def get_related(self, content_id):
		payload = {
			"contentId": content_id
		}

		response = self.call_api('page.content.display', payload)

		ret = []

		for block in response.get('layout', {}).get('blocks', []):
			if block['schema'] == 'CarouselBlock' and block['template'] == 'portraitGrid' and block.get('header',{}).get('title') == 'Podobné':
				for carousel in block['carousels']:
					for item in carousel['tiles']:
						if item['action']['params']['schema'] == 'PageContentDisplayApiAction':
							item_type = item['action']['params']['contentType']

							if item_type in ('show', 'movie', 'epgitem'):
								ret.append({
									'type': 'series' if item_type == 'show' else 'video',
									'id': item['action']['params']['payload']['contentId'],
									'title':  item['title'],
									'img': self._get_img(item),
								})

		return ret

	# #################################################################################################
