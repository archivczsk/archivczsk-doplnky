# -*- coding: utf-8 -*-

import os, time
import traceback
import xml.etree.ElementTree as ET

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request

COMMON_HEADERS = {
	"User-Agent": "Dalvik/1.6.0 (Linux; U; Android 4.4.4; Nexus 7 Build/KTU84P)"
}

IMAGE_WIDTH = 400
DUMP_REQUESTS=False

# #################################################################################################

class iVysilani(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self._ = content_provider._
		self.PAGE_SIZE = 100
		self.token = None
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.rid = 0

	# #################################################################################################

	def call_api(self, endpoint, data=None, auto_refresh_token=True, old=False):
		if not self.token and endpoint != 'token':
			self.token = self.call_api('token', { "user": "iDevicesMotion" }).text

		url = 'https://www.ceskatelevize.cz/services%s/ivysilani/xml/%s/' % ('-old' if old else '', endpoint)

		if data:
			post_data = data.copy()
		else:
			post_data = {}

		if self.token:
			post_data['token'] = self.token

		response = self.req_session.post(url, data=post_data)
		response.raise_for_status()

		if DUMP_REQUESTS:
			self.rid += 1
			with open('/tmp/%03d-%s.xml' % (self.rid, endpoint), 'wb') as f:
				f.write(response.content)
				comment = '<!-- %s -->\n<!-- %s -->\n' % (response.url, response.request.body)
				f.write(comment.encode('utf-8'))

		root = ET.fromstring(response.content)

		if root.tag == "errors":
			if auto_refresh_token and root[0].text == "wrong token":
				self.token = None
				return self.call_api(endpoint, data)
			else:
				raise AddonErrorException(', '.join([e.text for e in root]))

		return root

	# #################################################################################################

	def get_live_channels(self):
		ret = [
			("1", "ČT1"),
			("2", "ČT2"),
			("24", "ČT24"),
			("4", "ČT Sport"),
			("5", "ČT :D"),
			("6", "ČT art")
		]

		return ret

	# #################################################################################################

	def get_program_list(self, post_data):
		post_data['imageType'] = IMAGE_WIDTH

		ret = []
		for item in self.call_api('programmelist', post_data, old=True):
			ret.append( { child.tag: child.text for child in item } )

		return ret

	# #################################################################################################

	def get_channel_epg(self, channel_id, channel_date):
		post_data = {
			"date" : channel_date,
			"channel" : channel_id,
		}
		return self.get_program_list(post_data)

	# #################################################################################################

	def get_current_epg(self):
		post_data = {
			'imageType': IMAGE_WIDTH,
			'current': 1
		}

		ret = {}
		for item in self.call_api('programmelist', post_data, old=True):
			try:
				ret[item.tag[7:]] = { child.tag: child.text for child in item.find('live').find('programme') }
			except:
				self.cp.log_exception()

		return ret

	# #################################################################################################

	def get_context_list(self, item_id, context_name, page=1):
		post_data = {
			"ID": item_id,
			"paging[" + context_name + "][currentPage]": page,
			"paging[" + context_name + "][pageSize]": self.PAGE_SIZE,
			"imageType": IMAGE_WIDTH,
			"type[0]": context_name }

		ret = []
		for item in self.call_api('programmelist', post_data, old=True).findall(context_name + "/programme"):
			ret.append( { child.tag: child.text for child in item } )

		return ret

	# #################################################################################################

	def get_genres(self):
		ret = []
		for item in self.call_api('genrelist', old=True):
			ret.append( (item.find("link").text, item.find("title").text,) )

		return ret

	# #################################################################################################

	def get_alphabet(self):
		ret = []
		for item in self.call_api('alphabetlist', old=True):
			ret.append( (item.find("link").text, item.find("title").text,) )

		return ret

	# #################################################################################################

	def get_program_by_genre(self, genre_id):
		post_data = {
			"genre" : genre_id,
			'imageType': IMAGE_WIDTH
		}

		return self.get_program_list(post_data)

	# #################################################################################################

	def get_program_by_letter(self, letter_id):
		post_data = {
			"letter" : letter_id,
			'imageType': IMAGE_WIDTH
		}

		return self.get_program_list(post_data)

	# #################################################################################################

	def get_spotlight(self, spotlight_id):
		post_data = {
			"spotlight" : spotlight_id,
			'imageType': IMAGE_WIDTH
		}

		return self.get_program_list(post_data)

	# #################################################################################################

	def get_stream_url(self, item_id, player_type='iPad'):
		params = {
			'canPlayDrm': 'true',
			'quality': 'web',
			'streamType': 'hls' if player_type == 'iPad' else 'dash',
			'token': self.token,
			'origin': 'ivysilani',
			'usePlayability': 'true'
		}

		item_id = str(item_id)
		if item_id.startswith('CT'):
			# DRM handler can't properly process format of live manifest from ct, but it looks like it is sufficient to turn off drm here ...
			params['canPlayDrm'] = 'false'
			url = 'https://api.ceskatelevize.cz/video/v1/playlist-live/v1/stream-data/channel/CH_' + item_id[2:]
		else:
			url = 'https://api.ceskatelevize.cz/video/v1/playlist-vod/v1/stream-data/media/external/' + item_id

		response = self.req_session.get(url, params=params)

		response.raise_for_status()
		resp_json = response.json()

		if DUMP_REQUESTS:
			dump_json_request(response)

		url = None
		for s in resp_json.get('streams', []):
			url = s.get('url')

			if url:
				break

		else:
			url = resp_json.get('streamUrls', {}).get('main')

		if not url or (player_type == 'iPad' and "drmOnly=true" in url):
			# stream is only available as drm protected dash
			return self.get_stream_url(item_id, 'dash')

		return {
			'url': url,
			'type': 'hls' if player_type == 'iPad' else 'dash',
			'title': resp_json.get('showTitle') or resp_json.get('title') or ""
		}

# #################################################################################################
