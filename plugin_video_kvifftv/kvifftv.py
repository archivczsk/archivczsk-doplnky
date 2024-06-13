# -*- coding: utf-8 -*-

from tools_archivczsk.contentprovider.exception import AddonErrorException, LoginException
from tools_archivczsk.debug.http import dump_json_request

try:
	from urllib import quote
except:
	from urllib.parse import quote

# ##################################################################################################################

class KviffTv(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self.lang = 'cs'
		self.page_size = 500
		self.req_session = self.cp.get_requests_session()
		self.login_code = None
		self.login_data = self.cp.load_cached_data('login')

	# ##################################################################################################################

	def call_api(self, endpoint, params=None, method='GET'):
		if not endpoint.startswith('http'):
			endpoint = 'https://kviff.tv/api/' + endpoint

		if self.login_data.get('access_token'):
			headers = {
				'Authorization': 'Bearer ' + self.login_data['access_token']
			}
		else:
			headers = {}

		response = self.req_session.request(method=method, url=endpoint, params=params, headers=headers)
#		dump_json_request(response)

		try:
			resp = response.json()
		except:
			resp = {}

		if response.status_code == 401:
			raise LoginException(self.cp._("Wrong authorization token"))

		if response.status_code != 200:
			raise AddonErrorException(self.cp._("Unexpected return code from server") + ": %d" % response.status_code)

		return resp

	# ##################################################################################################################

	def check_login(self):
		if self.login_data.get('access_token') is None:
			return False

		# add some check to api and catch LoginException
		return True

 	# ##################################################################################################################

	def get_login_qr(self):
		params = {
			'language': self.lang
		}

		data = self.call_api('auth/devices/code', params)
		self.login_code = data['data']['accessCodeHash']

		return 'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=' + quote(data['data']['qrLink'])

 	# ##################################################################################################################

	def authorize_login_qr(self):
		if self.login_code is None:
			raise Exception('You need to run get_login_qr() first')

		params = {
			'code': self.login_code
		}

		try:
			data = self.call_api('auth/devices/code/login', params=params, method='POST')
		except LoginException:
			raise AddonErrorException(self.cp._("You have not yet authorized this device using provided QR code"))

		self.login_data['access_token']	= data['data']['token']
		self.cp.save_cached_data('login', self.login_data)
		self.login_code = None

	# ##################################################################################################################

	def get_collections(self):
		params = {
			'language': self.lang
		}

		return self.call_api('collections', params)['data']

	# ##################################################################################################################

	def get_collection(self, collection_id, page=1):
		params = {
			'p': page,
			'pageSize': self.page_size,
			'language': self.lang
		}

		data = self.call_api('collection/%s' % collection_id, params)
		return data['data'][0]['items']

	# ##################################################################################################################

	def get_genres(self):
		params = {
			'language': self.lang
		}

		data = self.call_api('home', params)
		return data['data'].get('genres',[]) or []

	# ##################################################################################################################

	def get_genre(self, genre_id, page=1):
		params = {
			'p': page,
			'pageSize': self.page_size,
			'language': self.lang
		}

		data = self.call_api('genre/%s' % genre_id, params)
		return data['data'][0]['items']

	# ##################################################################################################################

	def get_item_detail(self, item_id):
		params = {
			'language': self.lang
		}

		return self.call_api('detail/%s' % item_id, params)['data'][0]

 	# ##################################################################################################################

	def search(self, keyword, page=1):
		params = {
			'p': page,
			'pageSize': self.page_size,
			'language': self.lang,
			'keyword': keyword
		}

		data = self.call_api('search', params)
		return data['data'].get('items', [])

	# ##################################################################################################################

	def resolve_video(self, video_id):
		params = {
			'language': self.lang
		}

		videos = []
		subtitles = []

		resp = self.call_api('player/%s' % video_id, params)
		playlist = resp['data']['playlist'][0]

		for v in playlist['sources']:
			videos.append({
				'url': v['url'],
				'quality': v['size'],
			})
		videos.sort(key=lambda x: x['quality'] == 'Full HD', reverse=True)

		for trk in playlist.get('tracks',[]) or []:
			if trk['kind'] == 'captions':
				subtitles.append({
					'url': trk['src'],
					'name': trk['label'],
				})

		return videos, subtitles

	# ##################################################################################################################
