# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from .webshare import Webshare, WebshareLoginFail, ResolveException
from time import time

class WebshareContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, bgservice=None):
		CommonContentProvider.__init__(self, 'Webshare.cz', settings=settings, data_dir=data_dir)
		self.login_optional_settings_names = ('username', 'password')
		self.webshare = Webshare(self, bgservice)
		self.watched = self.load_cached_data('watched')

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing with free account")
			return True

		try:
			self.webshare.refresh_login_data()
			login_error = None
		except WebshareLoginFail as e:
			login_error = str(e)

		if login_error != None:
			if silent:
				return False

			self.show_error(self._("Login to premium account failed: {reason}\nContinuing with free account.").format(reason=login_error), noexit=True)

		return True

	# ##################################################################################################################

	def root(self):
		self.webshare.check_premium()

		self.add_search_dir()
		for item_id, item_data in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True):
			item = {
				'ident': item_id
			}
			item.update(item_data)
			self.add_video(item['title'] + _I(' [' + item['size'] + ']'), item['img'], cmd=self.resolve, video_title=item['title'], video_id=item['ident'], item=item)

	# ##################################################################################################################

	def search(self, keyword, search_id='', category=None, page=0):
		if category == None:
			category = self.get_setting('search_category')

		items, next_page = self.webshare.search(keyword, category=category, page=page)

		for item in items:
			self.add_video(item['title'] + _I(' [' + item['size'] + ']'), item['img'], cmd=self.resolve, video_title=item['title'], video_id=item['ident'], item=item)

		if next_page:
			self.add_next(cmd=self.search, keyword=keyword, category=category, page=page+1)

	# ##################################################################################################################

	def resolve(self, video_title, video_id, item=None):
		try:
			url = self.webshare.resolve(video_id)
		except ResolveException as e:
			raise AddonErrorException(str(e))

		self.add_play(video_title, url)
		self.add_watched_item(item)

	# ##################################################################################################################

	def add_watched_item(self, item):
		self.watched[item['ident']] = {
			'title': item['title'],
			'size': item['size'],
			'img': item['img'],
			'time': int(time()),
		}

		max_watched = int(self.get_setting('max_watched'))

		if len(self.watched) > max_watched:
			for k,_ in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True)[max_watched:]:
				del self.watched[k]

		self.save_cached_data('watched', self.watched)

	# ##################################################################################################################
