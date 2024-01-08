# -*- coding: utf-8 -*-

import time
from datetime import datetime
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.cache import ExpiringLRUCache

try:
	from urllib import urlencode
except:
	from urllib.parse import urlencode

# ##################################################################################################################


def get_time_offset():
	now_timestamp = time.time()
	return datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(now_timestamp)


def get_timezone():
	return int(get_time_offset().total_seconds() / 60 / 60)


def datetime_to_str(date, date_format='%Y-%m-%d %H:%M:%S'):
	return date.strftime(date_format)

# ##################################################################################################################


class SCC_API(object):
	def __init__(self, content_provider):
		self.cp = content_provider

		self.token = "asb6mnn72mqruo4v81tn"
		self.device_id = self.cp.get_setting('deviceid')

		self.req_session = self.cp.get_requests_session()
		self.cache = ExpiringLRUCache(30, 1800)

	# ##################################################################################################################

	@staticmethod
	def create_device_id():
		import uuid
		return str(uuid.uuid4())

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, data=None):
		headers = {
			'User-Agent': 'ArchivCZSK/%s (plugin.video.sc2/%s)' % (self.cp.get_engine_version(), self.cp.get_addon_version()),
			'X-Uuid': self.device_id
		}

		if not endpoint.startswith('http'):
			endpoint = 'https://plugin.sc2.zone/api/' + endpoint

		if params == None:
			params = {}

		if 'access_token' not in params:
			params.update({
				'access_token': self.token,
			})

		rurl = endpoint + '?' + urlencode(sorted(params.items(), key=lambda val: val[0]))
		if data:
			rurl += '#' + urlencode(sorted(data.items(), key=lambda val: val[0]))

		response = self.cache.get(rurl)

		if response:
			self.cp.log_debug("Request found in cache")
		else:
			if data:
				response = self.req_session.post(url=endpoint, headers=headers, params=params, json=data)
			else:
				response = self.req_session.get(url=endpoint, headers=headers, params=params)

#			dump_json_request(response)
			self.cache.put(rurl, response)

		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return response.json()

	# ##################################################################################################################

	def call_filter_api(self, filter_name, params):
		if filter_name == 'service':
			return self.call_api('media/filter/v2/' + filter_name, params={'type': params.get('type'), 'from': params.get('from', 0), 'size': params.get('size') }, data=params)
		else:
			return self.call_api('media/filter/v2/' + filter_name, params=params)

	# ##################################################################################################################

	def call_filter_count_api(self, filter_name, count_name, params):
		return self.call_api('media/filter/{}/count/{}'.format(filter_name, count_name), params=params)

	# ##################################################################################################################

	def call_streams_api(self, media_id):
		return self.call_api('media/{}/streams'.format(media_id))

	# ##################################################################################################################
