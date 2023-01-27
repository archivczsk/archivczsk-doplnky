# -*- coding: UTF-8 -*-
# /*
# *	 Copyright (C) 2022 Michal Novotny https://github.com/misanov
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
import os
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client
import re,datetime,time,json

from tools_xbmc.contentprovider.xbmcprovider import XBMCMultiResolverContentProvider
from tools_xbmc.contentprovider.provider import ContentProvider
from tools_xbmc.tools import util
from tools_xbmc.compat import XBMCCompatInterface
from Components.config import config

try:
	import cookielib
	from urllib2 import HTTPCookieProcessor, HTTPError, build_opener, install_opener
except:
	from urllib.request import HTTPCookieProcessor, build_opener, install_opener
	import http.cookiejar as cookielib
	from urllib.error import HTTPError

LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'eurosport.log')
letters = "aábcčdďeéěfghiíjklmnňoóöpqrřsštťuúůvwxyýzžAÁBCČDĎEÉĚFGHIÍJKLMNŇOÓÖPQRŘSŠTŤUÚŮVWXYÝZŽ"

def writeLog(msg, type='INFO'):
	try:
		with open(LOG_FILE, 'a') as f:
			dtn = datetime.datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
	except:
		pass

def showInfo(mmsg):
	client.add_operation("SHOW_MSG", {'msg': mmsg, 'msgType': 'info', 'msgTimeout': 4, 'canClose': True })

def showError(mmsg):
	client.add_operation("SHOW_MSG", {'msg': mmsg, 'msgType': 'error', 'msgTimeout': 4, 'canClose': True })

def parse_date(dt,totime=False):
	if not dt:
		return ''
	utcdate=datetime.datetime.strptime(dt,'%Y-%m-%dT%H:%M:%SZ')
	now_timestamp=time.time()
	offset=datetime.datetime.fromtimestamp(now_timestamp)-datetime.datetime.utcfromtimestamp(now_timestamp)
	if totime:
		return (utcdate+offset)
	else:
		return (utcdate+offset).strftime('%d.%m.%Y %H:%M')

def is_now(df,dt):
	if not df or not dt: return False
	now_timestamp=time.time()
	now=datetime.datetime.fromtimestamp(now_timestamp)
	offset=datetime.datetime.fromtimestamp(now_timestamp)-datetime.datetime.utcfromtimestamp(now_timestamp)
	utcdf=datetime.datetime.strptime(df,'%Y-%m-%dT%H:%M:%SZ')
	utcdt=datetime.datetime.strptime(dt,'%Y-%m-%dT%H:%M:%SZ')
	return (utcdf+offset<now<utcdt+offset)

class EPContentProvider(ContentProvider):

	def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp', token=''):
		ContentProvider.__init__(self, 'eurosport', 'https://eu3-prod-direct.eurosportplayer.com', username, password, filter, tmp_dir)
		self.cp = HTTPCookieProcessor(cookielib.LWPCookieJar())
		self.init_urllib()
		self.token = token
		self.headers = {
			'referer': 'https://www.eurosportplayer.com/',
			'cookie': 'st={}'.format(token),
			'X-disco-client': 'WEB:UNKNOWN:esplayer:prod',
			'X-disco-params': 'realm=eurosport,,'
		}
		self.data = ""
		self.images = {}
		self.channels = {}
		self.taxos = {}

	def init_urllib(self):
		opener = build_opener(self.cp)
		install_opener(opener)

	def getDatas(self):
		items = json.loads(self.data)
		self.channels = {}
		self.images = {}
		self.taxos = {}
		for item in items.get('included'):
			if item['type'] == 'channel':
				self.channels[item['id']] = item['attributes']['name']
			elif item['type'] == 'image':
				self.images[item['id']] = item['attributes']['src']
			elif item['type'] == 'taxonomyNode':
				self.taxos[item['id']] = item['attributes']['name']

	def parseVideos(self,item,addlive=False,adddate=False,addtime=False):
		chname = self.channels.get(item.get('relationships',{}).get('primaryChannel',{}).get('data',{}).get('id',None))
		try:
			sport = self.taxos.get(item.get('relationships',{}).get('txSports',{}).get('data',{})[0].get('id',None))
		except:
			sport = ''
		itm = self.video_item()
		itm['url'] = 'playback/v2/videoPlaybackInfo/%s?usePreAuth=true'%item['id']
		itm['title'] = ''
		itm['title'] += parse_date(item['attributes'].get('scheduleStart',item['attributes'].get('publishStart')))+' ' if adddate else ''
		itm['title'] += parse_date(item['attributes'].get('scheduleStart',item['attributes'].get('publishStart')))[11:]+' ' if addtime else ''
		itm['title'] += 'LIVE ' if addlive else ''
		itm['title'] += '[%s] ' % chname if chname and addlive else ''
		itm['title'] += '- %s ' % item['attributes']['name']
		itm['title'] += '[%s] ' % chname if chname and not addlive else ''
		itm['plot'] = '%s - %s'%(sport, item['attributes'].get('secondaryTitle'))
		itm['plot'] += ' (%s min.)' % int(item['attributes'].get('videoDuration')/1000/60) if item['attributes'].get('videoDuration') else ''
		itm['img'] = self.images.get(item.get('relationships',{}).get('images',{}).get('data',{})[0].get('id',None))
		itm['date'] = parse_date(item['attributes'].get('scheduleStart',item['attributes'].get('publishStart')),totime=True)
		return itm

	def capabilities(self):
		return ['categories', 'resolve', 'search']

	def search(self,keyword):
		result = []
		try:
			self.data = util.request(self.base_url+'content/videos?include=images,primaryChannel,taxonomyNodes&filter[videoType]=LIVE&filter[isPlayable]=true&query=%s'%keyword, headers=self.headers)
			self.getDatas()
			items = json.loads(self.data)
			for item in items.get('data'):
				if item['type'] != 'video': continue
				result.append(self.parseVideos(item,addlive=True,adddate=True))
			self.data = util.request(self.base_url+'content/videos?include=images,primaryChannel,taxonomyNodes&filter[videoType]=STANDALONE&filter[isPlayable]=true&query=%s'%keyword, headers=self.headers)
			self.getDatas()
			items = json.loads(self.data)
			for item in items.get('data'):
				if item['type'] != 'video': continue
				result.append(self.parseVideos(item,adddate=True))
		except:
			showInfo('Chyba vyhledávání.')
		return result

	def categories(self):
		result = []
		result.append(self.dir_item('Program', '#schedule'))
		result.append(self.dir_item('Na požádání', '#on-demand'))
		self.data = util.request(self.base_url+'cms/routes/home?include=default&decorators=viewingHistory,isFavorite,playbackAllowed&page[items.number]=1&page[items.size]=8', headers=self.headers)
		self.getDatas()
		items = json.loads(self.data)
		for item in items.get('included'):
			if item['type'] != 'video': continue
			if not is_now(item['attributes'].get('scheduleStart'), item['attributes'].get('scheduleEnd')): continue
			result.append(self.parseVideos(item,addlive=True))
		return result

	def list(self, url):
		result = []
		if '#day;' in url:
			vals = url.split(";")
			self.data = util.request(self.base_url+'cms/collections/%s?include=default&pf[day]=%s'%(vals[1],vals[2]), headers=self.headers)
			self.getDatas()
			items = json.loads(self.data)
			for item in items.get('included'):
				if item['type'] != 'video': continue
				result.append(self.parseVideos(item,addtime=True))
			result = sorted(result, key=lambda x:x['title'])
		elif '#sport;' in url:
			vals = url.split(";")
			# self.data = util.request(self.base_url+'cms/routes/sport/%s?include=default&decorators=viewingHistory,isFavorite,playbackAllowed&page[items.number]=1&page[items.size]=8'%vals[1], headers=self.headers)
			self.data = util.request(self.base_url+'cms/routes/sport/%s?include=default'%vals[1], headers=self.headers)
			self.getDatas()
			items = json.loads(self.data)
			for item in items.get('included'):
				if item['type'] != 'video': continue
				result.append(self.parseVideos(item,adddate=True))
			result = sorted(result, key=lambda x:x['date'], reverse=True)
		elif '#schedule' in url:
			httpdata = util.request(self.base_url+'cms/routes/schedule?include=default', headers=self.headers)
			items = json.loads(httpdata)
			for item in items.get('included'):
				if item['type'] == 'collection' and item.get('attributes',{}).get('alias') == 'schedule' and item.get('attributes',{}).get('component',{}).get('filters',{})[0].get('options'):
					for day in item['attributes']['component']['filters'][0]['options']:
						sd = day['value'].split('-')
						result.append(self.dir_item('%s.%s.%s'%(sd[2],sd[1],sd[0]), '#day;' + item['id'] + ';' + day['value']))
		elif '#on-demand' in url:
			httpdata = util.request(self.base_url+'cms/routes/on-demand?include=default', headers=self.headers)
			items = json.loads(httpdata)
			for item in items.get('included'):
				if item['type'] == 'taxonomyNode' and item['attributes'].get('kind') == 'sport':
					result.append(self.dir_item(item['attributes'].get('name'), '#sport;' + item['attributes'].get('alternateId')))
			result = sorted(result, key=lambda x:x['title'])
		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		item = item.copy()
		result = []
		try:
			httpdata = util.request(self.base_url+item['url'], headers=self.headers)
		except HTTPError as e:
			if e.code == 403:
				showInfo('Toto video není dostupné.')
			return []
		items = json.loads(httpdata)

		url = items.get('data',{}).get('attributes',{}).get('streaming',{}).get('hls',{}).get('url')
		if url:
			spliturl = url.split('index.m3u8')
			data = util.request(url)

			audqiurl = ''
			audenurl = ''
			audczurl = ''
			# default qis lang
			audio = re.search('#EXT-X-MEDIA:TYPE=AUDIO,.*?,LANGUAGE="qis",.*?,URI="(.*?)"', data, re.S)
			if audio:
				audqiurl = audio.group(1)
			# default eng lang
			audio = re.search('#EXT-X-MEDIA:TYPE=AUDIO,.*?,LANGUAGE="eng",.*?,URI="(.*?)"', data, re.S)
			if audio:
				audenurl = audio.group(1)
			# cze lang
			audio = re.search('#EXT-X-MEDIA:TYPE=AUDIO,.*?,LANGUAGE="cze",.*?,URI="(.*?)"', data, re.S)
			if audio:
				audczurl = audio.group(1)

			res = []
			for m in re.finditer('#EXT-X-STREAM-INF:.*?RESOLUTION=\d+x(?P<quality>\d+),.*?\s(?P<chunklist>[^\s]+)', data, re.DOTALL):
				if int(m.group('quality')) < 720: continue
				if audczurl != '':
					itm = {}
					itm['quality'] = m.group('quality') + 'p'
					itm['lang'] = ' CZ'
					itm['url'] = spliturl[0] + m.group('chunklist') + '&suburi=' + spliturl[0] + audczurl
					res.append(itm)
				if audenurl != '':
					itm = {}
					itm['quality'] = m.group('quality') + 'p'
					itm['lang'] = ' EN'
					itm['url'] = spliturl[0] + m.group('chunklist') + '&suburi=' + spliturl[0] + audenurl
					res.append(itm)
				if audqiurl != '':
					itm = {}
					itm['quality'] = m.group('quality') + 'p'
					itm['lang'] = ' N/A'
					itm['url'] = spliturl[0] + m.group('chunklist') + '&suburi=' + spliturl[0] + audqiurl
					res.append(itm)
			res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)

			for item in res:
				itm = self.video_item()
				itm['title'] = item['lang']
				itm['quality'] = item['quality']
				itm['url'] = item['url']
				result.append(itm)

		if len(result) > 0 and select_cb:
			return select_cb(result)
		return result

__addon__ = ArchivCZSK.get_xbmc_addon('plugin.video.eurosport')
addon_userdata_dir = __addon__.getAddonInfo('profile')

# #################################################################################################

def ep_run(session, params):
	settings = {'quality':__addon__.getSetting('quality')}
	cookie_file = addon_userdata_dir + "/" + "cookie"

	#print("PARAMS: %s"%params)

	try:
		token = open(cookie_file, "r").read()
	except:
		token = __addon__.getSetting('eurosporttoken')
		if token:
			f = open(cookie_file, 'w')
			f.write(token)
			f.close()
		else:
			token = None
	if token:
		provider = EPContentProvider(token=token.strip())
		XBMCMultiResolverContentProvider(provider, settings, __addon__, session).run(params)
	else:
		client.showInfo('Pro přehrávání pořadů je potřeba účet na eurosportplayer.com\n\nPokud účet máte, musíte vložit dlouhý token z webu.\n\nPřečtěte si prosím Změny nebo soubor readme.md v adresáři doplňku jak na to.', timeout=20)

# #################################################################################################

def main(addon):
	return XBMCCompatInterface(ep_run)

# #################################################################################################
