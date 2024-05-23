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

	def call_api(self, endpoint, data=None, auto_refresh_token=True):
		if not self.token and endpoint != 'token':
			self.token = self.call_api('token', { "user": "iDevicesMotion" }).text

		url = 'https://www.ceskatelevize.cz/services/ivysilani/xml/%s/' % endpoint

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
		for item in self.call_api('programmelist', post_data):
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
		for item in self.call_api('programmelist', post_data):
			ret[item.tag[7:]] = { child.tag: child.text for child in item.find('live').find('programme') }

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
		for item in self.call_api('programmelist', post_data).findall(context_name + "/programme"):
			ret.append( { child.tag: child.text for child in item } )

		return ret

	# #################################################################################################

	def get_genres(self):
		ret = []
		for item in self.call_api('genrelist'):
			ret.append( (item.find("link").text, item.find("title").text,) )

		return ret

	# #################################################################################################

	def get_alphabet(self):
		ret = []
		for item in self.call_api('alphabetlist'):
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
		post_data = {
			'ID': item_id,
			'quality': 'web',
			'playerType': player_type,
			'playlistType': 'json',
		}

		playlist_url = self.call_api('playlisturl', post_data).text

		response = self.req_session.get(playlist_url)

		if DUMP_REQUESTS:
			dump_json_request(response)

		response.raise_for_status()

		stream_config = response.json()

		url = None
		title = None

		for p in stream_config.get('playlist',[]):
			if p.get('type') != 'TRAILER':
				url = p.get('streamUrls',{}).get('main')
				title = p.get('title')

			if url:
				break

		if not url or (player_type == 'iPad' and "drmOnly=true" in url):
			# stream is only available as drm protected dash
			return self.get_stream_url(item_id, 'dash')

		return {
			'url': url,
			'type': 'hls' if player_type == 'iPad' else 'dash',
			'title': title
		}

# #################################################################################################
