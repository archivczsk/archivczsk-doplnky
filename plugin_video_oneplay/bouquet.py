# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator

# #################################################################################################

class OneplayTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	def logged_in(self):
		return self.cp.oneplay != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list(True)

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'adult': channel['adult'],
				'picon': channel['picon'],
				'id': int(channel['id']),
				'key': str(channel['key']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'id': int(channel['id']),
				'key': channel['key'],
				'order': channel['number']
			}

	def get_epg(self, channel, fromts, tots):
		for event in self.cp.oneplay.get_channel_epg(channel['key'], channel['order'], fromts, tots):
			yield event

# #################################################################################################
