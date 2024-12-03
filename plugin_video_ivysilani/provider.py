# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.string_utils import _I, _C, _B, clean_html
import sys, os

from datetime import datetime, timedelta
import time

from .ivysilani import iVysilani

DATE_MIN = "2015-01-01"

class iVysilaniContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, resources_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'iVysilani', settings=settings, data_dir=data_dir)
		self.resources_dir = resources_dir
		self.http_endpoint = http_endpoint
		self.ivysilani = iVysilani(self)

	# ##################################################################################################################

	def root(self):
		self.add_dir(self._("Live broadcasting"), cmd=self.list_live)
		self.add_dir(self._("By date"), cmd=self.list_dates)
		self.add_dir(self._("By letter"), cmd=self.list_letters)
		self.add_dir(self._("By genre"), cmd=self.list_genres)
		self.add_dir(self._("Tips"), cmd=self.list_spotlight, sid='tipsMain')
		self.add_dir(self._("Today's most watched"), cmd=self.list_spotlight, sid='topDay')
		self.add_dir(self._("Week's most watched"), cmd=self.list_spotlight, sid='topWeek')
		self.add_dir(self._("Don't miss"), cmd=self.list_spotlight, sid='tipsNote')
		self.add_dir(self._("From our archive"), cmd=self.list_spotlight, sid='tipsArchive')
		self.add_dir(self._("Others watching now"), cmd=self.list_spotlight, sid='watching')

	# ##################################################################################################################

	def list_live(self):
		channel_name_map = { k: v for k, v in self.ivysilani.get_live_channels() }

		for channel_id, epg_data in self.ivysilani.get_current_epg().items():
			channel_title = channel_name_map.get(channel_id, '')

#			this doesn't work anymore - it's not possible to know if channel is broadcasting or not ...
#			if epg_data.get('isOnline') != '1':
#				self.log_debug("Channel %s is not online now - skipping" % channel_title)
#				continue

			if epg_data.get('title'):
				channel_title += ' %s' % _I(epg_data['title'])

			if epg_data.get('elapsedPercentage'):
				channel_title += ' [%s%%]' % epg_data['elapsedPercentage']

			info_labels = {
				'plot' : '[%s]\n%s' % (epg_data.get('time') or '', clean_html(epg_data.get('synopsis') or ''),)
			}

			img = epg_data.get('imageURL')
			if img and img.startswith('//'):
				img = 'http:' + img

			self.add_video(channel_title, img, info_labels=info_labels, cmd=self.play_item, item_id='CT' + channel_id + '|' + epg_data['ID'])

	# ##################################################################################################################

	def list_dates(self):
		day_names = [
			self._("Monday"), self._("Tuesday"), self._("Wednesday"), self._("Thursday"), self._("Friday"), self._("Saturday"), self._("Sunday")
		]

		dt = datetime.now()
		min_date = datetime.fromtimestamp(time.mktime(time.strptime(DATE_MIN, "%Y-%m-%d")))

		while dt > min_date:
			pretty_date = day_names[dt.weekday()] + " - " + dt.strftime("%d.%m.%Y")
			formated_date = dt.strftime("%Y-%m-%d")

			self.add_dir(pretty_date, cmd=self.list_date, d=formated_date)
			dt = dt - timedelta(days=1)

	# ##################################################################################################################

	def list_date(self, d):
		for channel_id, channel_name in self.ivysilani.get_live_channels():
			img = os.path.join(self.resources_dir, 'picture', 'logo_ct%s_400x225.png' % channel_id)
			self.add_dir(channel_name, img, cmd=self.list_channel_archive, channel_id=channel_id, d=d)

	# ##################################################################################################################

	def list_program_item(self, item, episodes=False):
		if item.get('active', '1') != '1':
			return

		if item.get('time'):
			title = "[" + item['time'] + "] " + item['title']
		else:
			title = item['title']

		try:
			rating = int(item['rating']) / 10
		except:
			rating = None

		info_labels = {
			'rating': rating,
			'plot': item.get('synopsis')
		}

		menu = self.create_ctx_menu()
		menu.add_menu_item(self._('Related'), cmd=self.list_context, item_id=item.get('ID'), context_name='related')

		if not episodes:
			menu.add_menu_item(self._('Episodes'), cmd=self.list_context, item_id=item.get('ID'), context_name='episodes')

		menu.add_menu_item(self._('Bonuses'), cmd=self.list_context, item_id=item.get('ID'), context_name='bonuses')

		img = item.get('imageURL')
		if img and img.startswith('//'):
			img = 'http:' + img

		if episodes:
			self.add_dir(title, img, info_labels=info_labels, menu=menu, cmd=self.list_context, item_id=item.get('ID'), context_name='episodes')
		else:
			self.add_video(title, img, info_labels=info_labels, menu=menu, cmd=self.play_item, item_id=item.get('ID'))

	# ##################################################################################################################

	def list_channel_archive(self, channel_id, d):
		for item in self.ivysilani.get_channel_epg(channel_id, d):
			self.list_program_item(item)

	# ##################################################################################################################

	def list_context(self, item_id, context_name, page=1):
		items = self.ivysilani.get_context_list(item_id, context_name, page)
		for item in items:
			self.list_program_item(item)

		if len(items) == self.ivysilani.PAGE_SIZE:
			self.add_next(cmd=self.list_context, item_id=item_id, context_name=context_name, page=page+1)

	# ##################################################################################################################

	def list_letters(self):
		for item_id, item_name in self.ivysilani.get_alphabet():
			self.add_dir(item_name, cmd=self.list_letter, letter_id=item_id)

	# ##################################################################################################################

	def list_genres(self):
		for item_id, item_name in self.ivysilani.get_genres():
			self.add_dir(item_name, cmd=self.list_genre, genre_id=item_id)

	# ##################################################################################################################

	def list_letter(self, letter_id):
		for item in self.ivysilani.get_program_by_letter(letter_id):
			self.list_program_item(item, episodes=True)

	# ##################################################################################################################

	def list_genre(self, genre_id):
		for item in self.ivysilani.get_program_by_genre(genre_id):
			self.list_program_item(item, episodes=True)

	# ##################################################################################################################

	def list_spotlight(self, sid):
		for item in self.ivysilani.get_spotlight(sid):
			self.list_program_item(item)

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
			'drm' : {
				'licence_url': 'https://ivys-wvproxy.o2tv.cz/license?access_token=c3RlcGFuLWEtb25kcmEtanNvdS1wcm9zdGUtbmVqbGVwc2k='
			}
		}

	# ##################################################################################################################

	def play_item(self, item_id, try_nr=1):
		if try_nr > 3:
			return

		exc = None
		for i in item_id.split('|'):
			try:
				self.log_debug("Trying to get stream info for ID: %s" % i)
				stream = self.ivysilani.get_stream_url(i, self.get_setting('stream_type'))
				break
			except Exception as e:
				self.log_debug("Failed to get stream info: %s" % str(e))
				exc = e
		else:
			raise exc

		self.log_debug("Original stream address: %s" % stream['url'])

		if stream['type'] == 'hls':
			streams = self.get_hls_streams(stream['url'], max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				# sometimes it doesn't work at first time ...
				return self.play_item(item_id, try_nr+1)

			for s in streams:
				url = stream_key_to_hls_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth']} )

				bandwidth = int(s['bandwidth'])

				if bandwidth >= 6272000:
					quality = "1080p"
				elif bandwidth >= 3712000:
					quality = "720p"
				elif bandwidth >= 2176000:
					quality = "576p"
				elif bandwidth >= 1160000:
					quality = "404p"
				elif bandwidth >= 628000:
					quality = "288p"
				else:
					quality = "144p"

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': quality
				}

				self.add_play(stream['title'], url, info_labels=info_labels)
		elif stream['type'] == 'dash':
			streams = self.get_dash_streams(stream['url'], max_bitrate=self.get_setting('max_bitrate'))
			if not streams:
				# sometimes it doesn't work at first time ...
				return self.play_item(item_id, try_nr+1)

			for s in streams:
				url = stream_key_to_dash_url(self.http_endpoint, {'url': s['playlist_url'], 'bandwidth': s['bandwidth']})

				info_labels = {
					'bandwidth': int(s['bandwidth']),
					'quality': s['height'] + 'p' if s.get('height') else "720p"
				}

				self.add_play(stream['title'], url, info_labels=info_labels)


	# ##################################################################################################################
