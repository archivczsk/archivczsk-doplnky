# -*- coding: utf-8 -*-
from functools import partial
from tools_archivczsk.compat import urljoin
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.date_utils import iso8601_to_datetime
from tools_archivczsk.contentprovider.provider import InfoLabels
from datetime import date, timedelta, datetime
import re

PLAYLIST_IN_EMBED = re.compile(r"""url\s*:\s*["']([^"']*\.m3u8[^"']*)["']""")
KIND_MARKER = re.compile(r"video_id=\d{8}-([ZH])-", re.I)
KIND_MAP = {
	'Z': 'vodMatches',
    'H': 'highlights',
}

# ##################################################################################################################

class TVTipsportContentProvider(CommonContentProvider):
	BASE_URL = 'https://tv.tipsport.cz/'

	def __init__(self):
		CommonContentProvider.__init__(self)
		self.req_session = self.get_requests_session()

	# ##################################################################################################################

	def load_matches(self):
		response = self.req_session.get(urljoin(self.BASE_URL, 'stream.json'))
		response.raise_for_status()
		resp_json = response.json()

		matches = []

		for k in ('liveMatches', 'vodMatches', 'highlights'):
			for m in (resp_json.get(k) or []):
				m['scheduledStart'] = iso8601_to_datetime(m['scheduledStart'], True)
				m['thumbnail'] = urljoin(self.BASE_URL, m['thumbnail'])

				marker = KIND_MARKER.search(m['streamUrl'])
				m['type'] = KIND_MAP.get(marker.group(1), k) if marker else k
				m['league'] = m['league'].strip()
				matches.append(m)

		return sorted(matches, key=lambda x: x['scheduledStart'], reverse=True)

	# ##################################################################################################################

	def get_item_info_labels(self, item):
		il = InfoLabels('[{}] {} {} {}'.format(_I(item['scheduledStart'].strftime('%d.%m.%Y')), item['homeTeam'], _I('vs.'), item['awayTeam']))
		il.img = item['thumbnail']

		if item.get('time'):
			try:
				time_parts = item.get('time').split(':')
				if len(time_parts) == 1:
					h = 0
					m = 0
					s = time_parts[0]
				elif len(time_parts) == 2:
					m, s = time_parts
					h = 0
				elif len(time_parts) == 3:
					h, m, s = time_parts

				il.duration = timedelta(hours=int(h), minutes=int(m), seconds=int(s)).total_seconds()
			except:
				self.log_error("Failed to parse match duration: {}".format(item.get('time')))
				self.log_exception()

		il.desc = '{}: {}\n{}: {}'.format(self._("League"), item['league'], self._("Start"), item['scheduledStart'].strftime('%d.%m.%Y %H:%M'))

		if item.get('homeScore') and item.get('awayScore'):
			il.desc += '\n{}: {} : {}'.format(self._("Result"), item['homeScore'], item['awayScore'])

		il.active = item['scheduledStart'] < datetime.now()

		return il

	# ##################################################################################################################

	def root(self):
		try:
			self.matches = self.load_matches()
		except Exception as e:
			self.log_exception()
			raise AddonErrorException("{}:\n{}".format(self._("Failed to load list of matches from server"), e))

		now = datetime.now()

		for m in filter(lambda x: x['scheduledStart'] < now and x['scheduledStart'] + timedelta(minutes=120) > now, self.matches):
			il = self.get_item_info_labels(m)
			self.add_video(il, cmd=self.resolve_video, video_title=il.title, video_url=m.get('streamUrl'))

		self.add_dir(self._("Upcoming"), cmd=self.list_upcoming)
		self.add_dir(self._("Records"), cmd=self.list_records)
		self.add_dir(self._("Highlights"), cmd=self.list_records, record_type='highlights')
		self.add_dir(self._("By league"), cmd=self.list_leagues)

	# ##################################################################################################################

	def list_upcoming(self):
		for m in sorted(filter(lambda x: x['scheduledStart'] > datetime.now(), self.matches), key=lambda x: x['scheduledStart']):
			il = self.get_item_info_labels(m)
			self.add_video(il)

	# ##################################################################################################################

	def list_records(self, record_type='vodMatches', league=None):
		for m in filter(lambda x: (not record_type) or x['type'] == record_type, self.matches):
			if league and m['league'] != league:
				continue

			il = self.get_item_info_labels(m)
			if not record_type and m['type'] == 'highlights':
				il.title += ' ({})'.format(_I(self._("Highlight")))

			self.add_video(il, cmd=self.resolve_video, video_title=il.title, video_url=m.get('streamUrl'))

	# ##################################################################################################################

	def list_leagues(self):
		leagues = [m['league'] for m in self.matches]
		leagues = sorted(list(set(leagues)))

		for l in leagues:
			self.add_dir(l, cmd=self.list_records, record_type=None, league=l)

	# ##################################################################################################################

	def resolve_video(self, video_title, video_url):
		if not video_url:
			raise AddonErrorException(self._("Video URL is not available for this match."))

		video_url = urljoin(self.BASE_URL, video_url)
		response = self.req_session.get(video_url, headers={'Referer': self.BASE_URL})
		response.raise_for_status()

		match = PLAYLIST_IN_EMBED.search(response.text)

		if not match:
			self.log_error("Failed to find playlist URL in the video page: {}".format(video_url))
			raise AddonErrorException(self._("Failed to find playlist URL in the video page."))

		stream_url = urljoin(response.url, match.group(1).strip())
		return self.resolve_streams(video_title, stream_url)


	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth'],
		}

	# ##################################################################################################################

	def resolve_streams(self, video_title, url):
		for one in self.get_hls_streams(url, requests_session=self.req_session, max_bitrate=self.get_setting('max_bitrate')):
			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, one['url'], info_labels=info_labels)


	# ##################################################################################################################
