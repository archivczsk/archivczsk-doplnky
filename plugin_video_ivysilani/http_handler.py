# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.hls import HlsHTTPRequestHandler
from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
from xml.etree import ElementTree as ET

# #################################################################################################

class iVysilaniHTTPRequestHandler(HlsHTTPRequestHandler, DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(iVysilaniHTTPRequestHandler, self).__init__(content_provider, addon)
		self.hls_proxy_variants = False
		self.hls_proxy_segments = False
		self.dash_proxy_segments = False
		self.dash_internal_decrypt = True
		self.enable_hls_multiaudio = property(lambda self: self.cp.get_setting('hls_multiaudio') == True)

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		# let's do processing by default manifest handler
		super(iVysilaniHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		subs = dash_info.get('subs')

		if subs and self.cp.get_setting('subtitles') == 'embedded':
			# add subtitles to dash manifest

			ns = root.tag[1:root.tag.index('}')]
			ns = '{%s}' % ns

			# add new adaptation set with subtitles
			for e_period in root.findall('{}Period'.format(ns)):
				e_adaptation_set = ET.SubElement(e_period, 'AdaptationSet', {'id': '462248', 'segmentAlignment': 'true', 'lang': 'cs', 'contentType': 'text'})
				ET.SubElement(e_adaptation_set, 'Role', {'schemeIdUri': 'urn:mpeg:dash:role:2011', 'value': 'subtitle'})

				e_representation = ET.SubElement(e_adaptation_set, 'Representation', {'mimeType': "text/vtt", 'bandwidth': "13", 'id': "t11"})
				ET.SubElement(e_representation, 'BaseURL').text = subs

	# #################################################################################################
