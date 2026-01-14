# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, BouquetGenerator, XmlEpgGenerator, EnigmaEpgGenerator

# #################################################################################################

class OneplayTVBouquetGenerator(BouquetGenerator):
	def __init__(self, bxeg, channel_type=None):
		BouquetGenerator.__init__(self, bxeg, channel_type)
		self.play_url_pattern = '/playlive/%s/index.mpd'

# #################################################################################################

class OneplayTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	def __init__(self, content_provider):
		BouquetXmlEpgGenerator.__init__(self, content_provider)
		self.bouquet_generator = OneplayTVBouquetGenerator

	def refresh_bouquet(self):
		# this is temprorary code - remove it when all users update to this version
		if self.cp.load_cached_data('picons').get('version') != 1:
			# remove old picons, because they are wrong
			self.cp.log_info("Removing old picons")
			import os
			os.system('rm /usr/share/enigma2/picon/*_0_1_*_6DAE_1_7070000_0_0_0.png')
			self.cp.save_cached_data('picons', {'version': 1})

		return super(OneplayTVBouquetXmlEpgGenerator, self).refresh_bouquet()

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
