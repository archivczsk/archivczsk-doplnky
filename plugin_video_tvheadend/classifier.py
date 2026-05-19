# -*- coding: utf-8 -*-
"""
DVR archive classifier — extracted from provider.py for maintainability
(FIX 0.57.0, skyjet PR #22 review #4).

Klasifikuje TVH DVR nahrávky do kategórií (Filmy / Seriály / Spravodajstvo /
Šou / Šport / Detské / Hudba / Umenie / Dokumenty / Hobby / Nezaradené)
a sub-kategórií (Akčné / Krimi / Dráma / Sci-fi / atď.) pomocou:

1. Channel-based hints (CT :D = detské, Sport = šport, ...)
2. DVB-SI Level 1 content_type → category mapping
3. Title corpus lookup (~1945 hand-curated titles z JSON)
4. Keyword regex fallback v title/subtitle/description
5. IMDb GraphQL lookup (optional, 0.54beta+) — opt-in cez settings

Public API (volá sa z provider.py):
  - _classify_dvr_entry(entry) → (top_cat_id, sub_cat_id_or_None)
  - _determine_top_cat(entry) → top_cat_id
  - _movie_subgenre(entry) → mv_* sub-cat ID
  - _classify_all(entries) → (entries_by_top, entries_by_subcat, counts,
                              series_by_canonical, series_subcat_titles)
  - _CAT_LABELS_ORDER, _MV_LABELS_ORDER — display labels (SK strings)
  - Konstanty: _CAT_FILM, _CAT_SERIAL, ..., _MV_AKCNY, _MV_DRAMA, ...

Kompatibilita: Python 2.7 + Python 3.x. Žiadne f-strings, walrus, type hints.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os
import io
import json
import time

from tools_archivczsk.string_utils import strip_accents as _strip_accents_compat

# FIX 0.57.0: callback-based logging cez framework cp.log_info(). Provider
# nastaví callback pri __init__-e. Bez nastaveného callback-u (test mode)
# log entries sú silenced.
_LOG_CALLBACK = None

def set_log_callback(callback):
	"""Nastaviť log callback. Volá sa raz pri provider init."""
	global _LOG_CALLBACK
	_LOG_CALLBACK = callback if callable(callback) else None

def _log(msg):
	"""Log info-level message cez framework callback (ide do archivCZSK.log).
	Silent ak callback nie je nastavený."""
	try:
		if _LOG_CALLBACK is not None:
			_LOG_CALLBACK('[Tvheadend.classifier] ' + str(msg))
	except Exception:
		pass

# Lazy IMDb lookup - imported on demand v _classify_dvr_entry() aby sa nevykonal
# import pri load-e classifier-a (modul je opt-in cez online_metadata_lookup setting).

import re as _re_dvr  # alias aby sa neprenášal _re v iných miestach
import unicodedata as _unicodedata_dvr


# FIX 0.57.0: lokálna kópia _ts() helper-a — predtým importovaný z provider.py,
# čo by vytvorilo cyclical import. _ts je trivial timestamp extractor pre DVR entry.
def _ts(e):
	try:
		return int(e.get('start_real') or e.get('start') or 0)
	except Exception:
		return 0




# FIX 0.49d: Helper na strippe diakritiky a lower-case textu pred regex match.
# Slovenské/české keyword matching by inak failovalo na "spr[á]vy" vs "sprav"
# (a vs á sú rôzne znaky aj s IGNORECASE flagom). Riešenie: pre matching
# si text aj keywords ponechávame bez diakritiky. Pridanie diakritiky v
# keywordoch (každý znak ako alternácia [aá]) by zložitosť regexov výrazne
# zhoršilo. Strippe je O(n) a O(15µs) per call — zanedbateľné.
def _strip_accents_lower(s):
	"""Vráti text bez diakritiky a v lowercase. Pre regex match."""
	if not s:
		return ''
	# NFD: 'á' → 'a' + combining acute
	nfd = _unicodedata_dvr.normalize('NFD', s)
	# Filter combining marks (category Mn = Mark, nonspacing)
	stripped = ''.join(c for c in nfd if _unicodedata_dvr.category(c) != 'Mn')
	return stripped.lower()


# --------------------------------------------------------------------------
# Regex patterns
# --------------------------------------------------------------------------
# "25/31 ..." v subtitle (CT/Nova OLD formát)
_SUBTITLE_SERIES_PATTERN = _re_dvr.compile(r'^\s*\d+/\d+\b')

# "(N)" alebo "(N) (XX)" na konci title — N je 1-9999 (epizoda alebo rok)
_TITLE_EPISODE_PATTERN = _re_dvr.compile(
	r'\((\d{1,4})\)\s*(?:\([A-Z]{1,3}\))?\s*$'
)

# Single tech/audio/subtitle marker — rozšír ak narazíš na ďalší.
# Pozn.: DTS-HD musí byť pred DTS aby alternace zachytila dlhšiu variantu.
_TECH_MARKER = (
	r'(?:DD5\.1|DTS-HD|DTS-MA|UHD|DTS|5\.1|7\.1|ST|HD|AD|SS|3D|DD|TT|P)'
)
# FIX 0.56beta (backport Kodi 1.0.2 fix): parens s 1+ tech markermi v
# jednej zátvorke, oddelenými čiarkou alebo lomkou (s alebo bez whitespace).
# Predtým regex match-oval len single token v zátvorke — kombinácie ako
# "(AD,ST)" alebo "(HD, DD5.1)" nezachytil, ich rozdielne stripping
# narúšalo episode grouping (rovnaký seriál s rôznymi tech flagmi
# končil ako separate "samostatné" entries vedľa hlavnej skupiny).
# Rieši napr.: "(AD,ST)", "(HD, DD5.1)", "(AD/ST)", "(AD, ST, HD)".
_TECH_MARKER_PATTERN = _re_dvr.compile(
	r'\s*\(\s*' + _TECH_MARKER +
	r'(?:\s*[,/]\s*' + _TECH_MARKER + r')*\s*\)\s*',
	_re_dvr.IGNORECASE
)


def _strip_tech_markers(text):
	"""Odstráni '(ST)', '(HD)', '(AD)', '(AD,ST)', '(HD, DD5.1)' atď. z textu."""
	if not text:
		return ''
	return _TECH_MARKER_PATTERN.sub(' ', text).strip()


def _has_episode_suffix(title):
	"""True ak title končí '(N)' a N je epizoda (nie rok 1900-2099)."""
	clean = _strip_tech_markers(title)
	m = _TITLE_EPISODE_PATTERN.search(clean)
	if not m:
		return False
	try:
		n = int(m.group(1))
	except (ValueError, TypeError):
		return False
	# Rok výroby filmu (typicky 1900-2099) → toto nie je epizoda
	if 1900 <= n <= 2099:
		return False
	# Inak (1-1899, 2100+) → epizoda
	if 1 <= n <= 9999:
		return True
	return False


def _series_canonical_title(title):
	"""Strip episode suffix + tech markers — aby sa epizódy toho istého seriálu
	dali grupovať pod jeden názov.

	"Otec Brown IV (1)"   → "Otec Brown IV"
	"Otec Brown IV (2)"   → "Otec Brown IV"
	"Cesty domů II (31) (ST)" → "Cesty domů II"
	"Casablanca (1942)"   → "Casablanca (1942)"  (rok, nie epizoda)
	"""
	if not title:
		return ''
	clean = _strip_tech_markers(title).strip()
	m = _TITLE_EPISODE_PATTERN.search(clean)
	if m:
		try:
			n = int(m.group(1))
			# Strip iba ak N NIE JE rok výroby
			if not (1900 <= n <= 2099):
				clean = clean[:m.start()].strip()
		except (ValueError, TypeError):
			pass
	return clean


# --------------------------------------------------------------------------
# Top-level kategórie
# --------------------------------------------------------------------------
_CAT_FILM           = 'film'
_CAT_SERIAL         = 'serial'
_CAT_SPRAVODAJSTVO  = 'spravodajstvo'
_CAT_SHOW           = 'show'
_CAT_SPORT          = 'sport'
_CAT_DETSKE         = 'detske'
_CAT_HUDBA          = 'hudba'
_CAT_UMENIE         = 'umenie'
_CAT_DOKUMENTY      = 'dokumenty'
_CAT_HOBBY          = 'hobby'
_CAT_INE            = 'ine'

# DVB EIT content_type (top nibble) → naša kategória.
_CT_TO_CAT_BASE = {
	2:  _CAT_SPRAVODAJSTVO,
	3:  _CAT_SHOW,
	4:  _CAT_SPORT,
	5:  _CAT_DETSKE,
	6:  _CAT_HUDBA,
	7:  _CAT_UMENIE,
	8:  _CAT_SHOW,            # Social/Political magazíny → spojené so Show
	9:  _CAT_DOKUMENTY,
	10: _CAT_HOBBY,
	# 0, 1, 11 sa riešia inde:
	#   1  = film vs seriál heuristika
	#   0, 11 = keyword fallback
}

# Poradie a slovenské label-y. FIX 0.49b: bez počtu (užívateľ chcel počty preč)
_CAT_LABELS_ORDER = (
	(_CAT_FILM,           'Movies'),
	(_CAT_SERIAL,         'Series'),
	(_CAT_SPORT,          'Sport'),
	(_CAT_SPRAVODAJSTVO,  'News'),
	(_CAT_SHOW,           'Shows / Entertainment'),
	(_CAT_DETSKE,         'Children'),
	(_CAT_HUDBA,          'Music'),
	(_CAT_UMENIE,         'Arts / Culture'),
	(_CAT_DOKUMENTY,      'Documentaries / Educational'),
	(_CAT_HOBBY,          'Leisure / Hobby'),
	(_CAT_INE,            'Uncategorized'),
)


# --------------------------------------------------------------------------
# Podžánre (sub-categories) pre Filmy a Seriály
# --------------------------------------------------------------------------
_MV_AKCNY       = 'mv_akcny'
_MV_DRAMA       = 'mv_drama'
_MV_KOMEDIA     = 'mv_komedia'
_MV_KRIMI       = 'mv_krimi'
_MV_SCIFI       = 'mv_scifi'
_MV_ROMANTIKA   = 'mv_romantika'
_MV_HOROR       = 'mv_horor'
_MV_DOBRODR     = 'mv_dobrodruzny'
_MV_ANIMAK      = 'mv_animovany'
_MV_HISTORICKY  = 'mv_historicky'
_MV_WESTERN     = 'mv_western'
_MV_INE         = 'mv_ine'

_MOVIE_SUBCAT_LABELS = (
	(_MV_AKCNY,      'Action'),
	(_MV_KOMEDIA,    'Comedy'),
	(_MV_KRIMI,      'Crime / Thriller / Detective'),
	(_MV_DRAMA,      'Drama'),
	(_MV_SCIFI,      'Sci-fi / Fantasy'),
	(_MV_ROMANTIKA,  'Romance'),
	(_MV_HOROR,      'Horror'),
	(_MV_DOBRODR,    'Adventure'),
	(_MV_ANIMAK,     'Animation'),
	(_MV_HISTORICKY, 'Historical / War'),
	(_MV_WESTERN,    'Western'),
	(_MV_INE,        'Other'),
)

# DVB genre byte → sub-kategória (ak je dostupný v entry.genre)
_DVB_GENRE_TO_SUBCAT = {
	# 0x10 (16) = Movie/drama general — bez ďalšieho upresnenia → keyword fallback
	0x11: _MV_KRIMI,       # Detective/Thriller
	0x12: _MV_DOBRODR,     # Adventure/Western/War
	0x13: _MV_SCIFI,       # SF/Fantasy/Horror
	0x14: _MV_KOMEDIA,     # Comedy
	0x15: _MV_DRAMA,       # Soap/Melodrama/Folkloric
	0x16: _MV_ROMANTIKA,   # Romance
	0x17: _MV_HISTORICKY,  # Serious/Classical/Historical
	0x18: _MV_DRAMA,       # Adult — drama
}

# DVB Level 2 nibble decoding (FIX 0.53beta — z Kodi 1.0.4 portu).
# Keď je dostupný full 8-bit DVB genre kód (cca 6.5% entries), Level 2
# nibble priamo určuje sub-kategóriu pre non-film/serial kategórie —
# šport (0x40-0x4b), hudba (0x60-0x6b), arts (0x70-0x7b), dokumenty
# (0x90-0x9f), hobby (0xa0-0xaf). Funkcie _dvb_l2_sport_subgenre atď.
# použijú tieto mappingy pred keyword fallback-om (riešené v subgenre_fn
# pre každú kategóriu).

# Keyword regex → sub-kategória. PORADIE má význam: high-specificity first
# (krimi pred drama atď.).
# FIX 0.49d: keywords sú bez diakritiky a lowercase — match sa robí proti
# strippnutemu textu (cez _strip_accents_lower). re.IGNORECASE flag tým
# pádom nepotrebujeme.
# Horror keyword pattern — checkuje SAMOSTATNE proti title (FIX 0.53beta).
# Predtým bol horor v _KEYWORD_TO_SUBCAT spolu s ostatnými a matchol aj v
# description ("hrůza války" → war film padol do Horor). Teraz: horor patrí
# k filmu len ak slovo "horor/horror/desiv/hruz" je v title (nie subtitle,
# nie description). Ostatné podžánre matchujú proti celému textu — sú menej
# náchylné na false positives lebo "kriminálnik" v opise znamená naozaj krimi.
_HORROR_TITLE_PATTERN = _re_dvr.compile(r'\b(horor|horror|desiv|hruz)')

# Re-ordered _KEYWORD_TO_SUBCAT bez horor patternu (presunutý hore — FIX 0.53beta).
# Tiež: specifickejšie žánre majú prednosť pred genericky horor — historické,
# krimi, sci-fi, animované first. (Anyway, horor je teraz handled separately
# in _movie_subgenre cez _HORROR_TITLE_PATTERN.)
_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(detektiv|kriminal|krimi|thriller|vraz|policajn|vysetrov)'),
	 _MV_KRIMI),
	(_re_dvr.compile(r'\b(sci-?fi|sci\.\s?fi|fantasy|vedeckofant|vesmirn|mimozem|robot|kybern)'),
	 _MV_SCIFI),
	(_re_dvr.compile(r'\b(komedi|veselohra|humor|grotesk|sitcom)'),
	 _MV_KOMEDIA),
	(_re_dvr.compile(r'\b(romantick|milostn|romant)'),
	 _MV_ROMANTIKA),
	(_re_dvr.compile(r'\b(akcn|action|honic|prestrelk)'),
	 _MV_AKCNY),
	(_re_dvr.compile(r'\b(western|kovbo)'),
	 _MV_WESTERN),
	(_re_dvr.compile(r'\b(historick|valecn|vojensk|vojnov|histori)'),
	 _MV_HISTORICKY),
	(_re_dvr.compile(r'\b(dobrodruz|adventur|exped|cestopis)'),
	 _MV_DOBRODR),
	(_re_dvr.compile(r'\b(animovan|kreslen|animak|loutkov|cartoon|anime)'),
	 _MV_ANIMAK),
	(_re_dvr.compile(r'\b(drama|dramati)'),
	 _MV_DRAMA),
)


# --------------------------------------------------------------------------
# Sport sub-kategórie (FIX 0.49c)
# --------------------------------------------------------------------------
_SP_FUTBAL      = 'sp_futbal'
_SP_HOKEJ       = 'sp_hokej'
_SP_BASKETBAL   = 'sp_basketbal'
_SP_TENIS       = 'sp_tenis'
_SP_VOLEJBAL    = 'sp_volejbal'
_SP_HADZANA     = 'sp_hadzana'
_SP_ATLETIKA    = 'sp_atletika'
_SP_CYKLISTIKA  = 'sp_cyklistika'
_SP_MOTORSPORT  = 'sp_motorsport'
_SP_BOJOVE      = 'sp_bojove'
_SP_ZIMNE       = 'sp_zimne'
_SP_VODNE       = 'sp_vodne'
_SP_NEWS        = 'sp_news'
_SP_INE         = 'sp_ine'

_SPORT_SUBCAT_LABELS = (
	(_SP_FUTBAL,      'Football'),
	(_SP_HOKEJ,       'Hockey'),
	(_SP_BASKETBAL,   'Basketball'),
	(_SP_TENIS,       'Tennis'),
	(_SP_VOLEJBAL,    'Volleyball'),
	(_SP_HADZANA,     'Handball'),
	(_SP_ATLETIKA,    'Athletics'),
	(_SP_CYKLISTIKA,  'Cycling'),
	(_SP_MOTORSPORT,  'Motorsport'),
	(_SP_BOJOVE,      'Combat sports'),
	(_SP_ZIMNE,       'Winter sports'),
	(_SP_VODNE,       'Water sports'),
	(_SP_NEWS,        'Sports news'),
	(_SP_INE,         'Other'),
)

# Keyword → sport sub-cat. PORADIE má význam:
#   - Sport news najprv (lebo "Sportovní noviny" by mohli matchovať aj iné)
#   - Pak explicitné názvy športov (Basketbal:, Volejbal:, Hádzaná:)
#   - Pak ligy a značky (UEFA, NHL, IIHF, MONACObet, ...)
#   - Najmenej špecifické na koniec
# FIX 0.49d: keywords bez diakritiky — text sa normalizuje pred match
_SPORT_KEYWORD_TO_SUBCAT = (
	# Sport news — high priority pred individual sport keywords
	(_re_dvr.compile(r'\b(sportovni\s+noviny|sportove\s+noviny|sport\s+news|'
	                 r'spravy\s+zo\s+sportu|sportovni\s+studio|sports?\s+report|'
	                 r'polední\s+sport|odpoledni\s+sport)'),
	 _SP_NEWS),
	# Hokej — IIHF, NHL, KHL, hokej, hockey, ZOH hokej
	(_re_dvr.compile(r'\b(hokej|hockey|nhl|iihf|khl|hokejov)'),
	 _SP_HOKEJ),
	# Bojové športy pred futbalom kvôli "UFC"
	(_re_dvr.compile(r'\b(ufc|mma|oktagon|pml|kickbox|k-1|judo|karate|wrestl|'
	                 r'zapas|sumo|taekwon|grappling)'),
	 _SP_BOJOVE),
	(_re_dvr.compile(r'\bbox(er|ing|u|y)?\b'),
	 _SP_BOJOVE),
	# Futbal — UEFA, MONACObet, Niké liga, Premier League, Bundesliga, La Liga
	(_re_dvr.compile(r'\b(futbal|football|uefa|monacobet|nike\s+liga|niké\s+liga|'
	                 r'tipsport\s+liga|fortuna\s+liga|premier\s+league|bundesliga|'
	                 r'la\s+liga|champion(s)?\s+league|europa\s+league|conference\s+league|'
	                 r'ligue\s+1|serie\s+a\b|el\s+uefa|cl\s+uefa)'),
	 _SP_FUTBAL),
	# Basketbal
	(_re_dvr.compile(r'\b(basketbal|basketbol|nba|euroliga\s+basketbal|sbl|wnba)'),
	 _SP_BASKETBAL),
	# Volejbal
	(_re_dvr.compile(r'\b(volejbal|volleyball)'),
	 _SP_VOLEJBAL),
	# Hádzaná
	(_re_dvr.compile(r'\b(hadzana|handball)'),
	 _SP_HADZANA),
	# Tenis
	(_re_dvr.compile(r'\b(tenis|tennis|atp|wta|wimbledon|roland\s+garros|'
	                 r'us\s+open|australian\s+open|french\s+open)'),
	 _SP_TENIS),
	# Cyklistika
	(_re_dvr.compile(r'\b(cyklist|tour\s+de\s+france|giro\s+d|vuelta)'),
	 _SP_CYKLISTIKA),
	# Motorsport
	(_re_dvr.compile(r'\b(formula|formule|f1\b|motogp|wrc|rally|nascar|'
	                 r'moto2|moto3|velka\s+cena|grand\s+prix)'),
	 _SP_MOTORSPORT),
	# Zimné športy — ZOH, lyžovanie, biatlon, snowboard, Cortina
	(_re_dvr.compile(r'\b(zoh|olympi.*zimn|zimn.*olympi|lyzov|lyziarsk|'
	                 r'biatlon|snowboard|sjazd|slalom|krasokorcul|cortina\s+2026|'
	                 r'milano\s+cortina)'),
	 _SP_ZIMNE),
	# Vodné športy
	(_re_dvr.compile(r'\b(kanoistik|plavan|plav(ec|ky)|jachting|surf|veslov|'
	                 r'kayaking|swimming|vodn[ey]\s+polo|vodne\s+slalom|'
	                 r'rychlostna\s+kanoistik)'),
	 _SP_VODNE),
	# Atletika
	(_re_dvr.compile(r'\b(atletik|atletic|athletics|maraton|marathon|'
	                 r'beh\s+na|skok\s+do|hod\s+ostepom|dialk)'),
	 _SP_ATLETIKA),
)


# FIX 0.50beta: pred 0.50 mal každý sub-žáner top kategórie (Šport,
# Spravodajstvo, Šou, Detské, Hudba, Umenie, Dokumenty, Hobby) vlastnú
# 9-riadkovú funkciu _XYZ_subgenre(entry) s úplne identickou body
# logikou (compose text → strip_accents_lower → regex iter → return).
# Celkom 9 takmer identických definícií, ~80 riadkov boilerplate-u.
# FIX 0.50beta: nahradené factory funkciou `_make_subgenre_fn(patterns,
# default)`, ktorá vráti closure s identickou semantikou. Public mená
# funkcií (_sport_subgenre, _news_subgenre, ...) ostávajú zachované —
# používame ich v _SUBCAT_REGISTRY a v UI flow.
def _make_subgenre_fn(patterns, default_subcat):
	"""Vyrobí subgenre-classifier closure pre dané keyword patterns +
	fallback subcat. Text na klasifikáciu sa skladá z disp_title +
	disp_subtitle + disp_description + channelname, normalizuje sa
	bez diakritiky a lowercase, pak iteruje cez regex patterns
	v poradí (poradie = priorita)."""
	def _classify(entry):
		text = ((entry.get('disp_title') or '') + ' ' +
		        (entry.get('disp_subtitle') or '') + ' ' +
		        (entry.get('disp_description') or '') + ' ' +
		        (entry.get('channelname') or ''))
		if not text.strip():
			return default_subcat
		text = _strip_accents_lower(text)
		for pattern, subcat in patterns:
			if pattern.search(text):
				return subcat
		return default_subcat
	return _classify


_sport_subgenre = _make_subgenre_fn(_SPORT_KEYWORD_TO_SUBCAT, _SP_INE)


# ==========================================================================
# FIX 0.49d: Podžánre pre ostatné top kategórie
# (Spravodajstvo, Šou/Relácie, Detské, Hudba, Umenie, Dokumenty, Voľný čas)
# ==========================================================================
# Pre tieto kategórie nepotrebujeme DVB genre mapovanie (nie je definované
# pre sub-žánre v týchto top-cat-och) ani channel-based hints (môžu prísť
# z hociakého kanála). Použijeme len keyword scan v title + subtitle +
# description + channelname. PORADIE keywordov má význam — specific najprv.
# ==========================================================================

# -------- Spravodajstvo (News) --------
_NW_HLAVNE      = 'nw_hlavne'        # Hlavné správy bulletinu
_NW_POLITIKA    = 'nw_politika'      # Politické diskusie, komentáre
_NW_KRIMI       = 'nw_krimi'         # Krimi noviny, investigatíva
_NW_MAGAZINY    = 'nw_magaziny'      # Spravodajské magazíny
_NW_POCASIE     = 'nw_pocasie'       # Počasie
_NW_INE         = 'nw_ine'

_NEWS_SUBCAT_LABELS = (
	(_NW_HLAVNE,    'Main news'),
	(_NW_POLITIKA,  'Politics / Discussion'),
	(_NW_KRIMI,     'Crime / Reports'),
	(_NW_MAGAZINY,  'Magazines / Lifestyle'),
	(_NW_POCASIE,   'Weather'),
	(_NW_INE,       'Other'),
)

_NEWS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(pocasi|predpoved|predpovid)'),
	 _NW_POCASIE),
	(_re_dvr.compile(r'\b(krimi\s+noviny|reporter|reportaz|investigativ|'
	                 r'tajomstv|kriminal(ne)?\s+sprav|cernin)'),
	 _NW_KRIMI),
	(_re_dvr.compile(r'\b(politik|diskusia|diskuse|debata|otazk|otazky\s+vaclava|'
	                 r'studio\s+6|o\s+5\s+minut\s+12|polemika|interview\s+plus|'
	                 r'partia|sobotne\s+dial)'),
	 _NW_POLITIKA),
	(_re_dvr.compile(r'\b(magazin|spravodajsky\s+magazin|reflex\b|'
	                 r'7\s+dni|plus\s+7|fokus|profil|lifestyle)'),
	 _NW_MAGAZINY),
	(_re_dvr.compile(r'\b(noviny|sprav[yi]|udalosti|hlavni\s+sprav|hlavne\s+sprav|'
	                 r'tv\s+noviny|112\b|noviny\s+plus|teleráno|telerano|'
	                 r'spravy\s+rtvs|sledovanie\s+spravodajstv|spravodajstv)'),
	 _NW_HLAVNE),
)


_news_subgenre = _make_subgenre_fn(_NEWS_KEYWORD_TO_SUBCAT, _NW_INE)


# -------- Šou / Relácie (Show) --------
_SH_REALITY     = 'sh_reality'       # Reality show — Farmer, Survivor
_SH_TALK        = 'sh_talk'          # Talk show
_SH_SUTAZ       = 'sh_sutaz'         # Súťažné show — talent, X Factor
_SH_KUCHARSKE   = 'sh_kucharske'     # Kuchárske — MasterChef, Ano šéfe
_SH_ZABAVA      = 'sh_zabava'        # Humor, satira, estráda
_SH_MAGAZINY    = 'sh_magaziny'      # Magazíny ako Klíč, Reflex
_SH_INE         = 'sh_ine'

_SHOW_SUBCAT_LABELS = (
	(_SH_REALITY,    'Reality show'),
	(_SH_SUTAZ,      'Competition shows / Talents'),
	(_SH_KUCHARSKE,  'Cooking shows'),
	(_SH_TALK,       'Talk show'),
	(_SH_ZABAVA,     'Entertainment / Comedy'),
	(_SH_MAGAZINY,   'Magazines'),
	(_SH_INE,        'Other'),
)

_SHOW_KEYWORD_TO_SUBCAT = (
	# Kuchárske najprv (lebo "show" v texte by ich zachytilo)
	(_re_dvr.compile(r'\b(kucharsk|masterchef|hell\'?s\s+kitchen|'
	                 r'ano,?\s+sefe|jamie\s+oliver|recept|kuchar|kucharka|'
	                 r'gordon\s+ramsay)'),
	 _SH_KUCHARSKE),
	# Reality show
	(_re_dvr.compile(r'\b(reality\s?show|farmer|farma\b|survivor|big\s+brother|'
	                 r'rande|love\s+island|vyzva\b|prezit|hlada\s+sa|holky\s+z|'
	                 r'mama\s+ja\s+chcem)'),
	 _SH_REALITY),
	# Súťažné show / talenty
	(_re_dvr.compile(r'\b(talent\b|x\s?factor|got\s+talent|the\s+voice|'
	                 r'superstar|tvoja\s+tvar|hviezda|dancing\s+with|'
	                 r'cesko\s+slovenska|stardance|let\'?s\s+dance)'),
	 _SH_SUTAZ),
	# Talk show
	(_re_dvr.compile(r'\b(talk\s?show|show\s+jana\s+krausa|late\s+night|'
	                 r'kraus\b|particka|cestou\s+necestou|vy(2|3|4)\s+show)'),
	 _SH_TALK),
	# Magazíny (vrátane Klíč, Reflex, lifestyle)
	(_re_dvr.compile(r'\b(magazin|reflex\b|zivot\s+v\s+luxuse|'
	                 r'plus\s+7\s+dni|5\s+proti\s+5|inkognito|klic|'
	                 r'lifestyle|polopate)'),
	 _SH_MAGAZINY),
	# Zábava / humor
	(_re_dvr.compile(r'\b(zabavn|humor|estrad|skecz|stand-?up|parodi|'
	                 r'sranda|veselohra|kabaret|satira)'),
	 _SH_ZABAVA),
)


_show_subgenre = _make_subgenre_fn(_SHOW_KEYWORD_TO_SUBCAT, _SH_INE)


# -------- Detské (Children) --------
_CH_ANIMAK      = 'ch_animak'        # Animované, kreslené
_CH_ROZPRAVKY   = 'ch_rozpravky'     # Rozprávky, pohádky
_CH_VZDELAVAC   = 'ch_vzdelavac'     # Vzdelávacie (Kouzelná školka)
_CH_FILMY       = 'ch_filmy'         # Detské filmy
_CH_INE         = 'ch_ine'

_CHILDREN_SUBCAT_LABELS = (
	(_CH_ANIMAK,     'Animated / Cartoons'),
	(_CH_ROZPRAVKY,  'Fairy tales'),
	(_CH_VZDELAVAC,  'Educational'),
	(_CH_FILMY,      'Movies for children'),
	(_CH_INE,        'Other'),
)

_CHILDREN_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(rozpravk|pohadk|princ\b|princezn|'
	                 r'kralovstvo|carodej)'),
	 _CH_ROZPRAVKY),
	(_re_dvr.compile(r'\b(animovan|kreslen|loutkov|cartoon|anime|animak)'),
	 _CH_ANIMAK),
	(_re_dvr.compile(r'\b(kouzeln[aé]?\s+skolk|studio\s+kamar|vzdelavac|'
	                 r'vyuka|naucn|edukacn|do\s+skoly)'),
	 _CH_VZDELAVAC),
	(_re_dvr.compile(r'\b(detsk[yi]\s+film|pre\s+deti\s+film|family\s+film|'
	                 r'rodinny\s+film)'),
	 _CH_FILMY),
)


_children_subgenre = _make_subgenre_fn(_CHILDREN_KEYWORD_TO_SUBCAT, _CH_INE)


# -------- Hudba (Music) --------
_MU_KLASIKA     = 'mu_klasika'       # Klasická hudba, opera
_MU_KONCERT     = 'mu_koncert'       # Koncerty (pop/rock/jazz)
_MU_HITY        = 'mu_hity'          # Hitparáda, popové show
_MU_FOLK        = 'mu_folk'          # Folk, country, ľudovka
_MU_MAGAZINY    = 'mu_magaziny'      # Hudobné magazíny
_MU_INE         = 'mu_ine'

_MUSIC_SUBCAT_LABELS = (
	(_MU_KONCERT,   'Concerts'),
	(_MU_KLASIKA,   'Classical music / Opera'),
	(_MU_HITY,      'Charts / Pop'),
	(_MU_FOLK,      'Folk / Country / Traditional'),
	(_MU_MAGAZINY,  'Music magazines'),
	(_MU_INE,       'Other'),
)

_MUSIC_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(klasick[ay]\s+hudb|opera|symfoni|filharmon|'
	                 r'orchester|orchestr|arie|arij|koncert\s+klasick|smetanova|'
	                 r'ma\s+vlast)'),
	 _MU_KLASIKA),
	(_re_dvr.compile(r'\b(koncert\b|live\s+concert|tour\s+(world|live)|'
	                 r'mtv\s+live|unplugged)'),
	 _MU_KONCERT),
	(_re_dvr.compile(r'\b(folk\b|country|ludova\s+hudba|lidova\s+hudba|'
	                 r'cimbal|ludovk|lidovk|ciganska\s+hudba|folklor)'),
	 _MU_FOLK),
	(_re_dvr.compile(r'\b(hitparad|top\s+\d+|chart|charts|pop\b|popmusic|'
	                 r'pisnicky\s+z\s+obrazovky|videoklip)'),
	 _MU_HITY),
	(_re_dvr.compile(r'\b(hudobn[ye]\s+magaz|music\s+news|hudba\s+\d|hudobnik)'),
	 _MU_MAGAZINY),
)


_music_subgenre = _make_subgenre_fn(_MUSIC_KEYWORD_TO_SUBCAT, _MU_INE)


# -------- Umenie / Kultúra (Arts) --------
_AR_DIVADLO     = 'ar_divadlo'       # Divadlo, opera
_AR_FILM        = 'ar_film'          # Filmové umenie, dokumenty o filme
_AR_VYTVARNE    = 'ar_vytvarne'      # Výtvarné umenie
_AR_LITERATURA  = 'ar_literatura'    # Literatúra, knihy
_AR_INE         = 'ar_ine'

_ARTS_SUBCAT_LABELS = (
	(_AR_DIVADLO,    'Theater'),
	(_AR_FILM,       'Film art'),
	(_AR_VYTVARNE,   'Fine arts / Painting'),
	(_AR_LITERATURA, 'Literature / Books'),
	(_AR_INE,        'Other'),
)

_ARTS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(divadl|theater|inscenace|cinohra|opera\s+plus|baletn|'
	                 r'cinoherni)'),
	 _AR_DIVADLO),
	(_re_dvr.compile(r'\b(vytvarn|malba|maliarstv|socharst|galeri|'
	                 r'umelci|umelec|art\s+(gallery|show)|vystav)'),
	 _AR_VYTVARNE),
	(_re_dvr.compile(r'\b(literatur|literar|knih[ay]|kniha\b|spisovate|'
	                 r'roman\b|prozaik|poezi|basen|kniznic)'),
	 _AR_LITERATURA),
	(_re_dvr.compile(r'\b(filmov[ey]\s+umen|filmov[ya]\s+klasik|filmovi\s+tvorco|'
	                 r'reziser|kameraman|filmari)'),
	 _AR_FILM),
)


_arts_subgenre = _make_subgenre_fn(_ARTS_KEYWORD_TO_SUBCAT, _AR_INE)


# -------- Dokumenty / Vzdelávacie (Documentaries) --------
_DC_PRIRODA     = 'dc_priroda'       # Príroda, zvieratá
_DC_HISTORIA    = 'dc_historia'      # História, archeológia
_DC_VEDA        = 'dc_veda'          # Veda, technika, vesmír
_DC_CESTOPIS    = 'dc_cestopis'      # Cestopis, geografia
_DC_SPOLOCNOST  = 'dc_spolocnost'    # Spoločnosť, ekonomika, politika
_DC_OSOBNOSTI   = 'dc_osobnosti'     # Biografie, portréty
_DC_INE         = 'dc_ine'

_DOCS_SUBCAT_LABELS = (
	(_DC_PRIRODA,    'Nature / Animals'),
	(_DC_HISTORIA,   'History / Archaeology'),
	(_DC_VEDA,       'Science / Technology / Space'),
	(_DC_CESTOPIS,   'Travel / Geography'),
	(_DC_SPOLOCNOST, 'Society / Politics'),
	(_DC_OSOBNOSTI,  'Personalities / Biography'),
	(_DC_INE,        'Other'),
)

_DOCS_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(prirod|zviera|zvire|zivocich|zivocisn|'
	                 r'fauna|flora|narodny\s+park|narodni\s+park|safari|'
	                 r'ocean|dzungla|jerab|orel|sokol|tiger|delfin|velryba|'
	                 r'animal\s+planet|kralovstvo\s+divociny|kralovstvi\s+divociny)'),
	 _DC_PRIRODA),
	(_re_dvr.compile(r'\b(histori|dejiny|stredovek|stredovek|archeo|'
	                 r'antick|stara\s+civiliza|imperi|cisar|kral|'
	                 r'pyramid|rimsk|grecka\s+civi|stredovek)'),
	 _DC_HISTORIA),
	(_re_dvr.compile(r'\b(veda|vedeck|fyzik|chemi|biolog|'
	                 r'matematik|technika|technolog|vesmir|kozmos|'
	                 r'planeta|nasa|esa\s+\w|raketa|vynalez|umela\s+inteligenci)'),
	 _DC_VEDA),
	(_re_dvr.compile(r'\b(cestopis|cesty|cestou\s+necestou|krajiny|cestovate|'
	                 r'expedici|expedice|geografi|narody\s+sveta)'),
	 _DC_CESTOPIS),
	(_re_dvr.compile(r'\b(biografi|portret\s+osob|osobnost|zivotopis|zivot\s+a\s+dielo|'
	                 r'pamati|memoare|spomienky\s+na|zivot\s+a\s+\w)'),
	 _DC_OSOBNOSTI),
	(_re_dvr.compile(r'\b(spoloc|spolecn|ekonom|politick[ay]\s+dokum|kapitalizm|'
	                 r'globali|investigativ\s+dokum|chudoba|migra|trzn[ay]\s+ekonomik)'),
	 _DC_SPOLOCNOST),
)


_docs_subgenre = _make_subgenre_fn(_DOCS_KEYWORD_TO_SUBCAT, _DC_INE)


# -------- Voľný čas / Hobby --------
_HB_ZAHRADA     = 'hb_zahrada'       # Záhrada
_HB_BYVANIE     = 'hb_byvanie'       # Bývanie, renovácie
_HB_VARENIE     = 'hb_varenie'       # Vaření (hobby — nie show)
_HB_AUTO        = 'hb_auto'          # Auto, moto, technika
_HB_CESTOVANIE  = 'hb_cestovanie'    # Cestovanie
_HB_ZDRAVIE     = 'hb_zdravie'       # Zdravie, životospráva, fitness
_HB_DIY         = 'hb_diy'           # DIY, kutilstvo
_HB_INE         = 'hb_ine'

_HOBBY_SUBCAT_LABELS = (
	(_HB_ZAHRADA,    'Garden'),
	(_HB_BYVANIE,    'Living / Renovation'),
	(_HB_VARENIE,    'Cooking / Recipes'),
	(_HB_AUTO,       'Auto / Moto'),
	(_HB_CESTOVANIE, 'Travel'),
	(_HB_ZDRAVIE,    'Health / Fitness'),
	(_HB_DIY,        'DIY / Crafts'),
	(_HB_INE,        'Other'),
)

_HOBBY_KEYWORD_TO_SUBCAT = (
	(_re_dvr.compile(r'\b(zahrad|kvetin|sklenik|tri\s+v\s+zahrade|'
	                 r'okrasn[ay]\s+rastlin)'),
	 _HB_ZAHRADA),
	(_re_dvr.compile(r'\b(byvan|interier|renovac|architektur|'
	                 r'rekonstruk|nabytk|kuchyna\s+(snov|sna|dizajn)|bydleni)'),
	 _HB_BYVANIE),
	(_re_dvr.compile(r'\b(varen|recept|jedl[oa]|kuchar(stvo|ka|i)?|'
	                 r'peciem|s\s+kuchar|kucharka|babickovy)'),
	 _HB_VARENIE),
	(_re_dvr.compile(r'\b(auto\b|moto\b|automobil|motorka|automotive|'
	                 r'autosalon|garaz)'),
	 _HB_AUTO),
	(_re_dvr.compile(r'\b(cestovan|cestujeme|destinac|hotel\s+test|'
	                 r'vylety|vylet\s+po|destination|on\s+the\s+road|cestopis|'
	                 r'z\s+metropol)'),
	 _HB_CESTOVANIE),
	(_re_dvr.compile(r'\b(zdrav[ie]\s+|fitness|cvicen|wellness|'
	                 r'beh\s+v\s+meste|zivotospravu|chudnut)'),
	 _HB_ZDRAVIE),
	(_re_dvr.compile(r'\b(kutil|diy\b|hand\s+made|vlastnorucn|svojpomocn|'
	                 r'workshop|tvorime|dilna)'),
	 _HB_DIY),
)


_hobby_subgenre = _make_subgenre_fn(_HOBBY_KEYWORD_TO_SUBCAT, _HB_INE)


# --------------------------------------------------------------------------
# Title corpus (FIX 0.53beta — z Kodi 1.0.6)
# --------------------------------------------------------------------------
# Statický corpus filmov a seriálov v každom žánri + lokalizované sk/cs
# preklady. Klasifikátor sa pýta corpus-u PRED keyword scan-om — title-based
# match je spoľahlivejší ako "drama" keyword v opise.
#
# Corpus súbor: resources/title_genre_corpus.json relatívne k provider.py.
# Lazy načítanie pri prvom volaní. Bez I/O ak corpus chýba (graceful fallback).
_CORPUS_CODE_TO_SUBCAT = {
	'ak': _MV_AKCNY,
	'ko': _MV_KOMEDIA,
	'kr': _MV_KRIMI,
	'dr': _MV_DRAMA,
	'sf': _MV_SCIFI,
	'ro': _MV_ROMANTIKA,
	'ho': _MV_HOROR,
	'do': _MV_DOBRODR,
	'an': _MV_ANIMAK,
	'hi': _MV_HISTORICKY,
	'we': _MV_WESTERN,
}

_CORPUS_STATE = {
	'loaded': False,
	'titles': {},    # normalized_title → subcat constant
	'load_error': None,
	'meta': None,
}


def _corpus_path():
	"""Vráti absolútnu cestu k corpus JSON súboru.

	provider.py je v plugin_video_tvheadend/, corpus je v
	plugin_video_tvheadend/resources/.
	"""
	here = os.path.dirname(os.path.abspath(__file__))
	return os.path.join(here, 'resources', 'title_genre_corpus.json')


def _load_corpus_if_needed():
	"""Lazy načítanie corpus-u. Idempotentné — volá sa pred každým lookup-om."""
	if _CORPUS_STATE['loaded']:
		return
	_CORPUS_STATE['loaded'] = True  # set early — jeden pokus o load, no retry loop
	path = _corpus_path()
	try:
		with io.open(path, 'r', encoding='utf-8') as f:
			data = json.load(f)
	except (IOError, OSError):
		_CORPUS_STATE['load_error'] = 'corpus file not found: %s' % path
		return
	except (ValueError,) as e:
		_CORPUS_STATE['load_error'] = 'corpus load failed: %s' % e
		return

	raw_titles = (data.get('titles') if isinstance(data, dict) else None) or {}
	out = {}
	for k, code in raw_titles.items():
		sub = _CORPUS_CODE_TO_SUBCAT.get(code)
		if sub is None or not isinstance(k, str):
			continue
		if k:
			out[k] = sub
	_CORPUS_STATE['titles'] = out
	_CORPUS_STATE['meta'] = data.get('_meta') if isinstance(data, dict) else None

	try:
		_log('title corpus loaded: %d entries' % len(out))
	except Exception:
		pass


# Regex na odstránenie "(YYYY)" suffixu — corpus tituly tento suffix nemajú.
_TITLE_YEAR_SUFFIX = _re_dvr.compile(r'\s*\(\s*(?:19|20)\d{2}\s*\)\s*$')


def _canonical_title_for_corpus(title):
	"""Normalizuje title pre corpus lookup. Musí ladiť s normalizáciou
	použitou pri tvorbe corpus JSON-u."""
	if not title:
		return ''
	t = _strip_tech_markers(title)
	t = _series_canonical_title(t)
	t = _TITLE_YEAR_SUFFIX.sub('', t).strip()
	return _strip_accents_lower(t)


def _corpus_subgenre_match(entry):
	"""Vráti subcat constant ak title match-ne v corpuse, inak None."""
	_load_corpus_if_needed()
	titles = _CORPUS_STATE['titles']
	if not titles:
		return None
	title = entry.get('disp_title') or ''
	key = _canonical_title_for_corpus(title)
	if not key:
		return None
	return titles.get(key)


# --------------------------------------------------------------------------
# Registry: mapuje top_cat → (labels, subgenre_fn)
# Použité v archive_by_category na rozhodnutie či pridať podžánre menu
# --------------------------------------------------------------------------
_SUBCAT_REGISTRY = {
	_CAT_FILM:           (_MOVIE_SUBCAT_LABELS,    None),   # špeciálne — viď archive
	_CAT_SERIAL:         (_MOVIE_SUBCAT_LABELS,    None),   # špeciálne — viď archive
	_CAT_SPORT:          (_SPORT_SUBCAT_LABELS,    _sport_subgenre),
	_CAT_SPRAVODAJSTVO:  (_NEWS_SUBCAT_LABELS,     _news_subgenre),
	_CAT_SHOW:           (_SHOW_SUBCAT_LABELS,     _show_subgenre),
	_CAT_DETSKE:         (_CHILDREN_SUBCAT_LABELS, _children_subgenre),
	_CAT_HUDBA:          (_MUSIC_SUBCAT_LABELS,    _music_subgenre),
	_CAT_UMENIE:         (_ARTS_SUBCAT_LABELS,     _arts_subgenre),
	_CAT_DOKUMENTY:      (_DOCS_SUBCAT_LABELS,     _docs_subgenre),
	_CAT_HOBBY:          (_HOBBY_SUBCAT_LABELS,    _hobby_subgenre),
}


def _movie_subgenre(entry):
	"""Vráti sub-kategóriu pre film/seriál.

	Logika:
	1. DVB genre byte (ak je dostupný) → primary signal
	2. Title corpus match (~1945 hand-curated titulov) → confident sub-genre.
	   Pokrýva sci-fi franchise (Duna, Star Wars, Matrix, Avatar, Marvel/DC,
	   Terminator, atď.) + iné žánre.
	3. Keyword scan title + subtitle + description → secondary signal
	4. Horror — len v title (FIX 0.53beta: bez tohto matchol aj v opise
	   "hrůza války" → war film padol do Horor)
	5. Inak _MV_INE

	FIX 0.57.0 (skyjet PR #22 review #14): odstránený _TITLE_SCIFI_PATTERNS
	regex zoznam 38 patternov ako 2. krok pred corpus — bol redundant,
	všetkých 38 patternov má match v corpuse. Skyjet's poznámka "buď
	univerzálne alebo vôbec" — corpus je univerzálnejší (+ IMDb lookup
	ako 3. layer pre missing tituly).
	"""
	# 1) DVB genre check
	for g in (entry.get('genre') or []):
		try:
			g = int(g)
		except (ValueError, TypeError):
			continue
		sub = _DVB_GENRE_TO_SUBCAT.get(g)
		if sub:
			return sub

	# 2) Title corpus lookup
	corpus_sub = _corpus_subgenre_match(entry)
	if corpus_sub is not None:
		return corpus_sub

	# 3) Specifickejšie keyword scan
	text = ((entry.get('disp_title') or '') + ' ' +
	        (entry.get('disp_subtitle') or '') + ' ' +
	        (entry.get('disp_description') or ''))
	if not text.strip():
		return _MV_INE
	text = _strip_accents_lower(text)
	for pattern, subcat in _KEYWORD_TO_SUBCAT:
		if pattern.search(text):
			return subcat

	# 4) Horror — len v title
	# FIX 0.57.0: title_only definíciu sme potrebovali samostatne lebo
	# franchise step (kde bola predtým definovaná) bol odstránený.
	title_only = _strip_accents_lower(entry.get('disp_title') or '')
	if title_only and _HORROR_TITLE_PATTERN.search(title_only):
		return _MV_HOROR

	return _MV_INE


# --------------------------------------------------------------------------
# Channel-based hints (FIX 0.49b)
# --------------------------------------------------------------------------
# Niektoré kanály majú jednoznačnú orientáciu žánru — táto orientácia je
# spoľahlivejšia ako DVB content_type ktorý broadcast environment občas
# vypĺňa zle. Substring match v channelname (case-insensitive).
_CHANNEL_TOP_HINTS = (
	# Deti — CT :D, JOJ-ko, Disney, Nick atď.
	('ct :d',       _CAT_DETSKE),
	('ct d-art',    _CAT_DETSKE),
	('ct d/art',    _CAT_DETSKE),
	('decko',       _CAT_DETSKE),
	('jojko',       _CAT_DETSKE),
	('minimax',     _CAT_DETSKE),
	('cartoon',     _CAT_DETSKE),
	('disney',      _CAT_DETSKE),
	('nick',        _CAT_DETSKE),
	('boomerang',   _CAT_DETSKE),
	('baby tv',     _CAT_DETSKE),
	('duck tv',     _CAT_DETSKE),
	# Šport — substring 'sport' chytí Premier Sport, Nova Sport, Eurosport...
	('sport',       _CAT_SPORT),
	('eurosport',   _CAT_SPORT),
	('digi sport',  _CAT_SPORT),
	('nova sport',  _CAT_SPORT),
	('o2 sport',    _CAT_SPORT),
	# Spravodajstvo
	('cnn',         _CAT_SPRAVODAJSTVO),
	('bbc news',    _CAT_SPRAVODAJSTVO),
	('bbc world',   _CAT_SPRAVODAJSTVO),
	('ta3',         _CAT_SPRAVODAJSTVO),
	('ct24',        _CAT_SPRAVODAJSTVO),
	('ct 24',       _CAT_SPRAVODAJSTVO),
	('euronews',    _CAT_SPRAVODAJSTVO),
	# Hudba
	('ocko',        _CAT_HUDBA),
	('now 80',      _CAT_HUDBA),
	('now 90',      _CAT_HUDBA),
	('now rock',    _CAT_HUDBA),
	('mtv',         _CAT_HUDBA),
	('vh1',         _CAT_HUDBA),
	('mezzo',       _CAT_HUDBA),
	('óčko',        _CAT_HUDBA),
	# Dokumentárne kanály (FIX 0.53beta — z Kodi 1.0.4 portu).
	# Broadcasters často taggujú obsah na týchto kanáloch ako ct=1
	# (Movie/Drama) alebo ct=2 (News), čo nie je presné — drvivá väčšina
	# obsahu je documentary. Pre ct=0/1/2/9 doc channel hint vyhráva
	# (riešené v _determine_top_cat). Pre ct=3-10 explicit DVB tag
	# (Šport/Hudba/Šou) zostáva — športové news na doc kanáli má zmysel
	# klasifikovať podľa DVB tagu, nie ako documentary.
	('discovery',         _CAT_DOKUMENTY),
	('viasat history',    _CAT_DOKUMENTY),
	('viasat explore',    _CAT_DOKUMENTY),
	('viasat nature',     _CAT_DOKUMENTY),
	('viasat true crime', _CAT_DOKUMENTY),
	('national geographic', _CAT_DOKUMENTY),
	('nat geo',           _CAT_DOKUMENTY),
	('spektrum',          _CAT_DOKUMENTY),
	('animal planet',     _CAT_DOKUMENTY),
	('history channel',   _CAT_DOKUMENTY),
	('history hd',        _CAT_DOKUMENTY),
	('bbc earth',         _CAT_DOKUMENTY),
	('bbc knowledge',     _CAT_DOKUMENTY),
	('love nature',       _CAT_DOKUMENTY),
	('docubox',           _CAT_DOKUMENTY),
	('crime+investigation', _CAT_DOKUMENTY),
	('crime + investigation', _CAT_DOKUMENTY),
	# Krimi kanály — strong hint pre Filmy/Seriály sub-žáner
	# (HANDLED v _channel_subgenre_hint nižšie, nie tu — to je sub override)
)

# Channel name → movie/serial sub-genre hint (silnejší než keyword scan)
_CHANNEL_SUBCAT_HINTS = (
	('krimi',       _MV_KRIMI),       # JOJ KRIMI, Nova Krimi, Prima Krimi
	('action',      _MV_AKCNY),       # Nova Action
	('romantica',   _MV_ROMANTIKA),   # Nova Romantica
	('romantika',   _MV_ROMANTIKA),
	('comedy',      _MV_KOMEDIA),     # Comedy Central
	('cinema',      None),             # Nova Cinema, AXN Cinema — generic film
	('horror',      _MV_HOROR),
	('history',     _MV_HISTORICKY),
)


def _channel_top_hint(entry):
	"""Vráti top-level kategóriu na základe channelname, alebo None."""
	ch = (entry.get('channelname') or '').lower()
	if not ch:
		return None
	for substring, cat in _CHANNEL_TOP_HINTS:
		if substring in ch:
			return cat
	return None


def _channel_subgenre_hint(entry):
	"""Vráti sub-kategóriu na základe channelname, alebo None."""
	ch = (entry.get('channelname') or '').lower()
	if not ch:
		return None
	for substring, subcat in _CHANNEL_SUBCAT_HINTS:
		if substring in ch:
			return subcat
	return None


# --------------------------------------------------------------------------
# Series detection (FIX 0.49b: rozšírené)
# --------------------------------------------------------------------------
# Keywords v description ktoré naznačujú seriál (Czech/Slovak)
_SERIES_KEYWORDS = ('seriál', 'série', ' díl ', 'epizoda', 'epizóda',
                    'season ', 'episode ')


def _is_series_entry(entry):
	"""True ak je entry seriálom (na základe akéhokoľvek dostupného signálu).

	Detekuje 4 vzory:
	  1) "25/31 ..." v subtitle (CT/Nova old format)
	  2) "...(N)" sufix v title kde N nie je rok (Otec Brown IV (1))
	  3) episode_disp non-empty (TVH má explicit episode info)
	  4) keyword 'seriál'/'díl'/'epizoda' v description
	"""
	subtitle = (entry.get('disp_subtitle') or '').strip()
	if _SUBTITLE_SERIES_PATTERN.match(subtitle):
		return True

	title = (entry.get('disp_title') or '').strip()
	if _has_episode_suffix(title):
		return True

	if entry.get('episode_disp'):
		return True

	desc = ((entry.get('disp_description') or '') + ' ' + subtitle).lower()
	for kw in _SERIES_KEYWORDS:
		if kw in desc:
			return True

	return False


# --------------------------------------------------------------------------
# Fallback keyword guess pre Nezaradené (ct=0 alebo 11)
# FIX 0.53beta — z Kodi 1.0.4 + 1.0.7 portu:
#   - Detské: odstránený generický "detsk" pattern (matchol slovo "detský" v
#     opisoch home renovation shows). Iba explicitné detské markery zostávajú.
#   - Show: rozšírené o ~30 sk/cz reality/talk/cooking patternov ktoré
#     padali do _CAT_INE — Zámena manželiek, Top Gear, MasterChef atď.
#   - Hobby: nový pattern pre home/garden/design programmes
#     (Nové bývanie, Nová záhrada, Jak se staví sen).
# --------------------------------------------------------------------------
_FALLBACK_KEYWORD_TO_TOP = (
	# Šport
	(_re_dvr.compile(r'\b(futbal|hokej|tenis|golf|formula|f1|oktagon|liga|'
	                 r'majstrov|olympi|rally|cyklist|atletik|box|wrestlin|'
	                 r'biatlon|lyzovan|sjazd|mma|ufc|pml)'),
	 _CAT_SPORT),
	# Spravodajstvo
	(_re_dvr.compile(r'\b(spravodajstvo|sprav[yi]|udalosti|aktualn|reporter|noviny\s+tv|'
	                 r'tv\s+noviny|pocasi|uvodnik)'),
	 _CAT_SPRAVODAJSTVO),
	# Detské (FIX 0.53beta — odstránený generický 'detsk' ktorý matchol
	# "detský domov" v krimi reportáži, "detskú izbu" v design show, atď.
	# Iba explicitné detské markery zostávajú + konkrétne show formáty.)
	(_re_dvr.compile(r'\b(rozpravk|pohadk|pre\s+deti|pro\s+deti|pre\s+najmens|'
	                 r'kreslen[ay]|animovan[ay]|loutkov[ay]|'
	                 r'byl\s+jednou\s+jeden|fidlibum|miniatel|trpaslic|'
	                 r'labkov[aá]\s+patrol)'),
	 _CAT_DETSKE),
	# Hudba
	(_re_dvr.compile(r'\b(koncert|hudba|hudobn|hudebni|spevok|zpevak|spevak|'
	                 r'piesn|pisni|pop\s|rock\s|metal\s|klasick)'),
	 _CAT_HUDBA),
	# Šou (FIX 0.53beta — rozšírené o sk/cz reality/talk/cooking formáty)
	(_re_dvr.compile(r'\b(magazin|talk\s?show|\bshow\b|soutez|sutaz|'
	                 r'reality\s?show|farmer|farma|zabavn|estrada|kucharsk|'
	                 r'zamena\s+manzeliek|nebezpecne\s+vztahy|jak\s+to\s+dopadl|'
	                 r'intim\s+s\s|prima\s+pauza|najlepsie\s+viraln|'
	                 r'extremne\s+pripad|dokonaly\s+sef|utajeny\s+sef|spriznene\s+duse|'
	                 r'v\s+siedmom\s+nebi|poklad\s+z\s+pud|jak\s+se\s+stavi\s+sen|'
	                 r'ano\s+sefe|top\s+gear|masterchef|babicovy\s+tip|'
	                 r'varime\s+s|vareni\s+s|recept[aá]r|recepta?\s+prima|'
	                 r'babica\s+vs|co\s+bude\s+dnes\s+k\s+vecer|nase\s+zlepsovak|'
	                 r'afery\s+-?\s*neuver|rodinna\s+firma|vip\s+svet|na\s+plac|'
	                 r'exkluziv|zachranari|u\s+tebe\s+nebo\s+u\s+me|'
	                 r'nedorucena\s+tajemstv)'),
	 _CAT_SHOW),
	# Hobby (FIX 0.53beta — nový pattern pre home/garden/design)
	(_re_dvr.compile(r'\b(byvani[ae]?|byvanie|zahrad[ay]|zahradka|'
	                 r'navrhar|dizajn\s+|design\s+interier|'
	                 r'remeselni|stolarsk|truhlarsk|rybarsk[ay])'),
	 _CAT_HOBBY),
	# Dokumenty
	(_re_dvr.compile(r'\b(dokument|documentary|prirod|history|'
	                 r'vesmir|national\s+geographic|discovery)'),
	 _CAT_DOKUMENTY),
)


def _guess_top_category_from_keywords(entry):
	"""Pre záznamy s ct=0 alebo ct=11 (undefined) skús určiť top-level
	kategóriu cez keywords v title + subtitle + description + channelname.
	"""
	text = ((entry.get('disp_title') or '') + ' ' +
	        (entry.get('disp_subtitle') or '') + ' ' +
	        (entry.get('disp_description') or '') + ' ' +
	        (entry.get('channelname') or ''))
	if not text.strip():
		return _CAT_INE
	text = _strip_accents_lower(text)
	for pattern, cat in _FALLBACK_KEYWORD_TO_TOP:
		if pattern.search(text):
			return cat
	return _CAT_INE


# --------------------------------------------------------------------------
# Hlavná klasifikačná funkcia
# --------------------------------------------------------------------------
def _classify_dvr_entry(entry):
	"""Vráti (top_cat, sub_cat).

	sub_cat môže byť None ak top_cat nemá podžánre. Inak je to jeden
	z _MV_* / _SP_* / _NW_* / _SH_* / _CH_* / _MU_* / _AR_* / _DC_* / _HB_*
	identifikátorov.

	Priorita signálov pre Filmy/Seriály subcat (od 0.53beta):
	  1. Title corpus match (~1945 titulov) — vyhráva aj nad channel
	     subgenre hint-om (Duna na akčnom kanáli ostane sci-fi).
	  2. Channel sub-genre hint (Nova Krimi → krimi)
	  3. DVB genre byte + keyword scan (_movie_subgenre)
	  4. IMDb lookup ako posledný fallback (opt-in)

	FIX 0.57.0 (skyjet PR #22 review #14): predtým bol _TITLE_SCIFI_PATTERNS
	regex zoznam 38 sci-fi/fantasy franchise patternov ako prvý krok pred
	corpus. Bol redundant — všetkých 38 patternov má match v corpuse.
	Skyjet's feedback "buď univerzálne alebo vôbec" — corpus 1945 titulov
	je univerzálnejší + IMDb GraphQL lookup ako 3. layer pokrýva missing.
	"""
	# Najprv urči top kategóriu
	top = _determine_top_cat(entry)

	if top == _CAT_FILM or top == _CAT_SERIAL:
		# Title corpus beats channel hint (známy titul = silný signál).
		# Pokrýva sci-fi franchise (Duna, Star Wars, ...) aj iné žánre.
		corpus_sub = _corpus_subgenre_match(entry)
		if corpus_sub is not None:
			return top, corpus_sub

		# Channel hint má prednosť pred DVB/keyword scan
		sub = _channel_subgenre_hint(entry)
		if sub is None:
			sub = _movie_subgenre(entry)
			# FIX 0.54beta (z Kodi 1.0.9): ak movie_subgenre vrátil
			# mv_ine, skús IMDb lookup ako posledný fallback. Default
			# OFF cez settings toggle "online_metadata_lookup".
			if sub == _MV_INE:
				try:
					from . import imdb_lookup as _imdb
					_, imdb_sub = _imdb.lookup(entry)
					if imdb_sub is not None:
						sub = imdb_sub
				except Exception:
					pass
		return top, sub

	# FIX 0.49d: ostatné kategórie s podžánrami cez registry dispatch
	entry_cfg = _SUBCAT_REGISTRY.get(top)
	if entry_cfg and entry_cfg[1] is not None:
		# entry_cfg = (labels, subgenre_fn)
		sub = entry_cfg[1](entry)
		return top, sub

	# Kategórie bez podžánrov (napr. _CAT_INE)
	return top, None


def _determine_top_cat(entry):
	"""Helper: vráti top-level kategóriu pre entry.

	Logika (od 0.53beta — z Kodi 1.0.4 portu):
	- content_type je explicitný DVB-SI Level 1 signál z broadcaster-a —
	  má prednosť pred channel hint pre ct=2-10 (DVB tag presnejší než
	  channel name pre Šport/Hudba/News/Show/Arts/Edu/Hobby).
	- Pre dokumentárne kanály (Discovery, Viasat, NG, …) doc hint vyhráva
	  aj nad ct=0/1/2/9 lebo broadcasters routinely mistagujú obsah ako
	  Movie/Drama alebo News na týchto kanáloch.
	- Pre ct=1 (Movie/Drama) a ct=0/5/11: channel hint a series detection
	  majú zmysel — children's animated series channel by mal override-nuť
	  generic Movie tag.
	- Vrátí tuple (top_cat, reason_str) ak je diagnostika ON, inak iba top_cat.
	"""
	try:
		ct = int(entry.get('content_type') or 0)
	except Exception:
		ct = 0

	channel_top = _channel_top_hint(entry)

	# 1) Dokumentárne kanály overrideujú aj ct=0/1/2/9 — broadcasters mistagujú
	#    obsah ako Movie/Drama (ct=1) alebo News (ct=2). Pre ct=3-10 doc hint
	#    NEvyhráva (Šport/Hudba/Šou explicitne tagované je spec. program).
	if channel_top == _CAT_DOKUMENTY and ct in (0, 1, 2, 9):
		return _CAT_DOKUMENTY

	# 2) Explicit DVB-SI Level 1 (ct=2-10) — broadcaster vie čo nahral, dôveruj.
	if ct in (2, 3, 4, 6, 7, 8, 9, 10):
		return _CT_TO_CAT_BASE[ct]

	# 3) Channel hint pre kategórie kde channel name je presný signál
	#    (detský/športový/hudobný/spravodajský kanál).
	if channel_top in (_CAT_DETSKE, _CAT_SPORT, _CAT_HUDBA, _CAT_SPRAVODAJSTVO):
		return channel_top

	# 4) Series detection pred ct=1/5/0 — seriál môže mať ct=1 (Movie/Drama).
	if _is_series_entry(entry):
		return _CAT_SERIAL

	# 5) ct=1 Movie/Drama → film
	if ct == 1:
		return _CAT_FILM

	# 6) ct=5 Children → detské
	if ct == 5:
		return _CAT_DETSKE

	# 7) Keyword fallback pre ct=0/11 (undefined)
	guessed = _guess_top_category_from_keywords(entry)

	# 7b) Corpus-based top promotion (FIX 0.53beta — z Kodi 1.0.7).
	# Ak by entry skončila v _CAT_INE, ale titul je v title corpuse,
	# povýši sa na _CAT_FILM (corpus pozná film/seriál sub-genre).
	if guessed == _CAT_INE:
		if _corpus_subgenre_match(entry) is not None:
			return _CAT_FILM

		# 7c) FIX 0.54beta (z Kodi 1.0.9): IMDb GraphQL lookup ako
		# posledný safety net pred _CAT_INE. Default OFF cez settings
		# toggle "online_metadata_lookup". Ak je zapnutý a IMDb vráti
		# top override (Reality-TV/Documentary/News/Sport/Music/
		# Talk-Show/Game-Show), použij. Inak ak vráti film sub-žáner,
		# povýš top na CAT_FILM. Inak → ine.
		try:
			from . import imdb_lookup as _imdb
			imdb_top, imdb_sub = _imdb.lookup(entry)
			if imdb_top is not None and imdb_top in _IMDB_TOP_TO_CAT:
				return _IMDB_TOP_TO_CAT[imdb_top]
			if imdb_sub is not None:
				return _CAT_FILM
		except Exception:
			pass  # graceful — never crash classification on network problem

	return guessed


# Map IMDb-derived top names to our _CAT_* constants. Kept here (not in
# imdb_lookup.py) to avoid a circular import between the two modules.
# Order matches Kodi 1.0.9: Shows / Documentaries / News / Sports / Music.
_IMDB_TOP_TO_CAT = {
	'show':           _CAT_SHOW,
	'dokumenty':      _CAT_DOKUMENTY,
	'spravodajstvo':  _CAT_SPRAVODAJSTVO,
	'sport':          _CAT_SPORT,
	'hudba':          _CAT_HUDBA,
	'detske':         _CAT_DETSKE,
}


def _dedup_dvr_entries(entries):
	"""Vráti deduplikované entries — najnovší z každej (title, subtitle) skupiny.

	TVH 7x24 autorec môže nahrať tú istú epizódu viackrát počas dňa
	(napr. Pension pro svobodné pány 3× za pár hodín). Pre menu chceme
	ukázať len jeden záznam. Kľúč: (disp_title, disp_subtitle[:80]).
	Z duplikátov ostane ten s najvyšším _ts (najnovšie nahranie).
	"""
	by_key = {}
	for e in entries:
		title = (e.get('disp_title') or '').strip()
		if not title:
			continue
		sub = (e.get('disp_subtitle') or '')[:80]
		key = (title, sub)
		prev = by_key.get(key)
		if prev is None or _ts(e) > _ts(prev):
			by_key[key] = e
	return list(by_key.values())


# Cache pre klasifikáciu (60s TTL — rovnaké ako DVR cache)
_DVR_CLASSIFY_CACHE = {'ts': 0, 'data': None}
_DVR_CLASSIFY_TTL_SEC = 60


def _invalidate_classify_cache():
	_DVR_CLASSIFY_CACHE['ts'] = 0
	_DVR_CLASSIFY_CACHE['data'] = None


def _get_classified_dvr(entries):
	"""Vráti tuple s klasifikovanými dátami pre menu rendering.

	Args:
	    entries: list DVR entries (provider.py si ich získa cez vlastnú cache
	             vrstvu _get_dvr_finished_cached(tvh) a passuje sem).

	Returns:
	    entries_by_top: {top_cat: [entry, ...]}  flat lists pre non-Filmy/Seriály
	    entries_by_subcat: {(top_cat, sub_cat): [entry, ...]}  pre Filmy detail
	    counts: {top_cat: int}  pre rozhodovanie či pridať položku do root
	    series_by_canonical: {canonical_title: [entry, ...]}  pre Seriály detail
	    series_subcat_titles: {(top_cat, sub_cat): set(canonical_title)}
	                          pre filtrovanie zoznamu sérií v sub-žánre

	Sort: všetky listy newest-first (key=_ts, reverse=True).
	Cache: 60s (klasifikácia ako taká — entries cache rieši provider.py).

	FIX 0.57.0 (skyjet PR #22 review #4): signature zmenená z (tvh) na
	(entries) — clean separation, classifier nepotrebuje vedieť aký
	cache layer používa provider pre raw DVR entries.
	"""
	now = int(time.time())
	cached = _DVR_CLASSIFY_CACHE
	if cached['data'] and (now - cached['ts']) < _DVR_CLASSIFY_TTL_SEC:
		return cached['data']

	entries = _dedup_dvr_entries(entries or [])

	entries_by_top = {}
	entries_by_subcat = {}
	series_by_canonical = {}
	series_subcat_titles = {}

	for e in entries:
		top, sub = _classify_dvr_entry(e)
		entries_by_top.setdefault(top, []).append(e)
		if sub is not None:
			entries_by_subcat.setdefault((top, sub), []).append(e)

		if top == _CAT_SERIAL:
			title = (e.get('disp_title') or '').strip()
			if title:
				canonical = _series_canonical_title(title)
				if canonical:
					series_by_canonical.setdefault(canonical, []).append(e)
					if sub is not None:
						series_subcat_titles.setdefault(
							(top, sub), set()).add(canonical)

	# Sort: newest first
	for k in entries_by_top:
		entries_by_top[k].sort(key=_ts, reverse=True)
	for k in entries_by_subcat:
		entries_by_subcat[k].sort(key=_ts, reverse=True)
	for t in series_by_canonical:
		series_by_canonical[t].sort(key=_ts, reverse=True)

	counts = {cat: len(entries_by_top[cat]) for cat in entries_by_top}
	data = (entries_by_top, entries_by_subcat, counts,
	        series_by_canonical, series_subcat_titles)

	cached['ts'] = now
	cached['data'] = data
	return data
# ============================================================================
# end FIX 0.49 classification helpers
# ============================================================================
