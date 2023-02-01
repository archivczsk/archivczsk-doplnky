# -*- coding: utf-8 -*-

from .bouquet import BouquetGeneratorTemplate
from .xmlepg import XmlEpgGeneratorTemplate
import time

# #################################################################################################


class BouquetGenerator(BouquetGeneratorTemplate):

	def __init__(self, bxeg, channel_type=None):
		if channel_type:
			self.prefix = bxeg.prefix + '_' + channel_type
			self.name = bxeg.name + ' ' + channel_type
		else:
			self.prefix = bxeg.prefix
			self.name = bxeg.name

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

	def run(self, force):
		XmlEpgGeneratorTemplate.run(self, force, self.bxeg.get_setting('xmlepg_dir'), self.bxeg.get_setting('xmlepg_days'))

# #################################################################################################


class BouquetXmlEpgGenerator:
	'''
	This is a base for bouquet + xml epg generator. You need to create your own class and inherit from this one. Then in your
	class implement at least mandatory functions bellow. After initialisation this class will monitor settings change and will
	automaticaly run the generation of bouquet and xml epg or delete it. It will also run periodic check and refresh when
	something changes. Check will be run every 4 hour by default and xml epg data are refreshed every 20 hours. 
	'''
	def __init__(self, content_provider, http_endpoint, login_settings_names=('username', 'password'), user_agent=None, channel_types=('tv',)):
		''' content_provider shoould be based on CommonContentProvider '''
#		self.prefix = "o2tv"
#		self.name = "O2TV"
#		self.sid_start = 0xE000
#		self.tid = 5
#		self.onid = 2
#		self.namespace = 0xE030000
		self.cp = content_provider
		self.user_agent = user_agent
		self.http_endpoint = http_endpoint

		if not hasattr(self, 'bouquet_settings_names'):
			# set settings names, that will start bouquet rebuild + are used to check, if rebuild is needed
			self.bouquet_settings_names = ('enable_userbouquet', 'enable_adult', 'enable_xmlepg', 'enable_picons', 'player_name')

		if not hasattr(self, 'xmlepg_settings_names'):
			# set settings names that are chcecked if rebuild of xmlepg is needed
			self.xmlepg_settings_names = ('xmlepg_dir', 'xmlepg_days')

		# if any of login settings names changes, then it will force bouquet and xmlepg rebuild
		self.login_settings_names = login_settings_names
		self.channel_types = channel_types
		self.bouquet_generator = BouquetGenerator
		self.xmlepg_generator = XmlEpgGenerator
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
			self.cp.bouquet_refresh_running = True
			self.cp.bgservice.run_delayed('settings_changed(refresh bouquet)', 3, __bouquet_refreshed, self.refresh_bouquet)
		else:
			self.cp.log_debug("Bouquet refresh already running")

	# #################################################################################################

	def refresh_bouquet(self):
		self.load_channel_list()

		cks = self.cp.load_cached_data('bouquet')

		if self.logged_in() and self.get_setting('enable_userbouquet'):
			settings_cks = self.cp.get_settings_checksum(self.login_settings_names + self.bouquet_settings_names, self.user_agent)

			if settings_cks != cks.get('settings'):
				self.cp.log_debug("Settings for userbouquet changed - forcing update")
				cks = {}

			need_save = False
			for channel_type in self.channel_types:
				channel_checksum = self.get_channels_checksum(channel_type)

				if cks.get(channel_type) == None or cks.get(channel_type) != channel_checksum:
					self.cp.log_info("Channel list for type %s changed - starting generator" % channel_type)
					self.bouquet_generator(self, channel_type if len(self.channel_types) > 1 else None).run()
					self.cp.log_info("Userbouquet for channel type %s generated" % channel_type)
					cks[channel_type] = channel_checksum
					need_save = True

			if need_save:
				cks['settings'] = settings_cks
				self.cp.save_cached_data('bouquet', cks)
		elif cks != {}:
			# remove userbouquet
			for channel_type in self.channel_types:
				self.cp.log_info("Removing userbouquet for channel type %s" % channel_type)
				self.bouquet_generator(self, channel_type if len(self.channel_types) > 1 else None).userbouquet_remove()

			self.cp.save_cached_data('bouquet', {})

		self.bouquet_refresh_running = False

	# #################################################################################################

	def refresh_xmlepg(self):
		# do not run epg generator if time is not synced yet
		if time.time() < 3600:
			return

		cks = self.cp.load_cached_data('xmlepg')
		settings_cks = self.cp.get_settings_checksum(self.login_settings_names + self.xmlepg_settings_names)

		if cks.get('settings') != settings_cks:
			cks['settings'] = settings_cks
			force = True
		else:
			force = False

		if self.logged_in() and self.get_setting('enable_userbouquet') and self.get_setting('enable_xmlepg'):
			self.load_channel_list()
			self.xmlepg_generator(self).run(force)

		if force:
			self.cp.save_cached_data('xmlepg', cks)

	# #################################################################################################
