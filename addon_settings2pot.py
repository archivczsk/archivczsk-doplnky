# -*- coding: utf-8 -*-

from __future__ import print_function
import sys, os
from xml.etree.cElementTree import ElementTree


def print_string(s):
	print('msgid "%s"\nmsgstr ""\n' % s)


class SettingsXMLParser:
	def __init__(self, xml_file):
		if os.path.isfile(xml_file):
			el = ElementTree()
			el.parse(xml_file)
			self.xml = el.getroot()
		else:
			self.xml = None

	def parse(self):
		if self.xml is None:
			return

		categories = []
		settings = self.xml

		for setting in settings.findall('setting'):
			self.get_setting_entry(setting)

		for category in settings.findall('category'):
			self.get_category_entry(category)

	def get_category_entry(self, category):
		print_string(category.attrib.get('label'))

		for setting in category.findall('setting'):
			self.get_setting_entry(setting)

	def get_setting_entry(self, setting):
		print_string(setting.attrib.get('label'))

		entry_type = setting.attrib.get('type')

		if entry_type == 'enum':
			lvalues = setting.attrib.get('lvalues')
			for e in lvalues.split("|"):
				try:
					# ignore numbers
					x = int(e)
				except:
					print_string(e)

		elif entry_type == 'labelenum':
			values = setting.attrib.get('values')
			for e in values.split("|"):
				try:
					# ignore numbers
					x = int(e)
				except:
					print_string(e)

		elif entry_type == 'keyenum':
			values = setting.attrib.get('values')
			for e in values.split("|"):
				try:
					# ignore numbers
					x = int(e)
				except:
					print_string(e.split(';')[1])

if len(sys.argv) != 2:
	print("Usage: %s addon_path" % sys.argv[0])
	sys.exit(1)

SettingsXMLParser(os.path.join(sys.argv[1], 'resources', 'settings.xml')).parse()
