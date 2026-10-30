# -*- coding: utf-8 -*-
# Subtitles (closed captions) for YouTube videos: track selection, YouTube auto-translation and SRT conversion

import re

try:
	from html import unescape as _unescape
except ImportError:  # python2
	from HTMLParser import HTMLParser
	_unescape = HTMLParser().unescape


def _lang_code(code):
	return (code or '').split('.')[0].split('-')[0].split('_')[0].lower()


def _lang(track):
	return _lang_code(track.get('languageCode'))


def original_language(player_response):
	'''
	Language of the original (not AI dubbed) audio track of the video or None.
	YouTube adds automatic subtitles for every AI dubbed audio track too, so automatic subtitles
	don't tell the spoken language anymore.
	'''
	formats = (player_response.get('streamingData') or {}).get('adaptiveFormats') or []
	dubbed = set()
	for fmt in formats:
		audio_track = fmt.get('audioTrack')
		if not audio_track:
			continue
		raw_url = (fmt.get('url') or fmt.get('signatureCipher') or '').lower()
		if audio_track.get('isAutoDubbed') or re.search(r'acont(?:=|%3d|%253d)dubbed', raw_url):
			dubbed.add(audio_track.get('id'))
			continue
		if re.search(r'acont(?:=|%3d|%253d)original', raw_url) or 'original' in (audio_track.get('displayName') or '').lower():
			return _lang_code(audio_track.get('id'))

	renderer = (player_response.get('captions') or {}).get('playerCaptionsTracklistRenderer') or {}
	audio_tracks = renderer.get('audioTracks') or []
	idx = renderer.get('defaultAudioTrackIndex')
	if isinstance(idx, int) and 0 <= idx < len(audio_tracks):
		track_id = audio_tracks[idx].get('audioTrackId')
		if track_id and track_id not in dubbed and len(audio_tracks) > 1:
			return _lang_code(track_id)

	return None


def _find(tracks, lang):
	for track in tracks:
		if _lang(track) == lang:
			return track
	return None


def _track_url(track, tlang=None):
	url = re.sub(r'&fmt=[^&]*', '', track['baseUrl']) + '&fmt=srv1'
	if tlang:
		url += '&tlang=' + tlang
	return url


def choose_track_url(tracks, mode, lang='en', translate=True, orig_lang=None):
	"""
	tracks - captionTracks from YouTube player response
	orig_lang - language of the original audio track (see original_language()), if known
	mode 'lang' - subtitles in language lang: own subtitles first, otherwise YouTube translation of original subtitles
	mode 'orig' - subtitles in original language of the video (human made preferred over automatic)
	Returns tuple (url, description) or (None, None)
	"""
	tracks = [t for t in (tracks or []) if t.get('baseUrl')]
	if not tracks or mode not in ('lang', 'orig'):
		return None, None

	asr = [t for t in tracks if t.get('kind') == 'asr']
	manual = [t for t in tracks if t.get('kind') != 'asr']

	if not orig_lang:
		asr_langs = []
		for t in asr:
			if _lang(t) not in asr_langs:
				asr_langs.append(_lang(t))
		if len(asr_langs) == 1:
			# without AI dubbing automatic subtitles exist only in the spoken language
			orig_lang = asr_langs[0]
		elif manual:
			orig_lang = _lang(manual[0])
		elif 'en' in asr_langs:
			orig_lang = 'en'
		else:
			orig_lang = asr_langs[0]

	orig = _find(manual, orig_lang) or _find(asr, orig_lang) or (manual[0] if manual else asr[0])

	if mode == 'orig':
		return _track_url(orig), orig_lang

	# mode == 'lang'
	own = _find(manual, lang) or _find(asr, lang)
	if own:
		return _track_url(own), lang

	if translate:
		for source in [orig] + manual + asr:
			if source.get('isTranslatable', True):
				return _track_url(source, lang), '%s->%s' % (_lang(source), lang)

	return None, None


def _srt_time(seconds):
	ms = int(round(seconds * 1000))
	h, ms = divmod(ms, 3600000)
	m, ms = divmod(ms, 60000)
	s, ms = divmod(ms, 1000)
	return '%02d:%02d:%02d,%03d' % (h, m, s, ms)


def srv1_to_cues(xml):
	""" Parses YouTube timedtext 'srv1' XML to list of (begin, end, text) """
	items = re.findall(r'<text\s+start="([\d.]+)"(?:\s+dur="([\d.]+)")?[^>]*>(.*?)</text>', xml, re.S)
	cues = []
	for i, (start, dur, text) in enumerate(items):
		begin = float(start)
		end = begin + float(dur or 3)
		if i + 1 < len(items):
			# automatic subtitles overlap - show only one line at a time
			end = min(end, float(items[i + 1][0]))
		if end - begin < 0.3:
			continue
		# YouTube escapes the text twice (&amp;#39;)
		text = _unescape(_unescape(text))
		text = re.sub(r'<[^>]+>', '', text)
		# '>>' marks change of speaker in automatic subtitles
		text = re.sub(r'(^|\n)\s*>>\s*', r'\1', text).strip()
		if not text:
			continue
		cues.append((begin, end, text))
	return cues


def add_note(cues, note, duration):
	"""
	Shows note (for example about machine translation) at the start of the video without overlapping subtitles.
	If the first subtitle starts too early, the note is shown together with it.
	"""
	if not note:
		return cues
	if not cues or cues[0][0] >= 3:
		end = min(duration, cues[0][0]) if cues else duration
		return [(0.0, end, note)] + list(cues)
	begin, end, text = cues[0]
	return [(begin, max(end, min(duration, cues[1][0] if len(cues) > 1 else duration)), note + '\n' + text)] + list(cues[1:])


def cues_to_srt(cues):
	out = []
	for idx, (begin, end, text) in enumerate(cues, 1):
		out.append('%d\n%s --> %s\n%s\n' % (idx, _srt_time(begin), _srt_time(end), text))
	return '\n'.join(out)


def srv1_to_srt(xml):
	""" Converts YouTube timedtext 'srv1' XML to SRT """
	return cues_to_srt(srv1_to_cues(xml))


def download_srt(session, url, filename, timeout=10, note=None, note_duration=8):
	response = session.get(url, timeout=timeout)
	response.raise_for_status()
	response.encoding = 'utf-8'
	cues = srv1_to_cues(response.text)
	if not cues:
		return None
	srt = cues_to_srt(add_note(cues, note, note_duration))
	with open(filename, 'wb') as f:
		f.write(srt.encode('utf-8'))
	return filename
