# cython: boundscheck=False, wraparound=False, cdivision=True, nonecheck=False, initializedcheck=False, overflowcheck=False
# distutils: extra_compile_args = -O3 -ffast-math -march=native -fopenmp
# distutils: extra_link_args = -fopenmp
from libc.math cimport sin, cos, tan, asin, acos, atan2, sqrt, floor

cdef inline double _d2r(double d):
    return d * 0.017453292519943295

cdef inline double _r2d(double r):
    return r * 57.29577951308232

cdef inline double _pymod(double a, double n):
    return a - n * floor(a / n)

cdef inline double _clamp11(double v):
    if v < -1.0:
        return -1.0
    if v > 1.0:
        return 1.0
    return v

cdef inline double _julian_day(int year, int month, int day):
    cdef int y = year
    cdef int m = month
    if m <= 2:
        y -= 1
        m += 12
    cdef int a = y // 100
    cdef int b = 2 - a + a // 4
    return <double>(<int>(365.25 * (y + 4716))) + <double>(<int>(30.6001 * (m + 1))) + <double>day + <double>b - 1524.5


def sky_astro_update(int year, int month, int day,
                     double hour, double minute, double second,
                     double latitude, double longitude, double utc_offset,
                     double[:] P):
    cdef double obliquity_deg = P[0]
    cdef double obliquity_drift = P[1]
    cdef double sun_ml_epoch = P[2]
    cdef double sun_ml_rate = P[3]
    cdef double sun_ma_epoch = P[4]
    cdef double sun_ma_rate = P[5]
    cdef double sun_ecc = P[6]
    cdef double sun_ecc2 = P[7]
    cdef double moon_ml_epoch = P[8]
    cdef double moon_ml_rate = P[9]
    cdef double moon_ma_epoch = P[10]
    cdef double moon_ma_rate = P[11]
    cdef double moon_el_epoch = P[12]
    cdef double moon_el_rate = P[13]
    cdef double moon_af_epoch = P[14]
    cdef double moon_af_rate = P[15]
    cdef double moon_lon1 = P[16]
    cdef double moon_lon2 = P[17]
    cdef double moon_lon3 = P[18]
    cdef double moon_lon4 = P[19]
    cdef double moon_lon5 = P[20]
    cdef double moon_lat1 = P[21]
    cdef double moon_lat2 = P[22]
    cdef double moon_lat3 = P[23]
    cdef double moon_lat4 = P[24]
    cdef double synodic_month = P[25]
    cdef double new_moon_jd = P[26]
    cdef double gmst_epoch = P[27]
    cdef double gmst_rate = P[28]
    cdef double jd = _julian_day(year, month, day)
    cdef double civil = hour + minute / 60.0 + second / 3600.0
    cdef double utc = civil - utc_offset
    cdef double d = jd - 2451545.0 + utc / 24.0
    cdef double day_seconds = civil * 3600.0
    cdef double sim_seconds = (jd - 2451545.0) * 86400.0 + utc * 3600.0
    cdef double gmst = _pymod(gmst_epoch + gmst_rate * d, 24.0)
    cdef double lst = _pymod(gmst + longitude / 15.0, 24.0)
    cdef double star_rotation = _d2r(lst * 15.0)
    cdef double lat_r = _d2r(latitude)
    cdef double star_pole_x = 0.0
    cdef double star_pole_y = sin(lat_r)
    cdef double star_pole_z = -cos(lat_r)
    cdef double g = _pymod(sun_ma_epoch + sun_ma_rate * d, 360.0)
    cdef double q = _pymod(sun_ml_epoch + sun_ml_rate * d, 360.0)
    cdef double sun_lon = q + sun_ecc * sin(_d2r(g)) + sun_ecc2 * sin(_d2r(2.0 * g))
    cdef double ecl = obliquity_deg - obliquity_drift * d
    cdef double ln = _d2r(sun_lon)
    cdef double ep = _d2r(ecl)
    cdef double sun_ra = _r2d(atan2(sin(ln) * cos(ep) - tan(0.0) * sin(ep), cos(ln)))
    sun_ra = _pymod(sun_ra, 360.0)
    cdef double sun_dec = _r2d(asin(_clamp11(sin(0.0) * cos(ep) + cos(0.0) * sin(ep) * sin(ln))))
    cdef double lp = _pymod(moon_ml_epoch + moon_ml_rate * d, 360.0)
    cdef double mp = _pymod(moon_ma_epoch + moon_ma_rate * d, 360.0)
    cdef double ms = _pymod(sun_ma_epoch + sun_ma_rate * d, 360.0)
    cdef double dm = _pymod(moon_el_epoch + moon_el_rate * d, 360.0)
    cdef double f = _pymod(moon_af_epoch + moon_af_rate * d, 360.0)
    cdef double moon_lon = lp + moon_lon1 * sin(_d2r(mp)) \
        + moon_lon2 * sin(_d2r(2.0 * dm - mp)) \
        + moon_lon3 * sin(_d2r(2.0 * dm)) \
        + moon_lon4 * sin(_d2r(ms)) \
        + moon_lon5 * sin(_d2r(2.0 * mp - 2.0 * dm))
    cdef double moon_lat = moon_lat1 * sin(_d2r(f)) \
        + moon_lat2 * sin(_d2r(mp + f)) \
        + moon_lat3 * sin(_d2r(mp - f)) \
        + moon_lat4 * sin(_d2r(2.0 * dm - f))
    moon_lon = _pymod(moon_lon, 360.0)
    cdef double mln = _d2r(moon_lon)
    cdef double mbt = _d2r(moon_lat)
    cdef double moon_ra = _r2d(atan2(sin(mln) * cos(ep) - tan(mbt) * sin(ep), cos(mln)))
    moon_ra = _pymod(moon_ra, 360.0)
    cdef double moon_dec = _r2d(asin(_clamp11(sin(mbt) * cos(ep) + cos(mbt) * sin(ep) * sin(mln))))
    cdef double h_sun = _d2r((lst - sun_ra / 15.0) * 15.0)
    cdef double sin_alt_sun = sin(lat_r) * sin(_d2r(sun_dec)) + cos(lat_r) * cos(_d2r(sun_dec)) * cos(h_sun)
    cdef double alt_sun = asin(_clamp11(sin_alt_sun))
    cdef double cos_az_sun = (sin(_d2r(sun_dec)) - sin(alt_sun) * sin(lat_r)) / (cos(alt_sun) * cos(lat_r) + 1e-9)
    cos_az_sun = _clamp11(cos_az_sun)
    cdef double az_sun = _r2d(acos(cos_az_sun))
    if sin(h_sun) > 0.0:
        az_sun = 360.0 - az_sun
    cdef double alt_sun_d = _r2d(alt_sun)
    cdef double a_sun = _d2r(alt_sun_d)
    cdef double z_sun = _d2r(az_sun)
    cdef double sun_dx = sin(z_sun) * cos(a_sun)
    cdef double sun_dy = sin(a_sun)
    cdef double sun_dz = -cos(z_sun) * cos(a_sun)
    cdef double h_moon = _d2r((lst - moon_ra / 15.0) * 15.0)
    cdef double sin_alt_moon = sin(lat_r) * sin(_d2r(moon_dec)) + cos(lat_r) * cos(_d2r(moon_dec)) * cos(h_moon)
    cdef double alt_moon = asin(_clamp11(sin_alt_moon))
    cdef double cos_az_moon = (sin(_d2r(moon_dec)) - sin(alt_moon) * sin(lat_r)) / (cos(alt_moon) * cos(lat_r) + 1e-9)
    cos_az_moon = _clamp11(cos_az_moon)
    cdef double az_moon = _r2d(acos(cos_az_moon))
    if sin(h_moon) > 0.0:
        az_moon = 360.0 - az_moon
    cdef double alt_moon_d = _r2d(alt_moon)
    cdef double a_moon = _d2r(alt_moon_d)
    cdef double z_moon = _d2r(az_moon)
    cdef double moon_dx = sin(z_moon) * cos(a_moon)
    cdef double moon_dy = sin(a_moon)
    cdef double moon_dz = -cos(z_moon) * cos(a_moon)
    cdef double age = _pymod(d - new_moon_jd, synodic_month)
    cdef double moon_phase = age / synodic_month
    return (sun_dx, sun_dy, sun_dz, moon_dx, moon_dy, moon_dz, moon_phase,
            star_rotation, day_seconds, sim_seconds,
            star_pole_x, star_pole_y, star_pole_z)
