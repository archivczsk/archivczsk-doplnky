# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, BouquetGenerator

NAME_PREFIX = "o2tv_2"
NAME = "O2 TV 2.0"
SERVICEREF_SID_START = 0x10
SERVICEREF_TID = 0
SERVICEREF_ONID = 0
SERVICEREF_NAMESPACE = 0xE990000

# #################################################################################################

class O2TVBouquetGenerator(BouquetGenerator):

	def __init__(self, bxeg, channel_type=None):
		BouquetGenerator.__init__(self, bxeg, channel_type)
		self.play_url_pattern = '/playlive/%s/index.mpd'


class O2TVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'deviceid'), user_agent=user_agent)
		self.bouquet_generator = O2TVBouquetGenerator

	def logged_in(self):
		return self.cp.o2tv != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

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
		for event in self.cp.o2tv.get_channel_epg(channel['key'], fromts, tots):
			yield event

# #################################################################################################
