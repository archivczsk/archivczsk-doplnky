# -*- coding: utf-8 -*-

from .bouquet import BouquetGeneratorTemplate
from .xmlepg import XmlEpgGeneratorTemplate
from .enigmaepg import EnigmaEpgGeneratorTemplate
import time
from binascii import crc32

SERVICEREF_SID_START = 0x0001
SERVICEREF_ONID = 0x1
SERVICEREF_NAMESPACE = 0x7070000

# #################################################################################################

class BouquetGenerator(BouquetGeneratorTemplate):

	def __init__(self, bxeg, channel_type=None):
		if channel_type:
			self.prefix = bxeg.prefix + '_' + channel_type
			self.name = bxeg.name + ' ' + channel_type
		else:
			self.prefix = bxeg.prefix
			self.name = bxeg.name

		profile_info = bxeg.get_profile_info()
		if profile_info != None:
			self.prefix = self.prefix + '_' + profile_info[0]
			self.name = self.name + ' - ' + profile_info[1]

		self.bxeg = bxeg
		self.sid_start = bxeg.sid_start
		self.tid = bxeg.tid
		self.onid = bxeg.onid
		self.namespace = bxeg.namespace
		self.channel_type = channel_type
		BouquetGeneratorTemplate.__init__(self, bxeg.http_endpoint, bxeg.get_setting('enable_adult'), bxeg.get_setting('enable_xmlepg'), bxeg.get_setting('enable_picons'), bxeg.get_setting('player_name'), bxeg.user_agent)

	# #################################################################################################

	def get_channels(self):
		return self.bxeg.get_bouquet_channels(self.channel_type)

# #################################################################################################

class XmlEpgGenerator(XmlEpgGeneratorTemplate):
	def __init__(self, bxeg):
		self.bxeg = bxeg
		self.prefix = bxeg.prefix
		self.name = bxeg.name

		profile_info = bxeg.get_profile_info()
		if profile_info != None:
			self.prefix = self.prefix + '_' + profile_info[0]
			self.name = self.name + ' - ' + profile_info[1]

		self.sid_start = bxeg.sid_start
		self.tid = bxeg.tid
		self.onid = bxeg.onid
		self.namespace = bxeg.namespace
		XmlEpgGeneratorTemplate.__init__(self, log_info=bxeg.cp.log_info, log_error=bxeg.cp.log_error)

	# #################################################################################################

	def get_channels(self):
		return self.bxeg.get_xmlepg_channels()

	# #################################################################################################

	def get_epg(self, channel, fromts, tots):
		return self.bxeg.get_epg(channel, fromts, tots)

	# #################################################################################################

	def cleanup(self, uninstall=False):
		XmlEpgGeneratorTemplate.cleanup(self, self.bxeg.get_setting('xmlepg_dir'), uninstall)

	# #################################################################################################

	def run(self, force):
		XmlEpgGeneratorTemplate.run(self, force, self.bxeg.get_setting('xmlepg_dir'), self.bxeg.get_setting('xmlepg_days'))

# #################################################################################################

class EnigmaEpgGenerator(EnigmaEpgGeneratorTemplate):
	def __init__(self, bxeg):
		self.bxeg = bxeg

		self.sid_start = bxeg.sid_start
		self.tid = bxeg.tid
		self.onid = bxeg.onid
		self.namespace = bxeg.namespace
		EnigmaEpgGeneratorTemplate.__init__(self, log_info=bxeg.cp.log_info, log_error=bxeg.cp.log_error)

	# #################################################################################################

	def get_channels(self):
		return self.bxeg.get_xmlepg_channels()

	# #################################################################################################

	def get_epg(self, channel, fromts, tots):
		return self.bxeg.get_epg(channel, fromts, tots)

	# #################################################################################################

	def run(self, force):
		cks = self.bxeg.cp.load_cached_data('enigmaepg')
		if EnigmaEpgGeneratorTemplate.run(self, cks, force, self.bxeg.get_setting('xmlepg_days')):
			self.bxeg.cp.save_cached_data('enigmaepg', cks)

# #################################################################################################

class BouquetXmlEpgGenerator(object):
	'''
	This is a base for bouquet + xml epg generator. You need to create your own class and inherit from this one. Then in your
	class implement at least mandatory functions bellow. After initialisation this class will monitor settings change and will
	automaticaly run the generation of bouquet and xml epg or delete it. It will also run periodic check and refresh when
	something changes. Check will be run every 4 hour by default and xml epg data are refreshed every 20 hours.
	'''
	def __init__(self, content_provider, http_endpoint=None, login_settings_names=('username', 'password'), user_agent=None, channel_types=('tv',)):
		''' content_provider shoould be based on CommonContentProvider '''
		self.prefix = content_provider.get_addon_id(short=True)
		self.name = content_provider.name
		self.cp = content_provider
		self.user_agent = user_agent
		self.http_endpoint = http_endpoint or self.cp.http_endpoint

		profile_info = self.get_profile_info()

		self.namespace = SERVICEREF_NAMESPACE
		self.sid_start = SERVICEREF_SID_START

		if profile_info is not None:
			self.tid = 0x1 + crc32((self.prefix + profile_info[0]).encode('utf-8')) % 0xFFFE
			self.cp.log_debug("Bouquet generator initialised for profile %s; TID: 0x%x" % (profile_info[1], self.tid))
		else:
			self.tid = 0x1 + crc32(self.prefix.encode('utf-8')) % 0xFFFE
			self.cp.log_debug("Bouquet generator initialised; TID: 0x%x" % self.tid)

		self.onid = SERVICEREF_ONID

		if not hasattr(self, 'bouquet_settings_names'):
			# set settings names, that will start bouquet rebuild + are used to check, if rebuild is needed
			self.bouquet_settings_names = ('enable_userbouquet', 'enable_adult', 'enable_xmlepg', 'enable_picons', 'player_name')

		if not hasattr(self, 'xmlepg_settings_names'):
			# set settings names that are chcecked if rebuild of xmlepg is needed
			self.xmlepg_settings_names = ('xmlepg_dir', 'xmlepg_days')

		# if any of login settings names changes, then it will force bouquet and xmlepg rebuild
		self.login_settings_names = login_settings_names
		self.channel_types = channel_types       # list of enabled channel types
		self.channel_types_all = channel_types   # list of all channel types
		self.bouquet_generator = BouquetGenerator
		self.xmlepg_generator = XmlEpgGenerator
		self.enigmaepg_generator = EnigmaEpgGenerator
		self.bouquet_refresh_running = False
		self.cp.add_setting_change_notifier(self.bouquet_settings_names, self.bouquet_settings_changed)
		self.cp.add_initialised_callback(self.initialised)

	# #################################################################################################
	# These functions needs to be implemented
	# #################################################################################################

	def logged_in(self):
		''' implement this to return True/False if login was successful '''
		return True

	def get_channels_checksum(self, channel_type):
		raise Exception('No function to get channels checksum is impemented')

	def load_channel_list(self):
		''' implement this refresh channels list before bouquet or xmlepg generator will be run '''
		return

	def get_bouquet_channels(self, channel_type=None):
		'''
		Tou need to implement this to get list of channels included to bouquet for specified channel_type (if used)
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel the same as in function get_xmlepg_channels()'
			'key': key used to get stream address - it will be encoded and forwarded to http handler
			'adult': indicates if channel is for adults
			'picon': url with picon for this channel
			'is_separator': if true, then this item indicates separator in bouquets
		}
		'''

		raise Exception('No function to get channels for bouquet implemented')

	def get_xmlepg_channels(self):
		'''
		Tou need to implement this to get list of channels included in XML-EPG file
		Each channel is a map with these requiered fields:
		{
			'name': "channel name",
			'id': 'unique numeric id of channel - the same as in get_bouquet_channels'
			'id_content': 'unique string representation of channel - only letters, numbers and _ are allowed.' # optional - if not provided, it will be generated from name
		}
		'''

		raise Exception('No function to get channels for xmlepg implemented')

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

		raise Exception('No function to get channels for bouquet implemented')

	def get_setting(self, name):
		# optional: overwrite this function if don't use "standard" setting names
		return self.cp.get_setting(name)

	def get_profile_info(self):
		# optional: overwrite this function if don't use "standard" profiles
		return self.cp.get_profile_info()

	# #################################################################################################

	def initialised(self):
		self.cp.bgservice.run_in_loop('loop(refresh bouquet)', 4 * 3600, self.refresh_bouquet)
		self.cp.bgservice.run_in_loop('loop_changed(refresh xmlepg)', 4 * 3600, self.refresh_xmlepg)

	# #################################################################################################

	def bouquet_settings_changed(self, name, value):

		def __xmlepg_refreshed(success, result):
			self.cp.log_debug("XML-EPG refreshed")
			self.bouquet_refresh_running = False

		def __bouquet_refreshed(success, result):
			self.cp.log_debug("Bouquet refreshed")
			self.cp.bgservice.run_delayed('settings_changed(refresh xmlepg)', 3, __xmlepg_refreshed, self.refresh_xmlepg)

		if not self.bouquet_refresh_running:
			self.cp.log_debug("Starting bouquet+xmlepg refresh")
			self.bouquet_refresh_running = True
			self.cp.bgservice.run_delayed('settings_changed(refresh bouquet)', 3, __bouquet_refreshed, self.refresh_bouquet)
		else:
			self.cp.log_debug("Bouquet refresh already running")

	# #################################################################################################

	def refresh_bouquet(self):
		self.bouquet_refresh_running = True
		cks = self.cp.load_cached_data('bouquet')

		if self.logged_in() and self.get_setting('enable_userbouquet'):
			self.load_channel_list()
			settings_cks = self.cp.get_settings_checksum(self.login_settings_names + self.bouquet_settings_names, self.user_agent)

			if settings_cks != cks.get('settings'):
				self.cp.log_debug("Settings for userbouquet changed - forcing update")
				cks = {}

			if cks.get('version') != 2:
				self.cp.log_debug("Version of exported userbouquet doesn't match - forcing update")
				cks = {}

			need_save = False
			for channel_type in self.channel_types_all:
				channel_checksum = self.get_channels_checksum(channel_type)

				if channel_type in self.channel_types:
					if cks.get(channel_type) == None or cks.get(channel_type) != channel_checksum:
						self.cp.log_info("Channel list for type %s changed - starting generator" % channel_type)
						self.bouquet_generator(self, channel_type if len(self.channel_types_all) > 1 else None).run()
						self.cp.log_info("Userbouquet for channel type %s generated" % channel_type)
						cks[channel_type] = channel_checksum
						need_save = True
				else:
					if self.bouquet_generator(self, channel_type if len(self.channel_types_all) > 1 else None).userbouquet_remove():
						self.cp.log_info("Userbouquet for channel type %s disabled - removing" % channel_type)

			if need_save:
				cks['settings'] = settings_cks
				cks['version'] = 2
				self.cp.save_cached_data('bouquet', cks)

		elif cks != {}:
			# remove userbouquet
			for channel_type in self.channel_types_all:
				self.cp.log_info("Removing userbouquet for channel type %s" % channel_type)
				self.bouquet_generator(self, channel_type if len(self.channel_types_all) > 1 else None).userbouquet_remove()

			self.cp.save_cached_data('bouquet', {})

		self.bouquet_refresh_running = False

	# #################################################################################################

	def refresh_xmlepg_start(self, force=False):
		def __xmlepg_refreshed(success, result):
			self.cp.log_debug("XML-EPG refreshed")

		self.cp.log_debug("Starting xmlepg refresh")
		self.cp.bgservice.run_delayed('settings_changed(refresh xmlepg)', 3, __xmlepg_refreshed, self.refresh_xmlepg, force=force)

	# #################################################################################################

	def refresh_xmlepg(self, force = False):
		# do not run epg generator if time is not synced yet
		if time.time() < 3600:
			return

		cks = self.cp.load_cached_data('xmlepg')
		settings_cks = self.cp.get_settings_checksum(self.login_settings_names + self.xmlepg_settings_names)

		if cks.get('version') != 2:
			self.cp.log_debug("Version of exported XML-EPG doesn't match - forcing update")
			cks = {}

		if cks.get('settings') != settings_cks:
			cks['settings'] = settings_cks
			cks['version'] = 2
			force = True

		if self.logged_in() and self.get_setting('enable_userbouquet') and self.get_setting('enable_xmlepg'):
			self.load_channel_list()
			try:
				# try to directly export data to enigma's EPG cache
				self.enigmaepg_generator(self).run(force)

				try:
					if cks.get('xml_generated', True):
						self.xmlepg_generator(self).cleanup(True)
						cks['xml_generated'] = False
						force = True # needed to save cached data at the end of this function
				except:
					self.cp.log_exception()

			except Exception as e:
				self.cp.log_exception()
				self.cp.log_error("Failed to export EPG to enigma's cache: %s. Falling back to XML-EPG export ..." % str(e))
				self.xmlepg_generator(self).run(force)
				cks['xml_generated'] = True

		if force:
			self.cp.save_cached_data('xmlepg', cks)

	# #################################################################################################

