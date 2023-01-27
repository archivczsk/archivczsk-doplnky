# modified addon.py from https://github.com/StepanOrt/kodi-addons/blob/master/plugin.video.ivysilani/addon.py 
# for archivCZSK enigma2 plugin by mx3L

import re
import xml.etree.ElementTree as ET
import time
import os
import sys
import traceback
import json
from datetime import datetime, timedelta
import time
import random

import util
from provider import ContentProvider
import ivysilani

try:
	import cookielib
	from urllib2 import urlopen, HTTPCookieProcessor, build_opener, install_opener
	from urlparse import urlparse
	from urllib import quote_plus, unquote_plus
	is_py3 = False
except:
	from urllib.request import urlopen, HTTPCookieProcessor, build_opener, install_opener
	from urllib.parse import urlparse, quote_plus, unquote_plus
	import http.cookiejar as cookielib
	is_py3 = True
	unicode = str

_baseurl_ = ""


def get_params(url):
	params = url
	cleanedparams = params.replace('?', '')
	if (params[len(params) - 1] == '/'):
		params = params[0:len(params) - 2]
	pairsofparams = cleanedparams.split('&')
	param = {}
	for i in range(len(pairsofparams)):
		splitparams = {}
		splitparams = pairsofparams[i].split('=')
		if (len(splitparams)) == 2:
			param[splitparams[0]] = splitparams[1]
	return param

def _lang_(ID):
	return '$' + str(ID)

def _toString(text):
	if is_py3 == False and isinstance(text, unicode):
		output = text.encode('utf-8')
	else:
		output = str(text)
	return output

class iVysilaniContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
		ContentProvider.__init__(self, 'ivysilani.cz', 'http://ivysilani.cz', username, password, filter, tmp_dir)
		opener = build_opener(HTTPCookieProcessor(cookielib.LWPCookieJar()))
		install_opener(opener)

	def capabilities(self):
		return ['categories','resolve']

	def categories(self):
		result = []
		spotlight_labels = { "tipsMain": 30019,
							 "topDay": 30020,
							 "topWeek": 30021,
							 "tipsNote": 30022,
							 "tipsArchive": 30023,
							 "watching": 30024 }
		item = self.dir_item()
		item['title'] = _lang_(30015)
		item['url'] = _baseurl_ + "?menu=live"
		result.append(item)
		item = self.dir_item()
		item['title'] = _lang_(30016)
		item['url'] =  _baseurl_ + "?menu=byDate"
		result.append(item)
		item = self.dir_item()
		item['title'] = _lang_(30017)
		item['url'] = _baseurl_ + "?menu=byLetter"
		result.append(item)
		item = self.dir_item()
		item['title'] =_lang_(30018)
		item['url'] =  _baseurl_ +"?menu=byGenre"
		result.append(item)
		for spotlight in ivysilani.SPOTLIGHTS:
			item = self.dir_item()
			item['title'] = _lang_(spotlight_labels[spotlight.ID])
			item['url'] =  _baseurl_ + "?menu=" + spotlight.ID
			result.append(item)
		return result

	def list(self, url):
		param = get_params(url)
		menu = param.get('menu')
		genre = param.get('genre')
		letter = param.get('letter')
		date = param.get('date')
		channel = param.get('channel')
		related = param.get('related')
		episodes = param.get('episodes')
		bonuses = param.get('bonuses')
		page = param.get('page', 1)
		
		if genre:
			for g in ivysilani.genres():
				if g.link == genre:
					return self.listProgrammelist(g, episodes=True)
		elif letter:
			letter = unquote_plus(letter)
			for l in ivysilani.alphabet():
				if _toString(l.link) == _toString(letter):
					return self.listProgrammelist(l, episodes=True)
		elif date and channel:
			return self.listProgrammelist(ivysilani.Date(date, self.selectLiveChannel(channel)))
		else:
			if date:
				return self.listChannelsForDate(date)
			elif related:
				return self.listContext("related", related, page)
			elif episodes:
				return self.listContext("episodes", episodes, page)
			elif bonuses:
				return self.listContext("bonuses", bonuses, page)
			elif menu:
				if menu == "live":
					return self.listLiveChannels()
				elif menu == "byDate":
					return self.listDates()
				elif menu == "byLetter":
					return self.listAlphabet()
				elif menu == "byGenre":
					return self.listGenres()
				else:
					for spotlight in ivysilani.SPOTLIGHTS:
						if spotlight.ID == menu:
							return self.listProgrammelist(spotlight)
	
	def listLiveChannels(self):
		result = []
		for liveChannel in ivysilani.LIVE_CHANNELS:
			title = _toString(liveChannel.title)
			live_programme = liveChannel.programme()
			if hasattr(live_programme, "title") and live_programme.title:
				title += ": " + _toString(live_programme.title)
			plot = None
			if hasattr(live_programme, "time") and live_programme.time:
				plot = _toString(_lang_(30001)) + " " + _toString(live_programme.time)
			if hasattr(live_programme, "elapsedPercentage") and live_programme.elapsedPercentage:
				plot += " (" + _toString(live_programme.elapsedPercentage) + "%)"
			if hasattr(live_programme, "synopsis") and live_programme.synopsis:
				plot += "\n\n" + _toString(live_programme.synopsis)
			if hasattr(live_programme, "ID") and live_programme.ID:
				try:
					programme = ivysilani.Programme(live_programme.ID)
					if programme.videoURL:
							url = _baseurl_ + "?play=" + liveChannel.ID
							item = self.video_item()
							item['title'] = title
							item['url'] = url
							item['plot'] = plot
							item['image'] = live_programme.imageURL
							result.append(item)
							#addDirectoryItem(title, url, ID=liveChannel.ID, plot=plot, image=live_programme.imageURL)
							continue
				except:
					pass
			title += " [" + _toString(_lang_(30002)) + "]"
			url = _baseurl_ + "?menu=live"
			item = self.dir_item()
			item['title'] = title
			item['url'] = url
			result.append(item)
			#addDirectoryItem(title, url, image=live_programme.imageURL)
		return result

	def listProgrammelist(self, programmelist, episodes=False):
		result = []
		pList = programmelist.list()
		for item in pList:
			plot = None
			date = None
			if hasattr(item, "synopsis") and item.synopsis:
				plot = item.synopsis
			if episodes:
				url =  _baseurl_ + "?episodes=" + item.ID
			else:
				url = _baseurl_ + "?play=" + item.ID
			title = item.title
			if hasattr(item, 'time'):
				title = "[" + item.time + "] " + title
			active = True
			if hasattr(item, 'active'):
				active = (item.active == '1')
			if active:
				if episodes:
					itm = self.dir_item()
				else:
					itm = self.video_item()
				itm['title'] = title
				itm['plot'] = plot
				itm['url'] = url
				itm['img'] = item.imageURL
				itm['menu'] = {}
				itm['menu'][_lang_(30003)] =  {'list':_baseurl_ + "?related=" + item.ID, 'action-type':'list'}
				itm['menu'][_lang_(30004)] = {'list':_baseurl_ + "?episodes=" + item.ID, 'action-type':'list'}
				itm['menu'][_lang_(30005)] = {'list':_baseurl_ + "?bonuses=" + item.ID, 'action-type':'list'}
				result.append(itm)
				#addDirectoryItem(title, url, ID=item.ID, related=True, episodes=episodes, plot=plot, date=date, image=item.imageURL)
		return result
		
	def selectLiveChannel(self, ID):
		for liveChannel in ivysilani.LIVE_CHANNELS:
			if liveChannel.ID == ID:
				return liveChannel

	def listAlphabet(self):
		result = []
		for letter in ivysilani.alphabet():
			item = self.dir_item()
			item['title'] = letter.title
			item['url'] = _baseurl_ + "?letter=" + quote_plus(_toString(letter.link))
			result.append(item)
			#addDirectoryItem(letter.title, _baseurl_ + "?letter=" + quote_plus(_toString(letter.link)))
		return result

	def listGenres(self):
		result = []
		for genre in ivysilani.genres():
			item = self.dir_item()
			item['title'] = genre.title
			item['url'] = _baseurl_ + "?genre=" + quote_plus(_toString(genre.link))
			result.append(item)
			#addDirectoryItem(genre.title, _baseurl_ + "?genre=" + quote_plus(_toString(genre.link)))
		return result

	def listDates(self):
		result = []
		day_names = []
		for i in range(7):
			day_names.append(_lang_(31000 + i))
		dt = datetime.now();
		min_date = datetime.fromtimestamp(time.mktime(time.strptime(ivysilani.DATE_MIN, "%Y-%m-%d")))
		while dt > min_date:
			pretty_date = day_names[dt.weekday()] + " " + dt.strftime("%d.%m.%Y")
			formated_date = dt.strftime("%Y-%m-%d")
			item = self.dir_item()
			item['title'] = pretty_date
			item['url'] =  _baseurl_ + "?date=" + quote_plus(formated_date)
			result.append(item)
			# addDirectoryItem(pretty_date, _baseurl_ + "?date=" + quote_plus(formated_date))
			dt = dt - timedelta(days=1)
		return result

	def listChannelsForDate(self, date):
		result = []
		for channel in ivysilani.LIVE_CHANNELS:
			image = ""#os.path.join(_addon_.getAddonInfo('path'), 'resources', 'media', 'logo_' + channel.ID.lower() + '_400x225.png')
			url = _baseurl_ + "?date=" + quote_plus(date) + "&channel=" + channel.ID
			item = self.dir_item()
			item['title'] = _toString(channel.title)
			item['url'] = url
			item['img'] = image
			result.append(item)
			#addDirectoryItem(_toString(channel.title), url, image=image)
		return result
	
	def listContext(self, what, ID, page):
		result = []
		programme = ivysilani.Programme(ID)
		l = []
		if what == "related":
			l = programme.related(page)
		elif what == "episodes":
			l = programme.episodes(page)
		elif what == "bonuses":
			l = programme.bonuses(page)
		for item in l:
			plot = None
			if hasattr(item, "synopsis") and item.synopsis:
				plot = item.synopsis
			itm = self.video_item()
			itm['title'] = item.title
			itm['url'] =  _baseurl_ + "?play=" + str(item.ID)
			itm['plot'] = plot
			itm['img'] = item.imageURL
			# cm.append((_lang_(30003), "XBMC.Container.Update(" + _baseurl_ + "?related=" + ID + ")"))
			# cm.append((_lang_(30004), "XBMC.Container.Update(" + _baseurl_ + "?episodes=" + ID + ")"))
			# cm.append((_lang_(30005), "XBMC.Container.Update(" + _baseurl_ + "?bonuses=" + ID + ")"))
			itm['menu'] = {}
			itm['menu'][_lang_(30003)] =  {'list':_baseurl_ + "?related=" + item.ID, 'action-type':'list'}
			itm['menu'][_lang_(30004)] = {'list':_baseurl_ + "?episodes=" + item.ID, 'action-type':'list'}
			itm['menu'][_lang_(30005)] = {'list':_baseurl_ + "?bonuses=" + item.ID, 'action-type':'list'} 
			result.append(itm)
			#addDirectoryItem(item.title, _baseurl_ + "?play=" + item.ID, ID=item.ID, related=True, plot=plot, image=item.imageURL)
		if len(l) == ivysilani.PAGE_SIZE:
			item = self.dir_item()
			item['title'] = '[B]' + _lang_(30006) + ' >>[/B]'
			item['url'] = _baseurl_ + "?" + what + "=" + str(ID) + "&page=" + str(int(page)+1)
			#item['img'] =	_next_
			result.append(item)
		   # addDirectoryItem('[B]' + _lang_(30006) + ' >>[/B]', _baseurl_ + "?" + what + "=" + ID + "&page=" + str(page + 1), image=_next_)
		return result
	
	def resolve(self, item, captcha_cb=None, select_cb=None):
		result = []
		item = item.copy()
		play = get_params(item['url'])['play']
		playable = self.selectLiveChannel(play)
		if not playable:
			playable = ivysilani.Programme(play)
			image = "" #os.path.join(_addon_.getAddonInfo('path'), 'resources', 'media', 'logo_' + playable.ID.lower() + '_400x225.png')
		if isinstance(playable, ivysilani.Programme):
			image = playable.imageURL
		manifest = util.request(playable.url(ivysilani.Quality("web")))
		#for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+)\s(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
		
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+),AUDIO="\d+"\s(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
			item = self.video_item()
			item['title'] = _toString(playable.title)
			bandwidth = int(m.group('bandwidth'))
			if bandwidth < 628000:
				item['quality'] = "144p"
			if bandwidth >= 628000 and bandwidth < 1160000:
				item['quality'] = "288p"
			elif bandwidth >= 1160000 and bandwidth < 2176000:
				item['quality'] = "404p"
			elif bandwidth >= 2176000 and bandwidth < 3712000:
				item['quality'] = "576p"
			elif bandwidth >= 3712000 and bandwidth < 6272000:
				item['quality'] = "720p"	
			else:
				item['quality'] = "1080p"
			item['url'] = m.group('chunklist')
			result.append(item)
		result = sorted(result,key=lambda i:(len(i['quality']),i['quality']), reverse = True)
		if len(result) > 0 and select_cb:
			return select_cb(result)
		
		return result
