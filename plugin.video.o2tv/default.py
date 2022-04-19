# -*- coding: UTF-8 -*-

import os, xbmcutil, xbmcprovider, resolver
import sys, json, traceback, datetime, requests, re
from provider import ContentProvider, cached, ResolveException
from time import strftime
from cachestack import lru_cache
from Components.config import config
from Components.Language import language
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.compat import eConnectCallback
from Plugins.Extensions.archivCZSK.engine.tools.util import toString
from provider import ResolveException
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
#from util import addDir, addLink, addSearch, getSearch

try:
	from urllib2 import urlopen, HTTPError
except:
	from urllib.error import HTTPError

__scriptid__   = 'plugin.video.o2tv'
__scriptname__ = 'o2tv.sk'
__addon__	   = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__   = __addon__.getLocalizedString
__gets		   = __addon__.getSetting
__sets		   = __addon__.setSetting

class Singleton(type):
	_instances = {}
	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]

class o2log(object):
	ERROR = 0
	INFO = 1
	DEBUG = 2
	mode = INFO

	logEnabled = True
	logDebugEnabled = False
	LOG_FILE = ""
	

	@staticmethod
	def logDebug(msg):
		if o2log.logDebugEnabled:
			o2log.writeLog(msg, 'DEBUG')
	@staticmethod
	def logInfo(msg):
		o2log.writeLog(msg, 'INFO')
	@staticmethod
	def logError(msg):
		o2log.writeLog(msg, 'ERROR')
	@staticmethod
	def writeLog(msg, type):
		try:
			if not o2log.logEnabled:
				return
			o2log.LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'o2tv.log')
			f = open(o2log.LOG_FILE, 'a')
			dtn = datetime.datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] +" ["+type+"] %s\n" % msg)
			f.close()
		except:
#			 print( "####O2-TV#### write log failed!!!" )
			pass
#		 finally:
#			 print( "####O2-TV#### ["+type+"] "+msg )

class O2TvContentProvider(ContentProvider):
	__metaclass__ = Singleton
	ISO_639_1_CZECH = None
	par = None

	def __init__(self, username=None, password=None, filter=None):
		try:
			ContentProvider.__init__(self, name='czsklib', base_url='/', username=username, password=password, filter=filter)
			#util.init_urllib()
			self.usr = username
			self.pwd = password
			self.devId = ''
			self.o2language = 'ces'
			self.showEpg = False
			self.useNewLoginMethod = True
			self.devName = "Nexus 7"
			self.token = None
			self.language = language.getLanguage()
			self.streamQuality = 'HD'
			self.init_trans()
			o2log.logInfo("init o2tv...");
			self.session = None
			self.header = { "X-NanguTv-App-Version" : "Android 1.2.9",
							"X-NanguTv-Device-Name" : self.devName,
							"User-Agent" : "Dalvik/2.1.0 (Linux; U; Android 5.1.1; Nexus 6 Build/LMY47A)",
							"Accept-Encoding": "gzip",
							"Connection" : "Keep-Alive" }
		except:
			o2log.logError("init o2tv failed.\n%s"%traceback.format_exc())
			pass

	def capabilities(self):
		return ['resolve', 'categories']

	def categories(self):
		result = []
		try:
			if self.usr=='' or self.usr is None or self.pwd == '' or self.pwd is None:
				raise Exception('1')
			
			for c in self.getData():
				item = self.video_item(url=c['url'], img=None, quality='')
				item['title']= c['cname']
				result.append(item)
		except Exception as err:
			o2log.logError("Categories failed. %s"%traceback.format_exc())
			self.showMsg('%s'%err, 30)
			result.append(self.dir_item(title='ERROR - prihlasovacie udaje', url='xxx'))

		return result

	def resolve(self, item, captcha_cb=None, select_cb=None):
		res = []
		r = requests.get(item['url'], headers=self.header).text
		for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+)\s(?P<chunklist>[^\s]+)', r, re.DOTALL):
			itm = item.copy()
			itm['title']=item['title']
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
#			 addLink('['+itm['quality']+'] '+itm['title'],itm['url'],None,"")
		res = sorted(res,key=lambda i:(len(i['quality']),i['quality']), reverse = True)

		if len(res) == 1:
			return res[0]
		elif len(res) > 1 and select_cb:
			return select_cb(res)
		return []

	def getAt(self):
		if self.useNewLoginMethod:
			return self.getAtNew()
		return self.getAtOld()
	def getAtNew(self):
		try:
			o2log.logDebug("getting AT...")
			headers =  {
				'X-NanguTv-Device-Name': self.devId,
				'X-NanguTv-App-Version': 'Android',
				'User-Agent': 'okhttp/3.10.0',
				'Accept-Encoding': 'gzip',
				'Connection': 'Keep-Alive',
				'Content-Type': 'application/x-www-form-urlencoded'}
			data = {'username': self.usr,
					'password': self.pwd}
			req = requests.post('https://ottmediator.o2tv.cz:4443/ottmediator-war/login', data=data, headers=headers, verify=False)
			o2log.logDebug("AT1=%s"%req.text)
			j = req.json()
			service_id = str(j['services'][0]['service_id'])
			rat = str(j['remote_access_token'])

			data = {'service_id': service_id, 'remote_access_token': rat}
			req = requests.post('https://ottmediator.o2tv.cz:4443/ottmediator-war/loginChoiceService', data=data, headers=headers, verify=False)
		
			headers = {
				'Content-Type': 'application/x-www-form-urlencoded',
				'Connection': 'Keep-Alive'}
			data = {
				'client_id': 'tef-web-portal-etnetera',
				'client_secret': '2b16ac9984cd60dd0154f779ef200679',
				'platform_id': '231a7d6678d00c65f6f3b2aaa699a0d0',
				'language': 'cs',
				'grant_type': 'remote_access_token',
				'remote_access_token': rat,
				'authority': 'tef-sso',
				'isp_id': '1'}
			req = requests.post('https://oauth.o2tv.cz/oauth/token', data=data, headers=headers, verify=False)
			j = req.json()

			self.checkResponse(j)
			self.token = j['access_token']
			o2log.logInfo("get AT (new) success")
			return self.token
		except:
			o2log.logError("Get AT (new) failed.\n%s"%traceback.format_exc())
			raise Exception('1')
	def getAtOld(self):
		try:
			o2log.logDebug("getting AT...")

			headers = {
				'Content-Type': 'application/x-www-form-urlencoded',
				'Connection': 'Keep-Alive'}
			data = {  
				  'grant_type' : 'password',
				  'client_id' : 'tef-web-portal-etnetera',
				  'client_secret' : '2b16ac9984cd60dd0154f779ef200679',
				  'username' : self.usr,
				  'password' : self.pwd,
				  'platform_id' : '231a7d6678d00c65f6f3b2aaa699a0d0',
				  'language' : 'cs'}
			req = requests.post('https://oauth.o2tv.cz/oauth/token', data=data, headers=headers, verify=False)
			j = req.json()

			self.checkResponse(j)
			self.token = j['access_token']
			o2log.logInfo("get AT (old) success")
			return self.token
		except:
			o2log.logError("Get AT (old) failed.\n%s"%traceback.format_exc())
			raise Exception('1')

	def checkResponse(self, jsonResp):
		if 'statusCode' in jsonResp:
			emsg = 'ERROR MSG'
			smsg = 'STATUS MSG'
			scode = '-1'
			if 'statusMessage' in jsonResp: smsg=jsonResp['statusMessage']
			if 'errorMessage' in jsonResp: emsg=jsonResp['errorMessage']
			if 'statusCode' in jsonResp: scode=toString(jsonResp['statusCode'])
			if scode=='401': # invalid AT
				raise ResolveException("%s: %s (%s)"%(scode, smsg, emsg))
			else:
				raise Exception("%s: %s (%s)"%(scode, smsg, emsg))
	def getInfo(self):
		cookies = { "access_token": self.token, "deviceId": self.devId }
		j = self._get('http://app.o2tv.cz/sws/subscription/settings/subscription-configuration.json', None, self.header, cookies, True, 6).json()
		o2log.logDebug("#### subscription=%s"%j)
		self.checkResponse(j)
		subscription_code = toString(j["subscription"])
		offer = j["billingParams"]["offers"]
		tariff = j["billingParams"]["tariff"]
		locality = j["locality"]
		isp = toString(j["isp"])

		devType = "STB" #TABLET, MOBILE, PC
		params = { 
			"locality": locality,
			"tariff": tariff,
			"isp": isp,
			"language": self.o2language,
			"deviceType": devType,
			"liveTvStreamingProtocol":"HLS",
			"offer": offer
			}
		c = self._get('http://app.o2tv.cz/sws/server/tv/channels.json', params, self.header, cookies, True, 6).json()
		o2log.logDebug("#### channels=%s"%c)
		self.checkResponse(c)

		data = []
		distinct = []
		for key, value in c['channels'].items():
			if value['channelType'] != 'TV':
				continue
			try:
				# contains some channels with same name but not by channel key (bit strange)
				cn = toString(value['channelName']).lower()
				if	cn in distinct:
					continue
				distinct.append(cn)
				params = {"serviceType": "LIVE_TV",
						  "subscriptionCode": subscription_code,
						  "channelKey": value['channelKey'],
						  "deviceType": devType,
						  "streamingProtocol":"HLS"}
				cd = self._get('http://app.o2tv.cz/sws/server/streaming/uris.json', params, self.header, cookies, True, 6).json()
				uri = cd['uris'][0]['uri']
				for u in cd['uris']:
					if u['resolution'] == self.streamQuality:
						uri = u['uri']
						break
				data.append({'ckey':toString(value['channelKey']), 'cname':toString(value['channelName']), 'url':uri})
			except:
				o2log.logError('Add channel failed (%s)\n%s.'%(key, traceback.format_exc()))
		data.sort(key=lambda x: x['cname'], reverse=False)
		if self.showEpg:
			for d in data:
				try:
					d['cname'] = d['cname']+ (' (%s)'%self.getEpg(d['ckey'], cookies))
				except:
					o2log.logError('Load channel EPG failed (%s)\n%s.'%(d['ckey'], traceback.format_exc()))

		return data

	def getData(self):
		o2Info = None

		if self.token is None:
			self.getAt()
		try:
			o2Info = self.getInfo()
		except ResolveException as err:
			o2log.logInfo('Invalid AT, try login...')
			self.getAt()
			o2Info = self.getInfo()
		except:
			raise
		return o2Info

	def getEpg(self, channelKey, cookies):
		#
		# @TODO rewrite to find EPG in time, because now you can't CACHE response !!! (diffrent timestamp every time)
		#
		dtFrom, dtTo = self.getDatesRangeSimple()
		params = {"channelKey": channelKey,
					"fromTimestamp": dtFrom,
					"language": self.o2language,
					"toTimestamp": dtTo}
		cd = self._get('http://app.o2tv.cz/sws/server/tv/channel-programs.json', params, self.header, cookies, True, 30).json()
		o2log.logDebug("#### EPG=%s"%cd)
		return toString(cd[0]['name'])

	def getDatesRangeSimple(self):
		now = datetime.datetime.utcnow()
		to = now + datetime.timedelta(hours=2)
		epoch = datetime.datetime.utcfromtimestamp(0)
		epochNow = '%s'%int((now - epoch).total_seconds() * 1000)
		epochTo = '%s'%int((to - epoch).total_seconds() * 1000)
		return epochNow, epochTo

	def getDatesRange(self):
		self.EpgDaysForward = 3
		pub = datetime.date.today()
		now = datetime.datetime(pub.year, pub.month, pub.day)
		to = now + datetime.timedelta(days=self.EpgDaysForward+1)
		epoch = datetime.datetime.utcfromtimestamp(0)
		epochNow = '%s'%int((now - epoch).total_seconds() * 1000)
		epochTo = '%s'%int((to - epoch).total_seconds() * 1000)
		return epochNow, epochTo

	def init_trans(self):
		self.trans = {
			"1": {"sk_SK":"Prihlásenie zlyhalo.",
				  "en_EN":"Login failed.",
				  "cs_CZ":"Prihlásenie zlyhalo."},
			
			}
	
	def showMsg(self, msgId, showSec, canClose=True, isError=True):
		try:
			msgType = "error"
			#if not isError:
			#	 msgType = "info"
			client.add_operation("SHOW_MSG", {
												'msg': self._getName(msgId),
												'msgType': msgType,
												'msgTimeout': showSec,
												'canClose': canClose
											 })
		except:
			o2log.logError("showMsg failed (minimalna verzia archivCZSK 1.1.2).\n%s"%traceback.format_exc())
			from Plugins.Extensions.archivCZSK.gui.common import showErrorMessage
			showErrorMessage(self.session, ("ERRmsg - %s"%self._getName(msgId)), showSec)
			pass

	@lru_cache(maxsize = 500, timeout = 30*60) #30min
	def cache_request_30(self, url, qs, headers, cookies):
		o2log.logDebug("NOT CACHED REQUEST")
		return requests.get(url, params=qs, headers=headers, cookies=cookies)
	@lru_cache(maxsize = 500, timeout = 60*60) #1h
	def cache_request_1(self, url, qs, headers, cookies):
		o2log.logDebug("NOT CACHED REQUEST")
		return requests.get(url, params=qs, headers=headers, cookies=cookies)
	@lru_cache(maxsize = 500, timeout = 180*60) #3h
	def cache_request_3(self, url, qs, headers, cookies):
		o2log.logDebug("NOT CACHED REQUEST")
		return requests.get(url, params=qs, headers=headers, cookies=cookies)
	@lru_cache(maxsize = 250, timeout = 360*60) #6h
	def cache_request_6(self, url, qs, headers, cookies):
		o2log.logDebug("NOT CACHED REQUEST")
		return requests.get(url, params=qs, headers=headers, cookies=cookies)
	@lru_cache(maxsize = 100, timeout = 12*60*60) #12h
	def cache_request_12(self, url, qs, headers, cookies):
		o2log.logDebug("NOT CACHED REQUEST")
		return requests.get(url, params=qs, headers=headers, cookies=cookies)

	def get_data_cached(self, url, qs, headers, cookies, useCache, timeout):
		if useCache:
			if timeout==1:
				return self.cache_request_1(url, qs, headers, cookies);
			if timeout==3:
				return self.cache_request_3(url, qs, headers, cookies);
			if timeout==6:
				return self.cache_request_6(url, qs, headers, cookies);
			if timeout==12:
				return self.cache_request_12(url, qs, headers, cookies);

			return self.cache_request_30(url, qs, headers, cookies);
		else:
			return requests.get(url, params=qs, headers=headers, cookies=cookies)

	def _get(self, url, qs, headers, cookies, useCache=False, cacheTimeout=30):
		try:
			start = datetime.datetime.now()
			resp = self.get_data_cached(url, qs, headers, cookies, useCache, cacheTimeout)
			o2log.logDebug("Request takes: %s s\n%s"%((datetime.datetime.now()-start).total_seconds(), url))
			return resp
		except HTTPError as err:
			raise err
		except:
			o2log.logError("Chyba pripojenia.\n%s"%traceback.format_exc())
			raise

	def _getName(self, id):
		try:
			if self.language!="sk_SK" and self.language!="en_EN" and self.language!="cs_CZ":
				self.language="en_EN"

			if id in self.trans:
				return self.trans[id][self.language]
		except Exception:
			pass
		return id



'''
************************************ MAIN
'''


o2log.logDebugEnabled = __gets('debug_enabled') == 'true'

def getDeviceUid():
	uid = str(__gets('deviceid'))
	try:
		if len(uid)>5:
			return uid
		uid = ''
		import uuid
		mac = uuid.getnode()
		o2log.logDebug("##### UID_hex=%s"%mac)
		hx = hex((mac*7919)%(2**64))
		o2log.logDebug("##### UID_hex=%s"%hx)
		uid = str('0000000000000000'+hx[2:-1])[-16:]
		o2log.logDebug("##### UID_xx=%s"%uid)
		__sets('deviceid', uid)
		return uid
	except:
		o2log.logError('Generate UID from MAC failed, get random.')
		import random
		uid = ''.join([random.choice('0123456789abcdef') for x in range(16)])
		__sets('deviceid', uid)
		return uid
	__sets('deviceid', 'empty-uid')
	return 'empty-uid'


prov = O2TvContentProvider(username=__gets('o2tvuser'), password=__gets('o2tvpwd'))
prov.usr = __gets('o2tvuser')
prov.pwd = __gets('o2tvpwd')
prov.devId = getDeviceUid()
prov.showEpg = __gets('show_epg')=='true'
prov.useNewLoginMethod = __gets('login_method')=='0'
prov.session = session
settings = {'quality': __gets('quality')}
if __gets('stream_quality') == '1':
	prov.streamQuality = 'SD' # HD default
if __gets('o2lang') == '0':
	prov.o2language = 'slo'
else:
	prov.o2language = 'ces'

o2log.logDebug("PARAMS=%s"%params)
xbmcprovider.XBMCMultiResolverContentProvider(prov,settings,__addon__, session).run(params)
