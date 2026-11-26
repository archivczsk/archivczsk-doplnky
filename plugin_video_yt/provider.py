# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.string_utils import _I, _C, _B, decode_html
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from time import time
from datetime import timedelta, datetime
from base64 import b64decode
import re, os, io, json, shutil, requests, threading
from .youtube import resolve as yt_resolve
from .youtube.captions import choose_track_url, download_srt

CHANNEL_VIDEOS_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"
FEED_CACHE_TIME = 600
SUBSCRIPTIONS_DIR = '/tmp'
CHANNEL_ID_RE = re.compile(r'(UC[\w-]{22})')
# lock protecting watched.json - it is a module level object on purpose: the provider instance must stay copyable (copy.deepcopy), what instance attribute with a lock is not
FILE_LOCK = threading.RLock()

# ##################################################################################################################

def dig(obj, *path, **kw):
	"""
	Safe walk through nested dicts/lists returned by youtube API. Returns kw['default'] (None if not set), when any part of the path is missing.
	"""
	for p in path:
		try:
			obj = obj[p]
		except (KeyError, IndexError, TypeError):
			return kw.get('default')

	return obj

# ##################################################################################################################

def yt_text(obj):
	"""
	Converts youtube text object ({'simpleText': ..} / {'runs': [..]} / {'content': ..}) to plain text
	"""
	if isinstance(obj, dict):
		if 'simpleText' in obj:
			return obj['simpleText'] or u''
		if 'runs' in obj:
			return u''.join([r.get('text', u'') for r in obj['runs'] if isinstance(r, dict)])
		return obj.get('content') or u''

	return obj or u''

# ##################################################################################################################

class YoutubeContentProvider(CommonContentProvider):
	DETAILS_THREADS = 6        # number of parallel requests used to load video details
	DETAILS_CACHE_MAX = 500    # max number of cached video details
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
		self.feed_cache = (0, None, [])
		self.details_cache = {}
		self.channels_invalid = False
		self.migrate_channels()

	# ##################################################################################################################

	def root(self):
		self.add_search_dir()
		self.add_dir(self._("Last watched"), cmd=self.list_watched)
		if self.read_channels():
			self.add_dir(self._("New videos from saved channels"), cmd=self.list_channels_feed)
		subscriptions_file = self.find_subscriptions_file()
		if subscriptions_file:
			self.add_dir(self._("Import subscriptions") + ' (%s)' % subscriptions_file, info_labels={'plot': self._("Subscriptions exported from Google Takeout (YouTube) found. Channels will be added to saved channels.")}, cmd=self.import_subscriptions, filename=subscriptions_file)
		self.load_channels()

	# ##################################################################################################################

	def list_watched(self):
		ids = [i[0] for i in sorted(self.watched.items(), key=lambda i: i[1].get('time', 0), reverse=True)]

		self.list_watched_items(ids)

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

	def call_api(self, endpoint, params={}, timeout=None):
		while True:
			api_key = self.get_api_key()
			if not api_key:
				raise AddonErrorException(self._("This addon reached available limit of requests to youtube API. Try again later."))

			try:
				response = requests.post("https://www.youtube.com/youtubei/v1/" + endpoint + "?key=" + api_key, json=params, timeout=timeout)
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
			self.list_watched_items(ids)
		else:
			pending = []   # items found on this page - they are added at once after parsing, so video details can be loaded in parallel
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
					pending.append(dict(title=title, video_id=video_id, plot='', duration=None, channel_title=channel_title, channel_id=channel_id))
					continue
				elif "richItemRenderer" in block and "content" in block["richItemRenderer"] and "lockupViewModel" in block["richItemRenderer"]["content"]:
					one = block["richItemRenderer"]["content"]["lockupViewModel"]
				elif "videoRenderer" in block:
					one = block["videoRenderer"]
				elif "continuationItemRenderer" in block:
					cont = block.get("continuationItemRenderer").get("continuationEndpoint", {}).get("continuationCommand", {}).get("token", None)
					continue
				elif "channelRenderer" in block:
					pending.append({"channel_renderer": block["channelRenderer"]})
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
				pending.append(dict(title=title, video_id=video_id, plot=plot, duration=self.to_seconds(duration), channel_title=channel_title, channel_id=channel_id))

			self.add_list_items(pending)

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

	def write_json_file(self, filename, data, indent=2):
		''' Writes human readable (and easily editable) UTF-8 JSON file. File is written to temporary file first, so it can't be left half written '''
		text = json.dumps(data, ensure_ascii=False, indent=indent, separators=(',', ': '))
		if isinstance(text, bytes):
			text = text.decode('utf-8')

		tmp_filename = filename + '.tmp'
		with io.open(tmp_filename, "w", encoding="utf-8") as file:
			file.write(text + u'\n')

		os.rename(tmp_filename, filename)

	# ##################################################################################################################

	def channels_file(self):
		return os.path.join(self.data_dir, "channels.json")

	# ##################################################################################################################

	def legacy_channels_file(self):
		return os.path.join(self.data_dir, "channels.txt")

	# ##################################################################################################################

	def read_channels(self):
		'''
		Returns list of saved channels [(name, channel_id), ...] without duplicates.
		Format of channels.json: [{"name": "Channel name", "id": "UC..."}, ...]
		'''
		channels = []
		try:
			with io.open(self.channels_file(), "r", encoding="utf-8") as file:
				data = json.load(file)
		except (IOError, OSError):
			# file doesn't exist yet
			return channels
		except ValueError:
			# broken file (for example mistake done during manual editing) - it will be backed up before the next write
			self.log_exception()
			self.channels_invalid = True
			return channels

		if not isinstance(data, list):
			self.log_error("Unsupported content of %s - list of channels expected" % self.channels_file())
			self.channels_invalid = True
			return channels

		self.channels_invalid = False

		for item in data:
			if not isinstance(item, dict) or not item.get('id'):
				continue

			channel_id = item['id']
			if channel_id not in [c[1] for c in channels]:
				channels.append((item.get('name') or channel_id, channel_id))

		return channels

	# ##################################################################################################################

	def write_channels(self, channels):
		''' Saves list of channels [(name, channel_id), ...] to channels.json. Returns True on success '''
		try:
			if self.channels_invalid and os.path.isfile(self.channels_file()):
				# don't lose manually edited file, that we were not able to read
				shutil.copyfile(self.channels_file(), self.channels_file() + '.bak')
				self.channels_invalid = False

			self.write_json_file(self.channels_file(), [{'name': name, 'id': channel_id} for name, channel_id in channels])
			return True
		except Exception:
			self.log_exception()
			return False

	# ##################################################################################################################

	def migrate_channels(self):
		''' Converts channels.txt saved by older versions to channels.json (only when channels.json doesn't exist yet) and removes channels.txt '''
		txt_file = self.legacy_channels_file()

		try:
			if not os.path.isfile(txt_file) or os.path.exists(self.channels_file()):
				return

			channels = []
			with io.open(txt_file, "r", encoding="utf-8") as file:
				for line in file:
					line = line.strip()
					if ';' not in line:
						continue
					name, channel_id = line.rsplit(";", 1)
					channel_id = channel_id.strip()
					if channel_id and channel_id not in [c[1] for c in channels]:
						channels.append((name, channel_id))

			# txt file is removed only when the new file was written and can be read back
			if self.write_channels(channels) and len(self.read_channels()) == len(channels):
				os.remove(txt_file)
				self.log_info("Saved channels converted from channels.txt to channels.json (%d channels)" % len(channels))
		except Exception:
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

	def refresh_root(self):
		# refresh_screen() called from the root screen leaves the loading spinner running forever (ArchivCZSK core calls get_content() of the root item
		# with wrong arguments), so the new root content is returned directly and the screen is only told to replace its list
		self.root()
		self.update_content()

	# ##################################################################################################################

	def remove_channel(self, channel_id):
		self.write_channels([c for c in self.read_channels() if c[1] != channel_id])
		self.refresh_root()

	# ##################################################################################################################

	def fetch_channel_feed(self, name, channel_id):
		''' Latest videos of the channel from RSS feed - exact publish date, no API key needed '''
		entries = []
		r = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id, timeout=10)
		r.raise_for_status()
		r.encoding = 'utf-8'
		for entry in re.findall(r'<entry>(.*?)</entry>', r.text, re.S):
			video_id = re.search(r'<yt:videoId>([^<]+)</yt:videoId>', entry)
			link = re.search(r'<link rel="alternate" href="([^"]+)"', entry)
			if not video_id or (link and '/shorts/' in link.group(1)):
				continue
			title = re.search(r'<title>(.*?)</title>', entry, re.S)
			published = re.search(r'<published>([^<]+)</published>', entry)
			views = re.search(r'<media:statistics views="(\d+)"', entry)
			desc = re.search(r'<media:description>(.*?)</media:description>', entry, re.S)
			entries.append({
				'id': video_id.group(1),
				'title': decode_html(title.group(1)) if title else 'N/A',
				'published': published.group(1) if published else '',
				'views': views.group(1) if views else '',
				'desc': decode_html(desc.group(1)) if desc else '',
				'channel': name,
				'channel_id': channel_id,
			})
		return entries

	# ##################################################################################################################

	def get_channels_feed(self, channels):
		cache_time, cache_key, entries = self.feed_cache
		key = ','.join(c[1] for c in channels)
		if cache_key == key and time() - cache_time < FEED_CACHE_TIME:
			return entries

		entries = []
		lock = threading.Lock()

		def fetch(name, channel_id):
			try:
				result = self.fetch_channel_feed(name, channel_id)
				with lock:
					entries.extend(result)
			except Exception:
				self.log_exception()

		threads = []
		for name, channel_id in channels:
			t = threading.Thread(target=fetch, args=(name, channel_id))
			t.daemon = True
			t.start()
			threads.append(t)
			if len(threads) >= 8:
				threads.pop(0).join()
		for t in threads:
			t.join()

		entries = sorted(entries, key=lambda e: e['published'], reverse=True)[:100]
		self.feed_cache = (time(), key, entries)
		return entries

	# ##################################################################################################################

	def list_channels_feed(self):
		for e in self.get_channels_feed(self.read_channels()):
			plot = u'{} [{}] ({}x)\n{}'.format(self.iso_to_cet(e['published']), e['channel'], e['views'], e['desc'])
			self.add_video_item(e['title'], e['id'], plot, None, e['channel'], e['channel_id'], save_channel=False)

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

	@staticmethod
	def parse_subscriptions_line(line):
		'''
		Line of subscriptions CSV from Google Takeout: Channel Id,Channel Url,Channel Title
		Header and file name are localised by Google (subscriptions.csv, odběry.csv, ...), so only the content is checked.
		Returns (name, channel_id) or None
		'''
		parts = line.strip().split(',', 2)
		if len(parts) < 3:
			return None
		m = CHANNEL_ID_RE.match(parts[0].strip().strip('"'))
		if not m or 'youtube.com' not in parts[1]:
			return None
		name = parts[2].strip()
		if len(name) > 1 and name.startswith('"') and name.endswith('"'):
			name = name[1:-1].replace('""', '"')
		return (name or m.group(1), m.group(1))

	# ##################################################################################################################

	def find_subscriptions_file(self):
		''' Newest CSV file in /tmp that contains YouTube subscriptions '''
		found = []
		try:
			names = os.listdir(SUBSCRIPTIONS_DIR)
		except OSError:
			return None
		for name in names:
			if not name.lower().endswith('.csv'):
				continue
			filename = os.path.join(SUBSCRIPTIONS_DIR, name)
			try:
				if os.path.getsize(filename) > 5 * 1024 * 1024:
					continue
				with io.open(filename, "r", encoding="utf-8-sig", errors="ignore") as file:
					head = [file.readline() for _ in range(3)]
				if any(self.parse_subscriptions_line(line) for line in head):
					found.append((os.path.getmtime(filename), filename))
			except (OSError, IOError):
				continue
		return sorted(found)[-1][1] if found else None

	# ##################################################################################################################

	def import_subscriptions(self, filename):
		imported = []
		try:
			with io.open(filename, "r", encoding="utf-8-sig") as file:
				for line in file:
					item = self.parse_subscriptions_line(line)
					if item:
						imported.append(item)
		except Exception as e:
			self.log_exception()
			raise AddonErrorException(self._("Failed to read subscriptions file") + ':\n%s' % str(e))

		existing = self.read_channels()
		known = [c[1] for c in existing]
		new = []
		for item in sorted(imported, key=lambda c: c[0].lower()):
			if item[1] not in known:
				known.append(item[1])
				new.append(item)
		channels = existing + new
		if len(channels) > int(self.get_setting('channels') or 20):
			self.set_setting('channels', len(channels))
		self.write_channels(channels)
		self.show_info(self._("Imported channels") + ': %d' % len(new), noexit=True)
		self.refresh_root()

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

	def save_watched(self):
		with FILE_LOCK:
			try:
				self.write_json_file(os.path.join(self.data_dir, 'watched.json'), self.watched, indent=1)
			except Exception:
				self.log_exception()

	# ##################################################################################################################

	@staticmethod
	def has_details(item):
		''' True if watched item already holds all data needed to display it (older versions saved only the time) '''
		return isinstance(item, dict) and 'title' in item and 'desc' in item

	# ##################################################################################################################

	def add_watched_item(self, video_id):
		with FILE_LOCK:
			entry = self.watched.get(video_id)
			if not isinstance(entry, dict):
				entry = {}

			# already known details of the video are kept
			entry['time'] = int(time())
			self.watched[video_id] = entry

			max_watched = int(self.get_setting('max_watched'))

			if len(self.watched) > max_watched:
				for k,_ in sorted(self.watched.items(), key=lambda i: i[1].get('time', 0), reverse=True)[max_watched:]:
					del self.watched[k]

			self.save_watched()
			need_details = video_id in self.watched and not self.has_details(entry)

		if need_details:
			# details (title, description, ...) are loaded in background, so they don't delay the playback
			t = threading.Thread(target=self.update_watched_details, args=(video_id,))
			t.daemon = True
			t.start()

	# ##################################################################################################################

	def update_watched_details(self, video_id):
		try:
			details = self.load_details([video_id]).get(video_id)
			if details:
				with FILE_LOCK:
					# video could be removed from watched in the meantime
					if video_id in self.watched:
						self.watched[video_id].update(details)
						self.save_watched()
		except Exception:
			self.log_exception()

	# ##################################################################################################################

	def remove_watched_item(self, video_id):
		with FILE_LOCK:
			if video_id in self.watched:
				del self.watched[video_id]

			self.save_watched()

		self.refresh_screen()

	# ##################################################################################################################

	def list_watched_items(self, ids):
		''' Lists watched videos. All data are taken from watched.json - only videos saved by older version (without details) are loaded from internet and saved (once). '''
		missing = [video_id for video_id in ids if not self.has_details(self.watched.get(video_id))]
		if missing:
			details = self.load_details(missing)
			with FILE_LOCK:
				for video_id, d in details.items():
					if video_id in self.watched:
						self.watched[video_id].update(d)

				if details:
					self.save_watched()

		for video_id in ids:
			item = self.watched.get(video_id)
			if not self.has_details(item):
				continue

			try:
				duration = int(item.get('duration') or 0)
			except (TypeError, ValueError):
				duration = 0

			plot = u'{} [{}] {} ({}x)\n{}'.format(
				self.iso_to_cet(item.get('published')),
				item.get('channel') or u'N/A',
				self.format_time(duration),
				item.get('views') or 0,
				decode_html(item.get('desc') or u'')
			)
			self.add_video_item(item['title'], video_id, plot, duration, item.get('channel') or u'N/A', item.get('channel_id') or u'', watched=True)

	# ##################################################################################################################

	def is_desc_enabled(self):
		val = self.get_setting('video_desc')
		return val is None or val is True or str(val).lower() == 'true'

	# ##################################################################################################################

	def fetch_video_details(self, video_id):
		''' Loads details of the video from youtube. Returns dictionary, that is also saved to watched.json, or None if video is not available '''
		params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"videoId":video_id}
		data = self.call_api("player", params, timeout=15)

		video_details = data.get("videoDetails")
		if not video_details:
			return None

		microformat = dig(data, "microformat", "playerMicroformatRenderer", default={})

		try:
			duration = int(video_details.get("lengthSeconds") or 0)
		except (TypeError, ValueError):
			duration = 0

		return {
			'title': video_details.get("title") or u'N/A',
			'channel': microformat.get("ownerChannelName") or video_details.get("author") or u'N/A',
			'channel_id': video_details.get("channelId") or u'',
			'duration': duration,
			'published': microformat.get("publishDate") or u'',
			'views': video_details.get("viewCount") or u'0',
			'desc': video_details.get("shortDescription") or u'',
		}

	# ##################################################################################################################

	def load_details(self, video_ids):
		'''
		Loads details of videos (using more parallel requests) and returns them as dictionary video_id -> details.
		Videos, that can't be loaded, are missing in the result.
		'''
		result = {}
		todo = []

		for video_id in video_ids:
			if video_id in self.details_cache:
				result[video_id] = self.details_cache[video_id]
			elif video_id not in todo:
				todo.append(video_id)

		if not todo:
			return result

		fetched = {}

		def worker(ids):
			for video_id in ids:
				try:
					details = self.fetch_video_details(video_id)
				except Exception:
					# details are only a bonus - they must never break listing of videos
					self.log_error("Failed to load details of video %s" % video_id)
					continue

				if details:
					fetched[video_id] = details

		threads_cnt = min(self.DETAILS_THREADS, len(todo))
		threads = []
		for i in range(threads_cnt):
			t = threading.Thread(target=worker, args=(todo[i::threads_cnt],))
			t.daemon = True
			t.start()
			threads.append(t)

		for t in threads:
			t.join()

		if len(self.details_cache) + len(fetched) > self.DETAILS_CACHE_MAX:
			self.details_cache.clear()

		self.details_cache.update(fetched)
		result.update(fetched)
		return result

	# ##################################################################################################################

	def create_video_menu(self, title, video_id, channel_title, channel_id, watched=False, save_channel=True):
		menu = self.create_ctx_menu()
		channel_known = bool(channel_id) and channel_id != 'N/A'

		if watched:
			menu.add_menu_item(self._('Remove from watched'), cmd=self.remove_watched_item, video_id=video_id)
		elif channel_known:
			menu.add_menu_item(self._('View channel videos'), cmd=self.list_videos, endpoint='browse', params=self.channel_params(channel_id))

		if channel_known and save_channel:
			menu.add_menu_item(self._('Save channel'), cmd=self.save_channel, channel_name=channel_title, channel_id=channel_id)

		menu.add_menu_item(self._('Related videos'), cmd=self.list_related, video_id=video_id)
		menu.add_menu_item(self._('Comments'), cmd=self.list_comments, video_id=video_id)
		self.add_subtitles_menu(menu, title, video_id)
		return menu

	# ##################################################################################################################

	def add_video_item(self, title, video_id, plot, duration, channel_title, channel_id, desc=None, watched=False, save_channel=True):
		''' Adds one video to the list. Info button shows plot, so full description of the video (desc) is appended to it. '''
		if desc:
			plot = u'{}\n\n{}'.format(plot, desc) if plot else desc

		info_labels = {}
		if plot:
			info_labels['plot'] = plot
		if duration is not None:
			info_labels['duration'] = duration

		menu = self.create_video_menu(title, video_id, channel_title, channel_id, watched, save_channel)
		self.add_video(title, "https://i.ytimg.com/vi/" + video_id + "/maxresdefault.jpg", info_labels, menu=menu, cmd=self.resolve_video, video_title=title, video_id=video_id)

	# ##################################################################################################################

	def add_list_items(self, entries):
		'''
		Adds items found on one page (in the same order as they were found): videos (dictionaries with arguments of add_video_item())
		and channels ({'channel_renderer': ..}). Descriptions of all videos are loaded at once.
		'''
		details = {}
		if self.is_desc_enabled():
			video_ids = [e['video_id'] for e in entries if e.get('video_id') and e['video_id'] != 'N/A']
			if video_ids:
				details = self.load_details(video_ids)

		for e in entries:
			if 'channel_renderer' in e:
				self.add_channel_dir(e['channel_renderer'])
			else:
				self.add_video_item(desc=(details.get(e['video_id']) or {}).get('desc'), **e)

	# ##################################################################################################################

	def flatten_items(self, blocks):
		ret = []
		for block in blocks or []:
			if isinstance(block, dict) and "itemSectionRenderer" in block:
				ret += self.flatten_items(dig(block, "itemSectionRenderer", "contents", default=[]))
			else:
				ret.append(block)

		return ret

	# ##################################################################################################################

	def get_continuation_token(self, renderer):
		for endpoint in (dig(renderer, "continuationEndpoint"), dig(renderer, "button", "buttonRenderer", "command")):
			if not endpoint:
				continue

			token = dig(endpoint, "continuationCommand", "token")
			if token:
				return token

			for command in dig(endpoint, "commandExecutorCommand", "commands", default=[]):
				token = dig(command, "continuationCommand", "token")
				if token:
					return token

		return None

	# ##################################################################################################################

	def parse_related_item(self, block):
		'''
		Converts one item from the list of related videos to the dictionary with arguments of add_video_item(). Returns None for unsupported items (playlists, ads, ...).
		'''
		if "lockupViewModel" in block:
			one = block["lockupViewModel"]
			if one.get("contentType", "LOCKUP_CONTENT_TYPE_VIDEO") != "LOCKUP_CONTENT_TYPE_VIDEO":
				return None

			video_id = one.get("contentId", "")
			meta = dig(one, "metadata", "lockupMetadataViewModel", default={})
			rows = dig(meta, "metadata", "contentMetadataViewModel", "metadataRows", default=[])
			title = dig(meta, "title", "content", default=u'N/A')
			channel_title = dig(rows, 0, "metadataParts", 0, "text", "content", default=u'N/A')
			views = dig(rows, 1, "metadataParts", 0, "text", "content", default=u'')
			published = dig(rows, 1, "metadataParts", 1, "text", "content", default=u'')
			duration = dig(one, "contentImage", "thumbnailViewModel", "overlays", 0, "thumbnailBottomOverlayViewModel", "badges", 0, "thumbnailBadgeViewModel", "text", default=u'')
			channel_id = (
				dig(meta, "image", "decoratedAvatarViewModel", "rendererContext", "commandContext", "onTap", "innertubeCommand", "browseEndpoint", "browseId") or
				dig(rows, 0, "metadataParts", 0, "text", "commandRuns", 0, "onTap", "innertubeCommand", "browseEndpoint", "browseId") or
				u''
			)
			is_live = (duration == "LIVE")
		elif "compactVideoRenderer" in block:
			one = block["compactVideoRenderer"]
			video_id = one.get("videoId", "")
			title = yt_text(one.get("title")) or u'N/A'
			channel_title = yt_text(one.get("longBylineText") or one.get("shortBylineText")) or u'N/A'
			channel_id = dig(one, "longBylineText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId", default=u'')
			views = yt_text(one.get("viewCountText") or one.get("shortViewCountText"))
			published = yt_text(one.get("publishedTimeText"))
			duration = yt_text(one.get("lengthText"))
			is_live = (dig(one, "thumbnailOverlays", 0, "thumbnailOverlayTimeStatusRenderer", "style") == "LIVE")
		else:
			return None

		if not video_id:
			return None

		if is_live:
			title = _C('green', u"* " + title)

		plot = u'{} [{}] {}'.format(published, channel_title, duration)
		if views:
			plot += u'\n' + views

		return dict(title=title, video_id=video_id, plot=plot, duration=self.to_seconds(duration), channel_title=channel_title, channel_id=channel_id)

	# ##################################################################################################################

	def list_related(self, video_id=None, continuation=None):
		params = {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}}}
		if continuation:
			params["continuation"] = continuation
		else:
			params["videoId"] = video_id

		data = self.call_api("next", params)

		if continuation:
			blocks = []
			for action in (data.get("onResponseReceivedEndpoints") or []):
				blocks += dig(action, "appendContinuationItemsAction", "continuationItems", default=[])
		else:
			blocks = dig(data, "contents", "twoColumnWatchNextResults", "secondaryResults", "secondaryResults", "results", default=[])

		pending = []
		cont = None

		for block in self.flatten_items(blocks):
			if "continuationItemRenderer" in block:
				cont = self.get_continuation_token(block["continuationItemRenderer"]) or cont
				continue

			item = self.parse_related_item(block)
			if item:
				pending.append(item)

		if not pending and not continuation:
			self.show_info(self._("No related videos found"))

		self.add_list_items(pending)

		if cont:
			self.add_next(cmd=self.list_related, continuation=cont)

	# ##################################################################################################################

	def find_comments_token(self, data):
		for block in dig(data, "contents", "twoColumnWatchNextResults", "results", "results", "contents", default=[]):
			section = block.get("itemSectionRenderer") if isinstance(block, dict) else None
			if not section:
				continue

			if section.get("sectionIdentifier") != "comment-item-section" and section.get("targetId") != "comments-section":
				continue

			for item in section.get("contents", []):
				token = self.get_continuation_token(item.get("continuationItemRenderer", {}))
				if token:
					return token

		return None

	# ##################################################################################################################

	def parse_comment(self, thread, entities):
		'''
		Returns dictionary with comment data. Youtube uses two formats - the old one (data directly in commentRenderer) and the new one (data in entityBatchUpdate mutations)
		'''
		renderer = dig(thread, "comment", "commentRenderer")
		if renderer:
			return dict(
				author=yt_text(renderer.get("authorText")),
				text=yt_text(renderer.get("contentText")),
				published=yt_text(renderer.get("publishedTimeText")),
				likes=yt_text(renderer.get("voteCount")),
				replies=renderer.get("replyCount") or u''
			)

		payload = entities.get(dig(thread, "commentViewModel", "commentViewModel", "commentKey"))
		if payload:
			return dict(
				author=dig(payload, "author", "displayName", default=u''),
				text=dig(payload, "properties", "content", "content", default=u''),
				published=dig(payload, "properties", "publishedTime", default=u''),
				likes=dig(payload, "toolbar", "likeCountNotliked", default=u''),
				replies=dig(payload, "toolbar", "replyCount", default=u'')
			)

		return None

	# ##################################################################################################################

	def list_comments(self, video_id=None, continuation=None):
		first_page = not continuation

		if first_page:
			data = self.call_api("next", {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"videoId":video_id})
			continuation = self.find_comments_token(data)
			if not continuation:
				self.show_info(self._("Comments are disabled or not available for this video"))

		data = self.call_api("next", {"context":{"client":{"clientName":"WEB","clientVersion":"2.9999099"}},"continuation":continuation})

		blocks = []
		for action in (data.get("onResponseReceivedEndpoints") or []):
			for key in ("reloadContinuationItemsCommand", "appendContinuationItemsAction"):
				blocks += dig(action, key, "continuationItems", default=[])

		entities = {}
		for mutation in dig(data, "frameworkUpdates", "entityBatchUpdate", "mutations", default=[]):
			payload = dig(mutation, "payload", "commentEntityPayload")
			if payload and mutation.get("entityKey"):
				entities[mutation["entityKey"]] = payload

		cont = None
		count = 0

		for block in blocks:
			if "continuationItemRenderer" in block:
				cont = self.get_continuation_token(block["continuationItemRenderer"]) or cont
				continue

			if "commentThreadRenderer" not in block:
				continue

			comment = self.parse_comment(block["commentThreadRenderer"], entities)
			if not comment or not comment['text']:
				continue

			header = comment['author']
			if comment['published']:
				header += u' (%s)' % comment['published']

			lines = [header]
			stats = []
			if comment['likes']:
				stats.append(u'+%s' % comment['likes'])
			if comment['replies']:
				stats.append(u'%s: %s' % (self._('Replies'), comment['replies']))
			if stats:
				lines.append(u'  '.join(stats))

			short_text = re.sub(r'\s+', ' ', comment['text']).strip()
			if len(short_text) > 100:
				short_text = short_text[:100] + u'...'

			self.add_dir(u'{}: {}'.format(comment['author'], short_text), info_labels={'plot': u'\n'.join(lines) + u'\n\n' + comment['text']}, cmd=self.show_comment, author=comment['author'], text=comment['text'])
			count += 1

		if count == 0 and first_page:
			self.show_info(self._("Comments are disabled or not available for this video"))

		if cont:
			self.add_next(cmd=self.list_comments, continuation=cont)

	# ##################################################################################################################

	def show_comment(self, author, text):
		self.show_info(u'{}:\n\n{}'.format(author, text))

	# ##################################################################################################################