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

#sys.path.append( os.path.join ( os.path.dirname(__file__),'resources','lib') )
#sys.path.append( os.path.join ( os.path.dirname(__file__),'myprovider') )
sys.path.append( os.path.dirname(__file__) )

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

import re
#import util,xbmcprovider,xbmcutil
from scinema import StreamCinemaContentProvider, StreamCinemaProvider, StaticDataSC, sclog, StaticTraktWatched
from trakttv import trakt_tv

__scriptid__   = 'plugin.video.stream-cinema'
__scriptname__ = 'stream-cinema.online'
__addon__	   = ArchivCZSK.get_xbmc_addon(__scriptid__)
__language__   = __addon__.getLocalizedString
__gets		   = __addon__.getSetting
__sets		   = __addon__.setSetting

sclog.logDebugEnabled = __gets('debug_enabled') == 'false'

def getDeviceUid():
	uid = str(__gets('deviceid'))
	try:
		if uid.startswith('e2-'):
			if not (uid.startswith("e2-mac-") or uid.startswith("e2-rnd-")):
				return uid
		uid = ''
		   
		import uuid
		# save to settings and return
		uid = 'e2-'+str(uuid.uuid4())
		__sets('deviceid', uid)
		return uid
	except:
		if uid == '':
			import random
			import string
			uid = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(32))
			uid = 'e2-'+uid
			__sets('deviceid', uid)
			return uid
		pass
	__sets('deviceid', 'e2-empty')
	return 'e2-empty'
def fixXcursor():
	try:
		login = __gets('wsuser')
		pwd = __gets('wspass')
		if 'XcursorX' in login:
			login = str(login).replace('XcursorX','')
			__sets('wsuser', login)
		if 'XcursorX' in pwd:
			pwd = str(pwd).replace('XcursorX','')
			__sets('wspass', pwd)
	except:
		pass
def checkSetVIP(u, p, https):
	try:
		sclog.logDebug("StaticDataSC hit...")
		tmp = StaticDataSC(username=u, password=p, useHttps=https)
		sclog.logDebug("StaticDataSC DONE vipDays=%s"%tmp.vipDaysLeft)
		__sets('wsvipdays', tmp.vipDaysLeft)
	except:
		pass


settings = {'quality':__addon__.getSetting('quality'), 'keep-searches': __addon__.getSetting('keep-searches')}

reverse_eps = __gets('order-episodes') == '0'
use_https = __gets('use_https') == 'true'
trakt_enabled = __gets('trakt_enabled')=='true'

# fix entry by virtual keyboard
fixXcursor()
# set number of days left for VIP account
checkSetVIP(__gets('wsuser'), __gets('wspass'), use_https)

cl1='866e99f0dd041248dfc37c8c056b13ec97d8f930ee9cb608e611ad4e1db02cb1'
cl2='99d5d9360d0ea5586871560dbe9c643346105d6aaed76ab29a6c2138a9f35d6b'
token=__gets('trakt_token')
ref_token=__gets('trakt_refresh_token')
expireAt = 0
tmp = __gets('trakt_token_expire')
if tmp!='':
	try:
		expireAt = int(tmp)
	except:
		pass

scinema = StreamCinemaContentProvider(username=__gets('wsuser'),password=__gets('wspass'), useHttps=use_https,reverse_eps=reverse_eps)

# must set again (reason: singleton)
scinema.wsuser = __gets('wsuser')
scinema.wspass = __gets('wspass')
scinema.useHttps = use_https
scinema.trakt_enabled = trakt_enabled
scinema.trakt_filter = __gets('trakt_filter')
scinema.tapi = trakt_tv(cl1, cl2, token, ref_token, expireAt)
StaticTraktWatched().tapi = scinema.tapi

# must set again (reason: singleton)
scinema.deviceUid = getDeviceUid()
scinema.itemOrderGenre = __gets('item_order_genre')
scinema.itemOrderCountry = __gets('item_order_country')
scinema.itemOrderQuality = __gets('item_order_quality')
#scinema.automaticSubs = __gets('auto_subs')=='true'
scinema.langFilter = __gets('item_filter_lang')
scinema.streamSizeFilter = __gets('stream_max_size')
scinema.streamHevc3dFilter = __gets('filter_hevc_3d') == 'true'

scinema.session = session

sclog.logDebug("PARAMS=%s"%params)

if 'play' in params and 'ident' in params['play']:
	from webshare import Webshare as wx
	ws = wx(scinema.wsuser, scinema.wspass, scinema.useHttps)
	link = ws.resolve(params['play'][6:], scinema.deviceUid)
	from Plugins.Extensions.archivCZSK.engine.client import add_video
	add_video(params['title'], link, None, None)
else:
	StreamCinemaProvider(scinema,settings,__addon__, session).run(params)
