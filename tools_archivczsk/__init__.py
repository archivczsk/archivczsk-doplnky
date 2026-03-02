# fix updater in ArchivCZSK 3.5.4

try:
	from Plugins.Extensions.archivCZSK.version import version

	if version == '3.5.4':
		# this version has broken archiv updater - do monkey patch to fix it
		from Plugins.Extensions.archivCZSK.engine.tools.logger import log
		from Plugins.Extensions.archivCZSK.engine.tools import util
		from Plugins.Extensions.archivCZSK.engine.updater import ArchivUpdater

		def checkUpdateStarted_fixed(self):
			xmlroot = self.downloadUpdateXml()

			if xmlroot != None:
				local_version = version
				self.remote_version = xmlroot.attrib.get('version') or '0'
				self.remote_date = xmlroot.attrib.get('date')

				log.logDebug("ArchivUpdater remote date: '%s'" % self.remote_date )
				log.logDebug("ArchivUpdater version local/remote: %s/%s" % (local_version, self.remote_version))

				if util.check_version(local_version, self.remote_version):
					self.needUpdate = True
				else:
					self.needUpdate = False

			self.run_next(self.checkUpdateFinished, "New version found" if self.needUpdate else "No update found")

		log.info("Installing fixed version of checkUpdateStarted")
		ArchivUpdater.checkUpdateStarted = checkUpdateStarted_fixed

except:
	import traceback
	print( traceback.format_exc() )
