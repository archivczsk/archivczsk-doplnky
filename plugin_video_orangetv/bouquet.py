# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator

NAME_PREFIX = "orangetv"
NAME = "OrangeTV"
SERVICEREF_SID_START = 0x100
SERVICEREF_TID = 4
SERVICEREF_ONID = 3
SERVICEREF_NAMESPACE = 0xE020000

# #################################################################################################

class OrangeTVXmlEpgGenerator(XmlEpgGenerator):
	def run(self, force):
		XmlEpgGenerator.run(self, force)
		self.bxeg.cp.orangetv.saveEpgCache()


class OrangeTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'deviceid'), user_agent=user_agent)
		self.xmlepg_generator = OrangeTVXmlEpgGenerator

	def logged_in(self):
		return self.cp.orangetv != None

	def get_channels_checksum(self, channel_type):
		return self.cp.checksum

	def load_channel_list(self):
		self.cp.load_channel_list()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'adult': channel['adult'],
				'picon': channel['logo'],
				'id': channel['id'],
				'key': str(channel['key']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'id': channel['id'],
				'id_content': channel['key'],
			}

	def get_epg(self, channel, fromts, tots):
		epg = self.cp.orangetv.getChannelEpg(channel['id_content'], fromts, tots)
		self.cp.orangetv.fillChannelEpgCache(channel['id_content'], epg, fromts + (24 * 3600))

		for event in epg:
			yield {
				'start': event['startTimestamp'] / 1000,
				'end': event['endTimestamp'] / 1000,
				'title': event['name'],
				'desc': event.get('shortDescription')
			}

# #################################################################################################
