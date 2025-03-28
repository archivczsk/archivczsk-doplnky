# -*- coding: utf-8 -*-
#
import os, time, json, re
from datetime import datetime
import traceback
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
import uuid

############### init ################

class SweetTV:

	def __init__(self, content_provider):
		self.cp = content_provider
		self.device_id = None
		self.access_token = None
		self.refresh_token = None
		self.access_token_life = 0
		self.login_ver = 0
		self.data_dir = self.cp.data_dir
		self.log_function = self.cp.log_info
		self._ = self.cp._
		self.api_session = self.cp.get_requests_session()

		self.load_login_data()

		if self.device_id == None:
			self.device_id = self.create_device_id()

		self.common_headers = {
			"User-Agent": SweetTV.get_user_agent(),
			"Origin": "https://sweet.tv",
			"Referer": "https://sweet.tv",
			"Accept-encoding": "gzip",
			'Accept-language': 'sk',
			"Content-type": "application/json",
			"x-device": "1;22;0;2;3.7.1" # check also version string in device_info
		}

		self.common_headers_stream = {
			"User-Agent": SweetTV.get_user_agent(),
			"Origin": "https://sweet.tv",
			"Referer": "https://sweet.tv",
			"Accept-encoding": "gzip",
			'Accept-language': 'sk',
		}

		self.device_info = {
			"type": "DT_AndroidTV",
			"mac": ':'.join(self.device_id.replace('-','')[i*2:(i*2)+2] for i in range(6)),
			"application": {
				"type": "AT_SWEET_TV_Player"
			},
			"sub_type": 0,
			"firmware": {
				"versionCode": 1301,
				"versionString": "3.7.1"
			},
			"uuid": self.device_id,
			"supported_drm": {
				"widevine_modular": True
			},
			"screen_info": {
				"aspectRatio": 6,
				"width": 1920,
				"height": 1080
			},
			"advertisingId": str(uuid.uuid4())
		}

		self.channels = {}
		self.channels_next_load = 0

		self.check_login()

	# #################################################################################################
	@staticmethod
	def create_device_id():
		return str(uuid.uuid4())

	# #################################################################################################

	@staticmethod
	def get_user_agent():
		return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

	# #################################################################################################

	def load_login_data(self):
		if self.data_dir:
			try:
				# load access token
				with open(self.data_dir + '/login.json', "r") as f:
					login_data = json.load(f)
					self.login_ver = login_data.get('login_ver', 0)

					if self.login_ver == 2:
						self.access_token = login_data['access_token']
						self.refresh_token = login_data['refresh_token']
						self.device_id = login_data.get('device_id')
						self.access_token_life = login_data.get('access_token_life', 0)
						self.log_function("Login data loaded from cache")
					else:
						self.access_token = None
						self.refresh_token = None
						self.log_function("Not using cached login data - wrong checksum")
			except:
				self.access_token = None

	# #################################################################################################

	def save_login_data(self):
		if self.data_dir:
			try:
				if self.access_token:
					# save access token
					with open(self.data_dir + '/login.json', "w") as f:
						data = {
							'access_token': self.access_token,
							'refresh_token': self.refresh_token,
							'access_token_life': self.access_token_life,
							'login_ver': 2,
							'device_id': self.device_id
						}
						json.dump( data, f )
				else:
					os.remove(self.data_dir + '/login.json')
			except:
				pass

	# #################################################################################################

	def showError(self, msg):
		self.log_function("SWEET.TV API ERROR: %s" % msg )
		raise AddonErrorException(msg)

	def showLoginError(self, msg):
		self.log_function("SWEET.TV API ERROR: %s" % msg)
		raise LoginException(msg)

	# #################################################################################################

	def call_api(self, url, data=None, enable_retry=True, auth_header=True ):
		err_msg = None

		if not url.startswith('http'):
			url = 'https://api.sweet.tv/' + url

		headers = self.common_headers

		if auth_header:
			if not self.access_token:
				self.showLoginError(self._("Can't access this content. You are not logged in!"))

			headers['authorization'] = "Bearer " + self.access_token
		else:
			if 'authorization' in headers:
				del headers['authorization']

		try:
			resp = self.api_session.post( url, data=json.dumps(data, separators=(',', ':')), headers=headers )
#			dump_json_request(resp)

			if resp.status_code == 200 or (resp.status_code >= 400 and resp.status_code < 500):
				try:
					ret = resp.json()

					if auth_header and enable_retry and ret.get('status') != 'OK' and ret.get('result') != 'OK' and ret.get('code') == 16:
						if enable_retry:
							old_access_token = self.access_token
							self.load_login_data()

							if old_access_token == self.access_token:
								# we don't have newer access_token, so try to re-login
								self.refresh_login()
								enable_retry = False

							return self.call_api( url, data, enable_retry )

					return ret

				except:
					self.log_function(traceback.format_exc())
					return {}
			else:
				err_msg = self._("Unexpected return code from server") + ": %d" % resp.status_code
		except Exception as e:
			err_msg = str(e)

		if err_msg:
			self.log_function( "Sweet.tv error for URL %s: %s" % (url, traceback.format_exc()))
			self.showError(err_msg)

	# #################################################################################################

	def check_login(self):
		if self.access_token:
			if self.login_ver != 2:
				# force refresh of login data saved in old version
				self.logout()
				data = {}
			else:
				if self.access_token_life < int(time.time()):
					self.refresh_login()

				data = self.call_api('TvService/GetUserInfo.json', data={})

		if self.access_token and data.get('status') == 'OK':
			return True

		return False

	# #################################################################################################

	def get_signin_code(self):
		data = {
			"device": self.device_info,
		}
		data = self.call_api('SigninService/Start.json', data=data, enable_retry=False, auth_header=False)
		if data.get('result') != 'OK' or not 'auth_code' in data:
			self.cp.log_error("Failed to start signing process:\n%s" % str(data))
			raise LoginException(self._("Failed to start signing process"))

		return data['auth_code']

	# #################################################################################################

	def check_signin_status(self, auth_code):
		data = {
			"auth_code": auth_code
		}
		data = self.call_api('SigninService/GetStatus.json', data=data, enable_retry=False, auth_header=False)
		if data.get('result') != 'COMPLETED':
			self.cp.log_error("Signing process not yet completed:\n%s" % str(data))
			return False

		self.access_token = data.get('access_token')
		self.refresh_token = data.get('refresh_token')
		self.access_token_life = data.get('expires_in', 0) + int(time.time())
		self.login_ver = 2
		self.save_login_data()
		return True

	# #################################################################################################

	def refresh_login(self):
		if not self.refresh_token:
			self.access_token = None
			return False

		self.cp.log_debug("Refreshing access token using refresh token")
		data = {
			"device": self.device_info,
			"refresh_token": self.refresh_token,
		}

		data = self.call_api('AuthenticationService/Token.json', data=data, enable_retry=False)

		if 'access_token' not in data:
			self.access_token = None
			self.refresh_token = None
			self.access_token_life = 0
			self.save_login_data()
			self.cp.log_error("Failed to refresh access token:\n%s" % str(data))
			self.showLoginError(self._("Error by refresing login token") + ": %s" % data.get('message', ''))
			return False

		self.cp.log_debug("Access token refreshed")
		self.access_token = data.get('access_token')
		self.access_token_life = data.get('expires_in', 0) + int(time.time())
		self.save_login_data()

		return True

	# #################################################################################################

	def logout(self):
		if not self.refresh_token:
			self.access_token = None
			self.save_login_data()
			return True

		data = {
			"refresh_token": self.refresh_token,
		}

		self.call_api('SigninService/Logout.json', data=data, enable_retry=False)
		self.access_token = None
		self.refresh_token = None
		self.save_login_data()
		self.channels = {}
		self.channels_next_load = 0

		return True

	# #################################################################################################

	def get_devices(self):
		if not self.check_login():
			return []

		data = self.call_api('https://billing.sweet.tv/user/device/list', data={}, enable_retry=False )

		return data.get('list', [])

	# #################################################################################################

	def device_remove(self, did):
		if not self.check_login():
			return []

		req_data={
			'device_token_id' : did
		}

		data = self.call_api('https://billing.sweet.tv/user/device/delete', data=req_data, enable_retry=False )

		return data.get('result', False)

	# #################################################################################################

	def search(self, query ):
		req_data = {
			'needle': query,
		}

		data = self.call_api("SearchService/Search.json", data=req_data, enable_retry=False)

		result = {
			'movies': [],
			'events': []
		}

		movie_ids = []

		for item in (data.get('result') or []):
			if item['type'] == 'Movie':
				movie_ids.append(item['id'])

			elif item['type'] == 'EpgRecord':
				result['events'].append({
					'event_id': str(item['id']),
					'channel_id': str(item['sub_id']),
					'title': item['text'],
					'poster': item['image_url'],
					'time': '(%s - %s)' % (datetime.fromtimestamp(int(item["time_start"])).strftime('%d.%m. %H:%M'), datetime.fromtimestamp(int(item["time_stop"])).strftime('%H:%M'))
				})

		if len(movie_ids) > 0:
			result['movies'] = self.get_movie_info( movie_ids )

		return result

	# #################################################################################################

	def get_epg(self, time_start=None, limit_next=1, channels=None):
		if time_start == None:
			time_start = int(time.time())

		req_data = {
			'epg_current_time': time_start,
			'epg_limit_next': limit_next,
			'epg_limit_prev': 0,
			'need_epg': True,
			'need_list': True,
			'need_categories': False,
			'need_offsets': False,
			'need_hash': False,
			'need_icons': False,
			'need_big_icons': False
		}

		if channels:
			req_data['channels'] = channels

		data = self.call_api('TvService/GetChannels.json', data=req_data )

		if data.get('status') != 'OK':
			self.showError(self._("Error by loading EPG") + ": %s" % data.get('description', ''))
			return []

		epgdata = {}

		for channel in (data.get('list') or []):
			if 'epg' in channel:
				epgdata[str(channel['id'])] = channel['epg']

		return epgdata

	# #################################################################################################

	def get_channels(self):
		req_data = {
			'need_epg': False,
			'need_list': True,
			'need_categories': True,
			'need_offsets': False,
			'need_hash': True,
			'need_icons': False,
			'need_big_icons': False
		}

		data = self.call_api('TvService/GetChannels.json', data=req_data)

		if data.get('status') != 'OK':
			self.showError(self._("Error by loading channnel list") + ": %s" % data.get('description', ''))
			return []

		channels = []

		for channel in (data.get('list') or []):
			if not channel['available']:
				continue

			channels.append({
				'id': str(channel['id']),
				'name': channel['name'],
				'slug': channel['slug'],
				'adult': 1 in channel['category'] or "1" in channel['category'],
				'number': channel['number'],
				'picon': channel['icon_url'],
				'timeshift': channel['catchup_duration'] * 24 if channel.get('catchup') else 0
			})

		return sorted(channels, key=lambda ch: ch['number']), data.get('list_hash')

	# #################################################################################################

	def get_movie_configuration(self ):
		data = self.call_api('MovieService/GetConfiguration.json', data={} )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading movie configuration") + ": %s" % data.get('message', ''))
			return None

		return data

	# #################################################################################################

	def get_movie_collections(self ):
		data = self.call_api('MovieService/GetCollections.json', data={ 'type': 1 } )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading list of collections") + ": %s" % data.get('message', ''))
			return []

		result = []
		for one in (data.get('collection') or []):
			if one['type'] == 'Movie':
				result.append(one)

		return result

	# #################################################################################################

	def get_movie_collection(self, collection_id ):
		data = self.call_api('MovieService/GetCollectionMovies.json', data={ 'collection_id': int(collection_id) } )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading collections of movies") + ": %s" % data.get('message', ''))
			return None

		movie_ids = data.get('movies')

		if not movie_ids:
			return []

		return self.get_movie_info(movie_ids)

	# #################################################################################################

	def get_movie_genre(self, genre_id ):
		data = self.call_api('MovieService/GetGenreMovies.json', data={ 'genre_id': int(genre_id) } )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading movie genres") + ": %s" % data.get('message', ''))
			return None

		movie_ids = data.get('movies')

		if not movie_ids:
			return []

		return self.get_movie_info(movie_ids)

	# #################################################################################################

	def get_movie_info(self, movie_ids = None ):
		req_data = {
			'need_bundle_offers': False,
			'need_extended_info': True,
		}

		if movie_ids:
			req_data['movies'] = movie_ids

		data = self.call_api('MovieService/GetMovieInfo.json', data=req_data )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading movie informations") + ": %s" % data.get('message', ''))
			return []

		movies = []

		for movie in (data.get('movies') or []):
			movies.append({
				'id': str(movie['external_id_pairs'][0]['external_id']),
				'owner_id': str(movie['external_id_pairs'][0]['owner_id']),
				'title': movie['title'],
				'plot': movie.get('description'),
				'poster': movie['poster_url'],
				'rating': movie.get('rating_imdb'),
				'duration': movie.get('duration'),
				'year': int(movie['year']) if 'year' in movie else None,
				'available': movie['available'],
				'trailer': movie.get('trailer_url')
			})

		return movies

	# #################################################################################################

	def resolve_streams(self, url, stream_id=None, max_bitrate=None):
		try:
			req = self.api_session.get(url, headers=self.common_headers_stream)
		except:
			self.log_function("%s" % traceback.format_exc())
			self.showError(self._("Error by loading video"))
			return None

		if req.status_code != 200:
			self.showError(self._("Error by loading video") + ": http %d" % req.status_code)
			return None

		streams = []

		if max_bitrate and int(max_bitrate) > 0:
			max_bitrate = int(max_bitrate) * 1000000
		else:
			max_bitrate = 100000000

		for m in re.finditer(r'^#EXT-X-STREAM-INF:(?P<info>.+)\n(?P<chunk>.+)', req.text, re.MULTILINE):
			stream_info = {}
			for info in re.split(r''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', m.group('info')):
				key, val = info.split('=', 1)
				stream_info[key.lower()] = val

			stream_url = m.group('chunk')

			if not stream_url.startswith('http'):
				if stream_url.startswith('/'):
					stream_url = url[:url[9:].find('/') + 9] + stream_url
				else:
					stream_url = url[:url.rfind('/') + 1] + stream_url

			stream_info['url'] = stream_url
			if stream_id:
				stream_info['stream_id'] = stream_id

			if int(stream_info['bandwidth']) <= max_bitrate:
				streams.append(stream_info)

		if len(streams) == 0 and stream_id:
			self.close_stream(stream_id)

		return sorted(streams,key=lambda i: int(i['bandwidth']), reverse = True)

	# #################################################################################################

	def close_stream(self, stream_id ):
		req_data = {
			'stream_id': int(stream_id)
		}

		data = self.call_api('TvService/CloseStream.json', data=req_data )
		return data.get('result') == 'OK'

	# #################################################################################################

	def get_live_link(self, channel_key, event_id=None, max_bitrate=None):
		req_data = {
			'without_auth': True,
			'channel_id': channel_key,
			'accept_scheme': [ 'HTTP_HLS' ],
			'multistream': True
		}

		if event_id:
			req_data['epg_id'] = event_id

		data = self.call_api('TvService/OpenStream.json', data=req_data )

		if data.get('result') != 'OK':
			self.showError(self._("Error by loading stream address") + ": %s" % data.get('message', ''))
			return None

		hs = data['http_stream']
		url = 'http://%s:%d%s' % (hs['host']['address'], hs['host']['port'], hs['url'])
		return self.resolve_streams(url, data.get('stream_id'), max_bitrate)

	# #################################################################################################

	def get_movie_link(self, movie_id, owner_id = None ):
		if not owner_id:
			owner_id = self.get_movie_info([movie_id])[0]['owner_id']

		req_data = {
			'audio_track': -1,
			'movie_id': int(movie_id),
			'owner_id': int(owner_id),
			'preferred_link_type': 1,
			'subtitle': 'all'
		}

		data = self.call_api('MovieService/GetLink.json', data=req_data )

		if data.get('status') != 'OK':
			self.showError(self._("Error by loading movie stream address") + ": %s" % data['message'] if 'message' in data else data.get('status', ''))
			return None

		if data.get('link_type') not in ('HLS', 'DASH'):
			self.showError(self._("Unsupported stream type") + ": %s" % data.get('link_type', ''))
			return None

		return [ { 'url': data['url'], 'bandwidth': 1, 'name': '720p' } ]

	# #################################################################################################
