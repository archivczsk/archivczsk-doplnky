# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.player.features import PlayerFeatures
from time import time
from datetime import timedelta
from datetime import datetime
from dateutil import parser as duparser
from base64 import b64decode
import re, os, json, requests
from .youtube import resolve as yt_resolve

class YoutubeContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None):
		CommonContentProvider.__init__(self, 'Youtube', settings=settings, data_dir=data_dir)
		self.watched = self.load_cached_data('watched')
		self.req_session = self.get_requests_session()
		self.max_results = 50
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
		parts = map(int, time_str.split(":"))
		total = 0
		for p in parts:
			total = total * 60 + p
		return total

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
						duparser.isoparse(published).strftime("%-d.%-m.%Y %H:%M"),
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
					.get("contents", [])[0]
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
					self.add_video(title, "https://i.ytimg.com/vi/" + video_id + "/maxresdefault.jpg", info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)
					continue
				elif "richItemRenderer" in block and "content" in block["richItemRenderer"] and "videoRenderer" in block["richItemRenderer"]["content"]:
					one = block["richItemRenderer"]["content"]["videoRenderer"]
				elif "videoRenderer" in block:
					one = block["videoRenderer"]
				elif "continuationItemRenderer" in block:
					cont = block.get("continuationItemRenderer").get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", None)
					continue
				else:
					continue
				video_id = one.get("videoId", "N/A")
				title = one.get("title", {}).get("runs",[{}])[0].get("text","N/A")
				channel_title = data.get("header", {}).get("pageHeaderRenderer", {}).get("pageTitle", one.get("longBylineText", {}).get("runs", [{}])[0].get("text", "N/A"))
				channel_id = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId", one.get("longBylineText", {}).get("runs", [{}])[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", ""))
				published = one.get("publishedTimeText", {}).get("simpleText", "")
				is_live = 1 if one.get("thumbnailOverlays", [{}])[0].get("thumbnailOverlayTimeStatusRenderer", {}).get("style", None) == "LIVE" else 0
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
					one.get("lengthText", {}).get("simpleText", ""),
					re.sub(r"\D", "", one.get("viewCountText", {}).get("simpleText", "N/A")),
					decode_html(one.get("descriptionSnippet", {}).get("runs",[{}])[0].get("text",""))
				)
				info_labels = {
					'plot': plot,
					'duration': self.to_seconds(one.get("lengthText", {}).get("simpleText", "0"))
				}
				menu = self.create_ctx_menu()
				channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":channel_id,"params":"EgZ2aWRlb3PyBgQKAjoA"}
				menu.add_menu_item(self._('View channel videos'), cmd=self.list_videos, endpoint='browse', params=channel_params)
				menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)
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
					channel_params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"browseId":item[1],"params":"EgZ2aWRlb3PyBgQKAjoA"}
					self.add_dir(item[0], cmd=self.list_videos, endpoint='browse', params=channel_params)
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
			params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"query":keyword}
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
