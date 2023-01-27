# -*- coding: utf-8 -*-

from tools_xbmc.tools import xbmcutil
from tools_xbmc.contentprovider.xbmcprovider import XBMContentProvider
from tools_xbmc.compat import XBMCCompatInterface

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client
from .sc_provider import StreamCinemaContentProvider

# #################################################################################################

__scriptid__ = 'plugin.video.stream-cinema'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)

# #################################################################################################

class StreamCinemaXBMContentProvider( XBMContentProvider ):
	def __init__(self, provider, settings, addon, session):
		XBMContentProvider.__init__( self, provider, settings, addon, session )
		
	# #################################################################################################
	
	def list(self, items):
		for item in items:
			params = self.params()
			if item['type'] == 'csearch':
				params.update({'csearch-list':item['url']})
				xbmcutil.add_search_folder(item['title'], params, item['img'] if 'img' in item else xbmcutil.icon('search.png'))
			else:
				# handle using parent class
				XBMContentProvider.list( self, [item] )

	# #################################################################################################

	def run(self, params):
		if 'csearch-list' in list(params.keys()):
			return self.csearch_list(params.get('csearch-list'))
		elif 'csearch' in list(params.keys()):
			return self.do_csearch(params['csearch'], params.get('action-id'))
		elif 'csearch-remove' in list(params.keys()):
			return self.csearch_remove(params['csearch-remove'], params.get('action-id'))
		elif 'csearch-edit' in list(params.keys()):
			return self.csearch_edit(params['csearch-edit'], params.get('action-id'))
		else:
			XBMContentProvider.run( self, params )
			
	# #################################################################################################
	
	def csearch_list(self, action_id):
		params = self.params()
		params.update({'csearch':'', 'action-id' : action_id })
		xbmcutil.add_search_item(xbmcutil.__lang__(30004), params, xbmcutil.icon('search.png'))
		maximum = 10
		try:
			maximum = int(self.settings['keep-searches'])
		except:
			pass
		for what in xbmcutil.get_searches(self.addon, self.provider.name + action_id, maximum):
			params = self.params()
			menuItems = self.params()
			menuItems2 = self.params()
			params['csearch'] = what
			params['action-id'] = action_id
			menuItems['csearch-remove'] = what
			menuItems['action-id'] = action_id
			menuItems2['csearch-edit'] = what
			menuItems2['action-id'] = action_id
			xbmcutil.add_dir(what, params, menuItems={u'Remove':menuItems,u'Edit':menuItems2})

	# #################################################################################################
	
	def csearch_remove(self, what, action_id):
		xbmcutil.remove_search(self.addon, self.provider.name + action_id, what)
		client.refresh_screen()

	# #################################################################################################
	
	def csearch_edit(self, what, action_id):
		try:
			replacement = client.getTextInput(self.session, xbmcutil.__lang__(30003), what)
		except ValueError:
			client.showInfo("Please install new version of archivCZSK")
		if replacement != '':
			xbmcutil.edit_search(self.addon, self.provider.name + action_id, what, replacement)
			client.refresh_screen()

	# #################################################################################################

	def do_csearch(self, what, action_id):
		if what == '':
			what = client.getTextInput(self.session, xbmcutil.__lang__(30003))
		if not what == '':
			maximum = 10
			try:
				maximum = int(self.settings['keep-searches'])
			except:
				pass
			xbmcutil.add_search(self.addon, self.provider.name + action_id, what, maximum)
			self.csearch(what, action_id)
	
	# #################################################################################################
	
	def csearch(self, keyword, action_id ):
		self.list(self.provider.csearch(keyword, action_id))

	# #################################################################################################	


def sc_run(session, params):
	settings = {'quality':__addon__.get_setting('quality')}

	device_id = __addon__.get_setting('deviceid')
	if not device_id or len(device_id) == 0:
		import random, string
		device_id = 'e2-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(32))
		__addon__.set_setting("deviceid", device_id)

	provider = StreamCinemaContentProvider(device_id=device_id, data_dir=__addon__.get_info('profile'), session=session)
	StreamCinemaXBMContentProvider(provider, settings, __addon__, session).run(params)
	
# #################################################################################################

def main(addon):
	return XBMCCompatInterface(sc_run)

# #################################################################################################
