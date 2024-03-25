# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler

# #################################################################################################

class HboMaxHTTPRequestHandler(DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(HboMaxHTTPRequestHandler, self).__init__(content_provider, addon, proxy_segments=False)

	def handle_mpd_manifest(self, base_url, root, bandwidth, drm=None, cache_key=None):
		# let's do processing by default manifest handler
		super(HboMaxHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, drm, cache_key)

		# extract namespace of root element and set it as global namespace
		ns = root.tag[1:root.tag.index('}')]
		ns = '{%s}' % ns

		video_codec = self.cp.get_setting('video_codec')
		# keep only one adaption set for video - player doesn't support smooth streaming
		for e_period in root.findall('{}Period'.format(ns)):
			e_adaptation_list = []
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if e_adaptation_set.get('contentType','') == 'video' or e_adaptation_set.get('mimeType','').startswith('video/'):
					e_adaptation_list.append(e_adaptation_set)

			e_adaptation_list.sort(key=lambda x: (int(x.get('maxHeight')), x.find('{}Representation'.format(ns)).get('codecs').startswith(video_codec),), reverse=True)
			for child2 in e_adaptation_list[1:]:
				e_period.remove(child2)

