# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.audio.efx import get_reverb_preset, reverb_preset_names, normalize_preset_name, gain_to_mb, ensure_efx
from core.components.audio.reverb.efx import ReverbZoneEfxMixin
from core.components.audio.reverb.spatial import ReverbZoneSpatialMixin


@ComponentRegistry.register
class ReverbZone(ReverbZoneEfxMixin, ReverbZoneSpatialMixin, Component):
    _icon = "ReverbZone.png"
    _gizmo_icon_color = (80, 140, 220)
    _gizmo_icon_label = "RZ"
    _show_gizmo_icon = True
    _gizmo_pass = "audio"
    _instances = set()
    _last_routing_frame = -1
    _preset_params = frozenset({
        "room", "room_hf", "room_lf", "decay_time", "decay_hf_ratio",
        "reflections", "reflections_delay", "reverb", "reverb_delay",
        "diffusion", "density", "hf_reference", "lf_reference", "room_rolloff_factor",
    })

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        try:
            options = list(reverb_preset_names())
        except Exception:
            options = ["Off", "Generic", "User"]
        if "User" not in options:
            options = options + ["User"]
        return [
            InspectorField("", "Zone", FieldType.HEADER),
            InspectorField("min_distance", "Min Distance", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("max_distance", "Max Distance", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=1.0, decimals=2),
            InspectorField("preset", "Reverb Preset", FieldType.ENUM, enum_options=options),
            InspectorField("", "Room", FieldType.HEADER),
            InspectorField("room", "Room", FieldType.FLOAT, min_val=-10000.0, max_val=0.0, step=10.0, decimals=0),
            InspectorField("room_hf", "Room HF", FieldType.FLOAT, min_val=-10000.0, max_val=0.0, step=10.0, decimals=0),
            InspectorField("room_lf", "Room LF", FieldType.FLOAT, min_val=-10000.0, max_val=0.0, step=10.0, decimals=0),
            InspectorField("", "Decay", FieldType.HEADER),
            InspectorField("decay_time", "Decay Time", FieldType.FLOAT, min_val=0.1, max_val=20.0, step=0.1, decimals=2),
            InspectorField("decay_hf_ratio", "Decay HFRatio", FieldType.FLOAT, min_val=0.1, max_val=2.0, step=0.01, decimals=2),
            InspectorField("", "Reflections", FieldType.HEADER),
            InspectorField("reflections", "Reflections", FieldType.FLOAT, min_val=-10000.0, max_val=1000.0, step=10.0, decimals=0),
            InspectorField("reflections_delay", "Reflections Delay", FieldType.FLOAT, min_val=0.0, max_val=0.3, step=0.001, decimals=3),
            InspectorField("", "Reverb", FieldType.HEADER),
            InspectorField("reverb", "Reverb", FieldType.FLOAT, min_val=-10000.0, max_val=2000.0, step=10.0, decimals=0),
            InspectorField("reverb_delay", "Reverb Delay", FieldType.FLOAT, min_val=0.0, max_val=0.1, step=0.001, decimals=3),
            InspectorField("hf_reference", "HFReference", FieldType.FLOAT, min_val=1000.0, max_val=20000.0, step=10.0, decimals=0),
            InspectorField("lf_reference", "LFReference", FieldType.FLOAT, min_val=20.0, max_val=1000.0, step=5.0, decimals=0),
            InspectorField("room_rolloff_factor", "Room Rolloff Factor", FieldType.FLOAT, min_val=0.0, max_val=10.0, step=0.01, decimals=2),
            InspectorField("", "Mix", FieldType.HEADER),
            InspectorField("diffusion", "Diffusion", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.5, decimals=1),
            InspectorField("density", "Density", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.5, decimals=1),
        ]

    def __init__(self):
        object.__setattr__(self, "_suspend_preset_sync", True)
        super().__init__()
        object.__setattr__(self, "preset", "Generic")
        object.__setattr__(self, "min_distance", 10.0)
        object.__setattr__(self, "max_distance", 15.0)
        object.__setattr__(self, "room", -1000.0)
        object.__setattr__(self, "room_hf", -100.0)
        object.__setattr__(self, "room_lf", 0.0)
        object.__setattr__(self, "decay_time", 1.49)
        object.__setattr__(self, "decay_hf_ratio", 0.83)
        object.__setattr__(self, "reflections", -2602.0)
        object.__setattr__(self, "reflections_delay", 0.007)
        object.__setattr__(self, "reverb", 200.0)
        object.__setattr__(self, "reverb_delay", 0.011)
        object.__setattr__(self, "diffusion", 100.0)
        object.__setattr__(self, "density", 100.0)
        object.__setattr__(self, "hf_reference", 5000.0)
        object.__setattr__(self, "lf_reference", 250.0)
        object.__setattr__(self, "room_rolloff_factor", 0.0)
        object.__setattr__(self, "wet_mix", 1.0)
        object.__setattr__(self, "_effect_id", 0)
        object.__setattr__(self, "_slot_id", 0)
        object.__setattr__(self, "_params_sig", None)
        object.__setattr__(self, "_applied_preset", "Generic")
        object.__setattr__(self, "_preset_params_sig", None)
        object.__setattr__(self, "_suspend_preset_sync", False)
        try:
            self._preset_params_sig = self._params_signature()
            self._params_sig = None
        except Exception:
            pass

    def _is_entity_active(self) -> bool:
        try:
            ent = self._entity
            if ent is None:
                return True
            return bool(ent._active)
        except Exception:
            return True

    def _is_active(self) -> bool:
        try:
            return bool(self.enabled) and bool(self._is_entity_active())
        except Exception:
            return False

    def _is_off(self) -> bool:
        try:
            return str(getattr(self, "preset", "")) == "Off"
        except Exception:
            return False

    def _ensure_registered(self):
        try:
            ReverbZone._instances.add(self)
        except Exception:
            pass

    def _unregister(self):
        try:
            ReverbZone._instances.discard(self)
        except Exception:
            pass

    def on_awake(self):
        self._ensure_registered()
        try:
            self._sync_preset_tracking()
        except Exception:
            pass

    def on_start(self):
        self._ensure_registered()
        try:
            self._sync_preset_tracking()
        except Exception:
            pass
        try:
            self._ensure_effect()
        except Exception:
            pass

    def on_enable(self):
        self._ensure_registered()
        try:
            self._sync_preset_tracking()
        except Exception:
            pass
        try:
            self._ensure_effect()
        except Exception:
            pass

    def on_disable(self):
        try:
            self._disconnect_owned_sources()
        except Exception:
            pass
        try:
            self._cleanup()
        except Exception:
            pass

    def on_destroy(self):
        try:
            self._disconnect_owned_sources()
        except Exception:
            pass
        try:
            self._cleanup()
        except Exception:
            pass
        try:
            self._unregister()
        except Exception:
            pass

    def on_update(self, dt: float):
        self._ensure_registered()
        try:
            self._sync_preset_tracking()
        except Exception:
            pass
        if not self._is_active():
            if getattr(self, "_slot_id", 0) or getattr(self, "_effect_id", 0):
                try:
                    self._disconnect_owned_sources()
                except Exception:
                    pass
                try:
                    self._cleanup()
                except Exception:
                    pass
            return
        try:
            if not self._reverb_allowed():
                return
        except Exception:
            pass
        if self._is_off():
            if getattr(self, "_slot_id", 0) or getattr(self, "_effect_id", 0):
                try:
                    self._disconnect_owned_sources()
                except Exception:
                    pass
                try:
                    self._cleanup()
                except Exception:
                    pass
            return
        try:
            if not bool(ensure_efx()):
                return
        except Exception:
            return
        try:
            self._ensure_effect()
        except Exception:
            return
        try:
            self._apply_effect_params(force=False)
        except Exception:
            pass
        try:
            ReverbZone.update_routing(force=False)
        except Exception:
            pass

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "preset": str(getattr(self, "preset", "Generic")),
            "min_distance": self.min_distance,
            "max_distance": self.max_distance,
            "room": self.room,
            "room_hf": self.room_hf,
            "room_lf": self.room_lf,
            "decay_time": self.decay_time,
            "decay_hf_ratio": self.decay_hf_ratio,
            "reflections": self.reflections,
            "reflections_delay": self.reflections_delay,
            "reverb": self.reverb,
            "reverb_delay": self.reverb_delay,
            "diffusion": self.diffusion,
            "density": self.density,
            "hf_reference": self.hf_reference,
            "lf_reference": self.lf_reference,
            "room_rolloff_factor": self.room_rolloff_factor,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict):
        z = cls()
        try:
            z.enabled = data.get("enabled", True)
        except Exception:
            pass
        try:
            object.__setattr__(z, "_suspend_preset_sync", True)
            z.min_distance = float(data.get("min_distance", 10.0))
            z.max_distance = float(data.get("max_distance", 15.0))
            if "room" in data:
                z.room = float(data.get("room", -1000.0))
                z.room_hf = float(data.get("room_hf", -100.0))
                z.room_lf = float(data.get("room_lf", 0.0))
                z.decay_time = float(data.get("decay_time", 1.49))
                z.decay_hf_ratio = float(data.get("decay_hf_ratio", 0.83))
                z.reflections = float(data.get("reflections", -2602.0))
                z.reflections_delay = float(data.get("reflections_delay", 0.007))
                z.reverb = float(data.get("reverb", 200.0))
                z.reverb_delay = float(data.get("reverb_delay", 0.011))
                z.diffusion = float(data.get("diffusion", 100.0))
                z.density = float(data.get("density", 100.0))
                z.hf_reference = float(data.get("hf_reference", 5000.0))
                z.lf_reference = float(data.get("lf_reference", 250.0))
                z.room_rolloff_factor = float(data.get("room_rolloff_factor", 0.0))
                raw_preset = str(data.get("preset", "User"))
                try:
                    z.preset = normalize_preset_name(raw_preset)
                except Exception:
                    z.preset = "User"
                if z.preset != "User" and z.preset != "Off":
                    try:
                        table = get_reverb_preset(z.preset)
                        if table is not None:
                            matches = (
                                abs(float(z.room) - float(table["room"])) < 0.5
                                and abs(float(z.room_hf) - float(table["room_hf"])) < 0.5
                                and abs(float(z.decay_time) - float(table["decay_time"])) < 0.001
                            )
                            if not matches:
                                z.preset = "User"
                    except Exception:
                        pass
            else:
                legacy_preset = str(data.get("preset", "Generic"))
                try:
                    table = get_reverb_preset(legacy_preset)
                except Exception:
                    table = None
                if table is not None and legacy_preset != "User":
                    z.room = float(table["room"])
                    z.room_hf = float(table["room_hf"])
                    z.room_lf = float(table["room_lf"])
                    z.decay_time = float(table["decay_time"])
                    z.decay_hf_ratio = float(table["decay_hf_ratio"])
                    z.reflections = float(table["reflections"])
                    z.reflections_delay = float(table["reflections_delay"])
                    z.reverb = float(table["reverb"])
                    z.reverb_delay = float(table["reverb_delay"])
                    z.diffusion = float(table["diffusion"])
                    z.density = float(table["density"])
                    z.hf_reference = float(table["hf_reference"])
                    z.lf_reference = float(table["lf_reference"])
                    z.room_rolloff_factor = float(table.get("room_rolloff", 0.0))
                    try:
                        z.preset = normalize_preset_name(legacy_preset)
                    except Exception:
                        z.preset = "Generic"
                else:
                    try:
                        lin_density = float(data.get("density", 1.0))
                        lin_diffusion = float(data.get("diffusion", 1.0))
                        lin_gain = float(data.get("reverb_gain", 0.32))
                        lin_gain_hf = float(data.get("gain_hf", 0.89))
                        lin_refl = float(data.get("reflections_gain", 0.05))
                        lin_late = float(data.get("late_reverb_gain", 1.26))
                    except Exception:
                        lin_density = 1.0
                        lin_diffusion = 1.0
                        lin_gain = 0.32
                        lin_gain_hf = 0.89
                        lin_refl = 0.05
                        lin_late = 1.26
                    z.density = max(0.0, min(100.0, lin_density * 100.0))
                    z.diffusion = max(0.0, min(100.0, lin_diffusion * 100.0))
                    try:
                        z.room = float(gain_to_mb(lin_gain))
                    except Exception:
                        z.room = -1000.0
                    try:
                        hend = float(gain_to_mb(lin_gain_hf)) - float(gain_to_mb(lin_gain))
                        z.room_hf = max(-10000.0, min(0.0, float(gain_to_mb(lin_gain_hf))))
                    except Exception:
                        z.room_hf = -100.0
                    z.room_lf = 0.0
                    z.decay_time = float(data.get("decay_time", 1.49))
                    z.decay_hf_ratio = float(data.get("decay_hf_ratio", 0.83))
                    try:
                        z.reflections = float(gain_to_mb(lin_refl))
                    except Exception:
                        z.reflections = -2602.0
                    z.reflections_delay = float(data.get("reflections_delay", 0.007))
                    try:
                        z.reverb = float(gain_to_mb(lin_late))
                    except Exception:
                        z.reverb = 200.0
                    z.reverb_delay = float(data.get("late_reverb_delay", 0.011))
                    z.hf_reference = 5000.0
                    z.lf_reference = 250.0
                    z.room_rolloff_factor = float(data.get("room_rolloff_factor", data.get("room_rolloff", 0.0)))
                    z.preset = "User"
                z.min_distance = float(data.get("min_distance", 10.0))
                z.max_distance = float(data.get("max_distance", 15.0))
            try:
                z._applied_preset = str(getattr(z, "preset", "User"))
            except Exception:
                pass
            try:
                z._preset_params_sig = z._params_signature()
            except Exception:
                pass
            z._params_sig = None
        finally:
            try:
                object.__setattr__(z, "_suspend_preset_sync", False)
            except Exception:
                pass
        return z
