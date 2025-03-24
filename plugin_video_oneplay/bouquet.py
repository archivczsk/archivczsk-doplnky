# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, BouquetGenerator, XmlEpgGenerator, EnigmaEpgGenerator

# #################################################################################################

class OneplayTVBouquetGenerator(BouquetGenerator):
	def __init__(self, bxeg, channel_type=None):
		BouquetGenerator.__init__(self, bxeg, channel_type)
		self.play_url_pattern = '/playlive/%s/index.mpd'

# #################################################################################################

class OneplayTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	def __init__(self, content_provider, http_endpoint, user_agent):
		self.bouquet_settings_names = ('enable_userbouquet', 'enable_adult', 'enable_xmlepg', 'enable_picons', 'player_name')
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password'), user_agent=user_agent)
		self.bouquet_generator = OneplayTVBouquetGenerator

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
				'id': channel['number'],
				'key': str(channel['key']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'id': channel['number'],
				'key': channel['key'],
			}

	def get_epg(self, channel, fromts, tots):
		for event in self.cp.oneplay.get_channel_epg(channel['key'], channel['id'], fromts, tots):
			yield event

# #################################################################################################
