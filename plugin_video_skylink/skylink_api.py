# -*- coding: utf-8 -*-
#
# Skylink Live TV (slovenský aj český) - platforma Solocoo / M7.
#
# Prihlásenie (bez captchy, obyčajný JSON):
#   1. POST /v1/provision   {deviceInfo}                        -> provisionData (viaže sa na deviceSerial)
#   2. POST .../login       {provisionData, deviceInfo}         -> ssoToken (lístok pre prihlásenie)
#   3. POST .../login       {ticket, userInput:{username,...}}  -> ssoToken používateľa
#   4. POST /v1/session     {ssoToken, provisionData, ...}      -> token do hlavičky Authorization
#
# ssoToken je dlhodobý (ukladá sa do nastavení), token zo session platí cca pol hodiny
# a obnovuje sa sám. deviceSerial sa generuje raz a ukladá, aby doplnok nezaberal
# nové zariadenie pri každom štarte.
#
# Obsah:  /v1/bouquet (zoznam kanálov), /v1/collections (žánre), /v1/assets, /v1/schedule
# Prehrávanie: POST /v1/assets/<id>/play -> DASH manifest + licenčná adresa (Widevine)
#
# Kód je písaný tak, aby bežal na Pythone 2 aj 3 (staršie Enigma2 image).

import base64
import hashlib
import hmac
import json as json_mod
import calendar
import threading
import uuid
from time import time, strftime, strptime, gmtime

try:
	# na Python 2 vie prvé strptime zlyhať, ak ho naraz zavolá viac vlákien
	import _strptime
	del _strptime
except ImportError:
	pass

TVAPI_URL = 'https://tvapi.solocoo.tv'
LOGIN_URL = 'https://m7.login.solocoo.tv/login'

# Verzia doplnku a poradie zostavenia. Zostavenie sa zapisuje do logu a mení sa
# s každým balíkom, takže z logu vidno, ktorá verzia práve beží. Zmena zostavenia
# zároveň vynúti jeden nový export programu.
ADDON_VERSION = '1.2'
ADDON_BUILD = 5

APP_VERSION = '13.3'
FEATURE_LEVEL = 8

# server prijme v programe len časy zarovnané na štvrťhodiny
EPG_ALIGN = 900

# Prihlasovacia služba vyžaduje podpísanú hlavičku Authorization. Kľúč a tajomstvo
# sú zapečené v ich webovom klientovi - je to len kontrola, že požiadavka prišla od
# ich klienta, s prihlásením používateľa to nesúvisí.
CLIENT_KEY = 'web.NhFyz4KsZ54'
CLIENT_SECRET = 'OXh0-pIwu3gEXz1UiJtqLPscZQot3a0q'

# Hlásime sa ako ich webový prehrávač - server iné zariadenia na prihlásenie nepustí
DEVICE_OS = 'Windows 10'
DEVICE_MODEL = 'Chrome'
DEVICE_PRETTY_NAME = 'Chrome 138.0.0.0'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36')
# Strop na čakanie na odpoveď. Framework inak použije nastavenie "loading_timeout",
# kde nula znamená čakať donekonečna - to by pri exporte programu alebo vo vláknach
# s popismi zablokovalo celý beh, preto si strop držíme.
TIMEOUT = 20
TOKEN_MARGIN = 120  # sekúnd pred vypršaním tokenu ho obnovíme

# Značky platformy. Prihlásenie aj API sú rovnaké, líši sa len značka a krajina.
BRANDS = {
	'slsk': {'country': 'SK', 'language': 'sk_SK', 'web': 'https://livetv.skylink.sk', 'title': 'Skylink SK'},
	'slcz': {'country': 'CZ', 'language': 'cs_CZ', 'web': 'https://livetv.skylink.cz', 'title': 'Skylink CZ'},
}

# Prehrávač, ktorý hlásime serveru - podľa neho vyberie DASH a Widevine
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
	"""Text výnimky bezpečne pre Python 2 aj 3 (py2 str() padá na diakritike)."""
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
	"""Base64 bez výplne a s bezpečnými znakmi - rovnako ako ich klient."""
	text = base64.b64encode(data)
	if not isinstance(text, str):
		text = text.decode('ascii')
	return text.replace('+', '-').replace('/', '_').rstrip('=')


def sign_header(url, body):
	"""Hlavička Authorization pre prihlasovaciu službu.

	Podpis sa počíta z adresy, odtlačku tela požiadavky a času:
	sig = base64url(HMAC-SHA256(url + base64url(sha256(telo)) + čas, kľúč))
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
	"""Prevedie čas z API (2026-10-27T05:00:00Z) na sekundy od epochy."""
	if not value:
		return 0

	text = value.replace('Z', '').split('.')[0].replace('T', ' ')
	try:
		struct = strptime(text, '%Y-%m-%d %H:%M:%S')
	except Exception:
		return 0

	# API dáva časy v UTC
	return calendar.timegm(struct)


def api_time(timestamp):
	"""Čas pre API - UTC vo formáte 2026-10-27T23:00:00.000Z."""
	return strftime('%Y-%m-%dT%H:%M:%S.000Z', gmtime(timestamp))


def event_description(event):
	"""Popis relácie. Program z API popis neobsahuje, tak ho poskladáme z údajov,
	ktoré v ňom sú - žáner, formát, séria a vekové hodnotenie."""
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
	"""Doplní do adresy obrázka požadovaný rozmer. Bez neho server vracia originál,
	ktorý je priveľký a prijímač ho nestihne načítať."""
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
	"""Zoznam kanálov vracia každý kanál zabalený v assetInfo - rozbalí ho."""
	if not isinstance(entry, dict):
		return entry
	inner = entry.get('assetInfo')
	if isinstance(inner, dict) and inner:
		return inner
	return entry


def has_online_stream(entry):
	"""Kanály dostupné len zo satelitu majú prázdne sources - stream pre ne nie je."""
	if not isinstance(entry, dict) or 'sources' not in entry:
		return True

	for source in entry.get('sources') or []:
		if isinstance(source, dict) and source.get('type') == 'ott':
			return True

	return False


def channel_id(asset):
	"""Identifikátor kanála - podľa endpointu sa volá rôzne."""
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
	"""Vypršané alebo neplatné prihlásenie - volajúci má skúsiť prihlásiť sa znova."""
	pass


class SkylinkNoStreamError(Exception):
	"""Kanál je v zozname, ale Skylink preň nemá internetový stream."""
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
	# pomocné

	def _brand_info(self):
		return BRANDS.get(self.brand) or BRANDS['slsk']

	def web_url(self):
		return self._brand_info()['web']

	def device_info(self):
		"""Údaje o zariadení - posielajú sa pri provisioningu aj prihlásení.

		Hlásime sa rovnako ako ich webový prehrávač. Pri vlastných hodnotách
		(Enigma2 a podobne) prihlásenie končí chybou authorization_failed.
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
		"""Z odpovede platformy poskladá text chyby, ak nejaká je."""
		if not isinstance(result, dict):
			return None

		res = result.get('result')
		if res is not None and ('%s' % (res,)).lower() not in ('success', 'ok', 'true', 'proceed'):
			return '%s (%s)' % (result.get('label') or result.get('Message') or 'error', res)

		if result.get('Message') and not result.get('url'):
			return '%s: %s' % (result.get('label') or 'error', result.get('Message'))

		return None

	def request_timeout(self):
		"""Čakanie na odpoveď - nastavenie používateľa, ak ho má, inak náš strop."""
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
			# token alebo prihlásenie vypršalo
			self.token = None
			self.token_valid_until = 0
			if allow_retry:
				self.cp.log_info('Token expired, creating a new session')
				try:
					with self._token_lock:
						# iné vlákno mohlo session medzitým obnoviť - nerob to druhý raz
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

		# hlavička hovorí, ako dlho token platí
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
	# prihlásenie

	def setup(self, brand, device_serial, sso_token):
		"""Nastaví značku, sériové číslo zariadenia a uloženú session."""
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
		# predpona w = webový klient; iné predpony prihlasovacia služba odmieta
		return 'w' + str(uuid.uuid4())

	@staticmethod
	def valid_device_serial(serial):
		return bool(serial) and serial.startswith('w') and len(serial) == 37

	def provision(self, force=False):
		"""Zaregistruje zariadenie a získa provisionData + adresy prihlasovacích funkcií."""
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
		# telo si serializujeme sami - podpis sa počíta presne z odoslaných bajtov
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
		"""Prvý krok - server vráti buď lístok na zadanie mena a hesla,
		alebo rovno ssoToken, keď je zariadenie k účtu už priradené."""
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
		"""Prihlási používateľa a vráti dlhodobý ssoToken."""
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
		"""Vymení ssoToken za API token (hlavička Authorization)."""
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
			# platforma prihlasovací token pri obnove session občas vymení -
			# ten nový treba uložiť, inak by uložená session prestala sedieť
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

		# o novú session sa môžu pokúsiť viaceré vlákna naraz, pustíme len jedno
		with self._token_lock:
			if not self.token or (self.token_valid_until and time() > self.token_valid_until):
				self.create_session()

	def logged_in(self):
		return bool(self.token)

	# ##############################################################################################################
	# obsah

	def _log_structure(self, name, data):
		"""Do logu zapíše tvar odpovede - kľúče a vzorku prvej položky, bez hodnôt."""
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
		"""Z odpovede vyberie zoznam položiek - rôzne endpointy ich volajú rôzne."""
		if isinstance(data, list):
			return [x for x in data if isinstance(x, dict)]

		if not isinstance(data, dict):
			return []

		for key in ('assets', 'channels', 'bouquet', 'items', 'collection', 'devices', 'epg'):
			value = data.get(key)
			if isinstance(value, list):
				return [x for x in value if isinstance(x, dict)]

		# neznámy tvar - vezmi prvý zoznam slovníkov s id
		for value in data.values():
			if isinstance(value, list) and value and isinstance(value[0], dict) and 'id' in value[0]:
				return value

		return []

	def get_channels(self, force=False):
		"""Zoznam kanálov zoradený podľa čísla programu. Cache drží provider."""
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
			# náhradná cesta - poskladaj kanály zo žánrových skupín
			channels = self._channels_from_groups()

		result = []
		seen = set()
		for entry in channels:
			if not has_online_stream(entry):
				continue

			ch = unwrap_asset(entry)
			cid = channel_id(ch)
			if not cid or cid in seen:
				continue
			seen.add(cid)
			result.append(ch)

		self.cp.log_debug('Channels: %d from server, %d usable' % (len(channels), len(result)))

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
		"""Žánrové skupiny kanálov (každá nesie vlastný dopyt na zoznam kanálov)."""
		data = self._api('/v1/collections/livetv,withadult', params={'group': 'supergenre', 'sort': 'default'})
		if not isinstance(data, dict):
			return []
		return [g for g in (data.get('collection') or []) if isinstance(g, dict)]

	def get_assets(self, query, limit=100, next_asset=None, params=None):
		"""Zoznam položiek podľa dopytu. Vráti (položky, značka ďalšej strany)."""
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
		"""Popisy relácií k zoznamu položiek. API ich pri programe neposiela,
		takže ich ťaháme z detailov - paralelne a s pamäťou, lebo popis sa už nemení.

		Chyby sa do pamäte neukladajú, aby sa pri ďalšom otvorení skúsili znova.
		Naraz beží len jedno kolo, inak by sa vlákna nakopili.
		"""
		if not self._desc_lock.acquire(False):
			# iné kolo ešte beží - vráť, čo už je načítané
			return self._desc_cache

		try:
			wanted = []
			for asset_id in asset_ids:
				if asset_id and asset_id not in self._desc_cache and asset_id not in wanted:
					wanted.append(asset_id)

			if not wanted:
				return self._desc_cache

			# token si obnovíme ešte pred rozbehnutím vlákien
			self._ensure_token()

			headers = self._headers()
			headers['Authorization'] = 'Bearer %s' % self.token

			lock = threading.Lock()
			state = {'stop': False, 'loaded': 0}
			deadline = time() + time_limit

			def fetch(ids):
				# vlastná session na vlákno, bez opakovaní - inak by sa čakalo priveľa
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
							# vypršaný token - ďalšie požiadavky už nemajú zmysel
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

			# spoločný termín pre všetky vlákna, nie pre každé zvlášť
			for thread in threads:
				remaining = deadline - time()
				thread.join(remaining if remaining > 0 else 0.1)

			self.cp.log_debug('Loaded %d of %d programme descriptions' % (state['loaded'], len(wanted)))

			if state['stop']:
				# token vypršal počas sťahovania - obnov ho, nech ďalšie kolo prejde
				try:
					self._ensure_token()
				except Exception:
					pass

			return self._desc_cache
		finally:
			self._desc_lock.release()

	def get_schedule(self, channel_id, time_from, time_until):
		"""TV program kanála pre zadaný časový rozsah (sekundy od epochy).

		Server prijme len časy zarovnané na štvrťhodiny, inak odpovie chybou
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
		"""Práve bežiaci a nasledujúci program pre zoznam kanálov."""
		if not channel_ids:
			return {}

		data = self._api('/v1/schedule/now', params={'channels': ','.join(channel_ids)})
		if not isinstance(data, dict):
			return {}

		epg = data.get('epg')
		return epg if isinstance(epg, dict) else data

	def get_devices(self):
		"""Zariadenia zaregistrované na účte."""
		data = self._api('/v1/devices')
		devices = self._assets_from(data) if not isinstance(data, list) else data
		return [d for d in devices if isinstance(d, dict)]

	def get_stream(self, asset_id, playready=False):
		"""Vráti adresu DASH manifestu a licencie pre danú položku."""
		player = PLAYER_INFO
		if playready:
			# s PlayReady server vydá kľúč aj pre 1080p
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
