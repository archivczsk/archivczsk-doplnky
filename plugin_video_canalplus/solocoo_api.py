# -*- coding: utf-8 -*-
#
# Solocoo (m7cp) klient - prihlasenie kodom a program (EPG) s historiou.
# Prehravanie (zive aj archiv) riesi nativny Canal+ backend (canalplus_api.py), kde box
# dostane HD cez PlayReady. Solocoo session vracia aj Canal+ passToken, ktory sa na to pouzije.
#
#   parovanie:  POST m7cplogin.solocoo.tv/cpreversepairingrequest {deviceInfo}      -> kod + url
#               POST m7cplogin.solocoo.tv/cpreversepairingcheck   {deviceInfo,code} -> ssoToken
#   session:    POST tvapi-hlm2.solocoo.tv/v1/provision {deviceInfo}                -> provisionData
#               POST tvapi-hlm2.solocoo.tv/v1/session   {deviceInfo,ssoToken,prov}  -> token, passToken
#   program:    GET  tvapi-hlm2.solocoo.tv/v1/schedule?channels=..&from=..&until=..
#
# Parovanie kodom Canal+ podporuje pre TV aplikaciu, preto sa klient hlasi ako webOS TV.

import calendar
import json
import os
import threading
import uuid
from time import time, strftime, strptime, gmtime

TVAPI_URL = 'https://tvapi-hlm2.solocoo.tv'
PAIR_REQUEST_URL = 'https://m7cplogin.solocoo.tv/cpreversepairingrequest'
PAIR_CHECK_URL = 'https://m7cplogin.solocoo.tv/cpreversepairingcheck'

APP_VERSION = '142199'
FEATURE_LEVEL = 8
EPG_ALIGN = 900                 # server berie časy zarovnané na štvrťhodiny
SCHEDULE_WINDOW = 24 * 3600     # najväčší rozsah jedného dotazu
CHANNELS_PER_REQUEST = 20
TOKEN_MARGIN = 120
TIMEOUT = 20
DESC_CACHE_MAX = 5000

USER_AGENT = ('Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/79.0.3945.79 Safari/537.36')

# zóna a jazyk; m7cp je spoločný tenant pre SK aj CZ
BRANDS = {
	'cpsvk': {'country': 'SK', 'language': 'sk_SK', 'appStore': 'WebOS / LG (SK)'},
	'cpscz': {'country': 'CZ', 'language': 'cs_CZ', 'appStore': 'WebOS / LG (CZ)'},
}


def _to_ts(value):
	if not value:
		return 0
	if isinstance(value, (int, float)):
		v = int(value)
		return v // 1000 if v > 3000000000 else v
	text = str(value).replace('Z', '').split('.')[0].replace('T', ' ')
	for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
		try:
			return calendar.timegm(strptime(text, fmt))
		except Exception:
			continue
	return 0


def _iso(ts):
	return strftime('%Y-%m-%dT%H:%M:%S.000Z', gmtime(int(ts)))


class SolocooAuthError(Exception):
	"""Zariadenie nie je sparovane alebo server prihlasenie zamietol."""
	pass


class SolocooEpg(object):
	"""Solocoo prihlasenie a program. ssoToken a deviceSerial sa ukladaju do data_dir."""

	def __init__(self, api):
		self.api = api                 # CanalplusApi - req_session, data_dir, brand
		self.cp = api.cp
		self._lock = threading.RLock()
		self.serial = None
		self.sso_token = None
		self.token = None              # Bearer pre tvapi
		self.pass_token = None         # Canal+ passToken na nativne prehravanie
		self.token_valid_until = 0
		self._pair_interval = 5
		self._desc_cache = {}          # asset_id -> popis relacie
		self._desc_lock = threading.Lock()
		self._load_state()

	# ---- stav na disku --------------------------------------------------------------------------

	def _state_path(self):
		data_dir = getattr(self.api, 'data_dir', None)
		if not data_dir:
			return None
		return os.path.join(data_dir, 'solocoo.json')

	def _load_state(self):
		path = self._state_path()
		if path and os.path.isfile(path):
			try:
				with open(path, 'r') as f:
					st = json.load(f) or {}
				self.serial = st.get('serial') or None
				self.sso_token = st.get('ssoToken') or None
			except Exception:
				pass
		if not self.serial:
			self.serial = 'webos.m7cp.' + str(uuid.uuid4())
			self._save_state()

	def _save_state(self):
		path = self._state_path()
		if not path:
			return
		try:
			folder = os.path.dirname(path)
			if folder and not os.path.isdir(folder):
				os.makedirs(folder)
			tmp = path + '.tmp'
			with open(tmp, 'w') as f:
				json.dump({'serial': self.serial, 'ssoToken': self.sso_token}, f)
			os.rename(tmp, path)
		except Exception:
			pass

	# ---- pomocné --------------------------------------------------------------------------------

	def _brand(self):
		b = getattr(self.api, 'brand', 'cpsvk')
		return BRANDS.get(b) or BRANDS['cpsvk']

	def _timeout(self):
		try:
			return self.api.request_timeout()
		except Exception:
			return TIMEOUT

	def device_info(self, country=False):
		b = self._brand()
		d = {
			'operationMode': 'OTT', 'memberId': '0', 'deviceSerial': self.serial,
			'deviceType': 'ConnectedTV', 'deviceSubType': 'webos', 'deviceOem': 'LG',
			'featureLevel': FEATURE_LEVEL, 'language': b['language'], 'deviceModel': '43UP78003LB',
			'osVersion': '6.5.3', 'appVersion': APP_VERSION, 'appStore': b.get('appStore'),
			'brand': 'm7cp', 'environment': 'j', 'tvapiQueue': True,
		}
		if country:
			d['country'] = b['country']
		return d

	def _headers(self, bearer=False):
		h = {
			'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json',
			'Origin': 'https://m7cpstatic.solocoo.tv', 'Referer': 'https://m7cpstatic.solocoo.tv/',
			'User-Agent': USER_AGENT,
		}
		if bearer and self.token:
			h['Authorization'] = 'Bearer ' + self.token
		return h

	def _post(self, url, data, bearer=False):
		return self.api.req_session.post(url, json=data, headers=self._headers(bearer),
		                                 timeout=self._timeout())

	def _get(self, url, params=None, bearer=True):
		return self.api.req_session.get(url, params=params, headers=self._headers(bearer),
		                                timeout=self._timeout())

	# ---- párovanie kódom ------------------------------------------------------------------------

	def is_paired(self):
		return bool(self.sso_token)

	def request_pairing(self):
		"""Spustí párovanie. Vráti (kód, url)."""
		r = self._post(PAIR_REQUEST_URL, {'deviceInfo': self.device_info(country=True)})
		try:
			j = r.json() or {}
		except Exception:
			j = {}
		if j.get('result') == 'success' and j.get('code'):
			self._pair_interval = int(j.get('nextInterval') or 5)
			return j.get('code'), (j.get('url') or 'https://connect.canalplus.com')
		raise Exception(j.get('Message') or j.get('label')
		                or 'cpReversePairingRequest failed (HTTP %d)' % r.status_code)

	def pairing_interval(self):
		return self._pair_interval

	def poll_pairing_once(self, code):
		"""Jedno overenie. Vráti ssoToken keď spárované, inak None."""
		r = self._post(PAIR_CHECK_URL, {'deviceInfo': self.device_info(country=True), 'code': code})
		try:
			j = r.json() or {}
		except Exception:
			j = {}
		self._pair_interval = int(j.get('nextInterval') or self.pairing_interval() or 5)
		if j.get('paired') and j.get('ssoToken'):
			with self._lock:
				self.sso_token = j.get('ssoToken')
				self.token = None
				self.token_valid_until = 0
			self._save_state()
			return self.sso_token
		return None

	def logout(self):
		with self._lock:
			self.sso_token = None
			self.token = None
			self.pass_token = None
			self.token_valid_until = 0
		self._save_state()

	# ---- session -> Bearer ----------------------------------------------------------------------

	def _provision(self):
		r = self._post(TVAPI_URL + '/v1/provision', self.device_info())
		try:
			j = r.json() or {}
		except Exception:
			j = {}
		prov = (j.get('session') or {}).get('provisionData')
		if not prov:
			raise Exception('provision returned no provisionData (HTTP %d)' % r.status_code)
		return prov

	def ensure_session(self, force=False):
		with self._lock:
			if not force and self.token and time() < self.token_valid_until:
				return self.token
			if not self.sso_token:
				raise SolocooAuthError('Device is not paired')

			prov = self._provision()
			data = self.device_info()
			data['ssoToken'] = self.sso_token
			data['provisionData'] = prov
			r = self._post(TVAPI_URL + '/v1/session', data)
			try:
				j = r.json() or {}
			except Exception:
				j = {}

			if r.status_code == 403 and not j.get('ssoLogout'):
				# 403 moze byt aj docasne (WAF/geo) - sparovanie nemazeme
				raise Exception('session HTTP 403 (%s)' % (j.get('Message') or j.get('label') or ''))

			if r.status_code == 401 or j.get('ssoLogout'):
				self.sso_token = None
				self.token = None
				self._save_state()
				raise SolocooAuthError('Session rejected (%s)' % (j.get('Message') or j.get('label') or r.status_code))

			token = j.get('token')
			if not token:
				raise Exception('session returned no token (HTTP %d)' % r.status_code)

			self.token = token
			if j.get('passToken'):
				self.pass_token = j.get('passToken')
			new_sso = j.get('ssoToken')
			if new_sso and new_sso != self.sso_token:
				self.sso_token = new_sso
				self._save_state()
			exp = j.get('expiresIn') or j.get('ttl')
			try:
				secs = int(exp) if exp else 600
			except Exception:
				secs = 600
			self.token_valid_until = time() + max(60, secs - TOKEN_MARGIN)
			return self.token

	# ---- program (schedule) ---------------------------------------------------------------------

	@staticmethod
	def _event(item):
		if not isinstance(item, dict):
			return None
		params = item.get('params') or {}
		title = item.get('title') or item.get('name') or params.get('title') or ''
		if not title:
			return None
		start = _to_ts(item.get('start') or item.get('from') or params.get('start'))
		end = _to_ts(item.get('end') or item.get('until') or params.get('end'))
		if not start:
			return None
		subtitle = item.get('subtitle') or item.get('shortDescription') or ''
		# plny popis v programe nie je, dotahuje sa z detailu relacie (get_descriptions)
		desc = item.get('desc') or ''
		image = None
		for k in ('image', 'thumbnail', 'poster'):
			v = item.get(k) or params.get(k)
			if v:
				image = v
				break
		asset_id = item.get('id') or params.get('id') or ''
		return {'start': int(start), 'end': int(end) or 0, 'title': title,
		        'subtitle': subtitle or '', 'desc': desc or '', 'image': image, 'id': str(asset_id)}

	def get_descriptions(self, asset_ids, workers=6, time_limit=40):
		"""Plne popisy relacii z /v1/assets/<id> (paralelne, s pamatou)."""
		ids = []
		for a in asset_ids:
			a = str(a or '')
			if a and a not in self._desc_cache and a not in ids:
				ids.append(a)
		if not ids:
			return self._desc_cache
		if len(self._desc_cache) > DESC_CACHE_MAX:
			self._desc_cache = {}

		if not self._desc_lock.acquire(False):
			return self._desc_cache
		try:
			try:
				self.ensure_session()
			except Exception:
				return self._desc_cache

			idx = {'i': 0}
			lk = threading.Lock()
			deadline = time() + time_limit

			def worker():
				while True:
					with lk:
						i = idx['i']
						if i >= len(ids) or time() > deadline:
							return
						idx['i'] = i + 1
					aid = ids[i]
					try:
						r = self._get(TVAPI_URL + '/v1/assets/' + aid, bearer=True)
						if r.status_code == 200:
							d = r.json() or {}
							if isinstance(d, dict):
								with lk:
									self._desc_cache[aid] = d.get('desc') or (d.get('params') or {}).get('desc') or ''
					except Exception:
						pass

			threads = [threading.Thread(target=worker) for _ in range(min(workers, len(ids)))]
			for t in threads:
				t.daemon = True
				t.start()
			for t in threads:
				t.join(timeout=time_limit + 5)
			return self._desc_cache
		finally:
			try:
				self._desc_lock.release()
			except Exception:
				pass

	def _schedule_once(self, cc_ids, t_from, t_until):
		start = (int(t_from) // EPG_ALIGN) * EPG_ALIGN
		end = -((-int(t_until)) // EPG_ALIGN) * EPG_ALIGN
		if end <= start:
			end = start + EPG_ALIGN
		params = {'channels': ','.join(cc_ids), 'from': _iso(start), 'until': _iso(end)}
		r = self._get(TVAPI_URL + '/v1/schedule', params=params, bearer=True)
		if r.status_code in (401, 403):
			self.ensure_session(force=True)
			r = self._get(TVAPI_URL + '/v1/schedule', params=params, bearer=True)
		try:
			j = r.json() or {}
		except Exception:
			j = {}
		epg = j.get('epg')
		out = {}
		if isinstance(epg, dict):
			for cid, items in epg.items():
				evs = [e for e in (self._event(it) for it in (items or [])) if e]
				if evs:
					out[str(cid)] = evs
		return out

	def get_schedule_now(self, cc_ids):
		"""Prave beziaca relacia pre zoznam kanalov: {cc_id: udalost}."""
		cc_ids = [str(c) for c in cc_ids if c]
		if not cc_ids:
			return {}
		self.ensure_session()
		out = {}
		for i in range(0, len(cc_ids), CHANNELS_PER_REQUEST):
			group = cc_ids[i:i + CHANNELS_PER_REQUEST]
			params = {'channels': ','.join(group)}
			r = self._get(TVAPI_URL + '/v1/schedule/now', params=params, bearer=True)
			if r.status_code in (401, 403):
				self.ensure_session(force=True)
				r = self._get(TVAPI_URL + '/v1/schedule/now', params=params, bearer=True)
			try:
				j = r.json() or {}
			except Exception:
				j = {}
			epg = j.get('epg')
			if isinstance(epg, dict):
				now = time()
				for cid, items in epg.items():
					lst = items if isinstance(items, list) else [items]
					cur = None
					for it in lst:
						e = self._event(it)
						if not e:
							continue
						if cur is None:
							cur = e
						if e['start'] <= now < (e['end'] or (e['start'] + 1)):
							cur = e
							break
					if cur:
						out[str(cid)] = cur
		return out

	def get_schedule(self, cc_ids, t_from, t_until):
		"""Program kanalov (cc...) v rozsahu, deli sa na 24 h okna a skupiny kanalov.
		Vrati {cc_id: [udalosti]}."""
		cc_ids = [str(c) for c in cc_ids if c]
		if not cc_ids:
			return {}
		self.ensure_session()
		merged = {}
		for i in range(0, len(cc_ids), CHANNELS_PER_REQUEST):
			group = cc_ids[i:i + CHANNELS_PER_REQUEST]
			win = int(t_from)
			while win < int(t_until):
				win_end = min(win + SCHEDULE_WINDOW, int(t_until))
				try:
					part = self._schedule_once(group, win, win_end)
				except Exception as e:
					self.cp.log_error('Solocoo schedule failed: %s' % e)
					part = {}
				for cid, evs in part.items():
					bucket = merged.setdefault(cid, {})
					for ev in evs:
						bucket[ev['start']] = ev
				win = win_end
		return dict((cid, sorted(b.values(), key=lambda e: e['start'])) for cid, b in merged.items())
