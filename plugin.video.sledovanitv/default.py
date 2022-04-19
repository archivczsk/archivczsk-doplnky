# -*- coding: utf-8 -*-
#
# addon by misanov (c)2020 https://github.com/misanov
#

import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime, timedelta 
from datetime import date

try:
	from urllib import urlencode, quote, unquote_plus
	from urlparse import parse_qsl
	from urllib2 import urlopen, Request, HTTPError
	
	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

except:
	from urllib.request import urlopen, Request
	from urllib.parse import quote, unquote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError
	
	def py2_encode_utf8( text ):
		return text

	def py2_decode_utf8( text ):
		return text


from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video
from Plugins.Extensions.archivCZSK.engine import client
from Components.config import config

############### init ################
addon = ArchivCZSK.get_xbmc_addon('plugin.video.sledovanitv')
addon_userdata_dir = addon.getAddonInfo('profile')
home = addon.getAddonInfo('path')
icon = os.path.join(home, 'icon.png')
sessid = addon.getSetting("sessionid")
pin = addon.getSetting("pin")
apitime = int(time.time())

headers = {"User-Agent": "okhttp/3.12.0", "PHPSESSID": sessid}

LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'sledovanitv.log')
base_url = ""

def writeLog(msg, type='INFO'):
	try:
		f = open(LOG_FILE, 'a')
		dtn = datetime.now()
		f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
		f.close()
	except:
		pass

def _to_string(text):
	if type(text).__name__ == 'unicode':
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output

def showInfo(mmsg):
	client.showInfo(mmsg)

def showError(mmsg):
	client.showInfo(mmsg)

def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)

def get_url(**kwargs):
	return '{0}?{1}'.format(base_url, urlencode(kwargs))

def check_settings():
	if not addon.getSetting("serialid"):
		addon.setSetting("serialid",''.join(random.choice('0123456789abcdef') for n in range(40)))
	if not addon.getSetting("username") or not addon.getSetting("password"):
		showError('V nastavení je nutné mít vyplněné všechny přihlašovací údaje')
		return False
	return True

def call_api(url, data, header):
	request = Request(url = url , data = data.encode('utf-8'), headers = header)
	try:
		html = urlopen(request).read().decode('utf-8')
		if html and len(html) > 0:
			data = json.loads(html)
			return data
		else:
			return []
	except HTTPError as e:
		return { "err" : e.reason }				
  
def get_pairing():
	data = call_api(url = "https://sledovanitv.cz/api/create-pairing?username="+addon.getSetting("username")+"&password="+addon.getSetting("password")+"&type=androidportable&serial="+addon.getSetting("serialid")+"&product=Xiaomi%3ARedmi+Note+7&unit=default&checkLimit=1", data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém při přihlášení: %s"%data['error'])
		return

	if 'deviceId' in data and 'password' in data:
		data = call_api(url = "https://sledovanitv.cz/api/device-login?deviceId="+str(data['deviceId'])+"&password="+data['password']+"&version=2.7.4&lang=cs&unit=default", data = "", header = headers)
		if "status" not in data or data['status'] is 0:
			showError("Problém při přihlášení: %s"%data['error'])
			return

		if "PHPSESSID" in data:
			addon.setSetting("sessionid", data["PHPSESSID"])
			data = call_api(url = "https://sledovanitv.cz/api/keepalive?PHPSESSID="+data["PHPSESSID"], data = "", header = headers)
		else:
			showError("Problém s příhlášením: no session")
			return
	else:
		showError("Problém s příhlášením: no deviceid")
		return

def get_user_data():
	data = call_api(url = "https://sledovanitv.cz/api/get-user-info/?PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém při získání uživatelských dat: %s"%data['error'])
		return

def get_time():
	data = call_api(url = "https://sledovanitv.cz/api/time", data = "", header = headers)
	if "timestamp" in data:
		apitime = data['timestamp']

def getHome():
	data = call_api(url = "https://sledovanitv.cz/api/content-home?PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
#		showError("Problém při získání úvodu: %s"%data['error'])
		get_pairing()
		return

def compare_time(t):
	d = (t.replace(" ", "-").replace(":", "-")).split("-")
	now = datetime.now()
	start_time = now.replace(year=int(d[0]), month=int(d[1]), day=int(d[2]), hour=int(d[3]), minute=int(d[4]), second=0, microsecond=0)
	return start_time < now

def archiv_channels():
	data = call_api(url = "https://sledovanitv.cz/api/playlist?uuid="+addon.getSetting("serialid")+"&format=m3u8&quality=40&drm=widevine&capabilities=adaptive2&cast=chromecast&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením kanálů: %s"%data['error'])
		return False
	if 'channels' in data:
		for d in data['channels']:
			if d["timeshiftDuration"] != 0 and d["type"] == "tv":
				thumb = d["logoUrl"] if "logoUrl" in d else None
				tsd = int(d["timeshiftDuration"]/60/60/24)
				if tsd == 1: dtext=" den"
				elif tsd <5: dtext=" dny"
				else: dtext=" dní"
				addDir(d["name"]+" [COLOR green]["+str(tsd)+dtext+"][/COLOR]", get_url(action='archiv_days', cid = d["id"], days=tsd), 1, thumb)

def future_days(cid):
	for i in range(0,-15,-1):
		day = date.today() - timedelta(days = i)
		if i == 0:
			den = "Dnes"
		elif i == 1:
			den = "Včera"
		else:
			if day.strftime("%A") in day_translation:
				den = py2_decode_utf8(day_translation[day.strftime("%A")]) + " " + day.strftime("%d.%m.%Y")
			else:
				den = py2_decode_utf8(day.strftime("%A")) + " " + day.strftime("%d.%m.%Y")
				
		url = get_url(action='archiv_videos', cid=cid, day=day.strftime("%Y-%m-%d+00%%3A00"), future=1)
		addDir(den, url, 1, None)

def archiv_days(cid,days):
	addDir('Budoucí (nastavení nahrávek)', get_url(action='future_days', cid=cid), 1, None)
	for i in range(int(days)+1):
		day = date.today() - timedelta(days = i)
		if i == 0:
			den = "Dnes"
		elif i == 1:
			den = "Včera"
		else:
			if day.strftime("%A") in day_translation:
				den = py2_decode_utf8(day_translation[day.strftime("%A")]) + " " + day.strftime("%d.%m.%Y")
			else:
				den = py2_decode_utf8(day.strftime("%A")) + " " + day.strftime("%d.%m.%Y")
				
		url = get_url(action='archiv_videos', cid=cid, day=day.strftime("%Y-%m-%d+00%%3A00"), future=0)
		addDir(den, url, 1, None)

def archiv_videos(cid,day,future):
	data = call_api(url = "https://sledovanitv.cz/api/epg?time="+day+"&duration=1439&detail=description%2Cposter&allowOrder=true&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením archivu: %s"%data['error'])
		return False
	if 'channels' in data and cid in data['channels']:
		for event in data['channels'][cid]:
			title = event["startTime"][-5:] + "-" + event["endTime"][-5:] + " - " + event["title"]
			desc = event["description"] if 'description' in event else ""
			duration = event["duration"]*60 if 'duration' in event else None
			year = event["year"] if 'year' in event else None
			thumb = event["poster"] if 'poster' in event else None
			if event["availability"] == "timeshift":
				if future == "0" and compare_time(event["startTime"]) == True or future == "1" and compare_time(event["startTime"]) == False:
					addDir(title, get_url(action='play_event', eventid=event['eventId']), 1, thumb, infoLabels={'plot':desc, 'duration':duration, 'year':year}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': event["eventId"]}})

def list_channels():
	data = call_api(url = "https://sledovanitv.cz/api/playlist?uuid="+addon.getSetting("serialid")+"&format=m3u8&quality=40&drm=widevine&capabilities=adaptive2&cast=chromecast&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením kanálů: %s"%data['error'])
		return False
	now = datetime.now()
	epgdata = call_api(url = "https://sledovanitv.cz/api/epg?time="+now.strftime("%Y-%m-%d+%H%%3A%M")+"&duration=60&detail=description%2Cposter&allowOrder=true&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in epgdata or epgdata['status'] is 0:
		showError("Problém s načtením EPG: %s"%data['error'])

	playlist = "#NAME Sledovani TV\n"
	count = 0
	if 'channels' in data:
		for channel in data['channels']:
			if channel['locked'] != 'none' and channel['locked'] != 'pin': continue
			title = " (" + epgdata['channels'][channel["id"]][0]["title"] + " - " + epgdata['channels'][channel["id"]][0]["startTime"][-5:] + "-" + epgdata['channels'][channel["id"]][0]["endTime"][-5:] + ")" if 'channels' in epgdata else ""
			desc = epgdata['channels'][channel["id"]][0].get('description')
			thumb = epgdata['channels'][channel["id"]][0].get('poster')
			duration = epgdata['channels'][channel["id"]][0].get('duration')*60
			year = epgdata['channels'][channel["id"]][0].get('year')
			if channel['locked'] == 'pin':
				dname = '[COLOR red]' + channel["name"] + title + '[/COLOR]'
			else:
				dname = channel["name"]+'[COLOR yellow]'+title+'[/COLOR]'
			if channel['type'] != 'radio':
				addDir(dname, get_url(action='play', title=py2_encode_utf8(channel["name"]+title), url=channel["url"]), 1, thumb, infoLabels={'plot':desc,'duration':duration,'year':year}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': epgdata['channels'][channel["id"]][0]["eventId"]}})
				playlist += "#SERVICE 4097:0:1:"+str(count)+":0:0:0:0:0:0:"+channel['url'].replace(":","%3a")+": "+_to_string(channel["name"])+"\n#DESCRIPTION "+_to_string(channel["name"]+title)+"\n"
				count = count + 1
	else:
		showError("Problém s načtením kanálů: no channels")
		return
	f = open(os.path.join(config.plugins.archivCZSK.logPath.getValue(),'sledovanitv.pls'), 'w')
	f.write(playlist)
	f.close()
	return True

def list_radios():
	data = call_api(url = "https://sledovanitv.cz/api/playlist?uuid="+addon.getSetting("serialid")+"&format=m3u8&quality=40&drm=widevine&capabilities=adaptive2&cast=chromecast&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením kanálů: %s"%data['error'])
		return False
	now = datetime.now()
	epgdata = call_api(url = "https://sledovanitv.cz/api/epg?time="+now.strftime("%Y-%m-%d+%H%%3A%M")+"&duration=60&detail=description%2Cposter&allowOrder=true&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in epgdata or epgdata['status'] is 0:
		showError("Problém s načtením EPG: %s"%data['error'])

	if 'channels' in data:
		for channel in data['channels']:
			thumb = channel["logoUrl"] if "logoUrl" in channel else None
			title = " (" + epgdata['channels'][channel["id"]][0]["title"] + " - " + epgdata['channels'][channel["id"]][0]["startTime"][-5:] + "-" + epgdata['channels'][channel["id"]][0]["endTime"][-5:] + ")" if 'channels' in epgdata else ""
			desc = epgdata['channels'][channel["id"]][0].get('description')
			duration = epgdata['channels'][channel["id"]][0].get('duration')*60
			year = epgdata['channels'][channel["id"]][0].get('year')
			if channel['locked'] != 'none': continue
			if channel['type'] == 'radio':
				add_video(channel["name"]+'[COLOR yellow]'+title+'[/COLOR]', channel["url"], None, thumb, infoLabels={'plot':desc,'duration':duration,'year':year})
	else:
		showError("Problém s načtením kanálů: no channels")
		return
	return True

def list_recordings():
	data = call_api(url = "https://sledovanitv.cz/api/get-pvr?PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením nahrávek: %s"%data['error'])
		return False
	if 'records' in data:
		for record in data['records']:
			duration = record["eventDuration"] if "eventDuration" in record else None
			year = record["event"]["year"] if "event" in record and 'year' in record["event"] else None
			thumb = record["event"]["poster"] if "event" in record and 'poster' in record["event"] else None
			desc = record["event"]["title"]+' - '+record["event"]["description"] if 'event' in record and 'description' in record["event"] else ""
			cas = datetime.strptime(record["event"]["startTime"],"%Y-%m-%d %H:%M").strftime("%d.%m %H:%M") + " - " + datetime.strptime(record["event"]["endTime"],"%Y-%m-%d %H:%M").strftime("%d.%m %H:%M")
			desc += ' [expiruje '+datetime.strptime(record["expires"],"%Y-%m-%d").strftime("%d.%m.%Y")+']' if 'expires' in record else ''
			title = record['event']["startTime"][8:10] + "." + record['event']["startTime"][5:7] + ". " + record['event']["startTime"][11:16] + "-" + record['event']["endTime"][11:16] + " [" + record["channelName"] + "] [COLOR yellow]" + record["title"] + "[/COLOR]"
			if record["enabled"]==1:
				addDir(title, get_url(action='play_rec', recid=record["id"]), 1, thumb, infoLabels={'plot':desc,'duration':duration,'year':year}, menuItems={'Smazat nahrávku': {'action': 'del_rec', 'recid': record["id"]}})
			else:
				addDir('[COLOR grey]'+title+'[/COLOR]', get_url(action='play_rec', recid=record["id"]), 1, thumb, infoLabels={'plot':desc,'duration':duration,'year':year}, menuItems={'Smazat nahrávku': {'action': 'del_rec', 'recid': record["id"]}})
	return True

def set_rec(eventid):
	data = call_api(url = "https://sledovanitv.cz/api/record-event?eventId="+eventid+"&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s nastavením nahrávky: %s"%data['error'])
		return
	showInfo("Nahrávka nastavena")
	list_recordings()

def del_rec(recid):
	data = call_api(url = "https://sledovanitv.cz/api/delete-record?recordId="+recid+"&do=delete&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém se smazáním nahrávky: %s"%data['error'])
		return
	showInfo("Nahrávka smazána")
	list_recordings()

def list_search():
	query = client.getTextInput(session, "Hledat")
	if len(query) == 0:
		showError("Je potřeba zadat vyhledávaný řetězec")
		return
	data = call_api(url = "https://sledovanitv.cz/api/epg-search?query="+query+"&detail=description%2Cposter&allowOrder=true&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením vyhledávání: %s"%data['error'])
		return False
	if 'events' in data:
		for event in data['events']:
			title = event["startTime"][8:10] + "." + event["startTime"][5:7] + ". " + event["startTime"][-5:] + " [" + event["channel"].upper() + "] " + event["title"]
			desc = event["description"] if 'description' in event else ""
			duration = event["duration"]*60 if 'duration' in event else None
			year = event["year"] if 'year' in event else None
			thumb = event["poster"] if 'poster' in event else None
			if event["availability"] == "timeshift":
					addDir(title, get_url(action='play_event', eventid=event['eventId']), 1, thumb, infoLabels={'plot':desc, 'duration':duration, 'year':year}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': event["eventId"]}})
	return True

def list_home():
	data = call_api(url = "https://sledovanitv.cz/api/show-category?category=box-homescreen&detail=events%2Csubcategories&eventCount=1&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením kanálů: %s"%data['error'])
		return False
	if 'info' in data and 'items' in data['info']:
		catitle = "["+data['info']['title']+"] " if 'title' in data['info'] else ""
		for item in data['info']['items']:
			if item['events'][0]['availability'] != "timeshift": continue
			title = item['events'][0]["startTime"][8:10] + "." + item['events'][0]["startTime"][5:7] + ". " + item['events'][0]["startTime"][11:16] + "-" + item['events'][0]["endTime"][11:16] + " [" + item['events'][0]["channel"].upper() + "] " + item["title"]
			desc = item["description"] if 'description' in item else ""
			thumb = item["poster"] if 'poster' in item else None
			addDir(title, get_url(action='play_event', eventid=item['events'][0]['eventId']), 1, thumb, infoLabels={'plot':catitle+desc}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': item['events'][0]["eventId"]}})
	if 'subcategories' in data:
		for category in data['subcategories']:
			catitle = "["+category['title']+"] " if 'title' in category else ""
			if 'items' in category:
				for item in category['items']:
					if item['events'][0]['availability'] != "timeshift": continue
					title = item['events'][0]["startTime"][8:10] + "." + item['events'][0]["startTime"][5:7] + ". " + item['events'][0]["startTime"][11:16] + "-" + item['events'][0]["endTime"][11:16] + " [" + item['events'][0]["channel"].upper() + "] " + item["title"]
					desc = item["description"] if 'description' in item else ""
					thumb = item["poster"] if 'poster' in item else None
					duration = item['events'][0].get('duration')
					if compare_time(item["events"][0]["startTime"]):
						addDir(title, get_url(action='play_event', eventid=item['events'][0]['eventId']), 1, thumb, infoLabels={'plot':catitle+desc,'duration':duration}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': item['events'][0]["eventId"]}})
					else:
						addDir('[COLOR grey]'+title+'[/COLOR]', get_url(action='play_event', eventid=item['events'][0]['eventId']), 1, thumb, infoLabels={'plot':catitle+desc,'duration':duration}, menuItems={'Nahrát pořad': {'action': 'set_rec', 'eventid': item['events'][0]["eventId"]}})

def list_continue():
	data = call_api(url = "https://sledovanitv.cz/api/continue-watching?detail=description%2Cscore%2Cposter%2Cbackdrop%2Cgenres&overrun=true&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením pořadů: %s"%data['error'])
		return False

def play(title, url, subs=None):
	res = []
#	data = call_api(url = "https://sledovanitv.cz/api/pin-lock?PHPSESSID="+sessid, data = "", header = headers)
	data = call_api(url = "https://sledovanitv.cz/api/is-pin-locked?PHPSESSID="+sessid, data = "", header = headers)
	if data['pinLocked'] == 1 and pin != "":
		data = call_api(url = "https://sledovanitv.cz/api/pin-unlock?pin="+str(pin)+"&whiteLogo=true&PHPSESSID="+sessid, data = "", header = headers)
		if data.get('error'):
			showError("Špatný PIN")
			return
	try:
		req = requests.get(url)
	except:
		showError("Problém při načtení videa. Pokud je červené, zadejte v nastavení správný PIN!")
		return
	if req.status_code != 200:
		showError("Problém při načtení videa z %s: %s"%(url,req.status_code))
		return
	r = req.text
	for m in re.finditer('#EXT-X-STREAM-INF:.*?,RESOLUTION=(?P<resolution>[^\s]+)\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
		itm = {}
		itm['quality'] = m.group('resolution')
		itm['url'] = m.group('chunklist')
		res.append(itm)
	res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
	for stream in res:
		add_video('['+stream['quality']+'] '+py2_decode_utf8(title),stream['url'],subs=subs)

def play_event(eventid):
	data = call_api(url = "https://sledovanitv.cz/api/event-timeshift?format=m3u8&eventId="+eventid+"&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením nahrávky: %s"%data['error'])
		return
	subs = None
#	if 'subtitles' in data:						### vtt titulky prehravac zatim nepodporuje!
#		for sub in data['subtitles']:
#			if sub.get('lang') == "cze":
#				subs = sub.get('url')
	play(py2_encode_utf8(data["event"]["title"]),data["url"],subs)

def play_rec(recid):
	data = call_api(url = "https://sledovanitv.cz/api/record-timeshift?format=m3u8&recordId="+recid+"&PHPSESSID="+sessid, data = "", header = headers)
	if "status" not in data or data['status'] is 0:
		showError("Problém s načtením nahrávky: %s"%data['error'])
		return
	play(py2_encode_utf8(data["event"]["title"]),data["url"])

def list_menu():
	addDir("Úvodní stránka", get_url(action='list_home'), 1, None)
	addDir("Živě", get_url(action='list_channels'), 1, None)
	addDir("Rádia", get_url(action='list_radios'), 1, None)
	addDir("Archiv", get_url(action='archiv_channels'), 1, None)
	addDir("Nahrávky", get_url(action='list_recordings'), 1, None)
	addDir("Vyhledávání", get_url(action='list_search'), 1, None)
#	addDir("Pokračovat", get_url(action='list_continue'), 1, None)


day_translation = {"Monday" : "Pondělí", "Tuesday" : "Úterý", "Wednesday" : "Středa", "Thursday" : "Čtvrtek", "Friday" : "Pátek", "Saturday" : "Sobota", "Sunday" : "Neděle"}  
day_translation_short = {"Monday" : "Po", "Tuesday" : "Út", "Wednesday" : "St", "Thursday" : "Čt", "Friday" : "Pá", "Saturday" : "So", "Sunday" : "Ne"}	

def router(paramstring):
	params = dict(parse_qsl(paramstring))
	if params:
		if params["action"] == "list_channels":
			list_channels()
		elif params["action"] == "list_radios":
			list_radios()
		elif params["action"] == "archiv_channels":
			archiv_channels()
		elif params["action"] == "archiv_days":
			archiv_days(unquote_plus(params["cid"]),unquote_plus(params["days"]))
		elif params["action"] == "future_days":
			future_days(unquote_plus(params["cid"]))
		elif params["action"] == "archiv_videos":
			archiv_videos(unquote_plus(params["cid"]),params["day"],params["future"])
		elif params['action'] == 'list_recordings':
			list_recordings()
		elif params['action'] == 'set_rec':
			set_rec(unquote_plus(params["eventid"]))
		elif params['action'] == 'del_rec':
			del_rec(unquote_plus(params["recid"]))
		elif params['action'] == 'play':
			play(unquote_plus(params["title"]), unquote_plus(params["url"]))
		elif params['action'] == 'play_rec':
			play_rec(unquote_plus(params["recid"]))
		elif params['action'] == 'play_event':
			play_event(unquote_plus(params["eventid"]))
		elif params['action'] == 'archiv':
			archiv(unquote_plus(params["cid"]))
		elif params['action'] == 'list_search':
			list_search()
		elif params['action'] == 'list_home':
			list_home()
		elif params['action'] == 'list_continue':
			list_continue()
		else:
			raise ValueError('Invalid paramstring: {0}!'.format(paramstring))
	else:
		list_menu()

url=params['url'][1:] if 'url' in params else urlencode(params)

if check_settings():
	if not addon.getSetting("sessionid"):
		get_pairing()
	else:
		getHome()
	router(url)

if len(client.GItem_lst[0]) == 0:
	addDir('Nic nenalezeno nebo chyba','',1,None)
