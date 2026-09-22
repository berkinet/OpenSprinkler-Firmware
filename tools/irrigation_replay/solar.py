"""Dated sunset-to-sunrise intervals using the SunCalc formulas bundled in the UI.

Solar calculation adapted from SunCalc 1.7, (c) 2011-2015 Vladimir Agafonkin.
See SUNCalc-LICENSE.txt. Not terrain/horizon or twilight modeling.
"""
from datetime import datetime, time, timedelta
from math import acos, asin, sin, cos, pi, floor, ceil
from zoneinfo import ZoneInfo
from .model import number
from .calendar import normalize


def sun_times(day, tz, latitude, longitude):
    """UTC seconds for this local day's sunrise and sunset; None at polar edges."""
    rad = pi/180
    west = -longitude*rad
    phi = latitude*rad
    stamp = datetime.combine(day, time(12), tz).timestamp()
    days = stamp/86400 - .5 + 2440588 - 2451545
    cycle = floor(days-.0009-west/(2*pi)+.5)
    transit = .0009 + west/(2*pi) + cycle
    anomaly = rad*(357.5291+.98560028*transit)
    longitude_sun = anomaly + rad*(1.9148*sin(anomaly)+.02*sin(2*anomaly)+.0003*sin(3*anomaly)) + rad*102.9372 + pi
    declination = asin(sin(longitude_sun)*sin(rad*23.4397))
    noon = 2451545 + transit + .0053*sin(anomaly)-.0069*sin(2*longitude_sun)
    angle_cos = (sin(rad*-.833)-sin(phi)*sin(declination))/(cos(phi)*cos(declination))
    if not -1 <= angle_cos <= 1:
        return None
    delta = acos(angle_cos)/(2*pi)
    return ((noon-delta+.5-2440588)*86400, (noon+delta+.5-2440588)*86400)


def night_intervals(timezone_name, first, last, location):
    if not isinstance(location, dict) or set(location) != {'latitude', 'longitude'}:
        raise ValueError('night only requires latitude and longitude in runtime.location')
    latitude, longitude = float(number(location['latitude'])), float(number(location['longitude']))
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('location coordinates outside valid range')
    tz = ZoneInfo(timezone_name)
    nights = []
    day = first-timedelta(days=1)
    while day <= last:
        today = sun_times(day, tz, latitude, longitude)
        tomorrow = sun_times(day+timedelta(days=1), tz, latitude, longitude)
        # Missing polar events must not be interpreted as unrestricted watering.
        if today is None or tomorrow is None:
            raise ValueError('sunrise or sunset unavailable; night-only planning needs valid solar events')
        if tomorrow[0] <= today[1]:
            raise ValueError('solar events do not form a night')
        nights.append((ceil(today[1]), floor(tomorrow[0])))
        day += timedelta(days=1)
    return normalize(nights)
