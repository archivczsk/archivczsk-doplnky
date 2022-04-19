""" downloaded from http://xbmc-addons.googlecode.com/svn/addons/ """
""" addons.xml generator """

import os

try:
	from hashlib import md5
except:
	from md5 import new as md5

try:
	basestring
	
	def py2_encode( txt ):
		return txt.encode('utf-8')

	def py2_decode( txt ):
		return txt.decode('utf-8')
	
except NameError:
	def py2_decode( txt ):
		return txt

	def py2_encode( txt ):
		return txt
	
IGNORED = ['dev','repo','icons','test','hashes']

# let's keep ignored (not yet released) addons here
IGNORED += ['plugin.video.csfd-trailers']

class Generator:
	"""
		Generates a new addons.xml file from each addons addon.xml file
		and a new addons.xml.md5 hash file. Must be run from the root of
		the checked-out repo. Only handles single depth folder structure.
	"""
	def __init__( self ):
		# generate files
		self._generate_addons_file()
		self._generate_md5_file()
		# notify user
		print( "Finished updating addons xml and md5 files" )

	def _generate_addons_file( self ):
		# addon list
		addons = os.listdir( "." )
		# final addons text
		addons_xml = u"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<addons>\n"
		# loop thru and add each addons addon.xml file
		for addon in addons:
			try:
				# skip any file or .git folder
				if ( not os.path.isdir( addon ) or addon == ".git" or addon == ".settings" or addon in IGNORED ):
					continue
				
				# create path
				_path = os.path.join( addon, "addon.xml" )
				# split lines for stripping
				xml_lines = open( _path, "r" ).read().splitlines()
				# new addon
				addon_xml = ""
				# loop thru cleaning each line
				for line in xml_lines:
					# skip encoding format line
					if ( line.find( "<?xml" ) >= 0 ):
						continue
					# add line
					addon_xml += py2_decode( line.rstrip() + "\n" )
				# we succeeded so add to our final addons.xml text
				addons_xml += addon_xml.rstrip() + "\n\n"
			except Exception as e:
				# missing or poorly formatted addon.xml
				print( "Excluding %s for %s" % ( _path, e, ) )
		# clean and add closing tag
		addons_xml = addons_xml.strip() + u"\n</addons>\n"
		# save file
		self._save_file( py2_encode( addons_xml ), file="addons.xml" )

	def _generate_md5_file( self ):
		try:
			# create a new md5 hash
			m = md5( open( "addons.xml", 'rb' ).read() ).hexdigest()
			# save file
			self._save_file( m, file="addons.xml.md5" )
		except Exception as e:
			# oops
			print( "An error occurred creating addons.xml.md5 file!\n%s" % ( e, ) )

	def _save_file( self, data, file ):
		try:
			# write data to the file
			open( file, "w" ).write( data )
		except Exception as e:
			# oops
			print( "An error occurred saving %s file!\n%s" % ( file, e, ) )


if ( __name__ == "__main__" ):
	# start
	Generator()
