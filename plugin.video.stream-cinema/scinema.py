# -*- coding: UTF-8 -*-
# /*
# *		 Copyright (C) 2017 chaoss (origin from bbaron)
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

import sys
import os
import json
import traceback
import datetime
import util
import xbmcprovider,xbmcutil
from trakttv import trakt_tv, TraktRefreshException

from provider import ContentProvider, cached, ResolveException
from time import strftime
from cachestack import lru_cache
from Components.config import config
from Components.Language import language
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.compat import eConnectCallback

try:
	from urllib2 import HTTPError
	from urlparse import parse_qsl
	from urllib import quote, quote_plus, urlencode
except:
	from urllib.parse import quote, quote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError

#sys.path.append( os.path.join ( os.path.dirname(__file__),'myprovider') )
#sys.setrecursionlimit(10000)



API_VERSION="1.3"

class sclog(object):
	ERROR = 0
	INFO = 1
	DEBUG = 2
	mode = INFO

	logEnabled = True
	logDebugEnabled = False
	LOG_FILE = ""
	

	@staticmethod
	def logDebug(msg):
		if sclog.logDebugEnabled:
			sclog.writeLog(msg, 'DEBUG')
	@staticmethod
	def logInfo(msg):
		sclog.writeLog(msg, 'INFO')
	@staticmethod
	def logError(msg):
		sclog.writeLog(msg, 'ERROR')
	@staticmethod
	def writeLog(msg, type):
		try:
			if not sclog.logEnabled:
				return
			sclog.LOG_FILE = os.path.join(config.plugins.archivCZSK.logPath.getValue(),'stream-cinema.log')
			f = open(sclog.LOG_FILE, 'a')
			dtn = datetime.datetime.now()
			f.write(dtn.strftime("%d.%m.%Y %H:%M:%S.%f")[:-3] +" ["+type+"] %s\n" % msg)
			f.close()
		except:
			print( "####STREAM-CINEMA#### write log failed!!!" )
			pass
		finally:
			print( "####STREAM-CINEMA#### ["+type+"] "+msg )

class Singleton(type):
	_instances = {}
	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]

class StaticDataSC():
	__metaclass__ = Singleton
	
	def __init__(self, username=None, password=None, useHttps=False):
		self.vipDaysLeft = "-1"
		sclog.logDebug("StaticDataSC init...")

		if username and password:
			try:
				login = username
				pwd = password
				from webshare import Webshare as wx
				ws = wx(login, pwd, useHttps)
				if ws.loginOk:
					udata = ws.userData()
					self.vipDaysLeft = udata.vipDaysLeft
				else:
					self.vipDaysLeft = "-2"
			except:
				self.vipDaysLeft = "-99"
				sclog.logError("get vip days left failed.\n%s"%traceback.format_exc())
				pass
class StaticTraktWatched():
	__metaclass__ = Singleton
	def __init__(self):
		sclog.logDebug("StaticTraktWatched init...")
		self.tapi = None
		self.moviesTrakt = set()
		self.moviesTvdb = set()
		self.moviesImdb = set()
		self.showsTrakt = {}
		self.showsTvdb = {}
		self.reload = True
		self.loadUserWatchedError = False

	def reloadData(self):
		self.moviesTrakt = set()
		self.moviesTvdb = set()
		self.showsTrakt = {}
		self.showsTvdb = {}
		m, s = self.tapi.get_watched()
		for x in m:
			self.moviesTrakt.add(int(x['movie']['ids']['trakt']))
			#try:
			if 'tvdb' in x['movie']['ids'] and x['movie']['ids']['tvdb'] is not None:
				self.moviesTvdb.add(int(x['movie']['ids']['tvdb']))
			if 'imdb' in x['movie']['ids'] and x['movie']['ids']['imdb'] is not None:
				self.moviesImdb.add(x['movie']['ids']['imdb'].replace('tt',''))
			#except:
			#	 sclog.logDebug("TRAKT: reload data add movie failed.\n%s\n%s"%(x, traceback.format_exc()))
		for x in s:
			seasons = x['seasons']
			self.showsTrakt[int(x['show']['ids']['trakt'])] = seasons
			if 'tvdb' in x['show']['ids'] and x['show']['ids']['tvdb'] is not None:
				self.showsTvdb[int(x['show']['ids']['tvdb'])] = seasons
	
	def getItemType(self, item):
		try:
			tp = self.tapi.getItemType(item)
			#sclog.logDebug("TRAKT: returning item type=%s"%tp)
			return tp
		except:
			#sclog.logDebug("TRAKT: returning item type=-2")
			return -2

	def isMatch(self, item, itemType):
		if itemType==1:
			if 'trakt' in item:
				return int(item['trakt']) in self.moviesTrakt, None
			if 'tvdb' in item:
				return int(item['tvdb']) in self.moviesTvdb, None
			if 'imdb' in item:
				return item['imdb'].replace('tt','') in self.moviesImdb, None
		elif itemType==4:
			if 'trakt' in item:
				id = int(item['trakt'])
				if id in self.showsTrakt:
					return True, self.showsTrakt[id] 
			if 'tvdb' in item:
				id = int(item['tvdb'])
				if id in self.showsTvdb:
					return True, self.showsTvdb[id]
		return False, None

	def isMatchSeasonEpisode(self, season, episode, data):
		for x in data:
			if int(x['number'])==season:
				for y in x['episodes']:
					if int(y['number'])==episode:
						return True
				break
		return False

	def isWatched(self, item, itype):
		if self.reload and self.tapi.valid():
			self.reload = False
			sclog.logDebug("StaticTraktWatched reloading watched items...")
			try:
				self.reloadData()
				self.loadUserWatchedError = False
			except:
				sclog.logError("StaticTraktWatched load TRAKT user watched items failed.\n%s"%traceback.format_exc())
				# realod data after next whole movies page load on UI not for each item when loading (time consuming)
				self.loadUserWatchedError = True
				return False
		try:
			matched, foundShow = self.isMatch(item, itype)
			if itype==1:
				return matched
			elif itype==4:
				if matched:
					return self.isMatchSeasonEpisode(int(item['season']), int(item['episode']), foundShow)#x['seasons'])
		except:
			sclog.logError("StaticTraktWatched isWatched failed.item=%s\n%s"%(item,traceback.format_exc()))
		return False

class StreamCinemaProvider(xbmcprovider.XBMContentProvider):
	def __init__(self, provider, settings, addon, session):
		xbmcprovider.XBMContentProvider.__init__(self, provider, settings, addon, session)
		#self.check_setting_keys(['quality'])

	def resolve(self, url):
		def select_cb(resolved):
			#resolved = resolver.filter_by_quality(resolved, self.settings['quality'] or '0')
			if len(resolved) == 1:
				return resolved[0]
			else:
				stream_list = []
				if 'resolveTitle' in resolved[0]:
					stream_list = ['%s'%(s['resolveTitle']) for s in resolved]
				else:
					strem_list = ['%s empty'%(s['quality']) for s in resolved]
				idx = client.getListInput(self.session, stream_list, '')
				if idx == -1:
					return None
				return resolved[idx]

		item = self.provider.video_item()
		item.update({'url':url})
		try:
			return self.provider.resolve(item, select_cb=select_cb)
		except ResolveException as e:
			sclog.logError("Resolve item failed.\n%s"%traceback.format_exc())
			self._handle_exc(e)

class StreamCinemaContentProvider(ContentProvider):
	__metaclass__ = Singleton
	ISO_639_1_CZECH = None
	par = None

	def __init__(self, username=None, password=None, useHttps=False, filter=None, reverse_eps=False):
		try:
			self.useHttps = useHttps

			ContentProvider.__init__(self, name='czsklib', base_url=self.getBaseUrl(), username=username, password=password, filter=filter)
			util.init_urllib()
			self.reverse_eps = reverse_eps
			self.ws = None
			self.wsuser = username
			self.wspass = password
			self.language = language.getLanguage()
			self.init_trans()
			sclog.logDebug("init stream-cinema...");
			self.deviceUid = None
			self.itemOrderGenre = '0'
			self.itemOrderCountry = '0'
			self.itemOrderQuality = '0'
			self.langFilter = '0'
			self.streamSizeFilter = '0'
			self.streamHevc3dFilter = False
			self.trakt_enabled = False
			self.trakt_filter = 0
			#self.automaticSubs = False
			self.session = None
			self.tapi = None
		except:
			sclog.logError("init stream-cinema failed.\n%s"%traceback.format_exc())
			pass

	def init_trans(self):
		self.trans = {
			#<!-- custom -->
			"66666": {"sk_SK":"Prihlasovacie údaje sú nesprávne alebo nie sú v plugine nastavené. \n\nAk nemáte účet tak sa prosím zaregistrujte na webshare.cz",
					  "en_EN":"Login data is wrong or is not set in the plugin settings. \n\nIf you do not have an account so please register at webshare.cz",
					  "cs_CZ":"Přihlašovací údaje jsou nesprávné nebo nejsou v pluginu nastaveny. \n\nPokud nemáte účet tak se prosím zaregistrujte na webshare.cz"},
			"66667": {"sk_SK":"Príliš veľa požiadaviek, prosím čakajte 1 minútu.",
					  "en_EN":"Too many requests, please wait 1 minute", 
					  "cs_CZ":"Příliš mnoho požadavků, prosím čekejte 1 minutu."},
			"66668": {"sk_SK":"Pre sledovanie videa bez sekania je potrebné mať VIP účet na webshare.cz. \n\nMinimálna rýchlosť internetu 5 Mb/s (0.625 MB/s)",
					  "en_EN":"To watch a video without freezing you need a VIP account at webshare.cz. Minimum internet speed 5 Mb/s (0.625 MB/s)", 
					  "cs_CZ":"Pro sledování videa bez sekání je třeba mít VIP účet na webshare.cz. Minimální rychlost internetu 5 Mb/s (0.625 MB/s)"},
			"66669": {"sk_SK":"Nepodarilo sa načítať hlavné menu (chyba pripojenia). \n\nZa vzniknuté problémy sa ospravedlňujeme.",
					  "en_EN":"Unable to load main menu (connection error). \ n\nWe are apologizing for the problems you have encountered.", 
					  "cs_CZ":"Nepodařilo se načíst hlavní menu (chyba připojení). \n\nZa vzniklé problémy se omlouváme."},
			"66670": {"sk_SK":"+tit","en_EN":"+sub", "cs_CZ":"+tit"},
			"66671": {"sk_SK":"Film nie je možné prehrať z dôvodu zapnutého filtra na veľkosť streamu.","en_EN":"Movie can not be played due to enabled stream size filter.", "cs_CZ":"Film není možné přehrát z důvodu zapnutého filtru na velikost streamu."},
			"66672": {"sk_SK":"Váš účet (IP adresa) bol dočasne zablokovaný.",
					  "en_EN":"Your account (IP address) was temporarily blocked.", 
					  "cs_CZ":"Váš účet (IP adresa) byl dočasně zablokován."},
			"66673": {"sk_SK":"Načítavanie zlyhalo.","en_EN":"Loadaing failed.", "cs_CZ":"Načítání selhalo."},
			"66674": {"sk_SK":"Prosím vykonajte autorizáciu zariadenia na URL \n\n%s\n\n s týmto kódom: %s\n\n a až následne stlačte OK!","en_EN":"Please authorize your device to URL \n\n%s\n\n with this code: %s \n\nand after that press OK!", "cs_CZ":"Prosím proveďte autorizaci zařízení na URL \n\n%s\n\n s tímto kódem: %s\n\n a až následně stiskněte OK!"},
			"66675": {"sk_SK":"Zariadenie bolo úspešne autorizované.","en_EN":"The device has been successfully authorized.", "cs_CZ":"Zařízení bylo úspěšně autorizováno."},
			"66676": {"sk_SK":"Autorizácia zariadenia neúspešná.","en_EN":"Device authorization is failed.", "cs_CZ":"Autorizace zařízení neúspěšná."},
			"66677": {"sk_SK":"(Trakt) Operácia prebehla úspešne.","en_EN":"(Trakt) Operation complete successfully.", "cs_CZ":"(Trakt) Operace proběhla úspěšně."},
			"66678": {"sk_SK":"(Trakt) Operácia zlyhala.","en_EN":"(Trakt) Operation failed.", "cs_CZ":"(Trakt) Operace selhala."},
			"66679": {"sk_SK":"Trakt nie je zapnutý v nastaveniach doplnku.","en_EN":"Trakt is not enabled in addon settings.", "cs_CZ":"Trakt není zapnutý v nastaveních doplňku."},
			"66680": {"sk_SK":"Trakt nie je spárovaný s týmto zariadením.","en_EN":"Trakt is not pair with this device.", "cs_CZ":"Trakt není spárován s tímto zařízením."},
			"66681": {"sk_SK":"Obnovenie prístupu trakt.tv zlyhalo. Prosím, opätovne spárujte zariadenie.","en_EN":"Restoring trakt.tv access failed. Please pair device again.", "cs_CZ":"Obnovení přístupu trakt.tv selhalo. Prosím, znovu spárujte zařízení."},
			
			#<!-- texty v menu -->
			"30008": {"sk_SK":"Novinky dabované","en_EN":"New dubbed", "cs_CZ":"Novinky dabované"},
			"30901": {"sk_SK":"Filmy","en_EN":"Movies", "cs_CZ":"Filmy"},
			"30902": {"sk_SK":"Seriály","en_EN":"Series", "cs_CZ":"Seriály"},
			"30903": {"sk_SK":"A-Z","en_EN":"A-Z", "cs_CZ":"A-Z"},
			"30904": {"sk_SK":"Najnovšie","en_EN":"New", "cs_CZ":"Nově přidané streamy"},
			"30950": {"sk_SK":"Najnovšie","en_EN":"New", "cs_CZ":"Nejnovější"},
			"30950 dub": {"sk_SK":"Najnovšie (dabing)","en_EN":"New (dubbing)", "cs_CZ":"Nejnovější (dabing)"},
			"30905": {"sk_SK":"Populárne","en_EN":"Popular", "cs_CZ":"Populární"},
			"30956": {"sk_SK":"Práve sledované","en_EN":"Watching now", "cs_CZ":"Právě sledované"},
			"30906": {"sk_SK":"Krajina","en_EN":"Country", "cs_CZ":"Země"},
			"30907": {"sk_SK":"Kvalita","en_EN":"Quality", "cs_CZ":"Kvalita"},
			"30908": {"sk_SK":"Žáner","en_EN":"Genre", "cs_CZ":"Žánr"},
			"30909": {"sk_SK":"Rok","en_EN":"Year", "cs_CZ":"Rok"},
			"30910": {"sk_SK":"TV dnes","en_EN":"TV today", "cs_CZ":"TV dnes"},
			"30918": {"sk_SK":"Pridať nové do knižnice","en_EN":"xxx", "cs_CZ":"yyy"},
			"30919": {"sk_SK":"Séria","en_EN":"Series", "cs_CZ":"Série"},
			"30920": {"sk_SK":"Naposledy pridané časti","en_EN":"Latest episodes", "cs_CZ":"Poslední přidané části"},
			"30921": {"sk_SK":"Naposledy pridané seriály","en_EN":"Latest series", "cs_CZ":"Poslední přidané seriály"},
			"30922": {"sk_SK":"Nastavenia","en_EN":"Settings", "cs_CZ":"Nastavení"},
			"30923": {"sk_SK":"Pridať do knižnice s odberom","en_EN":"xxx", "cs_CZ":"yyy"},
			"30924": {"sk_SK":"Zrušiť odber","en_EN":"xxx", "cs_CZ":"yyy"},
			"30925": {"sk_SK":"Knižnica","en_EN":"xxx", "cs_CZ":"yyy"},
			"30926": {"sk_SK":"Pridať do knižnice (všetko)","en_EN":"xxx", "cs_CZ":"yyy"},
			"30927": {"sk_SK":"Naposledy sledované","en_EN":"Last watched", "cs_CZ":"Naposledy sledované"},
			"30928": {"sk_SK":"TV program na 14 dní","en_EN":"TV program 14 days", "cs_CZ":"TV program na 14 dni"},
			"30929": {"sk_SK":"Naposledy pridané","en_EN":"Latest streams", "cs_CZ":"Nově přidané"},
			"30930": {"sk_SK":"1) Navštívte: [COLOR skyblue]%s[/COLOR]","en_EN":"xxx", "cs_CZ":"yyy"},
			"30931": {"sk_SK":"2) Po výzve zadajte [COLOR skyblue]%s[/COLOR]","en_EN":"xxx", "cs_CZ":"yyy"},
			"30932": {"sk_SK":"Účet už je autorizovany.[CR]Chcete sa odhlasit?","en_EN":"xxx", "cs_CZ":"yyy"},
			"30933": {"sk_SK":"Chcete sa odhlasit?","en_EN":"xxx", "cs_CZ":"yyy"},
			#<!-- dni v tyzdni -->
			"30911": {"sk_SK":"Pondelok","en_EN":"Monday", "cs_CZ":"Pondělí"},
			"30912": {"sk_SK":"Utorok","en_EN":"Tuesday", "cs_CZ":"Úterý"},
			"30913": {"sk_SK":"Streda","en_EN":"Wednesday", "cs_CZ":"Strěda"},
			"30914": {"sk_SK":"Štvrtok","en_EN":"Thursday", "cs_CZ":"Čtvrtek"},
			"30915": {"sk_SK":"Piatok","en_EN":"Friday", "cs_CZ":"Pátek"},
			"30916": {"sk_SK":"Sobota","en_EN":"Saturday", "cs_CZ":"Sobota"},
			"30917": {"sk_SK":"Nedeľa","en_EN":"Sunday", "cs_CZ":"Neděle"},
			#<!-- zanre -->
			"31001": {"sk_SK":"Akčné","en_EN":"Action", "cs_CZ":"Akční"},
			"31128": {"sk_SK":"Animované","en_EN":"Animated", "cs_CZ":"Animovaný"},
			"31210": {"sk_SK":"Dobrodružné","en_EN":"Adventure", "cs_CZ":"Dobrodružný"},
			"32795": {"sk_SK":"Dokumentárne","en_EN":"Documentary", "cs_CZ":"Dokumentární"},
			"31005": {"sk_SK":"Dráma","en_EN":"Drama", "cs_CZ":"Drama"},
			"36160": {"sk_SK":"Erotické","en_EN":"Erotic", "cs_CZ":"Erotický"},
			"90991": {"sk_SK":"Experimentálne","en_EN":"Experimental", "cs_CZ":"Experimentální"},
			"31211": {"sk_SK":"Fantasy","en_EN":"Fantasy", "cs_CZ":"Fantasy"},
			"37446": {"sk_SK":"Film-Noir","en_EN":"Film-Noir", "cs_CZ":"Film-Noir"},
			"31242": {"sk_SK":"Historické","en_EN":"Historic", "cs_CZ":"Historický"},
			"31394": {"sk_SK":"Horor","en_EN":"Horor", "cs_CZ":"Horor"},
			"32488": {"sk_SK":"Hudobné","en_EN":"Music", "cs_CZ":"Hudební"},
			"36570": {"sk_SK":"IMAX","en_EN":"IMAX", "cs_CZ":"IMAX"},
			"32029": {"sk_SK":"Katastrofické","en_EN":"Catastrophic", "cs_CZ":"Katastrofický"},
			"31003": {"sk_SK":"Komédie","en_EN":"Comedy", "cs_CZ":"Komédie"},
			"38861": {"sk_SK":"Krátkometrážne","en_EN":"Short", "cs_CZ":"Krátkometrážní"},
			"31002": {"sk_SK":"Krimi","en_EN":"Crime", "cs_CZ":"Krimi"},
			"47830": {"sk_SK":"Bábkové","en_EN":"Puppet", "cs_CZ":"Lotkové"},
			"32369": {"sk_SK":"Muzikálové","en_EN":"Musical", "cs_CZ":"Muzikál"},
			"31153": {"sk_SK":"Mysteriózne","en_EN":"Mystery", "cs_CZ":"Mysteriózní"},
			"46777": {"sk_SK":"Podobenstvo","en_EN":"Parable", "cs_CZ":"Podobenství"},
			"44656": {"sk_SK":"Poetické","en_EN":"Poetic", "cs_CZ":"Poetický"},
			"32820": {"sk_SK":"Rozprávkové","en_EN":"Fairytale", "cs_CZ":"Pohádky"},
			"37092": {"sk_SK":"Poviedkové","en_EN":"The stories", "cs_CZ":"Povídkový"},
			"33581": {"sk_SK":"Psychologické","en_EN":"Psychological", "cs_CZ":"Psychologický"},
			"88668": {"sk_SK":"Publicistické","en_EN":"Journalistic", "cs_CZ":"Publicistický"},
			"45004": {"sk_SK":"Reality-TV","en_EN":"Reality-TV", "cs_CZ":"Reality-TV"},
			"34722": {"sk_SK":"Road movie","en_EN":"Road movie", "cs_CZ":"Road movie"},
			"32368": {"sk_SK":"Rodinné","en_EN":"Family", "cs_CZ":"Rodinný"},
			"31086": {"sk_SK":"Romantické","en_EN":"Romance", "cs_CZ":"Romantický"},
			"31100": {"sk_SK":"Sci-Fi","en_EN":"Sci-Fi", "cs_CZ":"Sci-Fi"},
			"31694": {"sk_SK":"Športové","en_EN":"Sports", "cs_CZ":"Sportovní"},
			"87745": {"sk_SK":"Talk-show","en_EN":"Talk-show", "cs_CZ":"Talk-show"},
			"45920": {"sk_SK":"Tanečné","en_EN":"Dancing", "cs_CZ":"Taneční"},
			"31004": {"sk_SK":"Thriller","en_EN":"Thriller", "cs_CZ":"Thriller"},
			"31178": {"sk_SK":"Vojnové","en_EN":"War", "cs_CZ":"Válečný"},
			"31063": {"sk_SK":"Western","en_EN":"Western", "cs_CZ":"Western"},
			"31241": {"sk_SK":"Životopisné","en_EN":"Biographical", "cs_CZ":"Životopisný"},
			#<!-- krajny -->
			"87943": {"sk_SK":"Alžírsko","en_EN":"Algeria", "cs_CZ":"Alžírsko"},
			"38690": {"sk_SK":"Argentina","en_EN":"Argentina", "cs_CZ":"Argentina"},
			"88639": {"sk_SK":"Aruba","en_EN":"Aruba", "cs_CZ":"Aruba"},
			"33878": {"sk_SK":"Austrália","en_EN":"Australia", "cs_CZ":"Austrálie"},
			"36379": {"sk_SK":"Bahamy","en_EN":"Bahamas", "cs_CZ":"Bahamy"},
			"32312": {"sk_SK":"Belgicko","en_EN":"Belgium", "cs_CZ":"Belgie"},
			"95071": {"sk_SK":"Bielorusko","en_EN":"Belarus", "cs_CZ":"Bielorusko"},
			"88610": {"sk_SK":"Bolívia","en_EN":"Bolivia", "cs_CZ":"Bolívie"},
			"95050": {"sk_SK":"Bosna a Hercegovina","en_EN":"Bosnia and Herzegovina", "cs_CZ":"Bosna a Hercegovina"},
			"92038": {"sk_SK":"Botswana","en_EN":"Botswana", "cs_CZ":"Botswana"},
			"32806": {"sk_SK":"Brazília","en_EN":"Brazil", "cs_CZ":"Brazílie"},
			"97876": {"sk_SK":"Brunej","en_EN":"Brunei", "cs_CZ":"Brunej"},
			"46295": {"sk_SK":"Bulharsko","en_EN":"Bulgaria", "cs_CZ":"Bulharsko"},
			"31240": {"sk_SK":"Česko","en_EN":"Czech Republic", "cs_CZ":"Česko"},
			"32241": {"sk_SK":"ČeskoSlovensko","en_EN":"Czecho-Slovakia", "cs_CZ":"Československo"},
			"34001": {"sk_SK":"Čína","en_EN":"China", "cs_CZ":"Čína"},
			"31209": {"sk_SK":"Dánsko","en_EN":"Denmark", "cs_CZ":"Dánsko"},
			"52388": {"sk_SK":"Egypt","en_EN":"Egypt", "cs_CZ":"Egypt"},
			"46699": {"sk_SK":"Estónsko","en_EN":"Estonia", "cs_CZ":"Estonsko"},
			"37250": {"sk_SK":"Fed. rep. Juhoslávia","en_EN":"Yugoslavia", "cs_CZ":"Fed. rep. Juhoslávie"},
			"48468": {"sk_SK":"Filipíny","en_EN":"Philippines", "cs_CZ":"Filipíny"},
			"42879": {"sk_SK":"Fínsko","en_EN":"Finland", "cs_CZ":"Finsko"},
			"31060": {"sk_SK":"Francúzko","en_EN":"France", "cs_CZ":"Francie"},
			"52387": {"sk_SK":"Ghana","en_EN":"Ghana", "cs_CZ":"Ghana"},
			"46700": {"sk_SK":"Gruzínsko","en_EN":"Georgia", "cs_CZ":"Gruzie"},
			"31665": {"sk_SK":"Hong Kong","en_EN":"Hong Kon", "cs_CZ":"Hong Kon"},
			"31654": {"sk_SK":"Chile","en_EN":"Chile", "cs_CZ":"Chile"},
			"92437": {"sk_SK":"Chorvátsko","en_EN":"Croatia", "cs_CZ":"Chorvátsko"},
			"32441": {"sk_SK":"India","en_EN":"India", "cs_CZ":"Indie"},
			"41584": {"sk_SK":"Indonézia","en_EN":"Indonesia", "cs_CZ":"Indonézie"},
			"88163": {"sk_SK":"Irán","en_EN":"Iran", "cs_CZ":"Irán"},
			"35890": {"sk_SK":"Írsko","en_EN":"Ireland", "cs_CZ":"Irsko"},
			"34626": {"sk_SK":"Island","en_EN":"Iceland", "cs_CZ":"Island"},
			"31911": {"sk_SK":"Taliansko","en_EN":"Italy", "cs_CZ":"Itálie"},
			"86962": {"sk_SK":"Izrael","en_EN":"Israel", "cs_CZ":"Izrael"},
			"93832": {"sk_SK":"Jamajka","en_EN":"Jamaica", "cs_CZ":"Jamajka"},
			"33214": {"sk_SK":"Japonsko","en_EN":"Japan", "cs_CZ":"Japonsko"},
			"31222": {"sk_SK":"Juhoafrická republika","en_EN":"South African Republic", "cs_CZ":"Juhoafrická republika"},
			"32794": {"sk_SK":"Južná Korea","en_EN":"South Korea", "cs_CZ":"Jížní Korea"},
			"52385": {"sk_SK":"Jordánsko","en_EN":"Jordan", "cs_CZ":"Jordánsko"},
			"38179": {"sk_SK":"Juhoslávia","en_EN":"Jugoslavia", "cs_CZ":"Jugoslávie"},
			"88248": {"sk_SK":"Kambodža","en_EN":"Cambodia", "cs_CZ":"Kambodža"},
			"31127": {"sk_SK":"Kanada","en_EN":"Canada", "cs_CZ":"Kanada"},
			"87392": {"sk_SK":"Katar","en_EN":"Catarrh", "cs_CZ":"Katar"},
			"95010": {"sk_SK":"Kazachstan","en_EN":"Kazakhstan", "cs_CZ":"Kazachstán"},
			"36470": {"sk_SK":"Keňa","en_EN":"Kenya", "cs_CZ":"Keňa"},
			"35397": {"sk_SK":"Kolumbia","en_EN":"Colombia", "cs_CZ":"Kolumbie"},
			"94782": {"sk_SK":"Lichtenštajnsko","en_EN":"Lichtenstein", "cs_CZ":"Lichtenštejnsko"},
			"39282": {"sk_SK":"Litva","en_EN":"Lithuania", "cs_CZ":"Litva"},
			"94247": {"sk_SK":"Lotyšsko","en_EN":"Latvia", "cs_CZ":"Lotyšsko"},
			"35917": {"sk_SK":"Luxembursko","en_EN":"Luxembourg", "cs_CZ":"Luxembursko"},
			"33446": {"sk_SK":"Maďarsko","en_EN":"Hungary", "cs_CZ":"Maďarsko"},
			"41583": {"sk_SK":"Malajzia","en_EN":"Malaysia", "cs_CZ":"Malajzie"},
			"53919": {"sk_SK":"Malta","en_EN":"Malta", "cs_CZ":"Malta"},
			"51642": {"sk_SK":"Maroko","en_EN":"Morocco", "cs_CZ":"Maroko"},
			"31335": {"sk_SK":"Mexiko","en_EN":"Mexico", "cs_CZ":"Mexiko"},
			"96308": {"sk_SK":"Monako","en_EN":"Monaco", "cs_CZ":"Monako"},
			"95011": {"sk_SK":"Mongolsko","en_EN":"Mongolia", "cs_CZ":"Mongolsko"},
			"52119": {"sk_SK":"Namibia","en_EN":"Namibia", "cs_CZ":"Namibia"},
			"31168": {"sk_SK":"Nemecko","en_EN":"Germany", "cs_CZ":"Německo"},
			"85001": {"sk_SK":"Nepál","en_EN":"Nepal", "cs_CZ":"Nepál"},
			"90146": {"sk_SK":"Nigéria","en_EN":"Nigeria", "cs_CZ":"Nigérie"},
			"33832": {"sk_SK":"Holandsko","en_EN":"Netherlands", "cs_CZ":"Holandsko"},
			"36661": {"sk_SK":"Nórsko","en_EN":"Norway", "cs_CZ":"Norsko"},
			"38548": {"sk_SK":"Nový Zéland","en_EN":"New Zealand", "cs_CZ":"Nový Zéland"},
			"94596": {"sk_SK":"Palestína","en_EN":"Palestine", "cs_CZ":"Palestina"},
			"84751": {"sk_SK":"Panama","en_EN":"Panama", "cs_CZ":"Panama"},
			"49883": {"sk_SK":"Papua-Nová Guinea","en_EN":"Papua New Guinea", "cs_CZ":"Papua-Nová Guinea"},
			"94714": {"sk_SK":"Paraguay","en_EN":"Paraguay", "cs_CZ":"Paraguay"},
			"32807": {"sk_SK":"Peru","en_EN":"Peru", "cs_CZ":"Peru"},
			"40183": {"sk_SK":"Poľsko","en_EN":"Poland", "cs_CZ":"Polsko"},
			"55947": {"sk_SK":"Portoriko","en_EN":"Puerto Rico", "cs_CZ":"Portoriko"},
			"49113": {"sk_SK":"Portugalsko","en_EN":"Portugal", "cs_CZ":"Portugalsko"},
			"32943": {"sk_SK":"Rakúsko","en_EN":"Austria", "cs_CZ":"Rakousko"},
			"31061": {"sk_SK":"Grécko","en_EN":"Greece", "cs_CZ":"Řecko"},
			"31151": {"sk_SK":"Rumunsko","en_EN":"Romania", "cs_CZ":"Rumunsko"},
			"31062": {"sk_SK":"Rusko","en_EN":"Russia", "cs_CZ":"Rusko"},
			"52386": {"sk_SK":"Saúdská Arábia","en_EN":"Saudi Arabia", "cs_CZ":"Saúdská Arábie<"},
			"33615": {"sk_SK":"Singapúr","en_EN":"Singapore", "cs_CZ":"Singapur"},
			"33623": {"sk_SK":"Slovensko","en_EN":"Slovakia", "cs_CZ":"Slovensko"},
			"46035": {"sk_SK":"Slovinsko","en_EN":"Slovenia", "cs_CZ":"Slovinsko"},
			"35539": {"sk_SK":"Sovietsky zväz","en_EN":"The Soviet Union", "cs_CZ":"Sovětský svaz"},
			"31334": {"sk_SK":"Španielsko","en_EN":"Spain", "cs_CZ":"Španělsko"},
			"40672": {"sk_SK":"Spojené arabské emiráty","en_EN":"United Arab Emirates", "cs_CZ":"Spojené arabské emiráty"},
			"85931": {"sk_SK":"Srbsko","en_EN":"Serbia", "cs_CZ":"Srbsko"},
			"94198": {"sk_SK":"Srbsko a Čierna Hora","en_EN":"Serbia and Montenegro", "cs_CZ":"Srbsko a Černá Hora"},
			"34708": {"sk_SK":"Švédsko","en_EN":"Sweden", "cs_CZ":"Švédsko"},
			"31152": {"sk_SK":"Švajčiarsko","en_EN":"Switzerland", "cs_CZ":"Švícarsko"},
			"54045": {"sk_SK":"Tanzánia","en_EN":"Tanzania", "cs_CZ":"Tanzánie"},
			"49447": {"sk_SK":"Thajsko","en_EN":"Thailand", "cs_CZ":"Thajsko"},
			"49640": {"sk_SK":"Tchaj-wan","en_EN":"Taiwan", "cs_CZ":"Tchaj-wan"},
			"87393": {"sk_SK":"Tunisko","en_EN":"Tunisia", "cs_CZ":"Tunisko"},
			"34948": {"sk_SK":"Turecko","en_EN":"Turkey", "cs_CZ":"Turecko"},
			"35100": {"sk_SK":"Ukrajina","en_EN":"Ukraine", "cs_CZ":"Ukrajina"},
			"87884": {"sk_SK":"Uruguay","en_EN":"Uruguay", "cs_CZ":"Uruguay"},
			"31035": {"sk_SK":"USA","en_EN":"USA", "cs_CZ":"USA"},
			"31150": {"sk_SK":"Veľká Británia","en_EN":"Great Britain", "cs_CZ":"Velká Británie"},
			"49263": {"sk_SK":"Venezuela","en_EN":"Venezuela", "cs_CZ":"Venezuela"},
			"84582": {"sk_SK":"Vietnam","en_EN":"Vietnam", "cs_CZ":"Vietnam"},
			"49591": {"sk_SK":"Východné Nemecko","en_EN":"East Germany", "cs_CZ":"Východní Německo"},
			"32966": {"sk_SK":"Západné Nemecko","en_EN":"West Germany", "cs_CZ":"Západní Německo"}
			}
	def capabilities(self):
		return ['resolve', 'categories', 'search', 'stats', 'trakt']

	def getBaseUrl(self):
		if self.useHttps:
			return 'https://stream-cinema.online/kodi'
		return 'http://stream-cinema.online/kodi'

	def showMsg(self, msgId, showSec, canClose=True, isError=True):
		try:
			# must be like this because show message on DM failed when not show up from main thread
			msgType = "error"
			if not isError:
				msgType = "info"
			client.add_operation("SHOW_MSG", {
												'msg': self._getName(msgId),
												'msgType': msgType,
												'msgTimeout': showSec,
												'canClose': canClose
											 })
		except:
			sclog.logError("showMsg failed (minimalna verzia archivCZSK 1.1.2).\n%s"%traceback.format_exc())
			from Plugins.Extensions.archivCZSK.gui.common import showErrorMessage
			showErrorMessage(self.session, self._getName(msgId), showSec)

	def on_init(self):
		kodilang = self.lang or 'cs'
		if kodilang == ISO_639_1_CZECH or kodilang == 'sk':
			self.ISO_639_1_CZECH = ISO_639_1_CZECH
		else:
			self.ISO_639_1_CZECH = 'en'

	def merge_dicts(self, *dict_args):
		result = {}
		for dictionary in dict_args:
			result.update(dictionary)
		return result

	# must be in Singleton or Static class/method because cachce store per instance but in plugin class create in each request
	@lru_cache(maxsize = 500, timeout = 30*60) #30min
	def cache_request_30(self, url):
		sclog.logDebug("NOT CACHED REQUEST")
		return util.request(url)
	@lru_cache(maxsize = 500, timeout = 60*60) #1h
	def cache_request_1(self, url):
		sclog.logDebug("NOT CACHED REQUEST")
		return util.request(url)
	@lru_cache(maxsize = 500, timeout = 180*60) #3h
	def cache_request_3(self, url):
		sclog.logDebug("NOT CACHED REQUEST")
		return util.request(url)
	@lru_cache(maxsize = 250, timeout = 360*60) #6h
	def cache_request_6(self, url):
		sclog.logDebug("NOT CACHED REQUEST")
		return util.request(url)
	@lru_cache(maxsize = 100, timeout = 12*60*60) #12h
	def cache_request_12(self, url):
		sclog.logDebug("NOT CACHED REQUEST")
		return util.request(url)

	def get_data_cached(self, url, useCache, timeout):
		if useCache:
			if timeout==1:
				return self.cache_request_1(url);
			if timeout==3:
				return self.cache_request_3(url);
			if timeout==6:
				return self.cache_request_6(url);
			if timeout==12:
				return self.cache_request_12(url);

			return self.cache_request_30(url);
		else:
			return util.request(url)

	def _json(self, url, useCache=False, cacheTimeout=30):
		try:
			qs = '?'
			if '?' in url:
				qs='&'
			sclog.logDebug("json url: %s" % url)
#			urlapi = url+qs+'ver='+API_VERSION+'&uid='+self.deviceUid
			urlapi = url+qs+'&uid='+self.deviceUid
			sclog.logDebug("json url: %s" % urlapi)
			jsonData = self.get_data_cached(urlapi, useCache, cacheTimeout)
			data = json.loads(jsonData)
#			sclog.logDebug("_json '%s' data:\n%s"%(urlapi, jsonData))
			return data
		except HTTPError as err:
			#sclog.logError("HTTP error (%s), url=%s.\n%s" % (err.code, url, traceback.format_exc()))
			raise err
		except:
			sclog.logError("Chyba pripojenia.\n%s"%traceback.format_exc())

	def _getName(self, id):
		try:
			id = id.replace("[B]","")
			id = id.replace("[/B]","")
			
			if self.language!="sk_SK" and self.language!="en_EN" and self.language!="cs_CZ":
				self.language="en_EN"
			if id.startswith('$'):
				id = id[1:]
				spl = id.split(' ')
				if len(spl) == 1:
					val = self.trans[id][self.language]
					if val=="xxx" or val=="yyy":
						return id+"(no translation)"
					return val
				else: 
					# hacky dubbing label
					if spl[1]=='dub': 
						return self.trans[id][self.language]
					# day of week tranlation, series etc...
					val = self.trans[spl[0]][self.language]
					if val=="xxx" or val=="yyy":
						return	id+"(no translation)"
					return id.replace(spl[0], val)
			return id
		except Exception:
			#sclog.logError(traceback.format_exc())
			pass
		return id

	def _getCacheTimeByUrl(self, url):
		try:
			urlStr = "%s"%url
			if (urlStr.endswith("/Movies") or urlStr.endswith("/Series") or
				urlStr.endswith("/Movies/country") or urlStr.endswith("/Movies/quality") or
				urlStr.endswith("/Movies/genre") or urlStr.endswith("/Movies/year") or
				urlStr.endswith("/Series/country") or urlStr.endswith("/Series/genre") or
				urlStr.endswith("/Anime")):
				return 12;

			if (urlStr.endswith("/Movies/collection") or urlStr.endswith("/Tv") or 
				"/Tv/archiv" in url or "/Search/getList" in url):
				return 6;
		except:
			sclog.logError("Get cache time by url failed (return 1).\n%s"%traceback.format_exc())
			pass
		return 1
	
	def categories(self):
		result = []
		try:
			data = self._json(self.getBaseUrl(), True, 12)
			if isinstance(data, dict) and data["menu"]:
				for m in data["menu"]:
					try:
						# skip not valid items
						if not 'url' in m:
							continue
						if m['type'] == 'dir' and m['url'].startswith('/'):
							# filter new search menu (not supported yet)
							if m['url'] != '/Search/menu':
								tmpTrans = self._getName(str(m['title']))
								item = self.dir_item(title=tmpTrans, url=self.getBaseUrl()+str(m['url']))
								result.append(item)
					except Exception:
						sclog.logError("get category failed (%s, title=%s).\n%s"%(m['url'],m['title'],traceback.format_exc()))
				# add trakt.tv
				if len(result) > 0 and self.trakt_enabled:
					result.append(self.dir_item(title='Trakt.tv', url=self.tapi.API_LIST))
			else:
				raise Exception("Get main menu category failed.")
		except HTTPError as err:
			if err.code == 500:
				self.showMsg("$66672", 20)
			else:
				self.showMsg("$66673", 30)
			sclog.logError("Get categories failed.\n%s"%traceback.format_exc())
		except:
			self.showMsg("$66673", 20)
			sclog.logError("Get categories failed.\n%s"%traceback.format_exc())

		return result

	def search(self, keyword):
		sq = {'search': keyword}
		return self._renderItem(self.getBaseUrl()+ '/Search?' + urlencode(sq))
	def list(self, url):
		return self._renderItem(url)

	def _renderItem(self, url):
		#startRender = datetime.datetime.now()
		# sort 1-desc order by releasedate (year)
		# sort 2- desc order by rating (not yet implemented)
		# not implemented on Series yet
		if 'Movies/genre/' in url or 'Series/genre/' in url:
			# dont add etc. NextPage item (...?p=2), and other
			if not ('?' in url) and self.itemOrderGenre == '1': 
				url = url+'/1'
		if 'Movies/country/' in url or 'Series/country/' in url:
			# dont add etc. NextPage item (...?p=2), and other
			if not ('?' in url) and self.itemOrderCountry == '1': 
				url = url+'/1'
		if 'Movies/guality/' in url or 'Series/quality/' in url:
			# dont add etc. NextPage item (...?p=2), and other
			if not ('?' in url) and self.itemOrderQuality == '1': 
				url = url+'/1'
		
		result = []

		if 'ksearch' in url: #MN
			searchValue = client.getTextInput(self.session, "", url[9:])
			if searchValue is not "":
				url = '/wsearch/'+searchValue
	
		if 'wsearch' in url: #MN
			if self.ws is None:
				from webshare import Webshare as wx
				self.ws = wx(self.wsuser, self.wspass, self.useHttps)
			result.append(self.dir_item('Upravit hledani','/ksearch/'+url[9:]))
			items = self.ws.search(url[9:])
			for item in items:
				itemV = self.video_item(url=item['url'], img=item['img'], quality='')
				itemV['title'] = "["+item['size']+"] "+item['title']
				result.append(itemV)
			return result

		try:
			# reload trakt user watched data
			if StaticTraktWatched().loadUserWatchedError:
				StaticTraktWatched().reload = True
			### TRAKT.TV
			if self.tapi.API_LIST == url: # trakt lists
				if not self.tapi.valid():
					#devCode, verUrl, userCode, interval
					self.code, verUrl, userCode, interval = self.tapi.get_device_code()
					msg = self._getName("$66674")%(verUrl, userCode)
					succ = self._getName("$66675")
					fail = self._getName("$66676")
					sclog.logInfo(msg)
					# execute this operation after load content in main thread
					# supported cmd: TRAKT_PAIR
					client.add_operation("TRAKT_PAIR", {'trakt':	{'url':self.tapi.API_AUTH+'/token', 
																		'code':self.code, 
																		'client_id':self.tapi.CLIENT_ID, 
																		'client_secret': self.tapi.CLIENT_SECRET},
														'msg':		{'pair': msg, 'success':succ, 'fail':fail}, 
														'settings': {'token': 'trakt_token',
																	 'refreshToken':'trakt_refresh_token', 
																	 'expire':'trakt_token_expire'}})
					
					return []
				res = []
				for tl in self.tapi.get_lists():
					spl = tl.split("##")
					res.append(self.dir_item(title=spl[0], url=spl[1]))
				return res

			data = None
			if self.tapi.API_LIST+'/' in url or self.tapi.API_WATCH_LIST == url: # concrete list items
				ids = ''
				traktItems = []
				if self.tapi.API_WATCH_LIST == url:
					traktItems = self.tapi.get_watch_list_items()
				else: # custom user list
					slug = url.replace(self.tapi.API_LIST+'/','').replace('/items','')
					traktItems = self.tapi.get_list_items(slug)
				idsArr = []
				for m in traktItems:
					idsArr.append('%s'%m['imdb'])
				seurl = "%s/Search?lang=eng&ver=%s&uid=%s&l=SK"%(self.getBaseUrl(), API_VERSION, self.deviceUid)
				if len(idsArr) > 0:
					data = json.loads(util.post(seurl, data={'ids': json.dumps(idsArr)}))
					tmpMenu = data['menu']
					tmpMenu.sort(key=lambda x: x['title'], reverse=False)
					data['menu'] = tmpMenu
				#sclog.logDebug('Search returns=>\n%s'%data)
				# synch not found
				for m in traktItems:
					#sclog.logDebug('trakt item=%s'%m)
					if 'menu' in data and data['menu']:
						found = False
						adinfo = ''
						for x in data['menu']:
							try:
								if 'imdb' in x and int(x['imdb']) == int(m['imdb'].replace('tt','')):
									found = True
									break
							except:
								sclog.DEBUG('Trakt imdb missmatch TRAKT:"%s"  SC:"%s"'%(m['imdb'], x['imdb']))
								adinfo='(missing imdb) '
						if not found:
							item = self.video_item(url='', img='', quality='')
							item['title']= '%s %s***NOT FOUND***'%(m['title'], adinfo)
							result.append(item)
					else:
						item = self.video_item(url='', img='', quality='')
						item['title']= '%s ***NOT FOUND***'%m['title']
						result.append(item)
				result.sort(key=lambda x: x['title'], reverse=False);
				# empty search
				try:
					if data is not None and 'menu' in data:
						kk = '%s'%data['menu'][0]['title']
						if kk=='none' or data['menu'][0]['url']=='/':
							data['menu'][0]['url'] = ''
				except:
					sclog.logError('Clear empty trakt.tv search failed.\n%s'%traceback.format_exc())
					pass
			else:
				data = self._json(url, True, self._getCacheTimeByUrl(url))

			
			if data is not None and 'menu' in data and data['menu']:
				itype = -1
				for m in data['menu']:
					# skip not valid items
					if not 'url' in m or m['url']=='':
						continue

					itemUrl = self.getBaseUrl()+str(m['url'])
					try:
						# filter lang
						if 'lang' in m and self.langFilter!= '0':
							# 0 all, 1-CZ&SK, 2-CZ 3-SK, 4-EN
							lng = m['lang'].lower()
							if self.langFilter == '1':
								if not lng.startswith("cz") and not lng.startswith("sk"):
									continue
							elif self.langFilter == '2':
								if not lng.startswith("cz"):
									continue
							elif  self.langFilter == '3':
								if not lng.startswith("sk"):
									continue
							elif  self.langFilter == '4':
								if not lng.startswith("en"):
									continue

						if m['type'] == 'dir' and m['url'].startswith('/'):
							item = self.dir_item(title=self._getName(m['title']), url=itemUrl)
						elif m['type'] == 'dir' and ("/genre" in url or "/year" in url or "/country" in url or "/quality" in url or "Tv/archiv" in url):
							item = self.dir_item(title=self._getName(m['title']), url=url+'/'+m['url'])
						elif m['type'] == 'dir' and not m['url'].startswith('/'):
							continue

						if	m['type'] == 'dir' and ('/series' in url.lower() or self.tapi.API in url.lower()): # set aditional info for series
							try:
								item['img'] = str(m['art']['poster'])
							except:
								pass;
							self.setAditionalVideoItemInfo(m, item)
						
						if m['type'] == 'video':
							image = ""
							try:
								image = str(m['art']['poster'])
							except:
								pass;

							if 'episode' in m and 'season' in m and 'tvshowtitle' in m: #MN
								item = self.dir_item(m['title'], "/wsearch/"+m['tvshowtitle'].replace(' ','-')+'-S'+str(m['season']).zfill(2)+'E'+str(m['episode']).zfill(2)+'-'+m['year'])
							else:
								item = self.dir_item(m['title'], "/wsearch/"+m['sorttitle']+'-'+m['year'])

							try:
								item['img'] = str(m['art']['poster'])
							except:
								pass;
							self.setAditionalVideoItemInfo(m, item)

#							 # check subs
#							 try:
#								 isVipAccount = int(StaticDataSC().vipDaysLeft) > 0
#								 lngtmp = ''
#								 if 'lang' in m:
#									 lngtmp = m['lang'].lower()
#								 if isVipAccount and 'subs' in m and not lngtmp.startswith("cz") and not lngtmp.startswith("sk"):
#									 if 'webshare.cz' in m['subs'] and '/file/' in m['subs']:
#										 m['title'] = m['title'] + " (%s)"%self._getName("$66670")
#							 except:
#								 sclog.logError("Check substitle failed.\n%s"%traceback.format_exc())
#								 pass
#
#							 item = self.video_item(url=itemUrl, img=image, quality='')
#
#							 item['title']= m['title']
#							 if '/Tv' in url:
#								 item['title'] = m['title'].replace('[LIGHT]','').replace('[/LIGHT]','')
#							 # set data for item
#							 self.setAditionalVideoItemInfo(m, item)
						
						# use for trakt
						if 'imdb' in m or 'trakt' in m or 'tvdb' in m:
							item['customDataItem'] = m
						# mark trakt items
						# trakt_filter=> 0-mark, 1-hide, 2-nothing
						if self.trakt_enabled and self.trakt_filter!='2' and 'id' in m and self.tapi.valid():
							if itype==-1:
								itype=StaticTraktWatched().getItemType(m)
							if StaticTraktWatched().isWatched(m, itype):
								if self.trakt_filter=='0':
									item['title']= "%s *"%item['title']
								elif self.trakt_filter=='1':
									continue
						self._filter(result, item)
					except TraktRefreshException as err:
						raise err
					except:
						sclog.logError("item render failed %s.\n%s"%(itemUrl, traceback.format_exc()))
						pass
			else:
				result.append(self.dir_item(title='none', url='failed_url'))
		except TraktRefreshException as err:
			# reset and save setting
			try:
				self.tapi.TOKEN = ''
				from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
				addon = ArchivCZSK.get_xbmc_addon('plugin.video.stream-cinema')
				addon.setSetting('trakt_token', '')
				addon.setSetting('trakt_token_expire', '')
				addon.setSetting('trakt_refresh_token', '')
			except:
				pass
			sclog.logError('Refresh trakt access token failed.\n%s'%traceback.format_exc())
			self.showMsg("$66681", 30, isError=True)
			result.append(self.dir_item(title='Render item failed...', url='failed_url'))
		except:
			sclog.logError("Render item failed.\n%s"%traceback.format_exc())
			result.append(self.dir_item(title='Render item failed (CONNECTION ERROR)...', url='failed_url'))

		#sclog.logDebug("Render item takes: %s s"%(datetime.datetime.now()-startRender).total_seconds())
		return result

	def setAditionalVideoItemInfo(selft, scItem, videoItem):
		try:
			# need also 'id' send to XBMC 
			# supprot ['plot', 'year', 'genre', 'rating', 'director', 'votes', 'cast', 'trailer'] ... feature 'duration'
			#if scItem['type'] == 'video':
			try:
				if 'postersmall' in scItem:
					videoItem['img']= scItem['postersmall']
				else:
					videoItem['img']= scItem['art']['postersmall']
			except:
				pass
			if 'year' in scItem:
				videoItem['year'] = scItem['year']
			if 'rating' in scItem:
				try:
					videoItem['rating'] = scItem['rating'] #float(scItem['rating'])*10
				except:
					pass
			if 'id' in scItem:
				videoItem['videoid'] = scItem['id']
			if 'mvideo' in scItem:
				videoItem['videowidth'] = scItem['mvideo']['width']

			if 'duration' in scItem:
				try:
					videoItem['duration'] = scItem['duration']
				except:
					pass
			if 'plot' in scItem:
				try:
					videoItem['plot'] = util.decode_html(scItem['plot'])
				except:
					pass
			if 'genre' in scItem:
				try:
					videoItem['genre'] = util.decode_html(scItem['genre'])
				except:
					pass
		except:
			sclog.logError("getAditionalVideoItemInfo failed.\n%s" % traceback.format_exc())
			pass
		

	def resolve(self, item, captcha_cb=None, select_cb=None):
		# shows list of streams
		try:
			# hack huste.tv
			if 'joj.sk/huste' in item['url']:
				sclog.logDebug("item url=%s"%item['url'])
				item['url'] = item['url'].replace(self.getBaseUrl(),'')
				huste = []
				huste.append(item)
				return huste;

			data = self._json(item['url'], True, 1)
			#sclog.logDebug("resolve data %s\n%s"%(item['url'],data))

			if 'info' in data and self.getBaseUrl() in item['url']:
				statsData = data['info']
				if 'strms' in data:
					out = [self.merge_dicts(data['info'], i) for i in data['strms']]
					data = out

				if len(data) < 1:
					raise ResolveException('Video is not available.')

				if self.ws is None:
					#sclog.logDebug("Resolve ws is null (reinit)...");
					from webshare import Webshare as wx
					self.ws = wx(self.wsuser, self.wspass, self.useHttps, saveVipDays=True) # save vip days if startup sigleton failed or user change login/password

				# check login
				if not self.ws.loginOk:
					#self.showMsg("$66666", 10)
					sclog.logInfo("Ws account login not ok.")
				
				isVipAccount = False
				try:
					isVipAccount = int(StaticDataSC().vipDaysLeft) > 0
				except:
					sclog.logError("get static vip status failed.\n%s"%s)

				res = []
				try:
					
					# filter stream size if > 0, size=2.51 GB
					filterSizeEnabled = self.streamSizeFilter != '0' and len(data) > 1
					filterApplied = False
					sizeLimit = 0
					if self.streamSizeFilter=='1':
						sizeLimit = 1
					if self.streamSizeFilter=='2':
						sizeLimit = 1.5
					if self.streamSizeFilter=='3':
						sizeLimit = 2
					if self.streamSizeFilter=='4':
						sizeLimit = 2.5
					if self.streamSizeFilter=='5':
						sizeLimit = 3
					if self.streamSizeFilter=='6':
						sizeLimit = 3.5
					if self.streamSizeFilter=='7':
						sizeLimit = 4


					#sclog.logDebug("_resolve start...")
					for m in data:
						try:
							# filter HEVC HDR (4K), 3D-SBS
							filterStreamType = False
							if self.streamHevc3dFilter:
								if 'quality' in m and '3D' in m['quality']:
									sclog.logDebug("Filtering 3D stream...")
									filterStreamType = True
								elif 'vinfo' in m and ('HEVC' in m['vinfo'] or 'HDR' in m['vinfo']):
									sclog.logDebug("Filtering HEVC,HDR stream...")
									filterStreamType = True

							sizeValid = True
							if filterSizeEnabled:
								try:
									sizeStr = "%s"%m['size']
									size = float(sizeStr.split(' ')[0])
									units = sizeStr.split(' ')[1]
									if units.lower()=='mb':
										size = size / 1024
									sclog.logDebug("Filter stream size compare %sGB > %sGB ..."%(size, sizeLimit))
									if size > sizeLimit:
										filterApplied = True
										sizeValid = False
								except:
									sclog.logError("Check valid stream size failed.\n%s"%traceback.format_exc())
									pass

							if sizeValid and not filterStreamType:
								if isVipAccount and 'subs' in m and not m['subs'] is None and 'webshare.cz' in m['subs']:
									try:
										sclog.logDebug("subs url=%s"%m['subs'])
										tmp2 = m['subs']
										if '/file/' in tmp2:
											idx = tmp2.index('/file/')
											tmp2 = tmp2[idx+len('/file/'):]
											tmp2 = tmp2.split('/')[0]
											if self.ws is None:
												#sclog.logDebug("_resolve ws is null...");
												from webshare import Webshare as wx
												self.ws = wx(self.wsuser, self.wspass, self.useHttps)
											m['subs'] = self.ws.resolve(tmp2, self.deviceUid)
											m['subExist'] = True
											#sclog.logDebug("resolved subs url=%s"%itm['subs'])
										#else:
										#	 sclog.logDebug("Substitles not supported...\n%s"%tmp)
									except:
										sclog.logError("Resolve substitles failed.\n%s"%traceback.format_exc())
										pass
								tmp = m

								#custom title
								series = ""
								if 'tvshowtitle' in m:
									tmp['customTitle'] = m['title']
								#custom file name
								if 'fname' in m:
									tmp['customFname'] = m['fname']
								
								#custom data item usings for stats
								tmp['customDataItem'] = m

								# better info for render
								vinfo = ''
								if 'vinfo' in tmp:
									vinfo = tmp['vinfo']
								size = ""
								if 'size' in tmp:
									size = "[%s]"%tmp['size']
								ainfo = ""
								if 'ainfo' in tmp:
									tstr = "%s"%tmp['ainfo']
									ainfo = tstr.replace(", ","").replace("][",", ")
								subExist = ""
								if 'subExist' in tmp:
									subExist = " %s"%self._getName("$66670") #" +tit"
								tmp['resolveTitle'] = "[%s%s]%s[%s%s]%s"%(tmp['quality'], vinfo, size, tmp['lang'],subExist,ainfo)

								self._filter(res, tmp)
						except:
							sclog.logError("_resolve load specific stream failed (continue...)%s"%traceback.format_exc())
							pass

					#sclog.logDebug("_resolve end...")
					if filterApplied and len(res) == 0:
						self.showMsg("$66671", 15, isError=False)

					if len(res) == 1:
						return self._resolve(res[0])
					elif len(res) > 1 and select_cb:
						return self._resolve(select_cb(res))
				except:
					sclog.logError("_resolve failed.\n%s"%traceback.format_exc())
					# soemthing happend with resolve webshare
					pass
			else:
				sclog.logError('resolve item failed (invalid data)!')

		except HTTPError as err:
			sclog.logError("HTTP error (%s) resolve failed %s.\n%s" % (err.code, item['url'], traceback.format_exc()))
			if err.code == 429:
				self.showMsg("$66667", 60, False)
			else:
				self.showMsg("$66673",30)
		except:
			sclog.logError("resolve failed %s.\n%s" % (item['url'], traceback.format_exc()))
			# service failed
			self.showMsg("$66673",20)

		return []
	def _resolve(self, itm):
		if itm is None:
			return None;
		sclog.logDebug("_resolve itm: %s %s"%(itm, itm['provider']))
		if itm['provider'] == 'plugin.video.online-files' or itm['provider'] == 'webshare':
			if self.ws is None:
				sclog.logDebug("_resolve ws is null...");
				from webshare import Webshare as wx
				self.ws = wx(self.wsuser, self.wspass, self.useHttps)
					
			try:
				data = self._json(self.getBaseUrl() + itm['url'], True, 1)
				if data and 'ident' in data:
					itm['url'] = self.ws.resolve(data['ident'], self.deviceUid)
				else:
					raise Exception("Resolve URL failed (IDT).")
			except:
				# reset ws reason: singleton
				# sclog.logError("ws _resolve failed...\n%s"%traceback.format_exc());
				self.ws = None
				raise
					
			if not itm['url']:
				raise Exception("Resolve url is empty")

			return itm
		raise Exception("Not supported item to resolve!")
		
	def stats(self, item, action):
		try:
			# action:
			#	- play
			#	- watching /every 10minutes/
			#	- end
			scAction=''
			if action.lower()=='play':
				scAction = 'start'
			if action.lower()=='watching':
				scAction = 'ping'
			if action.lower()=='end':
				scAction = 'end'
			
			sclog.logDebug("Stats hit action='%s' scAction='%s' ..."%(action, scAction))

			udata = self.ws.sendStats(item, scAction, self.getBaseUrl(), API_VERSION, self.deviceUid)
		except:
			sclog.logError("Send stats failed.\n%s"%traceback.format_exc())
			pass

	def trakt(self, item, action):
		# addon must have setting (bool) trakt_enabled ... and must be enabled to show trakt menu 
		# and must set 'customDataItem' with imdb, tvdb, trakt property (identify video item in trakt.tv)
		# addon must add capability 'trakt'

		try:
			# action:
			#	- add		add item to watchlist
			#	- remove	remove item from watchlist
			#	- watched	add to watched collection
			#	- unwatched remove from watched collection

			if self.trakt_enabled:
				if self.tapi.valid():
					sclog.logDebug("Trakt hit action=%s ..."%action)
					# do something
					act = action.lower()
					if act=='add':
						self.tapi.add_to_watchlist(item)
					if act=='remove':
						self.tapi.remove_from_watchlist(item)
					if act=='watched':
						self.tapi.mark_as_watched(item)
						StaticTraktWatched().reload = True
					if act=='unwatched':
						self.tapi.mark_as_not_watched(item)
						StaticTraktWatched().reload = True

					# add result message to show only for trakt
					client.add_operation_result(self._getName("$66677"), False)
				else:
					sclog.logInfo("Trakt is not pair with this device.")
					client.add_operation_result(self._getName("$66680"), True)
			else:
				sclog.logInfo("Trakt is not enabled in setting.")
				client.add_operation_result(self._getName("$66679"), True)
		except:
			sclog.logError("Trakt action (%s) failed.\n%s"%(action, traceback.format_exc()))
			client.add_operation_result(self._getName("$66678"), True)
