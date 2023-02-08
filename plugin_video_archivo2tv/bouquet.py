# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator

NAME_PREFIX = "o2tv"
NAME = "O2TV"
SERVICEREF_SID_START = 0xE000
SERVICEREF_TID = 5
SERVICEREF_ONID = 2
SERVICEREF_NAMESPACE = 0xE030000

# #################################################################################################


class O2TVXmlEpgGenerator(XmlEpgGenerator):
	def run(self, force):
		XmlEpgGenerator.run(self, force)
		self.bxeg.cp.o2tv.save_epg_cache()


class O2TVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'deviceid', 'devicename'), user_agent=user_agent)
		self.xmlepg_generator = O2TVXmlEpgGenerator

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
				'id': channel['id'],
				'key': str(channel['key']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'id': channel['id'],
				'key': channel['key'],
			}

	def get_epg(self, channel, fromts, tots):
		epg = self.cp.o2tv.get_channel_epg(channel['key'], fromts, tots)
		self.cp.o2tv.fill_channel_epg_cache(channel['key'], epg, fromts + (24 * 3600))

		for event in epg:
			yield {
				'start': event['startTimestamp'] / 1000,
				'end': event['endTimestamp'] / 1000,
				'title': event['name'],
				'desc': event.get('shortDescription')
			}

# #################################################################################################
