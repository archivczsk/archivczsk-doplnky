from Plugins.Extensions.archivCZSK.archivczsk import ArchivCZSK

class FakeYtConfig(object):
	def __init__(self, value=None):
		self.fake_value = value
		self.addon_settings = None

	def set_addon_settings(self, addon_settings):
		self.addon_settings = addon_settings

	def get_setting(self, name):
		if isinstance(self.addon_settings, dict):
			return self.addon_settings.get(name)

		if self.addon_settings is not None:
			addon_settings = self.addon_settings
		else:
			addon_settings = ArchivCZSK.get_addon('plugin.video.yt').settings
		return addon_settings.get_setting(name)

	def __getattr__(self, name):
		if name == 'value':
			return self.fake_value
		elif name == 'maxResolution':
			return FakeYtConfig(self.get_setting('max_resolution') or '37')
		elif name == 'searchLanguage':
			return FakeYtConfig(None)
		elif name == 'useDashMP4':
			return FakeYtConfig(self.get_setting('auto_used_player') == '2')
		else:
			return self

config = FakeYtConfig()
