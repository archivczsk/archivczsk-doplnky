# -*- coding: utf-8 -*-

import sys, traceback
from time import time

PY2 = sys.version_info[0] == 2

try:
	from enigma import eEPGCache
except:
	eEPGCache = None

# #################################################################################################

def _log_dummy(message):
	pass


class EnigmaEpgGeneratorTemplate(object):

	def __init__(self, log_info=None, log_error=None):
		# configuration to make this class little bit reusable also in other addons
		self.data_valid_time = ((20 * 3600) - 60) # refresh data every 20 hours by default
		self.log_info = log_info if log_info else _log_dummy
		self.log_error = log_error if log_error else _log_dummy

		if eEPGCache is not None:
			self.epgcache = eEPGCache.getInstance()

			if hasattr(self.epgcache, 'importEvent'):
				self.import_event = self.__import_event1
			elif hasattr(self.epgcache, 'importEvents'):
				self.import_event = self.__import_event2
			else:
				raise Exception("No enigma2 interface for importing EPG events found")
		else:
			raise Exception("No enigma2 eEPGCache interface found")

		# Child class must define these values
#		self.sid_start = 0xE000
#		self.tid = 5
#		self.onid = 2
#		self.namespace = 0xE030000


	# #################################################################################################

	def __import_event1(self, service, events):
		self.epgcache.importEvent(service, (events,))

	# #################################################################################################

	def __import_event2(self, service, events):
		self.epgcache.importEvents([service], (events,))

	# #################################################################################################

	def run(self, cks, force=False, xmlepg_days=5):
		last_export = cks.get('last_export', 0)

		if not force and (last_export + self.data_valid_time) >= time():
			# we have exported data less then 20 hours
			return False

		# time to generate new XML EPG file
		try:
			gen_time_start = time()
			self.start_epg_export(xmlepg_days)
			self.log_info("EPG exported in %d seconds" % int(time() - gen_time_start))
		except Exception as e:
			self.log_error("Something's failed by exporting epg")
			self.log_error(traceback.format_exc())
			return False

		cks['last_export'] = int(time())
		return True

	# #################################################################################################

	def get_channels(self):
		'''
		Tou need to implement this to get list of channels included in XML-EPG file
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel'
			'id_content': 'unique string representation of channel - only letters, numbers and _ are allowed.' # optional - if not provided, it will be generated from name
		}
		'''
		return []

	# #################################################################################################

	def get_epg(self, channel, fromts, tots):
		'''
		You need to implement this to get list of epg events for channel and time range
		Each epg event is a map with these fields:
		{
			'start': timestamp of event start
			'end': timestamp of event end
			'title': 'event title as string'
			'desc': 'description of event as string'
		}
		'''
		return []

	# #################################################################################################

	def to_utc(self, ts):
		return ts

	# #################################################################################################

	def start_epg_export(self, days):
		fromts = int(time())
		tots = fromts + (int(days) * 86400)

		for channel in self.get_channels():
			self.log_info("Exporting EPG for channel: %s" % channel['name'])

			serviceref = '1:0:1:%X:%X:%X:%X:0:0:0:http%%3a//' % (self.sid_start + channel['id'], self.tid, self.onid, self.namespace)

			for event in self.get_epg(channel, fromts, tots):
				try:
					start = self.to_utc(event['start'])
					stop = self.to_utc(event['end'])
					title = str(event['title'])
					subtitle = str(event.get('subtitle') or '')
					desc = str(event.get('desc') or '')

					epg_data = (
						int(start),                                     # UTC start timestamp
						int(stop - start),                              # duration in seconds
						title.encode('utf-8') if PY2 else title,        # title
						subtitle.encode('utf-8') if PY2 else subtitle,  # subtitle
						desc.encode('utf-8') if PY2 else desc,          # long description
						0,                                              # category number
					)

					self.import_event(serviceref, epg_data)

				except:
					self.log_error(traceback.format_exc())
					pass

	# #################################################################################################
