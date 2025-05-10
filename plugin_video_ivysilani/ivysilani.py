# -*- coding: utf-8 -*-

from datetime import date

from tools_archivczsk.contentprovider.exception import LoginException, AddonErrorException
from tools_archivczsk.debug.http import dump_json_request
from tools_archivczsk.contentprovider.provider import USER_AGENT

COMMON_HEADERS = {
	'User-Agent': USER_AGENT,
	'Accept-language': 'cs',
	'Accept': 'application/json; charset=utf-8',
	'Content-Type': 'application/json'
}

IMAGE_WIDTH = 400
DUMP_REQUESTS=False

# #################################################################################################

def _(s):
	return s

# used to translate error messages returned from server
ERROR_MESSAGES = [
	_("Medium does not have valid licence")
]

# #################################################################################################

class iVysilani(object):
	def __init__(self, content_provider):
		self.cp = content_provider
		self._ = content_provider._
		self.PAGE_SIZE = 40
		self.client_version = '1.142.0'
		self.req_session = self.cp.get_requests_session()
		self.req_session.headers.update(COMMON_HEADERS)
		self.rid = 0

	# #################################################################################################

	def call_api(self, endpoint, params=None, data=None):
		if endpoint.startswith('http'):
			url = endpoint
		else:
			url = 'https://api.ceskatelevize.cz/' + endpoint


		if data:
			response = self.req_session.post(url, params=params, json=data)
		else:
			response = self.req_session.get(url, params=params)

		if DUMP_REQUESTS:
			dump_json_request(response)

		try:
			response.raise_for_status()
		except Exception as e:
			try:
				msg = response.json()
				if 'playabilityMessage' in msg:
					err_msg = msg.get('playabilityMessage',{}).get('labels',{}).get('additionalText')
				elif 'errors' in msg:
					err_msg = msg['errors'][0]['message']
				elif 'message' in msg:
					err_msg = msg['message']
				else:
					err_msg = None

			except:
				err_msg = None

			if err_msg:
				raise AddonErrorException(self._(err_msg))
			else:
				raise e

		try:
			ret = response.json()
		except:
			ret = {}

		if 'errors' in ret:
			raise AddonErrorException(self._(ret['errors'][0]['message']))

		return ret

	# #################################################################################################

	def call_graphql(self, operation_name, query, variables={}):
		params = {
			'client': 'iVysilaniWeb',
			'version': self.client_version,
			'use-new-playability': True
		}

		data = {
			'operationName': operation_name,
			'query': query.replace('\t', '').replace('\n', ' '),
			'variables': variables,
		}

		data = self.call_api('graphql/', params=params, data=data)

		for result in data.get('data',{}).values():
			return result
		else:
			return None

	# #################################################################################################

	def get_live_channels(self):
		query = '''query TVProgramChannelsList
		{
			TVProgramChannelsList
			{
				channelAsString
				encoder
				channelSettings
				{
					channelLogo
					channelName
				}
			}
		}'''

		data = self.call_graphql('TVProgramChannelsList', query)
		i = 0
		channels = {}

		for item in data:
			if item['channelAsString'] in channels:
				continue

			channels[item['channelAsString']] = {
				'order': i,
				'id' : item['encoder'],
				'name' : item['channelSettings']['channelName'],
				'img' : item['channelSettings']['channelLogo']
			}
			i += 1

		return channels

	# #################################################################################################

	def get_stream_data(self, idec):
		params = {
			'canPlayDrm': 'true',
			'quality': 'web',
			'streamType': 'dash',
			'origin': 'ivysilani',
			'usePlayability': True
		}
		return self.call_api('video/v1/playlist-vod/v1/stream-data/media/external/' + str(idec), params=params)

	# #################################################################################################

	def get_live_stream_data(self, channel_id):
		params = {
			'canPlayDrm': 'false',
			'quality': 'web',
			'streamType': 'hls',
			'origin': 'ivysilani',
			'maxQualityCount': 5
		}

		return self.call_api('video/v1/playlist-live/v1/stream-data/channel/' + str(channel_id), params=params)

	# #################################################################################################

	def live_broadcast_find(self, channels=None):
		query = '''query LiveBroadcastFind
		{
			liveBroadcastFind
			{
				id
				slug
				current
				{
					id
					idec
					sidp
					channel
					encoder
					channelSettings
					{
						channelLogo
						channelName
					}
					title
					description
					previewImage(width: 480, height: 270)
					startsAt
					endsAt
					isExtra
					isPlayable
					willBePlayable
					cardLabels
					{
						center
					}
				}
				next
				{
					id
					idec
					sidp
					channel
					encoder
					channelSettings
					{
						channelLogo
						channelName
					}
					title
					description
					previewImage(width: 480, height: 270)
					startsAt
					endsAt
					isExtra
					isPlayable
					willBePlayable
					cardLabels
					{
						center
					}
				}
			}
		}'''

		return self.call_graphql('LiveBroadcastFind', query)

	# #################################################################################################

	def get_current_broadcast(self, channels=None):
		if not channels:
			channels = self.get_live_channels()

		if isinstance(channels, dict):
			channels = [k for k,v in sorted(channels.items(), key=lambda x: x[1]['order'])]

		query = '''query CurrentBroadcast($channels: [String!]!, $date: Date!)
		{
			TVProgramDailyChannelsPlanV2(channels: $channels, date: $date)
			{
				channel
				currentBroadcast
				{
					item
					{
						idec
						sidp
						startTime
						title
						episodeTitle
						part
						description
						imageUrl
						length
						isPlayableNow
						playableFrom
						liveOnly
						start
						end
					}
				}
			}
		}'''

		variables = {
			"channels": channels,
			"date": date.today().strftime('%m.%d.%Y')
		}

		return self.call_graphql('CurrentBroadcast', query, variables)


	# #################################################################################################

	def get_channel_epg(self, channel, day):
		query = '''query TvProgramDailyTablet($channels: [String!]!, $date: Date!)
		{
			TVProgramDailyChannelsPlanV2(channels: $channels, date: $date)
			{
				channel
				encoder
				program
				{
					idec
					sidp
					startTime
					title
					episodeTitle
					part
					description
					imageUrl
					length
					isPlayableNow
					playableFrom
					liveOnly
					start
					end
				}
			}
		}'''

		variables = {
			'channels': channel,
			'date': day.strftime('%m.%d.%Y')
		}

		return self.call_graphql('TvProgramDailyTablet', query, variables)[0]['program']

	# #################################################################################################

	def get_categories(self):
		query = '''query Categories($deviceType: String!)
		{
			menuOnlyCategories(deviceType: $deviceType)
			{
				categoryId
				title
				children
				{
					categoryId
					title
				}
			}
		}'''

		variables = {
			"deviceType": "website"
		}

		return self.call_graphql('Categories', query, variables)

	# #################################################################################################

	def get_category_by_id(self, cat_id, page=0):
		query = '''query GetCategoryById($limit: PaginationAmount!, $offset: Int!, $categoryId: String!, $order: OrderByDirection, $orderBy: CategoryOrderByType)
		{
			category(categoryId: $categoryId)
			{
				programmeFind(limit: $limit, offset:$offset, order:$order, orderBy:$orderBy)
				{
					totalCount
					items
					{
						id
						idec
						flatGenres(exceptCategoryId: $categoryId)
						{
							id
							title
						}
						title
						showType
						description
						duration
						shortDescription
						year
						images
						{
							card
							hero
							{
								mobile
							}
						}
						isPlayable
					}
				}
			}
		}'''

		variables = {
			"categoryId": cat_id,
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
#			"order":"asc",
#			"orderBy": "alphabet"
#			"orderBy": "popular_previous_seven_days"
		}

		return self.call_graphql('GetCategoryById', query, variables)

	# #################################################################################################

	def get_show_info(self, show_id):
		query = '''query Show($id: String!)
		{
			show(id: $id)
			{
				programmeId
				sidp
				idec
				isPlayable
				seasons
				{
					id
					title
				}
				title
				showType
				description
				shortDescription
				duration
				creators
				images
				{
					card
					hero
					{
						mobile
					}
				}
				year
				countriesOfOrigin
				{
					title
				}
				genres
				{
					children
					{
						title
					}
				}
				defaultSort
				playabilityError
				slug
			}
		}'''

		variables = {
			"id": show_id,
		}

		return self.call_graphql('Show', query, variables)

	# #################################################################################################

	def get_episodes(self, idec, page=0, season_id=None):
		query = '''query GetEpisodes($idec: String!, $seasonId: String, $limit: PaginationAmount!, $offset: Int!, $orderBy: EpisodeOrderByType!, $keyword: String, $onlyPlayable: Boolean)
		{
			episodesPreviewFind(idec: $idec, seasonId: $seasonId, limit: $limit, offset: $offset, orderBy: $orderBy, keyword: $keyword, onlyPlayable: $onlyPlayable)
			{
				totalCount
				items
				{
					id
					title
					description
					duration
					playable
					season
					{
						id
						title
					}
					images
					{
						card
					}
					showId
					showTitle
					lastBroadcast
					{
						datetime
						channel
					}
				}
			}
		}'''

		variables = {
			"idec": idec,
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
			"orderBy": "newest",
			"onlyPlayable": False
		}

		if season_id:
			variables['seasonId'] = season_id

		return self.call_graphql('GetEpisodes', query, variables)

	# #################################################################################################

	def get_homepage_rows(self, page=0):
		query = '''query HomepageRows($deviceType: String!, $limit: PaginationAmount!, $offset: Int!)
		{
			homepageConfig(deviceType: $deviceType)
			{
				rows(limit: $limit, offset: $offset)
				{
					id
					title
					subtitle
					type
					disabled
					assets
					{
						totalCount
					}
				}
			}
		}'''

		variables = {
			"deviceType": "website",
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
		}

		return self.call_graphql('HomepageRows', query, variables)

	# #################################################################################################

	def get_homepage_block(self, block_id, page=0):
		query = '''query HomepageBlock($id: String!, $limit: Int!, $offset: Int!, $deviceType: String!)
		{
			homepageBlock(id: $id, deviceType: $deviceType)
			{
				assets(limit: $limit, offset: $offset)
				{
					totalCount
					items
					{
						... on ShowCard
						{
							id
							sidp
							genres
							{
								id
								title
							}
							title
							description
							imageUrl
							playable
						}
						... on EpisodeCard
						{
							id
							sidp
							idec
							genres
							{
								id
								title
							}
							programmeType
							title
							description
							showTitle
							previewImage
							playable
						}
					}
				}
			}
		}'''

		variables = {
			"id": block_id,
			"deviceType": "website",
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
		}

		return self.call_graphql('HomepageBlock', query, variables)

	# #################################################################################################

	def get_related_shows(self, show_id, page=0):
		query = '''query RelatedShowFind($showId: String!, $limit: Int!, $offset: Int!)
		{
			relatedShowFind(id: $showId, limit: $limit, offset: $offset)
			{
				totalCount
				items
				{
					id
					idec
					title
					description
					shortDescription
					duration
					year
					showType
					images
					{
						card
						hero
						{
							mobile
						}
					}
					flatGenres
					{
						id
						title
					}
				}
			}
		}'''

		variables = {
			"showId": show_id,
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
		}

		return self.call_graphql('RelatedShowFind', query, variables)

	# #################################################################################################

	def search_shows(self, keyword, page=0):
		query = '''query SearchShows($keyword: String!, $limit: PaginationAmount!, $offset: Int!, $onlyPlayable: Boolean!)
		{
			searchShowsAsYouType(keyword: $keyword, limit: $limit, offset: $offset, onlyPlayable: $onlyPlayable)
			{
				totalCount
				items
				{
					id
					sidp
					genres
					{
						id
						title
					}
					title
					description
					imageUrl
					playable
				}
			}
		}'''

		variables = {
			"keyword": keyword,
			"limit": self.PAGE_SIZE,
			"offset": page * self.PAGE_SIZE,
			'onlyPlayable': True
		}

		return self.call_graphql('SearchShows', query, variables)

# #################################################################################################
