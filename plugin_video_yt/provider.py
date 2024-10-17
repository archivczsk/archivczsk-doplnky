# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.player.features import PlayerFeatures
from time import time
from datetime import timedelta
from base64 import b64decode
import re, os, json
from .youtube import resolve as yt_resolve

class YoutubeContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'Youtube', settings=settings, data_dir=data_dir)
		self.watched = self.load_cached_data('watched')
		self.req_session = self.get_requests_session()
		self.max_results = 100
		self.api_keys = json.loads(b64decode(b'WyJBSXphU3lDVFdDNzVpNzBtb0pMenlOaDN0dDRqekNsalpjUmtVOFkiLCAiQUl6YVN5Q0lNNEV6TnFpMWluMjJmNFozUnUzaVl2TGFZOHRjM2JvIiwgIkFJemFTeUQySjJscW5qRTVWMGZIdmlFSUNITXRjMlBTS3FZN0lTayIsICJBSXphU3lCVV9vV0VJVUxpMy1uOTZ2V0tFVFlDTXNsZFlEQWx6Mk0iLCAiQUl6YVN5QzRDM2d6U1NFcnptYzJGZVVUbGVRcVpHenc4LXotZDZ3IiwgIkFJemFTeUNyRldpUGZHY2I1SXN5Uy13cEFNazZlYU5kTWFDOHBYcyIsICJBSXphU3lEbFpSMlVod1FYZUd3MkloQ1JucG9aQjhMSFprYWd3STQiLCAiQUl6YVN5Q1hxanMyWlBiMFBRUmVJV2lFTk1BQWtTeDBfdHZkNG5rIiwgIkFJemFTeUNzRTkxUFRELVhqVFUzT19JWnBZMFB2Vm9tMnR3NERyOCIsICJBSXphU3lBcnJoa2g0OWIyR05sQzhVZExvZHEzdVNwS3pjZ2R6ZWciLCAiQUl6YVN5Q1BjQUtDNzRTemdRQjhNU1hLY1BPNnpJb1ZmcXdsT2lnIiwgIkFJemFTeURCa29IZEQxSXc2SG9vTWhNb09iYkhGQ1hIRlN3S3pJVSIsICJBSXphU3lDNEMzZ3pTU0Vyem1jMkZlVVRsZVFxWkd6dzgtei1kNnciLCAiQUl6YVN5QUdQUDRqQTNoTDhmZXNqeGFWR2U4YmRWVW9RcUtMRExRIiwgIkFJemFTeUFfNW13aVZSWko5WkphaXR1cXYxbmdJQ2RMLTVGMTdQayIsICJBSXphU3lBLXV3T0taQnBieXBXcDFUV3B1WWY1SzAtNHd1UHp3RzgiLCAiQUl6YVN5RGpuZXdqNUpKRnVxWmFva3FkYkoybWE3bmhQa3V3VHBNIiwgIkFJemFTeUJ2Z1lVX1lEQkpWU3RDNkxEWDRHZ2tpWDkxMnZtSHJDZyIsICJBSXphU3lCODBoaFIySEc4aUxxV1AtTXdmWjhDdnlYV3NQX0tyQUEiLCAiQUl6YVN5QkRGcWJidDViMEo5Y3VvaGw1cWtnQUYyWUo5UVVfa0l3IiwgIkFJemFTeUJ0blR6YU00MHRWZXVEV1hrQ3FuWGFVVjhiMkotMk5iWSIsICJBSXphU3lEZF9zZnZRNE5BU2ItazBvS1lBcl9nOUZaY1FJTHR5S2MiLCAiQUl6YVN5QnRuVHphTTQwdFZldURXWGtDcW5YYVVWOGIySi0yTmJZIiwgIkFJemFTeUJqODBualdzMEtjZ0Q2QTQ0eTZjRGRHMnFpbmZ2Ylo0VSIsICJBSXphU3lENDktWFoySlY3UndzM0tETTJUN25BNTZKYmktTzdkalkiLCAiQUl6YVN5Qmo4MG5qV3MwS2NnRDZBNDR5NmNEZEcycWluZnZiWjRVIiwgIkFJemFTeUR5cTNucjJLamJGTUU5RWVOcEh5OTdBWDg3dms3NUhfWSIsICJBSXphU3lBbHd6X1ZqNm1XSUJncWdLRDByUXdJODJGYTRTM2Nza2siLCAiQUl6YVN5RC1vWjhBcXNWTUo3U3pYZDB5ZnBSVEF6SmFwbGVnYUIwIiwgIkFJemFTeUFTUExBV21qQ1BEUm9pTXR0MUFIR1EwVEd5Ung5d1RSVSIsICJBSXphU3lCaWhuWEtVbXg5aDZESEFsVE5rclotNnpuenJ6M01FMU0iLCAiQUl6YVN5QThIVlFFc3lST0xtZVo0UDNHaEtSQ1UyQmFqVG5KVU5jIiwgIkFJemFTeUFnRThKT1kwNmtKU1V4QllZWENHS2hRbmh4MXFEOGpkQSIsICJBSXphU3lDR3pfOGJFMzJxNE5Ba2pkQVhqcEFpaWdCUzZ6OVpBU1UiLCAiQUl6YVN5QnhUdjBSUEl6X0Rqdms5U1JmTUNUTzNpdV83WXNNanJRIiwgIkFJemFTeURGNDZJeVpZd1BsYjZaQnhBRDYtSXVMeFZOWXNiVEl3USIsICJBSXphU3lCa2lMQXRhYXYyZWNJN1Z2Z3MtaUJlZU1zX3YzWG5kRDgiLCAiQUl6YVN5Qkc5OENzQlVTTFhfd2FWTFNiMzRiQ2VTRjFxc0pxR2pFIiwgIkFJemFTeUM3VkdROU9qdmpPYUlUT01tNFR2TFRlRy1feVFaUmkwUSIsICJBSXphU3lCaWE1Szd3MFNEOGJBS0dhc2RhQzl0SDQwXzBnRTdsRHciLCAiQUl6YVN5Q3JZVHpxVUx2V045YjlOSW5EZFFNcGY1dDVoeTl6UlNvIiwgIkFJemFTeUF0R3Vyd042R2Zzc0N3VlNIWHpQUmJBNG9meFlNNUZSbyIsICJBSXphU3lDT1RaVEV6VHlkY1h1ZXRjb25reFpVakVYS2lQTURwRzAiLCAiQUl6YVN5Q0F5WDYzQlI5XzVYUzhqRmhYeFY0ZG9JR2h2YWpjWjdjIiwgIkFJemFTeUNrZ2xYcHNvWG83UWpzTERCQUw4bXpDZlg0WVp6cGR0ZyIsICJBSXphU3lBN19FTTZ5NVI4UzlFdExXcC1KUEZBNDN1dGF1aTMtdm8iLCAiQUl6YVN5QW1obFQ3c1YtT0JadlJCRzh4alVHc2tUM2VzajBtYzNrIiwgIkFJemFTeUJfYjhCcjd1MW1JM2Yzb193N1VJT0F4VUdHSklHeDktYyIsICJBSXphU3lBbWhsVDdzVi1PQlp2UkJHOHhqVUdza1QzZXNqMG1jM2siLCAiQUl6YVN5RGlSTURVY25tbV93U1ZoWUxvMHZoQWVrSHlHaEl6a2N3IiwgIkFJemFTeUNqVG1xVHhSRmZhb2FkcUp5U1EwQzNIS2l6Vm5kWnJJVSIsICJBSXphU3lDdGQ5N1plczdraFpZbTJHQ0hjWUFmRFQ1RWd2bVdxWmsiLCAiQUl6YVN5Q0ZqcnU4ZE9aYkd0WlVpX0FRdTFDejFNTG9BTmFZMjJrIiwgIkFJemFTeURYU1hiUVNHRUN3aWpIN1RhQUs5UnRmSkFPSngwNjJHMCIsICJBSXphU3lCVHByaTZJamVmZWQ2bThONDhjN3hHUlJlZXBmd3JXYzAiLCAiQUl6YVN5QmViQkcxTFp5Yk96NURORGRaTXEzNW53c1ZxUm5LZVVrIiwgIkFJemFTeUNaQ1NFbUtoZm5QT1FORzBTanU0aGx3MllEVXhnaTZwZyIsICJBSXphU3lCT185bHdGQ0lQTmYxT3lvQWZ3VnVOS3RFTXB0Z3U0NG8iLCAiQUl6YVN5QjFaenJUbUZwZFNOYzJnSG1GOW45UzExQTR2Z0hyS2JjIiwgIkFJemFTeUNUeVRBRnhCN1BTeTB2S0I0RGo1OHc2djNiUFFobVBUVSIsICJBSXphU3lDVjRmbWZkZ3NWYWxHTlIzc2MtMFczY2JwRVo4dU9kNjAiLCAiQUl6YVN5REZyUU12WFRaOVBBUkZYdkxwY09UU2VDOGJCT3U2UHcwIiwgIkFJemFTeURSWWhFY29VWGlqX2kzMGlkdnFha0JWRUVQU2xrWEtyayIsICJBSXphU3lCd1RxaDdHLXhWNFdXWmdfLVFGQjA0SzR2Q1BqTFh6QVkiLCAiQUl6YVN5REFlQmZVdmpaWnNjNFd4NTJDa3ZOakZMT19wczNXZ204IiwgIkFJemFTeUE2RmJVYkRxVDJ3amFsdWlvM0N2Umh2V1N5d1lKRWNQZyIsICJBSXphU3lDemxiU181dlN0cm9EbWNkYThSaGs5T2swV1JDS2k4blEiLCAiQUl6YVN5QUczR3lEUk1TZ2NfXzlZS00zN0RORHppMG9nX0tvejFRIiwgIkFJemFTeURKTGY3cGxkanZmNlFldlZGX0JhejBTcmNYMEludmVNSSJd').decode('utf-8'))
		self.api_key_blacklist = {}

	# ##################################################################################################################

	def root(self):
		if self.get_setting('player-check'):
			PlayerFeatures.request_exteplayer3_version(self, 172)

		self.add_search_dir()
		self.add_dir(self._("Last watched"), cmd=self.list_watched)
		self.load_channels()

	# ##################################################################################################################

	def list_watched(self):
		ids = [i[0] for i in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True)]

		self.list_videos(None, None, ids)

	# ##################################################################################################################

	def get_api_key(self):
		api_key = self.get_setting('api_key')

		if api_key:
			api_keys = [api_key]
		else:
			api_keys = self.api_keys

		act_time = int(time())

		for api_key in api_keys:
			if self.api_key_blacklist.get(api_key, 0) < act_time:
				return api_key

		return None

	# ##################################################################################################################

	def blacklist_api_key(self, api_key):
		self.api_key_blacklist[api_key] = int(time()) + 7200

	# ##################################################################################################################

	def call_api(self, endpoint, params={}):
		while True:
			api_key = self.get_api_key()
			if not api_key:
				raise AddonErrorException(self._("This addon reached available limit of requests to youtube API. Try again later."))

			params.update({
				'key': api_key
			})

			try:
				response = self.req_session.get("https://www.googleapis.com/youtube/v3/" + endpoint, params=params)
				if response.status_code >= 400:
					# quata exceeded or wrong/revoked api key
					self.log_error("Request using API KEY %s FAILED - blacklisting" % api_key[-8:])
					self.blacklist_api_key(api_key)
					continue

				response.raise_for_status()
			except Exception as e:
				self.log_exception()
				raise AddonErrorException(str(e))

	#		dump_json_request(response)
			return response.json()

	# ##################################################################################################################

	def yt_time(self, duration="P1W2DT6H21M32S", in_sec=False):
		ISO_8601 = re.compile(
			'P'
			'(?:(?P<years>\d+)Y)?'
			'(?:(?P<months>\d+)M)?'
			'(?:(?P<weeks>\d+)W)?'
			'(?:(?P<days>\d+)D)?'
			'(?:T'
			'(?:(?P<hours>\d+)H)?'
			'(?:(?P<minutes>\d+)M)?'
			'(?:(?P<seconds>\d+)S)?'
			')?')

		if duration:
			m = ISO_8601.match(duration)
		else:
			m = None

		if m == None:
			return None if in_sec else ''

		units = list(m.groups()[-3:])
		units = list(reversed([int(x) if x != None else 0 for x in units]))

		seconds=sum([x*60**units.index(x) for x in units])

		if in_sec:
			return seconds
		else:
			return str(timedelta(seconds=seconds))

	# ##################################################################################################################

	def list_videos(self, endpoint, params, ids=None):
		watched = False

		if ids is not None:
			data = {}
			watched = True
		else:
			ids = []
			data = self.call_api(endpoint, params)
			for item in (data.get('items') or []):
				video_id = item.get("id", {}).get("videoId")
				if video_id:
					ids.append(video_id)

		detail_params = {
			'id': ','.join(ids),
			'part': 'snippet,statistics,contentDetails'
		}

		detail = {i.get('id'): i for i in (self.call_api('videos', detail_params).get('items') or [])}

		for video_id in ids:
			video_detail = detail.get(video_id,{})
			video_detail_snippet = video_detail.get('snippet', {})

			title = decode_html(video_detail_snippet.get("title", ""))

			is_live = video_detail_snippet.get("liveBroadcastContent")
			if is_live == "upcoming":
				title = _C('red', title)
			elif is_live == "live":
				title = _C('green', title)

			img = video_detail_snippet.get("thumbnails", {}).get("standard", {}).get("url")
			duration = video_detail.get("contentDetails", {}).get("duration")

			pt = video_detail_snippet.get("publishedAt", "") #2020-12-19T19:58:27Z
			pts = re.search("([\d]{4})-([\d]{2})-([\d]{2})T([\d]{2}):([\d]{2})",pt)
			publish = pts.group(3)+"."+pts.group(2)+"."+pts.group(1)+" "+pts.group(4)+":"+pts.group(5) if pts else ""

			channel_title = video_detail_snippet.get("channelTitle") or ''
			channel_id = video_detail_snippet.get("channelId", "")
			views = video_detail.get("statistics", {}).get("viewCount", "")

			plot = '{} [{}] {} ({}x)\n{}'.format(
				publish,
				channel_title,
				self.yt_time(duration),
				views,
				decode_html(video_detail_snippet.get("description") or '')
			)

			info_labels = {
				'plot': plot,
				'duration': self.yt_time(duration, True)
			}

			menu = self.create_ctx_menu()

			if watched:
				menu.add_menu_item(self._('Remove from watched'), cmd=self.remove_watched_item, video_id=video_id)

			channel_params = {
				'channelId': channel_id,
				'maxResults': self.max_results,
				'part': 'id',
				'order': 'date',
			}
			menu.add_menu_item(self._('View channel videos'), cmd=self.list_videos, endpoint='search', params=channel_params)
			menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)
			self.add_video(title, img, info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)

		if "nextPageToken" in data:
			params = params.copy()
			params['pageToken'] = data["nextPageToken"]

			self.add_next(cmd=self.list_videos, endpoint=endpoint, params=params)

	# ##################################################################################################################

	def save_channel(self,channel_name,channel_id):
		history = ['{};{}'.format(channel_name, channel_id)]
		max_history = self.get_setting('channels')

		filename = os.path.join(self.data_dir, "channels.txt")
		try:
			with open(filename, "r") as file:
				for line in file:
					item = line[:-1]
					history.append(item)
		except IOError:
			pass

		try:
			cnt = 0
			with open(filename, "w") as file:
				for item in history:
					cnt = cnt + 1
					if cnt <= max_history:
						file.write('%s\n' % item)
		except:
			self.log_exception()
			pass

		self.refresh_screen()

	# ##################################################################################################################

	def load_channels(self):
		filename = os.path.join(self.data_dir, "channels.txt")
		try:
			with open(filename, "r") as file:
				for line in file:
					item = line[:-1].split(";")
					channel_params = {
						'channelId': item[1],
						'maxResults': self.max_results,
						'part': 'id',
						'order': 'date',
					}

					self.add_dir(item[0], cmd=self.list_videos, endpoint='search', params=channel_params)
		except IOError:
			self.log_exception()

	# ##################################################################################################################

	def search(self, keyword, search_id=''):
		if search_id == 'resolve':
			# API: keyword = {
			# 	'title': 'Video title' - can be None
			#	'url': 'Video url or youtube video ID'
			#	'playlist': 'playlist interface used to add resolved item' - can be None
			#	'settings': addon settings used for resolving - can be None (use youtube addon settings)
			# }

			self.log_debug("Resolve interface for other addons called for keyword '%s'" % keyword)

			# interface for other addons to directly play youtube videos
			if not isinstance(keyword, dict):
				keyword = {'url': keyword}

			title = keyword.get('title', 'Video')
			video_id = keyword['url']
			playlist = keyword.get('playlist', self)
			settings = keyword.get('settings')

			try:
				url = yt_resolve(video_id, settings)
			except Exception as e:
				self.log_exception()
			else:
				# if no settings from other addon are specified and our player is set to exteplayer3, then force it (because of DASH support)
				self.log_debug('auto_used_player: %s' % self.get_setting('auto_used_player'))
				if not settings and self.get_setting('auto_used_player') == '2':
					s = {'forced_player': 5002}
				else:
					s = {}
				playlist.add_play(title, url, settings=s)
		else:
			# standard search
			params = {
				'q': keyword,
				'maxResults': self.max_results,
	#			'part': 'snippet,id'
				'part': 'id'
			}
			self.list_videos('search', params)

	# ##################################################################################################################

	def resolve_video(self, video_title, video_id):
		try:
			url = yt_resolve(video_id, self.settings)
		except Exception as e:
			self.log_exception()
			raise AddonErrorException(self._("Failed to get playable video stream address") + ':\n%s' % str(e))

		self.add_play(video_title, url)
		self.add_watched_item(video_id)

	# ##################################################################################################################

	def add_watched_item(self, video_id):
		self.watched[video_id] = {
			'time': int(time())
		}

		max_watched = int(self.get_setting('max_watched'))

		if len(self.watched) > max_watched:
			for k,_ in sorted(self.watched.items(), key=lambda i: i[1]['time'], reverse=True)[max_watched:]:
				del self.watched[k]

		self.save_cached_data('watched', self.watched)

	# ##################################################################################################################

	def remove_watched_item(self, video_id):
		if video_id in self.watched:
			del self.watched[video_id]

		self.save_cached_data('watched', self.watched)
		self.refresh_screen()

	# ##################################################################################################################
