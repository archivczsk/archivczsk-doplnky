# -*- coding: utf-8 -*-
#
# https://github.com/rg3/youtube-dl
#

import re
import os
import string

try:
	import cookielib
	from urllib2 import urlopen, HTTPError, URLError
	from urllib2 import Request as Request
	from urlparse import urlsplit, urlparse, parse_qs, parse_qsl
	from urllib import quote, unquote_plus, urlencode
	from httplib import HTTPException
except:
	from urllib.request import urlopen
	from urllib.request import Request as Request
	from urllib.parse import urlsplit, urlparse, quote, unquote_plus, parse_qsl, urlencode
	from urllib.error import HTTPError, URLError
	import http.cookiejar as cookielib
	from http.client import HTTPException



_VALID_URL = r"""^
					 (
						 (?:https?://)?										  # http(s):// (optional)
						 (?:youtu\.be/|(?:\w+\.)?youtube(?:-nocookie)?\.com/|
							tube\.majestyc\.net/)							  # the various hostnames, with wildcard subdomains
						 (?:.*?\#/)?										  # handle anchor (#/) redirect urls
						 (?!view_play_list|my_playlists|artist|playlist)	  # ignore playlist URLs
						 (?:												  # the various things that can precede the ID:
							 (?:(?:v|embed|e)/)								  # v/ or embed/ or e/
							 |(?:											  # or the v= param in all its forms
								 (?:watch(?:_popup)?(?:\.php)?)?			  # preceding watch(_popup|.php) or nothing (like /?v=xxxx)
								 (?:\?|\#!?)								  # the params delimiter ? or # or #!
								 (?:.*?&)?									  # any other preceding param (like /?s=tuff&v=xxxx)
								 v=
							 )
						 )?													  # optional -> youtube.com/xxxx is OK
					 )?														  # all until now is optional -> you can pass the naked ID
					 ([0-9A-Za-z_-]+)										  # here is it! the YouTube video ID
					 (?(1).+)?												  # if we found the ID, everything can follow
					 $"""						 
#_LANG_URL = r'http://www.youtube.com/?hl=en&persist_hl=1&gl=US&persist_gl=1&opt_out_ackd=1'
_NEXT_URL_RE = r'[\?&]next_url=([^&]+)'

# Listed in order of quality
_available_formats = ['38', '37', '46', '22', '45', '35', '44', '34', '18', '43', '6', '5', '17', '13']
_video_extensions = {
		'13': '3gp',
		'17': 'mp4',
		'18': 'mp4',
		'22': 'mp4',
		'37': 'mp4',
		'38': 'video', # You actually don't know if this will be MOV, AVI or whatever
		'43': 'webm',
		'44': 'webm',
		'45': 'webm',
		'46': 'webm',
	}
_video_dimensions = {
		'5': '240x400',
		'6': '???',
		'13': '???',
		'17': '144x176',
		'18': '360x640',
		'22': '720x1280',
		'34': '360x640',
		'35': '480x854',
		'37': '1080x1920',
		'38': '3072x4096',
		'43': '360x640',
		'44': '480x854',
		'45': '720x1280',
		'46': '1080x1920',
	}


def report_video_webpage_download( video_id):
	"""Report attempt to download video webpage."""
	print('[youtube] %s: Downloading video webpage' % video_id)
	
def report_video_info_webpage_download( video_id):
	"""Report attempt to download video info webpage."""
	print('[youtube] %s: Downloading video info webpage' % video_id)
	


def getURL(url):
	
	mobj = re.search(_NEXT_URL_RE, url)
	if mobj:
		url = 'http://www.youtube.com/' + unquote(mobj.group(1)).lstrip('/')
	
	# Extract video id from URL
	mobj = re.match(_VALID_URL, url, re.VERBOSE)
	if mobj is None:
		print('ERROR: invalid URL: %s' % url)
		return
	video_id = mobj.group(2)

	# Get video webpage
	report_video_webpage_download(video_id)
	request = Request('http://www.youtube.com/watch?v=%s&gl=US&hl=en&amp;has_verified=1' % video_id)
	try:
		video_webpage = urlopen(request).read()
		video_webpage = video_webpage.decode('utf-8', 'ignore')
	except	err:
		print('ERROR: unable to download video webpage: %s' % str(err))
		return

	# Attempt to extract SWF player URL
	mobj = re.search(r'swfConfig.*?"(http:\\/\\/.*?watch.*?-.*?\.swf)"', video_webpage)
	if mobj is not None:
		player_url = re.sub(r'\\(.)', r'\1', mobj.group(1))
	else:
		player_url = None

	# Get video info
	#report_video_info_webpage_download(video_id)
	for el_type in ['&el=embedded', '&el=detailpage', '&el=vevo', '']:
		video_info_url = ('http://www.youtube.com/get_video_info?&video_id=%s%s&ps=default&eurl=&gl=US&hl=en'
				   % (video_id, el_type))
		request = Request(video_info_url)
		try:
			video_info_webpage = urlopen(request).read()
			video_info_webpage = video_info_webpage.decode('utf-8', 'ignore')
			video_info = parse_qs(video_info_webpage)
			if 'token' in video_info:
				break
		except (URLError, HTTPException, socket.error) as err:
			print('ERROR: unable to download video info webpage: %s' % str(err))
			return
	if 'token' not in video_info:
		if 'reason' in video_info:
			print('ERROR: YouTube said: %s' % video_info['reason'][0].decode('utf-8'))
		else:
			print('ERROR: "token" parameter not in video info for unknown reason')
		return

	if 'conn' in video_info and video_info['conn'][0].startswith('rtmp'):
		#self.report_rtmp_download()
		video_url_list = [(None, video_info['conn'][0])]
		
	elif 'url_encoded_fmt_stream_map' in video_info and len(video_info['url_encoded_fmt_stream_map']) >= 1:
		url_data_strs = video_info['url_encoded_fmt_stream_map'][0].split(',')
		url_data = [parse_qs(uds) for uds in url_data_strs]
		url_data = [ud for ud in url_data if 'itag' in ud and 'url' in ud]
		url_map = dict((ud['itag'][0], ud['url'][0] + '&signature=' + ud['sig'][0]) for ud in url_data)
		#format_limit = params.get('format_limit', None)
		format_list = _available_formats
		existing_formats = [x for x in format_list if x in url_map]
		if len(existing_formats) == 0:
			print('ERROR: no known formats available for video')
			return
			
		video_url_list = [(existing_formats[0], url_map[existing_formats[0]])] # Best quality

	else:
		print(u'ERROR: no fmt_url_map or conn information found in video info')
		return

	for format_param, video_real_url in video_url_list:
		return video_real_url.decode('utf-8')
