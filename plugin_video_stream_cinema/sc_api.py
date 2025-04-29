# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache

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
		self.need_token_save = False
		self.load_token()

	# ##################################################################################################################

	def load_token(self):
		login_data = self.cp.load_cached_data('sc')

		if login_data.get('token'):
			self.cp.log_info("Auth token loaded from local cache")
			self.token = login_data['token']
		else:
			self.cp.log_info("No cached auth token found")

		if not self.token:
			self.load_backup_token()
			if self.token:
				self.need_token_save = True

	# ##################################################################################################################

	def save_token(self):
		if self.token:
			self.cp.save_cached_data('sc', {'token': self.token})
			self.save_backup_token()

	# ##################################################################################################################

	@staticmethod
	def create_device_id():
		import uuid
		return str(uuid.uuid4())


	# ##################################################################################################################

	def call_api(self, url, data=None, params=None, auto_refresh_token=True):
		request_url = url

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
			'X-Uuid': self.device_id,
		}

		if self.token:
			headers['X-AUTH-TOKEN'] = self.token

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

				# if GET request with refreshed token succeed, then save it
				if self.need_token_save:
					self.save_token()

			return resp
		elif resp.status_code == 404:
			if auto_refresh_token:
				self.cp.log_debug("Server returned HTTP 404 - maybe wrong auth token ...")
				self.refresh_auth_token(True)
				return self.call_api(request_url, data, params, False)
			else:
				raise SCAuthException(self.cp._("Failed to authenticate against stream cinema server. Try again later ..."))
		else:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

	# ##################################################################################################################

	def save_backup_token(self):
		if not self.token:
			return

		from .kraska import Kraska
		kr = Kraska(self.cp)

		try:
			if kr.refresh_login_data() > 0:
				self.cp.log_info("Saving auth token to kraska")
				kr.upload(self.token, 'sc_token.txt')
		except:
			self.cp.log_exception()

	# ##################################################################################################################

	def load_backup_token(self):
		from .kraska import Kraska

		kr = Kraska(self.cp)

		try:
			if kr.refresh_login_data() > 0:
				for name in ('sc_token.txt', 'sc.json'):
					found = kr.list_files(filter=name)

					if len(found.get('data', [])) == 1:
						for f in found.get('data', []):
							url = kr.resolve(f.get('ident'))
							data = self.req_session.get(url)
							if len(data.text) == 32:
								self.token = data.text
								self.cp.log_info("Auth token loaded from kraska")
								return
					else:
						self.cp.log_info("Backup file %s with auth token not found" % name)
		except:
			self.cp.log_exception()


	# ##################################################################################################################

	def refresh_auth_token(self, force=False, try_nr=0):
		if self.token and not force:
			return

		token = self.token

		# try to get auth token from backup
		self.load_backup_token()
		if self.token != token:
			self.need_token_save = True
			return

		self.cp.log_info("Requesting auth token from server")
		try:
			self.token = None
			self.need_token_save = False
			ret = self.call_api('/auth/token', data='', auto_refresh_token=False)
		except:
			ret = {}
			self.cp.log_exception()

		if 'error' in ret:
			self.cp.log_error("Error in getting auth token: %s" % str(ret))
			return

		if 'token' not in ret:
			self.cp.log_error("Response doesn't contain auth token: %s" % str(ret))
			return

		if ret['token'] != token:
			self.token = ret['token']
			self.need_token_save = True
		else:
			self.cp.log_info("New auth token is the same as the current one")

			if force and try_nr == 0:
				# rebuild device ID and try again ...
				self.device_id = self.create_device_id()
				self.cp.set_setting('deviceid', self.device_id)
				self.cp.log_info("Created new device ID: %s" % self.device_id)
				return self.refresh_auth_token(True, try_nr+1)

	# ##################################################################################################################
