# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.player.features import PlayerFeatures
from time import time
from datetime import timedelta, datetime
from base64 import b64decode
import re, os, io, json, requests
from .youtube import resolve as yt_resolve
from .youtube.captions import choose_track_url, download_srt

CHANNEL_VIDEOS_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"

class YoutubeContentProvider(CommonContentProvider):
	SUBTITLES_DIR = '/tmp'
	# YouTube refuses automatically translated subtitles quite often (HTTP 429), but later attempts usually succeed
	SUBTITLES_RETRY_DELAYS = (60, 180)

	def __init__(self):
		CommonContentProvider.__init__(self, 'Youtube')
		self.subtitles_retry = set()
		self.watched = self.load_cached_data('watched')
		self.req_session = self.get_requests_session()
		self.max_results = 50
		self.api_keys = json.loads(b64decode(b'WyJBSXphU3lDVFdDNzVpNzBtb0pMenlOaDN0dDRqekNsalpjUmtVOFkiLCAiQUl6YVN5Q0lNNEV6TnFpMWluMjJmNFozUnUzaVl2TGFZOHRjM2JvIiwgIkFJemFTeUQySjJscW5qRTVWMGZIdmlFSUNITXRjMlBTS3FZN0lTayIsICJBSXphU3lCVV9vV0VJVUxpMy1uOTZ2V0tFVFlDTXNsZFlEQWx6Mk0iLCAiQUl6YVN5QzRDM2d6U1NFcnptYzJGZVVUbGVRcVpHenc4LXotZDZ3IiwgIkFJemFTeUNyRldpUGZHY2I1SXN5Uy13cEFNazZlYU5kTWFDOHBYcyIsICJBSXphU3lEbFpSMlVod1FYZUd3MkloQ1JucG9aQjhMSFprYWd3STQiLCAiQUl6YVN5Q1hxanMyWlBiMFBRUmVJV2lFTk1BQWtTeDBfdHZkNG5rIiwgIkFJemFTeUNzRTkxUFRELVhqVFUzT19JWnBZMFB2Vm9tMnR3NERyOCIsICJBSXphU3lBcnJoa2g0OWIyR05sQzhVZExvZHEzdVNwS3pjZ2R6ZWciLCAiQUl6YVN5Q1BjQUtDNzRTemdRQjhNU1hLY1BPNnpJb1ZmcXdsT2lnIiwgIkFJemFTeURCa29IZEQxSXc2SG9vTWhNb09iYkhGQ1hIRlN3S3pJVSIsICJBSXphU3lDNEMzZ3pTU0Vyem1jMkZlVVRsZVFxWkd6dzgtei1kNnciLCAiQUl6YVN5QUdQUDRqQTNoTDhmZXNqeGFWR2U4YmRWVW9RcUtMRExRIiwgIkFJemFTeUFfNW13aVZSWko5WkphaXR1cXYxbmdJQ2RMLTVGMTdQayIsICJBSXphU3lBLXV3T0taQnBieXBXcDFUV3B1WWY1SzAtNHd1UHp3RzgiLCAiQUl6YVN5RGpuZXdqNUpKRnVxWmFva3FkYkoybWE3bmhQa3V3VHBNIiwgIkFJemFTeUJ2Z1lVX1lEQkpWU3RDNkxEWDRHZ2tpWDkxMnZtSHJDZyIsICJBSXphU3lCODBoaFIySEc4aUxxV1AtTXdmWjhDdnlYV3NQX0tyQUEiLCAiQUl6YVN5QkRGcWJidDViMEo5Y3VvaGw1cWtnQUYyWUo5UVVfa0l3IiwgIkFJemFTeUJ0blR6YU00MHRWZXVEV1hrQ3FuWGFVVjhiMkotMk5iWSIsICJBSXphU3lEZF9zZnZRNE5BU2ItazBvS1lBcl9nOUZaY1FJTHR5S2MiLCAiQUl6YVN5QnRuVHphTTQwdFZldURXWGtDcW5YYVVWOGIySi0yTmJZIiwgIkFJemFTeUJqODBualdzMEtjZ0Q2QTQ0eTZjRGRHMnFpbmZ2Ylo0VSIsICJBSXphU3lENDktWFoySlY3UndzM0tETTJUN25BNTZKYmktTzdkalkiLCAiQUl6YVN5Qmo4MG5qV3MwS2NnRDZBNDR5NmNEZEcycWluZnZiWjRVIiwgIkFJemFTeUR5cTNucjJLamJGTUU5RWVOcEh5OTdBWDg3dms3NUhfWSIsICJBSXphU3lBbHd6X1ZqNm1XSUJncWdLRDByUXdJODJGYTRTM2Nza2siLCAiQUl6YVN5RC1vWjhBcXNWTUo3U3pYZDB5ZnBSVEF6SmFwbGVnYUIwIiwgIkFJemFTeUFTUExBV21qQ1BEUm9pTXR0MUFIR1EwVEd5Ung5d1RSVSIsICJBSXphU3lCaWhuWEtVbXg5aDZESEFsVE5rclotNnpuenJ6M01FMU0iLCAiQUl6YVN5QThIVlFFc3lST0xtZVo0UDNHaEtSQ1UyQmFqVG5KVU5jIiwgIkFJemFTeUFnRThKT1kwNmtKU1V4QllZWENHS2hRbmh4MXFEOGpkQSIsICJBSXphU3lDR3pfOGJFMzJxNE5Ba2pkQVhqcEFpaWdCUzZ6OVpBU1UiLCAiQUl6YVN5QnhUdjBSUEl6X0Rqdms5U1JmTUNUTzNpdV83WXNNanJRIiwgIkFJemFTeURGNDZJeVpZd1BsYjZaQnhBRDYtSXVMeFZOWXNiVEl3USIsICJBSXphU3lCa2lMQXRhYXYyZWNJN1Z2Z3MtaUJlZU1zX3YzWG5kRDgiLCAiQUl6YVN5Qkc5OENzQlVTTFhfd2FWTFNiMzRiQ2VTRjFxc0pxR2pFIiwgIkFJemFTeUM3VkdROU9qdmpPYUlUT01tNFR2TFRlRy1feVFaUmkwUSIsICJBSXphU3lCaWE1Szd3MFNEOGJBS0dhc2RhQzl0SDQwXzBnRTdsRHciLCAiQUl6YVN5Q3JZVHpxVUx2V045YjlOSW5EZFFNcGY1dDVoeTl6UlNvIiwgIkFJemFTeUF0R3Vyd042R2Zzc0N3VlNIWHpQUmJBNG9meFlNNUZSbyIsICJBSXphU3lDT1RaVEV6VHlkY1h1ZXRjb25reFpVakVYS2lQTURwRzAiLCAiQUl6YVN5Q0F5WDYzQlI5XzVYUzhqRmhYeFY0ZG9JR2h2YWpjWjdjIiwgIkFJemFTeUNrZ2xYcHNvWG83UWpzTERCQUw4bXpDZlg0WVp6cGR0ZyIsICJBSXphU3lBN19FTTZ5NVI4UzlFdExXcC1KUEZBNDN1dGF1aTMtdm8iLCAiQUl6YVN5QW1obFQ3c1YtT0JadlJCRzh4alVHc2tUM2VzajBtYzNrIiwgIkFJemFTeUJfYjhCcjd1MW1JM2Yzb193N1VJT0F4VUdHSklHeDktYyIsICJBSXphU3lBbWhsVDdzVi1PQlp2UkJHOHhqVUdza1QzZXNqMG1jM2siLCAiQUl6YVN5RGlSTURVY25tbV93U1ZoWUxvMHZoQWVrSHlHaEl6a2N3IiwgIkFJemFTeUNqVG1xVHhSRmZhb2FkcUp5U1EwQzNIS2l6Vm5kWnJJVSIsICJBSXphU3lDdGQ5N1plczdraFpZbTJHQ0hjWUFmRFQ1RWd2bVdxWmsiLCAiQUl6YVN5Q0ZqcnU4ZE9aYkd0WlVpX0FRdTFDejFNTG9BTmFZMjJrIiwgIkFJemFTeURYU1hiUVNHRUN3aWpIN1RhQUs5UnRmSkFPSngwNjJHMCIsICJBSXphU3lCVHByaTZJamVmZWQ2bThONDhjN3hHUlJlZXBmd3JXYzAiLCAiQUl6YVN5QmViQkcxTFp5Yk96NURORGRaTXEzNW53c1ZxUm5LZVVrIiwgIkFJemFTeUNaQ1NFbUtoZm5QT1FORzBTanU0aGx3MllEVXhnaTZwZyIsICJBSXphU3lCT185bHdGQ0lQTmYxT3lvQWZ3VnVOS3RFTXB0Z3U0NG8iLCAiQUl6YVN5QjFaenJUbUZwZFNOYzJnSG1GOW45UzExQTR2Z0hyS2JjIiwgIkFJemFTeUNUeVRBRnhCN1BTeTB2S0I0RGo1OHc2djNiUFFobVBUVSIsICJBSXphU3lDVjRmbWZkZ3NWYWxHTlIzc2MtMFczY2JwRVo4dU9kNjAiLCAiQUl6YVN5REZyUU12WFRaOVBBUkZYdkxwY09UU2VDOGJCT3U2UHcwIiwgIkFJemFTeURSWWhFY29VWGlqX2kzMGlkdnFha0JWRUVQU2xrWEtyayIsICJBSXphU3lCd1RxaDdHLXhWNFdXWmdfLVFGQjA0SzR2Q1BqTFh6QVkiLCAiQUl6YVN5REFlQmZVdmpaWnNjNFd4NTJDa3ZOakZMT19wczNXZ204IiwgIkFJemFTeUE2RmJVYkRxVDJ3amFsdWlvM0N2Umh2V1N5d1lKRWNQZyIsICJBSXphU3lDemxiU181dlN0cm9EbWNkYThSaGs5T2swV1JDS2k4blEiLCAiQUl6YVN5QUczR3lEUk1TZ2NfXzlZS00zN0RORHppMG9nX0tvejFRIiwgIkFJemFTeURKTGY3cGxkanZmNlFldlZGX0JhejBTcmNYMEludmVNSSJd').decode('utf-8'))
		self.api_key_blacklist = {}

	# ##################################################################################################################

	def root(self):
		if self.get_setting('player-check'):
			PlayerFeatures.check_latest_exteplayer3(self)

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

			try:
				response = requests.post("https://www.youtube.com/youtubei/v1/" + endpoint + "?key=" + api_key, json=params)
				if response.status_code >= 400:
					# quota exceeded or wrong/revoked api key
					self.log_error("Request using API KEY %s FAILED - blacklisting" % api_key[-8:])
					self.blacklist_api_key(api_key)
					continue

				response.raise_for_status()
			except Exception as e:
				self.log_exception()
				raise AddonErrorException(str(e))

#			with open("/tmp/yt.txt", "w") as f:
#				f.write(response.text)

			return response.json()

	# ##################################################################################################################

	def to_seconds(self, time_str):
		total = 0
		try:
			parts = map(int, time_str.split(":"))
			for p in parts:
				total = total * 60 + p
		except:
			pass
		return total

	# ##################################################################################################################

	def iso_to_cet(self, s):
		try:
			dt = datetime.strptime(s[:-6], "%Y-%m-%dT%H:%M:%S")
			sign = 1 if s[-6] == "+" else -1
			h, m = int(s[-5:-3]), int(s[-2:])
			return (dt - sign * timedelta(hours=h, minutes=m) + timedelta(hours=1)).strftime("%d.%m.%Y %H:%M:%S")
		except:
			return "N/A"

	# ##################################################################################################################

	def format_time(self, seconds):
		h, rem = divmod(seconds, 3600)
		m, s = divmod(rem, 60)
		return "{}:{:02d}:{:02d}".format(h, m, s) if h > 0 else "{}:{:02d}".format(m, s)

	# ##################################################################################################################

	def list_videos(self, endpoint, params, ids=None):
		cont = None
		contItems = []
		if ids is not None:   ###### WATCHED
			params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"videoId":""}
			for video_id in ids:
				params['videoId'] = video_id
				data = self.call_api("player", params)
				if "videoDetails" in data:
					title = data.get("videoDetails").get("title", "N/A")
					length = data.get("videoDetails").get("lengthSeconds", 0)
					channel_id = data.get("videoDetails").get("channelId", "")
					desc = data.get("videoDetails").get("shortDescription", "")
					views = data.get("videoDetails").get("viewCount", "0")
					channel_title = data.get("microformat", {}).get("playerMicroformatRenderer", {}).get("ownerChannelName", "N/A")
					published = data.get("microformat", {}).get("playerMicroformatRenderer", {}).get("publishDate", "N/A")
					plot = '{} [{}] {} ({}x)\n{}'.format(
						self.iso_to_cet(published),
						channel_title,
						self.format_time(int(length)),
						views,
						decode_html(desc)
					)
					info_labels = {
						'plot': plot,
						'duration': int(length)
					}
					menu = self.create_ctx_menu()
					menu.add_menu_item(self._('Remove from watched'), cmd=self.remove_watched_item, video_id=video_id)
					menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)
					self.add_subtitles_menu(menu, title, video_id)
					self.add_video(title, "https://i.ytimg.com/vi/" + video_id + "/maxresdefault.jpg", info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)
		else:
			popular = None
			latest = None
			oldest = None
			data = self.call_api(endpoint, params)
			if "continuation" not in params:
				tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
				for idx, tab in enumerate(tabs):
					if len(tabs[idx].get("tabRenderer", {}).get("content", {}).get("richGridRenderer", {}).get("contents", [])) > 0:
						break
				if len(tabs) > 0:
					contents = (
						tabs[idx]
						.get("tabRenderer", {})
						.get("content", {})
						.get("richGridRenderer", {})
						.get("header", {})
						.get("feedFilterChipBarRenderer", {})
						.get("contents", [])
					)
					for block in contents:
						if block.get("chipCloudChipRenderer", {}).get("text", {}).get("simpleText", "") == "Latest":
							latest = block.get("chipCloudChipRenderer", {}).get("navigationEndpoint", {}).get("continuationCommand", {}).get("token", "")
						if block.get("chipCloudChipRenderer", {}).get("text", {}).get("simpleText", "") == "Popular":
							popular = block.get("chipCloudChipRenderer", {}).get("navigationEndpoint", {}).get("continuationCommand", {}).get("token", "")
						if block.get("chipCloudChipRenderer", {}).get("text", {}).get("simpleText", "") == "Oldest":
							oldest = block.get("chipCloudChipRenderer", {}).get("navigationEndpoint", {}).get("continuationCommand", {}).get("token", "")

			if "onResponseReceivedActions" in data and len(data["onResponseReceivedActions"]) > 1:
				contents = (
					data
					.get("onResponseReceivedActions")[1]
					.get("reloadContinuationItemsCommand", {})
					.get("continuationItems", [])
				)
				contItems = data.get("onResponseReceivedActions")[1].get("reloadContinuationItemsCommand", {}).get("continuationItems", [])
			elif "onResponseReceivedActions" in data and len(data["onResponseReceivedActions"]) > 0:
				contents = (
					data
					.get("onResponseReceivedActions")[0]
					.get("appendContinuationItemsAction", {})
					.get("continuationItems", [])
				)
			elif "onResponseReceivedCommands" in data and len(data["onResponseReceivedCommands"]) > 0:
				contents = (
					data
					.get("onResponseReceivedCommands")[0]
					.get("appendContinuationItemsAction", {})
					.get("continuationItems", [{}])[0]
					.get("itemSectionRenderer", {})
					.get("contents", [])
				)
				contItems = data.get("onResponseReceivedCommands")[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
			elif endpoint == "browse":
				tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
				for idx, tab in enumerate(tabs):
					if len(tabs[idx].get("tabRenderer", {}).get("content", {}).get("richGridRenderer", {}).get("contents", [])) > 0:
						break
				contents = (
					tabs[idx]
					.get("tabRenderer", {})
					.get("content", {})
					.get("richGridRenderer", {})
					.get("contents", [])
				)
				if params.get("params", "") != "EgZ2aWRlb3PyBgQKAjoA":
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":params["browseId"],"params":"EgZ2aWRlb3PyBgQKAjoA"}
					self.add_dir(self._("Videos"), cmd=self.list_videos, endpoint='browse', params=channel_params)
				if params.get("params", "") != "EgZzaG9ydHPyBgUKA5oBAA%3D%3D":
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":params["browseId"],"params":"EgZzaG9ydHPyBgUKA5oBAA%3D%3D"}
					self.add_dir(self._("Shorts"), cmd=self.list_videos, endpoint='browse', params=channel_params)
				if params.get("params", "") != "EgdzdHJlYW1z8gYECgJ6AA%3D%3D":
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":params["browseId"],"params":"EgdzdHJlYW1z8gYECgJ6AA%3D%3D"}
					self.add_dir(self._("Live"), cmd=self.list_videos, endpoint='browse', params=channel_params)
				if popular:
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"continuation":popular}
					self.add_dir(self._("Popular"), cmd=self.list_videos, endpoint='browse', params=channel_params)
				if oldest:
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"continuation":oldest}
					self.add_dir(self._("Oldest"), cmd=self.list_videos, endpoint='browse', params=channel_params)
			elif endpoint == "search":
				contents = (
					data
					.get("contents", {})
					.get("twoColumnSearchResultsRenderer", {})
					.get("primaryContents", {})
					.get("sectionListRenderer", {})
					.get("contents", [{}])[0]
					.get("itemSectionRenderer", {})
					.get("contents", [])
				)
			else:
				return None

			for block in contents:
				### special for Shorts
				if "richItemRenderer" in block and "content" in block["richItemRenderer"] and "shortsLockupViewModel" in block["richItemRenderer"]["content"]:
					title = block["richItemRenderer"]["content"]["shortsLockupViewModel"].get("accessibilityText", "")
					video_id = block["richItemRenderer"]["content"]["shortsLockupViewModel"].get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}).get("videoId", "N/A")
					channel_title = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("title", "N/A")
					channel_id = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId", "")
					info_labels = {}
					menu = self.create_ctx_menu()
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":channel_id,"params":"EgZ2aWRlb3PyBgQKAjoA"}
					menu.add_menu_item(self._('View channel videos'), cmd=self.list_videos, endpoint='browse', params=channel_params)
					menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)
					self.add_subtitles_menu(menu, title, video_id)
					self.add_video(title, "https://i.ytimg.com/vi/" + video_id + "/maxresdefault.jpg", info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)
					continue
				elif "richItemRenderer" in block and "content" in block["richItemRenderer"] and "lockupViewModel" in block["richItemRenderer"]["content"]:
					one = block["richItemRenderer"]["content"]["lockupViewModel"]
				elif "videoRenderer" in block:
					one = block["videoRenderer"]
				elif "continuationItemRenderer" in block:
					cont = block.get("continuationItemRenderer").get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", None)
					continue
				elif "channelRenderer" in block:
					self.add_channel_dir(block["channelRenderer"])
					continue
				else:
					continue

				if endpoint == "search":
					video_id = one.get("videoId", "N/A")
					title = one.get("title", {}).get("runs",[{}])[0].get("text","N/A")
					channel_title = data.get("header", {}).get("pageHeaderRenderer", {}).get("pageTitle", one.get("longBylineText", {}).get("runs", [{}])[0].get("text", "N/A"))
					channel_id = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId", one.get("longBylineText", {}).get("runs", [{}])[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", ""))
					published = one.get("publishedTimeText", {}).get("simpleText", "")
					duration = one.get("lengthText", {}).get("simpleText", "")
					views = re.sub(r"\D", "", one.get("viewCountText", {}).get("simpleText", "N/A"))
					is_live = 1 if one.get("thumbnailOverlays", [{}])[0].get("thumbnailOverlayTimeStatusRenderer", {}).get("style", None) == "LIVE" else 0
				else:
					video_id = one.get("contentId", "N/A")
					title = one.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "N/A")
					channel_title = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("title", data.get("header", {}).get("pageHeaderRenderer", {}).get("pageTitle", "N/A"))
					channel_id = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId", "N/A")
					duration = one.get("contentImage", {}).get("thumbnailViewModel", {}).get("overlays", [{}])[0].get("thumbnailBottomOverlayViewModel", {}).get("badges", [{}])[0].get("thumbnailBadgeViewModel", {}).get("text", "0")
					views = one.get("metadata", {}).get("lockupMetadataViewModel", {}).get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [{}])[0].get("metadataParts", [{},{}])[0].get("text", {}).get("content", "N/A")
					try:
						published = one.get("metadata", {}).get("lockupMetadataViewModel", {}).get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [{}])[0].get("metadataParts", [{},{}])[1].get("text", {}).get("content", "N/A")
					except (KeyError, IndexError, TypeError):
						published = "N/A"
					is_live = 1 if duration == "LIVE" else 0
				upcoming = int(one.get("upcomingEventData", {}).get("startTime", 0))
				if is_live == 0: # special for Search
					is_live = 1 if one.get("badges", [{}])[0].get("metadataBadgeRenderer", {}).get("label", None) == "LIVE" else 0
				if upcoming > 0:
					published = datetime.fromtimestamp(upcoming).strftime("%d.%m.%Y %H:%M:%S")
					title = _C('red', "- " + title)
				elif is_live == 1:
					title = _C('green', "* " + title)
				plot = '{} [{}] {} ({}x)\n{}'.format(
					published,
					channel_title,
					duration,
					"",
					views
				)
				info_labels = {
					'plot': plot,
					'duration': self.to_seconds(duration)
				}
				menu = self.create_ctx_menu()
				channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":channel_id,"params":"EgZ2aWRlb3PyBgQKAjoA"}
				menu.add_menu_item(self._('View channel videos'), cmd=self.list_videos, endpoint='browse', params=channel_params)
				menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)
				self.add_subtitles_menu(menu, title, video_id)
				self.add_video(title, "https://i.ytimg.com/vi/" + video_id + "/maxresdefault.jpg", info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)

			if not cont:
				tabs = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
				if len(tabs) > 1:
					cont = tabs[1].get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", None)

			if not cont and len(contItems) > 1:
				cont = contItems[1].get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", None)

			if cont:
				params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"continuation":cont}
				self.add_next(cmd=self.list_videos, endpoint=endpoint, params=params)

	# ##################################################################################################################

	def channels_file(self):
		return os.path.join(self.data_dir, "channels.txt")

	# ##################################################################################################################

	def read_channels(self):
		''' Returns list of saved channels [(name, channel_id), ...] without duplicates '''
		channels = []
		try:
			with io.open(self.channels_file(), "r", encoding="utf-8") as file:
				for line in file:
					line = line.strip()
					if ';' not in line:
						continue
					name, channel_id = line.rsplit(";", 1)
					if channel_id and channel_id not in [c[1] for c in channels]:
						channels.append((name, channel_id))
		except IOError:
			pass
		return channels

	# ##################################################################################################################

	def write_channels(self, channels):
		try:
			with io.open(self.channels_file(), "w", encoding="utf-8") as file:
				for name, channel_id in channels:
					file.write(u'%s;%s\n' % (name.replace('\n', ' '), channel_id))
		except:
			self.log_exception()

	# ##################################################################################################################

	def channel_params(self, channel_id):
		return {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":channel_id,"params":CHANNEL_VIDEOS_PARAMS}

	# ##################################################################################################################

	def save_channel(self,channel_name,channel_id):
		max_history = int(self.get_setting('channels') or 20)
		# newly saved channel goes to the top, already saved channel is only moved to the top
		channels = [(channel_name, channel_id)] + [c for c in self.read_channels() if c[1] != channel_id]
		self.write_channels(channels[:max(max_history, 1)])
		self.refresh_screen()

	# ##################################################################################################################

	def remove_channel(self, channel_id):
		self.write_channels([c for c in self.read_channels() if c[1] != channel_id])
		self.refresh_screen()

	# ##################################################################################################################

	def add_channel_dir(self, renderer):
		''' Channel found by search - opens channel videos (sorted from the newest) '''
		channel_id = renderer.get("channelId")
		if not channel_id:
			return
		name = renderer.get("title", {}).get("simpleText", "") or channel_id
		try:
			img = renderer["thumbnail"]["thumbnails"][-1]["url"]
			if img.startswith('//'):
				img = 'https:' + img
		except (KeyError, IndexError, TypeError):
			img = None
		info = []
		for key in ("subscriberCountText", "videoCountText"):
			text = renderer.get(key, {}).get("simpleText")
			if text:
				info.append(text)
		desc = ''.join(r.get("text", "") for r in renderer.get("descriptionSnippet", {}).get("runs", []))
		menu = self.create_ctx_menu()
		menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=name, channel_id=channel_id)
		self.add_dir(_B(self._("Channel") + ": " + name), img, {'plot': ' | '.join(info) + '\n' + decode_html(desc)}, menu=menu, cmd=self.list_videos, endpoint='browse', params=self.channel_params(channel_id))

	# ##################################################################################################################

	def load_channels(self):
		for name, channel_id in self.read_channels():
			menu = self.create_ctx_menu()
			menu.add_menu_item(self._('Remove channel'), cmd=self.remove_channel, channel_id=channel_id)
			self.add_dir(name, menu=menu, cmd=self.list_videos, endpoint='browse', params=self.channel_params(channel_id))

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
			params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"query":keyword}
			self.list_videos('search', params)

	# ##################################################################################################################

	def add_subtitles_menu(self, menu, title, video_id):
		menu.add_media_menu_item(self._('Play with subtitles') + ' (%s)' % self.get_subtitles_lang().upper(), cmd=self.resolve_video, video_title=title, video_id=video_id, subtitles='lang')
		menu.add_media_menu_item(self._('Play with subtitles in original language'), cmd=self.resolve_video, video_title=title, video_id=video_id, subtitles='orig')
		menu.add_media_menu_item(self._('Play without subtitles'), cmd=self.resolve_video, video_title=title, video_id=video_id, subtitles='off')

	# ##################################################################################################################

	def get_subtitles_lang(self):
		lang = self.get_setting('subtitles_lang')
		if not lang or lang == 'auto':
			lang = self.get_lang_code() or 'en'
		return lang.split('_')[0].lower()

	# ##################################################################################################################

	def subtitles_file(self, video_id, name):
		return os.path.join(self.SUBTITLES_DIR, 'youtube_%s_%s.srt' % (video_id, name))

	# ##################################################################################################################

	@staticmethod
	def cached_subtitles(filename):
		try:
			if os.path.getsize(filename) > 0:
				return filename
		except OSError:
			pass
		return None

	# ##################################################################################################################

	def retry_translated_subtitles(self, video_id, url, filename):
		''' Tries to download translated subtitles again in background - they will be used on next playback of the video '''
		import threading
		from time import sleep

		if video_id in self.subtitles_retry:
			return

		def retry():
			try:
				for delay in self.SUBTITLES_RETRY_DELAYS:
					sleep(delay)
					try:
						tmp_filename = filename + '.part'
						if download_srt(self.req_session, url, tmp_filename, note=self.translation_note(), note_duration=4):
							os.rename(tmp_filename, filename)
							self.log_info("Translated subtitles for %s downloaded on next attempt" % video_id)
							return
					except Exception as e:
						self.log_debug("Translated subtitles for %s still not available: %s" % (video_id, str(e)))
			finally:
				self.subtitles_retry.discard(video_id)

		self.subtitles_retry.add(video_id)
		t = threading.Thread(target=retry)
		t.daemon = True
		t.start()

	# ##################################################################################################################

	def translation_note(self):
		return '(' + self._('machine translation by YouTube') + ')'

	# ##################################################################################################################

	def fallback_note(self):
		return self._('YouTube refused machine translation of subtitles, subtitles are shown in the original language.') + '\n' + \
			self._('You can try to play the video again later.')

	# ##################################################################################################################

	def get_subtitles(self, video_id, captions, mode):
		if not mode or mode == 'off':
			return None
		try:
			lang = self.get_subtitles_lang()
			caption_tracks = captions.get('tracks')
			orig_lang = captions.get('orig_lang')
			url, desc = choose_track_url(caption_tracks, mode, lang, self.get_setting('subtitles_translate') == True, orig_lang)
			if not url and mode == 'lang':
				# no subtitles in subtitles language and machine translation is disabled - original language is better than nothing
				mode = 'orig'
				url, desc = choose_track_url(caption_tracks, mode, orig_lang=orig_lang)
			self.log_debug("Subtitles for %s (%s): %s" % (video_id, mode, desc))
			if not url:
				return None

			filename = self.subtitles_file(video_id, lang if mode == 'lang' else 'orig')
			# already downloaded subtitles are used again without asking YouTube
			if self.cached_subtitles(filename):
				return filename

			translated = '&tlang=' in url
			try:
				return download_srt(self.req_session, url, filename, note=self.translation_note() if translated else None, note_duration=4)
			except Exception as e:
				if not translated:
					raise
				# YouTube often refuses automatically translated subtitles outside of web browser (HTTP 429),
				# so use subtitles in original language of the video now and try the translation again in background
				self.log_error("Translated subtitles for %s not available (%s) - using original language" % (video_id, str(e)))
				self.retry_translated_subtitles(video_id, url, filename)
				orig_url, desc = choose_track_url(caption_tracks, 'orig', orig_lang=orig_lang)
				if not orig_url:
					return None
				# original subtitles with explanation shown at the start of the video
				return download_srt(self.req_session, orig_url, self.subtitles_file(video_id, lang + '_orig'), note=self.fallback_note())
		except Exception:
			# subtitles must never break playback
			self.log_exception()
		return None

		# ##################################################################################################################

	def resolve_video(self, video_title, video_id, subtitles=None):
		try:
			url, captions = yt_resolve(video_id, self.settings, with_captions=True)
		except Exception as e:
			self.log_exception()
			raise AddonErrorException(self._("Failed to get playable video stream address") + ':\n%s' % str(e))

		subs = self.get_subtitles(video_id, captions or {}, subtitles or self.get_setting('subtitles'))
		self.add_play(video_title, url, subs=subs)
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
