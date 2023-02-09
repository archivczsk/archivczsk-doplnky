# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator

NAME_PREFIX = "telly"
NAME = "Telly"
SERVICEREF_SID_START = 0xA000
SERVICEREF_TID = 7
SERVICEREF_ONID = 4
SERVICEREF_NAMESPACE = 0xE040000

# #################################################################################################


class TellyXmlEpgGenerator(XmlEpgGenerator):
	def run(self, force):
		XmlEpgGenerator.run(self, force)
		self.bxeg.cp.telly.save_epg_cache()


class TellyBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		self.prefix = NAME_PREFIX
		self.name = NAME
		self.sid_start = SERVICEREF_SID_START
		self.tid = SERVICEREF_TID
		self.onid = SERVICEREF_ONID
		self.namespace = SERVICEREF_NAMESPACE
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=(), user_agent=user_agent)
		self.xmlepg_generator = TellyXmlEpgGenerator

	def logged_in(self):
		return self.cp.telly != None

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
				'id': channel.id,
				'key': str(channel.id),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel.name,
				'id': channel.id,
				'epg_id': channel.epg_id
			}

	def get_epg(self, channel, fromts, tots):
		epg = self.cp.telly.get_channels_epg([channel['epg_id']], fromts, tots)
		self.cp.telly.fill_epg_cache([channel['epg_id']], fromts + (24 * 3600), epg)

		for event in epg.get(str(channel['epg_id']), []):
			if event["name"].startswith('Vysílání od '):
				continue

			if event["name"].startswith('Broadcast from '):
				continue

			yield {
				'start': event['timestamp_start'],
				'end': event['timestamp_end'],
				'title': event['name'],
				'desc': event.get('description_broadcast')
			}

# #################################################################################################
