# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator, EnigmaEpgGenerator

# #################################################################################################

class SweetTVXmlEpgGenerator(XmlEpgGenerator):
	def get_epg(self, channel, fromts, tots):
		for event in self.epgdata.get(str(channel['id']), []):
			yield {
				'start': event['time_start'],
				'end': event['time_stop'],
				'title': event['text'],
				'desc': ' '
			}

	def run(self, force):
		self.epgdata = self.bxeg.cp.sweettv.get_epg(limit_next=1000)
		XmlEpgGenerator.run(self, force)
		del self.epgdata

# #################################################################################################

class SweetTVEnigmaEpgGenerator(EnigmaEpgGenerator):
	def get_epg(self, channel, fromts, tots):
		for event in self.epgdata.get(str(channel['id']), []):
			yield {
				'start': event['time_start'],
				'end': event['time_stop'],
				'title': event['text'],
				'desc': ' '
			}

	def run(self, force):
		self.epgdata = self.bxeg.cp.sweettv.get_epg(limit_next=1000)
		EnigmaEpgGenerator.run(self, force)
		del self.epgdata

# #################################################################################################


class SweetTVBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):

	def __init__(self, content_provider, http_endpoint, user_agent):
		BouquetXmlEpgGenerator.__init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password', 'device_id'), user_agent=user_agent)
		self.xmlepg_generator = SweetTVXmlEpgGenerator
		self.enigmaepg_generator = SweetTVEnigmaEpgGenerator

	def logged_in(self):
		return self.cp.sweettv != None

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
				'id': int(channel['id']),
				'key': str(channel['id']),
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.channels:
			yield {
				'name': channel['name'],
				'id': int(channel['id']),
				'id_content': channel['slug'],
			}

# #################################################################################################
