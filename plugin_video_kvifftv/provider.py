# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import LoginException
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from .kvifftv import KviffTv
from time import time
from functools import partial

class KviffTvContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'Kviff.tv', settings=settings, data_dir=data_dir)
		self.req_session = self.get_requests_session()
		self.kvifftv = KviffTv(self)
		self.watched = self.load_cached_data('watched')
		self.pairing_started = None

	# ##################################################################################################################

	def root(self):
		try:
			if self.kvifftv.check_login == False:
				raise LoginException("No access token")

			home_data = self.kvifftv.call_api('home')['data']
		except LoginException:
			self.add_dir(self._("Pair device with your account"), cmd=self.do_login)
			return

		self.add_search_dir()

		self.add_dir(self._("Recent"), cmd=self.list_items, items=home_data['recent'])
		self.add_dir(self._("Recommended"), cmd=self.list_items, items=home_data['recommended'])
		self.add_dir(self._("Collections"), cmd=self.list_collections)
		self.add_dir(self._("Genres"), cmd=self.list_genres, genres=home_data['genres'])
		self.add_dir(self._("Watched"), cmd=self.list_watched)

	# ##################################################################################################################

	def load_info_labels(self, item_id):
		item_data = self.kvifftv.get_item_detail(item_id)

		if 'subtitle' in item_data:
			plot = '[%s]\n%s' % (item_data['subtitle'], self.extract_text(item_data.get('description','')))
		else:
			plot = self.extract_text(item_data.get('description',''))

		return {
			'duration': int(item_data['duration'] / 1000),
			'plot': plot,
			'year': item_data['year'],
			'genre': ', '.join(item_data['genres']),
		}

 	# ##################################################################################################################

	def list_watched(self):
		for item_id, item_data in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True):
			item = {
				'id': item_id
			}
			item.update(item_data)
			self.add_video(item['title'], item['image'], info_labels=partial(self.load_info_labels, item_id=item_id), cmd=self.play_item, item=item)

	# ##################################################################################################################

	def do_login(self):
		login_finished = {
			'value': False
		}
		def check_login():
			if login_finished['value']:
				self.refresh_screen()
				return

			self.kvifftv.authorize_login_qr()
			login_finished['value'] = True
			self.show_info(self._("Pairing completed. Quit addon and return back to enjoy available content."))

		info_labels = {
			'plot': self._('Scan showed QR code and login with your credentialas. Then press "Confirm pairing".')
		}

		img = self.kvifftv.get_login_qr()
		self.add_video(self._("Confirm pairing"), img, info_labels=info_labels, cmd=check_login)

	# ##################################################################################################################

	def search(self, keyword, search_id='', page=1):
		return self.list_items(self.kvifftv.search(keyword, page=page))

#		if next_page:
#			self.add_next(cmd=self.search, keyword=keyword, page=next_page)

	# ##################################################################################################################

	def extract_text(self, text):
		return decode_html(text).replace('<p>', '').replace('</p>', '\n')

 	# ##################################################################################################################

	def add_video_item(self, item):
		self.log_debug('Creating video item from %s' % item)

		if 'subtitle' in item:
			plot = '[%s]\n%s' % (item['subtitle'], self.extract_text(item.get('description','')))
		else:
			plot = self.extract_text(item.get('description',''))

		info_labels = {
			'duration': int(item.get('duration',0) / 1000),
			'plot': plot,
			'year': item.get('year'),
			'genre': ', '.join(item.get('genres',[])),
		}

		menu = self.create_ctx_menu()
		menu.add_menu_item(self._('Recommended'), cmd=self.list_recommended, item_id=item['id'])
		self.add_video(item['title'], item['image'], info_labels=info_labels, menu=menu, cmd=self.play_item, item=item)

	# ##################################################################################################################

	def list_recommended(self, item_id):
		self.list_items(self.kvifftv.get_item_detail(item_id)['recommended'])

 	# ##################################################################################################################

	def list_items(self, items):
		if isinstance(items, type({})):
			items = items.values()

		for c in items:
			if 'items' in c:
				info_labels = {
					'plot': self.extract_text(c.get('description',''))
				}

				if c['items']:
					self.add_dir(c['name'], c.get('image'), info_labels=info_labels, cmd=self.list_items, items=c['items'])
			elif 'id' in c:
				self.add_video_item(c)


  	# ##################################################################################################################

	def list_collections(self):
		self.list_items(self.kvifftv.get_collections())

	# ##################################################################################################################

	def list_genre(self, genre_id):
		for c in self.kvifftv.get_genre(genre_id):
			self.add_video_item(c)

	# ##################################################################################################################

	def list_genres(self, genres=None):
		if not genres:
			genres = self.kvifftv.get_genres()

		for c in genres:
			self.add_dir(c['title'], cmd=self.list_genre, genre_id=c['id'])

	# ##################################################################################################################

	def play_item(self, item):
		videos, subtitles = self.kvifftv.resolve_video(item['id'])

		subs_url = None
		if len(subtitles) > 0 and self.get_setting('enable_subtitles'):
			ret = self.get_list_input([s['name'] for s in subtitles], self._("Available subtitles"))
			if ret != None:
				subs_url = subtitles[ret]['url']

		for v in videos:
			info_labels = {
				'quality': v['quality']
			}
			self.add_play(item['title'], v['url'], info_labels=info_labels, subs=subs_url)

		if len(videos) > 0:
			self.add_watched_item(item)

	# ##################################################################################################################

	def add_watched_item(self, item):
		self.watched[item['id']] = {
			'title': item['title'],
			'image': item['image'],
			'time': int(time()),
		}

		max_watched = int(self.get_setting('max_watched'))

		if len(self.watched) > max_watched:
			for k,_ in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True)[max_watched:]:
				del self.watched[k]

		self.save_cached_data('watched', self.watched)

	# ##################################################################################################################
