# -*- coding: utf-8 -*-
"""
M3UMappingOverride - load and apply an e2m3u2bouquet-compatible
mapping XML to reorder, rename, disable categories and channels.

Example mapping XML (compatible with e2m3u2bouquet):

  <mapping>
    <categories>
      <category name="News" nameOverride="📰 News" enabled="true"/>
      <category name="Adult" enabled="false"/>
    </categories>
    <channels>
      <channel name="Markiza HD" nameOverride="" tvg-id="markiza.sk"
               enabled="true" category="None"
               serviceRef="1:0:1:1:08cf:d919:0:0:0:0"
               clearStreamUrl="false"/>
    </channels>
  </mapping>

The file is searched in:
  /etc/enigma2/m3u-sort-override.xml    (custom path also allowed)

Python 2.7 + Python 3.x compatible.
"""

from __future__ import absolute_import, unicode_literals, print_function

import os

try:
	from xml.etree.cElementTree import parse as et_parse
except ImportError:
	from xml.etree.ElementTree import parse as et_parse


class M3UMappingOverride(object):
	"""
	Loads mapping XML and offers methods to filter/reorder categories
	and channel lists produced by M3UProvider.
	"""

	def __init__(self, path=None, log=None):
		self.path = path
		self.log = log or (lambda *a, **k: None)
		self._cat_rules = []        # list of dicts in declared order
		self._cat_index = {}        # name -> rule dict
		self._chan_rules = {}       # (name, category) -> rule dict
		self._chan_rules_by_name = {}  # name -> list of rule dicts
		self._loaded = False

	def load(self):
		if not self.path or not os.path.exists(self.path):
			self.log('[M3U-map] No mapping file at %s' % self.path)
			return False
		try:
			tree = et_parse(self.path)
		except Exception as e:
			self.log('[M3U-map] Parse failed: %s' % e)
			return False

		root = tree.getroot()

		# Categories block
		for cat in root.findall('.//categories/category'):
			rule = {
				'name': cat.get('name', '').strip(),
				'name_override': cat.get('nameOverride', '').strip(),
				'enabled': cat.get('enabled', 'true').lower() != 'false',
			}
			if rule['name']:
				self._cat_rules.append(rule)
				self._cat_index[rule['name']] = rule

		# Channels block
		for ch in root.findall('.//channels/channel'):
			rule = {
				'name': ch.get('name', '').strip(),
				'name_override': ch.get('nameOverride', '').strip(),
				'tvg_id_override': ch.get('tvg-id', '').strip(),
				'enabled': ch.get('enabled', 'true').lower() != 'false',
				'category': ch.get('category', '').strip(),
				'category_override': ch.get('categoryOverride', '').strip(),
				'service_ref_override': ch.get('serviceRef', '').strip(),
				'clear_stream_url': ch.get('clearStreamUrl', 'false').lower() == 'true',
			}
			if rule['name']:
				key = (rule['name'], rule['category'])
				self._chan_rules[key] = rule
				self._chan_rules_by_name.setdefault(rule['name'], []).append(rule)

		self._loaded = True
		self.log('[M3U-map] Loaded %d category rules, %d channel rules' %
		         (len(self._cat_rules), len(self._chan_rules)))
		return True

	# ------------------ Filtering API ------------------

	def filter_and_order_categories(self, source_categories):
		"""
		Given the natural category order from the M3U, apply mapping rules:
		  - drop disabled categories
		  - reorder per XML declared order (XML order wins for listed cats)
		  - append unmapped categories at the end (preserving M3U order)
		Returns list of (orig_name, display_name).
		"""
		if not self._loaded:
			return [(c, c) for c in source_categories]

		src_set = set(source_categories)
		result = []
		seen = set()

		# Emit in XML order for categories present in source
		for rule in self._cat_rules:
			n = rule['name']
			if not rule['enabled']:
				continue
			if n in src_set:
				display = rule['name_override'] or n
				result.append((n, display))
				seen.add(n)

		# Append any categories from M3U not mentioned in XML
		for c in source_categories:
			if c not in seen and c not in self._cat_index:
				result.append((c, c))
			elif c not in seen and c in self._cat_index:
				# explicitly disabled - skip
				pass

		return result

	def apply_channel_rule(self, channel):
		"""
		Apply per-channel overrides in-place. Returns:
		  True   -> keep channel
		  False  -> drop channel (disabled)
		"""
		if not self._loaded:
			return True

		name = channel.get('name', '')
		cat = channel.get('group', '')

		rule = self._chan_rules.get((name, cat))
		if rule is None:
			# also try matching by name only (without category)
			cands = self._chan_rules_by_name.get(name) or []
			if cands:
				rule = cands[0]

		if rule is None:
			return True

		if not rule['enabled']:
			return False

		if rule['name_override']:
			channel['name'] = rule['name_override']
		if rule['category_override']:
			channel['group'] = rule['category_override']
		if rule['service_ref_override']:
			# Forced service ref - bouquet writer can prepend ':URL:Name' if needed
			channel['_forced_service_ref'] = rule['service_ref_override']
		if rule['clear_stream_url']:
			# Channel will be written as marker only (no URL part)
			channel['_clear_stream_url'] = True

		return True


# -------------------------------------------------
# Smoke test
# -------------------------------------------------
if __name__ == '__main__':
	import sys
	if len(sys.argv) < 2:
		print('Usage: m3u_mapping.py <override.xml>')
		sys.exit(1)
	m = M3UMappingOverride(path=sys.argv[1], log=print)
	m.load()
	print('Categories rules:', m._cat_rules)
	print('Total channel rules:', len(m._chan_rules))
