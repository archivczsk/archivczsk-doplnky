import re
import os
import io

try:
	basestring
	def py2_decode_utf8( str ):
		return str.decode('utf-8')
	
except:
	def py2_decode_utf8( str ):
		return str
	
try:
	import unidecode
	
	def strip_accents(s):
		return unidecode.unidecode(s)
except:
	import unicodedata
	
	def strip_accents(s):
		return ''.join(c for c in unicodedata.normalize('NFD', py2_decode_utf8(s)) if unicodedata.category(c) != 'Mn')

class TransponderS():
	def __init__(self):
		self.Frequency = 0x0  # In Hertz
		self.SymbolRateBPS = 0x0  # Symbol rate in bits per second.
		# 0=Horizontal, 1=Vertical, 2=Circular Left, 3=Circular right.
		self.Polarization = 0x0
		self.FEC = 0x0	# FEC_Auto=0, FEC_1_2=1, FEC_2_3=2, FEC_3_4=3, FEC_5_6=4, FEC_7_8=5, FEC_8_9=6, FEC_3_5=7, FEC_4_5=8, FEC_9_10=9, FEC_6_7=10, FEC_None=15
		# in degrees East: 130 is 13.0E, 192 is 19.2E. Negative values are West -123 is 12.3West.
		self.OrbitalPosition = 0x0
		self.Inversion = 0x0  # Inversion_Off, Inversion_On, Inversion_Unknown
		# Flags (Only in version 4): Field is absent in version 3.
		self.Flags = 0x0
		self.System = 0x0  # System_DVB_S, System_DVB_S2
		self.Modulation = 0x0  # 0 - Modulation_Auto, 1 - Modulation_QPSK, 2 - Modulation_8PSK, 3 - Modulation_QAM16, 4 - Modulation_16APSK, 5 - Modulation_32APSK
		# (Only used in DVB-S2): RollOff_alpha_0_35, RollOff_alpha_0_25, RollOff_alpha_0_20, RollOff_auto
		self.Rolloff = 0x0
		# (Only used in DVB-S2): Pilot_Off, Pilot_On, Pilot_Unknown
		self.Pilot = 0x0

	def ReadData(self, Line):
		DataLine = Line.split(":")
#		 print("Parsing line: " + Line)

		if DataLine:
			try:
				self.Frequency = int(DataLine[0])
				self.SymbolRateBPS = int(DataLine[1])
				self.Polarization = int(DataLine[2])
				self.FEC = DataLine[3]
				self.OrbitalPosition = int(DataLine[4])
				self.Inversion = int(DataLine[5])
				self.Flags = int(DataLine[6])
				self.System = int(DataLine[7])
				self.Modulation = int(DataLine[8])
				self.Rolloff = int(DataLine[9])
				self.Pilot = int(DataLine[10])
			except IndexError:
				return
		else:
			raise


class Transponder():
	def __init__(self):
		self.DVBNameSpace = 0x0
		self.TransportStreamID = 0x0
		self.OriginalNetworkID = 0x0
		# Satellite DVB ( s ), Terestrial DVB ( t ), Cable DVB ( c )
		self.Type = ''
		self.Data = None

	def ReadHeader(self, Line):
		HeaderLine = re.match(r"([\d\w]+):([\d\w]+):([\d\w]+)", Line)
		if HeaderLine:
			self.DVBNameSpace = int(HeaderLine.group(1), 16)
			self.TransportStreamID = int(HeaderLine.group(2), 16)
			self.OriginalNetworkID = int(HeaderLine.group(3), 16)
		else:
			raise

	def ReadData(self, Line):
		DataLine = re.match(r"([stc]) ([\d\w:-]+)", Line)
		if DataLine:
			self.Type = DataLine.group(1)
			if self.Type == 's':
				self.Data = TransponderS()
				self.Data.ReadData(DataLine.group(2))


class Service():
	def __init__(self):
		self.ServiceID = 0x0
		self.ServiceType = 0x0
		self.ServiceNumber = 0x0
		self.Transponder = None
		self.ChannelName = None
		self.Provider = None

	def ReadData(self, Line):
		DataLine = Line.split(":")

		if DataLine:
			try:
				self.ServiceID = int(DataLine[0], 16)
				self.ServiceType = int(DataLine[4], 16)
				self.ServiceNumber = int(DataLine[5], 16)
			except IndexError:
				return None, None, None
		return int(DataLine[1], 16), int(DataLine[2], 16), int(DataLine[3], 16)

	def ReadChannelName(self, Line):
		self.ChannelName = Line.strip()

	def ReadProvider(self, Line):
		self.Provider = Line


class lameDB():
	def __init__(self, Path):
		if Path == None:
			return
		self.Transponders = []
		self.Services = {}
		self.Open(Path)

	def getOrbitals(self):
		data = set()
		for transponder in self.Transponders:
			data.add(transponder.Data.OrbitalPosition)

		return list(data)

	def Open(self, Path):
		try:
			self._file = open(Path, encoding='utf-8', mode="r", errors='ignore')
		except:
			self._file = io.open(Path, encoding='utf-8', mode="r", errors='ignore')

		self._read()

	def _read(self):
		self._checkheader()
		self._readTranspondersSection()
		self._readServiceSection()

	def _checkheader(self):
		HeaderLine = re.match(r"eDVB services /(4)/", self._file.readline())

		if HeaderLine:
			self._version = HeaderLine.group(1)
		else:
			raise

	def _readTranspondersSection(self):
		transpondersLine = self._file.readline().strip()
		if transpondersLine != 'transponders':
			raise

		while True:
			Line = self._file.readline().strip()
			if Line == 'end':
				break

			transponder = Transponder()
			transponder.ReadHeader(Line)
			transponder.ReadData(self._file.readline().strip())

			self.Transponders.append(transponder)

			if self._file.readline().strip() != '/':
				raise

	def name_normalise( self, name ):
		name = strip_accents( name ).lower()

		name = name.replace("television", "tv")
		name = name.replace("(bonus)", "").strip()
		name = name.replace("eins", "1")
		
		if name.endswith(" hd"):
			name = name[:name.rfind(" hd")]

		if name.endswith(" tv"):
			name = name[:name.rfind(" tv")]
		
		if name.startswith("tv "):
			name = name[3:]

		if name.endswith(" channel"):
			name = name[:name.rfind(" channel")]

		name = name.replace("&", " and ").replace("'", "").replace(".", "").replace(" ", "")
		return name

	def _readServiceSection(self):
		transpondersLine = self._file.readline().strip()
		if transpondersLine != 'services':
			raise

		while True:
			Line = self._file.readline().strip()
			if Line == 'end':
				break

			service = Service()
			DVBNameSpace, TransportStreamID, OriginalNetworkID = service.ReadData(
				Line)

			service.ReadChannelName(self._file.readline().strip())
			service.ReadProvider(self._file.readline().strip())

			for transponder in self.Transponders:
				if transponder.DVBNameSpace == DVBNameSpace and transponder.TransportStreamID == TransportStreamID and transponder.OriginalNetworkID == OriginalNetworkID:
					service.Transponder = transponder
					break

			if service.Transponder == None:
				continue

			name = self.name_normalise( service.ChannelName )
			
			if name not in self.Services:
				self.Services[name] = []
				
			self.Services[name].append(service)
		return
