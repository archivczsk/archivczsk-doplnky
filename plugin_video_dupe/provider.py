# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from .dupe import Dupe
from time import time
from base64 import b64encode

class DupeContentProvider(CommonContentProvider):

	def __init__(self):
		CommonContentProvider.__init__(self)
		self.login_optional_settings_names = ('username', 'password')
		self.dupe = Dupe(self)
		self.play_time = 0

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			# no username/password provided - continue with free account
			self.log_debug("No username or password provided - continuing without account")
			return True

		ret = self.dupe.login()

		if ret == False:
			if silent:
				return False
			self.show_error(self._("Login failed. Check your credentials. Without valid credentials you will be unable to watch any content."), noexit=True)

		return True

	# ##################################################################################################################

	def root(self):
		self.add_search_dir()
		self.add_dir(self._("Movies"), cmd=self.list_movies_root)
		self.add_dir(self._("Series"), cmd=self.list_series_root)

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		self.ensure_supporter()
		for item in self.dupe.search(keyword):
			self.add_item_uni(item)


	# ##################################################################################################################

	def list_movies_root(self):
		self.add_dir(self._("All"), cmd=self.list_movies)
		for c in self.dupe.get_movie_categories():
			self.add_dir(c['title'], cmd=self.list_movies, url=c['url'])

		self.add_dir(self._("By genre"), cmd=self.list_genres, url='filmy/')

	# ##################################################################################################################

	def list_series_root(self):
		self.add_dir(self._("All"), cmd=self.list_series)
		for c in self.dupe.get_series_categories():
			self.add_dir(c['title'], cmd=self.list_series, url=c['url'])

		self.add_dir(self._("By genre"), cmd=self.list_genres, url='serialy/')

	# ##################################################################################################################

	def list_genres(self, url):
		for g in self.dupe.get_genres():
			if url.startswith('filmy/'):
				self.add_dir(g['title'], cmd=self.list_movies, url=url+'?'+g['url'])
			else:
				self.add_dir(g['title'], cmd=self.list_series, url=url+'?'+g['url'])

	# ##################################################################################################################

	def fix_img_url(self, url):
		if url.endswith('.webp'):
			url = self.http_endpoint + '/img/' + b64encode(url.encode('utf-8')).decode('ascii')

		return url

	# ##################################################################################################################

	def add_item_uni(self, item):
		if item['type'] == 'movie':
			info_labels = {
				'plot': item['plot'],
				'year': item['year'],
				'title': item['title']
			}

			if item['year']:
				title = '{} ({})'.format(item['title'], item['year'])
			else:
				title = item['title']

			self.add_video(title, self.fix_img_url(item['img']), info_labels, cmd=self.resolve_video, video_title=item['title'], url=item['url'])
		elif item['type'] == 'tvshow':
			info_labels = {
				'plot': item['plot'],
				'year': item['year'],
				'title': item['title']
			}

			if item['year']:
				title = '{} ({})'.format(item['title'], item['year'])
			else:
				title = item['title']

			self.add_dir(title, self.fix_img_url(item['img']), info_labels, cmd=self.list_tvshow, url=item['url'])

	# ##################################################################################################################

	def list_movies(self, url='filmy/', page=1):
		for item in self.dupe.get_movies(url, page):
			if item['type'] == 'next':
				self.add_next(cmd=self.list_movies, url=url, page=page+1)
			else:
				self.add_item_uni(item)

	# ##################################################################################################################

	def list_series(self, url='serialy/', page=1):
		for item in self.dupe.get_series(url, page):
			if item['type'] == 'next':
				self.add_next(cmd=self.list_series, url=url, page=page+1)
			else:
				self.add_item_uni(item)

	# ##################################################################################################################

	def list_tvshow(self, url):
		episodes = self.dupe.get_episodes(url)
		if len(episodes) == 1:
			return self.list_season(episodes[0]['episodes'])

		for s in episodes:
			self.add_dir(s['title'], cmd=self.list_season, episodes=s['episodes'])

	# ##################################################################################################################

	def list_season(self, episodes):
		for e in episodes:
			if e['streams']:
				self.add_video(e['title'], cmd=self.resolve_video, video_title=e['title'], url=None, providers=e['streams'])
			else:
				self.add_video(_C('gray', e['title']), cmd=None)


	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['u'],
			'bandwidth': stream_key['b'],
			'headers': stream_key['h']
		}

	# ##################################################################################################################

	def resolve_hls_streams(self, url, user_agent=None):
		if user_agent:
			headers = {
				'User-Agent': user_agent
			}
		else:
			headers = None

		streams = self.get_hls_streams(url, headers=headers)

		for stream in (streams or []):
			stream['url'] = stream_key_to_hls_url(self.http_endpoint, {'u':stream['playlist_url'], 'b': stream['bandwidth'], 'h': headers})
#			self.log_debug("HLS for bandwidth %s: %s" % (stream['bandwidth'], stream['url']))

		return streams

	# ##################################################################################################################

	def resolve_video(self, video_title, url, providers=None):
		if not self.dupe.is_logged_in():
			raise AddonErrorException(self._("In order to play content you need to enter login credentials in addon's setting."))

		if self.play_time >= 300:
			self.ensure_supporter(self._("You have reached the limit and playback of another item is not available for you."))

		providers = providers or self.dupe.get_stream_providers(url)

		if not providers:
			raise AddonErrorException(self._("No supported stream provider found"))

		if len(providers) == 1:
			provider = providers[0]
		else:
			titles = []
			for p in providers:
				title = "{} [{}]".format(p['provider'], _I(p['lang']))
				if p.get('quality'):
					title += ' {}'.format(_I(p['quality']))

				titles.append( title )

			idx = self.get_list_input(titles, self._('Please select a stream'))
			if idx == -1:
				return
			provider = providers[idx]

		resolved_video = self.dupe.get_stream_info(provider['provider'], provider['url'])

		video_settings = {}
		self.log_debug("Resolved %s video URL: %s" % (resolved_video.get('type'), resolved_video.get('url')))

		if resolved_video.get('type') == 'hls':
			stream_links = self.resolve_hls_streams(resolved_video['url'], resolved_video.get('User-Agent'))
		elif resolved_video.get('type') == 'hls_multiaudio':
			# TODO: this needs to be fixed - playlist contains multiple audio playlists packed as TS and this is not supported by exteplayer3 - only first audio is played and after switching to another one there is no sound ...
			stream_links = self.resolve_hls_streams(resolved_video['url'], resolved_video.get('User-Agent'))

#			video_settings['stype'] = int(self.get_setting('player_hls_multiaudio'))
		elif resolved_video.get('type') == 'mp4':
			stream_links = [{
				'url': resolved_video['url'],
				'bandwidth': 1
			}]
		else:
			raise AddonErrorException(self._("This video stream is not available. Try to select different one."))

		subs = None
		subtitles = resolved_video.get('subtitles')
		if subtitles:
			if len(subtitles) == 1 and subtitles[0].get('forced'):
				subs = subtitles[0]['url']
			else:
				titles = []
				for p in subtitles:
					t = []
					if p.get('lang'):
						t.append('[{}]'.format(_I(p['lang'].upper())))

					if p.get('title'):
						t.append('{}'.format(p['title']))

					if t:
						titles.append(' '.join(t))
					else:
						titles.append(self._("Subtitles"))

				idx = self.get_list_input(titles, self._('Please select subtitles'))
				if idx >= 0:
					subs = subtitles[idx]['url']


		if resolved_video.get('User-Agent'):
			video_settings['User-Agent'] = resolved_video['User-Agent']

		if resolved_video.get('headers'):
			video_settings['extra-headers'] = resolved_video['headers']

		for one in stream_links:
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, one['url'], info_labels=info_labels, subs=subs, settings=video_settings)


	# ##################################################################################################################

	def stats(self, data_item, action, duration=None, position=None, **extra_params):
		if not hasattr(self, 'play_start'):
			self.play_start = 0

		if action in ('play', 'unpause'):
			self.play_start = int(time())
		elif action in ('end', 'pause'):
			if self.play_start > 0:
				self.play_time += (int(time()) - self.play_start)
				self.play_start = 0

	# ##################################################################################################################
