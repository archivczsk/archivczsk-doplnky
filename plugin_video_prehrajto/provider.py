# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from .prehrajto import PrehrajTo
import sys
from time import time

class PrehrajtoContentProvider(CommonContentProvider):

	def __init__(self):
		CommonContentProvider.__init__(self, 'Prehraj.to')
		self.login_optional_settings_names = ('username', 'password')
		self.req_session = self.get_requests_session()
		self.prehrajto = PrehrajTo(self)
		self.watched = self.load_cached_data('watched')

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing with free account")
			return True

		ret = self.prehrajto.login()

		if ret == False:
			if silent:
				return False
			self.show_error(self._("Login to premium account failed. Continuing with free account."), noexit=True)

		return True

	# ##################################################################################################################

	def root(self):
		self.add_search_dir()
		for item_id, item_data in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True):
			item = {
				'id': item_id
			}
			item.update(item_data)
			self.add_video(item['title'] + _I(' [' + item['size'] + ']'), item['img'], cmd=self.resolve, video_title=item['title'], video_id=item['id'], item=item)


	# ##################################################################################################################

	def search(self, keyword, search_id='', page=1):
		items, next_page = self.prehrajto.search(keyword, page=page)

		for item in items:
			self.add_video(item['title'] + _I(' [' + item['size'] + ']'), item['img'], cmd=self.resolve, video_title=item['title'], video_id=item['id'], item=item)

		if next_page:
			self.add_next(cmd=self.search, keyword=keyword, page=next_page)

	# ##################################################################################################################

	def resolve(self, video_title, video_id, item=None):
		try:
			videos, subtitles = self.prehrajto.resolve_video(video_id)
		except:
			self.log_exception()
			self.show_error(self._("Failed to find video stream. If this message appears on every video, then site was probably changed and addon needs to be updated. In that case report this info to addon author."))

		subs_url = None
		if len(subtitles) > 0 and self.get_setting('enable_subtitles'):
			ret = self.get_list_input([s['lang'] for s in subtitles], self._("Available subtitles"))
			if ret != None:
				subs_url = subtitles[ret]['url']

		for v in videos:
			info_labels = {
				'quality': v['quality']
			}
			self.add_play(video_title, v['url'], info_labels=info_labels, subs=subs_url)

		if len(videos) > 0 and item:
			self.add_watched_item(item)

	# ##################################################################################################################

	def add_watched_item(self, item):
		self.watched[item['id']] = {
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
