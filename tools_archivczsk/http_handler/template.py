# -*- coding: utf-8 -*-

import os, base64
from Plugins.Extensions.archivCZSK.engine.httpserver import AddonHttpRequestHandler
from ..cache import SimpleAutokeyExpiringCache
from ..contentprovider.archivczsk_provider import _icon
import json

from tools_cenc.wvdecrypt import WvDecrypt
from tools_cenc.prdecrypt import PrDecrypt
from tools_cenc.mp4decrypt import mp4_pssh_get
from binascii import crc32
from time import time
import subprocess
import select

# #################################################################################################

class HTTPRequestHandlerTemplate(AddonHttpRequestHandler):
	CHUNK_SIZE = 40960

	def __init__(self, content_provider, addon):
		super(HTTPRequestHandlerTemplate, self).__init__(addon)

		self.cp = content_provider
		self.scache = SimpleAutokeyExpiringCache()
		self.req_session = self.cp.get_requests_session()

		self.enable_devel_logs = os.path.isfile('/tmp/archivczsk_enable_devel_logs')
		self.wvdecrypt = WvDecrypt.get_instance()
		self.prdecrypt = PrDecrypt.get_instance()
		self.pssh = {}

	# #################################################################################################

	def log_devel(self, msg):
		if self.enable_devel_logs:
			self.cp.log_debug(msg)

	# #################################################################################################

	@staticmethod
	def get_ffmpeg_path():
		if os.path.isfile('/usr/lib/exteplayer3_deps/ffmpeg'):
			return '/usr/lib/exteplayer3_deps/ffmpeg'
		else:
			return '/usr/bin/ffmpeg'

	# #################################################################################################

	@staticmethod
	def exception_as_stream(function):
		def wrapper(self, request, *args, **kwargs):
			try:
				return function(self, request, *args, **kwargs)
			except Exception as e:
				self.cp.log_error("Exception in HTTP request handler: %s - startting exception streaming" % str(e))
				self.cp.log_exception()

				error_ts_file = '/tmp/error-%d.ts' % int(time())

				cmd = "-r 1 -loop 1 -i %s -vf drawtext=text='{}':x=(w-tw)/2:y=4*(h-th)/5:fontsize=36:fontcolor=yellow:fontfile=/usr/share/fonts/DejaVuSans.ttf -c:v libx264 -pix_fmt yuv420p -preset ultrafast -tune stillimage -t 200ms -f mpegts %s" % (_icon('error.jpg'), error_ts_file)
				cmd = [HTTPRequestHandlerTemplate.get_ffmpeg_path()] + cmd.split(' ')
				cmd[8] = cmd[8].format(str(e).replace('\n', ' ').replace(':', 'x\:').replace('"', 'x\"').replace("'", "x\'"))

				try:
					subprocess.check_call(cmd)
				except:
					if cmd[0] != '/usr/bin/ffmpeg':
						cmd[0] = '/usr/bin/ffmpeg'
						subprocess.check_call(cmd)
					else:
						raise

				cmd = '-nostdin -loglevel info -stream_loop -1 -i %s -map 0 -c copy -muxdelay 0 -muxpreload 0 -mpegts_flags +resend_headers -f mpegts pipe:1' % error_ts_file
				cmd = [None] + cmd.split(' ')

				try:
					return self.ffmpeg_stream_ts(request, cmd)
				finally:
					if os.path.isfile(error_ts_file):
						os.remove(error_ts_file)

		return wrapper

	# #################################################################################################

	def ffmpeg_stream_ts(self, request, cmd):
		if len(cmd) > 0 and cmd[0] == None:
			cmd[0] = self.get_ffmpeg_path()

		# cmd = '/usr/bin/gst-launch-1.0 urisourcebin uri={input_url} name=src mpegtsmux name=mux pat-interval=100000000 pmt-interval=100000000 ! fdsink fd=1 src. ! parsebin name=vparse ! queue ! mux. src. ! parsebin name=aparse ! queue ! mux.'.format(input_url=input_url)

		input_url = '?'
		for c in cmd:
			if c == '-i':
				input_url = cmd[cmd.index(c) + 1]
				break

		process = None
		log = None

		try:
			self.cp.log_info("Starting stream conversion to TS for URL: %s" % input_url)
			log_file_name = '/tmp/tsconvert.log'

			if os.path.isfile(log_file_name):
				log = open('{}-{}'.format(log_file_name, input_url.replace('/', '_').replace(':', '_')), 'w')
			else:
				log = open(os.devnull, 'w')

			poll_obj = select.poll()
			process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, bufsize=0)
			poll_obj.register(process.stdout, select.POLLIN)
			poll_obj.register(request.wfile, select.POLLIN | select.POLLHUP | select.POLLERR)

			request.send_response(200)
			request.send_header('Content-Type', 'video/mp2t')
			request.send_header('Cache-Control','no-cache')
			request.send_header('Connection', 'close')

			while True:
				events = poll_obj.poll(1000)  # 6 second timeout
				if not events:
					continue

				for fd, event in events:
					if fd == request.wfile.fileno():
#						if event & (select.POLLHUP | select.POLLERR):
						raise IOError("Client disconnected")

				for fd, event in events:
					if fd == process.stdout.fileno():
						data = process.stdout.read(65536)

						if not data:
							break

						request.write(data)

		except (IOError, OSError):
			self.cp.log_debug("Stopping stream conversion for URL: %s - client disconnected" % input_url)

		except:
			self.cp.log_exception()

		finally:
			if process:
				try:
					if process.poll() is None:
#						process.terminate()
						process.kill()

						try:
							process.wait()
						except:
							self.cp.log_error("Failed to stop ffmpeg process for URL: %s" % input_url)
							self.cp.log_exception()

				except:
					self.cp.log_error("Failed to kill ffmpeg process for URL: %s" % input_url)
					self.cp.log_exception()

				try:
					poll_obj.unregister(process.stdout)
					poll_obj.unregister(request.wfile)
					process.stdout.close()
				except:
					self.cp.log_exception()

			if log:
				log.close()

			self.cp.log_info("Stream conversion for URL %s stopped" % input_url)

		return None

	# #################################################################################################

	@staticmethod
	def encode_stream_key(endpoint, stream_key, uri, extension):
		'''
		Converts stream key (string or dictionary) to url, that can be played by player.
		'''
		if stream_key == None:
			stream_key = ""

		if isinstance( stream_key, (type({}), type([]), type(()),) ):
			stream_key = '{' + json.dumps(stream_key) + '}'

		stream_key = base64.b64encode(stream_key.encode('utf-8')).decode('utf-8')
		return "%s/%s/%s.%s" % (endpoint, uri, stream_key, extension)

	# #################################################################################################

	def decode_stream_key(self, path):
		'''
		Decodes stream key encoded using stream_key_to_dash_url or stream_key_to_hls_url
		'''
		if path.endswith('.mpd'):
			path = path[:-4]
		elif path.endswith('.m3u8'):
			path = path[:-5]

		if len(path) > 0:
			stream_key = base64.b64decode(path.encode('utf-8')).decode("utf-8")
			if stream_key[0] == '{' and stream_key[-1] == '}':
				stream_key = json.loads(stream_key[1:-1])

			return stream_key

		else:
			return None

	# #################################################################################################

	def forward_http_data(self, request, url, headers=None):
		h = {}
		h.update(headers or {})

		r = request.get_header('Range')
		if r:
			h['Range'] = r

		try:
			response = self.req_session.get(url, headers=headers, stream=True)
		except:
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))
			request.send_response(500)
			return

		request.send_response(response.status_code)
		self.forward_http_headers(request, response)

		for chunk in response.iter_content(self.CHUNK_SIZE):
			request.write(chunk)

	# #################################################################################################

	def request_http_data(self, url, headers=None):
		try:
			response = self.req_session.get(url, headers=headers)
		except:
			self.cp.log_error('Request for url %s failed: %s' % (url, str(response)))
			return 500, None

		return response.status_code, response.content

	# #################################################################################################

	def forward_http_headers(self, request, response, headers=None):
		headers = headers or ('Accept-Ranges', 'Content-Type', 'Accept', 'Content-Range')

		for k,v in response.headers.items():
			if k in headers:
				request.send_header(k, v)

	# #################################################################################################

	def get_drm_license(self, drm_info, lic_request):
		session = self.cp.get_requests_session()

		try:
			response = session.post(drm_info['license_url'], data=lic_request, headers=drm_info.get('headers',{}))
			response.raise_for_status()
			content = response.content
		except Exception as e:
			self.cp.log_error("Failed to get DRM license: %s" % str(e))
			content = None

		session.close()

		return content

	# #################################################################################################

	def get_drm_keys(self, pssh_list, drm_info):
		wv_drm_info = drm_info.get('wv',{})
		pr_drm_info = drm_info.get('pr',{})

		keys = []
		for drm_type in ('wv', 'pr'):
			for p in pssh_list.get(drm_type,[]):
				if p == 'dynamic':
					# skip dummy pssh
					continue

				k = self.pssh.get(p)
				if k == None:
					if drm_type == 'wv':
						if wv_drm_info:
							self.cp.log_debug("Requesting keys for WV pssh %s from license server" % p)
							if wv_drm_info.get('privacy_mode', False):
								k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(wv_drm_info, lic_request), lambda cert_request: self.get_drm_license(wv_drm_info, cert_request))
							else:
								k = self.wvdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(wv_drm_info, lic_request))

							if not k:
								self.cp.log_error("Failed to get DRM keys for WV pssh %s" % p)
						elif not pr_drm_info:
							self.cp.log_debug("No widevine license URL provided")

					elif drm_type == 'pr':
						if pr_drm_info:
							self.cp.log_debug("Requesting keys for PR pssh %s from license server" % p)
							k = self.prdecrypt.get_content_keys(p, lambda lic_request: self.get_drm_license(pr_drm_info, lic_request))

							if not k:
								self.cp.log_error("Failed to get DRM keys for PR pssh %s" % p)
						elif not wv_drm_info:
							self.cp.log_debug("No playready license URL provided")

					self.pssh[p] = k
					if k:
						keys.extend(k)
						self.cp.log_debug("Received %d keys for pssh %s" % (len(k), p))
				else:
					self.log_devel("Keys for pssh %s found in cache" % p)
					keys.extend(k)

		return keys

	# #################################################################################################

	def get_mp4_pssh(self, data, pssh_list={}):
		wv_pssh, pr_pssh, kid = mp4_pssh_get(data)

		if wv_pssh:
			self.log_devel("Received WV PSSH from mp4: %s" % wv_pssh)

			if wv_pssh not in pssh_list['wv']:
				pssh_list['wv'].append(wv_pssh)
				self.cp.log_debug("Adding PSSH %s from mp4 to list of available WV PSSHs" % wv_pssh)

		if pr_pssh:
			self.log_devel("Received PR PSSH from mp4: %s" % pr_pssh)

			if pr_pssh not in pssh_list['pr']:
				pssh_list['pr'].append(pr_pssh)
				self.cp.log_debug("Adding PSSH %s from mp4 to list of available PR PSSHs" % pr_pssh)

		self.log_devel("Received KID from mp4: %s" % kid)

		return kid

	# #################################################################################################

	@staticmethod
	def calc_cache_key(data):
		return str(crc32(data.encode('utf-8')) & 0xffffffff)

	# #################################################################################################
