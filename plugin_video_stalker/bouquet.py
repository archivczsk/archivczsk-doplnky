# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet import BouquetGeneratorTemplate
import json
from binascii import crc32

# #################################################################################################

class StalkerBouquetGenerator(BouquetGeneratorTemplate):

	def __init__(self, name, ck, groups, channels_grouped, http_endpoint, player_name, user_agent):
		# configuration to make this class little bit reusable also in other addons
		self.prefix = name.replace(' ', '_').replace(':', '').lower()
		self.name = name
		self.sid_start = 0xB000
		self.tid = 10
		self.onid = 1
		self.namespace = 0xE000000 + crc32(name.encode('utf-8')) & 0xFFFFFF
		self.groups = groups
		self.channels_grouped = channels_grouped
		self.ck = ck
		BouquetGeneratorTemplate.__init__(self, http_endpoint, player_name=player_name, user_agent=user_agent)

		# #################################################################################################

	def get_channels(self):
		for g in self.groups:
			for channel in self.channels_grouped[g]:
				yield {
					'id': int(channel['id']),
					'key': json.dumps([ self.ck, channel['cmd'], channel['use_tmp_link'] ]),
					'name': channel['title'],
					'adult': False,
					'picon': None
				}

# #################################################################################################

