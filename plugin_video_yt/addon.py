# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) 2020 Michal Novotny https://github.com/misanov
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from Plugins.Extensions.archivCZSK.engine import client

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ContentProvider, ResolveException
from tools_xbmc.tools import util
from tools_xbmc.compat import XBMCCompatInterface

import re, time, json, datetime

try:
	import cookielib
	from urllib2 import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urlparse import urlparse, parse_qs
	from urllib import quote
except:
	from urllib.request import urlopen, Request, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlparse, parse_qs, quote
	import http.cookiejar as cookielib

api_url = "https://www.googleapis.com/youtube/v3/"
api_key = "AIzaSyCNReMvKLnaWRR5T5uGWpvn4I2VYc78Gy4"
max_res = 30

def writeLog(msg, type='INFO'):
	try:
		from Components.config import config
		f = open(os.path.join(config.plugins.archivCZSK.logPath.getValue(),'yt.log'), 'a')
		dtn = datetime.datetime.now()
		f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
		f.close()
	except:
		pass

def jsonPost(url, jsonData, headers={}):
	req = Request(url, json.dumps(jsonData).encode('utf-8'), headers)
	# req.add_header('User-Agent', UA)
	response = urlopen(req)
	data = response.read().decode('utf-8')
	response.close()
	return data

def yt_time(duration="P1W2DT6H21M32S"):
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
	units = list(ISO_8601.match(duration).groups()[-3:])
	units = list(reversed([int(x) if x != None else 0 for x in units]))
	return str(datetime.timedelta(seconds=sum([x*60**units.index(x) for x in units])))

class YTContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'YouTube', 'https://www.youtube.com/', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def search(self, keyword):
		return self.list(api_url + "search?q=" + quote(keyword) + "&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id")

	def categories(self):
		result = self.load_channels()
		# result.append(self.dir_item('LIVE NOVÉ', api_url + "search?eventType=live&type=video&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id&order=date"))
		# result.append(self.dir_item('LIVE CZ', api_url + "search?eventType=live&type=video&regionCode=CZ&relevanceLanguage=cs&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id"))
		# result.append(self.dir_item('LIVE SK', api_url + "search?eventType=live&type=video&regionCode=SK&relevanceLanguage=sk&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id"))
		return result

	def save_channel(self,name,url):
		max_history = __addon__.getSetting("channels") or 10
		cnt = 0
		history = []
		filename = addon_userdata_dir + "channels.txt"
		try:
			with open(filename, "r") as file:
				for line in file:
					item = line[:-1]
					history.append(item)
		except IOError:
			history = []
		history.insert(0,name+";"+url)
		with open(filename, "w") as file:
			for item in history:
				cnt = cnt + 1
				if cnt <= max_history:
					file.write('%s\n' % item)
		client.refresh_screen()

	def load_channels(self):
		history = []
		filename = addon_userdata_dir + "channels.txt"
		try:
			with open(filename, "r") as file:
				for line in file:
					item = line[:-1].split(";")
					history.append(self.dir_item(item[0], api_url + "search?channelId=" + item[1] + "&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id&order=date"))
		except IOError:
			history = []
		return history

	def list(self, url):
		# ulozit kanal
		if 'save;' in url:
			item = url.split(";")
			self.save_channel(item[1],item[2])
			return []

		# vypis
		if 'search?' in url:
			return self.parseData(url)

		# formaty
		if 'watch?' in url:
			return self.parseFormats(url)

		return []

	def parseData(self, url):
		httpdata = util.request(url)
		data = json.loads(httpdata)
		result = []
		ids = []
		for item in data.get('items'):
			if item.get("id", {}).get("videoId", "") != "": ids.append(item.get("id", {}).get("videoId", ""))
		httpdata = util.request(api_url + "videos?id=" + ','.join(ids) + "&key=" + api_key + "&part=snippet,statistics,contentDetails")
		details = json.loads(httpdata)
		detail = {}
		for temp in details.get('items'):
			detail[temp.get('id')] = temp
		for temp in data.get('items'):
			videoId = temp.get("id", {}).get("videoId", "")
			if videoId == "": continue
			item = self.dir_item()
			item['title'] = temp.get("snippet", {}).get("title", "")
			if temp.get("snippet", {}).get("liveBroadcastContent", "") == "upcoming":
				item['title'] = "[COLOR red]" + item['title'] + "[/COLOR]"
			elif temp.get("snippet", {}).get("liveBroadcastContent", "") == "live":
				item['title'] = "[COLOR green]" + item['title'] + "[/COLOR]"
			item['url'] = self.base_url+'watch?v=' + videoId
			item['img'] = detail[videoId].get("snippet", {}).get("thumbnails", {}).get("standard", {}).get("url", None)
			pt = temp.get("snippet", {}).get("publishTime", "") #2020-12-19T19:58:27Z
			pts = re.search("([\d]{4})-([\d]{2})-([\d]{2})T([\d]{2}):([\d]{2})",pt)
			publish = pts.group(3)+"."+pts.group(2)+"."+pts.group(1)+" "+pts.group(4)+":"+pts.group(5) if pts else ""
			desc = detail[videoId].get("snippet", {}).get("description", "")
			chan = detail[videoId].get("snippet", {}).get("channelTitle", "")
			chanId = detail[videoId].get("snippet", {}).get("channelId", "")
			duration = yt_time(detail[videoId].get("contentDetails", {}).get("duration", ""))
			views = detail[videoId].get("statistics", {}).get("viewCount", "")
			item['plot'] = publish + " [" + chan + "] " + str(duration) + " (" + views + "x) - " + desc
			item['menu'] = {}
			item['menu']['Videa kanálu: '+chan] = {'list': api_url + "search?channelId=" + chanId + "&maxResults=" + str(max_res) + "&key=" + api_key + "&part=snippet,id&order=date", 'action-type':'list'}
			item['menu']['Uložit kanál: '+chan] = {'list': 'save;'+chan+';'+chanId, 'action-type':'list'}
			result.append(item)
		if "nextPageToken" in data:
			item = self.dir_item()
			item['title'] = "[COLOR yellow]>>> DALŠÍ >>>[/COLOR]"
			if "pageToken" in url:
				item['url'] = re.sub(r"pageToken=([^\&]+)","pageToken=" + data["nextPageToken"],url)
			else:
				item['url'] = url + '&pageToken=' + data["nextPageToken"]
			result.append(item)
		return result

	def parseFormats(self, url):
		result = []
		url_data = urlparse(url)
		query = parse_qs(url_data.query)
		video_id = query["v"][0]
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json",
			"referer": "https://www.youtube.com",
			"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
			"X-Goog-Api-Key": "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
		}
		post = {
			"context": {
				"client": {
					"clientName": "TVLITE",
					"clientVersion": "2",
					"clientScreen": "EMBED"
				}
			},
			"videoId": video_id
		}
		html = jsonPost('https://youtubei.googleapis.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8', post, headers=headers)
		data = json.loads(html)
		if "streamingData" in data and "hlsManifestUrl" in data["streamingData"]: # Live stream
			html = util.request(data["streamingData"]["hlsManifestUrl"])
			for m in re.finditer('#EXT-X-STREAM-INF:.*?RESOLUTION=\d+x(?P<resolution>\d+).*?\s(?P<chunklist>[^\s]+)', html, re.DOTALL):
				item = self.video_item()
				item['url'] = m.group('chunklist')
				item['quality'] = m.group('resolution') + "p"
				item['title'] = "[" + item['quality'] + "] " + data.get("videoDetails",[]).get("title")
				result.append(item)
		elif "streamingData" in data and "formats" in data["streamingData"]: # Original YT stream
			if "url" in data["streamingData"]["formats"][0]:
				for format in data["streamingData"]["formats"]:
					item = self.video_item()
					item['url'] = format['url']
					item['quality'] = format['qualityLabel']
					item['title'] = "[" + item['quality'] + " Orig] " + data.get("videoDetails",[]).get("title")
					result.append(item)
		# Externi konverze do MP4 ne live streamu
		if not data.get("videoDetails", {}).get("isLive"):
			headers = {"referer": "https://yt1s.com/en23","user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36","x-requested-with": "XMLHttpRequest"}
			html = util.post('https://yt1s.com/api/ajaxSearch/index', {"q":url, "vt": "home"}, headers=headers)
			data = json.loads(html)
			if data["status"] == "ok" and "links" in data and "mp4" in data["links"]:
				for format in data["links"]["mp4"]:
					if data["links"]["mp4"][format].get("q") == "auto": continue
					item = self.video_item()
					item['url'] = data["vid"]+"|"+data["links"]["mp4"][format].get("k")
					item['quality'] = data["links"]["mp4"][format].get("q")
					item['title'] = "[" + data["links"]["mp4"][format].get("q","") + "] " + data["title"]
					result.append(item)
		return sorted(result, key=lambda i:(len(i['quality']),i['quality']), reverse = True)

	def resolve(self, item, captcha_cb=None, select_cb=None):
		if 'watch?' in item['url']:
			return self.parseFormats(item['url'])
		itm = item.copy()
		result = []
		if '|' in item['url']:
			par = item['url'].split('|')
			headers = {"referer": "https://yt1s.com/en5","user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36","x-requested-with": "XMLHttpRequest"}
			try:
				html = util.post('https://yt1s.com/api/ajaxConvert/convert', {"vid":par[0], "k": par[1]}, headers=headers)
				data = json.loads(html)
				if data["status"] == "ok" and "dlink" in data:
					item = self.video_item()
					item['url'] = data["dlink"]
					item['quality'] = data["fquality"]
					item['title'] = data["title"]
					result.append(item)
			except Exception as e:
				client.showInfo("Exception {0} occurred".format(e))
		else:
			item = self.video_item()
			item['url'] = itm["url"]
			item['title'] = itm["title"]
			result.append(item)
		return result

__scriptid__ = 'plugin.video.yt'
__scriptname__ = 'YouTube'
__addon__ = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__ = __addon__.getLocalizedString
addon_userdata_dir = __addon__.getAddonInfo('profile')+'/'

def yt_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}
	provider = YTContentProvider(tmp_dir='/tmp')
	XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)


def main(addon):
	return XBMCCompatInterface(yt_run)
