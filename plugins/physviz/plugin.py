# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import time
import numpy as np
from core.foundation.plugins import PluginBase
from core.foundation.logger import Logger
from core.gizmo.apiv import Gizmos
from .draw import PhysVizDrawMixin
from .draw import _TAG
try:
    from PyQt6.QtCore import QTimer
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QTimer = None
_CONFIG_VERSION = 2
_BOOL_KEYS = ("enabled", "show_velocity", "show_acceleration", "show_moment", "only_selected", "show_labels", "show_editor", "show_runtime", "show_contacts", "show_joints", "show_colliders")
_FLOAT_KEYS = ("velocity_scale", "acceleration_scale", "moment_scale", "max_length", "min_magnitude", "smooth", "accel_spike", "moment_spike", "contact_normal_length")
class PhysicsVisualisationPlugin(PhysVizDrawMixin, PluginBase):
    NAME = "PhysicsVisualisation"
    VERSION = "1.1.0"
    DESCRIPTION = ""
    SYSTEM = True
    def __init__(self):
        super().__init__()
        self._enabled = True; self._show_velocity = True; self._show_acceleration = True; self._show_moment = True
        self._only_selected = False; self._show_labels = False; self._show_editor = True; self._show_runtime = True
        self._velocity_scale = 0.3; self._acceleration_scale = 0.05; self._moment_scale = 0.05
        self._max_length = 2.5; self._min_magnitude = 0.1; self._smooth = 0.35
        self._accel_spike = 200.0; self._moment_spike = 400.0; self._label_cap = 48
        self._show_contacts = True; self._contact_normal_length = 0.6; self._show_joints = True; self._show_colliders = True
        self._velocity_color = (0.25, 0.95, 0.30, 1.0); self._acceleration_color = (1.0, 0.80, 0.15, 1.0)
        self._moment_color = (1.0, 0.30, 0.75, 1.0); self._contact_new_color = (1.0, 0.90, 0.25, 1.0)
        self._contact_stay_color = (1.0, 0.50, 0.15, 1.0); self._joint_color = (0.20, 1.0, 0.85, 1.0)
        self._collider_color = (0.35, 0.75, 1.0, 1.0); self._trigger_color = (0.70, 0.45, 1.0, 1.0)
        self._prev = {}; self._contact_pairs = set(); self._stashed_contacts = []
        self._hooked_pp = None; self._orig_process = None; self._orig_has = None; self._panel = None; self._timer = None
        self._XO = np.zeros((512, 3), dtype=np.float32); self._XF = np.zeros((512, 3), dtype=np.float32)
        self._xm = np.zeros((512,), dtype=bool); self._xm2 = np.zeros((512,), dtype=bool)
        self._last_draw = 0.0; self._min_interval = 1.0 / 30.0; self._auto_throttle_k = 8e-6
        self._rev_key = None; self._rev_s = None; self._rev_e = None; self._rev_c = None; self._rev_n = 0
        self._vec_scratch = {}; self._cap = 0; self._segcap = 0
        self._O = np.zeros((0, 3), dtype=np.float32); self._V = np.zeros((0, 3), dtype=np.float32)
        self._A = np.zeros((0, 3), dtype=np.float32); self._M = np.zeros((0, 3), dtype=np.float32)
        self._mv = np.zeros((0,), dtype=bool); self._ma = np.zeros((0,), dtype=bool); self._mm = np.zeros((0,), dtype=bool)
        self._S = np.zeros((0, 3), dtype=np.float32); self._E = np.zeros((0, 3), dtype=np.float32); self._C = np.zeros((0, 4), dtype=np.float32)
    @property
    def settings(self):
        return {"enabled": self._enabled, "show_velocity": self._show_velocity, "show_acceleration": self._show_acceleration, "show_moment": self._show_moment, "only_selected": self._only_selected, "show_labels": self._show_labels, "show_editor": self._show_editor, "show_runtime": self._show_runtime, "velocity_scale": self._velocity_scale, "acceleration_scale": self._acceleration_scale, "moment_scale": self._moment_scale, "max_length": self._max_length, "min_magnitude": self._min_magnitude, "smooth": self._smooth, "accel_spike": self._accel_spike, "moment_spike": self._moment_spike, "label_cap": self._label_cap, "show_contacts": self._show_contacts, "contact_normal_length": self._contact_normal_length, "show_joints": self._show_joints, "show_colliders": self._show_colliders}
    def initialize(self, engine):
        super().initialize(engine)
        try:
            ver = int(self.get_config("config_version", 1))
        except Exception:
            ver = 1
        if ver < _CONFIG_VERSION:
            self.set_config("velocity_scale", self._velocity_scale); self.set_config("acceleration_scale", self._acceleration_scale); self.set_config("moment_scale", self._moment_scale)
            self.set_config("max_length", self._max_length); self.set_config("min_magnitude", self._min_magnitude); self.set_config("smooth", self._smooth)
            self.set_config("accel_spike", self._accel_spike); self.set_config("moment_spike", self._moment_spike); self.set_config("label_cap", self._label_cap); self.set_config("config_version", _CONFIG_VERSION)
        for k in _BOOL_KEYS:
            try: setattr(self, "_" + k, bool(self.get_config(k, getattr(self, "_" + k))))
            except Exception: pass
        for k in _FLOAT_KEYS:
            try: setattr(self, "_" + k, float(self.get_config(k, getattr(self, "_" + k))))
            except Exception: pass
        try: self._label_cap = int(self.get_config("label_cap", self._label_cap))
        except Exception: pass
        if _HAS_QT:
            try:
                self.register_dock("Physics Visualisation", self._create_panel, area="right")
            except Exception as e:
                Logger.warning(f"[{self.NAME}] dock registration failed: {e}")
            try:
                self.add_menu_item("Tools", "Physics Visualisation", self._show_panel)
            except Exception as e:
                Logger.warning(f"[{self.NAME}] menu registration failed: {e}")
            try:
                self._timer = QTimer()
                self._timer.timeout.connect(self._on_timer)
                self._timer.setInterval(50)
                self._timer.start()
            except Exception as e:
                Logger.warning(f"[{self.NAME}] timer start failed: {e}")
                self._timer = None
        Logger.info(f"[{self.NAME}] initialized.")
    def shutdown(self):
        try:
            if self._timer is not None: self._timer.stop(); self._timer = None
        except Exception: pass
        self._remove_contact_hook(); self.clear(); super().shutdown()
    def on_scene_loaded(self, scene): self.clear()
    def on_play_start(self): self.clear()
    def on_play_stop(self): self.clear()
    def step(self, dt: float): self._redraw()
    def clear(self):
        try: self._prev.clear()
        except Exception: pass
        try: self._contact_pairs.clear()
        except Exception: pass
        try: self._stashed_contacts.clear()
        except Exception: pass
        self._purge_gizmos(); self._last_draw = 0.0
    def _physics_plugin(self):
        try:
            eng = self._engine
            if eng is None: return None
            pm = getattr(eng, "plugin_manager", None)
            if pm is None: return None
            get = getattr(pm, "get", None)
            if callable(get):
                try: return get("PhysicsPlugin")
                except Exception: pass
            try:
                for p in pm.get_all():
                    if getattr(p, "NAME", "") == "PhysicsPlugin": return p
            except Exception: pass
        except Exception: pass
        return None
    def _want_contacts(self):
        try:
            if not self._enabled or not self._show_contacts: return False
            eng = self._engine
            if eng is None: return False
            return bool(getattr(eng, "play_mode", False))
        except Exception: return False
    def _install_contact_hook(self, pp):
        try:
            if pp is None or getattr(pp, "_viz_hook_installed", False): return
            orig_process = pp._process_collisions; orig_has = pp._has_collision_listeners; plugin = self
            def _wrapped_process(scene, events):
                try: plugin._stash_contact_events(events)
                except Exception: pass
                return orig_process(scene, events)
            def _wrapped_has(scene):
                try:
                    if plugin._want_contacts(): return True
                except Exception: pass
                return orig_has(scene)
            pp._process_collisions = _wrapped_process; pp._has_collision_listeners = _wrapped_has; pp._viz_hook_installed = True
            self._hooked_pp = pp; self._orig_process = orig_process; self._orig_has = orig_has
        except Exception: pass
    def _remove_contact_hook(self):
        try:
            pp = self._hooked_pp
            if pp is not None:
                try:
                    if self._orig_process is not None: pp._process_collisions = self._orig_process
                except Exception: pass
                try:
                    if self._orig_has is not None: pp._has_collision_listeners = self._orig_has
                except Exception: pass
                try: pp._viz_hook_installed = False
                except Exception: pass
        except Exception: pass
        self._hooked_pp = None; self._orig_process = None; self._orig_has = None
    def _contact_tuple(self, pos, nor, imp, ea, eb):
        try: imp = float(imp)
        except Exception: imp = 0.0
        if not math.isfinite(imp): imp = 0.0
        px = py = pz = 0.0; nx = ny = nz = 0.0; has_pos = False
        try:
            px = float(pos[0]); py = float(pos[1]); pz = float(pos[2]); nx = float(nor[0]); ny = float(nor[1]); nz = float(nor[2])
            nl = math.sqrt(nx * nx + ny * ny + nz * nz)
            if nl > 1e-6 and math.isfinite(px + py + pz + nx + ny + nz):
                has_pos = True; nx /= nl; ny /= nl; nz /= nl
        except Exception: has_pos = False
        return ((px, py, pz), (nx, ny, nz), imp, ea, eb, has_pos)
    def _normalize_contact_events(self, raw, b2e):
        out = []
        if not raw: return out
        try: get_map = b2e.get if hasattr(b2e, "get") else (lambda k, d="": d)
        except Exception: return out
        for ev in raw:
            try:
                if not isinstance(ev, dict): continue
                pts = ev.get("points", None)
                if pts:
                    ba = ev.get("body_a", -1); bb = ev.get("body_b", -1)
                    try: ea = get_map(ba, "")
                    except Exception: ea = ""
                    try: eb = get_map(bb, "")
                    except Exception: eb = ""
                    for p in pts:
                        try:
                            if not isinstance(p, dict): continue
                            imp = p.get("impulse", p.get("force", ev.get("force", 0.0)))
                            out.append(self._contact_tuple(p.get("position"), p.get("normal"), imp, ea, eb))
                        except Exception: continue
                else:
                    try: ea = ev.get("entity_a", "") or get_map(ev.get("body_a", -1), "")
                    except Exception: ea = ""
                    try: eb = ev.get("entity_b", "") or get_map(ev.get("body_b", -1), "")
                    except Exception: eb = ""
                    out.append(self._contact_tuple(ev.get("position"), ev.get("normal"), ev.get("force", 0.0), ea, eb))
            except Exception: continue
            if len(out) >= 512: break
        return out
    def _stash_contact_events(self, events):
        try:
            items = self._normalize_contact_events(events, {})
            if items: self._stashed_contacts.extend(items); self._stashed_contacts = self._stashed_contacts[-512:] if len(self._stashed_contacts) > 512 else self._stashed_contacts
        except Exception: pass
    def _read_single_contacts(self, pp):
        try:
            scene = getattr(pp, "physics_scene", None)
            if scene is None: return []
            get = getattr(scene, "get_collision_events", None)
            if not callable(get): return []
            raw = get(); b2e = getattr(scene, "_body_to_entity", {})
            return self._normalize_contact_events(raw, b2e if b2e is not None else {})
        except Exception: return []
    def _purge_gizmos(self):
        try: Gizmos.clear_tag(_TAG)
        except Exception: pass
        try:
            import core.gizmo.api as _api
            inst = _api._gizmos_instance
            if inst is not None:
                with inst._lock: inst._flat_size = 0; inst._revision += 1
        except Exception: pass
    def configure(self, patch):
        try: items = list(dict(patch).items())
        except Exception: return
        for k, v in items:
            try: self._apply_setting(k, v)
            except Exception: continue
    def _apply_setting(self, key, value):
        if key == "enabled":
            v = bool(value)
            self._enabled = v
            self.set_config("enabled", v)
            if v: self._last_draw = 0.0
            else: self._purge_gizmos()
            return
        if key in ("show_velocity", "show_acceleration", "show_moment", "only_selected", "show_labels", "show_editor", "show_runtime", "show_contacts", "show_joints", "show_colliders"):
            v = bool(value)
            setattr(self, "_" + key, v)
            self.set_config(key, v)
            return
        if key in ("velocity_scale", "acceleration_scale", "moment_scale"):
            v = max(0.001, float(value))
            setattr(self, "_" + key, v)
            self.set_config(key, v)
            return
        if key == "max_length":
            self._max_length = max(0.1, float(value))
            self.set_config("max_length", self._max_length)
        elif key == "min_magnitude":
            self._min_magnitude = max(0.0, float(value))
            self.set_config("min_magnitude", self._min_magnitude)
        elif key == "smooth":
            self._smooth = min(0.98, max(0.02, float(value)))
            self.set_config("smooth", self._smooth)
        elif key in ("accel_spike", "moment_spike"):
            v = max(1.0, float(value))
            setattr(self, "_" + key, v)
            self.set_config(key, v)
        elif key == "label_cap":
            self._label_cap = max(0, int(value))
            self.set_config("label_cap", self._label_cap)
        elif key == "contact_normal_length":
            self._contact_normal_length = min(3.0, max(0.05, float(value)))
            self.set_config("contact_normal_length", self._contact_normal_length)
    def _on_timer(self):
        try:
            eng = self._engine
            playing = bool(eng.play_mode) if eng is not None else False
        except Exception: playing = False
        if playing: return
        self._redraw()
    def _create_panel(self):
        if self._panel is not None: return self._panel
        try:
            from .panel import _PhysicsVisualisationPanel as _P
            self._panel = _P(self)
        except Exception as e: Logger.error(f"[{self.NAME}] panel init failed: {e}", e); self._panel = None
        return self._panel
    def _show_panel(self):
        w = self._panel
        if w is None: w = self._create_panel()
        if w is None: return
        try:
            dock = w.parent()
            if dock is not None: dock.show(); dock.raise_(); dock.setFocus()
            else: w.show(); w.raise_()
        except Exception: pass
    def _selected_ids(self, eng):
        try: vp = eng.viewport
        except Exception: return set()
        if vp is None: return set()
        try: sel = getattr(vp, "_selected_entities", None)
        except Exception: return set()
        if not sel: return set()
        out = set()
        for e in sel:
            try: out.add(e.id)
            except Exception: continue
        return out
    def _ensure_cap(self, n):
        if n <= self._cap: return
        cap = self._cap if self._cap > 0 else 256
        while cap < n: cap = int(cap * 1.5) + 64
        self._O = np.zeros((cap, 3), dtype=np.float32); self._V = np.zeros((cap, 3), dtype=np.float32)
        self._A = np.zeros((cap, 3), dtype=np.float32); self._M = np.zeros((cap, 3), dtype=np.float32)
        self._mv = np.zeros((cap,), dtype=bool); self._ma = np.zeros((cap,), dtype=bool); self._mm = np.zeros((cap,), dtype=bool)
        self._cap = cap
    def _ensure_segcap(self, n):
        if n <= self._segcap: return
        cap = self._segcap if self._segcap > 0 else 768
        while cap < n: cap = int(cap * 1.5) + 256
        self._S = np.zeros((cap, 3), dtype=np.float32); self._E = np.zeros((cap, 3), dtype=np.float32); self._C = np.zeros((cap, 4), dtype=np.float32)
        self._segcap = cap
    def _redraw(self):
        if not self._enabled: return
        eng = self._engine
        if eng is None: return
        try: scene = eng.scene
        except Exception: return
        if scene is None: return
        try: playing = bool(eng.play_mode)
        except Exception: playing = False
        if playing and not self._show_runtime: self._purge_gizmos(); return
        if not playing and not self._show_editor: self._purge_gizmos(); return
        if not self._show_velocity and not self._show_acceleration and not self._show_moment: self._purge_gizmos(); return
        now = time.perf_counter()
        if now - self._last_draw < self._min_interval: return
        self._last_draw = now
        try: entities = scene.get_all_entities()
        except Exception: return
        try: Gizmos.clear_tag(_TAG)
        except Exception: pass
        selected = None
        if self._only_selected:
            selected = self._selected_ids(eng)
            if not selected:
                self._purge_gizmos()
                return
        self._collect_and_submit(entities, selected, now, scene, playing)
    def _read_body(self, tr, rb, is_2d):
        try:
            p = tr.position; ox = float(p.x); oy = float(p.y); oz = float(p.z)
        except Exception: return None
        try:
            if is_2d:
                v = rb.velocity; vx = float(v.x); vy = float(v.y); vz = 0.0; wx = 0.0; wy = 0.0; wz = float(rb.angular_velocity)
            else:
                v = rb.velocity; vx = float(v.x); vy = float(v.y); vz = float(v.z); w = rb.angular_velocity; wx = float(w.x); wy = float(w.y); wz = float(w.z)
            mass = float(rb.mass)
        except Exception: return None
        if not math.isfinite(ox + oy + oz + vx + vy + vz + wx + wy + wz + mass): return None
        if mass <= 0.0: mass = 1.0
        return (ox, oy, oz, vx, vy, vz, wx, wy, wz, mass)
    def _collect_and_submit(self, entities, selected, now, scene, playing):
        try: total_hint = len(entities)
        except Exception: total_hint = 256
        self._ensure_cap(max(256, total_hint))
        O = self._O; V = self._V; A = self._A; M = self._M; mv = self._mv; ma = self._ma; mm = self._mm
        prev = self._prev; alpha = self._smooth; min_mag = self._min_magnitude; acc_spike = self._accel_spike; mom_spike = self._moment_spike
        show_v = self._show_velocity; show_a = self._show_acceleration; show_m = self._show_moment
        k = 0; labels = []; lab_cap = self._label_cap if self._show_labels else 0
        for entity in entities:
            try:
                if not getattr(entity, "_active", True): continue
                eid = entity.id
                if selected is not None and eid not in selected: continue
                comps = getattr(entity, "_components", None)
                if not comps: continue
                tr = comps.get("Transform", None)
                if tr is None: continue
                rb = comps.get("Rigidbody", None); is_2d = False
                if rb is not None and getattr(rb, "enabled", True): pass
                else:
                    rb = comps.get("Rigidbody2D", None)
                    if rb is None or not getattr(rb, "enabled", True): continue
                    is_2d = True
                rd = self._read_body(tr, rb, is_2d)
                if rd is None: continue
                ox, oy, oz, vx, vy, vz, wx, wy, wz, mass = rd
                st = prev.get(eid, None)
                if st is None:
                    st = [vx, vy, vz, wx, wy, wz, now]; prev[eid] = st; svx, svy, svz = vx, vy, vz; acc_ok = False; mom_ok = False
                else:
                    try: dt = now - st[6]
                    except Exception: dt = 0.0
                    if dt < 1e-4 or dt > 1.0:
                        st[0] = vx
                        st[1] = vy
                        st[2] = vz
                        st[3] = wx
                        st[4] = wy
                        st[5] = wz
                        st[6] = now
                        svx, svy, svz = vx, vy, vz
                        acc_ok = False
                        mom_ok = False
                    else:
                        psvx, psvy, psvz = st[0], st[1], st[2]; pswx, pswy, pswz = st[3], st[4], st[5]
                        svx = psvx + alpha * (vx - psvx); svy = psvy + alpha * (vy - psvy); svz = psvz + alpha * (vz - psvz)
                        sswx = pswx + alpha * (wx - pswx); sswy = pswy + alpha * (wy - pswy); sswz = pswz + alpha * (wz - pswz)
                        ax = (svx - psvx) / dt; ay = (svy - psvy) / dt; az = (svz - psvz) / dt
                        alx = (sswx - pswx) / dt; aly = (sswy - pswy) / dt; alz = (sswz - pswz) / dt
                        amag = math.sqrt(ax * ax + ay * ay + az * az); mx = alx * mass; my = aly * mass; mz = alz * mass
                        mmag = math.sqrt(mx * mx + my * my + mz * mz)
                        acc_ok = show_a and amag > min_mag and amag <= acc_spike; mom_ok = show_m and mmag > min_mag and mmag <= mom_spike
                        st[0] = svx; st[1] = svy; st[2] = svz; st[3] = sswx; st[4] = sswy; st[5] = sswz; st[6] = now
                        if acc_ok: A[k, 0] = ax; A[k, 1] = ay; A[k, 2] = az
                        if mom_ok: M[k, 0] = mx; M[k, 1] = my; M[k, 2] = mz
                vmag = math.sqrt(svx * svx + svy * svy + svz * svz); vel_ok = show_v and vmag > min_mag
                if not vel_ok and not acc_ok and not mom_ok: continue
                O[k, 0] = ox; O[k, 1] = oy; O[k, 2] = oz; V[k, 0] = svx; V[k, 1] = svy; V[k, 2] = svz
                mv[k] = vel_ok; ma[k] = acc_ok; mm[k] = mom_ok
                if lab_cap > 0 and len(labels) < lab_cap and vel_ok:
                    sx = svx * self._velocity_scale; sy = svy * self._velocity_scale; sz = svz * self._velocity_scale
                    try: ll = math.sqrt(sx * sx + sy * sy + sz * sz)
                    except Exception: ll = 0.0
                    if ll > self._max_length and ll > 1e-12: kk = self._max_length / ll; sx *= kk; sy *= kk; sz *= kk
                    labels.append((ox + sx, oy + sy, oz + sz, f"{vmag:.2f}", self._velocity_color))
                k += 1
                if k >= self._cap: break
            except Exception: continue
        try:
            if len(prev) > 4096: prev.clear()
        except Exception: pass
        off = 0
        if show_v and k > 0: off = self._emit(O, V, mv, k, self._velocity_scale, self._velocity_color, off)
        if show_a and k > 0: off = self._emit(O, A, ma, k, self._acceleration_scale, self._acceleration_color, off)
        if show_m and k > 0: off = self._emit(O, M, mm, k, self._moment_scale, self._moment_color, off)
        off = self._collect_contacts(scene, selected, playing, labels, lab_cap, off)
        off = self._collect_extras(entities, selected, scene, labels, lab_cap, off)
        if off > 0:
            try: s = np.ascontiguousarray(self._S[:off]); e = np.ascontiguousarray(self._E[:off]); c = np.ascontiguousarray(self._C[:off])
            except Exception: self._purge_gizmos(); return
            self._flat_submit(s, e, c)
        else: self._purge_gizmos()
        if labels: self._submit_labels(labels)
    def _collect_contacts(self, scene, selected, playing, labels, lab_cap, off):
        return super()._collect_contacts(scene, selected, playing, labels, lab_cap, off)
    def _collect_extras(self, entities, selected, scene, labels, lab_cap, off):
        return super()._collect_extras(entities, selected, scene, labels, lab_cap, off)
def get_plugin():
    return PhysicsVisualisationPlugin()
