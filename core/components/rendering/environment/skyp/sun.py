# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3, Quat, FLOAT_TYPE
from core.components.lighting.lightp import Light, LightType
from .astro import _J2000_JD, _julian_day, _julian_day_to_ymd, _moon_equatorial, nearest_solar_eclipse


class ProceduralSkySunMixin:

    def set_time(self, year=None, month=None, day=None,
                 hour=None, minute=None, second=None):
        if year is not None:
            self.year = int(year)
        if month is not None:
            self.month = int(month)
        if day is not None:
            self.day = int(day)
        if hour is not None:
            self.hour = int(hour)
        if minute is not None:
            self.minute = int(minute)
        if second is not None:
            self.second = int(second)
        self._time_frac = 0.0
        try:
            self._time_transition = None
        except Exception:
            pass
        self._invalidate_time()

    def _clock_total(self) -> float:
        ty = int(self.year)
        carry, tm = divmod(int(self.month) - 1, 12)
        tm += 1
        ty += carry
        base = (_julian_day(ty, tm, int(self.day)) - _J2000_JD - 0.5) * 86400.0
        return base + int(self.hour) * 3600.0 + int(self.minute) * 60.0 + int(self.second) + float(getattr(self, "_time_frac", 0.0) or 0.0)

    def _apply_clock_total(self, total: float):
        days = math.floor(total / 86400.0)
        sod = total - days * 86400.0
        y, m, d = _julian_day_to_ymd(days + _J2000_JD + 0.5)
        h = int(sod // 3600)
        rem = sod - h * 3600.0
        mi = int(rem // 60)
        s = int(rem - mi * 60.0)
        if h < 0:
            h = 0
        elif h > 23:
            h = 23
        if mi < 0:
            mi = 0
        elif mi > 59:
            mi = 59
        if s < 0:
            s = 0
        elif s > 59:
            s = 59
        self.year, self.month, self.day, self.hour, self.minute = int(y), int(m), int(d), h, mi
        self.second = s
        frac = rem - mi * 60.0 - s
        if frac < 0.0 or frac >= 1.0:
            frac = 0.0
        self._time_frac = frac

    def transition_to_time(self, year=None, month=None, day=None,
                           hour=None, minute=None, second=None,
                           duration: float = 1.0, smooth: bool = True):
        try:
            ty = int(self.year) if year is None else int(year)
            tm = int(self.month) if month is None else int(month)
            td = int(self.day) if day is None else int(day)
            th = int(self.hour) if hour is None else int(hour)
            tmi = int(self.minute) if minute is None else int(minute)
            ts = int(self.second) if second is None else int(second)
            dur = float(duration)
        except Exception:
            return False
        carry, tm = divmod(tm - 1, 12)
        tm += 1
        ty += carry
        try:
            start = self._clock_total()
        except Exception:
            return False
        end = (_julian_day(ty, tm, td) - _J2000_JD - 0.5) * 86400.0 + th * 3600.0 + tmi * 60.0 + ts
        if dur <= 0.0 or end == start:
            try:
                self._time_transition = None
            except Exception:
                pass
            self._apply_clock_total(end)
            self._invalidate_time()
            return True
        try:
            self._time_transition = (start, end, dur, 0.0, bool(smooth))
        except Exception:
            return False
        return True

    def cancel_time_transition(self):
        try:
            self._time_transition = None
        except Exception:
            pass
        return True

    def advance_time(self, dt_seconds: float):
        try:
            step = float(dt_seconds)
        except Exception:
            return
        if step == 0.0:
            return
        try:
            self._time_transition = None
        except Exception:
            pass
        try:
            acc = float(getattr(self, "_time_frac", 0.0)) + step
        except Exception:
            acc = step
        import math as _m
        frac, full = _m.modf(acc)
        full = int(full)
        if full != 0:
            total = self.second + full
            carry, self.second = divmod(total, 60)
            self._carry_minutes(carry)
        self._time_frac = frac
        self._invalidate_time()

    def _days_in_month(self, y: int, m: int) -> int:
        if m == 2:
            leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
            return 29 if leap else 28
        return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30

    def _normalize_days(self):
        while self.day > self._days_in_month(self.year, self.month):
            self.day -= self._days_in_month(self.year, self.month)
            self.month += 1
            if self.month > 12:
                self.month = 1
                self.year += 1
        while self.day < 1:
            self.month -= 1
            if self.month < 1:
                self.month = 12
                self.year -= 1
            self.day += self._days_in_month(self.year, self.month)

    def _carry_days(self, n: int):
        if n == 0:
            return
        self.day += n
        self._normalize_days()

    def _carry_hours(self, n: int):
        if n == 0:
            return
        total = self.hour + n
        carry, self.hour = divmod(total, 24)
        self._carry_days(carry)

    def _carry_minutes(self, n: int):
        if n == 0:
            return
        total = self.minute + n
        carry, self.minute = divmod(total, 60)
        self._carry_hours(carry)

    def _on_time_field_set(self, name: str, value: int) -> bool:
        v = int(value)
        before = self._time_fields_key()
        if name == "second":
            carry, self.second = divmod(v, 60)
            self._carry_minutes(carry)
        elif name == "minute":
            carry, self.minute = divmod(v, 60)
            self._carry_hours(carry)
        elif name == "hour":
            carry, self.hour = divmod(v, 24)
            self._carry_days(carry)
        elif name == "day":
            self.day = v
            self._normalize_days()
        elif name == "month":
            carry, self.month = divmod(v - 1, 12)
            self.month += 1
            self.year += carry
        else:
            return False
        self._time_frac = 0.0
        self._invalidate_time()
        return self._time_fields_key() != before

    def set_sun_light(self, entity) -> bool:
        if entity is None or entity.transform is None:
            return False
        self.sun_light_entity_id = entity.id
        return True

    def _btn_nearest_solar_eclipse(self):
        p = self._astro_params()
        jd = _julian_day(self.year, self.month, self.day)
        civil = self.hour + self.minute / 60.0 + self.second / 3600.0
        utc = civil - self.utc_offset
        d0 = jd - _J2000_JD + utc / 24.0
        best = nearest_solar_eclipse(d0, p)
        if best is None:
            return
        jd = best[0] + _J2000_JD
        moon_ra, moon_dec = _moon_equatorial(best[0], p)
        gmst = (p["gmst_epoch"] + p["gmst_rate"] * best[0]) % 24.0
        sub_lon = ((moon_ra - 15.0 * gmst + 180.0) % 360.0) - 180.0
        self.latitude = max(-90.0, min(90.0, moon_dec))
        self.longitude = sub_lon
        self.utc_offset = float(int(round(self.longitude / 15.0)))
        local_hours = ((jd + 0.5) % 1.0) * 24.0 + self.utc_offset
        day_shift = math.floor(local_hours / 24.0)
        local_hours -= day_shift * 24.0
        y, m, day = _julian_day_to_ymd(jd + day_shift)
        h = int(local_hours)
        mi = int((local_hours - h) * 60.0)
        s = int(round(((local_hours - h) * 60.0 - mi) * 60.0))
        if s == 60:
            s = 0
            mi += 1
        if mi == 60:
            mi = 0
            h += 1
        self.set_time(year=y, month=m, day=int(day), hour=h, minute=mi, second=s)

    @property
    def sun_direction(self) -> Vec3:
        self._update_time_cache()
        return self._sun_dir

    @property
    def moon_direction(self) -> Vec3:
        self._update_time_cache()
        return self._moon_dir

    @property
    def moon_phase(self) -> float:
        self._update_time_cache()
        return self._moon_phase

    @property
    def day_seconds(self) -> float:
        self._update_time_cache()
        return self._day_seconds

    @property
    def sim_seconds(self) -> float:
        self._update_time_cache()
        return self._sim_seconds

    @property
    def eclipse_darkness(self) -> float:
        self._update_time_cache()
        return self._eclipse_darkness

    def get_sun_light(self):
        scene = self._entity._scene if self._entity else None
        ent = None
        if self.sun_light_entity_id and scene:
            ent = scene.get_entity(self.sun_light_entity_id)
        if ent is not None:
            l = ent.get_component(Light)
            t = ent.transform
            if l and l.enabled and t and l.light_type == LightType.DIRECTIONAL:
                return (l, t)
        if scene:
            try:
                cached = self._sun_light_cache
            except Exception:
                cached = None
            if cached is not None:
                try:
                    crv, ceid, cl, ct = cached
                    if scene._render_version == crv:
                        ce = scene.get_entity(ceid)
                        if ce is not None and ce._active and ce.transform is ct:
                            curl = ce.get_component(Light)
                            if curl is cl and cl.enabled and cl.light_type == LightType.DIRECTIONAL:
                                return (cl, ct)
                except Exception:
                    pass
                try:
                    self._sun_light_cache = None
                except Exception:
                    pass
            for e in scene.get_entities_with_component(Light):
                l = e.get_component(Light)
                t = e.transform
                if l and l.enabled and t and l.light_type == LightType.DIRECTIONAL:
                    try:
                        self._sun_light_cache = (scene._render_version, e.id, l, t)
                    except Exception:
                        pass
                    return (l, t)
        return None

    def _sync_sun_light(self):
        if not self.enabled:
            return
        self._update_time_cache()
        sl = self.get_sun_light()
        if sl is None:
            return
        _l, tr = sl
        try:
            sd = self._sun_dir
            last = self._synced_sun
            ent = tr._entity if tr is not None else None
            eid = ent._id if ent is not None else None
            if last is not None and eid is not None and last == (sd._x, sd._y, sd._z, eid):
                return
        except Exception:
            sd = None
            eid = None
        if sd is None:
            try:
                sd = self._sun_dir
            except Exception:
                return
        f = sd * -1.0
        r = f.cross(Vec3.up())
        rl = r.length()
        if rl < 1e-6:
            r = f.cross(Vec3.right())
            rl = r.length()
        r = r * (1.0 / rl)
        u = r.cross(f)
        m3 = np.eye(3, dtype=FLOAT_TYPE)
        m3[0] = [r.x, r.y, r.z]
        m3[1] = [u.x, u.y, u.z]
        m3[2] = [-f.x, -f.y, -f.z]
        tr.local_rotation = Quat._from_rotation_matrix3(m3.T)
        try:
            self._synced_sun = (sd._x, sd._y, sd._z, eid)
        except Exception:
            pass
