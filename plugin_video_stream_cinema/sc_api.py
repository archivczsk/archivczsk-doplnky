# -*- coding: utf-8 -*-

import requests
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache

try:
	from urlparse import urlparse, urlunparse, parse_qsl
	from urllib import urlencode
except:
	from urllib.parse import quote, urlparse, urlunparse, urlencode, parse_qsl

# ##################################################################################################################

class SC_API(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		
		self.device_id = self.cp.get_setting('deviceid')
		self.timeout = int(self.cp.get_setting('loading_timeout'))
		if self.timeout == 0:
			self.timeout = None
		
		self.req_session = requests.Session()
		self.cache = ExpiringLRUCache(30, 1800)
		
	# ##################################################################################################################

	@staticmethod
	def create_device_id():
		import random, string
		return 'e2-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(32))

	# ##################################################################################################################

	def call_api(self, url, data=None, params=None):

		if not url.startswith("https://"):
			url = "https://stream-cinema.online/kodi" + url

		default_params = {
			'ver': '2.0',
			'uid': self.device_id,
			'lang': self.cp.dubbed_lang_list[0],
		}

		# extract params from url and add them to default_params
		u = urlparse(url)
		default_params.update(dict(parse_qsl(u.query)))
		url = urlunparse((u.scheme, u.netloc, u.path, '', '', ''))

		if params:
			default_params.update(params)

		if self.cp.get_setting('item-lang-filter') == 'dubsubs':
			default_params.update({'dub': 1, "tit": 1}) # zobraz len filmy s dabingom alebo titulkami

		elif self.cp.get_setting('item-lang-filter') == 'dub':
			default_params.update({'dub': 1}) # zobraz len dabovane filmy

		if int(self.cp.get_setting('maturity-rating')) >= 0:
			default_params.update({"m": self.cp.get_setting('maturity-rating')}) # rating pre rodicovsku kontrolu

		default_params.update({'gen': 1 if self.cp.get_setting('show-genre') else 0 }) # zobraz zaner v nazve polozky

		if not params or 'HDR' not in params:
			default_params.update({'HDR': 1 if self.cp.get_setting('show-hdr') else 0 }) #zobrazit HDR ano/nie 1/0

		if not params or 'DV' not in params:
			default_params.update({'DV': 1 if self.cp.get_setting('show-dv') else 0 }) # zobrazit dolby vidion filmy ano/nie 1/0

		if self.cp.get_setting('old-menu'):
			default_params.update({'old': 1 }) # zobrazit povodny typ menu

		headers = {
			'User-Agent': 'ArchivCZSK/%s (plugin.video.stream-cinema/%s)' % (self.cp.get_engine_version(), self.cp.get_addon_version()),
			'X-Uuid': self.device_id,
		}

		if data:
			resp = self.req_session.post(url, data=data, params=default_params, headers=headers, timeout=self.timeout)
		else:
			rurl = url + '?' + urlencode(sorted(default_params.items(), key=lambda val: val[0]))

			resp = self.cache.get(rurl)
			if resp:
				self.cp.log_debug("Request found in cache")
				return resp

			resp = self.req_session.get(url, params=default_params, headers=headers, timeout=self.timeout)
#		dump_json_request(resp)

		if resp.status_code == 200:
			resp = resp.json()

			if not data:
				ttl = 3600
				if 'system' in resp and 'TTL' in resp['system']:
					ttl = int(resp['system']['TTL'])

				self.cache.put(rurl, resp, ttl)

			return resp
		else:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % resp.status_code)

	# ##################################################################################################################
