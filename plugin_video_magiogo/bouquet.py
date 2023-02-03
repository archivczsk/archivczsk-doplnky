# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, BouquetGenerator
import time

NAME_PREFIX = "magiogo"
NAME = "MagioGO"

SERVICEREF_SID_START = 0x100
SERVICEREF_TID = 7
SERVICEREF_ONID = 7
SERVICEREF_NAMESPACE = 0xAC40000

# #################################################################################################

class MagioGOBouquetGenerator(BouquetGenerator):

	def __init__(self, bxeg, channel_type=None):
		BouquetGenerator.__init__(self, bxeg, channel_type)
		self.play_url_pattern = '/playlive/%s/index'


class MagioGOBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('region', 'username', 'password', 'deviceid', 'devicetype'), user_agent=user_agent)
		self.bouquet_generator = MagioGOBouquetGenerator

	def logged_in(self):
		return self.cp.magiogo != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			yield {
				'name': channel.name,
				'adult': channel.adult,
				'picon': channel.picon,
				'id': int(channel.id),
				'key': channel.id
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel.name,
				'id': int(channel.id),
				'key': str(channel.id),
			}

	def get_epg(self, channel, fromts, tots):
		# don't request data too quickly - magio servers have requests limit
		time.sleep(1)

		for epg_item in self.cp.magiogo.get_channels_epg([channel['id']], fromts, tots):
			if channel['id'] == epg_item.get('channel', {}).get('channelId'):
				epg = epg_item.get('programs', [])
				break
		else:
			return

		for event in epg:
			yield {
				'start': event['startTimeUTC'] / 1000,
				'end': event['endTimeUTC'] / 1000,
				'title': event['program']['title'],
				'desc': event['program'].get("description")
			}

# #################################################################################################
