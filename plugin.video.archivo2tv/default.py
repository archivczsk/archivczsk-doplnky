# -*- coding: utf-8 -*-
#
# addon by misanov based on waladir plugin
#

import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime, timedelta 
from datetime import date

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video
from Plugins.Extensions.archivCZSK.engine import client
from Components.config import config
from Plugins.Extensions.archivCZSK.engine.tools.util import toString

try:
	from urllib2 import urlopen, Request, HTTPError
	from urllib import quote, unquote_plus, urlencode
	from urlparse import parse_qsl
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from urllib.request import urlopen, Request
	from urllib.parse import quote, unquote_plus, urlencode, parse_qsl
	from urllib.error import HTTPError

	def py2_encode_utf8( text ):
		return text
	
	def py2_decode_utf8( text ):
		return text

############### init ################
addon = ArchivCZSK.get_xbmc_addon('plugin.video.archivo2tv')
addon_userdata_dir = addon.getAddonInfo('profile')+'/'
home = addon.getAddonInfo('path')
icon = os.path.join(home, 'icon.png')

header_unity = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0", "Content-Type":"application/json"}
header = {"X-NanguTv-App-Version" : "Android#6.4.1", "User-Agent" : "Dalvik/2.1.0", "Accept-Encoding" : "gzip", "Connection" : "Keep-Alive", "Content-Type" : "application/x-www-form-urlencoded;charset=UTF-8", "X-NanguTv-Device-Name" : addon.getSetting("deviceid"), "X-NanguTv-Device-Name" : addon.getSetting("devicename")}

LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'archivo2tv.log')
base_url = ""
_url = ""

def writeLog(msg, type='INFO'):
	try:
		f = open(LOG_FILE, 'a')
		dtn = datetime.now()
		f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
		f.close()
	except:
		pass

def showInfo(mmsg):
	client.add_operation("SHOW_MSG", {'msg': mmsg, 'msgType': 'info', 'msgTimeout': 4, 'canClose': True })
#	writeLog(mmsg)

def showError(mmsg):
	client.add_operation("SHOW_MSG", {'msg': mmsg, 'msgType': 'error', 'msgTimeout': 4, 'canClose': True })
#	writeLog(mmsg,'ERROR')

def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)

def build_plugin_url(query):
	return base_url + '?' + urlencode(query)

def get_url(**kwargs):
	return '{0}?{1}'.format(_url, urlencode(kwargs))

def check_settings():
	if not addon.getSetting("deviceid"):
		addon.setSetting("deviceid",''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15)))
	if not addon.getSetting("username") or not addon.getSetting("password") or not addon.getSetting("deviceid") or not addon.getSetting("devicename") or  not addon.getSetting("devicetype"):
		showError('V nastavení je nutné mít vyplněné všechny přihlašovací údaje')
		return False
	return True

############### hledani - historie ################

def save_search_history(query):
	max_history = int(addon.getSetting("search_history"))
	cnt = 0
	history = []
	filename = addon_userdata_dir + "search_history.txt"
	
	try:
		with open(filename, "r") as file:
			for line in file:
				item = line[:-1]
				history.append(item)
	except IOError:
		history = []

	history.insert(0,query)

	with open(filename, "w") as file:
		for item  in history:
			cnt = cnt + 1
			if cnt <= max_history:
				file.write('%s\n' % item)

def load_search_history():
	history = []
	filename = addon_userdata_dir + "search_history.txt"
	try:
		with open(filename, "r") as file:
			for line in file:
				item = line[:-1]
				history.append(item)
	except IOError:
		history = []
	return history

############### O2 API ################

def call_o2_api(url, data, header):
	if data is not None and not isinstance( data, bytes ):
		data = data.encode('utf-8')
	request = Request(url = url , data = data, headers = header)
	if addon.getSetting("log_request_url") == "true":
		writeLog(url)
	if addon.getSetting("log_request_data") == "true" and data is not None:
		writeLog(data)
#	html = urlopen(request).read()

	try:
		html = urlopen(request).read().decode('utf-8')
		if addon.getSetting("log_response") == "true":
			writeLog(html)

		if html and len(html) > 0:
			data = json.loads(html)
			return data
		else:
			return []
	except HTTPError as e:
		return { "err" : e.reason }				
  
def get_auth_token():
	post = {"username" : addon.getSetting("username"), "password" : addon.getSetting("password")} 
	data = call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/login", data = urlencode(post), header = header)
	if "err" in data:
		showError("Problém při přihlášení: %s"%toString(data['err']))
		return

	if "services" in data and "remote_access_token" in data and len(data["remote_access_token"]) > 0 and "service_id" in data["services"][0] and len(data["services"][0]["service_id"]) > 0:
		remote_access_token = data["remote_access_token"]
		service_id = data["services"][0]['service_id']

		post = {"service_id" : service_id, "remote_access_token" : remote_access_token}
		data = call_o2_api(url = "https://ottmediator.o2tv.cz:4443/ottmediator-war/loginChoiceService", data = urlencode(post), header = header)
		if "err" in data:
			showError("Problém při přihlášení")
			return

		post = {"grant_type" : "remote_access_token", "client_id" : "tef-web-portal-etnetera", "client_secret" : "2b16ac9984cd60dd0154f779ef200679", "platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0", "language" : "cs", "remote_access_token" : str(remote_access_token), "authority" :	 "tef-sso", "isp_id" : "1"}
		data = call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data = urlencode(post), header = header)
		if "err" in data:
			showError("Problém při přihlášení: %s"%toString(data['err']))
			return

		if "access_token" in data and len(data["access_token"]) > 0:
			access_token = data["access_token"]
			header.update({"X-NanguTv-Access-Token" : str(access_token), "X-NanguTv-Device-Id" : addon.getSetting("deviceid")})
			data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/subscription-configuration.json", data = None, header = header)
			if "err" in data:
				showError("Problém při přihlášení: %s"%toString(data['err']))
				return
			if "isp" in data and len(data["isp"]) > 0 and "locality" in data and len(data["locality"]) > 0 and "billingParams" in data and len(data["billingParams"]) > 0 and "offers" in data["billingParams"] and len(data["billingParams"]["offers"]) > 0 and "tariff" in data["billingParams"] and len(data["billingParams"]["tariff"]) > 0:
				subscription = data["subscription"]
				isp = data["isp"]
				locality = data["locality"]
				offers = data["billingParams"]["offers"]
				tariff = data["billingParams"]["tariff"]
				header_unity = {"User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0", "Content-Type" : "application/json", "x-o2tv-access-token" : access_token}
				return access_token, subscription, isp, locality, offers, tariff
			else:
				showError("Problém s příhlášením")
				return
		else:
			showError("Problém s příhlášením")
			return
	else:
		showError("Problém s příhlášením")
		return

def get_auth_password():
	post = {"grant_type" : "password", "client_id" : "tef-web-portal-etnetera", "client_secret" : "2b16ac9984cd60dd0154f779ef200679", "platform_id" : "231a7d6678d00c65f6f3b2aaa699a0d0", "language" : "cs", "username" : addon.getSetting("username"), "password" : addon.getSetting("password")}
	data = call_o2_api(url = "https://oauth.o2tv.cz/oauth/token", data = urlencode(post), header = header)
	if "err" in data:
		showError("Problém při přihlášení: %s"%toString(data['err']))
		return

	if "access_token" in data and len(data["access_token"]) > 0:
		access_token = data["access_token"]
		header.update({"X-NanguTv-Access-Token" : str(access_token), "X-NanguTv-Device-Id" : addon.getSetting("deviceid")})
		data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/subscription-configuration.json", data = None, header = header)
		if "err" in data:
			showError("Problém při přihlášení: %s"%toString(data['err']))
			return
		 
		if "isp" in data and len(data["isp"]) > 0 and "locality" in data and len(data["locality"]) > 0 and "billingParams" in data and len(data["billingParams"]) > 0 and "offers" in data["billingParams"] and len(data["billingParams"]["offers"]) > 0 and "tariff" in data["billingParams"] and len(data["billingParams"]["tariff"]) > 0:
			subscription = data["subscription"]
			isp = data["isp"]
			locality = data["locality"]
			offers = data["billingParams"]["offers"]
			tariff = data["billingParams"]["tariff"]
			header_unity = {"User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0", "Content-Type" : "application/json", "x-o2tv-access-token" : access_token}
			return access_token, subscription, isp, locality, offers, tariff
		else:
			showError("Problém s příhlášením")
			return
	else:
		showError("Problém s příhlášením")
		return

############### menu ################


def list_menu():
	addDir("Kanály", build_plugin_url({ 'action': 'list_channels'}), 1, None)
	addDir("Nahrávky", build_plugin_url({ 'action': 'list_recordings'}), 1, None)
	addDir("Vyhledávání", build_plugin_url({ 'action': 'list_search'}), 1, None)
	if addon.getSetting("hide_channel_list_edit") is not "true":
		addDir("Pořadí kanálů", build_plugin_url({ 'action': 'list_channels_list'}), 1, None)
	
############### kanaly ################

def list_channels():
	channels_ordered = load_channels()	
	channels = {}
	channel_data = {}
	for offer in offers:
		post = {"locality" : locality, "tariff" : tariff, "isp" : isp, "language" : "ces", "deviceType" : addon.getSetting("devicetype"), "liveTvStreamingProtocol" : "HLS", "offer" : offer}
		data = call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data = urlencode(post), header = header)															   
		if "err" in data:
			showError("Problém s načtením kanálů: %s"%toString(data['err']))
			return

		if "channels" in data and len(data["channels"]) > 0:
			for channel in data["channels"]:
				if data["channels"][channel]["channelType"] == "TV":
					for channel_ordered in channels_ordered:
						if channel_ordered[0] == py2_encode_utf8(data["channels"][channel]["channelName"]):
							num = channel_ordered[1]
					channels.update({ num : {"channelName" : data["channels"][channel]["channelName"], "channelKey" : data["channels"][channel]["channelKey"]}})

	if addon.getSetting("details") == "true":
		data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", data = None, header = header_unity)															   
		if "err" in data:
			showError("Problém s načtením kanálů: %s"%toString(data['err']))
			return
		if "result" in data and len(data["result"]) > 0:
			for channel in data["result"]:
				channel_data.update({ py2_encode_utf8(channel["channel"]["channelKey"]) : "https://www.o2tv.cz/" + channel["channel"]["images"]["color"]["url"]});

	for num in sorted(channels.keys()):
		if addon.getSetting("details") == "true" and py2_encode_utf8(channels[num]["channelKey"]) in channel_data:
			thumb = channel_data[py2_encode_utf8(channels[num]["channelKey"])]
		else:
			thumb = None
			
		addDir(channels[num]["channelName"], build_plugin_url({ 'action': 'list_days', 'channelKey': py2_encode_utf8(channels[num]["channelKey"])}), 1, thumb)
		
def list_days(channelKey):
	epgId = 0
	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", data = None, header = header_unity)
	if "err" in data:
	  showError("Problém s načtením programu: %s"%toString(data['err']))
	  return

	if "result" in data and len(data["result"]) > 0:
		for channel in data["result"]:
			if py2_encode_utf8(channel["channel"]["channelKey"]) == channelKey and "live" in channel:
				epgId = channel["live"]["epgId"]

	if epgId != 0:
		epgdata = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
		if "err" in epgdata:
			showError("Problém s načtením programu: %s"%toString(epgdata['err']))
			return

		img = "";
		plot = "";
		if "images" in epgdata and len(epgdata["images"]) > 0:
			plot = epgdata["longDescription"]
			img = epgdata["images"][0]["cover"]
 
	if epgId != 0:
		start = datetime.fromtimestamp(epgdata["start"]/1000)
		end = datetime.fromtimestamp(epgdata["end"]/1000)
		nazev = "Živě: " + py2_encode_utf8(epgdata["name"]) + " (" + start.strftime("%H:%M") + " - " + end.strftime("%H:%M") + ")"
	else:
		nazev = "Živě"

	infoLabels = {}
	thumb = None
	if addon.getSetting("details") == "true" and epgId != 0:  
		thumb = "https://www.o2tv.cz/" + img
		infoLabels = {"title":epgdata["name"], "plot":plot}
		if "ratings" in epgdata and len(epgdata["ratings"]) > 0:
			for rating, rating_value in list(epgdata["ratings"].items()):
				infoLabels['rating'] = rating_value/10

	url = get_url(action='play_live', channelKey = channelKey, title = py2_encode_utf8(epgdata["name"]) + " (" + start.strftime("%H:%M") + " - " + end.strftime("%H:%M") + ")") 
	addDir(nazev, url, 1, thumb, infoLabels=infoLabels)

	url = get_url(action='future_program', channelKey = channelKey)
	addDir("Budoucí (nastavení nahrávek)", url, 1, None)
   
	for i in range (7):
		day = date.today() - timedelta(days = i)
		if i == 0:
			den = "Dnes"
		elif i == 1:
			den = "Včera"
		else:
			if day.strftime("%A") in day_translation:
				den = day_translation[day.strftime("%A")] + " " + day.strftime("%d.%m.%Y")
			else:
				den = day.strftime("%A") + " " + day.strftime("%d.%m.%Y")
			den = py2_decode_utf8( den )
			
		url = get_url(action='list_program', channelKey = channelKey, day_min = i)  
		addDir(den, url, 1, None)

def list_program(channelKey, day_min):
	if int(day_min) == 0:
		from_datetime = datetime.combine(date.today(), datetime.min.time())
		to_datetime = datetime.now()
	else:
		from_datetime = datetime.combine(date.today(), datetime.min.time()) - timedelta(days = int(day_min))
		to_datetime = datetime.combine(from_datetime, datetime.max.time())
	from_ts = int(time.mktime(from_datetime.timetuple()))
	to_ts = int(time.mktime(to_datetime.timetuple()))

	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/epg/depr/?channelKey=" + quote(channelKey) + "&from=" + str(from_ts*1000) + "&to=" + str(to_ts*1000) + "&forceLimit=true&limit=500", data = None, header = header_unity)
	if "err" in data:
		showError("Problém s načtením programu: %s"%toString(data['err']))
		return

	if "epg" in data and len(data["epg"]) > 0 and len(data["epg"]["items"]) > 0 and len(data["epg"]["items"][0]["programs"]) > 0:
		for programs in data["epg"]["items"][0]["programs"]:
			startts = programs["start"]
			start = datetime.fromtimestamp(programs["start"]/1000)
			endts = programs["end"]
			end = datetime.fromtimestamp(programs["end"]/1000)
			epgId = programs["epgId"]
	
			if to_ts > int(programs["end"]/1000):	  
				if addon.getSetting("details") == "true":	 
					data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
					if "err" in data:
						showError("Problém s načtením programu: %s"%toString(data['err']))
						return
		  
					img = "";
					plot = "";
					if "images" in data and len(data["images"]) > 0:
						plot = data["longDescription"]
						img = data["images"][0]["cover"]
		   
				infoLabels = {}
				thumb = None
				if start.strftime("%A") in day_translation_short:
					nazev = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + programs["name"]
				else:
					nazev = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + programs["name"]
					
				nazev = py2_decode_utf8( nazev )
				
				if addon.getSetting("details") == "true":	 
					thumb = "https://www.o2tv.cz/" + img
					infoLabels = {"title":programs["name"], "plot":plot}
					if "ratings" in data and len(data["ratings"]) > 0:
						for rating, rating_value in list(data["ratings"].items()):
							infoLabels['rating'] = rating_value/10
				else:
					infoLabels = {"title":programs["name"]}
			
				url = get_url(action='play_video', channelKey = channelKey, start = startts, end = endts, epgId = epgId)
				addDir(nazev, url, 1, thumb, infoLabels=infoLabels, menuItems={'Nahrát pořad': {'action': 'add_recording', 'epgId': epgId}})
	else:
		showError("Problém s načtením programu")
		return

def future_program(channelKey):
	from_datetime = datetime.now()
	from_ts = int(time.mktime(from_datetime.timetuple()))
	to_ts = from_ts
	
	for i in range(7):
		from_ts = to_ts
		to_ts = from_ts + 24*60*60
		data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/epg/depr/?channelKey=" + quote(channelKey) + "&from=" + str(from_ts*1000) + "&to=" + str(to_ts*1000) + "&forceLimit=true&limit=500", data = None, header = header_unity)
		if "err" in data:
			showError("Problém s načtením programu: %s"%toString(data['err']))
			return
	
		if "epg" in data and len(data["epg"]) > 0 and len(data["epg"]["items"]) > 0 and len(data["epg"]["items"][0]["programs"]) > 0:
			for programs in data["epg"]["items"][0]["programs"]:
				startts = programs["start"]
				start = datetime.fromtimestamp(programs["start"]/1000)
				endts = programs["end"]
				end = datetime.fromtimestamp(programs["end"]/1000)
				epgId = programs["epgId"]
		  
				if addon.getSetting("details_future") == "true":	
					data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
					if "err" in data:
						showError("Problém s načtením programu: %s"%toString(data['err']))
						return
		  
					img = "";
					plot = "";
					if "images" in data and len(data["images"]) > 0:
						plot = data["longDescription"]
						img = data["images"][0]["cover"]
		   
				infoLabels = {}
				thumb = None
				if start.strftime("%A") in day_translation_short:
					nazev = day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + programs["name"]
				else:
					nazev = start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + " | " + programs["name"]
					
				nazev = py2_decode_utf8( nazev )
				
				if addon.getSetting("details_future") == "true":	
					thumb = "https://www.o2tv.cz/" + img
					infoLabels = {"title":programs["name"], "plot":plot}
		  
					if "ratings" in data and len(data["ratings"]) > 0:
						for rating, rating_value in list(data["ratings"].items()):
							infoLabels['rating'] = rating_value/10
				else:
					infoLabels = {"title":programs["name"]}
				url = get_url(action='add_recording', channelKey = channelKey, epgId = epgId)
				addDir(nazev, url, 1, thumb, infoLabels=infoLabels, menuItems={'Nahrát pořad': {'action': 'add_recording', 'epgId': epgId}})
		else:
			  showError("Problém s načtením programu")
			  return

############### nahravky ################

def list_recordings():
	recordings = {}

	url = get_url(action='list_future_recordings')	
	addDir("Budoucí nahrávky", url, 1, None)

	header_unity2 = {"User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0", "Content-Type" : "application/json", "x-o2tv-access-token" : str(access_token), "x-o2tv-device-id" : addon.getSetting("deviceid"), "x-o2tv-device-name" : addon.getSetting("devicename")}
	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/user/profile/", data = None, header = header_unity2)
	if "err" in data:
		showError("Problém s načtením nahrávek: %s"%toString(data['err']))
		return
	sdata = data["sdata"]
	
	header_unity2.update({"x-o2tv-sdata" : str(sdata)})

	data_pvr = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/recordings/", data = None, header = header_unity2)
	if "err" in data_pvr:
		showError("Problém s načtením nahrávek: %s"%toString(data_pvr['err']))
#	 return
 
	if "result" in data_pvr and len(data_pvr["result"]) > 0:
		for program in data_pvr["result"]:
			if program["state"] == "DONE":
				pvrProgramId = program["pvrProgramId"]
				epgId = program["program"]["epgId"]
				if "ratings" in program["program"] and len(program["program"]["ratings"]) > 0:
					ratings = program["program"]["ratings"]
				else:
					ratings = {}
				if "longDescription" in program["program"] and len(program["program"]["longDescription"]) > 0:
					plot = program["program"]["longDescription"]
				else:
					plot = ""
				if "images" in program["program"] and len(program["program"]["images"]) > 0 and "cover" in program["program"]["images"][0]:
					img = program["program"]["images"][0]["cover"]
				else:
					img = ""
				recordings.update({program["program"]["start"]+random.randint(0,100) : {"pvrProgramId" : pvrProgramId, "name" : program["program"]["name"], "channelKey" : program["program"]["channelKey"], "start" : datetime.fromtimestamp(program["program"]["start"]/1000).strftime("%d.%m %H:%M"), "end" : datetime.fromtimestamp(program["program"]["end"]/1000).strftime("%H:%M"), "plot" : plot, "img" : img, "ratings" : ratings}}) 
	
		for recording in sorted(list(recordings.keys()), reverse = True):
			infoLabels = {}
			thumb = None
			nazev = recordings[recording]["name"] + " (" + recordings[recording]["channelKey"] + " | " + recordings[recording]["start"] + " - " + recordings[recording]["end"] + ")"
			if addon.getSetting("details") == "true":  
				thumb = "https://www.o2tv.cz/" + recordings[recording]["img"]
				infoLabels = {"title":recordings[recording]["name"], "plot":recordings[recording]["plot"]}
				for rating, rating_value in list(recordings[recording]["ratings"].items()):
					infoLabels['rating'] = rating_value/10
			else:
				infoLabels = {"title":recordings[recording]["name"]}
			url = get_url(action='play_recording', pvrProgramId = recordings[recording]["pvrProgramId"], title = py2_encode_utf8(recordings[recording]["name"]))
			addDir(nazev, url, 1, thumb, infoLabels=infoLabels, menuItems={'Smazat nahrávku': {'action': 'delete_recording', 'pvrProgramId': str(recordings[recording]["pvrProgramId"])}})
	else:
		showInfo("Nenalezena žádná nahrávka")
		return

def list_future_recordings():
	recordings = {}

	header_unity2 = {"User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0", "Content-Type" : "application/json", "x-o2tv-access-token" : str(access_token), "x-o2tv-device-id" : addon.getSetting("deviceid"), "x-o2tv-device-name" : addon.getSetting("devicename")}
	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/user/profile/", data = None, header = header_unity2)
	if "err" in data:
		showError("Problém s načtením nahrávek: %s"%toString(data['err']))
		return
	sdata = data["sdata"]
	
	header_unity2.update({"x-o2tv-sdata" : str(sdata)})

	data_pvr = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/recordings/", data = None, header = header_unity2)
	if "err" in data_pvr:
		showError("Problém s načtením nahrávek: %s"%toString(data_pvr['err']))
  #	return
	
	if "result" in data_pvr and len(data_pvr["result"]) > 0:
		for program in data_pvr["result"]:
			if program["state"] != "DONE":
				pvrProgramId = program["pvrProgramId"]
				epgId = program["program"]["epgId"]
				if "ratings" in program["program"] and len(program["program"]["ratings"]) > 0:
					ratings = program["program"]["ratings"]
				else:
					ratings = {}
				if "longDescription" in program["program"] and len(program["program"]["longDescription"]) > 0:
					plot = program["program"]["longDescription"]
				else:
					plot = ""
				if "images" in program["program"] and len(program["program"]["images"]) > 0 and "cover" in program["program"]["images"][0]:
					img = program["program"]["images"][0]["cover"]
				else:
					img = ""
		
				recordings.update({program["program"]["start"]+random.randint(0,100) : {"pvrProgramId" : pvrProgramId, "name" : program["program"]["name"], "channelKey" : program["program"]["channelKey"], "start" : datetime.fromtimestamp(program["program"]["start"]/1000).strftime("%d.%m %H:%M"), "end" : datetime.fromtimestamp(program["program"]["end"]/1000).strftime("%H:%M"), "plot" : plot, "img" : img, "ratings" : ratings}}) 
	
		for recording in sorted(list(recordings.keys()), reverse = True):
			nazev = recordings[recording]["name"] + " (" + recordings[recording]["channelKey"] + " | " + recordings[recording]["start"] + " - " + recordings[recording]["end"] + ")"
			if addon.getSetting("details") == "true":  
				thumb = "https://www.o2tv.cz/" + recordings[recording]["img"]
				infoLabels = {"title":recordings[recording]["name"], "plot":recordings[recording]["plot"]}
				for rating, rating_value in list(recordings[recording]["ratings"].items()):
					infoLabels['rating']=rating_value/10
			else:
				infoLabels = {"title":recordings[recording]["name"]}
			url = get_url(action='delete_recording',pvrProgramId=str(recordings[recording]["pvrProgramId"]))  
			addDir(nazev, url, 1, thumb, infoLabels=infoLabels, menuItems={'Smazat nahrávku': {'action': 'delete_recording', 'pvrProgramId': str(recordings[recording]["pvrProgramId"])}})
	else:
		showInfo("Nenalezena žádná nahrávka")
		return

def delete_recording(pvrProgramId):
	post = {"pvrProgramId" : int(pvrProgramId)}
	data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-remove-program.json", data = urlencode(post), header = header)
	showInfo("Nahrávka odstraněna")
#	client.set_command('updatelist')
#	client.refresh_screen(restoreLastPosition=False)

def add_recording(epgId):
	post = {"epgId" : int(epgId)}
	data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/vod/pvr-add-program.json", data = urlencode(post), header = header)
	if "err" in data:
		showError("Problém s přidáním nahrávky: %s"%toString(data['err']))
		return
	showInfo("Nahrávka přidána")
#	client.set_command('updatelist')
#	client.refresh_screen(restoreLastPosition=True)

############### prehravani ################

def parse_m3u8(url):
	res = []
	r = requests.get(url).text
	for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+)\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
		itm = {}
		bandwidth = int(m.group('bandwidth'))
		if bandwidth < 1400000:
			itm['quality'] = "288p"
		elif bandwidth >= 1400000 and bandwidth < 2450000:
			itm['quality'] = "404p"
		elif bandwidth >= 2450000 and bandwidth < 4100000:
			itm['quality'] = "576p"
		elif bandwidth >= 4100000 and bandwidth < 6000000:
			itm['quality'] = "720p"	   
		else:
			itm['quality'] = "1080p"
		itm['url'] = m.group('chunklist')
		res.append(itm)
	res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
	return res
	
def play_video(channelKey, start, end, epgId=0):
	post = {"serviceType" : "TIMESHIFT_TV", "deviceType" : addon.getSetting("devicetype"), "streamingProtocol" : "HLS",	 "subscriptionCode" : subscription, "channelKey" : channelKey, "fromTimestamp" : start, "toTimestamp" : str(int(end) + (int(addon.getSetting("offset"))*60*1000)), "id" : epgId, "encryptionType" : "NONE"}
	if addon.getSetting("only_sd") == "true":
		post.update({"resolution" : "SD"})
	data = call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data = urlencode(post), header = header)

	if "err" in data:
		showError("Problém s přehráním streamu")
		return

	if epgId != 0:
		epgdata = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
		if "err" in data:
			showError("Problém s načtením programu")
#		return

	url = ""
	if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
		for uris in data["uris"]:
			if addon.getSetting("only_sd") is not "true" and uris["resolution"] == "HD":
				url = uris["uri"]
		if url == "":
			url = data["uris"][0]["uri"]
		streams = parse_m3u8(url)
		for stream in streams:
			add_video('['+stream['quality']+'] '+ py2_encode_utf8(epgdata["name"]), stream['url'])

def play_live(channelKey,title):
	post = {"serviceType" : "LIVE_TV", "deviceType" : addon.getSetting("devicetype"), "streamingProtocol" : "HLS", "subscriptionCode" : subscription, "channelKey" : channelKey, "encryptionType" : "NONE"}
	if addon.getSetting("only_sd") == "true":
		post.update({"resolution" : "SD"})
	data = call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data = urlencode(post), header = header)

	if "err" in data:
		showError("Problém s přehráním streamu")
		return

	url = ""
	if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
		for uris in data["uris"]:
			if addon.getSetting("only_sd") is not "true" and uris["resolution"] == "HD":
				url = uris["uri"]
		if url == "":
			url = data["uris"][0]["uri"]
		streams = parse_m3u8(url)
		for stream in streams:
			add_video('['+stream['quality']+'] '+title,stream['url'])

def play_recording(pvrProgramId, title):
	post = {"serviceType" : "NPVR", "deviceType" : addon.getSetting("devicetype"), "streamingProtocol" : "HLS", "subscriptionCode" : subscription, "contentId" : pvrProgramId, "encryptionType" : "NONE"}
	if addon.getSetting("only_sd") == "true":
		post.update({"resolution" : "SD"})
	data = call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data = urlencode(post), header = header)

	if "err" in data:
		showError("Problém s přehráním streamu")
		return

	url = ""
	if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
		for uris in data["uris"]:
			if addon.getSetting("only_sd") is not "true" and uris["resolution"] == "HD":
				url = uris["uri"]
		if url == "":
			url = data["uris"][0]["uri"]
		streams = parse_m3u8(url)
		for stream in streams:
			add_video('['+stream['quality']+'] '+title,stream['url'])


############### hledani ################


def list_search():
	nazev = "Nové hledání"
	url = get_url(action='program_search', query = "-----")	 
	addDir(nazev,url,1,None)
	history = load_search_history()
	for item in history:
		nazev = item
		url = get_url(action='program_search', query = item)	
		addDir(nazev,url,1,None)

def program_search(query):
	if query == "-----":
		query = client.getTextInput(session, "Hledat")
		if len(query) == 0:
			showError("Je potřeba zadat vyhledávaný řetězec")
			return	 
		else:
			save_search_history(query)

	channels = load_channels()
	kanaly = []
	if len(channels) > 0:
		for channel in channels:
			kanaly.append(channel[0])
	max_ts = int(time.mktime(datetime.now().timetuple()))
	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/search/tv/depr/?groupLimit=1&maxEnd=" + str(max_ts*1000) + "&q=" + quote(query), data = None, header = header_unity)
	if "err" in data:
		showError("Problém při hledání")
		return
	
	if "groupedSearch" in data and "groups" in data["groupedSearch"] and len(data["groupedSearch"]["groups"]) > 0:
		for item in data["groupedSearch"]["groups"]:
			programs = item["programs"][0]
			startts = programs["start"]
			start = datetime.fromtimestamp(programs["start"]/1000)
			endts = programs["end"]
			end = datetime.fromtimestamp(programs["end"]/1000)
			epgId = programs["epgId"]
			
			if addon.getSetting("details") == "true":
				epgdata = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
				if "err" in epgdata:
					showError("Problém při hledání")
		#			return
				img = "";
				plot = "";
				if "images" in epgdata and len(epgdata["images"]) > 0:
					plot = epgdata["longDescription"]
					img = epgdata["images"][0]["cover"]
	
			if programs["channelKey"] not in kanaly: continue # nezobrazovat nezakoupene kanaly
			if start.strftime("%A") in day_translation_short:
				nazev = programs["name"] + " (" + programs["channelKey"] + " | " + day_translation_short[start.strftime("%A")] + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"
			else:
				nazev = programs["name"] + " (" + programs["channelKey"] + " | " + start.strftime("%a") + " " + start.strftime("%d.%m %H:%M") + " - " + end.strftime("%H:%M") + ")"
				
			nazev = py2_decode_utf8( nazev )
			
			thumb = None
			infoLabels = {}
			if addon.getSetting("details") == "true":  
				thumb = "https://www.o2tv.cz/" + img
				infoLabels = {"title":programs["name"], "plot":plot}
				if "ratings" in epgdata and len(epgdata["ratings"]) > 0:
					for rating, rating_value in list(epgdata["ratings"].items()):
						infoLabels['rating'] = rating_value/10
			else:
				infoLabels = {"title":programs["name"]}
			url = get_url(action='play_video', channelKey = py2_encode_utf8(programs["channelKey"]), start = startts, end = endts, epgId = epgId)
			addDir(nazev,url,1,thumb,infoLabels=infoLabels)
	else:
		showInfo("Nic nenalezeno")

############### editace kanalu ################

def list_channels_list():
	addDir("Ruční editace", get_url(action="list_channels_edit"),1,None)
	addDir("Načtení uživatelského seznamu z O2",get_url(action="get_o2_channels_lists"),1,None)
	addDir("Resetovat seznam kanálů",get_url(action="reset_channel_list"),1,None)

def get_o2_channels_lists():
	data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/get-user-pref.json?name=nangu.channelListUserChannelNumbers", data = None, header = header)
	if not data or "err" in data:
		showError("Problém s načtením seznamu kanálů")
		return
	if "listUserChannelNumbers" in data and len(data["listUserChannelNumbers"]) > 0:
		for list in data["listUserChannelNumbers"]:
			nazev = list.replace("user::","")
			url = get_url(action="load_o2_channel_list", list = py2_encode_utf8(list))  
			addDir(nazev,url,1,None)
	else:
		showError("Nanalezen žádný seznam v O2")
	
	return

def load_o2_channel_list(list):
	channels = {}
	filename = addon_userdata_dir + "channels.txt"
	data = call_o2_api(url = "https://app.o2tv.cz/sws/subscription/settings/get-user-pref.json?name=nangu.channelListUserChannelNumbers", data = None, header = header)
	if not data or "err" in data:
		showError("Problém s načtením seznamu kanálů")
		return
	if "listUserChannelNumbers" in data and len(data["listUserChannelNumbers"]) > 0:
		for list2 in data["listUserChannelNumbers"]:
			if list == list2:
				for channel in data["listUserChannelNumbers"][list]:
					channels.update({int(data["listUserChannelNumbers"][list][channel]) : channel})
		
				with open(filename, "w") as file:
					for key in sorted(channels.keys()):
						line = py2_encode_utf8(channels[key])+";"+str(key)
						file.write('%s\n' % line)
		showInfo("Seznam kanálů byl načten")
	else:
		showError("Nanalezen žádný seznam v O2")
		return
	  
def reset_channel_list():	 
	filename = addon_userdata_dir + "channels.txt"
	if os.path.exists(filename):
		os.remove(filename) 
	channels = load_channels()
	showInfo("Seznam kanálů byl resetován")
	
def list_channels_edit():
	channels = load_channels()
	if len(channels) > 0:
		for channel in channels:
			nazev = str(channel[1]) + " " + channel[0]
			url = get_url(action='edit_channel', channelName = channel[0])	
			addDir(nazev,url,1,None)
	
def load_channels():
	channels = {}
	channels_ordered = []
	channels_to_add = {}
	filename = addon_userdata_dir + "channels.txt"

	try:
		with open(filename, "r") as file:
			for line in file:
				channel = line[:-1].split(";")
				channels_ordered.append((channel[0], int(channel[1])))
				max_num = int(channel[1])
	
		for offer in offers:
			post = {"locality" : locality, "tariff" : tariff, "isp" : isp, "language" : "ces", "deviceType" : addon.getSetting("devicetype"), "liveTvStreamingProtocol" : "HLS", "offer" : offer}
			data = call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data = urlencode(post), header = header)															   
			if "err" in data:
				showError("Problém s načtením kanálů")
				return
			if "channels" in data and len(data["channels"]) > 0:
				for channel in data["channels"]:
					if data["channels"][channel]["channelType"] == "TV":
					 
						fnd = 0
						for channel_ordered in channels_ordered:
							if channel_ordered[0] == py2_encode_utf8(data["channels"][channel]["channelName"]):
								fnd = 1
						if fnd == 0:
							channels_to_add.update({int(data["channels"][channel]["channelNumber"]) : data["channels"][channel]["channelName"]})
			for key in sorted(channels_to_add.keys()):
				max_num = max_num + 1
				with open(filename, "a+") as file:
					line = py2_encode_utf8(channels_to_add[key])+";"+str(max_num)
					channels_ordered.append(( py2_encode_utf8(channels_to_add[key]), max_num)) 
					file.write('%s\n' % line)

	except IOError:
		for offer in offers:
			post = {"locality" : locality, "tariff" : tariff, "isp" : isp, "language" : "ces", "deviceType" : addon.getSetting("devicetype"), "liveTvStreamingProtocol" : "HLS", "offer" : offer}
			data = call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data = urlencode(post), header = header)															   
			if "err" in data:
				showError("Problém s načtením kanálů")
				return
			if "channels" in data and len(data["channels"]) > 0:
				for channel in data["channels"]:
					if data["channels"][channel]["channelType"] == "TV":
						channels.update({data["channels"][channel]["channelNumber"] : data["channels"][channel]["channelName"]})
		if len(channels) > 0:
			with open(filename, "w") as file:
				for key in sorted(channels.keys()):
					line = py2_encode_utf8(channels[key])+";"+str(key)
					channels_ordered.append(( py2_encode_utf8(channels[key]), key)) 
					file.write('%s\n' % line)
	return channels_ordered		 

def edit_channel(channelName):
	num = -1
	channels = {}
	channels_ordered = []
	filename = addon_userdata_dir + "channels.txt"
	try:
		with open(filename, "r") as file:
			for line in file:
				channel = line[:-1].split(";")
				channels_ordered.append((channel[0], int(channel[1])))
	except IOError:
		showError("Problém s načtením kanálů")

	for offer in offers:
		post = {"locality" : locality, "tariff" : tariff, "isp" : isp, "language" : "ces", "deviceType" : addon.getSetting("devicetype"), "liveTvStreamingProtocol" : "HLS", "offer" : offer}
		data = call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data = urlencode(post), header = header)															   
		if "err" in data:
			showError("Problém s načtením kanálů")
			return
		if "channels" in data and len(data["channels"]) > 0:
			for channel in data["channels"]:
				if data["channels"][channel]["channelType"] == "TV":
					fnd = 0
					for channel_ordered in channels_ordered:
						if channel_ordered[0] == py2_encode_utf8(data["channels"][channel]["channelName"]):
							fnd = 1
					if fnd == 0:
						max_num = max_num + 1
						with open(filename, "a+") as file:
							line = data["channels"][channel]["channelName"].encode("utf-8")+";"+str(max_num)
							channels_ordered.append(( py2_encode_utf8(data["channels"][channel]["channelName"]), max_num)) 
							file.write('%s\n' % line)

	for channel in channels_ordered:
		if channel[0] == channelName:
			num = channel[1]
		else:
			channels.update({channel[1] : channel[0]})
	  
	new_num = client.getTextInput(session, "Číslo kanálu", str(num)) ### dodelat ziskani jen cisla
	if new_num and int(new_num) > 0:
		if int(new_num) in list(channels.keys()):
			showError("Číslo kanálu " + str(new_num) + " je už použité u kanálu " + channels[int(new_num)])
		else:	 
			channels[int(new_num)] = channelName
			channels.update({int(new_num) : channelName})
			with open(filename, "w") as file:
				for key in sorted(channels.keys()):
					line = channels[key]+";"+str(key)
					file.write('%s\n' % line)

############### IPTV ################

def generate_playlist():
	channels_ordered = load_channels()	
	channels = {}
	channel_data = {}

	filename = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'playlist.m3u')

	for offer in offers:
		post = {"locality" : locality, "tariff" : tariff, "isp" : isp, "language" : "ces", "deviceType" : addon.getSetting("devicetype"), "liveTvStreamingProtocol" : "HLS", "offer" : offer}
		data = call_o2_api(url = "https://app.o2tv.cz/sws/server/tv/channels.json", data = urlencode(post), header = header)															   
		if "err" in data:
			showError("Problém s načtením kanálů")
			return
	
		if "channels" in data and len(data["channels"]) > 0:
			for channel in data["channels"]:
				if data["channels"][channel]["channelType"] == "TV":
					for channel_ordered in channels_ordered:
						if(channel_ordered[0] == py2_encode_utf8(data["channels"][channel]["channelName"])):
							num = channel_ordered[1]
					  
					channels.update({ num : {"channelName" : data["channels"][channel]["channelName"], "channelKey" : data["channels"][channel]["channelKey"]}})

	data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", data = None, header = header_unity)															   
	if "err" in data:
		showError("Problém s načtením kanálů")
		return
	if "result" in data and len(data["result"]) > 0:
		for channel in data["result"]:
			channel_data.update({channel["channel"]["channelKey"] : "https://www.o2tv.cz/" + channel["channel"]["images"]["color"]["url"]});

	with open(filename, "w") as file:
		file.write('%s\n' % "#EXTM3U")
		for channel in sorted(channels.keys()):  
			if channels[channel]["channelKey"] in channel_data:	  
				logo = py2_encode_utf8(channel_data[channels[channel]["channelKey"]])
			else:
				logo = ""	 
			line = "#EXTINF:-1 tvh-epg=\"0\" tvg-logo=\"" + logo + "\"," + py2_encode_utf8(channels[channel]["channelName"])
			file.write('%s\n' % line)
			line = "?action=get_stream_url&channelKey=" + py2_encode_utf8(channels[channel]["channelKey"])
			file.write('%s\n' % line)
		  
	showInfo("Playlist byl uložen")

def get_stream_url(channelKey):
	post = {"serviceType" : "LIVE_TV", "deviceType" : addon.getSetting("devicetype"), "streamingProtocol" : "HLS", "subscriptionCode" : subscription, "channelKey" : channelKey, "encryptionType" : "NONE"}
	if addon.getSetting("only_sd") == "true":
		post.update({"resolution" : "SD"})
	data = call_o2_api(url = "https://app.o2tv.cz/sws/server/streaming/uris.json", data = urlencode(post), header = header)

	if "err" in data:
		showError("Problém s přehráním streamu")
		return

	url = ""
	if "uris" in data and len(data["uris"]) > 0 and "uri" in data["uris"][0] and len(data["uris"][0]["uri"]) > 0 :
		for uris in data["uris"]:
			if addon.getSetting("only_sd") is not "true" and uris["resolution"] == "HD":
				url = uris["uri"]
		if url == "":
			url = data["uris"][0]["uri"]

		epgId = 0
		data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/channels/", data = None, header = header_unity)
		if "err" in data:
			showError("Problém s načtením datailů")
			return
	  
		if "result" in data and len(data["result"]) > 0:
			for channel in data["result"]:
				if py2_encode_utf8(channel["channel"]["channelKey"]) == channelKey and "live" in channel:
					epgId = channel["live"]["epgId"]
		if epgId != 0:
			data = call_o2_api(url = "https://api.o2tv.cz/unity/api/v1/programs/" + str(epgId) + "/", data = None, header = header_unity)
			if "err" in data:
				showError("Problém s načtením programu")
				return
	  
			img = "";
			plot = "";
			if "images" in data and len(data["images"]) > 0:
				 plot = data["longDescription"]
				 img = data["images"][0]["cover"]
	
		add_video( py2_encode_utf8(data["name"]),url)
#		playlist=xbmc.PlayList(1)
#		playlist.clear()
#		list_item = xbmcgui.ListItem(py2_encode_utf8(data["name"]))
#		xbmc.PlayList(1).add(url, list_item)
#		xbmc.Player().play(playlist)


############### main ################

day_translation = {"Monday" : "Pondělí", "Tuesday" : "Úterý", "Wednesday" : "Středa", "Thursday" : "Čtvrtek", "Friday" : "Pátek", "Saturday" : "Sobota", "Sunday" : "Neděle"}  
day_translation_short = {"Monday" : "Po", "Tuesday" : "Út", "Wednesday" : "St", "Thursday" : "Čt", "Friday" : "Pá", "Saturday" : "So", "Sunday" : "Ne"}	

def router(paramstring):
	params = dict(parse_qsl(paramstring))
	if params:
		if params["action"] == "list_channels":
			list_channels()
		elif params["action"] == "list_days":
			list_days(params["channelKey"])
		elif params['action'] == 'list_program':
			list_program(params["channelKey"], params["day_min"])
		elif params['action'] == 'future_program':
			future_program(params["channelKey"])
		elif params["action"] == "list_recordings":
			list_recordings()
		elif params["action"] == "list_future_recordings":
			list_future_recordings()
		elif params["action"] == "delete_recording":
			delete_recording(params["pvrProgramId"])
		elif params["action"] == "add_recording":
			add_recording(params["epgId"])
		elif params['action'] == 'play_video':
			play_video(params["channelKey"], params["start"], params["end"], params["epgId"])
		elif params['action'] == 'play_live':
			play_live(params["channelKey"], params["title"])
		elif params['action'] == 'play_recording':
			play_recording(params["pvrProgramId"], params["title"])
		elif params['action'] == 'list_search':
			list_search()
		elif params['action'] == 'program_search':
			program_search(params["query"])
		elif params['action'] == 'list_channels_list':
			list_channels_list()
		elif params['action'] == 'get_o2_channels_lists':
			get_o2_channels_lists()
		elif params['action'] == 'load_o2_channel_list':
			load_o2_channel_list(params["list"])			
		elif params['action'] == 'reset_channel_list':
			reset_channel_list()			
		elif params['action'] == 'list_channels_edit':
			list_channels_edit()
		elif params['action'] == 'edit_channel':
			edit_channel(params["channelName"])
		elif params['action'] == 'generate_playlist':
			generate_playlist()
		elif params['action'] == 'get_stream_url':
			get_stream_url(params["channelKey"])
		else:
			raise ValueError('Invalid paramstring: {0}!'.format(paramstring))
	else:
		list_menu()

url=params['url'][1:] if 'url' in params else urlencode(params)
writeLog("URL: "+url)

chk = False
if check_settings():
	if "@" in addon.getSetting("username"):
		gat = get_auth_token()
		if gat:
			access_token, subscription, isp, locality, offers, tariff = gat
			chk = True
	else:
		gap = get_auth_password()
		if gap:
			access_token, subscription, isp, locality, offers, tariff = gap
			chk = True
	if chk: router(url)

if len(client.GItem_lst[0]) == 0:
	addDir('Chyba: Nezadane prihlasovaci udaje','',1,None)
