# -*- coding: utf-8 -*-
from functools import partial
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.string_utils import _I, _C, _B
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.date_utils import iso8601_to_datetime
from datetime import date, timedelta, datetime
import re

# ##################################################################################################################

class TiposTVContentProvider(CommonContentProvider):
	def __init__(self):
		CommonContentProvider.__init__(self)
		self.req_session = self.get_requests_session()
		self.beautifulsoup = self.get_beautifulsoup()

	# ##################################################################################################################

	def call_api(self, endpoint, params=None):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://www.tipos.sk/Millennium.TiposTV/TIPOSTV/' + endpoint

		headers = {
			'Accept': 'application/json; charset=utf-8',
			'X-Requested-With': 'XMLHttpRequest'
		}

		try:
			response = self.req_session.get(url, params=params, headers=headers)
		except Exception as e:
			raise AddonErrorException(self._('Request to remote server failed. Try to repeat operation.') + '\n%s' % str(e))

#		dump_json_request(response)

		if response.status_code == 200:
			return response.json()
		else:
			raise AddonErrorException(self._('HTTP response code') + ': %d' % response.status_code)

	# ##################################################################################################################

	def root(self):
		self.add_dir(self._("Basketball"), cmd=self.list_basketball)
		self.add_dir(self._("Football"), cmd=self.list_football)

	# ##################################################################################################################

	def list_basketball_live(self):
		now = datetime.now()
		today = now.date()

		for item in self.call_api('GetSchedule') or []:
			match_date = iso8601_to_datetime(item['date'])

			info_labels = {
				'plot': '[{}]\n{}\n{}'.format(str(match_date), item['competition'], item['tournament'])
			}

			if match_date < now and match_date.date() == today:
				title = '[{}] {}'.format(match_date.strftime("%H:%M"), _I(item['team1']) + ' vs. ' + _I(item['team2']))
				self.add_video(title, info_labels=info_labels, cmd=self.resolve_basketball_video, video_title=title, archive=item['live'])
			elif match_date.date() == today:
				title = '[{}] {}'.format(match_date.strftime("%H:%M"), _C('gray', item['team1']) + ' vs. ' + _C('gray', item['team2']))
				self.add_video(title, info_labels=info_labels)


	# ##################################################################################################################

	def load_basketball_data(self):
		self.basketball_data = []

		for item in self.call_api('GetArchive') or []:
			match_date = iso8601_to_datetime(item['date'])

			self.basketball_data.append({
				'plot': '[{}]\n{}\n{}'.format(str(match_date), item['competition'], item['tournament']),
				'title': '[{}] {}'.format(match_date.strftime("%d.%m.%Y %H:%M"), _I(item['team1']) + ' vs. ' + _I(item['team2'])),
				'match_date': match_date.date(),
				'archive': item['archive'],
				'highlight': item['highlight'],
				'team1': item['team1'],
				'team2': item['team2'],
				'competition': item['competition']
			})

	# ##################################################################################################################

	def list_basketball(self, filtering=None):
		if filtering is None:
			self.load_basketball_data()
			self.list_basketball_live()
			self.add_dir(self._("By month"), cmd=self.list_basketball, filtering='month')
			self.add_dir(self._("By competition"), cmd=self.list_basketball, filtering='competition')
			self.add_dir(self._("By team"), cmd=self.list_basketball, filtering='team')
		elif filtering == 'month':
			months = {}
			for item in self.basketball_data:
				d = item['match_date'].strftime("%Y / %m")
				months[d] = True

			for m in sorted(months.keys(), reverse=True):
				self.add_dir(m, cmd=self.list_basketball_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))
		elif filtering == 'competition':
			competition = {}
			for item in self.basketball_data:
				competition[item['competition']] = True

			for m in sorted(competition.keys()):
				self.add_dir(m, cmd=self.list_basketball_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))

		elif filtering == 'team':
			teams = {}
			for item in self.basketball_data:
				teams[item['team1']] = True
				teams[item['team2']] = True

			for m in sorted(teams.keys()):
				self.add_dir(m, cmd=self.list_basketball_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))

	# ##################################################################################################################

	def list_basketball_filtered(self, filter_fn):
		for item in filter(filter_fn, self.basketball_data):
			self.add_video(item['title'], info_labels={'plot': item['plot']}, cmd=self.resolve_basketball_video, video_title=item['title'], archive=item['archive'], highlight=item['highlight'])

	# ##################################################################################################################

	def load_football_data(self):
		self.football_data = []
		for item in self.call_api('GetArchiveFutbal'):
			match_date = iso8601_to_datetime(item['scheduled_start'])

			self.football_data.append({
				'title': '[{}] {}'.format(match_date.strftime("%d.%m.%Y %H:%M"), _I(item['home_team_name']) + ' vs. ' + _I(item['away_team_name'])),
				'plot': '[{}]\n{}\n{}: {}'.format(str(match_date), item['league_name'], self._("Result"), item['result']),
				'img': item['thumbnail'],
				'short_title': item['name'],
				'slug': item['slug'],
				'match_date': iso8601_to_datetime(item['scheduled_start']).date(),
				'league': item['league_name'],
				'team1': item['home_team_name'],
				'team2': item['away_team_name']
			})

	# ##################################################################################################################

	def list_football(self, filtering=None):
		if filtering is None:
			self.load_football_data()
			self.add_dir(self._("By month"), cmd=self.list_football, filtering='month')
			self.add_dir(self._("By league"), cmd=self.list_football, filtering='league')
			self.add_dir(self._("By team"), cmd=self.list_football, filtering='team')
		elif filtering == 'month':
			months = {}
			for item in self.football_data:
				d = item['match_date'].strftime("%Y / %m")
				months[d] = True

			for m in sorted(months.keys(), reverse=True):
				self.add_dir(m, cmd=self.list_football_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))
		elif filtering == 'league':
			league = {}
			for item in self.football_data:
				league[item['league']] = True

			for m in sorted(league.keys()):
				self.add_dir(m, cmd=self.list_football_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))

		elif filtering == 'team':
			teams = {}
			for item in self.football_data:
				teams[item['team1']] = True
				teams[item['team2']] = True

			for m in sorted(teams.keys()):
				self.add_dir(m, cmd=self.list_football_filtered, filter_fn=partial(self.filter_fn, criteria=filtering, value=m))

	# ##################################################################################################################

	@staticmethod
	def filter_fn(item, criteria, value):
		if criteria == 'month':
			return item['match_date'].strftime("%Y / %m") == value
		elif criteria == 'league':
			return item['league'] == value
		elif criteria == 'team':
			return item['team1'] == value or item['team2'] == value
		elif criteria == 'competition':
			return item['competition'] == value


	# ##################################################################################################################
	#
	def list_football_filtered(self, filter_fn):
		for item in filter(filter_fn, self.football_data):
			self.add_video(item['title'], item['img'], info_labels={'plot': item['plot']}, cmd=self.resolve_football_video, video_title=item['short_title'], slug=item['slug'])

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

	def resolve_basketball_video(self, video_title, archive, highlight=None):
		if highlight:
			lst = [
				self._("Full match"),
				self._('Highlight')
			]
			idx = self.get_list_input(lst)
			if idx == 0:
				url = archive
			elif idx == 1:
				url = highlight
			else:
				return

		soup = self.beautifulsoup(self.req_session.get(url).content)
		video_url = None

		for script in soup.find_all('script') or []:
			match = re.findall('https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', str(script))
			for u in match:
				if '.m3u8' in u:
					video_url = u.rstrip(',').rstrip('\'')
					return self.resolve_streams(video_title, video_url)

	# ##################################################################################################################

	def resolve_football_video(self, video_title, slug):
		url = None
		urls = self.get_football_urls(slug)

		if len(urls) == 0:
			self.log_error("No URLs for this match were found")
			return
		elif len(urls) == 1:
			url = urls[0]
		else:
			lst = [ self._("Part") + (' %d' % (i+1)) for i in range(len(urls)) ]
			idx = self.get_list_input(lst)

			if idx >= 0:
				url = urls[idx]

		if url is None:
			return

		self.add_play(video_title, url)

	# ##################################################################################################################

	def get_football_urls(self, slug):
		data = {
			"operationName":"Videos",
			"variables": {
				"gameSlug": slug
			},
			"query": '''query Videos($gameSlug: String!)
			{
				allGames(slug: $gameSlug)
				{
					edges
					{
						node
						{
							assets
						}
					}
				}
			}'''.replace('\t', '').replace('\n', ' ')
		}

		response = self.req_session.post('https://sport.video/graphql', json=data)
		response.raise_for_status()
#		dump_json_request(response)

		return response.json()['data']['allGames']['edges'][0]['node']['assets']

	# ##################################################################################################################
