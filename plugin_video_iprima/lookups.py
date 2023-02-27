# -*- coding: utf-8 -*-

shared = {
	'graphql_base': 'https://api.iprima.cz/graphql',
	'play_api_base': 'https://api.play-backend.iprima.cz/api/v1',
	'plugin_path': 'plugin://plugin.video.iprima',
	'pagination': 25, # default value, can be overriden in addon settings
}

settings = {
	'pagination_options': [25, 50, 100, 150, 300, 500]
}

menu_items = [
	{
		'title': 'Živé vysílání',
		'resource': 'live',
	},
	{
		'title': 'Nejsledovanější',
		'resource': 'programs_sort_top'
	},
	{
		'title': 'Naposledy odvysílané',
		'resource': 'programs_sort_broadcast_date'
	},
	{
		'title': 'Pořady a seriály',
		'resource': 'programs',
	},
	{
		'title': 'Filmy',
		'resource': 'movies',
	},
	{
		'title': 'Seriály pro děti',
		'resource': 'kids_series',
	},
	{
		'title': 'Filmy pro děti',
		'resource': 'kids_movies',
	}
]

resources = {
	'live': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'channelList'],
		'post_data': '{ "query": "{ channelList { name logo playId id } }"}'
	},
	'programs': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'programList'],
		'post_data': '{ "query": "{ programList(paging: {count: $count, offset: $offset}, hasEpisodes: true, sort: title_asc) { title type teaser thumbnailData(size: hbbtv_tile_m) {url} seasons availableEpisodesCount genres nid }}"}',
#		'subsections': [
#			{'title': 'Nejsledovanější', 'resource': 'programs_sort_top'},
#			{'title': 'Naposledy odvysílané', 'resource': 'programs_sort_broadcast_date'}
#		]
	},
	'programs_sort_top': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'programList'],
		'post_data': '{ "query": "{ programList(paging: {count: $count, offset: $offset}, hasEpisodes: true, sort: top) { title type teaser thumbnailData(size: hbbtv_tile_m) {url} seasons availableEpisodesCount genres nid }}"}'
	},
	'programs_sort_broadcast_date': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'programList'],
		'post_data': '{ "query": "{ programList(paging: {count: $count, offset: $offset}, hasEpisodes: true, sort: broadcast_date) { title type teaser thumbnailData(size: hbbtv_tile_m) {url} seasons availableEpisodesCount genres nid }}"}'
	},
	'program_by_id': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'programById'],
		'post_data': '{ "query": "{ programById(id: $nid) { title type genres teaser seasons episodes(paging: {count: $count, offset: $offset}) { title type admittanceType episodeTitle teaser genres premiereDate length thumbnailData(size: hbbtv_tile_m) {url} playId } }}"}'
	},
	'movies': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-movies\\", paging: { count: $count, offset: $offset } sort: title_asc params: { facetFilters: { type: [video] } } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId } } } }"}'
	},
	'kids_movies': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-children\\", paging: { count: $count, offset: $offset } sort: title_asc params: { facetFilters: { type: [video] } } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId } } } }"}'
	},
	'kids_series': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-children\\", paging: { count: $count, offset: $offset } sort: title_asc params: { facetFilters: { type: [program] } } ) { title content { ... on ProgramNode { title type teaser genres seasons availableEpisodesCount thumbnailData(size: hbbtv_tile_m) {url} nid } } } }"}'
	},
	'season': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'videoList'],
		'post_data': '{ "query": "{ videoList( paging: { count: $count, offset: $offset }, programId: $programId sort: premiere_date videoCategory: episode season: \\"$season\\") { title type genres teaser premiereDate length thumbnailData(size: hbbtv_tile_m) {url} playId } }"}'
	},
	'bonus': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'videoList'],
		'post_data': '{ "query": "{ videoList( paging: { count: $count, offset: $offset }, programId: $programId sort: premiere_date videoCategory: bonus ) { title type genres teaser premiereDate length thumbnailData(size: hbbtv_tile_m) {url} playId } }"}'
	},
	'search_series': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-search-series\\", paging: { count: $count, offset: $offset } sort: title_asc params: { keyword: \\"$keyword\\" } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId } } } }"}'

	},
	'search_episodes': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-search-episodes\\", paging: { count: $count, offset: $offset } sort: title_asc params: { keyword: \\"$keyword\\" } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId nid } } } }"}'
	},
	'search_movies': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-search-movies\\", paging: { count: $count, offset: $offset } sort: title_asc params: { keyword: \\"$keyword\\" } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId nid } } } }"}'
	},
	'search_bonus': {
		'path': shared['graphql_base'],
		'method': 'POST',
		'content_path': ['data', 'strip', 'content'],
		'post_data': '{ "query": "{ strip( id: \\"web-search-video-bonus\\", paging: { count: $count, offset: $offset } sort: title_asc params: { keyword: \\"$keyword\\" } ) { title content { ... on VideoNode { title type teaser genres premiereDate length admittanceType thumbnailData(size: hbbtv_tile_m) {url} playId nid } } } }"}'
	},
	'play': {
		'path': shared['play_api_base'] + '/products/id-{id}/play',
		'method': 'GET',
	}
}

item_types = {
	'program': {
		'playable': False
	},
	'video': {
		'playable': True
	}
}

free_admittance_types = ['free', 'basic', 'registered']
