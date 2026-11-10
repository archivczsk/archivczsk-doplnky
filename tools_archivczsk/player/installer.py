# -*- coding: utf-8 -*-

from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.client import config, log
from Plugins.Extensions.archivCZSK.engine.tools.stbinfo import stbinfo
import os, traceback

EXTEPLAYER3_BIN_PATH = '/usr/bin/exteplayer3'
EXTEPLAYER3_BIN_BACKUP_PATH = '/usr/bin/exteplayer3.backup'

EXTEPLAYER3_LIB_PATH = '/usr/lib/exteplayer3_deps'
EXTEPLAYER3_LIB_BACKUP_PATH = '/usr/lib/exteplayer3_deps.backup'

def get_archivczsk_exteplayer3_dir():
	if stbinfo.hw_arch in ('armv7l', 'mips', 'aarch64'):
		tools_player_addon = ArchivCZSK.get_addon('tools.player.%s' % stbinfo.hw_arch)
		if tools_player_addon:
			return os.path.join(tools_player_addon.path, 'bin')

	return None

def install_exteplayer3():
	archivczsk_exteplayer3_dir = get_archivczsk_exteplayer3_dir()
	if not archivczsk_exteplayer3_dir or not os.path.isdir(archivczsk_exteplayer3_dir):
		log.debug('No ArchivCZSK exteplayer3 binary found for this architecture: %s' % stbinfo.hw_arch)
		return

	if os.path.isfile(EXTEPLAYER3_BIN_PATH):
		log.info('Renaming original exteplayer3 binary to %s' % EXTEPLAYER3_BIN_BACKUP_PATH)
		os.rename(EXTEPLAYER3_BIN_PATH, EXTEPLAYER3_BIN_BACKUP_PATH)
	elif os.path.islink(EXTEPLAYER3_BIN_PATH):
		log.info('Removing existing symlink for exteplayer3 binary')
		os.unlink(EXTEPLAYER3_BIN_PATH)
	elif os.path.exists(EXTEPLAYER3_BIN_PATH):
		log.error('Existing exteplayer3 binary is not a file or symlink, skipping installation')
		return
	else:
		log.info('No existing exteplayer3 binary found, proceeding with installation')

	log.info('Replacing installed exteplayer3 with ArchivCZSK version')
	os.symlink(os.path.join(archivczsk_exteplayer3_dir, 'exteplayer3'), EXTEPLAYER3_BIN_PATH)

	if os.path.isdir(EXTEPLAYER3_LIB_PATH):
		log.info('Renaming original exteplayer3 library path to %s' % EXTEPLAYER3_LIB_BACKUP_PATH)
		os.rename(EXTEPLAYER3_LIB_PATH, EXTEPLAYER3_LIB_BACKUP_PATH)

	log.info('Replacing installed exteplayer3 library path with ArchivCZSK version')
	if os.path.islink(EXTEPLAYER3_LIB_PATH):
		os.unlink(EXTEPLAYER3_LIB_PATH)

	os.symlink(archivczsk_exteplayer3_dir, EXTEPLAYER3_LIB_PATH)
	log.info('exteplayer3 installed successfully')

def uninstall_exteplayer3():
	if os.path.isfile(EXTEPLAYER3_BIN_BACKUP_PATH):
		log.info('Restoring installed exteplayer3 from ArchivCZSK version with original version')
		os.unlink(EXTEPLAYER3_BIN_PATH)
		os.rename(EXTEPLAYER3_BIN_BACKUP_PATH, EXTEPLAYER3_BIN_PATH)

		if os.path.isdir(EXTEPLAYER3_LIB_BACKUP_PATH):
			log.info('Restoring installed exteplayer3 library path from ArchivCZSK version with original version')
			os.unlink(EXTEPLAYER3_LIB_PATH)
			os.rename(EXTEPLAYER3_LIB_BACKUP_PATH, EXTEPLAYER3_LIB_PATH)

		log.info('exteplayer3 restored successfully')


def check_installed_exteplayer3(cfg_element=None):
	try:
		if config.plugins.archivCZSK.videoPlayer.replace_exteplayer3.value:
			if not os.path.islink(EXTEPLAYER3_BIN_PATH):
				install_exteplayer3()
		else:
			if os.path.islink(EXTEPLAYER3_BIN_PATH):
				uninstall_exteplayer3()
	except:
		log.error('Error by checking/reinstalling exteplayer3')
		log.error(traceback.format_exc())

def run_exteplayer3_check_service():
	addon = ArchivCZSK.get_addon('tools.archivczsk')
	addon.bgservice.run_in_loop('exteplayer3 check', 900, check_installed_exteplayer3)
	try:
		addon.add_global_change_notifier(config.plugins.archivCZSK.videoPlayer.replace_exteplayer3, check_installed_exteplayer3, initial_call=False, immediate_feedback=False)
	except:
		log.error(traceback.format_exc())
