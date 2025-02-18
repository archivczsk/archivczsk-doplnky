import datetime
import time
import calendar
import re

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

	try:
		local_timestamp = time.mktime(time.localtime(utc_timestamp)) # Local Timestamp
	except OverflowError:
		# whops, what not?
		local_timestamp = 2**31 - 1

	return local_timestamp

def iso8601_to_datetime(iso_string, utc=False):
	local_timestamp = iso8601_to_timestamp(iso_string, utc)
	local_datetime = datetime.datetime.fromtimestamp(local_timestamp)
	return local_datetime

def iso8601_duration_to_timedelta(iso_duration="P2DT6H21M32S"):
	if not iso_duration:
		return None

	m = re.match(r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:.\d+)?)S)?$', iso_duration)

	if m is None:
		return None

	days = 0
	hours = 0
	minutes = 0
	seconds = 0.0

	# Years and months are not being utilized here, as there is not enough
	# information provided to determine which year and which month.
	# Python's time_delta class stores durations as days, seconds and
	# microseconds internally, and therefore we'd have to
	# convert parsed years and months to specific number of days.

	if m.group(3):
		days = int(m.group(3))
	if m.group(4):
		hours = int(m.group(4))
	if m.group(5):
		minutes = int(m.group(5))
	if m.group(6):
		seconds = float(m.group(6))

	return datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

def iso8601_duration_to_seconds(iso_duration="P2DT6H21M32S"):
	t = iso8601_duration_to_timedelta(iso_duration)

	if t is not None:
		return int(t.total_seconds())
	else:
		return None
