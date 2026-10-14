# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


class BlackHolePersistenceMixin:
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_schwarzschild_radius": self._schwarzschild_radius,
            "_lensing_strength": self._lensing_strength,
            "_show_disk": self._show_disk,
            "_disk_inner": self._disk_inner,
            "_disk_outer": self._disk_outer,
            "_disk_brightness": self._disk_brightness,
            "_inner_color": list(self._inner_color),
            "_outer_color": list(self._outer_color),
            "_rotation_speed": self._rotation_speed,
            "_doppler_strength": self._doppler_strength,
            "_turbulence": self._turbulence,
            "_photon_intensity": self._photon_intensity,
            "_photon_width": self._photon_width,
            "_fringe": self._fringe,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> BlackHole:
        inst = super().deserialize(data)
        inst._schwarzschild_radius = float(data.get("_schwarzschild_radius", 2.0))
        inst._lensing_strength = float(data.get("_lensing_strength", 1.0))
        inst._show_disk = bool(data.get("_show_disk", True))
        inst._disk_inner = float(data.get("_disk_inner", 3.0))
        inst._disk_outer = float(data.get("_disk_outer", 8.0))
        inst._disk_brightness = float(data.get("_disk_brightness", 2.2))
        inst._inner_color = tuple(data.get("_inner_color", [0.7, 0.82, 1.0]))
        inst._outer_color = tuple(data.get("_outer_color", [1.0, 0.45, 0.12]))
        inst._rotation_speed = float(data.get("_rotation_speed", 0.6))
        inst._doppler_strength = float(data.get("_doppler_strength", 1.0))
        inst._turbulence = float(data.get("_turbulence", 0.7))
        inst._photon_intensity = float(data.get("_photon_intensity", 3.0))
        inst._photon_width = float(data.get("_photon_width", 0.08))
        inst._fringe = float(data.get("_fringe", 0.02))
        inst._ctx = None
        inst._prog = None
        inst._vao = None
        inst._vbo = None
        inst._ibo = None
        return inst
