# -*- coding: utf-8 -*-

import sys
from datetime import date, timedelta, datetime
import time
from .provider import CommonContentProvider
from ..string_utils import _I, _B, _C

try:
	from .archivczsk_provider import _
except:

	def _(string_id):
		return string_id

# #################################################################################################

class CPModuleTemplate():
	'''
	Base content provider module used as template for other modules
	'''

	def __init__(self, content_provider, module_name, plot=None, img=None):
		'''
		Initialises module.
		
		Arguments:
		content_provider - ModuleContentProvider class that will be used for content manipulation
		module_name - Name of module
		plot - Description that will be shown for that module
		img - Image that will be displayed for this module
		'''
		self.cp = content_provider
		self.module_name = module_name
		self.module_plot = plot
		self.module_img = img

	def _(self, s):
		'''
		Calls translate function from content provider
		'''
		return self.cp._(s)

	def add(self):
		'''
		This is called by ModuleContentProvider to add this module menu.
		Override this funcion if you don't want to add it to menu or want to do it based on some condition
		'''
		info_labels = {}
		if self.module_plot:
			info_labels['plot'] = self._(self.module_plot)

		self.cp.add_dir(self._(self.module_name), img=self.module_img, info_labels=info_labels, cmd=self.root)

	def root(self):
		''' You need to implement this to create module's root menu'''
		return

# #################################################################################################

class CPModuleLiveTV(CPModuleTemplate):
	'''
	Content provider module that implements Live TV base
	'''

	def __init__(self, content_provider, name=None, categories=False, plot=None, img=None):
		if not plot:
			plot = _('Here you will find list of Live TV channels')

		CPModuleTemplate.__init__(self, content_provider, name if name else _('Live TV'), plot, img)
		self.categories = categories

	# #################################################################################################

	def root(self):
		if self.categories:
			self.get_live_tv_categories()
		else:
			self.get_live_tv_channels()

	# #################################################################################################

	def get_live_tv_categories(self):
		'''
		Implement this function if you want to support categories for Live TV
		It should use self.add_live_tv_categoty() to add categories
		'''
		return

	# #################################################################################################

	def add_live_tv_category(self, title, cat_id, img=None, info_labels={}):
		''' Adds new live TV category to menu '''
		self.cp.add_dir(title, img, info_labels, cmd=self.get_live_tv_channels, cat_id=cat_id)

	# #################################################################################################

	def get_live_tv_channels(self, cat_id=None):
		'''
		Implement this function to get list of Live TV channels
		It should call self.cp.add_video() or self.cp.add_play() to add videos or resolved videos
		'''
		return

# #################################################################################################

class CPModuleArchive(CPModuleTemplate):
	'''
	Content provider module that implements archive base
	'''

	def __init__(self, content_provider, name=None, plot=None, img=None):
		if not plot:
			plot = _('Here you will find your channels archive')

		CPModuleTemplate.__init__(self, content_provider, name if name else _("Archive"), plot, img)
		self.days_of_week = (_('Monday'), _('Tuesday'), _('Wednesday'), _('Thursday'), 	_('Friday'), _('Saturday'), _('Sunday'))
		self.day_str = (_('day'), _('days2-4'), _('days5+'))
		self.hour_str = (_('hour'), _('hours2-4'), _('hours5+'))

	# #################################################################################################

	def root(self):
		self.get_archive_channels()

	# #################################################################################################

	def add_archive_channel(self, title, channel_id, archive_hours, img=None, info_labels={}):
		if archive_hours < 24:
			tsd = archive_hours
			tr_map = self.hour_str
		else:
			tsd = int(archive_hours // 24)
			tr_map = self.day_str

		if tsd == 1:
			dtext = tr_map[0]
		elif tsd < 5:
			dtext = tr_map[1]
		else:
			dtext = tr_map[2]

		self.cp.add_dir(title + _C('green', '  [%d %s]' % (tsd, dtext)), img, info_labels, cmd=self.get_archive_days_for_channels, channel_id=channel_id, archive_hours=archive_hours)

	# #################################################################################################

	def get_archive_channels(self):
		'''
		Implement this function to get list of Live TV channels
		It should call self.add_archive_channel()
		'''
		return

	# #################################################################################################

	def get_archive_days_for_channels(self, channel_id, archive_hours):
		'''
		Implement this function creates list days for channel_id (see params for self.add_archive_channel())
		'''
		if archive_hours < 24:
			return self.get_archive_program(channel_id, archive_day=(archive_hours * 60))

		for i in range(int(archive_hours // 24)):
			if i == 0:
				day_name = _("Today")
			elif i == 1:
				day_name = _("Yesterday")
			else:
				day = date.today() - timedelta(days=i)
				day_name = self.days_of_week[day.weekday()] + " " + day.strftime("%d.%m.%Y")

			self.cp.add_dir(day_name, cmd=self.get_archive_program, channel_id=channel_id, archive_day=i)

	# #################################################################################################

	def archive_day_to_datetime_range(self, archive_day, return_timestamp=False):
		"""
		Return datetime or timestamp range for archive day in form start, end
		"""

		if archive_day > 30:
			# archive day is in minutes
			from_datetime = datetime.now() - timedelta(minutes=archive_day)
			to_datetime = datetime.now()
		elif archive_day == 0:
			from_datetime = datetime.combine(date.today(), datetime.min.time())
			to_datetime = datetime.now()
		else:
			from_datetime = datetime.combine(date.today(), datetime.min.time()) - timedelta(days=archive_day)
			to_datetime = datetime.combine(from_datetime, datetime.max.time())

		if return_timestamp:
			from_ts = int(time.mktime(from_datetime.timetuple()))
			to_ts = int(time.mktime(to_datetime.timetuple()))
			return from_ts, to_ts
		else:
			return from_datetime, to_datetime

	# #################################################################################################

	def get_archive_program(self, channel_id, archive_day):
		'''
		Implement this function to list program for channel_id and archive day (0=today, 1=yesterday, ...)
		It should call self.cp.add_video() or self.cp.add_play() to add videos, or resolved videos to menu
		
		Special case: If archive_day > 30, then it should be interpreted as minutes back 
		'''
		return

# #################################################################################################


class CPModuleSearch(CPModuleTemplate):
	'''
	Content provider module that implements search base
	'''

	def __init__(self, content_provider, name=None, search_id='', plot=None, img=None):
		CPModuleTemplate.__init__(self, content_provider, name if name else _("Search"), plot, img)
		self.search_id = search_id

	# #################################################################################################

	def add(self):
		'''
		This is called by ModuleContentProvider to add this module menu.
		Override this funcion if you don't want to add it to menu or want to do it based on some condition
		'''
		info_labels = {}
		if self.module_plot:
			info_labels['plot'] = self._(self.module_plot)

		self.cp.add_search_dir(self._(self.module_name), search_id=self.search_id, img=self.module_img, info_labels=info_labels)

	# #################################################################################################


class ModuleContentProvider(CommonContentProvider):
	'''
	This provider implements simple module based system. The main point is, that this provider implements
	all the common part for all modules that will be used and each module implements only code related to it.
	With this concept no data or methods will be mixed between modules.
	Each used module should be child of CPModuleTemplate
	'''

	def __init__(self, name='dummy', settings=None, data_dir=None, bgservice=None, modules=[]):
		CommonContentProvider.__init__(self, name, settings, data_dir, bgservice)
		self.modules = modules

	# #################################################################################################

	def root(self):
		for module in self.modules:
			module.add()

	# #################################################################################################

	def run_shortcut(self, action, kwargs):
		'''
		Tries to search for right module to run shortcut.
		'''
		self.log_info("Trying to run shortcut: %s" % action)
		qualname = None

		if action.startswith('<bound method '):
			qualname = action.split(' ')[2]
			modulename = action.split(' ')[4][1:]

		if not qualname or not modulename:
			self.log_debug("Can't get qualname of action - givig up")
			return

		self.log_debug("Full qualname of action: %s" % qualname)
		self.log_debug("Full module name of action: %s" % modulename)

		# extract class name and method
		modulename, class_name = modulename.rsplit('.', 1)
		method = qualname.split('.')[1]

		# check if class is child of this provider
		if isinstance(self, getattr(sys.modules[modulename], class_name)):
			# run the action
			getattr(self, method)(**eval(kwargs))
			return

		shortcut_class = getattr(sys.modules[modulename], class_name)

		# search for right class in registered modules
		for module in [self] + self.modules:
			if isinstance(module, shortcut_class):
				self.log_debug("Running shortcut action on class %s" % module.__class__.__name__)
				# run the action
				getattr(module, method)(**eval(kwargs))
				break
		else:
			self.log_error("Class name %s is not child of any registered modules - giving up" % class_name)

