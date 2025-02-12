import datetime
import time
import calendar

def iso8601_to_timestamp(iso_string, utc=False):
	"""Converts an ISO 8601 formatted UTC date string to a local
	   datetime object (without pytz, compatible with Python 2.7 and 3.x).

	Args:
		iso_string: The ISO 8601 date string (e.g., "2022-12-23T04:59:00.000Z").
		utc: If true, then it returns UTC timestamp instead of local TZ timestamp

	Returns:
		A datetime object in the local timezone, or None if parsing fails.
	"""
	# 1. Parse the ISO string (handle 'Z' and fractional seconds):
	if '.' in iso_string: # Check for fractional seconds
		iso_string = iso_string.replace('Z', '')
		utc_datetime = datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S.%f")
	else:
		iso_string = iso_string.replace('Z', '')
		utc_datetime = datetime.datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%S")

	# 2. Convert to local time (Python 2.7 and 3.x compatible):
	utc_timestamp = calendar.timegm(utc_datetime.utctimetuple())  # UTC timestamp

	if utc:
		return utc_timestamp

	local_timestamp = time.mktime(time.localtime(utc_timestamp)) # Local Timestamp
	return local_timestamp

def iso8601_to_datetime(iso_string, utc=False):
	local_timestamp = iso8601_to_timestamp(iso_string, utc)
	local_datetime = datetime.datetime.fromtimestamp(local_timestamp)
	return local_datetime
