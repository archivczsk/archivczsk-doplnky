# -*- coding: utf-8 -*-

from tools_archivczsk.http_handler.dash import DashHTTPRequestHandler
import xml.etree.ElementTree as ET

# #################################################################################################

class WBDMaxHTTPRequestHandler(DashHTTPRequestHandler):
	def __init__(self, content_provider, addon ):
		super(WBDMaxHTTPRequestHandler, self).__init__(content_provider, addon, proxy_segments=False)

	# #################################################################################################

	def handle_mpd_manifest(self, base_url, root, bandwidth, dash_info={}, cache_key=None):
		prefer_ac3 = self.cp.get_setting('enable_ac3')
		enabled_subs = self.cp.get_setting('enabled_subs')
		enabled_audios = self.cp.get_setting('enabled_audios')
		prefered_langs = self.cp.dubbed_lang_list

		enabled_subs = [ s.strip() for s in enabled_subs.split(',') ]
		enabled_audios = [ s.strip() for s in enabled_audios.split(',') ]

		ns = root.tag[1:root.tag.index('}')]
		ns = '{%s}' % ns

		# remove all periods without content encryption
		# keep only first period with encryption - remove all others

		periods = list(root.findall('{}Period'.format(ns)))
		multiperiod_manifest = len(periods) > 1

		if multiperiod_manifest:
			remove_period = False

			for e_period in periods:
				cenc_found = False
				for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
					if cenc_found == False:
						for e_content_protection in e_adaptation_set.findall('{}ContentProtection'.format(ns)):
							if e_content_protection.get('schemeIdUri') == 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed':
								cenc_found = True
								break

				if remove_period or cenc_found == False:
					root.remove(e_period)
				else:
					remove_period = True
					# remove start and duration - they are wrong because all other periods are removed
					if 'start' in e_period.attrib:
						del e_period.attrib['start']

					if 'duration' in e_period.attrib:
						del e_period.attrib['duration']

		if root.get('type') == 'dynamic':
			if root.get('suggestedPresentationDelay') != None:
				root.set('minBufferTime', root.get('suggestedPresentationDelay'))

		# let's do processing by default manifest handler
		super(WBDMaxHTTPRequestHandler, self).handle_mpd_manifest(base_url, root, bandwidth, dash_info, cache_key)

		# prefer h264, because exteplayer3 has problem with seeking in encrypted h265 and sometimes returns corrupted data
		video_codec = 'avc1' #self.cp.get_setting('video_codec')

		# keep only one adaption set for video - player doesn't support smooth streaming
		for e_period in root.findall('{}Period'.format(ns)):
			e_adaptation_list = []
			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if e_adaptation_set.get('contentType','') == 'video' or e_adaptation_set.get('mimeType','').startswith('video/'):
					e_adaptation_list.append(e_adaptation_set)

			e_adaptation_list.sort(key=lambda x: (int(x.get('maxHeight', x.find('{}Representation'.format(ns)).get('height'))), x.find('{}Representation'.format(ns)).get('codecs').startswith(video_codec),), reverse=True)
			for child2 in e_adaptation_list[1:]:
				e_period.remove(child2)


		# fix subtitles - replace splitted subtitles by period for the complete one
		# select audio track based on addon setting (aac vs ac3)
		for e_period in root.findall('{}Period'.format(ns)):
			e_adaptation_set_rem = []
			e_adaptation_set_audio = []
			e_adaptation_set_subtitles = []

			for e_adaptation_set in e_period.findall('{}AdaptationSet'.format(ns)):
				if e_adaptation_set.get('contentType','') not in ("audio", "text"):
					continue

				# append for removal - usable subtitles and audio will be added again at then end in the corrected order
				e_adaptation_set_rem.append(e_adaptation_set)

				if e_adaptation_set.get('contentType','') == "audio":
					e_adaptation_set_audio.append(e_adaptation_set)
					continue

				# correct subtitles
				lang = e_adaptation_set.get('lang','')
				# normalise lang code
				e_adaptation_set.set('lang', lang.split('-')[0].lower())

				subtitle_type = None

				for e_role in e_adaptation_set.findall('{}Role'.format(ns)):
					if e_role.get('schemeIdUri','') == "urn:mpeg:dash:role:2011":
						value = e_role.get('value')
						if value == 'subtitle':
							subtitle_type = 'sub'
						elif value == 'forced-subtitle':
							subtitle_type = 'forced'
						break

				if subtitle_type != None:
					# known/supported subtitle type
					if len(enabled_subs) == 0 or e_adaptation_set.get('lang') in enabled_subs:
						e_adaptation_set_subtitles.append( (e_adaptation_set, subtitle_type == 'forced',) )

					# create path to full (not splitted) subtitle file
					for e_representation in e_adaptation_set.findall('{}Representation'.format(ns)):
						segment_template_list = list(e_representation.findall('{}SegmentTemplate'.format(ns)))

						if not segment_template_list:
							continue

						for e_segment_template in segment_template_list:
							stub = e_segment_template.get('media','').split('/')[1]
							e_representation.remove(e_segment_template)

						ET.SubElement(e_representation, 'BaseURL').text = 't/{stub}/{lang}_{type}.vtt'.format(stub='sub' if stub.startswith('t') else stub, lang=lang, type=subtitle_type)

			# remove not needed adaptation sets
			for child in e_adaptation_set_rem:
				e_period.remove(child)

			# process audio tracks
			audio_by_lang = {}
			for child in e_adaptation_set_audio:
				if child.find('{}Accessibility'.format(ns)) != None:
					# ignore audio track with Accessibility defined (like some kind of audio description)
					continue

				lang = child.get('lang', '')
				if lang:
					# normalise lang code
					lang = lang.split('-')[0].lower()
					child.set('lang', lang)

				if lang not in audio_by_lang:
					audio_by_lang[lang] = { 'ac3': [], 'aac': [] }

				for child2 in child.findall('{}Representation'.format(ns)):
					if child2.get('codecs', '') == 'ec-3':
						audio_by_lang[lang]['ac3'].append(child)
					else:
						audio_by_lang[lang]['aac'].append(child)

			new_audios = []
			for lang, audio_adaptation_sets in audio_by_lang.items():
				if prefer_ac3:
					new_audios.extend(audio_adaptation_sets['ac3'] or audio_adaptation_sets['aac'])
				else:
					new_audios.extend(audio_adaptation_sets['aac'] or audio_adaptation_sets['ac3'])

			if len(enabled_audios) > 0:
				# if there are audio tracks from enabled audios, then keep only this - otherwise keep all
				self.cp.log_debug("Number of audio tracks before filtering: %d" % len(new_audios))

				new_audios_filtered = list(filter(lambda x: x.get('lang') in enabled_audios, new_audios ))
				if len(new_audios_filtered) > 0:
					self.cp.log_debug("Number of audio tracks after filtering: %d" % len(new_audios_filtered))
					new_audios = new_audios_filtered
				else:
					self.cp.log_info("No audio track meets audio preference - keeping all")

			# sort audio tracks - move tracks in prefered langs to the top
			new_audios.sort(key=lambda x: x.get('lang') not in prefered_langs)
			e_period.extend(new_audios)

			# process subtitles
			# sort subtitles by forced, prefered and lang
			def sub_cmp(sub):
				forced = sub[1]
				lng = sub[0].get('lang')

				return (lng not in prefered_langs, lng, not forced,)

			e_adaptation_set_subtitles.sort(key=sub_cmp)
			for child in e_adaptation_set_subtitles:
				e_period.append(child[0])

	# #################################################################################################
