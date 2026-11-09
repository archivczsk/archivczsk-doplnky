# -*- coding: utf-8 -*-
#
# Skylink Live TV (Slovak and Czech) - Solocoo / M7 platform.
#
# Login (no captcha, plain JSON):
#   1. POST /v1/provision   {deviceInfo}                        -> provisionData (bound to deviceSerial)
#   2. POST .../login       {provisionData, deviceInfo}         -> ssoToken (ticket for the login)
#   3. POST .../login       {ticket, userInput:{username,...}}  -> user's ssoToken
#   4. POST /v1/session     {ssoToken, provisionData, ...}      -> token for the Authorization header
#
# ssoToken is long-lived (stored in the settings), the session token is valid for about half
# an hour and is refreshed automatically. deviceSerial is generated once and stored, so the
# addon doesn't take a new device slot on every start.
#
# Content:  /v1/bouquet (channel list), /v1/collections (genres), /v1/assets, /v1/schedule
# Playback: POST /v1/assets/<id>/play -> DASH manifest + license URL (Widevine)
#
# The code is written to run on Python 2 and 3 (older Enigma2 images).

import base64
import hashlib
import hmac
import json as json_mod
import calendar
import threading
import uuid
from time import time, strftime, strptime, gmtime

try:
	# on Python 2 the first strptime may fail when called by several threads at once
	import _strptime
	del _strptime
except ImportError:
	pass

TVAPI_URL = 'https://tvapi.solocoo.tv'
LOGIN_URL = 'https://m7.login.solocoo.tv/login'

# Build number. It is written to the log and changes with every package, so the log shows
# which build is running. A build change also forces one new schedule export.
ADDON_BUILD = 10

APP_VERSION = '13.3'
FEATURE_LEVEL = 8

# the server accepts only schedule times aligned to quarter hours
EPG_ALIGN = 900

# The login service requires a signed Authorization header. The key and secret are
# baked into their web client - it is only a check that the request came from their
# client, it has nothing to do with the user's login.
CLIENT_KEY = 'web.NhFyz4KsZ54'
CLIENT_SECRET = 'OXh0-pIwu3gEXz1UiJtqLPscZQot3a0q'

# we identify as their web player - the server doesn't let other devices log in
DEVICE_OS = 'Windows 10'
DEVICE_MODEL = 'Chrome'
DEVICE_PRETTY_NAME = 'Chrome 138.0.0.0'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36')
# Response timeout. The framework would otherwise use the "loading_timeout" setting,
# where zero means wait forever - that would block the whole run during the schedule
# export or in the description threads, so we keep our own limit.
TIMEOUT = 20
TOKEN_MARGIN = 120  # seconds before the token expires it is refreshed

# Platform brands. Login and API are the same, only the brand and country differ.
BRANDS = {
	'slsk': {'country': 'SK', 'language': 'sk_SK', 'web': 'https://livetv.skylink.sk', 'title': 'Skylink SK'},
	'slcz': {'country': 'CZ', 'language': 'cs_CZ', 'web': 'https://livetv.skylink.cz', 'title': 'Skylink CZ'},
}

# Player reported to the server - it selects DASH and Widevine based on it
PLAYER_INFO = {
	'name': 'RxPlayer',
	'version': '4.3.0',
	'capabilities': {
		'mediaTypes': ['DASH'],
		'drmSystems': ['Widevine'],
		'audioQualities': ['DolbyAtmos', 'DolbyDigital', 'Stereo'],
		'smartLib': True,
		'embeddedSubtitles': True,
		'cdnCallbacks': True,
	}
}


# ##################################################################################################################

def error_text(e):
	"""Exception text safe for Python 2 and 3 (py2 str() fails on non-ASCII)."""
	msg = None
	try:
		if getattr(e, 'args', None):
			msg = e.args[0]
	except Exception:
		msg = None

	if msg is None:
		try:
			msg = str(e)
		except Exception:
			msg = e.__class__.__name__

	if not isinstance(msg, str):
		try:
			msg = msg.decode('utf-8') if isinstance(msg, bytes) else ('%s' % (msg,))
		except Exception:
			msg = e.__class__.__name__

	return msg


def _b64url(data):
	"""Base64 without padding and with URL safe characters - like their client."""
	text = base64.b64encode(data)
	if not isinstance(text, str):
		text = text.decode('ascii')
	return text.replace('+', '-').replace('/', '_').rstrip('=')


def sign_header(url, body):
	"""Authorization header for the login service.

	The signature is computed from the URL, the request body digest and the time:
	sig = base64url(HMAC-SHA256(url + base64url(sha256(body)) + time, key))
	"""
	if not isinstance(body, bytes):
		body = body.encode('utf-8')

	timestamp = str(int(time()))
	body_hash = _b64url(hashlib.sha256(body).digest())

	message = (url + body_hash + timestamp).encode('utf-8')
	secret = base64.b64decode(CLIENT_SECRET.replace('_', '/').replace('-', '+'))
	signature = _b64url(hmac.new(secret, message, hashlib.sha256).digest())

	return 'Client key=%s,time=%s,sig=%s' % (CLIENT_KEY, timestamp, signature)


def to_timestamp(value):
	"""Converts an API time (2026-10-27T05:00:00Z) to seconds since the epoch."""
	if not value:
		return 0

	text = value.replace('Z', '').split('.')[0].replace('T', ' ')
	try:
		struct = strptime(text, '%Y-%m-%d %H:%M:%S')
	except Exception:
		return 0

	# the API gives times in UTC
	return calendar.timegm(struct)


def api_time(timestamp):
	"""Time for the API - UTC in the 2026-10-27T23:00:00.000Z format."""
	return strftime('%Y-%m-%dT%H:%M:%S.000Z', gmtime(timestamp))


def event_description(event):
	"""Programme description. The API schedule has no description, so it is assembled
	from the data it has - genre, format, series and age rating."""
	desc = event.get('desc')
	if desc:
		return desc

	params = event.get('params') or {}
	parts = []

	for group in ('formats', 'genres'):
		for item in (params.get(group) or []):
			if isinstance(item, dict) and item.get('title'):
				parts.append(item['title'])

	season = params.get('seriesSeason')
	episode = params.get('seriesEpisode')
	if season and episode:
		parts.append('S%s:E%s' % (season, episode))
	elif episode:
		parts.append('E%s' % episode)

	age = params.get('age')
	if age:
		parts.append('%s+' % age)

	return ', '.join(parts)


def image_url(url, width=0, height=0):
	"""Adds the requested size to the image URL. Without it the server returns the original,
	which is too big and the receiver fails to load it."""
	if not url or not width:
		return url

	for marker in ('?w=', '&w=', '?h=', '&h='):
		if marker in url:
			return url

	separator = '&' if '?' in url else '?'
	size = 'w=%d' % width
	if height:
		size += '&h=%d' % height
	return url + separator + size


def unwrap_asset(entry):
	"""The channel list returns every channel wrapped in assetInfo - unwraps it."""
	if not isinstance(entry, dict):
		return entry
	inner = entry.get('assetInfo')
	if isinstance(inner, dict) and inner:
		return inner
	return entry


def has_online_stream(entry):
	"""Channels available only via satellite have empty sources - there is no stream for them."""
	if not isinstance(entry, dict) or 'sources' not in entry:
		return True

	for source in entry.get('sources') or []:
		if isinstance(source, dict) and source.get('type') == 'ott':
			return True

	return False


def channel_id(asset):
	"""Channel identifier - named differently depending on the endpoint."""
	if not isinstance(asset, dict):
		return None
	for key in ('id', 'channelId', 'assetId', 'stationId'):
		value = asset.get(key)
		if value:
			return '%s' % (value,)
	params = asset.get('params')
	if isinstance(params, dict):
		for key in ('channelId', 'id'):
			if params.get(key):
				return '%s' % (params[key],)
	return None


def channel_title(asset):
	for key in ('title', 'name', 'channelName'):
		value = asset.get(key)
		if value:
			return value
	return ''


class SkylinkSessionError(Exception):
	"""Expired or invalid login - the caller should try to log in again."""
	pass


class SkylinkNoStreamError(Exception):
	"""The channel is in the list, but Skylink has no internet stream for it."""
	pass


# ##################################################################################################################

class SkylinkApi(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()

		self.brand = 'slsk'
		self.device_serial = None
		self.provision_data = None
		self.login_endpoint = LOGIN_URL
		self.token = None
		self.token_valid_until = 0
		self.sso_token = None
		self.user_info = {}
		self._desc_cache = {}
		self._token_lock = threading.RLock()
		self._desc_lock = threading.Lock()

	# ##############################################################################################################
	# helpers

	def _brand_info(self):
		return BRANDS.get(self.brand) or BRANDS['slsk']

	def web_url(self):
		return self._brand_info()['web']

	def device_info(self):
		"""Device data - sent with provisioning and login.

		We identify like their web player. With custom values (Enigma2 and the like)
		the login ends with authorization_failed.
		"""
		info = self._brand_info()
		return {
			'osVersion': DEVICE_OS,
			'deviceModel': DEVICE_MODEL,
			'deviceType': 'PC',
			'deviceSerial': self.device_serial,
			'deviceOem': DEVICE_MODEL,
			'devicePrettyName': DEVICE_PRETTY_NAME,
			'appVersion': APP_VERSION,
			'language': info['language'],
			'brand': self.brand,
			'country': info['country'],
		}

	def _headers(self):
		web = self.web_url()
		return {
			'Accept': 'application/json, text/plain, */*',
			'Content-Type': 'application/json',
			'Origin': web,
			'Referer': web + '/',
			'User-Agent': USER_AGENT,
		}

	@staticmethod
	def _result_error(result):
		"""Assembles the error text from the platform response, if there is any."""
		if not isinstance(result, dict):
			return None

		res = result.get('result')
		if res is not None and ('%s' % (res,)).lower() not in ('success', 'ok', 'true', 'proceed'):
			return '%s (%s)' % (result.get('label') or result.get('Message') or 'error', res)

		if result.get('Message') and not result.get('url'):
			return '%s: %s' % (result.get('label') or 'error', result.get('Message'))

		return None

	def request_timeout(self):
		"""Response timeout - the user setting if there is one, otherwise our limit."""
		try:
			value = int(self.cp.get_setting('loading_timeout'))
		except Exception:
			value = 0
		return value if value > 0 else TIMEOUT

	def _request(self, method, url, params=None, data=None, authorized=False, allow_retry=True):
		headers = self._headers()

		if authorized:
			self._ensure_token()
			headers['Authorization'] = 'Bearer %s' % self.token

		response = self.req_session.request(method, url, params=params, json=data,
		                                    headers=headers, timeout=self.request_timeout())

		if response.status_code in (401, 403) and authorized:
			# the token or the login expired
			self.token = None
			self.token_valid_until = 0
			if allow_retry:
				self.cp.log_info('Token expired, creating a new session')
				try:
					with self._token_lock:
						# another thread may have refreshed the session meanwhile - don't do it twice
						if not self.token or not self.token_valid_until:
							self.create_session()
				except Exception as e:
					raise SkylinkSessionError(error_text(e) or 'Session expired')
				return self._request(method, url, params=params, data=data,
				                     authorized=True, allow_retry=False)

			message = ''
			try:
				result = response.json() or {}
				if isinstance(result, dict):
					message = result.get('label') or result.get('Message') or ''
			except Exception:
				message = ''

			raise SkylinkSessionError(message or 'Session expired')

		if response.status_code == 404:
			try:
				label = (response.json() or {}).get('label') or ''
			except Exception:
				label = ''

			if label.endswith('cannot_play'):
				raise SkylinkNoStreamError(label)

			raise Exception('HTTP 404')

		try:
			result = response.json()
		except Exception:
			result = None

		if result is None:
			response.raise_for_status()
			return {}

		err = self._result_error(result)
		if err:
			raise Exception(err)

		if response.status_code >= 400:
			raise Exception('HTTP %d' % response.status_code)

		# the header says how long the token is valid
		expires = response.headers.get('x-expires-after')
		if expires:
			try:
				self.token_valid_until = time() + int(expires) - TOKEN_MARGIN
			except Exception:
				pass

		return result

	def _api(self, path, params=None, data=None, method=None):
		return self._request(method or ('POST' if data is not None else 'GET'),
		                     TVAPI_URL + path, params=params, data=data, authorized=True)

	# ##############################################################################################################
	# login

	def setup(self, brand, device_serial, sso_token):
		"""Sets the brand, the device serial number and the stored session."""
		if brand in BRANDS:
			self.brand = brand
		self.device_serial = device_serial or self.new_device_serial()
		self.sso_token = sso_token or None
		self.token = None
		self.token_valid_until = 0
		self.provision_data = None
		self._desc_cache = {}

	@staticmethod
	def new_device_serial():
		# prefix w = web client; the login service refuses other prefixes
		return 'w' + str(uuid.uuid4())

	@staticmethod
	def valid_device_serial(serial):
		return bool(serial) and serial.startswith('w') and len(serial) == 37

	def provision(self, force=False):
		"""Registers the device and gets provisionData + the login function URLs."""
		if self.provision_data and not force:
			return self.provision_data

		info = self._brand_info()
		data = dict(self.device_info())
		data.pop('country', None)
		data['language'] = 'en_US'
		data['featureLevel'] = FEATURE_LEVEL

		result = self._request('POST', TVAPI_URL + '/v1/provision', data=data)

		session = result.get('session') or {}
		self.provision_data = session.get('provisionData')

		provider = result.get('provider') or {}
		functions = provider.get('functions') or {}
		endpoint = (functions.get('login') or {}).get('endpoint')
		if endpoint:
			self.login_endpoint = endpoint

		if not self.provision_data:
			raise Exception('No provisionData received (brand %s)' % self.brand)

		self.cp.log_debug('Provisioned for brand %s (%s)' % (self.brand, info['country']))
		return self.provision_data

	def _login_request(self, data):
		# the body is serialised by us - the signature is computed from the exact bytes sent
		body = json_mod.dumps(data, separators=(',', ':'))

		headers = self._headers()
		headers['Authorization'] = sign_header(self.login_endpoint, body)

		response = self.req_session.post(self.login_endpoint, data=body.encode('utf-8'),
		                                 headers=headers, timeout=self.request_timeout())
		try:
			result = response.json()
		except Exception:
			response.raise_for_status()
			raise Exception('Unexpected login response')

		if not isinstance(result, dict):
			raise Exception('Unexpected login response')

		err = self._result_error(result)
		if err:
			self.cp.log_debug('Login response: HTTP %d, fields %s, message: %s' % (
				response.status_code, ', '.join(sorted(result.keys())),
				('%s' % (result.get('Message'),))[:200]))
			raise Exception(err)

		return result

	def start_login(self):
		"""First step - the server returns either a ticket for entering username and password,
		or directly the ssoToken when the device is already assigned to the account."""
		self.provision()

		result = self._login_request({
			'provisionData': self.provision_data,
			'deviceInfo': self.device_info(),
		})

		sso = result.get('ssoToken')
		if sso:
			return None, sso

		ticket = result.get('ticket')
		if not ticket:
			self.cp.log_debug('Login response fields: %s' % ', '.join(sorted(result.keys())))
			raise Exception(result.get('label') or 'No login ticket received')

		return ticket, None

	def login(self, username, password):
		"""Logs the user in and returns the long-lived ssoToken."""
		ticket, sso = self.start_login()

		if not sso:
			result = self._login_request({
				'ticket': ticket,
				'userInput': {
					'username': username,
					'password': password,
				}
			})
			sso = result.get('ssoToken')

		if not sso:
			raise Exception('Login failed')

		self.sso_token = sso
		return sso

	def create_session(self, remove_device=None):
		"""Exchanges the ssoToken for an API token (Authorization header)."""
		if not self.sso_token:
			raise SkylinkSessionError('No sign-in data')

		self.token_valid_until = 0
		self.provision()

		data = dict(self.device_info())
		data.pop('country', None)
		data['ssoToken'] = self.sso_token
		data['provisionData'] = self.provision_data
		data['memberId'] = '0'
		data['featureLevel'] = FEATURE_LEVEL
		if remove_device:
			data['removeDevice'] = remove_device

		result = self._request('POST', TVAPI_URL + '/v1/session', data=data)

		token = result.get('token')
		if not token:
			raise SkylinkSessionError(result.get('label') or 'No token received')

		self.token = token
		if result.get('ssoToken') and result['ssoToken'] != self.sso_token:
			# the platform sometimes replaces the login token when the session is refreshed -
			# the new one must be stored, otherwise the stored session would stop matching
			self.sso_token = result['ssoToken']
			try:
				self.cp.save_session(self.sso_token)
			except Exception:
				self.cp.log_error('Failed to save the refreshed sign-in token')
		if not self.token_valid_until:
			self.token_valid_until = time() + 1500

		self.user_info = {
			'user': result.get('userName') or result.get('subscriberId') or '',
			'community': result.get('communityName') or '',
			'brand': result.get('brandName') or '',
			'country': result.get('countryCode') or '',
			'customer_id': result.get('crmCustomerId') or '',
		}

		return token

	def _ensure_token(self):
		if self.token and (not self.token_valid_until or time() <= self.token_valid_until):
			return

		# several threads may try to get a new session at once, only one is let through
		with self._token_lock:
			if not self.token or (self.token_valid_until and time() > self.token_valid_until):
				self.create_session()

	def logged_in(self):
		return bool(self.token)

	# ##############################################################################################################
	# content

	def _log_structure(self, name, data):
		"""Logs the shape of the response - keys and a sample of the first item, without values."""
		try:
			if isinstance(data, dict):
				parts = []
				for key in list(data.keys())[:12]:
					value = data[key]
					if isinstance(value, list):
						parts.append('%s[%d]' % (key, len(value)))
					else:
						parts.append(key)
				self.cp.log_debug('%s: dict(%s)' % (name, ', '.join(parts)))

				for key in data:
					value = data[key]
					if isinstance(value, list) and value and isinstance(value[0], dict):
						first = value[0]
						self.cp.log_debug('%s: %s[0] type=%s fields %s' % (
							name, key, first.get('type'), ', '.join(sorted(first.keys()))[:200]))
						break
			elif isinstance(data, list):
				self.cp.log_debug('%s: list(%d)' % (name, len(data)))
				if data and isinstance(data[0], dict):
					self.cp.log_debug('%s: [0] type=%s fields %s' % (
						name, data[0].get('type'), ', '.join(sorted(data[0].keys()))[:200]))
			else:
				self.cp.log_debug('%s: %s' % (name, type(data).__name__))
		except Exception:
			pass

	@staticmethod
	def _assets_from(data):
		"""Picks the item list from the response - different endpoints name it differently."""
		if isinstance(data, list):
			return [x for x in data if isinstance(x, dict)]

		if not isinstance(data, dict):
			return []

		for key in ('assets', 'channels', 'bouquet', 'items', 'collection', 'devices', 'epg'):
			value = data.get(key)
			if isinstance(value, list):
				return [x for x in value if isinstance(x, dict)]

		# unknown shape - take the first list of dicts with an id
		for value in data.values():
			if isinstance(value, list) and value and isinstance(value[0], dict) and 'id' in value[0]:
				return value

		return []

	def get_entitled_offers(self):
		"""Codes of the offers (packages) the account is subscribed to - from /v1/entitlements.
		Returns None on error, then no filtering by subscription takes place."""
		try:
			data = self._api('/v1/entitlements')
		except SkylinkSessionError:
			raise
		except Exception as e:
			self.cp.log_error('Failed to read entitlements: %s' % error_text(e))
			return None

		if not isinstance(data, dict):
			return None

		offers = set()
		for item in data.get('offers') or []:
			if isinstance(item, dict) and item.get('id') is not None:
				offers.add('%s' % (item['id'],))
			elif isinstance(item, (str, int)):
				offers.add('%s' % (item,))

		self.cp.log_debug('Entitled offers: %s' % ', '.join(sorted(offers, key=lambda x: (len(x), x))))
		return offers

	@staticmethod
	def asset_offers(asset):
		"""Codes of the offers the channel is part of (deals -> offers)."""
		offers = set()
		for deal in (asset or {}).get('deals') or []:
			if isinstance(deal, dict):
				for o in deal.get('offers') or []:
					offers.add('%s' % (o,))
		return offers

	def get_channels(self, force=False, only_subscribed=True):
		"""Channel list sorted by channel number. The cache is kept by the provider.
		only_subscribed - skips channels that are in no subscribed offer
		(the server sends them in the list, but they can't be played: offer_missing)."""
		channels = []
		try:
			data = self._api('/v1/bouquet')
			self._log_structure('Bouquet', data)
			channels = self._assets_from(data)
		except SkylinkSessionError:
			raise
		except Exception as e:
			self.cp.log_error('Failed to read the channel list: %s' % error_text(e))

		if not channels:
			# fallback - assemble the channels from the genre groups
			channels = self._channels_from_groups()

		entitled = self.get_entitled_offers() if only_subscribed else None

		result = []
		seen = set()
		skipped = 0
		for entry in channels:
			if not has_online_stream(entry):
				continue

			ch = unwrap_asset(entry)
			cid = channel_id(ch)
			if not cid or cid in seen:
				continue

			if entitled is not None:
				offers = self.asset_offers(ch)
				# a channel without offers is kept - nothing can be said about its availability
				if offers and not (offers & entitled):
					skipped += 1
					continue

			seen.add(cid)
			result.append(ch)

		self.cp.log_debug('Channels: %d from server, %d usable, %d outside subscription' % (len(channels), len(result), skipped))

		result.sort(key=lambda c: ((c.get('params') or {}).get('lcn') or 9999, c.get('title') or ''))

		return result

	def _channels_from_groups(self):
		channels = []
		try:
			for group in self.get_channel_groups():
				query = group.get('query')
				if not query:
					continue
				try:
					assets, _next = self.get_assets(query, limit=200, params=group.get('params'))
				except Exception as e:
					self.cp.log_error('Genre %s failed: %s' % (query, error_text(e)))
					continue
				self.cp.log_debug('Genre %s: %d items' % (query, len(assets)))
				channels.extend(assets)
		except Exception as e:
			self.cp.log_error('Failed to read channel genres: %s' % error_text(e))
		return channels

	def get_channel_groups(self):
		"""Genre groups of channels (each carries its own query for the channel list)."""
		data = self._api('/v1/collections/livetv,withadult', params={'group': 'supergenre', 'sort': 'default'})
		if not isinstance(data, dict):
			return []
		return [g for g in (data.get('collection') or []) if isinstance(g, dict)]

	def get_assets(self, query, limit=100, next_asset=None, params=None):
		"""Item list for a query. Returns (items, next page token)."""
		request_params = {'query': query, 'limit': limit}
		if isinstance(params, dict):
			for key, value in params.items():
				if value is not None:
					request_params[key] = value
		if next_asset:
			request_params['nextAsset'] = next_asset

		data = self._api('/v1/assets', params=request_params)
		if not isinstance(data, dict):
			self._log_structure('Assets %s' % query, data)
			return [], None

		assets = [unwrap_asset(a) for a in (data.get('assets') or []) if isinstance(a, dict)]
		if not assets:
			self._log_structure('Assets %s' % query, data)

		return assets, data.get('nextAsset')

	def get_descriptions(self, asset_ids, workers=8, time_limit=45):
		"""Programme descriptions for a list of items. The API doesn't send them with the schedule,
		so they are fetched from the details - in parallel and cached, because a description doesn't change.

		Errors are not cached, so they are retried on the next opening.
		Only one round runs at a time, otherwise the threads would pile up.
		"""
		if not self._desc_lock.acquire(False):
			# another round is still running - return what is loaded already
			return self._desc_cache

		try:
			wanted = []
			for asset_id in asset_ids:
				if asset_id and asset_id not in self._desc_cache and asset_id not in wanted:
					wanted.append(asset_id)

			if not wanted:
				return self._desc_cache

			# refresh the token before starting the threads
			self._ensure_token()

			headers = self._headers()
			headers['Authorization'] = 'Bearer %s' % self.token

			lock = threading.Lock()
			state = {'stop': False, 'loaded': 0}
			deadline = time() + time_limit

			def fetch(ids):
				# own session per thread, without retries - otherwise the wait would be too long
				session = self.cp.get_requests_session(auto_retry=False)
				try:
					for asset_id in ids:
						if state['stop'] or time() > deadline:
							break

						try:
							response = session.get(TVAPI_URL + '/v1/assets/%s' % asset_id,
							                       headers=headers, timeout=TIMEOUT)
						except Exception:
							continue

						if response.status_code in (401, 403):
							# expired token - further requests make no sense
							with lock:
								state['stop'] = True
							break

						if response.status_code != 200:
							continue

						try:
							data = response.json() or {}
						except Exception:
							continue

						if not isinstance(data, dict):
							continue

						with lock:
							self._desc_cache[asset_id] = data.get('desc') or ''
							state['loaded'] += 1
				finally:
					try:
						session.close()
					except Exception:
						pass

			if len(self._desc_cache) > 3000:
				self._desc_cache.clear()

			workers = max(1, min(workers, len(wanted)))
			threads = []
			for index in range(0, workers):
				part = wanted[index::workers]
				if not part:
					continue
				thread = threading.Thread(target=fetch, args=(part,))
				thread.daemon = True
				threads.append(thread)
				thread.start()

			# common deadline for all threads, not for each one separately
			for thread in threads:
				remaining = deadline - time()
				thread.join(remaining if remaining > 0 else 0.1)

			self.cp.log_debug('Loaded %d of %d programme descriptions' % (state['loaded'], len(wanted)))

			if state['stop']:
				# the token expired during the download - refresh it so the next round passes
				try:
					self._ensure_token()
				except Exception:
					pass

			return self._desc_cache
		finally:
			self._desc_lock.release()

	def get_schedule(self, channel_id, time_from, time_until):
		"""TV schedule of a channel for the given time range (seconds since the epoch).

		The server accepts only times aligned to quarter hours, otherwise it responds with
		"from must be a whole multiple of 15 minutes".
		"""
		start = (int(time_from) // EPG_ALIGN) * EPG_ALIGN
		end = -((-int(time_until)) // EPG_ALIGN) * EPG_ALIGN
		if end <= start:
			end = start + EPG_ALIGN

		data = self._api('/v1/schedule', params={
			'channels': channel_id,
			'from': api_time(start),
			'until': api_time(end),
		})
		if not isinstance(data, dict):
			return []

		epg = data.get('epg')
		if not isinstance(epg, dict):
			return []

		items = epg.get('%s' % (channel_id,)) or []
		return [i for i in items if isinstance(i, dict)]

	def get_schedule_now(self, channel_ids):
		"""Running and next programme for the channel list."""
		if not channel_ids:
			return {}

		data = self._api('/v1/schedule/now', params={'channels': ','.join(channel_ids)})
		if not isinstance(data, dict):
			return {}

		epg = data.get('epg')
		return epg if isinstance(epg, dict) else data

	def get_devices(self):
		"""Devices registered on the account."""
		data = self._api('/v1/devices')
		devices = self._assets_from(data) if not isinstance(data, list) else data
		return [d for d in devices if isinstance(d, dict)]

	def get_stream(self, asset_id, playready=False):
		"""Returns the DASH manifest and license URL for the given item."""
		player = PLAYER_INFO
		if playready:
			# with PlayReady the server issues a key for 1080p too
			player = dict(player)
			player['capabilities'] = dict(player['capabilities'], drmSystems=['PlayReady'])

		result = self._api('/v1/assets/%s/play' % asset_id, data={'player': player})

		url = result.get('url')
		drm = result.get('drm') or {}

		return {
			'url': url,
			'license_url': drm.get('licenseUrl') or '',
			'drm_system': drm.get('system') or '',
			'media_type': result.get('mediaType') or '',
			'title': result.get('statsChannelName') or '',
		}
