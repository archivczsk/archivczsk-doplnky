# -*- coding: utf-8 -*-

from Plugins.Extensions.archivCZSK.engine.addon import XBMCAddon
from Plugins.Extensions.archivCZSK.engine import client
from .tools.xbmcutil import __lang__

addons_blacklist = {
	# adddon id, list of blacklisted versions (or empty if all)
	'plugin.video.joj.sk': []
}

class XBMCCompatInterface(object):
	def __init__(self, xbmc_run_cbk, addon):
		self.xbmc_run_cbk = xbmc_run_cbk
		self.addon = XBMCAddon(addon)
		self.blacklisted = False

		if addon.id in addons_blacklist:
			versions = addons_blacklist[addon.id]

			if len(versions) > 0:
				if addon.version in versions:
					self.blacklisted = True
			else:
				self.blacklisted = True

	# #################################################################################################

	def check_blacklist(self):
		if self.blacklisted:
			client.showError(__lang__(300))

	# #################################################################################################

	def run(self, session, params):
		self.check_blacklist()
		self.xbmc_run_cbk(session, params, self.addon)

	# #################################################################################################

	def run_silent(self, session, params):
		self.check_blacklist()
		params['silent_mode'] = True
		self.xbmc_run_cbk(session, params, self.addon)

	# #################################################################################################

	def stats(self, session, item, action, **extra_params):
		params = {
			'cp': 'czsklib',
			'stats': action,
			'item': item
		}

		if extra_params.get('duration') != None:
			params['duration'] = extra_params['duration']

		if extra_params.get('position') != None:
			params['lastPlayPos'] = extra_params['position']

		self.run(session, params)

	# #################################################################################################

	def trakt(self, session, item, action, result):
		params = {
			'cp': 'czsklib',
			'trakt': action,
			'item': item,
			'result': 'success' if result['success'] else 'fail',
			'msg': result['msg'],
		}
		self.run(session, params)

	# #################################################################################################

	def search(self, session, keyword, search_id=None):
		params = {
			'search': keyword,
			'search-no-history':True
		}

		if search_id:
			params['cp'] = search_id

		self.run(session, params)

# #################################################################################################
