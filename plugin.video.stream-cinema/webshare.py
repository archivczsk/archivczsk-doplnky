# -*- coding: UTF-8 -*-
#/*
# *		 Copyright (C) 2017 bbaron
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
from md5crypt import md5crypt
import xml.etree.ElementTree as ET
import hashlib
from provider import ResolveException
import random
import re
import sys
import traceback
import util
import datetime
from time import strftime
from scinema import sclog

try:
	from urllib2 import HTTPError
	from urlparse import parse_qsl
	from urllib import quote, quote_plus, urlencode
except:
	from urllib.parse import quote, quote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError

class wsUserData(object):
	def __init__(self, isVip, vipDaysLeft, userId):
		self.isVip = isVip
		self.vipDaysLeft = vipDaysLeft
		self.userId = userId

class Webshare():

	def __init__(self,username=None,password=None,useHttps=False,cache=None,saveVipDays=False):
		self.username = username
		self.password = password
		self.base_url = 'http://webshare.cz/'
		if useHttps:
			self.base_url = 'https://webshare.cz/'
		self.token = ''
		#util.init_urllib()
		self.login()
		self.loginOk = False
		if self.token:
			self.loginOk = True
		if saveVipDays:
			self.saveVipDaysToSettings()
		
	def _url(self, url):
		"""
		Transforms relative to absolute url based on ``base_url`` class property
		"""
		if url.startswith('http'):
			return url
		return self.base_url + url.lstrip('./')

	def _create_request(self,url,base):
		args = dict(parse_qsl(url))
		headers = {'X-Requested-With':'XMLHttpRequest','Accept':'text/xml; charset=UTF-8','Referer':self.base_url}
		req = base.copy()
		for key in req:
			if key in args:
				req[key] = args[key]
		return headers,req

	def login(self):
		if not self.username and not self.password:
			return True # fall back to free account
		elif self.username and self.password and len(self.username)>0 and len(self.password)>0:
			#util.info('Login user=%s, pass=*****' % self.username)
			#sclog.logDebug("Login start...")
			# get salt
			headers,req = self._create_request('',{'username_or_email':self.username})
			sclog.logDebug("Webshare login try '%s' ..."%self._url('api/salt/'))
			data = util.post(self._url('api/salt/'),req,headers=headers)
			xml = ET.fromstring(data)
			if not xml.find('status').text == 'OK':
				#sclog.logDebug("Login end salt...")
				#util.error('Server returned error status, response: %s' % data)
				return False
			salt = xml.find('salt').text
			if salt is None:
				salt = ''
			# create hashes
			password = hashlib.sha1(md5crypt(self.password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
			digest = hashlib.md5(self.username.encode('utf-8') + b':Webshare:' + self.password.encode('utf-8')).hexdigest()
			# login
			headers,req = self._create_request('',{'username_or_email':self.username,'password':password,'digest':digest,'keep_logged_in':1})
			data = util.post(self._url('api/login/'),req,headers=headers)
			xml = ET.fromstring(data)
			#sclog.logDebug("Login end...")
			if not xml.find('status').text == 'OK':
				#util.error('Server returned error status, response: %s' % data)
				return False
			
			self.token = xml.find('token').text
			#util.info('Login successfull')
			return True
		return False

	def userData(self):
		if self.token:
			headers,req = self._create_request('/',{'wst':self.token})
			data = util.post(self._url('api/user_data/'), req, headers=headers)
			xml = ET.fromstring(data)
			xml.find('vip').text
			isVip = xml.find('vip').text
			vipDays = xml.find('vip_days').text
			ident = xml.find('ident').text

			if isVip != '1':
				isVip = '0'
			return wsUserData(isVip, vipDays, ident)
		return wsUserData('-1', '0', '')

	def saveVipDaysToSettings(self):
		vipDaysLeft = "-99"
		try:
			if self.token and self.loginOk:
				udata = userData()
				vipDaysLeft = udata.vipDaysLeft
			else:
				vipDaysLeft = "-2"			  
		except:
			pass

		# save to settings
		try:
			from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
			addon = ArchivCZSK.get_xbmc_addon('plugin.video.stream-cinema')
			addon.setSetting('wsvipdays', vipDaysLeft)
		except:
			pass

	def sendStats(self, item, action, baseUrl, apiVer, deviceId):
		#send data to server about watching movie
		#sclog.logDebug('Stats start...')
		udata = self.userData()
		urlStats = baseUrl + '/Stats?ver='+apiVer+'&uid='+deviceId
		
		dur = float(item['duration'])
		brate = int(item['bitrate'])
		ep = ''
		se = ''
		if 'episode' in item:
			ep = str(item['episode'])
		if 'season' in item:
			se = str(item['season'])
		now = datetime.datetime.now()
		endIn = now + datetime.timedelta(seconds=int(dur))
		endStr = endIn.strftime('%H:%M:%S')

		data = { 'vip':udata.isVip, 'vd': udata.vipDaysLeft, 'est':endStr, 'scid':str(item['id']), 
				 'action': action, 'ws':udata.userId, 'dur':dur, 'bitrate':brate,
				 'ep':ep, 'se':se }
			
		#sclog.logDebug('data=%'%data)

		headers = {'Content-Type':'application/json', 'X-Uid':deviceId}
		response = util.post_json(urlStats, data, headers)

		sclog.logDebug('Stats(%s)=%s'%(item['id'], response))

		return udata

	def resolve(self, ident, devid, dwnType='video_stream'):
		try:
			headers,req = self._create_request('/',{'ident':ident,'wst':self.token, 'download_type': dwnType, 'device_uuid': devid })
			# @TODO add params, maybe later 'device_res_x': infoLabel('System.ScreenWidth'), 'device_res_y': infoLabel('System.ScreenHeight'),
			
			#util.info(headers)
			#util.info(req)
			data = util.post(self._url('api/file_link/'), req, headers=headers)
			xml = ET.fromstring(data)
			if not xml.find('status').text == 'OK':
				#util.error('Server returned error status, response: %s' % data)
				raise ResolveException(xml.find('message').text)
			return xml.find('link').text
		except:
			raise

	def search(self, title):
		result = []
		headers,req = self._create_request('/',{'what': title, 'offset': 0, 'limit': 30, 'category': 'video', 'sort': 'rating', 'wst': self.token})
		data = util.post(self._url('api/search/'), req, headers=headers)
		xml = ET.fromstring(data)
		if not xml.find('status').text == 'OK':
			self.error('Server returned error status, response: %s' % data)
			return []
		total = int(xml.find('total').text)
		for file in xml.findall('file'):
			item = {}
			item['title'] = file.find('name').text
			item['url'] = 'ident=%s' % file.find('ident').text
			osize = file.find('size').text
			size = int(file.find('size').text)
			item['size'] = '%d MB' % (int(size)/1024/1024)
#			 img = file.find('img').text
#			 if img:
#				 item['img'] = self._url(img)
			item['img'] = file.find('img').text
			result.append(item)
#			 sclog.logDebug(item['url']+str(osize)+item['size']+item['img']+item['title'])
#		 listed = int(req['limit']) + int(req['offset'])
#		 if total > listed:
#			 req['offset'] = listed
#			 item = self.dir_item()
#			 item['type'] = 'next'
#			 item['url'] = urllib.urlencode(req)
#			 result.append(item)
#			 sclog.logDebug(item['url']+item['type'])
		return result
