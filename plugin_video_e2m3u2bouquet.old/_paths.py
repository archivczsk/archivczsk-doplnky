# -*- coding: utf-8 -*-
"""
FIX 0.48j: persistent data directory pre stamp súbory.

Predtým: všetky .stamp súbory ležali v /tmp (tmpfs), ktorý sa pri reboot-e
typicky maže. Teraz: stamp súbory sa ukladajú do ArchivCZSK plugin data
adresára, ktorý prežíva reboot. Cache obrázkov (picons) ostáva v /tmp lebo
je regenerovateľná a tmpfs je rýchle pre časté GUI access.

Vyhľadávanie data_dir: skúšame zhora dole, prvý ktorý je writable vyhráva.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os


_ADDON_ID = 'plugin.video.e2m3u2bouquet'

_DATA_DIR_CANDIDATES = (
	# ArchivCZSK conventional path (preferovaná)
	'/usr/lib/enigma2/python/Plugins/Extensions/archivCZSK/resources/data/' + _ADDON_ID,
	'/etc/archivczsk/' + _ADDON_ID,
	'/etc/enigma2/' + _ADDON_ID,
	# Posledný fallback ak žiadna z hore uvedených nie je writable
	'/tmp',
)

# Cache: raz uložené, žiadne re-check pri každom volaní
_DATA_DIR_RESOLVED = None


def _try_make_writable(path):
	"""Skúsi vytvoriť adresár a otestovať writability. Vráti True/False."""
	try:
		if not os.path.isdir(path):
			os.makedirs(path)
		test = os.path.join(path, '.write_test')
		with open(test, 'w') as f:
			f.write('1')
		os.remove(test)
		return True
	except Exception:
		return False


def get_data_dir():
	"""Vráti adresár na ukladanie stamp/state súborov pluginu.

	Lazily vyhľadá writable lokáciu (cache-uje výsledok). Pri prvom volaní
	prejde _DATA_DIR_CANDIDATES, vytvorí prvú writable cestu a vráti ju.
	Pri ďalších volaniach vráti cache-ovanú hodnotu (žiadne stat() volania).

	Garancia: vráti vždy writable string cestu. V najhoršom prípade /tmp.
	"""
	global _DATA_DIR_RESOLVED
	if _DATA_DIR_RESOLVED is not None:
		return _DATA_DIR_RESOLVED

	for candidate in _DATA_DIR_CANDIDATES:
		if _try_make_writable(candidate):
			_DATA_DIR_RESOLVED = candidate
			try:
				print('[plugin.e2m3u2bouquet] using data dir: %s' % candidate)
			except Exception:
				pass
			return _DATA_DIR_RESOLVED

	# Theoretically nedosiahnuteľné, ale defensive
	_DATA_DIR_RESOLVED = '/tmp'
	return _DATA_DIR_RESOLVED


def data_path(name):
	"""Vráti absolútnu cestu k súboru v data dir-u.

	`name` je len base-name (žiadny prefix /tmp/, žiadne /).
	Príklad: data_path('bouquet_refresh.stamp') ->
	         '/usr/lib/enigma2/.../plugin.video.tvheadend/bouquet_refresh.stamp'
	"""
	return os.path.join(get_data_dir(), name)
