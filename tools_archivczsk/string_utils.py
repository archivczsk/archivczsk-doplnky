# -*- coding: utf-8 -*-

#/*
# *		 Copyright (C) 2011 Libor Zoubek
# *
# *
# *	 This Program is free software; you can redistribute it and/or modify
# *	 it under the terms of the GNU General Public License as published by
# *	 the Free Software Foundation; either version 2, or (at your option)
# *	 any later version.
# *
# *	 This Program is distributed in the hope that it will be useful,
# *	 but WITHOUT ANY WARRANTY; without even the implied warranty of
# *	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *	 GNU General Public License for more details.
# *
# *	 You should have received a copy of the GNU General Public License
# *	 along with this program; see the file COPYING.	 If not, write to
# *	 the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *	 http://www.gnu.org/copyleft/gpl.html
# *
# */
import os, re, sys, traceback

if sys.version[0] == 2:
	is_py3 = False
	
	def py2_decode_utf8( text ):
		return text.decode('utf-8', 'ignore')

	def py2_encode_utf8( text ):
		return text.encode('utf-8', 'ignore')

else:
	is_py3 = True

	def py2_decode_utf8( text ):
		return text

	def py2_encode_utf8( text ):
		return text

# #################################################################################################

def decode_html(data):
	def _substitute_entity(match):
		ent = match.group(3)
		if match.group(1) == '#':
			# decoding by number
			if match.group(2) == '':
				# number is in decimal
				return unichr(int(ent))
			elif match.group(2) == 'x':
				# number is in hex
				return unichr(int('0x' + ent, 16))
		else:
			# they were using a name
			cp = n2cp.get(ent)
			if cp: return unichr(cp)
			else: return match.group()
	try:
		if is_py3 == False and not isinstance(data, unicode):
			data = unicode(data, 'utf-8', errors='ignore')
		entity_re = re.compile(r'&(#?)(x?)(\w+);')
		return entity_re.subn(_substitute_entity, data)[0]
	except:
		return data
	
# #################################################################################################

def _C(color, str):
	"""
	Returns colored text
	"""
	return '[COLOR %s]%s[/COLOR]' % (color, str)

def _B(str):
	"""
	Returns bold text
	"""
	return '[B]%s[/B]' % str

def _I(str):
	"""
	Returns italic text
	"""
	return '[I]%s[/I]' % str

# #################################################################################################
