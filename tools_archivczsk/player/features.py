# -*- coding: utf-8 -*-
import os
import json
import subprocess
from Plugins.Extensions.archivCZSK.engine.tools.stbinfo import stbinfo
from Plugins.Extensions.archivCZSK.engine import client
from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK
from Plugins.Extensions.archivCZSK.engine.player.info import videoPlayerInfo
import traceback
__addon__ = ArchivCZSK.get_addon('tools.archivczsk')

def _(id):
	return __addon__.get_localized_string(id)

EXTEPLAYER3_NAME='exteplayer3_169'
FFMPEG_NAME='ffmpeg_169'

class PlayerFeatures(object):
	DATA_LOADED = False
	exteplayer3_version = None
	exteplayer3_cenc_params_supported = None
	exteplayer3_cenc_supported = None
	ffmpeg_mpd_supported = None
	ffmpeg_cenc_supported = None

	def __init__(self, reload=False):
		if PlayerFeatures.DATA_LOADED == False or reload:
			self.extract_exteplayer3_features()
			self.extract_ffmpeg_features()
			PlayerFeatures.DATA_LOADED = True
			client.log.debug("Player feature: exteplayer3_version = %s" % PlayerFeatures.exteplayer3_version )
			client.log.debug("Player feature: exteplayer3_cenc_supported = %s" % PlayerFeatures.exteplayer3_cenc_supported )
			client.log.debug("Player feature: exteplayer3_cenc_params_supported = %s" % PlayerFeatures.exteplayer3_cenc_params_supported )
			client.log.debug("Player feature: ffmpeg_mpd_supported = %s" % PlayerFeatures.ffmpeg_mpd_supported )
			client.log.debug("Player feature: ffmpeg_cenc_supported = %s" % PlayerFeatures.ffmpeg_cenc_supported )

	def extract_exteplayer3_features(self):
		try:
			try:
				data = subprocess.check_output(['exteplayer3'], shell=False, stderr=subprocess.STDOUT)
			except subprocess.CalledProcessError as ex:
				data = ex.output
			data = data.decode('utf-8')
			if data[-1:] == '\n':
				data = data[:-1]

			lines = list(map(lambda x: x.strip(), data.splitlines()))

			PlayerFeatures.exteplayer3_cenc_params_supported = '[-6 idx] video MPEG-DASH stream index cenc decryption key' in lines and '[-7 idx] audio MPEG-DASH stream index cenc decryption key' in lines
			PlayerFeatures.exteplayer3_version = json.loads(lines[0])['EPLAYER3_EXTENDED']['version']
			PlayerFeatures.exteplayer3_cenc_supported = PlayerFeatures.exteplayer3_version >= 168
		except:
			client.log.error(traceback.format_exc())
			return None

	def extract_ffmpeg_features(self):
		try:
			try:
				data = subprocess.check_output(['ffmpeg'], shell=False, stderr=subprocess.STDOUT)
			except subprocess.CalledProcessError as ex:
				data = ex.output
			data = data.decode('utf-8')
			if data[-1:] == '\n':
				data = data[:-1]

			cfg_line = list(filter(lambda x: x.lstrip().startswith('configuration:'), data.splitlines()))[0].split(':')[1]
			cfg = { c.strip().replace('"',"").replace("'",''): True for c in cfg_line.split(' ') }

			PlayerFeatures.ffmpeg_mpd_supported = '--enable-libxml2' in cfg and '--enable-demuxer=dash' in cfg
			PlayerFeatures.ffmpeg_cenc_supported = self.exteplayer3_cenc_supported and '-Wl,-rpath,/usr/lib/exteplayer3_deps' in cfg
		except:
			client.log.error(traceback.format_exc())
			return None

	@classmethod
	def download_and_install(cls, name):
		if stbinfo.hw_arch == 'armv7l':
			url = 'https://github.com/skyjet18/exteplayer3/raw/master/ipk/%s_armv7ahf.ipk' % name
		elif stbinfo.hw_arch == 'mips':
			url = 'https://github.com/skyjet18/exteplayer3/raw/master/ipk/%s_mips32el.ipk' % name
		else:
			return

		local_file = '/tmp/%s.ipk' % name

		try:
			subprocess.check_call(['curl', '-k', '-L', '-o', local_file, url])
			subprocess.check_call(['opkg', 'install', '--force-downgrade', '--force-depends', local_file])
		except:
			client.log.error(traceback.format_exc())

		if os.path.isfile(local_file):
			os.remove(local_file)

	@classmethod
	def request_ffmpeg_mpd_support(cls, content_provider):
		if cls.ffmpeg_mpd_supported == True:
			return

		if not videoPlayerInfo.serviceappAvailable:
			return

		if stbinfo.hw_arch not in ('armv7l', 'mips'):
			return

		if cls.ffmpeg_mpd_supported == None:
			msg = _('It was not possible to determine, if you have installed ffmpeg and if it can process MPEG-DASH streams needed by this addon.')
		else:
			msg = _("Installed version of ffmpeg probably doesn't support MPEG-DASH streams needed by this addon.")

		if content_provider.get_yes_no_input(msg + ' ' + _("It is recommended to install modified version of exteplayer3 and ffmpeg with build in support for MPEG-DASH and DRM streams.\nShould I download and install recommanded version for you?")) == True:
			cls.download_and_install(EXTEPLAYER3_NAME)
			cls.download_and_install(FFMPEG_NAME)
			PlayerFeatures(True)

	@classmethod
	def request_exteplayer3_cenc_support(cls, content_provider):
		return cls.request_exteplayer3_version(content_provider, 168)

	@classmethod
	def request_exteplayer3_version(cls, content_provider, req_version):
		if cls.exteplayer3_version is not None and cls.exteplayer3_version >= req_version:
			return

		if not videoPlayerInfo.serviceappAvailable:
			if stbinfo.is_dmm_image:
				content_provider.show_error(_("This addon is not supported on DMM image"))
			else:
				content_provider.show_error(_("You need to install ServiceApp in order to use this addon"))
			return

		if stbinfo.hw_arch not in ('armv7l', 'mips'):
			content_provider.show_error(_("Hardware platform of your receiver is not supported"))
			return

		if cls.exteplayer3_version == None:
			msg = _('It was not possible to determine, if you have installed exteplayer3 and if it provides features needed by this addon.')
		else:
			msg = _("Installed version of exteplayer3 doesn't support all features needed by this addon.")

		if content_provider.get_yes_no_input(msg + ' ' + _("It is recommended to install latest modified version of exteplayer3 and ffmpeg with build in all features needed.\nShould I download and install recommanded version for you?")) == True:
			cls.download_and_install(EXTEPLAYER3_NAME)
			cls.download_and_install(FFMPEG_NAME)
			PlayerFeatures(True)

PlayerFeatures()
