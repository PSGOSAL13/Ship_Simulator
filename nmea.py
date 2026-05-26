import math
from datetime import datetime, timezone


def _checksum(sentence: str) -> str:
    cs = 0
    for ch in sentence:
        cs ^= ord(ch)
    return f"{cs:02X}"


def _lat_nmea(lat: float):
    d = int(abs(lat))
    m = (abs(lat) - d) * 60
    return f"{d:02d}{m:07.4f}", "N" if lat >= 0 else "S"


def _lon_nmea(lon: float):
    d = int(abs(lon))
    m = (abs(lon) - d) * 60
    return f"{d:03d}{m:07.4f}", "E" if lon >= 0 else "W"


def gprmc(lat: float, lon: float, speed_kts: float, course: float) -> str:
    now = datetime.now(timezone.utc)
    t = now.strftime("%H%M%S.00")
    d = now.strftime("%d%m%y")
    la, lad = _lat_nmea(lat)
    lo, lod = _lon_nmea(lon)
    body = f"GPRMC,{t},A,{la},{lad},{lo},{lod},{speed_kts:.2f},{course:.1f},{d},,"
    return f"${body}*{_checksum(body)}"


def gpgga(lat: float, lon: float) -> str:
    now = datetime.now(timezone.utc)
    t = now.strftime("%H%M%S.00")
    la, lad = _lat_nmea(lat)
    lo, lod = _lon_nmea(lon)
    body = f"GPGGA,{t},{la},{lad},{lo},{lod},1,08,1.0,0.0,M,0.0,M,,"
    return f"${body}*{_checksum(body)}"


def gpvtg(course: float, speed_kts: float) -> str:
    kmh = speed_kts * 1.852
    body = f"GPVTG,{course:.1f},T,,M,{speed_kts:.2f},N,{kmh:.2f},K"
    return f"${body}*{_checksum(body)}"


def gpgll(lat: float, lon: float) -> str:
    now = datetime.now(timezone.utc)
    t = now.strftime("%H%M%S.00")
    la, lad = _lat_nmea(lat)
    lo, lod = _lon_nmea(lon)
    body = f"GPGLL,{la},{lad},{lo},{lod},{t},A"
    return f"${body}*{_checksum(body)}"


def dead_reckon(lat: float, lon: float, speed_kts: float, course: float, dt: float = 1.0):
    """Advance position by dt seconds using course and speed (dead reckoning)."""
    dist_nm = speed_kts * dt / 3600
    dlat = dist_nm * math.cos(math.radians(course)) / 60
    cos_lat = math.cos(math.radians(lat))
    dlon = (dist_nm * math.sin(math.radians(course)) / (60 * cos_lat)) if abs(cos_lat) > 1e-10 else 0.0
    return lat + dlat, lon + dlon
