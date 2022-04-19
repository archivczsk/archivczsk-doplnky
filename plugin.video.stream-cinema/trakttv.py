import sys
import os
import json
import traceback
import datetime
import util

try:
	from urllib2 import HTTPError
except:
	from urllib.error import HTTPError

class TraktRefreshException(Exception):
	pass

class trakt_tv(object):
	def __init__(self, client_id, client_secret, token='', refresh_token='', expire=0):
		self.API = 'https://api.trakt.tv'
		self.API_AUTH = '%s/oauth/device'%self.API
		self.API_LIST = '%s/users/me/lists'%self.API
		self.API_WATCH_LIST = '%s/users/me/watchlist/items'%self.API
		self.API_VERSION = 2
		self.TOKEN = ''
		self.REFRESH_TOKEN = ''
		self.EXPIRE = 0
		self.CLIENT_ID = client_id
		self.CLIENT_SECRET = client_secret
		if token!='':
			self.TOKEN = token
		if refresh_token!='':
			self.REFRESH_TOKEN = refresh_token
		if expire!=0:
			self.EXPIRE = expire
		from scinema import sclog
		self.log = sclog()

	def getItemType(self, item):
		# 4- season+espisode
		# 3- season 1,2,3
		# 2- tvshow
		# 1- movie
		id = int(item['id'])
		url = item['url'].lower()
		#self.log.logDebug("TRAKT: getItemType url=%s"%url)
		if url[0]=='/': # item from menu
			if url == '/play/%s'%id:
				return 1
			if url=='/get/%s'%id:
				return 2
			if url.startswith('/get/%s/'%id):
				return 3
			if url.startswith('/play/%s/'%id):
				return 4
		else: # playing movie item (only mark as watched, can be only movie or episode)
			if 'episode' in item:
				return 4
			else:
				return 1
		raise Exception("Invalid trakt item (TYPE).")

	def getTraktIds(self, item):
		if 'trakt' in item:
			return {"trakt":item['trakt']}
		if 'tvdb' in item:
			return {"tvdb":item['tvdb']}
		if 'imdb' in item:
			return {"imdb":'tt%s'%item['imdb'].replace('tt','')}
		raise Exception("Invalid trakt item (IDs).")

	# API
	def get_lists(self):
		if self.valid():
			ret = []
			ret.append("%s##%s"%('Watchlist',self.API_WATCH_LIST))
			data = json.loads(util.request(self.API_LIST, {'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':'%s'%self.CLIENT_ID}))
			for m in data:
				ret.append("%s##%s"%(m['name'],'%s/%s/items'%(self.API_LIST, m['ids']['slug'])))
			return ret
		raise Exception('Invalid trakt token')

	def get_watch_list_items(self):
		if self.valid():
			ret = []
			data = json.loads(util.request(self.API_WATCH_LIST, {'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
			for m in data:
				try:
					tp = '%s'%m['type']
					obj = {'imdb':'%s'%m[tp]['ids']['imdb'], 'title':'%s (%s)'%(m[tp]['title'],m[tp]['year'])}
					ret.append(obj)
				except:
					self.log.logError("(TRAKT) Add trakt item to search watchlist failed. %s\n%s"%(traceback.format_exc(),m))
					pass
			return ret
		raise Exception('Invalid trakt token')
	
	def get_list_items(self, id):
		if self.valid():
			ret = []
			data = json.loads(util.request(self.API_LIST+'/%s/items'%id, {'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
			for m in data:
				tp = '%s'%m['type']
				obj = {'imdb':'%s'%m[tp]['ids']['imdb'], 'title':'%s (%s)'%(m[tp]['title'],m[tp]['year'])}
				ret.append(obj)
			return ret
		raise Exception('Invalid trakt token')

	def add_to_watchlist(self, item):
		mediatype= self.getItemType(item)
		postdata = {}
		if mediatype==1:
			postdata = {"movies": [{"ids": self.getTraktIds(item)}]}
		# to watchlist can be added only whole tvseason
		if mediatype==2 or mediatype==3 or mediatype==4:
			postdata = {'shows':[{'ids':self.getTraktIds(item)}]}
			
		data = json.loads(util.post_json(self.API+'/sync/watchlist', data=postdata, headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
		self.log.logDebug("add_to_watchlist response:\n%s"%data)
		if mediatype==1:
			if not (int(data['added']['movies'])==1 or int(data['existing']['movies'])==1):
				raise Exception('Movie item not added to watchlist.')
		if mediatype==2 or mediatype==3 or mediatype==4:
			if not (int(data['added']['shows'])==1 or int(data['existing']['shows'])==1):
				raise Exception('TvShow item not added to watchlist.')

	def remove_from_watchlist(self, item):
		mediatype= self.getItemType(item)
		postdata = {}
		if mediatype==1:
			postdata = {"movies": [{"ids": self.getTraktIds(item)}]}
		# to watchlist can be added only whole tvseason
		if mediatype==2 or mediatype==3 or mediatype==4:
			postdata = {'shows':[{'ids': self.getTraktIds(item)}]}
			
		data = json.loads(util.post_json(self.API+'/sync/watchlist/remove', data=postdata, headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
		self.log.logDebug("remove_from_watchlist response:\n%s"%data)
		if mediatype==1:
			if int(data['deleted']['movies'])!=1:
				raise Exception('Movie item not removed from watchlist.')
		if mediatype==2 or mediatype==3 or mediatype==4:
			if int(data['deleted']['shows'])!=1:
				raise Exception('TvShow item not removed from watchlist.')

	def mark_as_watched(self, item):
		mediatype= self.getItemType(item)
		postdata = {}
		if mediatype==1:
			postdata = {"movies": [{"ids": self.getTraktIds(item)}]}
		if mediatype==2:
			postdata = {'shows':[{'ids':self.getTraktIds(item)}]}
		if mediatype==3:
			postdata = {'shows':[{'seasons':[{'number':int('%s'%item['season'])}], 'ids':self.getTraktIds(item)}]}
		if mediatype==4:
			postdata = {'shows':[{'seasons':[{'episodes':[{'number':int('%s'%item['episode'])}], 'number':int('%s'%item['season'])}], 'ids':self.getTraktIds(item)}]}

		self.log.logDebug("mark_as_watched postdata=%s"%postdata)
			
		data = json.loads(util.post_json(self.API+'/sync/history', data=postdata, headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
		self.log.logDebug("mark_as_watched response:\n%s"%data)
		if mediatype==1:
			if int(data['added']['movies'])!=1:
				raise Exception('Movie item not mark as watched.')
		if mediatype==2 or mediatype==3:
			if int(data['added']['episodes'])<1:
				raise Exception('TvShow (season) not mark as watched.')
		if mediatype==4:
			if int(data['added']['episodes'])!=1:
				raise Exception('TvShow episode not mark as watched.')

	def mark_as_not_watched(self, item):
		mediatype= self.getItemType(item)
		postdata = {}
		if mediatype==1:
			postdata = {"movies": [{"ids": self.getTraktIds(item)}]}
		if mediatype==2:
			postdata = {'shows':[{'ids':self.getTraktIds(item)}]}
		if mediatype==3:
			postdata = {'shows':[{'seasons':[{'number':int('%s'%item['season'])}], 'ids':self.getTraktIds(item)}]}
		if mediatype==4:
			postdata = {'shows':[{'seasons':[{'episodes':[{'number':int('%s'%item['episode'])}], 'number':int('%s'%item['season'])}], 'ids':self.getTraktIds(item)}]}
			
		data = json.loads(util.post_json(self.API+'/sync/history/remove', data=postdata, headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
		self.log.logDebug("mark_as_not_watched response:\n%s"%data)
		if mediatype==1:
			if int(data['deleted']['movies'])!=1:
				raise Exception('Movie item not mark as not watched.')
		if mediatype==2 or mediatype==3:
			if int(data['deleted']['episodes'])<1:
				raise Exception('TvShow (season) not mark as not watched.')
		if mediatype==4:
			if int(data['deleted']['episodes'])!=1:
				raise Exception('TvShow episode not mark as not watched.')
		pass

	def get_watched(self):
		if self.valid():
			dataMovies = json.loads(util.request(self.API+'/sync/watched/movies', headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
			dataSeries = json.loads(util.request(self.API+'/sync/watched/shows', headers={'Content-Type':'application/json', 'Authorization':'Bearer %s'%self.TOKEN, 'trakt-api-version':self.API_VERSION, 'trakt-api-key':self.CLIENT_ID}))
			return dataMovies, dataSeries
		return [], []

	# PAIR
	def valid(self):
		if self.TOKEN == '':
			return False
		
		# check refresh
		now = (datetime.datetime.now() - datetime.datetime(1970,1,1)).total_seconds()
		if self.EXPIRE-432000 < now: #-5dni (5*24*60*60)
			self.refresh_token()
		return True

	def get_device_code(self):
		self.log.logDebug('get device URL='+self.API_AUTH+'/code')
		data = json.loads(util.post_json(self.API_AUTH+'/code', data={'client_id':self.CLIENT_ID}, headers={'Content-Type':'application/json'}))
		interval = data['interval'] #seconds
		expire = data['expires_in'] #seconds
		verUrl = data['verification_url']
		devCode = data['device_code']
		userCode = data['user_code']
		tryies = expire/interval

		return devCode, verUrl, userCode, interval

	def get_token(self, code):
		try:
			data = json.loads(util.post_json(self.API_AUTH+'/token', data={'code':code,'client_id':self.CLIENT_ID, 'client_secret':self.CLIENT_SECRET}, headers={'Content-Type':'application/json'}))
			self.TOKEN = data['access_token']
			self.REFRESH_TOKEN = data['refresh_token']

			expire = data['expires_in'] #seconds
			created = data['created_at']

			self.EXPIRE = expire+created

			self.log.logDebug("Get token return token=%s, rtoken=%s, exp=%s"%(self.TOKEN, self.REFRESH_TOKEN, self.EXPIRE))

			#update settings
			self.writeSetting('trakt_token', '%s'%self.TOKEN)
			self.writeSetting('trakt_refresh_token', '%s'%self.REFRESH_TOKEN)
			self.writeSetting('trakt_token_expire', '%s'%self.EXPIRE)

		except HTTPError as err:
			return None
		return self.TOKEN

	def refresh_token(self, redirect_uri='urn:ietf:wg:oauth:2.0:oob', grant_type='refresh_token'):
		try:
			data = json.loads(util.post_json(self.API+'/oauth/token', data={'refresh_token':self.REFRESH_TOKEN, 'client_id':self.CLIENT_ID, 'client_secret':self.CLIENT_SECRET, 'redirect_uri':redirect_uri, 'grant_type':grant_type}, headers={'Content-Type':'application/json'}))
			self.TOKEN = data['access_token']
			self.REFRESH_TOKEN = data['refresh_token']

			expire = data['expires_in'] #seconds
			created = data['created_at']

			self.EXPIRE = expire+created

			#update settings
			self.writeSetting('trakt_token', '%s'%self.TOKEN)
			self.writeSetting('trakt_refresh_token', '%s'%self.REFRESH_TOKEN)
			self.writeSetting('trakt_token_expire', '%s'%self.EXPIRE)
		except HTTPError as err:
			if err.code == 401:
				raise TraktRefreshException('Refresh trakt access token failed (reset settings).')
			raise err
		except:
			raise

	def writeSetting(self, id, val):
		from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
		addon = ArchivCZSK.get_xbmc_addon('plugin.video.stream-cinema')
		addon.setSetting(id, val)
