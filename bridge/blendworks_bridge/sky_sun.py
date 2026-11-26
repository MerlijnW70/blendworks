import datetime
import math
import re

from .errors import bad_args

DATE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?$")


def direction(elevation, azimuth):
    """Unit vector towards the sun: azimuth clockwise from north (+Y) towards east (+X)."""
    e = math.radians(elevation)
    a = math.radians(azimuth)
    return (math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e))


def angles(vector):
    x, y, z = vector
    horizontal = math.hypot(x, y)
    elevation = math.degrees(math.atan2(z, horizontal))
    azimuth = math.degrees(math.atan2(x, y)) % 360.0 if horizontal > 1e-12 else 0.0
    return elevation, azimuth


def parse_date(text):
    match = DATE_PATTERN.match(text)
    if match is None:
        raise bad_args(f'date must be YYYY-MM-DD, not "{text}"')
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as error:
        raise bad_args(f"date {text} does not exist: {error}") from error


def parse_time(text):
    match = TIME_PATTERN.match(text)
    if match is None:
        raise bad_args(f'time must be HH:MM or HH:MM:SS, not "{text}"')
    hours, minutes = int(match.group(1)), int(match.group(2))
    seconds = float(match.group(3)) if match.group(3) else 0.0
    if hours > 23 or minutes > 59 or seconds >= 60.0:
        raise bad_args(f"time {text} is not a time of day")
    return hours + minutes / 60.0 + seconds / 3600.0


def julian_day(date, hours_utc):
    ordinal = date.toordinal() + 1721424.5
    return ordinal + hours_utc / 24.0


def refraction(elevation):
    """Atmospheric refraction in degrees for a true elevation (NOAA solar calculator)."""
    if elevation > 85.0:
        return 0.0
    tangent = math.tan(math.radians(elevation))
    if elevation > 5.0:
        minutes = 58.1 / tangent - 0.07 / tangent ** 3 + 0.000086 / tangent ** 5
    elif elevation > -0.575:
        minutes = 1735.0 + elevation * (-518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711)))
    else:
        minutes = -20.772 / tangent
    return minutes / 3600.0


def solar_position(date_text, time_text, latitude, longitude, utc_offset):
    """Apparent sun elevation and azimuth in degrees after the NOAA solar calculator (Meeus)."""
    date = parse_date(date_text)
    local = parse_time(time_text)
    day = julian_day(date, local - utc_offset)
    century = (day - 2451545.0) / 36525.0
    mean_longitude = (280.46646 + century * (36000.76983 + century * 0.0003032)) % 360.0
    mean_anomaly = 357.52911 + century * (35999.05029 - 0.0001537 * century)
    eccentricity = 0.016708634 - century * (0.000042037 + 0.0000001267 * century)
    anomaly = math.radians(mean_anomaly)
    centre = (math.sin(anomaly) * (1.914602 - century * (0.004817 + 0.000014 * century))
              + math.sin(2 * anomaly) * (0.019993 - 0.000101 * century) + math.sin(3 * anomaly) * 0.000289)
    true_longitude = mean_longitude + centre
    omega = math.radians(125.04 - 1934.136 * century)
    apparent = math.radians(true_longitude - 0.00569 - 0.00478 * math.sin(omega))
    seconds = 21.448 - century * (46.815 + century * (0.00059 - century * 0.001813))
    mean_obliquity = 23.0 + (26.0 + seconds / 60.0) / 60.0
    obliquity = math.radians(mean_obliquity + 0.00256 * math.cos(omega))
    declination = math.asin(math.sin(obliquity) * math.sin(apparent))
    y = math.tan(obliquity / 2.0) ** 2
    longitude_rad = math.radians(mean_longitude)
    equation = 4.0 * math.degrees(
        y * math.sin(2 * longitude_rad) - 2 * eccentricity * math.sin(anomaly)
        + 4 * eccentricity * y * math.sin(anomaly) * math.cos(2 * longitude_rad)
        - 0.5 * y * y * math.sin(4 * longitude_rad) - 1.25 * eccentricity * eccentricity * math.sin(2 * anomaly)
    )
    true_solar_minutes = (local * 60.0 + equation + 4.0 * longitude - 60.0 * utc_offset) % 1440.0
    hour_angle = true_solar_minutes / 4.0 - 180.0 if true_solar_minutes >= 0 else true_solar_minutes / 4.0 + 180.0
    lat = math.radians(latitude)
    cos_zenith = (math.sin(lat) * math.sin(declination)
                  + math.cos(lat) * math.cos(declination) * math.cos(math.radians(hour_angle)))
    zenith = math.acos(max(-1.0, min(1.0, cos_zenith)))
    true_elevation = 90.0 - math.degrees(zenith)
    elevation = true_elevation + refraction(true_elevation)
    sin_zenith = math.sin(zenith)
    if abs(math.cos(lat) * sin_zenith) < 1e-12:
        azimuth = 180.0 if latitude > 0 else 0.0
    else:
        cos_azimuth = (math.sin(lat) * cos_zenith - math.sin(declination)) / (math.cos(lat) * sin_zenith)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_azimuth))))
        azimuth = (angle + 180.0) % 360.0 if hour_angle > 0 else (540.0 - angle) % 360.0
    return {
        "elevation": elevation,
        "azimuth": azimuth,
        "true_elevation": true_elevation,
        "declination": math.degrees(declination),
        "equation_of_time_minutes": equation,
        "hour_angle": hour_angle,
    }


def resolve(sun):
    """Sun elevation and azimuth from {elevation, azimuth} or {date, time, latitude, longitude, utc_offset}."""
    placed = "elevation" in sun or "azimuth" in sun
    dated = any(key in sun for key in ("date", "time", "latitude", "longitude", "utc_offset"))
    if placed and dated:
        raise bad_args("sun takes elevation and azimuth, or date, time, latitude and longitude, not both")
    if dated:
        missing = [key for key in ("date", "time", "latitude", "longitude") if key not in sun]
        if missing:
            raise bad_args(f"sun by date needs {', '.join(missing)}")
        offset = sun.get("utc_offset", round(sun["longitude"] / 15.0))
        position = solar_position(sun["date"], sun["time"], sun["latitude"], sun["longitude"], offset)
        position["utc_offset"] = offset
        position["source"] = "date"
        return position
    return {"elevation": sun.get("elevation", 45.0), "azimuth": sun.get("azimuth", 180.0) % 360.0, "source": "angles"}
