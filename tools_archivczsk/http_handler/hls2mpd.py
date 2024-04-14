# -*- coding: utf-8 -*-

import re
from collections import OrderedDict
import requests
import xml.etree.ElementTree as ET

try:
	from urllib import quote, unquote
	from urlparse import urljoin
except:
	from urllib.parse import urljoin, quote, unquote

def parse_attributes(line):
	attr = OrderedDict()
	for a in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', line):
		s = a.split('=')
		value = '='.join(s[1:])
		if value.startswith('"'):
			value = value[1:-1]
		attr[s[0]] = value

	return attr

# ##################################################################################################################

class Segment(object):
	def __init__(self, duration, url):
		self.duration = duration
		self.url = url

# ##################################################################################################################

class Playlist(object):
	def __init__(self, playlist_url, attrs={}):
		self.playlist_url = playlist_url
		self.initialization = None
		self.attrs = attrs
		self.segments = []
		self.duration = 0.0
		self.pssh = []

	def has_segments(self):
		return len(self.segments) > 0

	def get(self, name, default=None):
		return self.attrs.get(name, default)

	def group(self):
		return self.attrs.get("GROUP-ID")

	def parse_attributes(self, line):
		return parse_attributes(line)

	def process_drm_attributes(self, attrs):
		if attrs.get('KEYFORMAT','').lower() == 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed':
			# wv drm data
			pssh = attrs.get('URI','')
			if pssh.startswith('data:text/plain;base64,'):
				self.pssh.append(pssh[23:])

	def load_segments(self, data):
		duration = 0.0
		for line in iter(data.splitlines()):
			if not line.strip():
				continue

			if not line.startswith('#'):
				s = Segment(duration, line)
				self.segments.append(s)
				self.duration += duration
			elif line.startswith('#EXTINF:'):
				duration = float(line[8:].split(',')[0])
			elif line.startswith('#EXT-X-KEY:'):
				attrs = self.parse_attributes(line[11:])
				self.process_drm_attributes(attrs)
			elif line.startswith('#EXT-X-MAP:'):
				attrs = self.parse_attributes(line[11:])
				self.initialization = attrs.get("URI")

# ##################################################################################################################

class Hls2Mpd(object):
	def __init__(self):
		self.video_playlists = []
		self.audio_playlists = []
		self.subtitles_playlists = []

	# ##################################################################################################################

	def load_http_data(self, url):
		return requests.get(url).text

	# ##################################################################################################################

	def parse_attributes(self, line):
		return parse_attributes(line)

	# ##################################################################################################################

	def add_video_playlist(self, playlist_url, attrs):
		p = Playlist(playlist_url, attrs)
		self.video_playlists.append(p)

	# ##################################################################################################################

	def add_media_playlist(self, attrs, master_playlist_url):
		url = urljoin(master_playlist_url, attrs['URI'])
		playlist_type = attrs.get('TYPE')

		if playlist_type == 'AUDIO':
			p = Playlist(url, attrs)
			self.audio_playlists.append(p)
		elif playlist_type == 'SUBTITLES':
			p = Playlist(url, attrs)
			self.subtitles_playlists.append(p)

	# ##################################################################################################################

	def process_master_playlist(self, playlist_url, playlist_data ):
		attrs = {}
		for line in iter(playlist_data.splitlines()):
			if not line.strip():
				continue

			if not line.startswith('#'):
				url = urljoin(playlist_url, line)
				self.add_video_playlist(url, attrs)
				attrs = {}
			elif line.startswith('#EXT-X-STREAM-INF:'):
				attrs = self.parse_attributes(line[18:])
			elif line.startswith('#EXT-X-MEDIA:'):
				self.add_media_playlist(self.parse_attributes(line[13:]), playlist_url)

	# ##################################################################################################################

	def load_media_playlists(self):
		audio_load = []
		subtitles_load = []
		for vp in self.video_playlists:
			vp_data = self.load_http_data(vp.playlist_url)
			vp.load_segments(vp_data)
			a = vp.get('AUDIO')
			if a not in audio_load:
				audio_load.append(a)

			s = vp.get('SUBTITLES')
			if s not in subtitles_load:
				subtitles_load.append(s)

		for p in self.audio_playlists:
			if p.group() in audio_load:
				if p.get('LANGUAGE','en').split('-')[0].lower() in ('sk', 'cs', 'en'):
					ap_data = self.load_http_data(p.playlist_url)
					p.load_segments(ap_data)

		for p in self.subtitles_playlists:
			if p.group() in subtitles_load:
				if p.get('LANGUAGE','en').split('-')[0].lower() in ('sk', 'cs'):
					sp_data = self.load_http_data(p.playlist_url)
					p.load_segments(sp_data)

	# ##################################################################################################################

	def build_mpd(self):
		def fill_segments(e, p):
			TIMESCALE=1000000
			ET.SubElement(e, 'BaseURL').text = urljoin(p.playlist_url, '.')
			e = ET.SubElement(e, 'SegmentList', {
				'timescale': '%d' % TIMESCALE,
				'startNumber': "0",
			})

			if p.initialization:
				ET.SubElement(e, 'Initialization', {
					'sourceURL': p.initialization
				})

			st = ET.SubElement(e, 'SegmentTimeline')

			max_duration = 0.0
			for i, segment in enumerate(p.segments):
				if i == 0:
					ET.SubElement(st, 'S',{
						't': '0',
						'd': '%s' % int(segment.duration * TIMESCALE)
					})
				else:
					ET.SubElement(st, 'S',{
						'd': '%s' % int(segment.duration * TIMESCALE)
					})

				ET.SubElement(e, 'SegmentURL',{
					'media': segment.url,
#					'duration': '%d' % int(segment.duration * TIMESCALE)
				})
				if segment.duration > max_duration:
					max_duration = segment.duration

			e.set('duration', '%d' % int(max_duration * TIMESCALE))


		root = ET.Element('MPD', {
			'xmlns': "urn:mpeg:dash:schema:mpd:2011",
			'xmlns:cenc': "urn:mpeg:cenc:2013",
			'minBufferTime': "PT2S",
#			"mediaPresentationDuration": "PT1H40M46S", # this will be filled later, because it is required
			'type': "static",
			'profiles': "urn:mpeg:dash:profile:isoff-main:2011"
		})

		e_period = ET.SubElement(root, 'Period', {'id': '0', 'start': "PT0S"})

		for i, p in enumerate(self.audio_playlists):
			if not p.has_segments():
				continue

			e = ET.SubElement(e_period, 'AdaptationSet', {
				'subsegmentAlignment': "true",
				'subsegmentStartsWithSAP': "1",
				'id': 'as' + str(i),
				'lang': p.get('LANGUAGE', 'en-US'),
				'contentType': "audio"
			})
			e = ET.SubElement(e, 'Representation',{
				'mimeType': "audio/mp4",
				'id': 'a%d' % i,
			})
			if len(p.pssh) > 0:
				keys = self.get_drm_keys(p.pssh)
				if keys:
					e.set('cenc_decryption_keys', ':'.join(k.replace(':','=') for k in keys))

			fill_segments(e, p)

		max_duration = 0
		for i, p in enumerate(self.video_playlists):
			if not p.has_segments():
				continue

			e = ET.SubElement(e_period, 'AdaptationSet', {
				'subsegmentAlignment': "true",
				'subsegmentStartsWithSAP': "1",
				'id': 'vs' + str(i),
				'contentType': "video"
			})
			e = ET.SubElement(e, 'Representation',{
				'mimeType': "video/mp4",
				'id': 'v%d' % i,
			})
			if len(p.pssh) > 0:
				keys = self.get_drm_keys(p.pssh)
				if keys:
					e.set('cenc_decryption_keys', ':'.join(k.replace(':','=') for k in keys))
			fill_segments(e, p)

			if p.duration > max_duration:
				max_duration = p.duration

		for i, p in enumerate(self.subtitles_playlists):
			if not p.has_segments():
				continue

			e = ET.SubElement(e_period, 'AdaptationSet', {
				'subsegmentAlignment': "true",
				'subsegmentStartsWithSAP': "1",
				'id': 'ss' + str(i),
				'lang': p.get('LANGUAGE', 'en-US'),
				'contentType': "text"
			})
			ET.SubElement(e, 'Role', {
				'schemeIdUri': "urn:mpeg:dash:role:2011",
				'value': "subtitle"
			})
			e = ET.SubElement(e, 'Representation',{
				'mimeType': "text/vtt",
				'id': 's%d' % i,
			})
			fill_segments(e, p)

		duration_str = 'PT%dH%dM%dS' % ((max_duration // 3600), (max_duration //60) % 60, max_duration % 60)
		root.set('mediaPresentationDuration', duration_str)
		return root

	# ##################################################################################################################

	def run(self, mp_url, mp_data=None):
		if not mp_data:
			mp_data = self.load_http_data(mp_url)
		self.process_master_playlist(mp_url, mp_data)

		# filter out not needed data from master playlist in order to speed up all another operations
		self.filter_master_playlist()

		self.load_media_playlists()
		return self.build_mpd()

	# ##################################################################################################################

	def filter_master_playlist(self):
		# just simple default filter that gets the best stream by bandwidth
		playlists = self.video_playlists
		playlists = sorted(playlists, key=lambda p: int(p.get('BANDWIDTH',0)), reverse=True)
		self.video_playlists = [playlists[0]]

	# ##################################################################################################################

	def get_drm_keys(self, pssh):
		# you need to implement this if you want DRM support
		return None

	# ##################################################################################################################
