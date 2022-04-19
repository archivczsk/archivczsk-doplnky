# -*- coding: utf-8 -*-
# /*
# *	 Copyright (C) 2021 Michal Novotny https://github.com/misanov
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

sys.path.append(os.path.dirname(__file__))

import sys, os, string, random, time, json, uuid, requests, re
from datetime import datetime
try:
	from urlparse import urlparse, parse_qs
	from urllib import urlencode
except ImportError:
	from urllib.parse import urlparse, parse_qs, urlencode

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video
from Plugins.Extensions.archivCZSK.engine import client
from Components.config import config

import helpers as helpers
import lookups as lookups
import auth as auth

############### init ################
addon = ArchivCZSK.get_xbmc_addon('plugin.video.iprima')
addon_userdata_dir = addon.getAddonInfo('profile')
home = addon.getAddonInfo('path')
icon = os.path.join(home, 'icon.png')

LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'iprima.log')
base_url = ""
chlive = {}
chlivethm = {}

def writeLog(msg, type='INFO'):
	try:
		f = open(LOG_FILE, 'a')
		dtn = datetime.now()
		f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
		f.close()
	except:
		pass

def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
	params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
	add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)

def menu():
	add_dir('Vyhledat', { 'url': '/search/'}, None)
	for item in lookups.menu_items:
		addDir(item['title'], '/section/{0}/'.format(item['resource']), 1, None)
	add_dir('HLAVNÍ ZPRÁVY', { 'url': '/program/6555972/'}, None)

def section(resource):
	if resource == 'live':
		html = requests.get('https://www.iprima.cz', verify=False)
		sections = re.findall("<video .*?poster=\"(.*?)\".*?molecule--list--live-broadcasting-list--item\".*?<a .*?data-trueview-id=\"HP - TV Channels - (.*?)\".*?--item--time\">(.*?)</span>(.*?)</a>.*?--item--time\">(.*?)</span>", html.text, re.S)
		for chan in sections:
			chid = chan[1]
			if chan[1] == "cnn": chid="cnn_news"
			chlivethm[chid] = chan[0]
			chlive[chid] = ' [COLOR YELLOW](' + chan[3].replace("&nbsp;", " ").strip() + ' ' + chan[2] + ' - ' + chan[4] + ')[/COLOR]'
	items = helpers.requestResource(resource, page=page)
	if 'subsections' in lookups.resources[resource] and page == 0:
		for item in lookups.resources[resource]['subsections']:
			addDir(item['title'], '/section/{0}/'.format(item['resource']), 1, None)
	renderItems(items)
	if len(items) == lookups.shared['pagination']:
		addDir('>> Další strana', '/section/{0}/?page={1}'.format(resource, page+1), 1, None)

def program(nid):
	programDetail = helpers.requestResource( 'program_by_id', page=page, postOptions={'nid': nid} )
	if page == 0:
		for season in programDetail['seasons'] or []:
			addDir(season, '/sublisting/{0}/{1}/'.format(nid, season.replace('/', '%2F')), 1, None)
		bonuses = helpers.requestResource( 'bonus', postOptions={'programId': nid, 'count': 1} )
		if len(bonuses) > 0:
			addDir('Bonusy', '/sublisting/{0}/bonus/'.format(nid), 1, None)
	renderItems(programDetail['episodes'])
	if len(programDetail['episodes']) == lookups.shared['pagination']:
		addDir('>> Další strana', '/program/{0}/?page={1}'.format(nid, page+1), 1, None)

def sublisting(programId, season):
	if season == 'bonus':
		items = helpers.requestResource( 'bonus', page=page, postOptions={'programId': programId} )
	else:
		items = helpers.requestResource( 'season', page=page, postOptions={'programId': programId, 'season': season.replace('%2F', '/')} )
	renderItems(items)
	if len(items) == lookups.shared['pagination']:
		addDir('>> Další strana', '/sublisting/{0}/{1}?page={2}'.format(programId, season, page+1), 1, None)

def search():
	query = client.getTextInput(session, "Hledat")
	if len(query) == 0:
		client.showError("Je potřeba zadat vyhledávaný řetězec")
		return
	items = helpers.requestResource( 'search_movies', page=page, postOptions={'keyword': query} )
	renderItems(items,'Filmy: ')
	items = helpers.requestResource( 'search_series', page=page, postOptions={'keyword': query} )
	renderItems(items,'Seriály: ')
	items = helpers.requestResource( 'search_episodes', page=page, postOptions={'keyword': query} )
	renderItems(items,'Epizody: ')
	items = helpers.requestResource( 'search_bonus', page=page, postOptions={'keyword': query} )
	renderItems(items,'Bonusy: ')

def renderItems(items,mtitle=None):
	for item in items:
		if not item: continue
		if 'admittanceType' in item and item['admittanceType'] not in lookups.free_admittance_types: continue
		label = item.get('name',item.get('title'))
		label = label + ' - ' + item.get('episodeTitle') if 'episodeTitle' in item and item['episodeTitle'] else label
		if mtitle: label = mtitle + label
		infoLabels = {
			'genre': ', '.join(item.get('genres',[]) or ''),
			'plot': item.get('teaser','') or ''
		}
		if 'premiereDate' in item and item['premiereDate']: #2021-01-26T19:15:00+00:00
			infoLabels['plot'] = datetime.strptime(item['premiereDate'],"%Y-%m-%dT%H:%M:%S+00:00").strftime("%d.%m.%Y") + " - " + infoLabels['plot']
			infoLabels['year'] = datetime.strptime(item['premiereDate'],"%Y-%m-%dT%H:%M:%S+00:00").strftime("%Y")
		if 'length' in item:
			infoLabels['duration'] = item['length']
		if 'thumbnailData' in item and item['thumbnailData']:
			thumb = item['thumbnailData'].get('url',None)
		else:
#			thumb = item.get('logo',None)
			thumb = None
		if item.get('id',0) in chlive:
			label = label + chlive[item['id']]
			thumb = chlivethm[item['id']]
		isPlayable = helpers.isPlayable(item.get('type','video'))
		if isPlayable:
			url = '/play/{0}'.format(item['playId'])
			add_dir(label, { 'url': url }, thumb, infoLabels=infoLabels, video_item=True)
		else:
			url = '/program/{0}/'.format(item['nid'])
			addDir(label, url, 1, thumb, infoLabels=infoLabels)

def play(name):
	videoId = adr[1]
	videoDetail = helpers.requestResource('play', replace={'id': videoId})
	url = None
	title = ''
	thumb = None
	if 'streamInfos' in videoDetail:
		for stream in videoDetail['streamInfos']:
			if stream.get('type') == "HLS":
				url = stream.get('url')
				break
	if url == None:
		client.showError('Nenalezen žádný stream pro video')
		return
	if "productDetail" in videoDetail:
		title = videoDetail['productDetail'].get('localTitle')
	if "thumbnailInfo" in videoDetail:
		thumb = videoDetail['thumbnailInfo'].get('url',None)
	add_video(title, url, None, thumb, filename=title, infoLabels={'title': title})

def router(paramstring):
	if adr[0] == "section":
		section(adr[1])
	elif adr[0] == "program":
		program(adr[1])
	elif adr[0] == "sublisting":
		sublisting(adr[1],adr[2])
	elif adr[0] == "search":
		search()
	elif adr[0] == "play":
		play(adr[1])
	else:
		menu()

#print('PARAMS: ',params)
url=params['url'][1:] if 'url' in params else urlencode(params)
parsed_url = urlparse(params['url'] if 'url' in params else urlencode(params))
params = parse_qs(parsed_url.query)
page = int(params['page'][0]) if 'page' in params else 0
adr = url.split('/')

#print('URL: ',url)
#print('PURL: ',parsed_url)
#print('PARAMS: ',params)
#print('ADR: ',adr)
#print('PAGE: ',page)

lookups.shared['pagination'] = lookups.settings['pagination_options'][int(addon.getSetting('pagination'))]
credentialsAvailable = auth.performCredentialCheck()
if credentialsAvailable:
	router(url)
else:
	from Plugins.Extensions.archivCZSK.gsession import GlobalSession
	addon.open_settings(GlobalSession.getSession())

if len(client.GItem_lst[0]) == 0:
	addDir('Nic nenalezeno nebo chyba','',1,None)
