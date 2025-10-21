# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache

import json

try:
	from urlparse import urlparse, urlunparse, parse_qs
	from urllib import urlencode
except:
	from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

class SCAuthException(AddonErrorException):
	pass

# ##################################################################################################################

class SC_API(object):
	def __init__(self, content_provider):
		self.cp = content_provider

		self.device_id = self.cp.get_setting('deviceid')

		self.req_session = self.cp.get_requests_session()
		self.cache = ExpiringLRUCache(30, 1800)
		self.token = None

	# ##################################################################################################################

	def load_token(self):
		login_data = self.cp.load_cached_data('sc')

		if login_data.get('token'):
			self.cp.log_info("Auth token loaded from local cache")
			token = login_data['token']

			if self.cp.kraska.login_data.get('checksum') != login_data.get('kr_checksum'):
				self.cp.log_info("SC auth token was created for another Kraska account - ignoring")
				token = None
			else:
				if login_data.get('addon_ver') != self.cp.get_addon_version():
					self.update_token(token)
					self.cp.update_cached_data('sc', {'addon_ver': self.cp.get_addon_version()})
		else:
			token = None
			self.cp.log_info("No cached auth token found")

		return token

	# ##################################################################################################################

	def update_token(self, token):
		try:
			krt = self.cp.kraska.get_token()

			ret = self.call_api('/auth/token/update', data='', params={'krt': krt, 'token': token})
			self.cp.log_debug("Token update response: %s" % ret)
		except:
			self.cp.log_exception()


	# ##################################################################################################################

	def save_token(self):
		if self.token:
			self.cp.save_cached_data('sc', {
				'token': self.token,
				'addon_ver': self.cp.get_addon_version(),
				'kr_checksum': self.cp.kraska.login_data.get('checksum')
			})

	# ##################################################################################################################

	@staticmethod
	def create_device_id():
		import uuid
		return str(uuid.uuid4())


	# ##################################################################################################################

	def call_api(self, url, data=None, params=None):
		if url.startswith('/auth/'):
			token = None
		else:
			token = self.token

			if not token:
				raise SCAuthException(self.cp._("You are not authorized to access Stream Cinema service"))

		if not url.startswith("https://"):
			url = "https://stream-cinema.online/kodi" + url

		default_params = {
			'ver': '2.0',
			'uid': self.device_id,
			'lang': self.cp.dubbed_lang_list[0],
		}

		# extract params from url and add them to default_params
		u = urlparse(url)
		default_params.update(parse_qs(u.query))
		url = urlunparse((u.scheme, u.netloc, u.path, '', '', ''))

		if params:
			default_params.update(params)

		if self.cp.get_setting('item-lang-filter') == 'dubsubs':
			# zobraz len filmy s dabingom alebo titulkami
			if 'tit' not in default_params:
				default_params.update({"tit": 1})

			if 'dub' not in default_params:
				default_params.update({'dub': 1})

		elif self.cp.get_setting('item-lang-filter') == 'dub' and 'dub' not in default_params:
			default_params.update({'dub': 1}) # zobraz len dabovane filmy

		# podla nastaveni skontroluj a pripadne uprav rating pre rodicovsku kontrlu
		mr_setting = int(self.cp.get_setting('maturity-rating'))
		mr_params = default_params.get('m', 1000)
		if isinstance(mr_params, type([])):
			mr_params = mr_params[0]

		if mr_setting >= 0 and int(mr_params) > mr_setting:
			default_params.update({"m": mr_setting})

		default_params.update({'gen': 1 if self.cp.get_setting('show-genre') else 0 }) # zobraz zaner v nazve polozky

		if not params or 'HDR' not in params:
			default_params.update({'HDR': 1 if self.cp.get_setting('show-hdr') else 0 }) #zobrazit HDR ano/nie 1/0

		if not params or 'DV' not in params:
			default_params.update({'DV': 0 }) # zobrazit dolby vidion filmy ano/nie 1/0 - ziaden enigma2 prijimac toto nepodoruje

		if self.cp.get_setting('old-menu'):
			default_params.update({'old': 1 }) # zobrazit povodny typ menu

		for k in ('HDR', 'tit', 'dub'):
			# -1 means ANY for some parameters, but not for these, so remove them
			if default_params.get(k) == -1:
				del default_params[k]

		headers = {
			'User-Agent': 'ArchivCZSK/%s (plugin.video.stream-cinema/%s)' % (self.cp.get_engine_version(), self.cp.get_addon_version()),
			'X-Uuid': self.device_id
		}

		if token:
			headers['X-AUTH-TOKEN'] = token

		if data != None:
			rurl = url + '?' + urlencode(sorted(default_params.items(), key=lambda val: val[0]), True)
			resp = self.req_session.post(rurl, data=data, headers=headers)
		else:
			rurl = url + '?' + urlencode(sorted(default_params.items(), key=lambda val: val[0]), True)

			resp = self.cache.get(rurl)
			if resp:
				self.cp.log_debug("Request found in cache")
				return resp

			resp = self.req_session.get(rurl, headers=headers)
#		dump_json_request(resp)

		if resp.status_code == 200:
			resp = resp.json()

			if not data:
				ttl = 3600
				if 'system' in resp and 'TTL' in resp['system']:
					ttl = int(resp['system']['TTL'])

				self.cache.put(rurl, resp, ttl)

			return resp
		elif resp.status_code == 404 or not token:
			raise SCAuthException(self.cp._("Stream Cinema service is not available or you don't have access to it.\nServer returned HTTP error code {code} with description \"{reason}\".").format(code=resp.status_code, reason=resp.reason))
		else:
			raise AddonErrorException(self.cp._("Stream Cinema service is not available or you don't have access to it.\nServer returned HTTP error code {code} with description \"{reason}\".").format(code=resp.status_code, reason=resp.reason))

	# ##################################################################################################################

	def save_backup_token(self):
		if not self.token:
			return

		kr = self.cp.kraska

		try:
			if kr.refresh_login_data() > 0:
				self.cp.log_info("Saving auth token to kraska")
				kr.upload(self.token, 'sc_token.txt')
		except:
			self.cp.log_exception()

	# ##################################################################################################################

	def load_backup_token(self):
		kr = self.cp.kraska
		tokens = []

		try:
			if kr.refresh_login_data() > 0:
				for name in ('sc_token.txt', 'sc.json'):
					found = kr.list_files(filter=name)

					if len(found.get('data', [])) == 1:
						for f in found.get('data', []):
							url = kr.resolve(f.get('ident'))
							data = self.req_session.get(url)
							if len(data.text) == 32:
								# raw token file
								tokens.append(data.text)
								self.cp.log_info("Auth token %s loaded from kraska" % name)
							else:
								# try real json encoded file
								try:
									token = json.loads(data.text)['token']
									if len(token) == 32:
										tokens.append(token)
										self.cp.log_info("Auth token %s in alternative format loaded from kraska" % name)
								except:
									pass

					else:
						self.cp.log_info("Backup file %s with auth token not found" % name)
		except:
			self.cp.log_exception()

		return tokens

	# ##################################################################################################################

	def check_token(self):
		try:
			self.call_api('/')
			return True
		except SCAuthException:
			return False

	# ##################################################################################################################

	def set_auth_token(self, force=False):
		if force == False and self.token:
			return

		self.token = self.load_token()

		if self.token:
			if self.check_token():
				self.cp.log_info("Local auth token is valid")
				return
			else:
				self.cp.log_error("Local auth token is invalid")
		else:
			self.cp.log_info("Local auth token not found")

		self.token = None

		# try to load token from backup
		for i, token in enumerate(self.load_backup_token()):
			self.cp.log_info("Trying token #%s from backup ..." % i)
			self.token = token
			if self.check_token():
				self.cp.log_info("Token #%s from backup is valid" % i)
				# valid token loaded from backup
				self.save_token()
				return
			else:
				self.cp.log_info("Token #%s from backup is invalid" % i)

		self.token = None
		krt = self.cp.kraska.get_token()
		token_data = self.cp.load_cached_data('sc')

		if krt and (token_data.get('id') != self.device_id or token_data.get('krt') != krt):
			# the last chance - try to get token directly from sc server
			self.cp.log_info("Requesting auth token from server")
			try:
				ret = self.call_api('/auth/token', data='', params={'krt': krt})
			except:
				ret = {}
				self.cp.log_exception()

			if not ret.get('token'):
				self.cp.log_error("Error in getting auth token from SC server: %s" % ret)
				return

			self.token = ret['token']
			self.save_token()
			self.cp.update_cached_data('sc', {'id': self.device_id, 'krt': krt})

			if self.check_token():
				self.cp.log_info("Received valid token from SC server")
				self.save_backup_token()
				return

			self.cp.log_error("Auth token received from SC server is invalid")

		self.cp.log_error("No valid auth token available")
		self.token = None

	# ##################################################################################################################
