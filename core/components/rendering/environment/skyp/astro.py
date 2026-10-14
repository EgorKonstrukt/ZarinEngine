# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3

_DEFAULT_YEAR = 2024
_DEFAULT_MONTH = 6
_DEFAULT_DAY = 21
_DEFAULT_HOUR = 12
_DEFAULT_MINUTE = 0
_DEFAULT_SECOND = 0
_DEFAULT_LATITUDE = 55.75
_DEFAULT_LONGITUDE = 37.62
_DEFAULT_UTC_OFFSET = 3.0
_J2000_JD = 2451545.0
_ASTRO_KEYS = (
    "obliquity_deg", "obliquity_drift",
    "sun_ml_epoch", "sun_ml_rate", "sun_ma_epoch", "sun_ma_rate",
    "sun_ecc", "sun_ecc2",
    "moon_ml_epoch", "moon_ml_rate", "moon_ma_epoch", "moon_ma_rate",
    "moon_el_epoch", "moon_el_rate", "moon_af_epoch", "moon_af_rate",
    "moon_lon1", "moon_lon2", "moon_lon3", "moon_lon4", "moon_lon5",
    "moon_lat1", "moon_lat2", "moon_lat3", "moon_lat4",
    "synodic_month", "new_moon_jd", "gmst_epoch", "gmst_rate",
)
_ASTRO_DEFAULTS = {
    "obliquity_deg": 23.439,
    "obliquity_drift": 0.0000004,
    "sun_ml_epoch": 280.459,
    "sun_ml_rate": 0.98564736,
    "sun_ma_epoch": 357.5291,
    "sun_ma_rate": 0.98560028,
    "sun_ecc": 1.915,
    "sun_ecc2": 0.020,
    "moon_ml_epoch": 218.316,
    "moon_ml_rate": 13.176396,
    "moon_ma_epoch": 134.963,
    "moon_ma_rate": 13.064993,
    "moon_el_epoch": 297.850,
    "moon_el_rate": 12.190749,
    "moon_af_epoch": 93.272,
    "moon_af_rate": 13.229350,
    "moon_lon1": 6.289,
    "moon_lon2": -1.274,
    "moon_lon3": 0.658,
    "moon_lon4": -0.186,
    "moon_lon5": -0.060,
    "moon_lat1": 5.128,
    "moon_lat2": 0.280,
    "moon_lat3": 0.277,
    "moon_lat4": -0.017,
    "synodic_month": 29.530588853,
    "new_moon_jd": 2451550.258,
    "gmst_epoch": 18.697374558,
    "gmst_rate": 24.06570982441908,
}
_ECLIPSE_SEARCH_DAYS = 365 * 5
_ECLIPSE_SAMPLE_STEP = 0.25
_ECLIPSE_MAX_SEPARATION = 0.9

try:
    from core._sky_astro import sky_astro_update as _sky_astro_cy
except ImportError:
    _sky_astro_cy = None


def _julian_day(year: int, month: int, day: int) -> float:
    y = year
    m = month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5


def _sun_ecliptic_longitude(d: float, p: dict = None) -> float:
    if p is None:
        p = _ASTRO_DEFAULTS
    g = (p["sun_ma_epoch"] + p["sun_ma_rate"] * d) % 360.0
    q = (p["sun_ml_epoch"] + p["sun_ml_rate"] * d) % 360.0
    return q + p["sun_ecc"] * math.sin(math.radians(g)) + p["sun_ecc2"] * math.sin(math.radians(2.0 * g))


def _obliquity(d: float, p: dict = None) -> float:
    if p is None:
        p = _ASTRO_DEFAULTS
    return p["obliquity_deg"] - p["obliquity_drift"] * d


def _equatorial(lon_deg: float, lat_deg: float, ecl_deg: float):
    ln = math.radians(lon_deg)
    bt = math.radians(lat_deg)
    ep = math.radians(ecl_deg)
    ra = math.atan2(math.sin(ln) * math.cos(ep) - math.tan(bt) * math.sin(ep), math.cos(ln))
    dec = math.asin(math.sin(bt) * math.cos(ep) + math.cos(bt) * math.sin(ep) * math.sin(ln))
    return math.degrees(ra) % 360.0, math.degrees(dec)


def _solar_equatorial(d: float, p: dict = None):
    ecl = _obliquity(d, p)
    return _equatorial(_sun_ecliptic_longitude(d, p), 0.0, ecl)


def _moon_ecliptic(d: float, p: dict = None):
    if p is None:
        p = _ASTRO_DEFAULTS
    lp = (p["moon_ml_epoch"] + p["moon_ml_rate"] * d) % 360.0
    mp = (p["moon_ma_epoch"] + p["moon_ma_rate"] * d) % 360.0
    ms = (p["sun_ma_epoch"] + p["sun_ma_rate"] * d) % 360.0
    dm = (p["moon_el_epoch"] + p["moon_el_rate"] * d) % 360.0
    f = (p["moon_af_epoch"] + p["moon_af_rate"] * d) % 360.0
    lon = lp + p["moon_lon1"] * math.sin(math.radians(mp)) \
          + p["moon_lon2"] * math.sin(math.radians(2.0 * dm - mp)) \
          + p["moon_lon3"] * math.sin(math.radians(2.0 * dm)) \
          + p["moon_lon4"] * math.sin(math.radians(ms)) \
          + p["moon_lon5"] * math.sin(math.radians(2.0 * mp - 2.0 * dm))
    lat = p["moon_lat1"] * math.sin(math.radians(f)) \
          + p["moon_lat2"] * math.sin(math.radians(mp + f)) \
          + p["moon_lat3"] * math.sin(math.radians(mp - f)) \
          + p["moon_lat4"] * math.sin(math.radians(2.0 * dm - f))
    return lon % 360.0, lat


def _moon_equatorial(d: float, p: dict = None):
    lon, lat = _moon_ecliptic(d, p)
    return _equatorial(lon, lat, _obliquity(d, p))


def _local_sidereal_hours(d: float, longitude_deg: float, p: dict = None) -> float:
    if p is None:
        p = _ASTRO_DEFAULTS
    gmst = (p["gmst_epoch"] + p["gmst_rate"] * d) % 24.0
    return (gmst + longitude_deg / 15.0) % 24.0


def _alt_az_from_equatorial(ra_deg: float, dec_deg: float, lst_hours: float, latitude_deg: float):
    h = math.radians((lst_hours - ra_deg / 15.0) * 15.0)
    lat = math.radians(latitude_deg)
    dec = math.radians(dec_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (math.cos(alt) * math.cos(lat) + 1e-9)
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))
    if math.sin(h) > 0.0:
        az = 360.0 - az
    return math.degrees(alt), az


def _dir_from_alt_az(alt_deg: float, az_deg: float) -> Vec3:
    a = math.radians(alt_deg)
    z = math.radians(az_deg)
    return Vec3(math.sin(z) * math.cos(a), math.sin(a), -math.cos(z) * math.cos(a))


def _sep_deg(a: Vec3, b: Vec3) -> float:
    dot = max(-1.0, min(1.0, a.x * b.x + a.y * b.y + a.z * b.z))
    return math.degrees(math.acos(dot))


def _moon_phase_from_days(d: float, p: dict = None) -> float:
    if p is None:
        p = _ASTRO_DEFAULTS
    age = (d - p["new_moon_jd"]) % p["synodic_month"]
    return age / p["synodic_month"]


def _sun_moon_separation(d: float, p: dict = None) -> float:
    lon_m, lat_m = _moon_ecliptic(d, p)
    lon_s = _sun_ecliptic_longitude(d, p)
    lat_s = 0.0
    cos_sep = (math.sin(math.radians(lat_m)) * math.sin(math.radians(lat_s))
               + math.cos(math.radians(lat_m)) * math.cos(math.radians(lat_s))
               * math.cos(math.radians(lon_m - lon_s)))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


def _new_moon_offset(d: float, p: dict = None) -> float:
    r = (_moon_ecliptic(d, p)[0] - _sun_ecliptic_longitude(d, p)) % 360.0
    return ((r - 180.0) % 360.0) - 180.0


def _refine_new_moon(t0: float, t1: float, p: dict = None) -> float:
    for _ in range(24):
        tm = (t0 + t1) * 0.5
        if _new_moon_offset(tm, p) < 0.0:
            t0 = tm
        else:
            t1 = tm
    return (t0 + t1) * 0.5


def nearest_solar_eclipse(d0: float, p: dict = None):
    best = None
    prev_t = None
    prev_r = None
    t = d0 - _ECLIPSE_SEARCH_DAYS
    end = d0 + _ECLIPSE_SEARCH_DAYS
    while t <= end:
        r = _new_moon_offset(t, p)
        if prev_r is not None and prev_r <= 0.0 < r:
            nm = _refine_new_moon(prev_t, t, p)
            sep = _sun_moon_separation(nm, p)
            if sep < _ECLIPSE_MAX_SEPARATION:
                if best is None or abs(nm - d0) < abs(best[0] - d0):
                    best = (nm, sep)
        prev_t = t
        prev_r = r
        t += _ECLIPSE_SAMPLE_STEP
    return best


def _julian_day_to_ymd(jd: float):
    jd = jd + 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - int(alpha / 4)
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    return int(year), int(month), day


class ProceduralSkyAstroMixin:

    @staticmethod
    def _eclipse_coverage(sun_r_deg: float, moon_r_deg: float, sep_deg: float) -> float:
        import math as _m
        if sep_deg <= 0.0:
            return 1.0 if moon_r_deg >= sun_r_deg else (moon_r_deg / sun_r_deg) ** 2
        R = _m.radians(sun_r_deg)
        r = _m.radians(moon_r_deg)
        d = _m.radians(sep_deg)
        if d >= R + r:
            return 0.0
        if d <= r - R:
            return 1.0
        if d <= R - r:
            return (r / R) ** 2
        cos1 = (d * d + R * R - r * r) / (2.0 * d * R)
        cos1 = max(-1.0, min(1.0, cos1))
        a1 = _m.acos(cos1) * R * R
        cos2 = (d * d + r * r - R * R) / (2.0 * d * r)
        cos2 = max(-1.0, min(1.0, cos2))
        a2 = _m.acos(cos2) * r * r
        p = (R + r + d) * 0.5
        tri = 2.0 * _m.sqrt(max(0.0, (p - R) * (p - r) * (p - d) * p))
        return (a1 + a2 - tri) / (_m.pi * R * R)

    def _invalidate_time(self):
        self._time_cache_key = None

    def _astro_params(self) -> dict:
        return {k: getattr(self, "_astro_" + k, _ASTRO_DEFAULTS[k]) for k in _ASTRO_DEFAULTS}

    def _astro_params_key(self) -> tuple:
        return tuple(self._astro_params().values())

    def _time_fields_key(self):
        return (self.year, self.month, self.day, self.hour, self.minute,
                self.second, self.latitude, self.longitude, self.utc_offset,
                self._astro_params_key())

    def _update_time_cache(self):
        tkey = (self.year, self.month, self.day, self.hour, self.minute,
                self.second, self.latitude, self.longitude, self.utc_offset)
        ck = self._time_cache_key
        if ck is not None and ck[0] == tkey:
            return
        akey = self._astro_params_key()
        if ck is not None and ck[0] == tkey and ck[1] == akey:
            return
        self._time_cache_key = (tkey, akey)
        if _sky_astro_cy is not None:
            try:
                if self._update_time_cache_cy():
                    return
            except Exception:
                pass
        p = self._astro_params()
        jd = _julian_day(self.year, self.month, self.day)
        civil = self.hour + self.minute / 60.0 + self.second / 3600.0
        utc = civil - self.utc_offset
        d = jd - _J2000_JD + utc / 24.0
        self._day_seconds = civil * 3600.0
        self._sim_seconds = (jd - _J2000_JD) * 86400.0 + utc * 3600.0
        lst = _local_sidereal_hours(d, self.longitude, p)
        self._star_pole = _dir_from_alt_az(self.latitude, 0.0)
        self._star_rotation = math.radians(lst * 15.0)
        sun_ra, sun_dec = _solar_equatorial(d, p)
        sal, saz = _alt_az_from_equatorial(sun_ra, sun_dec, lst, self.latitude)
        self._sun_dir = _dir_from_alt_az(sal, saz)
        moon_ra, moon_dec = _moon_equatorial(d, p)
        mal, maz = _alt_az_from_equatorial(moon_ra, moon_dec, lst, self.latitude)
        self._moon_dir = _dir_from_alt_az(mal, maz)
        self._moon_phase = _moon_phase_from_days(d, p)
        self._update_eclipse()

    def _update_time_cache_cy(self):
        import numpy as _np
        p = self._astro_params()
        arr = _np.empty(29, dtype=_np.float64)
        for i, k in enumerate(_ASTRO_KEYS):
            arr[i] = float(p[k])
        r = _sky_astro_cy(int(self.year), int(self.month), int(self.day),
                          float(self.hour), float(self.minute), float(self.second),
                          float(self.latitude), float(self.longitude), float(self.utc_offset), arr)
        self._sun_dir = Vec3(r[0], r[1], r[2])
        self._moon_dir = Vec3(r[3], r[4], r[5])
        self._moon_phase = r[6]
        self._star_rotation = r[7]
        self._day_seconds = r[8]
        self._sim_seconds = r[9]
        self._star_pole = Vec3(r[10], r[11], r[12])
        self._update_eclipse()
        return True

    def _update_eclipse(self):
        sun_r_deg = 0.27
        try:
            from core.components.rendering.environment.atmosp import Atmosphere
            try:
                _ent = self._entity
                _sc = _ent._scene if _ent is not None else None
            except Exception:
                _sc = None
            atmos = Atmosphere.for_scene(_sc)
            if atmos is not None:
                sun_r_deg = float(getattr(atmos, "_sun_angular_radius", 0.27))
        except Exception:
            pass
        sep = _sep_deg(self._sun_dir, self._moon_dir)
        self._eclipse_darkness = self._eclipse_coverage(sun_r_deg, self.moon_size, sep)
