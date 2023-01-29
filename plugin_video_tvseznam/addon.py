# -*- coding: utf-8 -*-
#
# plugin.video.tvseznam
#
# (c) Michal Novotny
#
# original at https://www.github.com/misanov/
#
# Free for non-commercial use under author's permissions
# Credits must be used

import re,sys,os,string,time,datetime,requests,unicodedata
from Components.config import config
from Plugins.Extensions.archivCZSK.engine.client import add_dir, add_video
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine import client

try:
	from urllib import unquote_plus
except:
	from urllib.parse import unquote_plus

addon =	 ArchivCZSK.get_xbmc_addon('plugin.video.tvseznam')
profile = addon.getAddonInfo('profile')
__settings__ = addon
home = __settings__.getAddonInfo('path')
icon =	os.path.join( home, 'icon.png' )
nexticon =	os.path.join( home, 'next.png' )
LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'tvs.log')


def tvseznam_run(session, params):

	def writeLog(msg, type='INFO'):
		try:
			f = open(LOG_FILE, 'a')
			dtn = datetime.datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] + " [" + type + "] %s\n" % msg)
			f.close()
		except:
			pass

	def strip_accents(s):
		return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

	def addDir(name, url, mode, image, page=None, kanal=None, infoLabels={}, menuItems={}):
		params = {'name':name, 'url':url, 'mode':mode, 'page':page, 'kanal':kanal}
		add_dir(name, params, image, infoLabels=infoLabels, menuItems=menuItems)

	def getUrl(url, post_data=''):
		if post_data == '':
			return requests.get(url=url, headers={'User-Agent': 'okhttp/3.12.2', 'Content-Type': 'application/json; charset=utf-8'}, timeout=15)
		else:
			return requests.post(url=url, data=post_data, headers={'User-Agent': 'okhttp/3.12.2', 'Content-Type': 'application/json; charset=utf-8'}, timeout=15)

	def Most():
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"TagEpisodes","variables":{"id":"VGFnOjEyNDk1OTY","cursor":null,"limit":20},"query":"query TagEpisodes($id: ID, $cursor: String, $limit: Int = 20) {  tag(id: $id) {    __typename    episodesConnection(after: $cursor, first: $limit) {      __typename      ...EpisodeConnector    }  }}fragment EpisodeConnector on EpisodeItemConnection {  __typename  pageInfo {    __typename    hasNextPage    endCursor  }  edges {    __typename    cursor    node {      __typename      ...EpisodeDetail    }  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' not in jso or 'tag' not in jso['data'] or 'episodesConnection' not in jso['data']['tag'] or 'edges' not in jso['data']['tag']['episodesConnection']:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru, zkuste to za chvilku', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		for edge in jso['data']['tag']['episodesConnection']['edges']:
			if edge['node']:
				poster = 'https:' + edge['node']['images'][0]['url'] if 'images' in edge['node'] and 'url' in edge['node']['images'][0] else None
				datum = datetime.datetime.utcfromtimestamp(edge['node']['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in edge['node'] and 'timestamp' in edge['node']['publishTime'] else ''
				addDir(edge['node']['name'], edge['node']['id'], 4, poster, None, None, infoLabels={'plot':'[' + edge['node']['originTag']['name'] + '] ' + datum + edge['node']['perex'], 'duration':edge['node']['duration'], 'rating': edge['node']['views']})

	def Latests():
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"TagEpisodes","variables":{"id":"VGFnOjEyNDM2OTc","cursor":null,"limit":50},"query":"query TagEpisodes($id: ID, $cursor: String, $limit: Int = 20) {  tag(id: $id) {    __typename    episodesConnection(after: $cursor, first: $limit) {      __typename      ...EpisodeConnector    }  }}fragment EpisodeConnector on EpisodeItemConnection {  __typename  pageInfo {    __typename    hasNextPage    endCursor  }  edges {    __typename    cursor    node {      __typename      ...EpisodeDetail    }  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' not in jso or 'tag' not in jso['data'] or 'episodesConnection' not in jso['data']['tag'] or 'edges' not in jso['data']['tag']['episodesConnection']:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru, zkuste to za chvilku', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		for edge in jso['data']['tag']['episodesConnection']['edges']:
			if edge['node']:
				poster = 'https:' + edge['node']['images'][0]['url'] if 'images' in edge['node'] and 'url' in edge['node']['images'][0] else None
				datum = datetime.datetime.utcfromtimestamp(edge['node']['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in edge['node'] and 'timestamp' in edge['node']['publishTime'] else ''
				addDir(edge['node']['name'], edge['node']['id'], 4, poster, None, None, infoLabels={'plot':'[' + edge['node']['originTag']['name'] + '] ' + datum + edge['node']['perex'], 'duration':edge['node']['duration'], 'rating': edge['node']['views']})

	def LatestsStream():
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"TagEpisodes","variables":{"id":"VGFnOjI","cursor":null,"limit":20},"query":"query TagEpisodes($id: ID, $cursor: String, $limit: Int = 20) {  tag(id: $id) {    __typename    episodesConnection(after: $cursor, first: $limit) {      __typename      ...EpisodeConnector    }  }}fragment EpisodeConnector on EpisodeItemConnection {  __typename  pageInfo {    __typename    hasNextPage    endCursor  }  edges {    __typename    cursor    node {      __typename      ...EpisodeDetail    }  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' not in jso or 'tag' not in jso['data'] or 'episodesConnection' not in jso['data']['tag'] or 'edges' not in jso['data']['tag']['episodesConnection']:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru, zkuste to za chvilku', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		for edge in jso['data']['tag']['episodesConnection']['edges']:
			if edge['node']:
				poster = 'https:' + edge['node']['images'][0]['url'] if 'images' in edge['node'] and 'url' in edge['node']['images'][0] else None
				datum = datetime.datetime.utcfromtimestamp(edge['node']['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in edge['node'] and 'timestamp' in edge['node']['publishTime'] else ''
				addDir(edge['node']['name'], edge['node']['id'], 4, poster, None, None, infoLabels={'plot':'[' + edge['node']['originTag']['name'] + '] ' + datum + edge['node']['perex'], 'duration':edge['node']['duration'], 'rating': edge['node']['views']})

	def detailEpisode(id):
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"DetailEpisodeRequest","variables":{"id":"' + id + '"},"query":"query DetailEpisodeRequest($id: ID) {  episode(id: $id) {    __typename    ...EpisodeDetail  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' in jso and 'episode' in jso['data']:
			poster = 'https:' + jso['data']['episode']['images'][0]['url'] if 'images' in jso['data']['episode'] and 'url' in jso['data']['episode']['images'][0] else None
			datum = datetime.datetime.utcfromtimestamp(jso['data']['episode']['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in jso['data']['episode'] and 'timestamp' in jso['data']['episode']['publishTime'] else ''
			addDir(jso['data']['episode']['name'], jso['data']['episode']['spl'], 5, poster, None, None, { 'plot': '[' + jso['data']['episode']['originTag']['name'] + '] ' + datum + jso['data']['episode']['perex'], 'duration': jso['data']['episode']['duration'], 'rating': jso['data']['episode']['views']})
			posterCat = None
			for image in jso['data']['episode']['originTag']['images']:
				if image['usage'] == 'square': posterCat = 'https:' + image['url']
			addDir('Více z kategorie [COLOR yellow]' + jso['data']['episode']['originTag']['name'] + '[/COLOR]', jso['data']['episode']['originTag']['id'], 3, posterCat, None, None)

	def Guide():
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"Guide","variables":{},"query":"query Guide {  inGuideTags: tags(orderType: guide, inGuide: true, limit: 30) {    __typename    ...TagPlaylist  }}fragment TagPlaylist on Tag {  __typename  id  dotId  name  episodes {    __typename    name    id    originUrl    commentsDisabled    duration    images {      __typename      ...Img    }  }  images {    __typename    ...Img  }  originTag {    __typename    ...OriginTag  }  category  episodesCount}fragment Img on Image {  __typename  url  usage}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' not in jso or 'inGuideTags' not in jso['data'] or jso['data']['inGuideTags'] == None:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru, zkuste to za chvilku', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		addDir('[COLOR yellow]Hledat[/COLOR]', 'search', 9, None, 1)
		addDir('[COLOR yellow]Živě[/COLOR]', 'live', 8, None, 1)
		addDir('[COLOR yellow]Nejnovější[/COLOR]', 'last', 7, None, 1)
		addDir('[COLOR yellow]Nejnovější Stream[/COLOR]', 'laststream', 11, None, 1)
		addDir('[COLOR yellow]Nejsledovanější[/COLOR]', 'most', 10, None, 1)
		if 'data' in jso and 'inGuideTags' in jso['data']:
			guides = {}
			for article in jso['data']['inGuideTags'] or []:
				poster = None
				for image in article['images']:
					if image['usage'] == 'square': poster = 'https:' + image['url']
				guides[article['name']] = { 'id': article['id'], 'poster': poster }
			for key in sorted(guides):
				addDir(key, guides[key]['id'], 2, guides[key]['poster'], 1)

	def Playlists(id):
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"GuidePlaylists","variables":{"playlistID":"' + id + '","playlistLimit":100,"playlistOffset":0},"query":"query GuidePlaylists($playlistID: ID, $playlistLimit: Int, $playlistOffset: Int) {  tags: tags(id: $playlistID, limit: $playlistLimit, offset: $playlistOffset, listing: direct_children, orderType: guide, category: show) {    __typename    ...TagPlaylist  }}fragment TagPlaylist on Tag {  __typename  id  dotId  name  episodes {    __typename    name    id    originUrl    commentsDisabled    duration    images {      __typename      ...Img    }  }  images {    __typename    ...Img  }  originTag {    __typename    ...OriginTag  }  category  episodesCount}fragment Img on Image {  __typename  url  usage}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' in jso:
			guides = {}
			for article in jso['data']['tags']:
				poster = None
				for image in article['images']:
					if image['usage'] == 'square': poster = 'https:' + image['url']
				guides[strip_accents(article['name'])] = { 'id': article['id'], 'poster': poster, 'name': article['name'], 'count': article['episodesCount'] }
			for key in sorted(guides):
				addDir(guides[key]['name'] + ' (' + str(guides[key]['count']) + ')', guides[key]['id'], 3, guides[key]['poster'], 1)

	def Episodes(id, cursor='"null"'):
		if cursor == '"null"':
			data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"TagEpisodes","variables":{"id":"' + id + '","cursor":null,"limit":50},"query":"query TagEpisodes($id: ID, $cursor: String, $limit: Int = 20) {  tag(id: $id) {    __typename    episodesConnection(after: $cursor, first: $limit) {      __typename      ...EpisodeConnector    }  }}fragment EpisodeConnector on EpisodeItemConnection {  __typename  pageInfo {    __typename    hasNextPage    endCursor  }  edges {    __typename    cursor    node {      __typename      ...EpisodeDetail    }  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		else:
			data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"TagEpisodes","variables":{"id":"' + id + '","cursor":' + cursor + ',"limit":50},"query":"query TagEpisodes($id: ID, $cursor: String, $limit: Int = 20) {  tag(id: $id) {    __typename    episodesConnection(after: $cursor, first: $limit) {      __typename      ...EpisodeConnector    }  }}fragment EpisodeConnector on EpisodeItemConnection {  __typename  pageInfo {    __typename    hasNextPage    endCursor  }  edges {    __typename    cursor    node {      __typename      ...EpisodeDetail    }  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' in jso:
			for episode in jso['data']['tag']['episodesConnection']['edges']:
				poster = 'https:' + episode['node']['images'][0]['url'] if 'images' in episode['node'] and 'url' in episode['node']['images'][0] else None
				datum = datetime.datetime.utcfromtimestamp(episode['node']['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in episode['node'] and 'timestamp' in episode['node']['publishTime'] else ''
				addDir(episode['node']['name'], episode['node']['spl'], 5, poster, None, None, { 'plot': '[' + episode['node']['originTag']['name'] + '] ' + datum + episode['node']['perex'], 'duration': episode['node']['duration'], 'rating': episode['node']['views']})
			if jso['data']['tag']['episodesConnection']['pageInfo']['hasNextPage']:
				addDir('Další strana >>', id, 3, nexticon, jso['data']['tag']['episodesConnection']['pageInfo']['endCursor'])

	def videoLink(url):
		data = getUrl(url + 'spl2,3,VOD')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'Location' in jso:
			url = jso['Location']
			data = getUrl(url)
			if data.status_code != 200:
				client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
				return False
			jso = data.json()
		if 'data' in jso:
			if 'mp4' in jso['data'] and '1080p' in jso['data']['mp4']: add_video('[1080p] ' + name, '/'.join(url.split('/')[:-2] + jso['data']['mp4']['1080p']['url'].split('/')[1:]), None, None)
			if 'mp4' in jso['data'] and '720p' in jso['data']['mp4']: add_video('[720p] ' + name, '/'.join(url.split('/')[:-2] + jso['data']['mp4']['720p']['url'].split('/')[1:]), None, None)
			if 'mp4' in jso['data'] and '480p' in jso['data']['mp4']: add_video('[480p] ' + name, '/'.join(url.split('/')[:-2] + jso['data']['mp4']['480p']['url'].split('/')[1:]), None, None)
			if 'mp4' in jso['data'] and '360p' in jso['data']['mp4']: add_video('[360p] ' + name, '/'.join(url.split('/')[:-2] + jso['data']['mp4']['360p']['url'].split('/')[1:]), None, None)
			if 'mp4' in jso['data'] and '240p' in jso['data']['mp4']: add_video('[240p] ' + name, '/'.join(url.split('/')[:-2] + jso['data']['mp4']['240p']['url'].split('/')[1:]), None, None)

	def Search():
		query = client.getTextInput(session, 'Hledat')
		if len(query) == 0:
	#		client.refresh_screen()
			return
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"Search","variables":{"query":"' + query + '"},"query":"query Search($query: String) {  searchEpisode(query: $query, originalTagEpisodeLimit: 20) {    __typename    ...EpisodeDetail  }  searchTag(query: $query, originalTagEpisodeLimit: 20) {    __typename    ...OriginTag  }}fragment EpisodeDetail on Episode {  __typename  id  dotId  name  duration  perex  publishTime {    __typename    timestamp  }  spl  isLive  originTag {    __typename    ...OriginTag  }  images {    __typename    ...Img  }  views  urlName  originUrl  commentsDisabled  downloadable  contextualFields {    __typename    lastVideoPositionSec  }  expirationTime {    __typename    timestamp  }}fragment OriginTag on Tag {  __typename  id  dotId  category  name  favouritesCount  urlName  originTag {    __typename    name  }  images {    __typename    ...Img  }}fragment Img on Image {  __typename  url  usage}"}')
		if data.status_code != 200:
	#		client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			client.showInfo('Chyba načítání dat ze serveru')
			return
		jso = data.json()
		if 'data' in jso and 'searchTag' in jso['data']:
			for tag in jso['data']['searchTag']:
				poster = None
				for image in tag['images']:
					if image['usage'] == 'square': poster = 'https:' + image['url']
				addDir('[COLOR yellow]' + tag['name'] + '[/COLOR]', tag['id'], 3, poster, 1)
		if 'data' in jso and 'searchEpisode' in jso['data']:
			for episode in jso['data']['searchEpisode']:
				poster = 'https:' + episode['images'][0]['url'] if 'images' in episode and 'url' in episode['images'][0] else None
				datum = datetime.datetime.utcfromtimestamp(episode['publishTime']['timestamp']).strftime('%d.%m.%y %H:%M') + ' - ' if 'publishTime' in episode and 'timestamp' in episode['publishTime'] else ''
				addDir(episode['name'], episode['spl'], 5, poster, None, None, { 'plot': '[' + episode['originTag']['name'] + '] ' + datum + episode['perex'], 'duration': episode['duration']})
	#	else:
	#		client.add_operation("SHOW_MSG", {'msg': 'Nic nenalezeno', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
		if len(client.GItem_lst[0]) == 0:
			addDir('Nic nenalezeno nebo chyba', '', 1, None)
			client.showInfo('Nic nenalezeno')

	def Live():
		tcur = int(time.time())
		tfrom = tcur - 90000
	#	tto = tcur+45000
		tto = tcur
		data = getUrl('https://api.televizeseznam.cz/graphql', '{"operationName":"Playout","variables":{"timeFrom":' + str(tfrom) + ',"timeTo":' + str(tto) + '},"query":"query Playout($timeFrom: Int, $timeTo: Int) {  playout(timeFrom: $timeFrom, timeTo: $timeTo) {    __typename    ...Playout  }  playoutConfig {    __typename    status    selfPromo  }}fragment Playout on Playout {  __typename  id  dotId  start  end  epgStart  title  description  link  profile  internetExpiration  ads {    __typename    start    end  }  selfs {    __typename    start    end  }  jingles {    __typename    start    end  }  isRunning  vrplMode  noInternetAds  program  assetId  segB}"}')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'data' in jso and 'playout' in jso['data']:
			for playout in jso['data']['playout']:
				epgstart = datetime.datetime.fromtimestamp(playout['epgStart']).strftime('%d.%m.%y %H:%M')
				timestart = datetime.datetime.fromtimestamp(playout['start']).strftime('%d.%m.%y %H:%M')
				timeend = datetime.datetime.fromtimestamp(playout['end']).strftime('%H:%M')
				if playout['start'] < tcur and playout['end'] > tcur:
					addDir('[COLOR yellow]' + timestart + '-' + timeend + ' ŽIVĚ - ' + playout['title'] + '[/COLOR]', playout['link'] + 'bw|', 6, None, None, None, {'plot': epgstart + ' - ' + playout['description']})
				else:
					addDir(timestart + '-' + timeend + ' ' + playout['title'], playout['link'], 6, None, None, None, {'plot': epgstart + ' - ' + playout['description']})
		client.GItem_lst[0].reverse()

	def playLive(url):
		data = getUrl(url + 'spl2,4,EVENT')
		if data.status_code != 200:
			client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
			return False
		jso = data.json()
		if 'Location' in jso:
			url = jso['Location']
			data = getUrl(url)
			if data.status_code != 200:
				client.add_operation("SHOW_MSG", {'msg': 'Chyba nacitani dat ze serveru', 'msgType': 'error', 'msgTimeout': 10, 'canClose': True })
				return False
			jso = data.json()
		if 'pls' in jso and 'hls' in jso['pls'] and 'url' in jso['pls']['hls']:
			add_video(name, '/'.join(url.split('/')[:-1]) + '/' + jso['pls']['hls']['url'], None, None)

	url = None
	name = None
	thumb = None
	mode = None
	page = 'null'

	try:
			url = unquote_plus(params["url"])
	except:
			pass
	try:
			name = unquote_plus(params["name"])
	except:
			pass
	try:
			mode = int(params["mode"])
	except:
			pass
	try:
			page = unquote_plus(params["page"])
	except:
			pass

	#writeLog('PAGE: '+str(page))
	#writeLog('URL: '+str(url))
	#writeLog('NAME: '+str(name))
	#writeLog('MODE: '+str(mode))

	if mode == None or url == None or len(url) < 1:
			Guide()
	elif mode == 2:
			Playlists(url)
	elif mode == 3:
			Episodes(url, '"' + page + '"')
	elif mode == 4:
			detailEpisode(url)
	elif mode == 5:
			videoLink(url)
	elif mode == 6:
			playLive(url)
	elif mode == 7:
			Latests()
	elif mode == 8:
			Live()
	elif mode == 9:
			Search()
	elif mode == 10:
			Most()
	elif mode == 11:
			LatestsStream()

	if len(client.GItem_lst[0]) == 0:
		addDir('Nic nenalezeno nebo chyba', '', 1, None)
		client.showInfo('Nic nenalezeno')


def main(addon):
	return tvseznam_run
