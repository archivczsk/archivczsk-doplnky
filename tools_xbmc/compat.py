# -*- coding: utf-8 -*-

class XBMCCompatInterface():

	def __init__(self, xbmc_run_cbk):
		self.xbmc_run_cbk = xbmc_run_cbk

	# #################################################################################################

	def run(self, session, params):
		self.xbmc_run_cbk(session, params)

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
