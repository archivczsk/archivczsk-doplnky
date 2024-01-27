#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os
import xml.etree.ElementTree as ET
import argparse
import subprocess
import zipfile
from itertools import zip_longest
from hashlib import md5

DEBUG=False
REPO_DIR='repo'

# ###########################################################################################################

def log_error(s):
	print('ERROR: ' + s, file=sys.stderr)

def log_warning(s):
	print('WARNING: ' + s, file=sys.stderr)

def log_info(s):
	print(s, file=sys.stdout)

def log_debug(s):
	if DEBUG:
		print(s, file=sys.stdout)

# ###########################################################################################################

class XmlOnlyAddon(object):
	def __init__(self, xml_root):
		self.xml_root = xml_root
		self.hash = self.xml_root.attrib.get('hash','')
		self.addon_id = self.xml_root.attrib.get('id')
		self.name = self.xml_root.attrib.get('name')
		self.version = self.xml_root.attrib.get('version')
		self.broken_msg = None

		for e in self.xml_root.findall('extension'):
			if e.attrib.get('point') == 'archivczsk.addon.metadata':
				self.broken_msg = e.findtext('broken')

		if self.addon_id == None or self.name == None or self.version == None:
			raise Exception('Some of mandatory attributes (id, name, version) in file %s missing' % self.addon_xml_file)

	# ###########################################################################################################

	def __hash__(self):
		return hash((self.addon_id, self.name, self.version))

	# ###########################################################################################################

	def write_xml(self, file):
		ET.ElementTree(element=self.xml_root).write(file, encoding='UTF-8', xml_declaration=True)

	# ###########################################################################################################

	def get_xml_data(self):
		return ET.tostring(self.xml_root, encoding='utf-8').decode('utf-8')

	# ###########################################################################################################

	def get_simple_xml_root(self):
		e = ET.Element('addon', {
			'id': self.addon_id,
			'name': self.name,
			'version': self.version,
			'hash': self.hash
		})
		e.tail = '\n'

		if self.broken_msg != None:
			s = ET.SubElement(e, 'extension', attrib={'point': 'archivczsk.addon.metadata'})
			s = ET.SubElement(s, 'broken')
			s.text = self.broken_msg

		return e

# ###########################################################################################################

class Addon(XmlOnlyAddon):
	lang_codes = ('cs', 'sk')

	def __init__(self, addon_dir=None):
		self.addon_dir = addon_dir
		self.addon_xml_file = os.path.join(self.addon_dir, 'addon.xml')

		XmlOnlyAddon.__init__(self, ET.parse(self.addon_xml_file).getroot())
		self.hash = self.get_addon_data_hash()

	# ###########################################################################################################

	def get_addon_files(self, files_only=True):
		if files_only:
			files = []
		else:
			files = [self.addon_dir + '/']

		for dirpath,dirs,filenames in os.walk(self.addon_dir):
			if dirpath.endswith('.git'):
				continue

			if files_only == False:
				for f in dirs:
					files.append(os.path.join(dirpath, f) + '/')

			for f in filenames:
				files.append(os.path.join(dirpath, f))

		return sorted(files)

	# ###########################################################################################################

	def get_addon_data_hash(self):
		m = md5()
		for file in self.get_addon_files():
			if not self.is_filtered(file, extra=('.mo',)):
				with open(file, 'rb') as f:
					for data in iter(lambda: f.read(8192), b''):
						m.update(data)

		return m.hexdigest()

	# ###########################################################################################################

	def build_lang_files(self):
		for l in self.lang_codes:
			lang_dir = os.path.join(self.addon_dir, 'resources', 'language')
			src_file = os.path.join(lang_dir, l + '.po')
			if os.path.isfile(src_file):
				lang_out_dir = os.path.join(lang_dir, l, 'LC_MESSAGES')
				os.makedirs(lang_out_dir, exist_ok=True)
				subprocess.check_call( ['msgfmt', src_file, '-o', os.path.join(lang_out_dir, self.addon_id + '.mo')] )

	# ###########################################################################################################

	def clean_lang_files(self):
		for l in self.lang_codes:
			lang_dir = os.path.join(self.addon_dir, 'resources', 'language')
			src_file = os.path.join(lang_dir, l + '.po')
			if os.path.isfile(src_file):
				lang_out_dir = os.path.join(lang_dir, l, 'LC_MESSAGES')
				try:
					os.remove(os.path.join(lang_out_dir, self.addon_id + '.mo'))
				except:
					pass

				try:
					os.rmdir(lang_out_dir)
				except:
					pass

				try:
					os.rmdir(os.path.join(lang_dir, l))
				except:
					pass

	# ###########################################################################################################

	def is_filtered(self, file, extra=()):
		if file.startswith('.') or os.path.basename(file).startswith('.'):
			return True

		for ext in ('.pyo', '.pyc', '.swo', '.swn', '.swc', '.so') + extra:
			if file.endswith(ext):
				return True

		return False

	# ###########################################################################################################

	def create_release_zip(self):
		self.build_lang_files()
		output_dir=os.path.join(REPO_DIR, self.addon_id)
		os.makedirs(output_dir, exist_ok=True)
		with zipfile.ZipFile( os.path.join(output_dir, self.addon_id + '-' + self.version + '.zip'), mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
			for file in self.get_addon_files(files_only=False):
				if not self.is_filtered(file, extra=('.po', 'atk_client.py')):
					z.write(file)
			pass

		self.clean_lang_files()

	# ###########################################################################################################

	def clean_old_zip(self, keep_current=True):
		current_zip = self.addon_id + '-' + self.version + '.zip'
		addon_repo_dir = os.path.join(REPO_DIR, self.addon_id)

		for file in os.listdir(addon_repo_dir):
			if file.startswith(self.addon_id) and file.endswith('.zip') and (keep_current == False or file != current_zip):
				log_debug("Removing old release zip for addon %s (%s): %s" % (self.name, self.addon_id, file))
				os.remove(os.path.join(addon_repo_dir, file))

		if keep_current == False:
			try:
				os.rmdir(addon_repo_dir)
			except:
				pass

	# ###########################################################################################################

	def check_git_status(self):
		if subprocess.check_output( ['git', 'status', '--porcelain', self.addon_dir] ) != b'':
			raise Exception('Addon %s (%s) has uncommited changes in directory %s' % (self.name, self.addon_id, self.addon_dir))

	# ###########################################################################################################

	def add_to_git_index(self):
		addon_repo_dir = os.path.join(REPO_DIR, self.addon_id)
		subprocess.check_call( ['git', 'add', addon_repo_dir] )

	# ###########################################################################################################

	def check_changelog(self):
		ret = None
		for name in ('changelog.txt', 'Changelog.txt'):
			changelog_file = os.path.join(self.addon_dir, name)
			log_debug("Checking for changelog file %s" % changelog_file)
			if os.path.isfile(changelog_file):
				with open(changelog_file, 'r') as f:
					i = 0
					for l in f.readlines():
						if self.version in l:
							log_debug("Version %s found on line %d" % (self.version, i))
							ret = True
							break
						i += 1
						if i > 10:
							ret = False
							break
				break

		return ret

	# ###########################################################################################################

# ###########################################################################################################

class ArchivczskAddonsReleaser(object):
	def __init__(self, addon_dirs=[], force=False, git_nocheck=False, check_only=False):
		self.addon_dirs = addon_dirs
		self.force = force
		self.git_nocheck = git_nocheck
		self.check_only = check_only

	# ###########################################################################################################

	def run(self):
		log_info('Checking, if there are uncommited changes in git staging index ...')
		self.check_git_staged_status()

		log_info('Searching for available addons ...')
		available_addons = self.get_available_addons()

		log_info('Reading released addons ...')
		released_addons = self.get_released_addons()

		log_info('Comparing addons data ...')
		updated_addons, del_addons = self.compare_addons(available_addons, released_addons)

		need_commit = False
		if self.git_nocheck == False:
			log_debug('Checking for uncommited changes in git ...')
			self.check_git_status(updated_addons)

		for addon in updated_addons:
			ck = addon.check_changelog()
			if ck == None:
				log_warning("There is no changelog file for addon %s (%s)" % (addon.name, addon.addon_id) )
			elif ck == False:
				log_warning("There is no info about version %s in the changelog file of addon %s (%s)" % (addon.version, addon.name, addon.addon_id) )

			if self.check_only:
				log_info("New release zip file for addon %s (%s) version %s will be created" % (addon.name, addon.addon_id, addon.version))
			else:
				need_commit = True
				log_info("Creating release zip file for addon %s (%s) version %s" % (addon.name, addon.addon_id, addon.version))
				addon.create_release_zip()
				addon.clean_old_zip()
				addon.add_to_git_index()

		for addon in del_addons:
			if self.check_only:
				log_info("Release zip file for addon %s (%s) version %s will be removed" % (addon.name, addon.addon_id, addon.version))
			else:
				need_commit = True
				log_info("Removing release zip file for addon %s (%s) version %s" % (addon.name, addon.addon_id, addon.version))
				addon.clean_old_zip(keep_current=False)
				addon.add_to_git_index()

		if need_commit:
			log_info("Rebuilding addons.xml ...")
			if len(self.addon_dirs) == 0:
				# user has not specified addons to release, so write addons.xml from all available addons
				self.write_addons_xml(available_addons.values())
			else:
				# user has specified addons to release, so merge user specified with released and write new addons.xml
				addons = released_addons.copy()
				addons.update(available_addons)
				self.write_addons_xml(addons.values())

			log_info("Commiting changes to git ...")
			subprocess.check_call( ['git', 'add', 'addons.xml'] )
			self.commit_to_git(updated_addons, del_addons)

			log_info('New release prepared. Use "git push" to send new addons versions to the wild world and hope for the best :-)')
		elif not self.check_only:
			log_info("No addons needing update found - nothing to do ...")

	# ###########################################################################################################

	def check_git_status(self, addons):
		for addon in addons:
			addon.check_git_status()

	# ###########################################################################################################

	def check_git_staged_status(self):
		for line in subprocess.check_output( ['git', 'status', '--porcelain'] ).splitlines():
			if not line.startswith(b' ') and not line.startswith(b'?'):
				raise Exception("You have uncommited changes in git staged index. Staged index must be clean before you run this script.")

	# ###########################################################################################################

	def commit_to_git(self, updated_addons, del_addons):
		message = ['release\n']

		for addon in updated_addons:
			message.append("%s (%s) version %s" % (addon.name, addon.addon_id, addon.version))

		for addon in del_addons:
			message.append("REMOVED %s (%s) version %s" % (addon.name, addon.addon_id, addon.version))

		if DEBUG:
			# check_call() will print command output to stdout, while check_output() will suppress it
			subprocess.check_call( ['git', 'commit', '-m', '\n'.join(message)] )
		else:
			subprocess.check_output( ['git', 'commit', '-m', '\n'.join(message)] )

	# ###########################################################################################################

	def check_version(self, local, remote, compare_postfix=True):
		'''
		Returns True if local version is lower then remote = update is needed
		Supports tilde (~) at the end of the version string (eg. 1.2.3~4).
		Version with ~ is beta one, so it's value is always considered lower then version without ~
		Examples:
		1.2.3 < 1.2.4
		1.2 < 1.2.1
		1.2 == 1.2.0
		1.2.1 > 1.2
		1.2.3~4 < 1.2.3
		1.2.3~4 > 1.2.4~3
		'''

		# extract postfix from version string
		if '~' in local:
			local, postfix_local = local.split('~')
		else:
			postfix_local = None

		if '~' in remote:
			remote, postfix_remote = remote.split('~')
		else:
			postfix_remote = None

		# split versions by dots, convert to int and compare each other
		local = [int(i) for i in local.split('.')]
		remote = [int(i) for i in remote.split('.')]

		for l, r in zip_longest(local, remote, fillvalue=0):
			if l == r:
				continue
			else:
				return l < r

		# versions are the same, so check for postfix (after ~)
		if compare_postfix:
			if postfix_remote is not None and postfix_local is not None:
				return int(postfix_local) < int(postfix_remote)
			elif postfix_local is not None:
				# local has postfix, so version is lower then remote without postfix
				return True

		# remote has postfix or no versions have them, so locale version is not lower then remote
		return False

	# ###########################################################################################################

	def compare_addons(self, available_addons, released_addons):
		newer_addons = []
		del_addons = []
		available_ids = []

		for aid, aa in available_addons.items():
			ra = released_addons.get(aid)

			if ra == None:
				# addon was never released before
				newer_addons.append(aa)
				log_debug("Addon %s (%s) version %s was never released before" % (aa.name, aa.addon_id, aa.version))
			else:
				# check if available addon has newer version
				ver_check_result = self.check_version(ra.version, aa.version)
				if self.force or ver_check_result:
					newer_addons.append(aa)
					if ver_check_result:
						log_debug("Addon %s (%s) needs new release: %s > %s" % (aa.name, aa.addon_id, aa.version, ra.version))
					else:
						log_debug("Addon %s (%s) release forced for version: %s" % (aa.name, aa.addon_id, aa.version))
				elif ra.hash != aa.hash:
					log_warning("Addon %s (%s) data changed, but version is not updated" % (aa.name, aa.addon_id))

				available_ids.append(aid)

		if len(self.addon_dirs) == 0:
			for aid in set(set(sorted(released_addons.keys())) - set(sorted(available_ids))):
				a = released_addons[aid]
				log_debug("Addon %s (%s) version %s is not available anymore and will be removed from release" % (a.name, a.addon_id, a.version))
				del_addons.append(a)

		return newer_addons, del_addons

	# ###########################################################################################################

	def get_available_addons(self):
		addons = {}
		addon_dirs = self.addon_dirs[:]

		ignore_os_error = False
		if len(addon_dirs) == 0:
			ignore_os_error = True
			for d in sorted(os.listdir()):
				if os.path.isdir(d):
					addon_dirs.append(d)

		for addon_dir in addon_dirs:
			try:
				addon = Addon(addon_dir)
			except OSError:
				if ignore_os_error:
					pass
				else:
					raise Exception("No addon.xml file found in directory %s" % addon_dir )
			else:
				log_debug("Found addon: %s (%s) version %s" % (addon.name, addon.addon_id, addon.version))
				addons[addon.addon_id] = addon

		return addons

	# ###########################################################################################################

	def get_released_addons(self):
		addons = {}

		xml_root = ET.parse('addons.xml').getroot()

		for element in xml_root:
			addon = XmlOnlyAddon(element)
			log_debug("Readed addon: %s (%s) version %s" % (addon.name, addon.addon_id, addon.version))
			addons[addon.addon_id] = addon

		return addons

	# ###########################################################################################################

	def write_addons_xml(self, addons):
		root = ET.Element('addons')
		root.tail = '\n'
		root.text = '\n'
		for addon in addons:
			root.append(addon.get_simple_xml_root())

		ET.ElementTree(element=root).write('addons.xml', encoding='UTF-8', xml_declaration=True)

# ###########################################################################################################

def cmdl_parse():
	parser = argparse.ArgumentParser(prog='make_release', description='Releases new version of ArchivCZSK addons')
	parser.add_argument('addons', nargs='*', action='append', help="Name of addon directory to release (all, if omitted)")
	parser.add_argument('-c', '--check', default=False, action='store_true', help="Only check what needs to be done")
	parser.add_argument('-f', '--force', default=False, action='store_true', help="Rewrite addons update archive even if version has not changed")
	parser.add_argument('-n', '--nocheck', default=False, action='store_true', help="Don't check for uncommited changes in addon directory")
	parser.add_argument('-v', '--verbose', default=False, action='store_true', help="Print debug messages and tracebacks on errors")

	args = parser.parse_args()
	global DEBUG
	DEBUG=args.verbose
	return {
		'force': args.force,
		'git_nocheck': args.nocheck,
		'check_only': args.check,
		'addon_dirs': args.addons[0],
	}

# ###########################################################################################################

if __name__ == "__main__":
	settings = cmdl_parse()
	aar = ArchivczskAddonsReleaser(**settings)
	try:
		aar.run()
	except Exception as e:
		if DEBUG:
			raise
		else:
			log_error(str(e))
