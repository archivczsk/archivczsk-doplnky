import struct
import base64

WIDEVINE_UUID = bytearray([237, 239, 139, 169, 121, 214, 74, 206, 163, 200, 39, 220, 213, 29, 33, 237])
WIDEVINE_PSSH = bytearray([112, 115, 115, 104])

def cenc_init(data=None, uuid=None, kids=None):
	data = data or bytearray()
	uuid = uuid or WIDEVINE_UUID
	kids = kids or []

	length = len(data) + 32

	if kids:
		#each kid is 16 bytes (+ 4 for kid count)
		length += (len(kids) * 16) + 4

	init_data = bytearray(length)
	pos = 0

	# length (4 bytes)
	r_uint32 = struct.pack(">I", length)
	init_data[pos:pos+len(r_uint32)] = r_uint32
	pos += len(r_uint32)

	# pssh (4 bytes)
	init_data[pos:pos+len(r_uint32)] = WIDEVINE_PSSH
	pos += len(WIDEVINE_PSSH)

	# version (1 if kids else 0)
	r_uint32 = struct.pack("<I", 1 if kids else 0)
	init_data[pos:pos+len(r_uint32)] = r_uint32
	pos += len(r_uint32)

	# uuid (16 bytes)
	init_data[pos:pos+len(uuid)] = uuid
	pos += len(uuid)

	if kids:
		# kid count (4 bytes)
		r_uint32 = struct.pack(">I", len(kids))
		init_data[pos:pos+len(r_uint32)] = r_uint32
		pos += len(r_uint32)

		for kid in kids:
			# each kid (16 bytes)
			init_data[pos:pos+len(uuid)] = kid
			pos += len(kid)

	# length of data (4 bytes)
	r_uint32 = struct.pack(">I", len(data))
	init_data[pos:pos+len(r_uint32)] = r_uint32
	pos += len(r_uint32)

	# data (X bytes)
	init_data[pos:pos+len(data)] = data
	pos += len(data)

	return base64.b64encode(init_data).decode('utf8')

def parse_cenc_init(b64string):
	init_data = bytearray(base64.b64decode(b64string))
	pos = 0

	# length (4 bytes)
	r_uint32 = init_data[pos:pos+4]
	length, = struct.unpack(">I", r_uint32)
	pos += 4

	# pssh (4 bytes)
	r_uint32 = init_data[pos:pos+4]
	pssh, = struct.unpack(">I", r_uint32)
	pos += 4

	# version (4 bytes) (1 if kids else 0)
	r_uint32 = init_data[pos:pos+4]
	version, = struct.unpack("<I", r_uint32)
	pos += 4

	# uuid (16 bytes)
	uuid = init_data[pos:pos+16]
	pos += 16

	kids = []
	if version == 1:
		# kid count (4 bytes)
		r_uint32 = init_data[pos:pos+4]
		num_kids, = struct.unpack(">I", r_uint32)
		pos += 4

		for i in range(num_kids):
			# each kid (16 bytes)
			kids.append(init_data[pos:pos+16])
			pos += 16

	# length of data (4 bytes)
	r_uint32 = init_data[pos:pos+4]
	data_length, = struct.unpack(">I", r_uint32)
	pos += 4

	# data
	data = init_data[pos:pos+data_length]
	pos += data_length

	return uuid, version, data, kids
