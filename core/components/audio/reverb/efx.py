# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.foundation.logger import Logger


class ReverbZoneEfxMixin:
    def __setattr__(self, name: str, value):
        from core.audio.efx import get_reverb_preset, normalize_preset_name
        suspend = False
        try:
            suspend = bool(object.__getattribute__(self, "_suspend_preset_sync"))
        except Exception:
            suspend = True
        if suspend or name.startswith("_") or name in ("min_distance", "max_distance", "wet_mix", "enabled"):
            object.__setattr__(self, name, value)
            return
        if name == "preset":
            try:
                normalized = normalize_preset_name(value)
            except Exception:
                normalized = "User"
            object.__setattr__(self, "preset", normalized)
            if suspend:
                return
            if normalized == "User" or normalized == "Off":
                try:
                    object.__setattr__(self, "_applied_preset", normalized)
                except Exception:
                    pass
                try:
                    object.__setattr__(self, "_params_sig", None)
                except Exception:
                    pass
                try:
                    self._refresh_live_effect()
                except Exception:
                    pass
                return
            try:
                data = get_reverb_preset(normalized)
            except Exception:
                data = None
            if data is None:
                try:
                    object.__setattr__(self, "preset", "User")
                    object.__setattr__(self, "_applied_preset", "User")
                except Exception:
                    pass
                return
            try:
                object.__setattr__(self, "_suspend_preset_sync", True)
                for key, attr in (
                    ("room", "room"), ("room_hf", "room_hf"), ("room_lf", "room_lf"),
                    ("decay_time", "decay_time"), ("decay_hf_ratio", "decay_hf_ratio"),
                    ("reflections", "reflections"), ("reflections_delay", "reflections_delay"),
                    ("reverb", "reverb"), ("reverb_delay", "reverb_delay"),
                    ("diffusion", "diffusion"), ("density", "density"),
                    ("hf_reference", "hf_reference"), ("lf_reference", "lf_reference"),
                    ("room_rolloff", "room_rolloff_factor"),
                ):
                    try:
                        object.__setattr__(self, attr, float(data[key]))
                    except Exception:
                        pass
            finally:
                try:
                    object.__setattr__(self, "_suspend_preset_sync", False)
                except Exception:
                    pass
            try:
                object.__setattr__(self, "_applied_preset", normalized)
            except Exception:
                pass
            try:
                object.__setattr__(self, "_preset_params_sig", self._params_signature())
            except Exception:
                pass
            try:
                object.__setattr__(self, "_params_sig", None)
            except Exception:
                pass
            try:
                self._refresh_live_effect()
            except Exception:
                pass
            return
        if name in type(self)._preset_params:
            object.__setattr__(self, name, value)
            if suspend:
                return
            try:
                current = str(object.__getattribute__(self, "preset"))
            except Exception:
                current = "User"
            if current != "User" and current != "Off":
                try:
                    object.__setattr__(self, "preset", "User")
                except Exception:
                    pass
                try:
                    object.__setattr__(self, "_applied_preset", "User")
                except Exception:
                    pass
            try:
                object.__setattr__(self, "_params_sig", None)
            except Exception:
                pass
            try:
                self._refresh_live_effect()
            except Exception:
                pass
            return
        object.__setattr__(self, name, value)

    def _refresh_live_effect(self):
        try:
            effect = int(getattr(self, "_effect_id", 0) or 0)
            if not effect:
                return
            self._apply_effect_params(force=True)
        except Exception:
            pass

    def _reverb_allowed(self) -> bool:
        from core.audio.efx import reverb_enabled
        try:
            return bool(reverb_enabled())
        except Exception:
            return True

    def _params_signature(self):
        try:
            return (
                round(float(self.room), 2),
                round(float(self.room_hf), 2),
                round(float(self.room_lf), 2),
                round(float(self.decay_time), 4),
                round(float(self.decay_hf_ratio), 4),
                round(float(self.reflections), 2),
                round(float(self.reflections_delay), 4),
                round(float(self.reverb), 2),
                round(float(self.reverb_delay), 4),
                round(float(self.diffusion), 2),
                round(float(self.density), 2),
                round(float(self.hf_reference), 1),
                round(float(self.lf_reference), 1),
                round(float(self.room_rolloff_factor), 3),
            )
        except Exception:
            return None

    def _sync_preset_tracking(self):
        from core.audio.efx import get_reverb_preset
        try:
            current = str(getattr(self, "preset", "User"))
        except Exception:
            return
        if current == "User" or current == "Off":
            try:
                self._applied_preset = current
            except Exception:
                pass
            return
        try:
            data = get_reverb_preset(current)
        except Exception:
            data = None
        if data is None:
            try:
                object.__setattr__(self, "_suspend_preset_sync", True)
                object.__setattr__(self, "preset", "User")
            finally:
                try:
                    object.__setattr__(self, "_suspend_preset_sync", False)
                except Exception:
                    pass
            try:
                self._applied_preset = "User"
            except Exception:
                pass
            return
        try:
            sig = self._params_signature()
        except Exception:
            sig = None
        if self._applied_preset != current:
            self._applied_preset = current
            self._preset_params_sig = sig
            self._params_sig = None

    def apply_preset_now(self, name: str) -> bool:
        try:
            self.preset = str(name)
        except Exception:
            return False
        if self._effect_id:
            self._apply_effect_params(force=True)
        return True

    def _apply_effect_params(self, force: bool = False) -> bool:
        from core.audio.efx import apply_reverb_mb, set_aux_slot_gain
        if not self._effect_id:
            return False
        if self._is_off():
            return False
        sig = self._params_signature()
        if not force and sig is not None and sig == self._params_sig:
            return True
        try:
            ok = bool(apply_reverb_mb(
                int(self._effect_id),
                float(self.room), float(self.room_hf), float(self.room_lf),
                float(self.decay_time), float(self.decay_hf_ratio),
                float(self.reflections), float(self.reflections_delay),
                float(self.reverb), float(self.reverb_delay),
                float(self.diffusion), float(self.density),
                float(self.hf_reference), float(self.lf_reference),
                float(self.room_rolloff_factor),
            ))
            if ok:
                try:
                    set_aux_slot_gain(int(self._slot_id), 1.0)
                except Exception:
                    pass
                self._params_sig = sig
                self._preset_params_sig = sig
            return bool(ok)
        except Exception as e:
            try:
                Logger.error(str("ReverbZone: failed to apply params: ") + str(e))
            except Exception:
                pass
            return False

    def _disconnect_owned_sources(self):
        try:
            slot = int(getattr(self, "_slot_id", 0) or 0)
        except Exception:
            return
        if not slot:
            return
        try:
            mgr = AudioSourceManager.instance()
        except Exception:
            mgr = None
        if not mgr:
            return
        try:
            for src_id in list(mgr.get_active_source_ids()):
                try:
                    if int(mgr.get_source_aux_slot(int(src_id))) == int(slot):
                        try:
                            mgr.set_source_aux_send(int(src_id), 0, 0, 0)
                        except Exception:
                            pass
                        try:
                            if hasattr(mgr, "_source_aux_gain"):
                                mgr._source_aux_gain[int(src_id)] = 0.0
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def _cleanup(self):
        from core.audio.efx import delete_aux_slot, delete_effect, set_aux_slot_effect
        try:
            self._disconnect_owned_sources()
        except Exception:
            pass
        try:
            slot = int(getattr(self, "_slot_id", 0) or 0)
        except Exception:
            slot = 0
        try:
            effect = int(getattr(self, "_effect_id", 0) or 0)
        except Exception:
            effect = 0
        if slot:
            try:
                try:
                    set_aux_slot_effect(int(slot), 0)
                except Exception:
                    pass
                delete_aux_slot(int(slot))
            except Exception:
                pass
            try:
                self._slot_id = 0
            except Exception:
                pass
        if effect:
            try:
                delete_effect(int(effect))
            except Exception:
                pass
            try:
                self._effect_id = 0
            except Exception:
                pass
        self._params_sig = None

    def _ensure_effect(self) -> bool:
        from core.audio.sys import AudioSourceManager
        from core.audio.efx import ensure_efx, create_effect, delete_effect, is_effect, apply_reverb_mb, create_aux_slot, is_aux_slot, set_aux_slot_effect, set_aux_slot_gain
        try:
            if not self._is_active():
                return False
            if not self._reverb_allowed():
                return False
            if self._is_off():
                try:
                    self._cleanup()
                except Exception:
                    pass
                return False
            if not bool(ensure_efx()):
                return False
        except Exception:
            return False
        try:
            effect = int(getattr(self, "_effect_id", 0) or 0)
            slot = int(getattr(self, "_slot_id", 0) or 0)
        except Exception:
            effect = 0
            slot = 0
        valid_effect = False
        valid_slot = False
        try:
            valid_effect = bool(effect) and bool(is_effect(int(effect)))
        except Exception:
            valid_effect = False
        try:
            valid_slot = bool(slot) and bool(is_aux_slot(int(slot)))
        except Exception:
            valid_slot = False
        if valid_effect and valid_slot:
            try:
                self._apply_effect_params(force=False)
            except Exception:
                pass
            return True
        try:
            self._cleanup()
        except Exception:
            pass
        try:
            new_effect = int(create_effect())
            ok = bool(apply_reverb_mb(
                int(new_effect),
                float(self.room), float(self.room_hf), float(self.room_lf),
                float(self.decay_time), float(self.decay_hf_ratio),
                float(self.reflections), float(self.reflections_delay),
                float(self.reverb), float(self.reverb_delay),
                float(self.diffusion), float(self.density),
                float(self.hf_reference), float(self.lf_reference),
                float(self.room_rolloff_factor),
            ))
            if not ok:
                try:
                    delete_effect(int(new_effect))
                except Exception:
                    pass
                return False
            new_slot = int(create_aux_slot())
            set_aux_slot_effect(int(new_slot), int(new_effect))
            set_aux_slot_gain(int(new_slot), 1.0)
            self._effect_id = int(new_effect)
            self._slot_id = int(new_slot)
            self._params_sig = self._params_signature()
            self._preset_params_sig = self._params_sig
            return True
        except Exception as e:
            try:
                Logger.error(str("ReverbZone: failed to create effect/slot: ") + str(e))
            except Exception:
                pass
            try:
                self._cleanup()
            except Exception:
                pass
            return False
