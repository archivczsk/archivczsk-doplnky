# -*- coding: utf-8 -*-

from tools_archivczsk.generator.bouquet_xmlepg import BouquetXmlEpgGenerator, XmlEpgGenerator, EnigmaEpgGenerator
from hashlib import md5

# #################################################################################################

class VoyoXmlEpgGenerator(XmlEpgGenerator):
	def get_epg(self, channel, fromts, tots):
		for event in self.epgdata.get(channel['id_content'], []):
			yield {
				'start': event['start'],
				'end': event['end'],
				'title': event['title'],
				'desc': event['desc']
			}

	def run(self, force):
		self.epgdata = self.bxeg.cp.voyo.get_epg(days=self.bxeg.get_setting('xmlepg_days'))
		XmlEpgGenerator.run(self, force)
		del self.epgdata

# #################################################################################################

class VoyoEnigmaEpgGenerator(EnigmaEpgGenerator):
	def get_epg(self, channel, fromts, tots):
		for event in self.epgdata.get(channel['id_content'], []):
			yield {
				'start': event['start'],
				'end': event['end'],
				'title': event['title'],
				'desc': event['desc']
			}

	def run(self, force):
		self.epgdata = self.bxeg.cp.voyo.get_epg(days=self.bxeg.get_setting('xmlepg_days'))
		EnigmaEpgGenerator.run(self, force)
		del self.epgdata

# #################################################################################################

class VoyoBouquetXmlEpgGenerator(BouquetXmlEpgGenerator):
	def __init__(self, content_provider):
		self.bouquet_settings_names = ('enable_userbouquet', 'enable_xmlepg', 'enable_picons', 'player_name')
		BouquetXmlEpgGenerator.__init__(self, content_provider)
		self.xmlepg_generator = VoyoXmlEpgGenerator
		self.enigmaepg_generator = VoyoEnigmaEpgGenerator

	def logged_in(self):
		return self.cp.is_supporter() and self.cp.voyo and self.cp.voyo.check_access_token()

	def get_channels_checksum(self, channel_type):
		channels = self.cp.voyo.list_live_channels()
		ids = '|'.join( '{};{}'.format(ch['id'], ch['title']) for ch in channels )
		return md5(ids.encode('utf-8')).hexdigest()

	def get_bouquet_channels(self, channel_type=None):
		for channel in self.cp.voyo.list_live_channels():
			yield {
				'name': channel['title'],
				'adult': False,
				'picon': channel['picon'],
				'id': channel['id_num'],
				'key': channel['id'],
			}

	def get_xmlepg_channels(self):
		for channel in self.cp.voyo.list_live_channels():
			yield {
				'name': channel['title'],
				'id': channel['id_num'],
				'id_content': channel['id'],
			}

# #################################################################################################
