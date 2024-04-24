# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator
import time

# #################################################################################################

class MagioGOBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('region', 'username', 'password', 'deviceid', 'devicetype'), user_agent=user_agent)

	def logged_in(self):
		return self.cp.magiogo != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			if channel.type == 'TV':
				yield {
					'name': channel.name,
					'adult': channel.adult,
					'picon': channel.picon,
					'id': int(channel.id),
					'key': channel.id
				}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			if channel.type == 'TV':
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
