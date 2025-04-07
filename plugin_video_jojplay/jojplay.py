# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.string_utils import int_to_roman
from tools_archivczsk.date_utils import iso8601_to_timestamp
from time import time
from datetime import datetime
import json
import os
DUMP_API_REQUESTS = False

# ##################################################################################################################

class FirestoreJsonProcessor(object):
	def __init__(self, documents):
		self.documents = documents

	def parse_value(self, value):
		if type(value) == list:
			ret = []
			for i in value:
				ret.append(self.parse_value(i))
			return ret

		value_type = list(value.keys())[0]

		if value_type == 'geoPointValue':
			return (value['geoPointValue']['latitude'], value['geoPointValue']['longitude'],)
		elif value_type == 'arrayValue':
			if value['arrayValue'].get('values') == None:
				return []
			else:
				return self.parse_value(value['arrayValue']['values'])
		elif value_type == 'mapValue':
			if value['mapValue'].get('fields') == None:
				return {}
			else:
				return self.parse_fields(value['mapValue']['fields'])
		elif value_type == 'integerValue':
			return int(value['integerValue'])
		elif value_type == 'doubleValue':
			return float(value['doubleValue'])
		else:
			return value[value_type]

	def parse_fields(self, fields):
		res = {}

		for key, value in fields.items():
			res[key] = self.parse_value(value)

		return res

	def run(self):
		unpack = False
		if not isinstance(self.documents, list):
			self.documents = [self.documents]
			unpack = True

		ret = []
		for x in self.documents:
			if 'fields' not in x and 'document' in x:
				x = x['document']

			if 'fields' in x:
				d = self.parse_fields(x['fields'])
				d['__name'] = x.get('name')
				ret.append(d)

		return ret[0] if unpack else ret

# ##################################################################################################################

# low level JojPlay client - handles communication with backends and returns partialy processed data

class JojPlayClient(object):
	APP_KEY = "AIzaSyB02udgMkNLADkLJ_w5YNBMR2VR1WHfusI"
	TENANT_ID = "XEpbY0V54AE34rFO7dB2-i9m04"
	ORGANIZATION_ID = "dEpbY0V54AE34rFO7dB2"

	ORG_PATH = "/organizations/" + ORGANIZATION_ID
	DOCUMENTS_ROOT = 'projects/tivio-production/databases/(default)/documents'
	ORG_ROOT = DOCUMENTS_ROOT + ORG_PATH
	TAGS_ROOT = ORG_ROOT + '/tags/'

	FIRESTORE_REST_URL = 'https://firestore.googleapis.com/v1/' + DOCUMENTS_ROOT

	def __init__(self, content_provider):
		self.cp = content_provider
		self.req_session = self.cp.get_requests_session()
		self.login_data = {}
		self.purchases = []
		self.user_info = {}
		self.favourites = {'video': {}, 'tag': {}}
		self.watch_positions = {}
		self.load_login_data()

		if DUMP_API_REQUESTS:
			# patch requests to dump requests/responses send to API
			self.req_session.request_orig = self.req_session.request
			def request_and_dump(*args, **kwargs):
				response = self.req_session.request_orig(*args, **kwargs)
				dump_json_request(response)
				return response

			self.req_session.request = request_and_dump

	# ##################################################################################################################

	def load_login_data(self):
		self.login_data = self.cp.load_cached_data('login')

	# ##################################################################################################################

	def save_login_data(self):
		self.cp.save_cached_data('login', self.login_data)

	# ##################################################################################################################

	def login(self):
		self.cp.log_debug("Starting login procedure")

		username = self.cp.get_setting('username')
		password = self.cp.get_setting('password')

		if not username or not password:
			raise LoginException(self._("No username or password provided"))

		params = {
			'key': self.APP_KEY
		}
		data = {
			'tenantId': self.TENANT_ID,
			'email': username,
			'password': password,
			'returnSecureToken': True
		}
		headers = {
			'Referer': "https://play.joj.sk/"
		}

		response = self.req_session.post("https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword", params=params, json=data, headers=headers)

		try:
			resp_json = response.json()
		except:
			resp_json = {}

		try:
			response.raise_for_status()
		except:
			self.cp.log_error("Login failed: %s" % resp_json.get('message'))
			raise LoginException(self.cp._("Login failed. Probably wrong username/password combination."))


		self.login_data['id_token'] = resp_json['idToken']
		self.login_data['refresh_token'] = resp_json['refreshToken']
		self.login_data['valid_to'] = int(time()) + int(resp_json['expiresIn'])
		self.login_data['local_id'] = resp_json['localId']
		self.login_data['checksum'] = self.cp.get_settings_checksum(('username', 'password',))
		self.save_login_data()

	# ##################################################################################################################

	def refresh_id_token(self):
		self.cp.log_debug("Refreshing ID token")
		params = {
			'key': self.APP_KEY
		}

		data = {
			'grant_type': 'refresh_token',
			'refresh_token': self.login_data['refresh_token']
		}

		headers = {
			'Referer': "https://play.joj.sk/"
		}

		response = self.req_session.post("https://securetoken.googleapis.com/v1/token", params=params, json=data, headers=headers)

		try:
			resp_json = response.json()
		except:
			resp_json = {}

		try:
			response.raise_for_status()
		except:
			self.cp.log_error("Login refresh failed: %s" % str(resp_json))
			raise LoginException(self.cp._("Login refresh failed. Refresh token is not valid anymore."))

		self.login_data['id_token'] = resp_json['id_token']
		self.login_data['refresh_token'] = resp_json['refresh_token']
		self.login_data['valid_to'] = int(time()) + int(resp_json['expires_in'])
		self.save_login_data()


	# ##################################################################################################################

	def refresh_user_data(self):
		params = {
			'key': self.APP_KEY
		}
		data = {
			'idToken': self.login_data['id_token']
		}
		headers = {
			'Referer': "https://play.joj.sk/"
		}

		response = self.req_session.post("https://www.googleapis.com/identitytoolkit/v3/relyingparty/getAccountInfo", params=params, json=data, headers=headers)

		try:
			resp_json = response.json()
		except:
			resp_json = {}

		try:
			response.raise_for_status()
		except:
			self.user_info = {}
			self.cp.log_error("Login failed: %s" % resp_json.get('message'))
			raise LoginException(self.cp._("Failed to get user informations"))

		user_id = json.loads(resp_json['users'][0]['customAttributes'])['tivioUserId']

		purchases = self.load_purchases(user_id)
		self.purchases = [p['monetizationRef'].split('/')[-1] for p in purchases]
		self.dump_json('purchases', self.purchases)
		self.user_info = self.load_document('/users/' + user_id)
		self.dump_json('user-info', self.user_info)

		# refresh favourites list
		self.favourites = {'video': {}, 'tag': {}}
		for f in self.user_info.get('favorites', []):
			if f.get('profileId') == self.login_data.get('profile_id'):
				item_type = f.get('contentRef','/').split('/')[-2]
				if item_type == 'videos':
					self.favourites['video'][f['contentRef'].split('/')[-1]] = True
				elif item_type == 'tags':
					self.favourites['tag'][f['contentRef'].split('/')[-1]] = True

		# refresh watch positions
		self.watch_positions = {}
		for witem in self.user_info.get('watchHistory', []):
			if witem.get('videoRef') and witem.get('profileId') == self.login_data.get('profile_id'):
				position = witem.get('position', 0)
				if position > 0 and position < witem.get('videoDuration', 0):
					self.watch_positions[witem['videoRef'].split('/')[-1]] = position

	# ##################################################################################################################

	def refresh_login(self):
		self.cp.log_debug("Checking login data")

		if self.login_data.get('valid_to', 0) < int(time()) and self.login_data.get('refresh_token'):
			self.cp.log_debug("Login refresh is needed")
			try:
				self.refresh_id_token()
			except:
				self.cp.log_debug("Failed to refresh ID token")
				self.login_data = {}

		if self.cp.get_settings_checksum(('username', 'password',)) != self.login_data.get('checksum'):
			self.cp.log_debug("Login data changed - starting fresh login using name/password")
			self.login_data = {}
			self.login()
			self.user_info = {}

		if not self.user_info:
			self.cp.log_debug("Refreshing user info")
			self.user_info = {'x': True} # needed to break possible recursion
			self.refresh_user_data()

			profiles = [x['id'] for x in self.user_info.get('profiles',[])]

			if len(profiles) > 0:
				if self.login_data.get('profile_id') not in profiles:
					self.login_data['profile_id'] = profiles[0]
					self.save_login_data()

	# ##################################################################################################################

	def call_firestore_api(self, query=None, path='', org_root=False):
		self.refresh_login()

		headers = {
			'Authorization': 'Bearer ' + self.login_data['id_token']
		}

		data = {
			"structuredQuery": query,
		}

		if org_root:
			path = self.ORG_PATH + path

		if query:
			response = self.req_session.post(self.FIRESTORE_REST_URL + path + ":runQuery", json=data, headers=headers)
		else:
			response = self.req_session.get(self.FIRESTORE_REST_URL + path, headers=headers)

		response.raise_for_status()

		self.dump_json('last-firestore-response', response.json())
		return FirestoreJsonProcessor(response.json()).run()

	# ##################################################################################################################

	def call_tivio_api(self, endpoint, data):
		self.refresh_login()

		headers = {
			'Authorization': 'Bearer ' + self.login_data['id_token']
		}

		response = self.req_session.post('https://europe-west3-tivio-production.cloudfunctions.net/' + endpoint, json={'data':data}, headers=headers)
		try:
			response.raise_for_status()
		except:
			err_msg = None
			try:
				err_msg = response.json()['error']['details']['reason']

				if err_msg == 'MONETIZATION':
					err_msg = self.cp._("With your subscription you don't have access to this content.")
				else:
					err_msg = response.json()['error']['message']
			except:
				pass

			if err_msg:
				raise AddonErrorException(err_msg)
			else:
				raise

		return response.json().get('result')


	# ##################################################################################################################

	def load_screen(self, screen_id):
		query = {
			"from": [{"collectionId":"screens"}],
			"where":
			{
				"fieldFilter":
				{
					"field": { "fieldPath":"screenId" },
					"op":"EQUAL",
					"value": { "stringValue": screen_id }
				}
			},
			"orderBy":
			[
				{ "field": { "fieldPath":"__name__" }, "direction":"ASCENDING" }
			],
			"limit":2
		}

		return self.call_firestore_api(query, org_root=True)

	# ##################################################################################################################

	def load_tvchannel_ref(self, ref):
		query = {
			"from": [{"collectionId":"videos"}],
			"where":
			{
				"compositeFilter":
				{
					"op":"AND",
					"filters":
					[
						{
							"fieldFilter":
							{
								"field": { "fieldPath":"tvChannelRef" },
								"op":"EQUAL",
								"value":{ "referenceValue": ref	}
							}
						},
						{
							"fieldFilter":
							{
								"field": { "fieldPath":"from" },
								"op":"LESS_THAN",
								"value": { "timestampValue": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:00.000000000Z') }
							}
						}
					]
				}
			},
			"orderBy":
			[
				{"field":{"fieldPath":"from"},"direction":"DESCENDING"},
				{"field":{"fieldPath":"__name__"},"direction":"DESCENDING"}
			],
			"limit":2
		}

		return self.call_firestore_api(query)

	# ##################################################################################################################

	def get_screen_rows(self, screen_id, offset=0, limit=30):
		data = {
			"organizationId": self.ORGANIZATION_ID,
			"screenId": screen_id,
			"offset": offset,
			"limit": limit,
			"initialTilesCount":1,
			"isLockedApplicationOnStargazeHosting":False,
			"anonymousUserId":None
		}

		ret = self.call_tivio_api('getRowsInScreen3', data)
		self.dump_json('getRowsInScreen3-'+ screen_id, ret)
		return ret

	# ##################################################################################################################

	def get_row_tiles(self, row_id, offset=0, limit=30):
		data = {
			'limit': limit,
			'offset': offset,
			"organizationId": self.ORGANIZATION_ID,
			'rowId': row_id
		}

		ret = self.call_tivio_api('getTilesInRow', data)
		self.dump_json('getTilesInRow-' + row_id, ret)
		return ret

	# ##################################################################################################################

	def load_tags_by_id(self, tag_ids):
		MAX_CHUNK_SIZE=30
		# toto vie loadnut info o tagoch - tagy sa daju ziskat pomocou get_rows_in_screen() alebo pomocou load_row() [customItems]

		if not isinstance(tag_ids, list):
			tag_ids = [tag_ids]

		fdata = [ {'stringValue': x} for x in tag_ids ]

		fdata_chunks = [fdata[i:i + MAX_CHUNK_SIZE] for i in range(0, len(fdata), MAX_CHUNK_SIZE)]

		ret = []
		for fdata_chunk in fdata_chunks:
			query = {
				"from":[{"collectionId":"tags"}],
				"where":
				{
					"fieldFilter":
					{
						"field": { "fieldPath":"tagId" },
						"op":"IN",
						"value": { "arrayValue":{ "values": fdata_chunk }	}
					}
				},
				"orderBy":
				[
					{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
				]
			}

			ret.extend(self.call_firestore_api(query, org_root=True))

		self.dump_json('tags-by-id-' + str(tag_ids), ret)
		return ret

	# ##################################################################################################################

	def load_tags_by_ref(self, ref_values):
		MAX_CHUNK_SIZE=30
		# toto vie loadnut info o tagoch - tagy sa daju ziskat pomocou get_rows_in_screen() alebo pomocou load_row() [customItems]

		if not isinstance(ref_values, list):
			ref_values = [ref_values]

		fdata = [ {'referenceValue': x} for x in ref_values ]

		fdata_chunks = [fdata[i:i + MAX_CHUNK_SIZE] for i in range(0, len(fdata), MAX_CHUNK_SIZE)]

		ret = []
		for fdata_chunk in fdata_chunks:
			query = {
				"from":[{"collectionId":"tags"}],
				"where":
				{
					"fieldFilter":
					{
						"field": { "fieldPath":"__name__" },
						"op":"IN",
						"value": { "arrayValue":{ "values": fdata_chunk }	}
					}
				},
				"orderBy":
				[
					{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
				]
			}

			ret.extend(self.call_firestore_api(query, org_root=True))

#		self.dump_json('tags-by-ref', ret, True)
		return ret

	# ##################################################################################################################

	def load_videos(self, ref_values):
		MAX_CHUNK_SIZE=30
		# toto vie loadnut info o tagoch - tagy sa daju ziskat pomocou get_rows_in_screen() alebo pomocou load_row() [customItems]

		if not isinstance(ref_values, list):
			ref_values = [ref_values]

		fdata = [ {'referenceValue': x} for x in ref_values ]

		fdata_chunks = [fdata[i:i + MAX_CHUNK_SIZE] for i in range(0, len(fdata), MAX_CHUNK_SIZE)]

		ret = []
		for fdata_chunk in fdata_chunks:
			query = {
				"from":[{"collectionId":"videos"}],
				"where":
				{
					"fieldFilter":
					{
						"field": { "fieldPath":"__name__" },
						"op":"IN",
						"value": { "arrayValue":{ "values": fdata_chunk }	}
					}
				},
				"orderBy":
				[
					{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
				]
			}

			ret.extend(self.call_firestore_api(query))

#		self.dump_json('videos', ret, True)
		return ret

	# ##################################################################################################################

	def load_videos_for_tag(self, tag_id, season_nr=None):
#		season_nr = season_nr or 1
		query ={
			"from":[{"collectionId":"videos"}],
			"where":{
				"compositeFilter":{
					"op":"AND",
					"filters":
					[
						{
							"fieldFilter":
							{
								"field":{"fieldPath":"tags"},
								"op":"ARRAY_CONTAINS_ANY",
								"value":
								{
									"arrayValue":{
										"values":
										[
											{"referenceValue": self.TAGS_ROOT + tag_id}
										]
									}
								}
							}
						},
						{
							"fieldFilter":
							{
								"field":{"fieldPath":"publishedStatus"},
								"op":"EQUAL",
								"value":{"stringValue":"PUBLISHED"}
							}
						},
						{
							"fieldFilter":
							{
								"field":{"fieldPath":"transcodingStatus"},
								"op":"EQUAL",
								"value":{"stringValue":"ENCODING_DONE"}
							}
						},
						{
							"fieldFilter":
							{
								"field":{"fieldPath":"seasonNumber"},
								"op":"EQUAL",
								"value":{"integerValue": season_nr or 1}
							}
						}
					]
				}
			},
			"orderBy":[
				{"field":{"fieldPath":"episodeNumber"},"direction":"ASCENDING"},
				{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
			],
#			"limit":11
		}

		ret = self.call_firestore_api(query)
		self.dump_json('videos-for-tag', ret)
		return ret

	# ##################################################################################################################

	def load_document_content(self, document_id):
		ret = self.call_firestore_api(path="/contents/" + document_id)
		self.dump_json('document-content', ret)
		return ret

	# ##################################################################################################################

	def load_document(self, document_path, org_root=False):
		ret = self.call_firestore_api(path=document_path, org_root=org_root)
		self.dump_json('document', ret)
		return ret

	# ##################################################################################################################

	def load_purchases(self, user_id):
		query = {
			"from": [{"collectionId":"purchases"}],
			"where":
			{
				"fieldFilter":
				{
					"field":{"fieldPath":"status"},
					"op":"IN",
					"value":
					{
						"arrayValue":
						{
							"values":
							[
								{"stringValue":"PAID"},
								{"stringValue":"CANCELLING"}
							]
						}
					}
				}
			},
			"orderBy":
			[
				{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
			]
		}

		return self.call_firestore_api(query, '/users/' + user_id)

	# ##################################################################################################################

	def get_video_source_url(self, video_id, video_type='video'):
		data = {
			"id": video_id,
			"documentType": video_type,
			"capabilities":
			[
#					{"codec":"h264","protocol":"dash","encryption":"none"},
#					{"codec":"h264","protocol":"dash","encryption":"widevine"},
					{"codec":"h264","protocol":"hls","encryption":"none"} if video_type == 'tvChannel' else {"codec":"h264","protocol":"dash","encryption":"none"},
			]
		}

		return self.call_tivio_api('getSourceUrl', data)['url']

	# ##################################################################################################################

	def get_virtual_channel_epg(self, channel_ids, time_from, time_to):
		if not isinstance(channel_ids, list):
			channel_ids = [channel_ids]

		if isinstance(time_from, datetime):
			time_from = int(time_from.timestamp())

		if isinstance(time_to, datetime):
			time_to = int(time_to.timestamp())

		data = {
			"from": time_from,
			"to": time_to,
			"organizationId": self.ORGANIZATION_ID,
			"tvChannelIds": channel_ids #["GJ59DgWw15mXaCnXyxTK"]
		}

		response = self.req_session.post('https://api.tiv.io/epg', json=data)
		return response.json().get('programs',[])

	# ##################################################################################################################

	def add_watch_position(self, duration, position, video_id, tag_id, episode, season):
		data = {
			"position": position,        # position in ms - 216106,
			"videoPath": "videos/" + video_id,  # "videos/OlmxPaqpjRr4W4L5gCYb",
			"videoDuration": duration,   # duration in ms - 971440,
			"profileId": self.login_data['profile_id']
		}

		if tag_id:
			data['tagPath'] = "organizations/dEpbY0V54AE34rFO7dB2/tags/" + tag_id

		if episode:
			data.update({
				"episodeNumber": episode,
				"seasonNumber": season,
			})

		if position == 0 or duration == position:
			if video_id in self.watch_positions:
				del self.watch_positions[video_id]
		else:
			self.watch_positions[video_id] = position

		self.call_tivio_api('addWatchPosition', data)

	# ##################################################################################################################

	def update_fav(self, cmd, item_type, item_id):
		# cmd can be add or remove
		# item type can be tag or video
		# item_id is tag_id or video_id

		# TODO: dokoncit

		if item_type == 'tag':
			document_path = self.ORG_PATH + "/tags/{}".format(item_id)
		elif item_type == 'video':
			document_path = "videos/{}".format(item_id)

		data = {
			"action": cmd,
			"contentDocumentPath": document_path,   #"organizations/dEpbY0V54AE34rFO7dB2/tags/2poWErKNxttooLjlglrY",
			"profileId": self.login_data['profile_id']
		}

		if cmd == 'add':
			self.favourites[item_type][item_id] = True
		elif cmd == 'remove':
			if item_id in self.favourites[item_type]:
				del self.favourites[item_type]

		self.call_tivio_api('updateFavorites', data)

	# ##################################################################################################################

	def dump_json(self, name, data, force=False):
		if DUMP_API_REQUESTS or force:
			file_name = os.path.join(self.cp.tmp_dir, name + '.json')
			with open(file_name, 'w') as f:
				json.dump(data, f)

	# ##################################################################################################################

	def load_genres(self):
		query = {
			"from":[{"collectionId":"tags"}],
			"where":
			{
				"fieldFilter":
				{
					"field": { "fieldPath":"type" },
					"op":"EQUAL",
					"value": { "stringValue": "genre" }
				}
			},
			"orderBy":
			[
				{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
			]
		}

		return self.call_firestore_api(query, org_root=True)

	# ##################################################################################################################

	def load_genre_items(self, genre_ref):
		# not working ...
		query = {
			"from":[{"collectionId":"tags"}],
			"where":
			{
				"fieldFilter":
				{
					"field":{"fieldPath":"tags"},
					"op":"ARRAY_CONTAINS",
					"value": { "referenceValue": self.TAGS_ROOT + genre_ref }
				}
			},
			"orderBy":
			[
				{"field":{"fieldPath":"__name__"},"direction":"ASCENDING"}
			],
			"limit": 10
		}

		ret = self.call_firestore_api(query, org_root=True)
#		self.dump_json('row', ret, True)
		return ret

	# ##################################################################################################################

	def call_algolia_api(self, endpoint, data):
		params = {
			'x-algolia-api-key': 'NTdiZTE4MWI4NGYzYWU0ZGE1ZDVlNWVmZWM2MGFkYWE4NWI2ODNhMTVmMTkxMTg2YWIwMzQwNmQzYzEzMDE2MHJlc3RyaWN0SW5kaWNlcz0lNUIlMjJ2aWRlb3MlMjIlMkMlMjJ2aWRlb3NfY3JlYXRlZF9kZXNjJTIyJTJDJTIydGFncyUyMiUyQyUyMnR2Q2hhbm5lbHMlMjIlNUQ=',
			'x-algolia-application-id': 'OL4UZ1QNHS'
		}

		response = self.req_session.post('https://ol4uz1qnhs-dsn.algolia.net/{}'.format(endpoint), params=params, json=data)
		response.raise_for_status()

		return response.json()

	# ##################################################################################################################

	def search(self, keyword, search_videos=False, page=0):
		video_filter = "organizationPath:organizations/dEpbY0V54AE34rFO7dB2 AND isDraft:false AND isDuplicate:false AND hide:false AND NOT contentType:SERIES"
		series_filter = "organizationPath:organizations/dEpbY0V54AE34rFO7dB2"

		data = {
			"query": keyword,
			"filters": video_filter if search_videos else series_filter,
			"hitsPerPage": 30,
			"page": 0
		}

		resp = self.call_algolia_api('1/indexes/{}/query'.format('videos' if search_videos else 'tags'), data)

		if search_videos:
			return resp['hits']
		else:
			return [h for h in resp["hits"] if h.get('tagTypePath') == 'globalTagTypes/1X9nXUOc9XbtobIcFdyA']

	# ##################################################################################################################

	def get_related_videos(self, item_id):
		data = {
			"requests":
			[
				{
					"objectID": item_id,
					"indexName": "videos",
					"maxRecommendations":30,
					"queryParameters":
					{
						"filters":"monetizationAccessIds:false AND organizationPath:organizations/dEpbY0V54AE34rFO7dB2 AND isDraft:false AND isDuplicate:false AND hide:false AND NOT contentType:SERIES",
						"userToken":"sMf8JqvL6tWYITrcPfbj-0d2ede48-922b-45c0-878b-f7a4cfb23385"
					},
					"model": "related-products",
					"threshold":0
				}
			]
		}

		results = self.call_algolia_api('1/indexes/*/recommendations', data).get('results',[])

		if results:
			return results[0].get('hits',[])
		else:
			return []

	# ##################################################################################################################

	def get_videos_by_url(self, url_part):
		query = {
			"from":[{"collectionId":"videos"}],
			"where":
			{
				"fieldFilter":
				{
					"field": {"fieldPath":"urlName.sk"},
					"op": "ARRAY_CONTAINS",
					"value": { "stringValue": url_part}
				}
			},
			"orderBy":
			[
				{"field":{"fieldPath":"__name__"}, "direction":"ASCENDING"}
			],
			"limit":2
		}

		ret = self.call_firestore_api(query)
		self.dump_json('videos-by-url-' + url_part, ret)
		return ret

# ##################################################################################################################

# high level JojPlay client - uses JojPlayClient to request data from backend and processes it for frontend

class JojPlay(object):
	APPLICATION_ID = 'micEeZCQvGG8OTDK4cJm'

	ROW_ID_MAPPING = {
		'livetv': 'row-zTiahechfCL27mSsM4Z1W',
	}

	def __init__(self, content_provider):
		self.page_limit = 30
		self.langs = ['sk', 'cs', 'en']
		self.cp = content_provider
		self.client = JojPlayClient(content_provider)

	# ##################################################################################################################

	def login(self):
		self.client.refresh_login()

	# ##################################################################################################################

	def get_lang_label(self, item):
		if isinstance(item, dict):
			for l in self.langs:
				if item.get(l):
					return item[l]
			else:
				return ""
		else:
			return item

	# ##################################################################################################################

	def check_playability(self, item):
		ret = 1
		for m in item.get('monetizations',[]):
			if m.get('type') == 'transaction':
				ret = 0
			elif m.get('type') == 'subscription':
				ret = 0
				mon_id = m.get('id') or m.get('monetizationRef','').split('/')[-1]
				if mon_id in self.client.purchases:
					return 2

		return ret

	# ##################################################################################################################

	def get_img(self, item):
		if 'itemSpecificData' in item:
			item = item['itemSpecificData']

		item = item.get('assets')

		if not item:
			return None

		img = None
		for k in ('portrait', 'tag_portrait_cover', 'cover', 'logo', 'tag_landscape_cover', 'tag_detial_cover'):
			img = (item.get(k) or {}).get('@1',{}).get('background')
			if img:
				return img

		# nothing found - get the first available image
		for k in item.keys():
			img = item.get(k,{}).get('@1',{}).get('background')
			if img:
				return img

		return img

	# ##################################################################################################################

	def _add_video_item(self, item, series_tag_id=None):
		title = self.get_lang_label(item['name'])
		plot = self.get_lang_label(item.get('description',{}))

#		self.client.dump_json('video-item-%s' % title, item, True)

		return {
			'title': title,
			'plot': plot,
			'img': self.get_img(item),
			'type': 'video',
			'id': item['__name'].split('/')[-1],
			'playable': self.check_playability(item),
			'parent_tag_id': series_tag_id,
		}

	# ##################################################################################################################

	def _add_tag_item(self, item):
		if not item:
			return

		title = self.get_lang_label(item['name'])
		plot = self.get_lang_label(item.get('description',{}))

#		self.client.dump_json('tag-item-%s' % title, item, True)

		is_series = False
		seasons = []
		if item.get('type') == 'series':
			is_series = True

		for x in item.get('metadata',[]):
			if x.get("key") == 'availableSeasons':
				seasons = [ s['seasonNumber'] for s in x['value']]
				is_series = True

		return {
			'title': title,
			'plot': plot,
			'img': self.get_img(item),
			'type': 'series' if is_series else 'video',
			'id': item['__name'].split('/')[-1],
			'seasons': seasons
		}

	# ##################################################################################################################

	def _add_banner_item(self, item):
		title = self.get_lang_label(item['name'])
		plot = self.get_lang_label(item.get('itemSpecificData',{}).get('description',{}))

#		self.client.dump_json('banner-%s' % title, item, True)

		if item.get('itemType') == 'VIDEO':
			item_type = 'video'
#			self.client.dump_json('banner-%s' % title, item, True)
		elif item.get('itemType') == 'TAG':
			item_type = 'tag'
		else:
			self.cp.log_error("Unsupported banner item type: %s" % item.get('itemType'))
			return None

		return {
			'title': title,
			'plot': plot,
			'img': self.get_img(item),
			'type': item_type,
			'id': item['id'],
#			'tag_id': item.get('itemSpecificData',{}).get('tagId'),
			'playable': self.check_playability(item.get('itemSpecificData',{}))
		}

	# ##################################################################################################################

	def _add_row(self, item):
		title = self.get_lang_label(item['name'])

		return {
			'title': title,
			'type': 'row',
			'id': item['rowId']
		}

	# ##################################################################################################################

	def _add_banner(self, item):
		ret = []
		for tile_item in item['tiles']['items']:
			x = self._add_banner_item(tile_item)
			if x:
				ret.append(x)

		return ret

	# ##################################################################################################################

	def _add_tag(self, item):
		title = self.get_lang_label(item['name'])
		plot = self.get_lang_label(item.get('description',{}))

#		self.client.dump_json('banner-%s' % title, item, True)

		return {
			'title': title,
			'plot': plot,
			'img': self.get_img(item),
			'type': 'tag',
			'id': item['__name'].split('/')[-1],
		}

	# ##################################################################################################################

	def _add_favourites(self, item):
		title = self.get_lang_label(item['name'])

		return {
			'title': title,
			'type': 'fav',
		}

	# ##################################################################################################################

	def _add_continue_watch(self, item):
		title = self.get_lang_label(item['name'])

		return {
			'title': title,
			'type': 'watchlist',
		}

	# ##################################################################################################################

	def get_screen_items(self, screen_id, page=0, ref=False):
		if ref:
			# we have screen reference - to get rows, we need to get screen ID instead
			screen_id = self.get_document('/screens/' + screen_id, True)['screenId']

		screen_data = self.client.get_screen_rows(screen_id, page * self.page_limit, self.page_limit)

		ret = []
		for item in screen_data['items']:
			row_type = item.get('rowComponent')
			if row_type == 'ROW':
				subtype = item.get('type')
				if subtype == 'favourites':
					ret.append(self._add_favourites(item))
				elif subtype == 'continueToWatch':
					if self.cp.get_setting("sync_playback"):
						ret.append(self._add_continue_watch(item))
				elif item.get('itemComponent') != 'ROW_ITEM_HIGHLIGHTED':
					ret.append(self._add_row(item))
			elif row_type == 'BANNER':
				ret.extend(self._add_banner(item))
			else:
				self.cp.log_error("Unsupported ROW type: %s" % row_type)

		if screen_data.get('nextPageParams'):
			ret.append({'type': 'next'})

		return ret


	# ##################################################################################################################

	def get_item_details(self, item_type, item_id):
		org_root = False
		if item_type == 'tag':
			org_root = True

		ret = self.client.load_document('/{}s/{}'.format(item_type, item_id), org_root=org_root)
		self.client.dump_json('document-%s-%s' % (item_type, item_id), ret)

		return ret

	# ##################################################################################################################

	def _add_row_video(self, item):
		# playable: can be movie, episode or event
		title = self.get_lang_label(item['name'])

		item_data = item.get('itemSpecificData',{})
		if 'episodeNumber' in item_data:
			title += ' {} ({})'.format(int_to_roman(item_data.get('seasonNumber', 0)), item_data['episodeNumber'])

		return {
			'title': title,
			'img': self.get_img(item),
			'type': 'video',
			'id': item['id'],
			'playable': self.check_playability(item_data)
		}

	# ##################################################################################################################

	def _add_row_tag(self, item):
		# directory: tag is group of items (any kind of)

		title = self.get_lang_label(item['name'])

		item_data = item.get('itemSpecificData',{})
		plot = self.get_lang_label(item_data.get('description',{}))

		seasons = []

		for x in item_data.get('metadata',[]):
			if x.get("key") == 'availableSeasons':
				seasons = [ s['seasonNumber'] for s in x['value']]

		return {
			'title': title,
			'plot': plot,
			'img': self.get_img(item),
			'type': 'tag',
			'id': item['id'],
			'seasons': seasons
		}

	# ##################################################################################################################

	def _add_row_tvchannel(self, item):
		# playable: live tv channel (real or virutal)
		title = self.get_lang_label(item['name'])
		item_data = item.get('itemSpecificData',{})

		return {
			'title': title,
			'img': self.get_img(item),
			'type': 'tvChannel',
			'id': item['id'],
			'playable': self.check_playability(item_data),
			'virtual': item_data.get('type') == 'VIRTUAL'
		}

	# ##################################################################################################################

	def get_row_items(self, row_id, page=0):
		row_id = self.ROW_ID_MAPPING.get(row_id, row_id)
		row_data = self.client.get_row_tiles(row_id, page * self.page_limit, self.page_limit)

		ret = []
		for item in row_data['items']:
			item_type = item.get('itemType')

			if item_type == 'VIDEO':
				ret.append(self._add_row_video(item))
			elif item_type == 'TAG':
				ret.append(self._add_row_tag(item))
			elif item_type == 'TV_CHANNEL':
				ret.append(self._add_row_tvchannel(item))
			else:
				self.cp.log_error("Unsupported ROW item type: %s, path: %s" % (item_type, item.get('path')))

		if row_data.get('nextPageParams'):
			ret.append({'type': 'next'})

		return ret

	# ##################################################################################################################

	def get_serie_videos(self, tag_id, season=None):
		ret = []

		for item in self.client.load_videos_for_tag(tag_id, season):
			ret.append(self._add_video_item(item, tag_id))

		return ret

	# ##################################################################################################################

	def get_tag_data(self, tag_id):
#		ret = self.client.load_tags_by_id(tag_id)

		ret = self.client.load_tags_by_ref(self.client.TAGS_ROOT + tag_id)

		self.client.dump_json('tag-' + str(tag_id), ret)
		return ret

	# ##################################################################################################################

	def get_related(self, tags):
		tags = [self.client.TAGS_ROOT + t for t in tags]
		data = self.client.load_tags_by_ref(tags)
#		self.client.dump_json('tags-related', data, True)

		ret = []
		for item in data:
			x = self._add_tag(item)
			if x:
				ret.append(x)

		return ret

	# ##################################################################################################################

	def get_video_source_url(self, video_id, video_type='video'):
		return self.client.get_video_source_url(video_id, video_type)

	# ##################################################################################################################

	def get_document(self, path, org_root=False):
		ret = self.client.load_document(path, org_root)
		self.client.dump_json('document-' + path.replace('/','_'), ret)
		return ret

	# ##################################################################################################################

	def get_root_screens(self):
		is_kid = self.get_current_profile().get('kid')

		document = self.get_document('/applications/' + self.APPLICATION_ID, True)

		ret = []
		for screen in document.get('applicationScreens',[]):
			if is_kid:
				if not screen.get('showForUserProfileType',{}).get('kids'):
					continue
			else:
				if not screen.get('showForUserProfileType',{}).get('adults'):
					continue

			ret.append({
				'title': self.get_lang_label(screen['name']),
				'id': screen['screenRef'].split('/')[-1]
			})

		return ret

	# ##################################################################################################################

	def get_channel_current_epg(self, channel_id):
		cur_time = int(time())
		epg_list = self.client.load_tvchannel_ref(self.client.DOCUMENTS_ROOT +'/tvChannels/' + channel_id)

		for epg in epg_list:
			if cur_time > iso8601_to_timestamp(epg['from']) and cur_time < iso8601_to_timestamp(epg['to']):
				return {
					'from': iso8601_to_timestamp(epg['from']),
					'to': iso8601_to_timestamp(epg['to']),
					'plot': self.get_lang_label(epg.get('description','')),
					'title': self.get_lang_label(epg.get('name','')),
				}
		else:
			return {}


	# ##################################################################################################################

	def get_virtual_channel_current_epg(self, channel_id):
		cur_time = int(time())
		time_from = cur_time - (cur_time % (4*3600))
		time_to = time_from + (4*3600)

		epg_list = self.client.get_virtual_channel_epg(channel_id, time_from, time_to).get(channel_id,[])
		for epg in epg_list:
			if epg['from'] < cur_time and epg['to'] > cur_time:
				return {
					'from': epg['from'],
					'to': epg['to'],
					'plot': self.get_lang_label(epg.get('video',{}).get('description','')),
					'title': self.get_lang_label(epg.get('video',{}).get('name','')),
					'video_id': epg['videoId']
				}

		return {}

	# ##################################################################################################################

	def get_profiles(self):
		self.login()
		return [ {'name': x['name'], 'id': x['id'], 'kid': x.get('survey', {}).get('age', {}).get('kidsOnly') == True, 'active': x['id'] == self.client.login_data.get('profile_id') } for x in self.client.user_info.get('profiles', [])]

	# ##################################################################################################################

	def set_current_profile(self, profile_id):
		self.client.login_data['profile_id'] = profile_id
		self.client.save_login_data()

	# ##################################################################################################################

	def get_current_profile(self):
		cur_profile_id = self.client.login_data.get('profile_id')

		for p in self.get_profiles():
			if p['id'] == cur_profile_id:
				return p

		return {}

	# ##################################################################################################################

	def get_genres(self):
		genres = self.client.load_genres()
		self.client.dump_json('genres', genres)
		ret = []
		for item in genres:
			ret.append(self._add_tag(item))

		return ret

	# ##################################################################################################################

	def search(self, keyword, search_videos=False, page=0):
		resp = self.client.search(keyword, search_videos, page)
		self.client.dump_json('search-%s' % keyword, resp)

		ret = []
		for item in resp:
			ret.append({
				"id": item["objectID"],
				"type": "video" if search_videos else "tag",
				"title": self.get_lang_label(item.get("name")),
				"plot": self.get_lang_label(item.get("description")),
				"img": self.get_img(item)
			})

		return ret

	# ##################################################################################################################

	def get_related_videos(self, item_id):
		resp = self.client.get_related_videos(item_id)
		self.client.dump_json('related-video-%s' % item_id, resp)

		ret = []
		for item in resp:
			ret.append({
				"id": item["objectID"],
				"type": "video",
				"title": self.get_lang_label(item.get("name")),
				"plot": self.get_lang_label(item.get("description")),
				"img": self.get_img(item) or "https://assets.tivio.studio/videos/" + item["objectID"] + "/cover"
			})

		return ret

	# ##################################################################################################################

	def add_favourite(self, item_type, item_id):
		return self.client.update_fav('add', item_type, item_id)

	# ##################################################################################################################

	def remove_favourite(self, item_type, item_id):
		return self.client.update_fav('remove', item_type, item_id)

	# ##################################################################################################################

	def is_favourite(self, item_type, item_id):
		return self.client.favourites.get(item_type,{}).get(item_id, False)

	# ##################################################################################################################

	def get_favourites(self, item_type):
		# TODO: try to optimise in order to not request item detail one by one
		ret = []
		for item_id in list(self.client.favourites.get(item_type,{}).keys()):
			item = self.get_item_details(item_type, item_id)
			if item_type == 'tag':
				ret.append(self._add_tag(item))
			elif item_type == 'video':
				ret.append(self._add_video_item(item))

		return ret

	# ##################################################################################################################

	def add_watch_position(self, duration, position, video_id, tag_id, episode, season):
		if not self.cp.get_setting("sync_playback"):
			return

		return self.client.add_watch_position(duration, position, video_id, tag_id, episode, season)

	# ##################################################################################################################

	def get_watchlist(self):
		# TODO: try to optimise in order to not request item detail one by one
		self.client.refresh_user_data()

		ret = []
		for witem in self.client.user_info.get('watchHistory', []):
			if not witem.get('videoRef'):
				continue

			if witem.get('profileId') != self.client.login_data.get('profile_id'):
				continue

			position = witem.get('position',0)
			if position == 0 or position == witem.get('duration'):
				continue

			item = self.get_item_details('video', witem['videoRef'].split('/')[-1])
			series_tag_id = witem.get('tagRef','').split('/')[-1] or None
			ret.append(self._add_video_item(item, series_tag_id))

		return ret

	# ##################################################################################################################

	def get_play_pos(self, video_id):
		if not self.cp.get_setting("sync_playback"):
			return 0

		return int(self.client.watch_positions.get(video_id, 0) // 1000)

	# ##################################################################################################################

	def get_tag_id_data(self, tag_id):
		ret = self.client.load_tags_by_id(tag_id)

		self.client.dump_json('tag-id-' + str(tag_id), ret)
		return ret

	# ##################################################################################################################
