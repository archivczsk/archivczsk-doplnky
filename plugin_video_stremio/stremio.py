# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.exception import AddonErrorException, LoginException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache
from tools_archivczsk.compat import urlencode, urljoin, quote_plus, urlencode
from collections import OrderedDict
from tools_archivczsk.cache import ExpiringLRUCache
from tools_archivczsk.string_utils import _I
import json, re

NON_BMP_RE = re.compile(u"[^\U00000000-\U0000218f\U00002c00-\U0000d7ff\U0000f900-\U0000ffff]", flags=re.UNICODE)
SPACE_NORMALIZE_RE = re.compile(r'\s+', flags=re.UNICODE)

def clean_str(s):
	return SPACE_NORMALIZE_RE.sub(u' ', NON_BMP_RE.sub(u"", s).replace('\n', ' ')).strip() if s else s

# ##################################################################################################################

class StremioAddonTitleFormatter(object):
	def __init__(self):
		if self.name == 'AIOStreams':
			self.format_stream_title = self.format_title_aiostreams
		elif self.addon_id == 'org.stremio.skcz-torrents':
			self.format_stream_title = self.format_title_czsktorrent
		elif self.addon_id == 'org.stream-cinema.online':
			self.format_stream_title = self.format_title_sc
		elif self.addon_id in ('luna.absolutecinema.addon', 'luna.search.addon'):
			self.format_stream_title = self.format_title_luna

	def format_title_aiostreams(self, stream):
		# compatible with google drive formatter
		name = stream['name'].strip()
		cached = '⚡' in name
		name = re.sub('⚡', '+', name)
		name = re.sub('(Your Media)', '', name, flags=re.IGNORECASE)
		name = re.sub(r' \(.*\)$', '', name)

		description = stream['description']
		description = re.sub('📁.*[\n]*', '', description)
		description = re.sub('☁︎.*\n', '', description)
		description = re.sub('Name: .*\n', '', description)
		description = re.sub('ℹ️.*\n', '', description)
		description = re.sub('⚡', '+', description)
		description = re.sub('⏱️ .* ', '', description)
		if cached:
			description = re.sub(r'👥 \d+', '', description)
		else:
			description = re.sub('👥 ', ' S:', description)
		description = re.sub(r' \(.* Mbps\)', '', description)

		return (re.sub(r'\s+', ' ', clean_str(name)), re.sub(r'\s+', ' ', clean_str(description)),)

	def format_title_czsktorrent(self, stream):
		name = clean_str(stream['name'])
		title = stream['title']
		if '[' in title:
			title = '[' + re.sub(r'.*?\[', '', title, 1)

		title = re.sub('👤 ', ' S:', title)
		title = re.sub('💾 ', ' Size:', title)
		title = re.sub('📝 ', ' Lang:', title)

		return (name, clean_str(title),)

	def format_title_sc(self, stream):
		description = stream['description']
		description = re.sub(r'🕒\[.*?\]', '', description)
		description = clean_str(description)

		name = stream['name']

		if 'Dub: ✅' in name:
			name = stream['name'].replace('Dub: ✅', ', '.join([_I(l) for l in ('CZ', 'SK') if ' {}'.format(l) in description]))

		return (clean_str(name), description,)

	def format_title_luna(self, stream):
		name = stream['name']
		name = '{} {}'.format(self.name, clean_str(name.replace('🔎', '').replace(' · ', ', ').replace('𝗙𝘂𝗹𝗹 𝗛𝗗', '1080p').replace('𝗛𝗗', '720p').replace('𝗦𝗗', 'SD').replace('𝟰𝗞', '4K').replace('⠀', '')))

		meta_info = (stream.get('title') or '').split('\n')

		for i, m in enumerate(meta_info):
			if i == 0:
				meta_info[i] = m.replace(' · ', ' ').split(' ')[-1].strip() + 'B'
			else:
				meta_info[i] = clean_str(m.replace('🔊', 'Audio[').replace('💬', 'Tit[').replace(' · ', ', ').replace('⠀', ' ')) + ' ]'

		return (name, ' '.join(meta_info),)

# ##################################################################################################################

STREMIO_PAGE_SIZE=100

class StremioAddon(StremioAddonTitleFormatter):
	def __init__(self, cp, url, manifest=None):
		self.cp = cp
		self._ = self.cp._
		self.req_session = self.cp.get_requests_session()

		if manifest == None:
			response = self.req_session.get(url)
			response.raise_for_status()
			manifest = response.json()

		self.addon_id = manifest['id']
		self.name = manifest['name'].strip()
		self.version = manifest['version']
		self.description = manifest['description']
		self.logo = manifest.get('logo')
		self.adult = manifest.get('behaviorHints',{}).get('adult')
		self.id_prefixes = manifest.get('idPrefixes') or []
		self.types = manifest.get('types') or []
		self.url = url
		self.cache = ExpiringLRUCache(20, 1800)
		self.parse_resources(manifest['resources'])
		self.parse_catalogs(manifest.get('catalogs'))
		self.log_debug("addon succesfully loaded")
		self.log_debug("Supported resources: %s" % json.dumps(self.resources))
		self.i = 0

		if self.addon_id == 'org.stremio.local' and self.cp.get_setting('streaming-server'):
			# update IP address of local addon
			self.url = self.url.replace('127.0.0.1', self.cp.get_setting('streaming-server'))

		super(StremioAddon, self).__init__()

	def log_debug(self, s):
		self.cp.log_debug("[{}] {}".format(self, s))

	def log_info(self, s):
		self.cp.log_info("[{}] {}".format(self, s))

	def log_error(self, s):
		self.cp.log_error("[{}] {}".format(self, s))

	def parse_resources(self, resources):
		self.resources = {}
		for r in resources:
			if isinstance(r, dict):
				self.resources[r['name']] = {
					'id_prefixes': r.get('id_prefixes') or self.id_prefixes,
					'types': r.get('types') or self.types
				}
			else:
				self.resources[r] = {
					'id_prefixes': self.id_prefixes,
					'types': self.types
				}

	def parse_catalogs(self, catalogs):
		self.catalogs = catalogs or []
		for c in self.catalogs:
			if c.get('name'):
				c['name'] = clean_str(c['name'])
			else:
				# TODO: doplnit meno podla nejakeho prekladu ID->Meno, napr. top->Najlepsie, videos->Videa, ...
				pass

		if self.catalogs and 'catalog' not in self.resources:
			# fix resources, because sometimes it doesn't contains info about catalogs

			self.resources['catalog'] = {
				'id_prefixes': self.id_prefixes,
				'types': list(self.get_catalog_types()) or self.types
			}

	def __str__(self):
		return '{} ({})'.format(self.name, self.version)

	def is_adult(self):
		return self.adult or any( (x in self.addon_id) for x in ('porn', 'xxx') )

	def supports_catalog(self, cat_type=None):
		ret = 'catalog' in self.resources and (cat_type == None or cat_type in self.resources['catalog']['types'] )
		self.log_debug("Checking if supporting catalog with type %s: %s" % (cat_type, ret))
		return ret

	def supports_meta(self, prefix=None):
		return 'meta' in self.resources and (prefix == None or not self.resources['meta']['id_prefixes'] or any(prefix.startswith(p) for p in self.resources['meta']['id_prefixes']))

	def supports_stream(self, prefix=None):
		return 'stream' in self.resources and (prefix == None or not self.resources['stream']['id_prefixes'] or any(prefix.startswith(p) for p in self.resources['stream']['id_prefixes']))

	def supports_subtitles(self, prefix=None):
		return 'subtitles' in self.resources and (prefix == None or not self.resources['subtitles']['id_prefixes'] or any(prefix.startswith(p) for p in self.resources['subtitles']['id_prefixes']))

	def get_catalogs_list(self, cat_type=None):
		return filter(lambda x: cat_type == None or x['type'] == cat_type, self.catalogs)

	def build_url(self, resource, res_type, res_id, params=None):
		url = [ '{}/{}/{}'.format(quote_plus(resource), quote_plus(res_type), quote_plus(res_id)) ]

		if params:
			url.append('/')
			url.append('&'.join('{}={}'.format(k, v) for k, v in params))

		url.append('.json')

		return ''.join(url)

	def call_api(self, resource, res_type, res_id, params=None):
		url = urljoin(self.url, self.build_url(resource, res_type, res_id, params))


		resp_json = self.cache.get(url)
		if resp_json:
			self.log_debug("Response for API %s returned from cache" % url)
			return resp_json

		self.log_debug("Calling API: %s" % url)
		try:
			resp = self.req_session.get(url)
#			dump_json_request(resp)
			resp.raise_for_status()
		except:
			self.log_error("Failed to get %s" % url)
#			self.cp.log_exception()
			return {}

		try:
			resp_json = resp.json()
		except:
			resp_json = {}

		if 'error' in resp_json:
			self.cp.log_error('Error response returned by calling %s\n%s' % (url, json.dumps(resp_json)))

			if isinstance(resp_json.get('error'), dict):
				err_str = resp_json['error'].get('message')
			else:
				err_str = None

			raise AddonErrorException('{}: {}'.format(self._("Error by calling stremio addon API"), err_str or resp_json.get('error')))

		self.cache.put(url, resp_json)
		return resp_json or {}

	def get_catalog_types(self):
		cat_types = []
		for c in self.catalogs:
			if c['type'] not in cat_types:
				cat_types.append(c['type'])
		return cat_types

	def get_catalog(self, cat_type, cat_id, params=None, page=0):
		if page > 0:
			params = params or []
			params.append( ('skip', page * STREMIO_PAGE_SIZE,) )

		resp = self.call_api('catalog', cat_type, cat_id, params)
		return resp.get('metas') or []

	def get_meta(self, cat_type, item_id):
		if not self.supports_meta(item_id):
			return None

		resp = self.call_api('meta', cat_type, item_id)
		return resp.get('meta') or {}

	def get_streams(self, cat_type, item_id, search_query=None):
		if not self.supports_stream(item_id):
			return None

		resp = self.call_api('stream', cat_type, item_id)

		# if resp.get('streams'):
		# 	while True:
		# 		self.i += 1
		# 		name = '/tmp/{}_streams_{:03d}.json'.format(self.addon_id, self.i)
		# 		if not os.path.exists(name):
		# 			with open(name, 'w') as f:
		# 				json.dump(resp['streams'], f)

		# 			break

		streams = []
		# perform some basic filtering here, to filter out unsupported streams
		for s in resp.get('streams') or []:
			if s.get('url') or s.get('infoHash'):
				streams.append(s)

		return streams

	def search(self, cat_type, item_id, keyword, params=None, page=0):
		params = params or []
		if page != None and page > 0:
			params.append( ('skip', page * STREMIO_PAGE_SIZE,) )

		params.append( ('search', keyword,) )

		resp = self.call_api('catalog', cat_type, item_id, params)
		return resp.get('metas') or []

	def get_subtitles(self, cat_type, item_id, filename=None, video_size=None, video_hash=None):
		if not self.supports_subtitles(item_id) or (not filename and not video_hash):
			return []

		params = []
		if filename:
			params.append( ('filename', filename,) )

		if video_size:
			params.append( ('videoSize', video_size,) )

		if video_hash:
			params.append( ('videoHash ', video_hash,) )

		resp = self.call_api('subtitles', cat_type, item_id, params)
		return resp.get('subtitles') or []

# ##################################################################################################################

class StremioClient(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self._ = self.cp._

		self.req_session = self.cp.get_requests_session()
		self.cache = ExpiringLRUCache(30, 1800)
		self.token = self.load_token()
		self.clear_addons()

	# ##################################################################################################################

	def clear_addons(self):
		self.addons = OrderedDict()

	# ##################################################################################################################

	def get_login_checksum(self):
		return self.cp.get_settings_checksum(('username', 'password',))

	# ##################################################################################################################

	def load_token(self):
		login_data = self.cp.load_cached_data('login')

		if login_data.get('token'):
			self.cp.log_info("Auth token loaded from local cache")
			token = login_data['token']
			checksum = login_data.get('checksum')

			if checksum and (self.get_login_checksum() != checksum):
				self.cp.log_info("Login token was created for another account - ignoring")
				token = None
		else:
			token = None
			self.cp.log_info("No cached auth token found")

		return token

	# ##################################################################################################################

	def save_token(self):
		if self.token is not None:
			self.cp.save_cached_data('login', {
				'token': self.token,
				'checksum': self.get_login_checksum()
			})
		else:
			self.cp.save_cached_data('login', {})

	# ##################################################################################################################

	@staticmethod
	def create_device_id():
		import uuid
		return str(uuid.uuid4())


	# ##################################################################################################################

	def call_api(self, endpoint, data={}):
		url = urljoin('https://api.strem.io/api/', endpoint)

		if self.token:
			data['authKey'] = self.token

		resp = self.req_session.post(url, json=data)
#		dump_json_request(resp)
		resp.raise_for_status()

		resp_json = resp.json()
		if 'error' in resp_json:
			self.cp.log_error('Error response returned by calling %s\n%s' % (url, json.dumps(resp_json)))
			raise AddonErrorException('{}: {}'.format(self._("Error by calling stremio API"), resp_json['error'].get('message')))

		return resp_json.get('result') or {}

	# ##################################################################################################################

	def logged_in(self):
		return self.token is not None

	# ##################################################################################################################

	def login(self):
		username = self.cp.get_setting('username')
		password = self.cp.get_setting('password')
		self.token = None
		self.save_token()

		if username == '' and password == '':
			self.cp.log_info("No username or password provided - continuing with default built-in account")
			self.token = ''
			self.save_token()
			return

		data = {
			'type': "Login",
			'email': username,
			'password': password,
			'facebook': False
		}

		try:
			resp = self.call_api('login', data)
		except AddonErrorException:
			raise LoginException(self._("Login failed. Probably wrong username or password provided."))

		if not resp.get('authKey'):
			self.cp.log_error("Wrong login response without authKey:\n%s" % json.dumps(resp))
			raise LoginException(self._("Login failed. Wrong response data received."))

		self.token = resp['authKey']
		self.save_token()

	# ##################################################################################################################

	def get_custom_addons(self):
		return self.cp.load_cached_data('custom_addons') or []

	# ##################################################################################################################

	def load_addons(self):
		data = {
			'type': "AddonCollectionGet",
			'update': True,
		}

		self.clear_addons()

		if self.token == '':
			resp = {}
		else:
			resp = self.call_api('addonCollectionGet', data)

		for addon_desc in (resp.get('addons') or []) + self.get_custom_addons():
			self.cp.log_debug("Loading addon: %s" % addon_desc.get('transportUrl'))
			try:
				addon = StremioAddon(self.cp, addon_desc['transportUrl'], addon_desc.get('manifest'))
			except:
				self.cp.log_error("Failed to load addon from %s" % addon_desc.get('transportUrl'))
				self.cp.log_exception()
			else:
				self.addons[addon.addon_id] = addon

		from .internal_addons import internal_addons_list

		for addon_cls in internal_addons_list:
			self.cp.log_debug("Loading internal addon: %s" % addon_cls.__name__)
			try:
				addon = addon_cls(self.cp)
			except:
				self.cp.log_error("Failed to load internal addon %s" % addon_cls.__name__)
				self.cp.log_exception()
			else:
				if addon.addon_id not in self.addons:
					self.addons[addon.addon_id] = addon
				else:
					self.cp.log_info("Ignoring internal addon %s - addon with the same ID is already loaded" % addon_cls.__name__)

	# ##################################################################################################################

	def get_addon(self, addon_id):
		return self.addons.get(addon_id)

	# ##################################################################################################################

	def get_catalog_addons(self, cat_type=None):
		return filter(lambda a: a.supports_catalog(cat_type), self.addons.values())

	# ##################################################################################################################

	def get_meta_addons(self, prefix=None):
		return filter(lambda a: a.supports_meta(prefix), self.addons.values())

	# ##################################################################################################################

	def get_stream_addons(self, prefix=None):
		return filter(lambda a: a.supports_stream(prefix), self.addons.values())

	# ##################################################################################################################

	def get_subtitle_addons(self, prefix=None):
		return filter(lambda a: a.supports_subtitles(prefix), self.addons.values())

	# ##################################################################################################################

	def get_catalogs_list(self, addon_id=None, cat_type=None):
		catalogs = []
		for a in self.get_catalog_addons(cat_type):
			if addon_id == None or a.addon_id == addon_id:
				catalogs.append( (a.addon_id, a.get_catalogs_list(cat_type)), )

		return catalogs

	# ##################################################################################################################

	def supports_paging(self, extra):
		extra = extra or []
		return any(filter(lambda e: e['name'] == 'skip', extra))

	# ##################################################################################################################

	def supports_search(self, extra, required=False):
		extra = extra or []
		if required:
			return any(filter(lambda e: e['name'] == 'search' and e.get('isRequired'), extra))
		else:
			return any(filter(lambda e: e['name'] == 'search', extra))

	# ##################################################################################################################

	def required_params(self, extra):
		extra = extra or []
		return any(filter(lambda e: e.get('isRequired'), extra))

	# ##################################################################################################################

	def build_default_params(self, extra):
		if not self.required_params(extra):
			return None

		# some params are requiered, so we will pick the first available one from each requiered
		ret = []
		for e in (extra or []):
			if e.get('isRequired') and e.get('options'):
				param_name = e.get('name')
				param_options = e['options']
				ret.append( (param_name, param_options[-1 if param_name == 'year' else 0],))

		return ret

	# ##################################################################################################################

	def supports_filtering(self, extra):
		extra = extra or []
		return any(filter(lambda e: e.get('options'), extra))

	# ##################################################################################################################

	def get_catalog_types(self, addon_id=None):
		cat_types = []
		for a in self.get_catalog_addons():
			if addon_id == None or a.addon_id == addon_id:
				for t in a.get_catalog_types():
					if t not in cat_types:
						cat_types.append(t)

		return cat_types

# ##################################################################################################################

class StremioServiceClient(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self._ = self.cp._
		self.req_session = self.cp.get_requests_session()
		self.reinit()

	def reinit(self):
		self.service_address = self.cp.get_setting('streaming-server')

	def get_address(self):
		return 'http://{}:11470/'.format(self.service_address)

	def call_api(self, endpoint, params=None):
		url = self.get_address() + endpoint

		self.cp.log_debug("Calling %s" % url)
		try:
			resp = self.req_session.get(url, params=params, timeout=30)
		except:
			self.cp.log_error("Failed to connect to stremio service on %s" % self.get_address())
			return None

		resp.raise_for_status()
		return resp.json()

	def is_available(self):
		if self.service_address and self.cp.get_setting('enable-streaming-server'):
			return self.call_api('device-info') is not None

		return False

	def probe(self, info_hash, file_idx=-1, trackers=None):
		params = {
			'mediaURL': self.get_stream(info_hash, file_idx, trackers)
		}

		# this can take quite long time
		self.cp.log_info("Probe for hash %s started" % info_hash)
		ret = self.call_api('hlsv2/probe', params) or {}
		self.cp.log_info("Probe finished - found streams:\n%s" % json.dumps(ret.get('streams')))

		return ret.get('streams')

	def get_stream(self, info_hash, file_idx=-1, trackers=None):
		# TODO: add support for HLS
		# for now return direct stream without transcoding

		if trackers:
			params = '?' + urlencode( [ ('tr', t,) for t in trackers ])
		else:
			params = ''

		return '{}{}/{}{}'.format(self.get_address(), info_hash, file_idx, params)

# ##################################################################################################################
