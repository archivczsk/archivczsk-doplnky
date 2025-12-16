# -*- coding: utf-8 -*-
from tools_archivczsk.contentprovider.provider import CommonContentProvider
from tools_archivczsk.contentprovider.exception import AddonErrorException
from tools_archivczsk.http_handler.hls import stream_key_to_hls_url
from tools_archivczsk.http_handler.dash import stream_key_to_dash_url
from tools_archivczsk.cache import SimpleAutokeyExpiringCache
from tools_archivczsk.string_utils import _I, _C, _B, int_to_roman
from .primaplus import PrimaPlus
from datetime import datetime, date, timedelta
import time

class PrimaPlusContentProvider(CommonContentProvider):

	def __init__(self, settings=None, data_dir=None, http_endpoint=None):
		CommonContentProvider.__init__(self, 'Prima+', settings=settings, data_dir=data_dir)
		self.http_endpoint = http_endpoint
		self.primaplus = None
		self.login_optional_settings_names = ('username', 'password')
		self.scache = SimpleAutokeyExpiringCache()

	# ##################################################################################################################

	def login(self, silent):
		if not self.get_setting('username') or not self.get_setting('password'):
			if not silent:
				self.show_info(self._("To display the content, you must enter a login name and password in the addon settings"), noexit=True)
			return False

		self.primaplus = PrimaPlus(self)
		if self.primaplus.check_access_token() == False:
			self.primaplus.login()

		self.days_of_week = (self._('Monday'), self._('Tuesday'), self._('Wednesday'), self._('Thursday'), 	self._('Friday'), self._('Saturday'), self._('Sunday'))
		return True

	# ##################################################################################################################

	def root(self):
		self.primaplus.clear_subscription()

		self.add_search_dir()
		self.add_dir(self._("Movies"), cmd=self.list_layout, layout='categoryMovie')
		self.add_dir(self._("Series"), cmd=self.list_layout, layout='categorySeries')
		self.add_dir(self._("Kids"), cmd=self.list_layout, layout='kids')
		self.add_dir(self._("New releases"), cmd=self.list_layout, layout='categoryNewReleases')
		self.add_dir(self._("My"), cmd=self.list_layout, layout='mySection')
		self.add_dir(self._("Genres"), cmd=self.list_genres)
		self.add_dir(self._("Live"), cmd=self.list_chnnels)
		self.add_dir(self._("Archive"), cmd=self.list_archive)
		self.add_dir(self._("Informations and settings"), cmd=self.list_info)

	# ##################################################################################################################

	def list_info(self):
		self.add_dir(self._("Profiles"), cmd=self.list_profiles)
		self.add_dir(self._("Devices"), cmd=self.list_devices)
		self.add_video(self._("Account informations"), cmd=self.account_info)

	# ##################################################################################################################

	def account_info(self):
		data = self.primaplus.get_account_info()

		result = []
		result.append(self._("Customer") + ':')
		result.append(self._("Name") + ': %s %s' % (data["firstName"] or '', data['lastName'] or ''))
		if data.get("address"):
			result.append(self._("Address") + ': %s, %s %s' % (data["address"]['streetAddress'] or '', data["address"]['postalCode'] or '', data["address"]['locality'] or ''))
		result.append(self._("E-Mail") + ': ' + data["email"])

		if data.get("birthYear"):
			result.append(self._("Year of birth") + ': %d' % data["birthYear"])

		result.append(self._("Customer key") + ": " + data["uuid"])
		result.append("")
		result.append(self._("Active subscription") + ": " + data["primaPlay"]['userLevel'])
		result.append("{}: {}".format(self._("Paid"), self._("Yes") if data["primaPlay"]['paidSubscription'] else self._("No")))
		try:
			d = datetime.strptime(data['subscriptionData']["currentSubscription"]['validFrom'][:19], "%Y-%m-%dT%H:%M:%S")
			result.append(self._("Valid from") + ": {:02}.{:02}.{:04} - {:02d}:{:02d} UTC".format(d.day, d.month, d.year, d.hour, d.minute))
		except:
			self.log_exception()

		try:
			d = datetime.strptime(data['subscriptionData']["currentSubscription"]['validUntil'][:19], "%Y-%m-%dT%H:%M:%S")
			result.append(self._("Valid until") + ": {:02}.{:02}.{:04} - {:02d}:{:02d} UTC".format(d.day, d.month, d.year, d.hour, d.minute))
		except:
			self.log_exception()

		self.show_info('\n'.join(result), noexit=True)

	# ##################################################################################################################

	def list_devices(self):
		for item in self.primaplus.get_devices():
			plot = []
			d = datetime.strptime(item["registered"][:19], "%Y-%m-%dT%H:%M:%S")
			plot.append("{}: {:02}.{:02}.{:04} - {:02d}:{:02d} UTC".format(self._("Registered at"), d.day, d.month, d.year, d.hour, d.minute))

			d = datetime.strptime(item["lastChanged"][:19], "%Y-%m-%dT%H:%M:%S")
			plot.append("{}: {:02}.{:02}.{:04} - {:02d}:{:02d} UTC".format(self._("Last change"), d.day, d.month, d.year, d.hour, d.minute))

			title = '[%s]: %s' % (item['slotType'], item['title'])
			if item['this']:
				title = _I(title)
			self.add_video(title, info_labels={'plot': '\n'.join(plot)}, cmd=self.delete_device, device_id=item['slotId'] if item['this'] == False else None )

	# ##################################################################################################################

	def delete_device(self, device_id):
		if device_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to delete this device?")) == True:
			self.primaplus.delete_device(device_id)
			self.refresh_screen()

	# ##################################################################################################################

	def list_profiles(self):
		for p in self.primaplus.get_profiles():
			d = datetime.strptime(p['metadata']["createdAt"][:19], "%Y-%m-%dT%H:%M:%S")
			plot = ["{}: {:02}.{:02}.{:04} - {:02d}:{:02d} UTC".format(self._("Created at"), d.day, d.month, d.year, d.hour, d.minute)]
			plot.append('%s: %d' % (self._('Year of birth'), p['birthYear']))
			if p['master']:
				plot.append(self._("Main profile"))
			if p['kids']:
				plot.append(self._("Kids profile"))

			if p['this']:
				title = _I(p['name'])
			else:
				title = p['name']

			self.add_video(title, img=p['avatarUrl'], info_labels={'plot':'\n'.join(plot)}, cmd=self.switch_profile, profile_id=p['ulid'] if p['this'] == False else None)

	# ##################################################################################################################

	def switch_profile(self, profile_id):
		if profile_id == None:
			return

		if self.get_yes_no_input(self._("Do you realy want to switch profile?")) == True:
			self.primaplus.switch_profile(profile_id)
			self.refresh_screen()

	# ##################################################################################################################

	def search(self, keyword, search_id):
		for item in self.primaplus.search(keyword):
			self.add_media_item(item)

	# ##################################################################################################################

	def add_media_item(self, item, menu=None):
		if item['type'] not in ('movie', 'episode', 'series'):
			return

		subscription = self.primaplus.get_subscription()
		additionals = item.get('additionals',{}) or {}
		date = ''
		if additionals.get('broadcastDateTime') is not None:
			split_date = additionals['broadcastDateTime'][:10].split('-')
			date = ' | ' + split_date[2] + '.' + split_date[1] + '.' + split_date[0]
		elif additionals.get('premiereDateTime') is not None:
			split_date = additionals['premiereDateTime'][:10].split('-')
			date = ' | ' + split_date[2] + '.' + split_date[1] + '.' + split_date[0]

		if item['type'] == 'episode' and '(' + str(additionals.get('episodeNumber', 0)) + ')' not in item['title']:
			title = item['title'] + ' (' + str(additionals.get('episodeNumber', 0)) + ')' + date
		else:
			title = item['title']

		locked = False
		for d in filter(lambda x: x['userLevel'] == subscription, item.get('distributions') or []):
			if d['showLock']:
				title = _C('gray', title )
				locked = True

		info_labels = {
			'title': item['title'],
			'plot': item.get('perex'),
			'year': int(additionals.get('year', 0) or 0),
			'genre' : ', '.join(additionals.get('genres',[]))
		}
		if item['type'] == 'episode':
			info_labels.update({
				'epname': item['title'],
				'episode': int(additionals.get('episodeNumber',0)),
				'season': int(additionals.get('seasonNumber',0)),
			})
			info_labels['title'] += ' %s (%d)' % (int_to_roman(info_labels['season']), info_labels['episode'])

		if menu == None:
			menu = self.create_ctx_menu()

		if self.is_fav(item):
			menu.add_menu_item(self._("Remove from my list"), self.remove_fav, item=item)
		else:
			menu.add_menu_item(self._("Add to my list"), self.add_fav, item=item)

		img = item['images']['3x5'] or additionals.get('programImages',{}).get('3x5') or additionals.get('parentImages',{}).get('3x5') or item['images']['16x9'] or additionals.get('programImages',{}).get('16x9') or additionals.get('parentImages',{}).get('16x9')

		if item['type'] == 'series':
			self.add_dir(item['title'], img=img, info_labels=info_labels, menu=menu, cmd=self.list_series, series_id=item['id'])
		else:
			self.add_video(title, img=img, info_labels=info_labels, menu=menu, cmd=self.play_stream, play_id=None if locked else item['playId'], play_title=title)


	# ##################################################################################################################

	def add_item_uni(self, item, menu=None, data_filter=None):
		if item['type'] in ('movie', 'episode', 'series'):
			return self.add_media_item(item, menu=menu)
		elif item['type'] == 'api' and item['method'] == 'vdm.frontend.genre.list':
			self.add_dir(item['title'], cmd=self.list_genres)
		elif item['type'] == 'recombee':
			self.add_dir(item['title'], cmd=self.list_recombee, scenario=item['scenario'], data_filter=data_filter)
		elif item['type'] == 'technical' and item['subtype'] == 'watchList':
			self.add_dir(item['title'], cmd=self.list_watchlist, scenario=item['scenario'])
		else:
			self.log_error("Item with type %s is not supported\n%s" % (item['type'], str(item)))

	# ##################################################################################################################

	def list_watchlist(self, scenario):
		self.primaplus.watchlist_reload()

		data_filter = "'xVdmId' in {%s}" % ','.join('"{}"'.format(x) for x in self.primaplus.watchlist.keys())
		return self.list_recombee(scenario, data_filter=data_filter)

	# ##################################################################################################################

	def add_fav(self, item):
		self.primaplus.watchlist_add(item['id'])
		self.refresh_screen()

	def remove_fav(self, item):
		self.primaplus.watchlist_remove(item['id'])
		self.refresh_screen()

	def is_fav(self, item):
		return self.primaplus.watchlist_search(item['id'])

	# ##################################################################################################################

	def list_layout(self, layout, data_filter=None):
		for item in self.primaplus.get_layout(layout):
			self.add_item_uni(item, data_filter=data_filter)

	# ##################################################################################################################

	def list_recombee(self, scenario, order_abc=False, data_filter=None):
		items = self.primaplus.get_recombee_data(scenario, data_filter=data_filter)

		if order_abc:
			items = sorted(items, key=lambda d: d['title'])

		menu = self.create_ctx_menu()
		menu.add_menu_item(self._("Order by alphabet"), cmd=self.list_recombee, scenario=scenario, order_abc=True, data_filter=data_filter)

		for item in items:
			self.add_item_uni(item, menu=menu)

	# ##################################################################################################################

	def list_genres(self):
		for item in self.primaplus.get_genres():
			self.add_dir(item['title'], cmd=self.list_layout, layout='genres', data_filter=item.get('data_filter'))

	# ##################################################################################################################

	def get_utc_offset(self):
		ts = int(time.time())
		return datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)

	# ##################################################################################################################

	def list_chnnels(self):
		utc_offset = self.get_utc_offset()
		epg_data = self.primaplus.get_current_epg( [ch['id'] for ch in self.primaplus.get_channels()] )
		for ch in self.primaplus.get_channels():
			epg = epg_data.get(ch['id'])

			try:
				title = ch['title'] + '  ' + _I(epg['title'])
				start = epg["programStartTime"] or epg['realStartDateTime']
				end = epg["programEndTime"] or epg['realEndDateTime']
				epg_start = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S") + utc_offset
				epg_stop = datetime.strptime(end[:19], "%Y-%m-%dT%H:%M:%S") + utc_offset

				info_labels = {
					'plot':  "[{:02}:{:02} - {:02d}:{:02d}]\n{}".format(epg_start.hour, epg_start.minute, epg_stop.hour, epg_stop.minute, epg.get('description') or ''),
					'year': epg.get('year'),
					'genre': ', '.join(epg.get('genres',[])),
					'duration': epg.get('duration') // 1000 if epg.get('duration') else 0
				}
			except Exception as e:
				if epg:
					self.log_error("Wrong EPG for channel %s:\n%s" % (str(ch), str(e)))

				title = ch['title']
				info_labels = {}

			self.add_video(title, ch['img'], info_labels=info_labels, cmd=self.play_stream, play_id=ch['play_id'], play_title=ch['title'])

	# ##################################################################################################################

	def list_archive(self):
		for ch in self.primaplus.get_channels():
			self.add_dir(ch['title'], ch['img'], cmd=self.list_archive_days, channel_id=ch['id'])

	# ##################################################################################################################

	def list_archive_days(self, channel_id):
		for i in range(31):
			if i == 0:
				day_name = self._("Today")
			elif i == 1:
				day_name = self._("Yesterday")
			else:
				day = date.today() - timedelta(days=i)
				day_name = self.days_of_week[day.weekday()] + " " + day.strftime("%d.%m.%Y")

			self.add_dir(day_name, cmd=self.list_archive_program, channel_id=channel_id, archive_day=i)

	# ##################################################################################################################

	def list_archive_program(self, channel_id, archive_day):
		utc_offset = self.get_utc_offset()

		for item in self.primaplus.get_channel_epg(channel_id, -archive_day):
			epg_start = datetime.strptime(item["programStartTime"][:19], "%Y-%m-%dT%H:%M:%S") + utc_offset
			epg_stop = datetime.strptime(item["programEndTime"][:19], "%Y-%m-%dT%H:%M:%S") + utc_offset
			title = "{:02}:{:02} - {:02d}:{:02d}".format(epg_start.hour, epg_start.minute, epg_stop.hour, epg_stop.minute)

			info_labels = {
				'year': item.get('year'),
				'plot': item.get('description'),
				'genre': ', '.join(item.get('genres',[])),
				'duration': item.get('duration') // 1000 if item.get('duration') else None
			}

			try:
				img = item.get('images',{}).get('3x5') or item.get('programImages',{}).get('3x5') or item.get('parentImages',{}).get('3x5')
			except:
				try:
					img = item.get('images',{}).get('16x9') or item.get('programImages',{}).get('16x9') or item.get('parentImages',{}).get('16x9')
				except:
					img = None

			if item.get('isPlayable'):
				title = title + ' - ' + _I(item['title'])
				self.add_video(title, img=img, info_labels=info_labels, cmd=self.play_stream, play_id=item.get('playId'), play_title=item['title'])
			else:
				title = _C('gray',title + ' - ' + item['title'])
				self.add_video(title, img=img, info_labels=info_labels)


	# ##################################################################################################################

	def list_series(self, series_id, page=0):
		seasons, add_next = self.primaplus.get_seasons(series_id, page)
		if len(seasons) > 1 or page > 0:
			for season in seasons:
				self.add_dir('%02d - %s' % (season['seasonNumber'], season['title']), cmd=self.list_season, season_id=season['id'])

			if add_next:
				self.add_next(cmd=self.list_series, series_id=series_id, page=page+1)
		else:
			for season in seasons:
				self.list_season(season['id'])

	# ##################################################################################################################

	def list_season(self, season_id, page=0):
		episodes, add_next = self.primaplus.get_episodes(season_id, page)
		for item in episodes:
			self.add_media_item(item)

		if add_next:
			self.add_next(cmd=self.list_season, season_id=season_id, page=page+1)

	# ##################################################################################################################

	def get_hls_info(self, stream_key):
		return {
			'url': stream_key['url'],
			'bandwidth': stream_key['bandwidth']
		}

	# ##################################################################################################################

	def get_dash_info(self, stream_key):
		data = self.scache.get(stream_key['key'])
		drm_info = data['drm_info'] or {}

		ret_data = {
			'url': data['url'],
			'bandwidth': stream_key['bandwidth']
		}

		if drm_info.get('license_url') and drm_info.get('license_key'):
			ret_data.update({
				'drm' : {
					'wv': {
						'license_url': drm_info['license_url'],
						'headers': {
							'X-AxDRM-Message': drm_info['license_key']
						}
					}
				}
			})

		return ret_data

	# ##################################################################################################################

	def resolve_hls_streams(self, url, video_title):
		for one in self.get_hls_streams(url, self.primaplus.req_session, max_bitrate=self.get_setting('max_bitrate')):
			key = {
				'url': url,
				'bandwidth': one['bandwidth']
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('resolution', 'x???').split('x')[1] + 'p'
			}
			self.add_play(video_title, stream_key_to_hls_url(self.http_endpoint, key), info_labels=info_labels)
			break # store only first best available stream to playlist

	# ##################################################################################################################

	def resolve_dash_streams(self, url, video_title, drm_info):
		data = {
			'url': url,
			'drm_info': drm_info
		}

		cache_key = self.scache.put(data)
		for one in self.get_dash_streams(url, self.primaplus.req_session, max_bitrate=self.get_setting('max_bitrate')):
			key = {
				'key': cache_key,
				'bandwidth': one['bandwidth']
			}

			info_labels = {
				'bandwidth': one['bandwidth'],
				'quality': one.get('height', '???') + 'p'
			}
			self.add_play(video_title, stream_key_to_dash_url(self.http_endpoint, key), info_labels=info_labels)
			break # store only first best available stream to playlist

	# ##################################################################################################################

	def play_stream(self, play_id, play_title):
		if not play_id:
			return

		prefered_stream_type  = self.get_setting('stream_type')
		all_streams = sorted(self.primaplus.get_streams(play_id), key=lambda x: x['lang'] == 'cs', reverse=True)

		for s in list(filter(lambda x: x['type'] == prefered_stream_type, all_streams)) or all_streams:
			if s['type'] == 'HLS':
				self.resolve_hls_streams(s['url'], '[%s] %s'% (s['lang'].upper(), play_title))
			elif s['type'] == 'DASH':
				self.resolve_dash_streams(s['url'], '[%s] %s'% (s['lang'].upper(), play_title), s.get('drm_info'))

	# ##################################################################################################################
