import xml.etree.ElementTree as ET
try:
	from typing import Union, Optional
except ImportError:
	pass

from ..misc.drmresults import DrmResult
from ..misc.exceptions import InvalidSoapMessage, ServerException
from ..system.compat import html_unescape, text_type, tostring


class SoapMessage(object):
	XML_DECLARATION = '<?xml version="1.0" encoding="utf-8"?>'

	_NS = {
		"soap": "http://schemas.xmlsoap.org/soap/envelope/",
		"envelope": "http://www.w3.org/2003/05/soap-envelope"
	}

	def __init__(self, root):
		# type: (ET.Element) -> None
		self.root = root

	@classmethod
	def create(cls, message):
		# type: (ET.Element) -> SoapMessage
		Envelope = ET.Element("soap:Envelope", {
			"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
			"xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
			"xmlns:soap": "http://schemas.xmlsoap.org/soap/envelope/"
		})

		Body = ET.SubElement(Envelope, "soap:Body")
		Body.append(message)

		return cls(Envelope)

	@classmethod
	def loads(cls, data):
		# type: (Union[str, bytes]) -> SoapMessage
		if not data:
			raise InvalidSoapMessage("Data must not be empty")

		if isinstance(data, text_type):
			data = data.encode()

		parser = ET.XMLParser(encoding="utf-8")
		root = ET.fromstring(data, parser=parser)

		if not root.tag.endswith("Envelope"):
			raise InvalidSoapMessage("Soap Message root must be Envelope")

		return cls(root)

	def get_message(self):
		# type: () -> Optional[ET.Element]
		Body = self.root.find("soap:Body", self._NS) or self.root.find("envelope:Body", self._NS)
		if Body is None:
			return None

		if len(list(Body)) == 0:
			return None

		return Body[0]

	@staticmethod
	def read_namespace(element):
		# type: (...) -> Optional[str]
		if element.tag.startswith("{"):
			return element.tag.split("}")[0][1:]
		return None

	def raise_faults(self):
		fault = self.get_message()

		if not fault.tag.endswith("Fault"):
			return

		nsmap = {"soap": self.read_namespace(fault)}

		status_code = fault.findtext("detail/Exception/StatusCode")
		drm_result = DrmResult.from_code(status_code) if status_code is not None else None
		fault_text = fault.findtext("faultstring") or fault.findtext("soap:Reason/soap:Text", namespaces=nsmap)

		error_message = fault_text or getattr(drm_result, "message", "(No message)")
		exception_message = ("[{0}] ".format(drm_result.name) if drm_result else "") + error_message

		raise ServerException(exception_message)

	def dumps(self):
		# type: () -> str
		xml_data = tostring(self.root, encoding="utf-8")

		# this shouldn't exist
		return self.XML_DECLARATION + html_unescape(xml_data.decode())
