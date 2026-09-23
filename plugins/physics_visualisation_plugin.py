from __future__ import annotations
import math
import time
import numpy as np
from core.foundation.plugin_manager import PluginBase
from core.foundation.logger import Logger
from core.gizmo.api import Gizmos
try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget
    _HAS_QT = True
except Exception:
    _HAS_QT = False
_TAG = "physics_visualisation"
_CONFIG_VERSION = 2
_BOX_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
_REF_X = np.array([1.0, 0.0, 0.0], dtype=np.float32)
_REF_Y = np.array([0.0, 1.0, 0.0], dtype=np.float32)


class PhysicsVisualisationPlugin(PluginBase):
    NAME = "PhysicsVisualisation"
    VERSION = "1.1.0"
    DESCRIPTION = ""
    SYSTEM = True

    def __init__(self):
        super().__init__()
        self._enabled = True
        self._show_velocity = True
        self._show_acceleration = True
        self._show_moment = True
        self._only_selected = False
        self._show_labels = False
        self._show_editor = True
        self._show_runtime = True
        self._velocity_scale = 0.3
        self._acceleration_scale = 0.05
        self._moment_scale = 0.05
        self._max_length = 2.5
        self._min_magnitude = 0.1
        self._smooth = 0.35
        self._accel_spike = 200.0
        self._moment_spike = 400.0
        self._label_cap = 48
        self._show_contacts = True
        self._contact_normal_length = 0.6
        self._show_joints = True
        self._show_colliders = True
        self._velocity_color = (0.25, 0.95, 0.30, 1.0)
        self._acceleration_color = (1.0, 0.80, 0.15, 1.0)
        self._moment_color = (1.0, 0.30, 0.75, 1.0)
        self._contact_new_color = (1.0, 0.90, 0.25, 1.0)
        self._contact_stay_color = (1.0, 0.50, 0.15, 1.0)
        self._joint_color = (0.20, 1.0, 0.85, 1.0)
        self._collider_color = (0.35, 0.75, 1.0, 1.0)
        self._trigger_color = (0.70, 0.45, 1.0, 1.0)
        self._prev = {}
        self._contact_pairs = set()
        self._stashed_contacts = []
        self._hooked_pp = None
        self._orig_process = None
        self._orig_has = None
        self._panel = None
        self._timer = None
        self._XO = np.zeros((512, 3), dtype=np.float32)
        self._XF = np.zeros((512, 3), dtype=np.float32)
        self._xm = np.zeros((512,), dtype=bool)
        self._xm2 = np.zeros((512,), dtype=bool)
        self._last_draw = 0.0
        self._min_interval = 1.0 / 30.0
        self._cap = 0
        self._segcap = 0
        self._O = np.zeros((0, 3), dtype=np.float32)
        self._V = np.zeros((0, 3), dtype=np.float32)
        self._A = np.zeros((0, 3), dtype=np.float32)
        self._M = np.zeros((0, 3), dtype=np.float32)
        self._mv = np.zeros((0,), dtype=bool)
        self._ma = np.zeros((0,), dtype=bool)
        self._mm = np.zeros((0,), dtype=bool)
        self._S = np.zeros((0, 3), dtype=np.float32)
        self._E = np.zeros((0, 3), dtype=np.float32)
        self._C = np.zeros((0, 4), dtype=np.float32)

    @property
    def settings(self):
        return {
            "enabled": self._enabled,
            "show_velocity": self._show_velocity,
            "show_acceleration": self._show_acceleration,
            "show_moment": self._show_moment,
            "only_selected": self._only_selected,
            "show_labels": self._show_labels,
            "show_editor": self._show_editor,
            "show_runtime": self._show_runtime,
            "velocity_scale": self._velocity_scale,
            "acceleration_scale": self._acceleration_scale,
            "moment_scale": self._moment_scale,
            "max_length": self._max_length,
            "min_magnitude": self._min_magnitude,
            "smooth": self._smooth,
            "accel_spike": self._accel_spike,
            "moment_spike": self._moment_spike,
            "label_cap": self._label_cap,
            "show_contacts": self._show_contacts,
            "contact_normal_length": self._contact_normal_length,
            "show_joints": self._show_joints,
            "show_colliders": self._show_colliders,
        }

    def initialize(self, engine):
        super().initialize(engine)
        try:
            ver = int(self.get_config("config_version", 1))
        except Exception:
            ver = 1
        if ver < _CONFIG_VERSION:
            self.set_config("velocity_scale", self._velocity_scale)
            self.set_config("acceleration_scale", self._acceleration_scale)
            self.set_config("moment_scale", self._moment_scale)
            self.set_config("max_length", self._max_length)
            self.set_config("min_magnitude", self._min_magnitude)
            self.set_config("smooth", self._smooth)
            self.set_config("accel_spike", self._accel_spike)
            self.set_config("moment_spike", self._moment_spike)
            self.set_config("label_cap", self._label_cap)
            self.set_config("config_version", _CONFIG_VERSION)
        self._enabled = bool(self.get_config("enabled", self._enabled))
        self._show_velocity = bool(self.get_config("show_velocity", self._show_velocity))
        self._show_acceleration = bool(self.get_config("show_acceleration", self._show_acceleration))
        self._show_moment = bool(self.get_config("show_moment", self._show_moment))
        self._only_selected = bool(self.get_config("only_selected", self._only_selected))
        self._show_labels = bool(self.get_config("show_labels", self._show_labels))
        self._show_editor = bool(self.get_config("show_editor", self._show_editor))
        self._show_runtime = bool(self.get_config("show_runtime", self._show_runtime))
        self._velocity_scale = float(self.get_config("velocity_scale", self._velocity_scale))
        self._acceleration_scale = float(self.get_config("acceleration_scale", self._acceleration_scale))
        self._moment_scale = float(self.get_config("moment_scale", self._moment_scale))
        self._max_length = float(self.get_config("max_length", self._max_length))
        self._min_magnitude = float(self.get_config("min_magnitude", self._min_magnitude))
        self._smooth = float(self.get_config("smooth", self._smooth))
        self._accel_spike = float(self.get_config("accel_spike", self._accel_spike))
        self._moment_spike = float(self.get_config("moment_spike", self._moment_spike))
        self._show_contacts = bool(self.get_config("show_contacts", self._show_contacts))
        self._contact_normal_length = float(self.get_config("contact_normal_length", self._contact_normal_length))
        self._show_joints = bool(self.get_config("show_joints", self._show_joints))
        self._show_colliders = bool(self.get_config("show_colliders", self._show_colliders))
        try:
            self._label_cap = int(self.get_config("label_cap", self._label_cap))
        except Exception:
            pass
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
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
        except Exception:
            pass
        self._remove_contact_hook()
        self.clear()
        super().shutdown()

    def on_scene_loaded(self, scene):
        self.clear()

    def on_play_start(self):
        self.clear()

    def on_play_stop(self):
        self.clear()

    def step(self, dt: float):
        self._redraw()

    def clear(self):
        try:
            self._prev.clear()
        except Exception:
            pass
        try:
            self._contact_pairs.clear()
        except Exception:
            pass
        try:
            self._stashed_contacts.clear()
        except Exception:
            pass
        self._purge_gizmos()
        self._last_draw = 0.0

    def _physics_plugin(self):
        try:
            eng = self._engine
            if eng is None:
                return None
            pm = getattr(eng, "plugin_manager", None)
            if pm is None:
                return None
            get = getattr(pm, "get", None)
            if callable(get):
                try:
                    return get("PhysicsPlugin")
                except Exception:
                    pass
            try:
                for p in pm.get_all():
                    if getattr(p, "NAME", "") == "PhysicsPlugin":
                        return p
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _want_contacts(self):
        try:
            if not self._enabled or not self._show_contacts:
                return False
            eng = self._engine
            if eng is None:
                return False
            return bool(getattr(eng, "play_mode", False))
        except Exception:
            return False

    def _install_contact_hook(self, pp):
        try:
            if pp is None or getattr(pp, "_viz_hook_installed", False):
                return
            orig_process = pp._process_collisions
            orig_has = pp._has_collision_listeners
            plugin = self

            def _wrapped_process(scene, events):
                try:
                    plugin._stash_contact_events(events)
                except Exception:
                    pass
                return orig_process(scene, events)

            def _wrapped_has(scene):
                try:
                    if plugin._want_contacts():
                        return True
                except Exception:
                    pass
                return orig_has(scene)

            pp._process_collisions = _wrapped_process
            pp._has_collision_listeners = _wrapped_has
            pp._viz_hook_installed = True
            self._hooked_pp = pp
            self._orig_process = orig_process
            self._orig_has = orig_has
        except Exception:
            pass

    def _remove_contact_hook(self):
        try:
            pp = self._hooked_pp
            if pp is not None:
                try:
                    if self._orig_process is not None:
                        pp._process_collisions = self._orig_process
                except Exception:
                    pass
                try:
                    if self._orig_has is not None:
                        pp._has_collision_listeners = self._orig_has
                except Exception:
                    pass
                try:
                    pp._viz_hook_installed = False
                except Exception:
                    pass
        except Exception:
            pass
        self._hooked_pp = None
        self._orig_process = None
        self._orig_has = None

    def _contact_tuple(self, pos, nor, imp, ea, eb):
        try:
            imp = float(imp)
        except Exception:
            imp = 0.0
        if not math.isfinite(imp):
            imp = 0.0
        px = py = pz = 0.0
        nx = ny = nz = 0.0
        has_pos = False
        try:
            px = float(pos[0])
            py = float(pos[1])
            pz = float(pos[2])
            nx = float(nor[0])
            ny = float(nor[1])
            nz = float(nor[2])
            nl = math.sqrt(nx * nx + ny * ny + nz * nz)
            if nl > 1e-6 and math.isfinite(px + py + pz + nx + ny + nz):
                has_pos = True
                nx /= nl
                ny /= nl
                nz /= nl
        except Exception:
            has_pos = False
        return ((px, py, pz), (nx, ny, nz), imp, ea, eb, has_pos)

    def _normalize_contact_events(self, raw, b2e):
        out = []
        if not raw:
            return out
        try:
            get_map = b2e.get if hasattr(b2e, "get") else (lambda k, d="": d)
        except Exception:
            return out
        for ev in raw:
            try:
                if not isinstance(ev, dict):
                    continue
                pts = ev.get("points", None)
                if pts:
                    ba = ev.get("body_a", -1)
                    bb = ev.get("body_b", -1)
                    try:
                        ea = get_map(ba, "")
                    except Exception:
                        ea = ""
                    try:
                        eb = get_map(bb, "")
                    except Exception:
                        eb = ""
                    for p in pts:
                        try:
                            if not isinstance(p, dict):
                                continue
                            imp = p.get("impulse", p.get("force", ev.get("force", 0.0)))
                            out.append(self._contact_tuple(p.get("position"), p.get("normal"), imp, ea, eb))
                        except Exception:
                            continue
                else:
                    try:
                        ea = ev.get("entity_a", "") or get_map(ev.get("body_a", -1), "")
                    except Exception:
                        ea = ""
                    try:
                        eb = ev.get("entity_b", "") or get_map(ev.get("body_b", -1), "")
                    except Exception:
                        eb = ""
                    out.append(self._contact_tuple(ev.get("position"), ev.get("normal"), ev.get("force", 0.0), ea, eb))
            except Exception:
                continue
            if len(out) >= 512:
                break
        return out

    def _stash_contact_events(self, events):
        try:
            items = self._normalize_contact_events(events, {})
            if items:
                self._stashed_contacts.extend(items)
                if len(self._stashed_contacts) > 512:
                    self._stashed_contacts = self._stashed_contacts[-512:]
        except Exception:
            pass

    def _read_single_contacts(self, pp):
        try:
            scene = getattr(pp, "physics_scene", None)
            if scene is None:
                return []
            get = getattr(scene, "get_collision_events", None)
            if not callable(get):
                return []
            raw = get()
            b2e = getattr(scene, "_body_to_entity", {})
            return self._normalize_contact_events(raw, b2e if b2e is not None else {})
        except Exception:
            return []

    def _purge_gizmos(self):
        try:
            Gizmos.clear_tag(_TAG)
        except Exception:
            pass
        try:
            import core.gizmo.api as _api
            inst = _api._gizmos_instance
            if inst is not None:
                with inst._lock:
                    inst._flat_size = 0
                    inst._revision += 1
        except Exception:
            pass

    def configure(self, patch):
        try:
            items = list(dict(patch).items())
        except Exception:
            return
        for k, v in items:
            try:
                self._apply_setting(k, v)
            except Exception:
                continue

    def _apply_setting(self, key, value):
        if key == "enabled":
            self._enabled = bool(value)
            self.set_config("enabled", bool(value))
            if bool(value):
                self._last_draw = 0.0
            else:
                self._purge_gizmos()
        elif key == "show_velocity":
            self._show_velocity = bool(value)
            self.set_config("show_velocity", bool(value))
        elif key == "show_acceleration":
            self._show_acceleration = bool(value)
            self.set_config("show_acceleration", bool(value))
        elif key == "show_moment":
            self._show_moment = bool(value)
            self.set_config("show_moment", bool(value))
        elif key == "only_selected":
            self._only_selected = bool(value)
            self.set_config("only_selected", bool(value))
        elif key == "show_labels":
            self._show_labels = bool(value)
            self.set_config("show_labels", bool(value))
        elif key == "show_editor":
            self._show_editor = bool(value)
            self.set_config("show_editor", bool(value))
        elif key == "show_runtime":
            self._show_runtime = bool(value)
            self.set_config("show_runtime", bool(value))
        elif key == "velocity_scale":
            self._velocity_scale = max(0.001, float(value))
            self.set_config("velocity_scale", self._velocity_scale)
        elif key == "acceleration_scale":
            self._acceleration_scale = max(0.001, float(value))
            self.set_config("acceleration_scale", self._acceleration_scale)
        elif key == "moment_scale":
            self._moment_scale = max(0.001, float(value))
            self.set_config("moment_scale", self._moment_scale)
        elif key == "max_length":
            self._max_length = max(0.1, float(value))
            self.set_config("max_length", self._max_length)
        elif key == "min_magnitude":
            self._min_magnitude = max(0.0, float(value))
            self.set_config("min_magnitude", self._min_magnitude)
        elif key == "smooth":
            self._smooth = min(0.98, max(0.02, float(value)))
            self.set_config("smooth", self._smooth)
        elif key == "accel_spike":
            self._accel_spike = max(1.0, float(value))
            self.set_config("accel_spike", self._accel_spike)
        elif key == "moment_spike":
            self._moment_spike = max(1.0, float(value))
            self.set_config("moment_spike", self._moment_spike)
        elif key == "label_cap":
            self._label_cap = max(0, int(value))
            self.set_config("label_cap", self._label_cap)
        elif key == "show_contacts":
            self._show_contacts = bool(value)
            self.set_config("show_contacts", bool(value))
        elif key == "contact_normal_length":
            self._contact_normal_length = min(3.0, max(0.05, float(value)))
            self.set_config("contact_normal_length", self._contact_normal_length)
        elif key == "show_joints":
            self._show_joints = bool(value)
            self.set_config("show_joints", bool(value))
        elif key == "show_colliders":
            self._show_colliders = bool(value)
            self.set_config("show_colliders", bool(value))

    def _on_timer(self):
        try:
            eng = self._engine
            playing = bool(eng.play_mode) if eng is not None else False
        except Exception:
            playing = False
        if playing:
            return
        self._redraw()

    def _create_panel(self):
        if self._panel is not None:
            return self._panel
        try:
            self._panel = _PhysicsVisualisationPanel(self)
        except Exception as e:
            Logger.error(f"[{self.NAME}] panel init failed: {e}", e)
            self._panel = None
        return self._panel

    def _show_panel(self):
        w = self._panel
        if w is None:
            w = self._create_panel()
        if w is None:
            return
        try:
            dock = w.parent()
            if dock is not None:
                dock.show()
                dock.raise_()
                dock.setFocus()
            else:
                w.show()
                w.raise_()
        except Exception:
            pass

    def _selected_ids(self, eng):
        try:
            vp = eng.viewport
        except Exception:
            return set()
        if vp is None:
            return set()
        try:
            sel = getattr(vp, "_selected_entities", None)
        except Exception:
            return set()
        if not sel:
            return set()
        out = set()
        for e in sel:
            try:
                out.add(e.id)
            except Exception:
                continue
        return out

    def _ensure_cap(self, n):
        if n <= self._cap:
            return
        cap = self._cap if self._cap > 0 else 256
        while cap < n:
            cap = int(cap * 1.5) + 64
        self._O = np.zeros((cap, 3), dtype=np.float32)
        self._V = np.zeros((cap, 3), dtype=np.float32)
        self._A = np.zeros((cap, 3), dtype=np.float32)
        self._M = np.zeros((cap, 3), dtype=np.float32)
        self._mv = np.zeros((cap,), dtype=bool)
        self._ma = np.zeros((cap,), dtype=bool)
        self._mm = np.zeros((cap,), dtype=bool)
        self._cap = cap

    def _ensure_segcap(self, n):
        if n <= self._segcap:
            return
        cap = self._segcap if self._segcap > 0 else 768
        while cap < n:
            cap = int(cap * 1.5) + 256
        self._S = np.zeros((cap, 3), dtype=np.float32)
        self._E = np.zeros((cap, 3), dtype=np.float32)
        self._C = np.zeros((cap, 4), dtype=np.float32)
        self._segcap = cap

    def _redraw(self):
        if not self._enabled:
            return
        eng = self._engine
        if eng is None:
            return
        try:
            scene = eng.scene
        except Exception:
            return
        if scene is None:
            return
        try:
            playing = bool(eng.play_mode)
        except Exception:
            playing = False
        if playing and not self._show_runtime:
            self._purge_gizmos()
            return
        if not playing and not self._show_editor:
            self._purge_gizmos()
            return
        if not self._show_velocity and not self._show_acceleration and not self._show_moment:
            self._purge_gizmos()
            return
        now = time.perf_counter()
        if now - self._last_draw < self._min_interval:
            return
        self._last_draw = now
        try:
            entities = scene.get_all_entities()
        except Exception:
            return
        try:
            Gizmos.clear_tag(_TAG)
        except Exception:
            pass
        selected = None
        if self._only_selected:
            selected = self._selected_ids(eng)
            if not selected:
                self._purge_gizmos()
                return
        self._collect_and_submit(entities, selected, now, scene, playing)

    def _read_body(self, tr, rb, is_2d):
        try:
            p = tr.position
            ox = float(p.x)
            oy = float(p.y)
            oz = float(p.z)
        except Exception:
            return None
        try:
            if is_2d:
                v = rb.velocity
                vx = float(v.x)
                vy = float(v.y)
                vz = 0.0
                wx = 0.0
                wy = 0.0
                wz = float(rb.angular_velocity)
            else:
                v = rb.velocity
                vx = float(v.x)
                vy = float(v.y)
                vz = float(v.z)
                w = rb.angular_velocity
                wx = float(w.x)
                wy = float(w.y)
                wz = float(w.z)
            mass = float(rb.mass)
        except Exception:
            return None
        if not math.isfinite(ox + oy + oz + vx + vy + vz + wx + wy + wz + mass):
            return None
        if mass <= 0.0:
            mass = 1.0
        return (ox, oy, oz, vx, vy, vz, wx, wy, wz, mass)

    def _collect_and_submit(self, entities, selected, now, scene, playing):
        try:
            total_hint = len(entities)
        except Exception:
            total_hint = 256
        self._ensure_cap(max(256, total_hint))
        O = self._O
        V = self._V
        A = self._A
        M = self._M
        mv = self._mv
        ma = self._ma
        mm = self._mm
        prev = self._prev
        alpha = self._smooth
        min_mag = self._min_magnitude
        acc_spike = self._accel_spike
        mom_spike = self._moment_spike
        show_v = self._show_velocity
        show_a = self._show_acceleration
        show_m = self._show_moment
        k = 0
        labels = []
        lab_cap = self._label_cap if self._show_labels else 0
        for entity in entities:
            try:
                if not getattr(entity, "_active", True):
                    continue
                eid = entity.id
                if selected is not None and eid not in selected:
                    continue
                comps = getattr(entity, "_components", None)
                if not comps:
                    continue
                tr = comps.get("Transform", None)
                if tr is None:
                    continue
                rb = comps.get("Rigidbody", None)
                is_2d = False
                if rb is not None and getattr(rb, "enabled", True):
                    pass
                else:
                    rb = comps.get("Rigidbody2D", None)
                    if rb is None or not getattr(rb, "enabled", True):
                        continue
                    is_2d = True
                rd = self._read_body(tr, rb, is_2d)
                if rd is None:
                    continue
                ox, oy, oz, vx, vy, vz, wx, wy, wz, mass = rd
                st = prev.get(eid, None)
                if st is None:
                    st = [vx, vy, vz, wx, wy, wz, now]
                    prev[eid] = st
                    svx, svy, svz = vx, vy, vz
                    acc_ok = False
                    mom_ok = False
                else:
                    try:
                        dt = now - st[6]
                    except Exception:
                        dt = 0.0
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
                        psvx, psvy, psvz = st[0], st[1], st[2]
                        pswx, pswy, pswz = st[3], st[4], st[5]
                        svx = psvx + alpha * (vx - psvx)
                        svy = psvy + alpha * (vy - psvy)
                        svz = psvz + alpha * (vz - psvz)
                        sswx = pswx + alpha * (wx - pswx)
                        sswy = pswy + alpha * (wy - pswy)
                        sswz = pswz + alpha * (wz - pswz)
                        ax = (svx - psvx) / dt
                        ay = (svy - psvy) / dt
                        az = (svz - psvz) / dt
                        alx = (sswx - pswx) / dt
                        aly = (sswy - pswy) / dt
                        alz = (sswz - pswz) / dt
                        amag = math.sqrt(ax * ax + ay * ay + az * az)
                        mx = alx * mass
                        my = aly * mass
                        mz = alz * mass
                        mmag = math.sqrt(mx * mx + my * my + mz * mz)
                        acc_ok = show_a and amag > min_mag and amag <= acc_spike
                        mom_ok = show_m and mmag > min_mag and mmag <= mom_spike
                        st[0] = svx
                        st[1] = svy
                        st[2] = svz
                        st[3] = sswx
                        st[4] = sswy
                        st[5] = sswz
                        st[6] = now
                        if acc_ok:
                            A[k, 0] = ax
                            A[k, 1] = ay
                            A[k, 2] = az
                        if mom_ok:
                            M[k, 0] = mx
                            M[k, 1] = my
                            M[k, 2] = mz
                vmag = math.sqrt(svx * svx + svy * svy + svz * svz)
                vel_ok = show_v and vmag > min_mag
                if not vel_ok and not acc_ok and not mom_ok:
                    continue
                O[k, 0] = ox
                O[k, 1] = oy
                O[k, 2] = oz
                V[k, 0] = svx
                V[k, 1] = svy
                V[k, 2] = svz
                mv[k] = vel_ok
                ma[k] = acc_ok
                mm[k] = mom_ok
                if lab_cap > 0 and len(labels) < lab_cap and vel_ok:
                    sx = svx * self._velocity_scale
                    sy = svy * self._velocity_scale
                    sz = svz * self._velocity_scale
                    try:
                        ll = math.sqrt(sx * sx + sy * sy + sz * sz)
                    except Exception:
                        ll = 0.0
                    if ll > self._max_length and ll > 1e-12:
                        kk = self._max_length / ll
                        sx *= kk
                        sy *= kk
                        sz *= kk
                    labels.append((ox + sx, oy + sy, oz + sz, f"{vmag:.2f}", self._velocity_color))
                k += 1
                if k >= self._cap:
                    break
            except Exception:
                continue
        try:
            if len(prev) > 4096:
                prev.clear()
        except Exception:
            pass
        off = 0
        if show_v and k > 0:
            off = self._emit(O, V, mv, k, self._velocity_scale, self._velocity_color, off)
        if show_a and k > 0:
            off = self._emit(O, A, ma, k, self._acceleration_scale, self._acceleration_color, off)
        if show_m and k > 0:
            off = self._emit(O, M, mm, k, self._moment_scale, self._moment_color, off)
        off = self._collect_contacts(scene, selected, playing, labels, lab_cap, off)
        off = self._collect_extras(entities, selected, scene, labels, lab_cap, off)
        if off > 0:
            try:
                s = np.ascontiguousarray(self._S[:off])
                e = np.ascontiguousarray(self._E[:off])
                c = np.ascontiguousarray(self._C[:off])
            except Exception:
                self._purge_gizmos()
                return
            self._flat_submit(s, e, c)
        else:
            self._purge_gizmos()
        if labels:
            self._submit_labels(labels)

    def _entity_center(self, scene, eid):
        if not eid:
            return None
        try:
            ent = scene.get_entity(eid)
        except Exception:
            return None
        if ent is None:
            return None
        try:
            comps = getattr(ent, "_components", None)
            tr = comps.get("Transform", None) if comps else None
            if tr is None:
                return None
            p = tr.position
            return (float(p.x), float(p.y), float(p.z))
        except Exception:
            return None

    def _seg(self, sx, sy, sz, ex, ey, ez, color, off):
        try:
            self._ensure_segcap(off + 1)
            self._S[off, 0] = sx
            self._S[off, 1] = sy
            self._S[off, 2] = sz
            self._E[off, 0] = ex
            self._E[off, 1] = ey
            self._E[off, 2] = ez
            self._C[off] = color
            return off + 1
        except Exception:
            return off

    def _cross(self, x, y, z, s, color, off):
        off = self._seg(x - s, y, z, x + s, y, z, color, off)
        off = self._seg(x, y - s, z, x, y + s, z, color, off)
        off = self._seg(x, y, z - s, x, y, z + s, color, off)
        return off

    def _xform_point(self, m, x, y, z, w):
        try:
            ox = x * m[0, 0] + y * m[1, 0] + z * m[2, 0] + w * m[3, 0]
            oy = x * m[0, 1] + y * m[1, 1] + z * m[2, 1] + w * m[3, 1]
            oz = x * m[0, 2] + y * m[1, 2] + z * m[2, 2] + w * m[3, 2]
            return (float(ox), float(oy), float(oz))
        except Exception:
            return None

    def _wire_poly(self, pts, color, off):
        try:
            n = len(pts)
            if n < 2:
                return off
            for i in range(n):
                a = pts[i]
                b = pts[(i + 1) % n]
                off = self._seg(a[0], a[1], a[2], b[0], b[1], b[2], color, off)
            return off
        except Exception:
            return off

    def _wire_box_at(self, m, cx, cy, cz, sx, sy, sz, color, off):
        try:
            hx = float(sx) * 0.5
            hy = float(sy) * 0.5
            hz = float(sz) * 0.5
            local = (
                (cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz),
                (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz),
                (cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz),
                (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz),
            )
            if m is not None:
                pts = []
                for p in local:
                    q = self._xform_point(m, p[0], p[1], p[2], 1.0)
                    if q is None:
                        return off
                    pts.append(q)
            else:
                pts = list(local)
            for a, b in _BOX_EDGES:
                pa = pts[a]
                pb = pts[b]
                off = self._seg(pa[0], pa[1], pa[2], pb[0], pb[1], pb[2], color, off)
            return off
        except Exception:
            return off

    def _wire_circle_at(self, m, cx, cy, cz, ux, uy, uz, vx, vy, vz, r, color, off, segs=20):
        try:
            rr = max(1e-6, float(r))
            pts = []
            for i in range(max(3, int(segs))):
                a = 6.283185307179586 * float(i) / float(max(3, int(segs)))
                ca = math.cos(a) * rr
                sa = math.sin(a) * rr
                lx = float(cx) + ux * ca + vx * sa
                ly = float(cy) + uy * ca + vy * sa
                lz = float(cz) + uz * ca + vz * sa
                if m is not None:
                    q = self._xform_point(m, lx, ly, lz, 1.0)
                    if q is None:
                        return off
                    pts.append(q)
                else:
                    pts.append((lx, ly, lz))
            return self._wire_poly(pts, color, off)
        except Exception:
            return off

    def _collect_contacts(self, scene, selected, playing, labels, lab_cap, off):
        if not playing or not self._show_contacts:
            return off
        pp = self._physics_plugin()
        if pp is not None:
            try:
                if self._hooked_pp is None:
                    self._install_contact_hook(pp)
            except Exception:
                pass
        items = []
        try:
            if pp is not None and getattr(pp, "_simulation_mode", "") == "single":
                items = self._read_single_contacts(pp)
            else:
                items = self._stashed_contacts
                self._stashed_contacts = []
        except Exception:
            items = []
        if not items:
            return off
        try:
            nl = min(3.0, max(0.05, float(self._contact_normal_length)))
        except Exception:
            nl = 0.6
        cur_pairs = set()
        cn = 0
        CO = self._XO
        CF = self._XF
        mn = self._xm
        ms = self._xm2
        for pos, nor, imp, ea, eb, has_pos in items:
            try:
                if selected is not None and ea not in selected and eb not in selected:
                    continue
                if ea and eb:
                    pair = (ea, eb) if ea <= eb else (eb, ea)
                    cur_pairs.add(pair)
                    is_new = pair not in self._contact_pairs
                else:
                    is_new = True
                color = self._contact_new_color if is_new else self._contact_stay_color
                if has_pos:
                    px, py, pz = pos
                    nx, ny, nz = nor
                    off = self._cross(px, py, pz, 0.09, color, off)
                    if cn < 512:
                        CO[cn, 0] = px
                        CO[cn, 1] = py
                        CO[cn, 2] = pz
                        CF[cn, 0] = nx * nl
                        CF[cn, 1] = ny * nl
                        CF[cn, 2] = nz * nl
                        mn[cn] = is_new
                        ms[cn] = not is_new
                        cn += 1
                    if lab_cap > 0 and len(labels) < lab_cap and imp > 0.0:
                        try:
                            labels.append((px + nx * nl, py + ny * nl, pz + nz * nl, f"{imp:.1f}", color))
                        except Exception:
                            pass
                else:
                    ca = self._entity_center(scene, ea)
                    cb = self._entity_center(scene, eb)
                    if ca is not None and cb is not None:
                        off = self._seg(ca[0], ca[1], ca[2], cb[0], cb[1], cb[2], self._contact_stay_color, off)
            except Exception:
                continue
        try:
            self._contact_pairs = cur_pairs
        except Exception:
            pass
        if cn > 0:
            off = self._emit(CO, CF, mn, cn, 1.0, self._contact_new_color, off)
            off = self._emit(CO, CF, ms, cn, 1.0, self._contact_stay_color, off)
        return off

    def _collect_extras(self, entities, selected, scene, labels, lab_cap, off):
        show_j = self._show_joints
        show_c = self._show_colliders
        show_v = self._show_velocity
        if not show_j and not show_c and not show_v:
            return off
        cc = 0
        CO = self._XO
        CF = self._XF
        mm = self._xm
        for entity in entities:
            try:
                if not getattr(entity, "_active", True):
                    continue
                eid = entity.id
                if selected is not None and eid not in selected:
                    continue
                comps = getattr(entity, "_components", None)
                if not comps:
                    continue
                tr = comps.get("Transform", None)
                if tr is None:
                    continue
                try:
                    p = tr.position
                    ox = float(p.x)
                    oy = float(p.y)
                    oz = float(p.z)
                except Exception:
                    continue
                if show_v:
                    try:
                        chc = comps.get("CharacterController", None)
                        if chc is not None and getattr(chc, "enabled", True):
                            v = chc._velocity
                            vx = float(v.x)
                            vy = float(v.y)
                            vz = float(v.z)
                            vm = math.sqrt(vx * vx + vy * vy + vz * vz)
                            if vm > self._min_magnitude and cc < 512:
                                CO[cc, 0] = ox
                                CO[cc, 1] = oy
                                CO[cc, 2] = oz
                                CF[cc, 0] = vx
                                CF[cc, 1] = vy
                                CF[cc, 2] = vz
                                mm[cc] = True
                                cc += 1
                                if lab_cap > 0 and len(labels) < lab_cap:
                                    labels.append((ox, oy, oz, f"cc {vm:.2f}", self._velocity_color))
                    except Exception:
                        pass
                if show_j:
                    try:
                        jn = comps.get("Joint", None)
                        if jn is not None and getattr(jn, "enabled", True):
                            off = self._draw_joint(entity, scene, entities, tr, jn, ox, oy, oz, off)
                    except Exception:
                        pass
                if show_c:
                    try:
                        off = self._draw_colliders(comps, tr, ox, oy, oz, off)
                    except Exception:
                        pass
            except Exception:
                continue
        if show_v and cc > 0:
            off = self._emit(CO, CF, mm, cc, self._velocity_scale, self._velocity_color, off)
        return off

    def _draw_joint(self, entity, scene, entities, tr, jn, ox, oy, oz, off):
        try:
            m = getattr(tr, "world_matrix", None)
            m = m._d if m is not None else None
        except Exception:
            m = None
        try:
            a = jn.anchor
            ax = float(a.x)
            ay = float(a.y)
            az = float(a.z)
        except Exception:
            ax = ay = az = 0.0
        if m is not None:
            q = self._xform_point(m, ax, ay, az, 1.0)
            if q is None:
                return off
            wx, wy, wz = q
        else:
            wx = ox + ax
            wy = oy + ay
            wz = oz + az
        try:
            d = jn.axis
            dx = float(d.x)
            dy = float(d.y)
            dz = float(d.z)
        except Exception:
            dx = dy = dz = 0.0
        dl = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dl > 1e-9 and m is not None:
            q = self._xform_point(m, dx, dy, dz, 0.0)
            if q is not None:
                dx, dy, dz = q
                dl = math.sqrt(dx * dx + dy * dy + dz * dz)
        conn = None
        try:
            cid = getattr(jn, "_connected_entity_id", "") or ""
            if cid:
                try:
                    conn = scene.get_entity(cid)
                except Exception:
                    conn = None
            if conn is None:
                nm = getattr(jn, "connected_entity_name", "") or ""
                if nm:
                    for e in entities:
                        try:
                            if getattr(e, "name", "") == nm:
                                conn = e
                                break
                        except Exception:
                            continue
        except Exception:
            conn = None
        if conn is not None:
            cp = self._entity_center(scene, getattr(conn, "id", ""))
            if cp is not None:
                off = self._seg(ox, oy, oz, cp[0], cp[1], cp[2], self._joint_color, off)
        off = self._cross(wx, wy, wz, 0.12, self._joint_color, off)
        if dl > 1e-9:
            try:
                ux = dx / dl
                uy = dy / dl
                uz = dz / dl
                off = self._seg(wx, wy, wz, wx + ux * 0.5, wy + uy * 0.5, wz + uz * 0.5, self._joint_color, off)
            except Exception:
                pass
        return off

    def _draw_colliders(self, comps, tr, ox, oy, oz, off):
        try:
            m = getattr(tr, "world_matrix", None)
            m = m._d if m is not None else None
        except Exception:
            m = None
        box = comps.get("BoxCollider", None)
        if box is not None and getattr(box, "enabled", True):
            try:
                ce = box.center
                sz = box.size
                color = self._trigger_color if getattr(box, "is_trigger", False) else self._collider_color
                off = self._wire_box_at(m, float(ce.x), float(ce.y), float(ce.z), float(sz.x), float(sz.y), float(sz.z), color, off)
            except Exception:
                pass
        sph = comps.get("SphereCollider", None)
        if sph is not None and getattr(sph, "enabled", True):
            try:
                ce = sph.center
                r = max(1e-6, float(sph.radius))
                color = self._trigger_color if getattr(sph, "is_trigger", False) else self._collider_color
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, r, color, off)
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, r, color, off)
                off = self._wire_circle_at(m, float(ce.x), float(ce.y), float(ce.z), 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, r, color, off)
            except Exception:
                pass
        cap = comps.get("CapsuleCollider", None)
        if cap is not None and getattr(cap, "enabled", True):
            try:
                ce = cap.center
                r = max(1e-6, float(cap.radius))
                h = max(0.0, float(cap.height))
                color = self._trigger_color if getattr(cap, "is_trigger", False) else self._collider_color
                off = self._wire_capsule_at(m, float(ce.x), float(ce.y), float(ce.z), r, h, int(getattr(cap, "direction", 1)), color, off)
            except Exception:
                pass
        b2 = comps.get("BoxCollider2D", None)
        if b2 is not None and getattr(b2, "enabled", True):
            try:
                ce = getattr(b2, "center", None)
                cx = float(ce.x) if ce is not None else 0.0
                cy = float(ce.y) if ce is not None else 0.0
                sz = b2.size
                color = self._trigger_color if getattr(b2, "is_trigger", False) else self._collider_color
                off = self._wire_box_at(m, cx, cy, 0.0, float(sz.x), float(sz.y), 0.001, color, off)
            except Exception:
                pass
        c2 = comps.get("CircleCollider2D", None)
        if c2 is not None and getattr(c2, "enabled", True):
            try:
                ce = getattr(c2, "center", None)
                cx = float(ce.x) if ce is not None else 0.0
                cy = float(ce.y) if ce is not None else 0.0
                r = max(1e-6, float(c2.radius))
                color = self._trigger_color if getattr(c2, "is_trigger", False) else self._collider_color
                off = self._wire_circle_at(m, cx, cy, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, r, color, off)
            except Exception:
                pass
        return off

    def _wire_capsule_at(self, m, cx, cy, cz, r, h, direction, color, off):
        try:
            if direction == 0:
                ax, ay, az = 1.0, 0.0, 0.0
            elif direction == 2:
                ax, ay, az = 0.0, 0.0, 1.0
            else:
                ax, ay, az = 0.0, 1.0, 0.0
            if abs(ay) > 0.9:
                rx, ry, rz = 1.0, 0.0, 0.0
            else:
                rx, ry, rz = 0.0, 1.0, 0.0
            ux = ay * rz - az * ry
            uy = az * rx - ax * rz
            uz = ax * ry - ay * rx
            ul = math.sqrt(ux * ux + uy * uy + uz * uz)
            if ul < 1e-9:
                return off
            ux /= ul
            uy /= ul
            uz /= ul
            vx = ay * uz - az * uy
            vy = az * ux - ax * uz
            vz = ax * uy - ay * ux
            half = max(0.0, float(h) * 0.5 - float(r))
            tx = float(cx) + ax * half
            ty = float(cy) + ay * half
            tz = float(cz) + az * half
            bx = float(cx) - ax * half
            by = float(cy) - ay * half
            bz = float(cz) - az * half
            off = self._wire_circle_at(m, tx, ty, tz, ux, uy, uz, vx, vy, vz, r, color, off)
            off = self._wire_circle_at(m, bx, by, bz, ux, uy, uz, vx, vy, vz, r, color, off)
            for k in range(4):
                a = 1.5707963267948966 * float(k)
                ca = math.cos(a) * r
                sa = math.sin(a) * r
                lx = ux * ca + vx * sa
                ly = uy * ca + vy * sa
                lz = uz * ca + vz * sa
                if m is not None:
                    p0 = self._xform_point(m, tx + lx, ty + ly, tz + lz, 1.0)
                    p1 = self._xform_point(m, bx + lx, by + ly, bz + lz, 1.0)
                    if p0 is None or p1 is None:
                        return off
                    off = self._seg(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], color, off)
                else:
                    off = self._seg(tx + lx, ty + ly, tz + lz, bx + lx, by + ly, bz + lz, color, off)
            return off
        except Exception:
            return off

    def _emit(self, O, F, mask, k, scale, color, off):
        try:
            idx = np.flatnonzero(mask[:k])
        except Exception:
            return off
        if idx.size == 0:
            return off
        try:
            Ok = O[idx]
            Sv = F[idx] * np.float32(scale)
            L = np.sqrt(np.einsum("ij,ij->i", Sv, Sv))
            g = L > np.float32(1e-9)
            if not bool(np.any(g)):
                return off
            Ok = np.ascontiguousarray(Ok[g])
            Sv = np.ascontiguousarray(Sv[g])
            L = np.ascontiguousarray(L[g])
            m = int(Ok.shape[0])
            self._ensure_segcap(off + m * 3)
            ends = Ok + Sv
            h = np.minimum(L * np.float32(0.22), np.float32(0.30))
            Ls = np.maximum(L, np.float32(1e-9))
            d = Sv / Ls[:, None]
            up = np.abs(d[:, 1]) > np.float32(0.9)
            ref = np.where(up[:, None], _REF_X, _REF_Y)
            p1 = np.cross(d, ref)
            n1 = np.linalg.norm(p1, axis=1)
            p1 = p1 / np.maximum(n1, np.float32(1e-6))[:, None]
            hw = (h * np.float32(0.5))[:, None]
            hh = h[:, None]
            b = ends - d * hh
            S = self._S
            E = self._E
            C = self._C
            S[off + 0::3][:m] = Ok
            E[off + 0::3][:m] = ends
            S[off + 1::3][:m] = ends
            E[off + 1::3][:m] = b + p1 * hw
            S[off + 2::3][:m] = ends
            E[off + 2::3][:m] = b - p1 * hw
            C[off:off + m * 3] = color
            return off + m * 3
        except Exception:
            return off

    def _flat_submit(self, s, e, c):
        try:
            import core.gizmo.api as _api
            inst = _api._gizmos_instance
        except Exception:
            inst = None
        if inst is not None:
            try:
                with inst._lock:
                    try:
                        inst._flat_size = 0
                    except Exception:
                        pass
                    inst._revision += 1
                Gizmos.draw_lines(s, e, c)
                return
            except Exception:
                pass
        self._fallback_submit(s, e, c)

    def _fallback_submit(self, s, e, c):
        try:
            n = int(s.shape[0])
        except Exception:
            return
        for i in range(n):
            try:
                Gizmos.draw_line(
                    (float(s[i, 0]), float(s[i, 1]), float(s[i, 2])),
                    (float(e[i, 0]), float(e[i, 1]), float(e[i, 2])),
                    color=(float(c[i, 0]), float(c[i, 1]), float(c[i, 2]), float(c[i, 3])),
                    thickness=1.0,
                    tag=_TAG,
                )
            except Exception:
                continue

    def _submit_labels(self, labels):
        for x, y, z, text, color in labels:
            try:
                Gizmos.draw_label(
                    (x, y, z),
                    text,
                    color=color,
                    font_size=12,
                    tag=_TAG,
                )
            except Exception:
                continue


if _HAS_QT:
    class _PhysicsVisualisationPanel(QWidget):
        def __init__(self, plugin, parent=None):
            super().__init__(parent)
            self._plugin = plugin
            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)
            s = plugin.settings
            self._cb_enabled = QCheckBox("Enabled")
            self._cb_enabled.setChecked(bool(s["enabled"]))
            self._cb_enabled.toggled.connect(lambda v: self._set("enabled", bool(v)))
            layout.addWidget(self._cb_enabled)
            self._cb_velocity = QCheckBox("Velocity")
            self._cb_velocity.setChecked(bool(s["show_velocity"]))
            self._cb_velocity.toggled.connect(lambda v: self._set("show_velocity", bool(v)))
            layout.addWidget(self._cb_velocity)
            self._cb_acceleration = QCheckBox("Acceleration")
            self._cb_acceleration.setChecked(bool(s["show_acceleration"]))
            self._cb_acceleration.toggled.connect(lambda v: self._set("show_acceleration", bool(v)))
            layout.addWidget(self._cb_acceleration)
            self._cb_moment = QCheckBox("Moment")
            self._cb_moment.setChecked(bool(s["show_moment"]))
            self._cb_moment.toggled.connect(lambda v: self._set("show_moment", bool(v)))
            layout.addWidget(self._cb_moment)
            self._cb_selected = QCheckBox("Only selected")
            self._cb_selected.setChecked(bool(s["only_selected"]))
            self._cb_selected.toggled.connect(lambda v: self._set("only_selected", bool(v)))
            layout.addWidget(self._cb_selected)
            self._cb_labels = QCheckBox("Value labels")
            self._cb_labels.setChecked(bool(s["show_labels"]))
            self._cb_labels.toggled.connect(lambda v: self._set("show_labels", bool(v)))
            layout.addWidget(self._cb_labels)
            self._cb_editor = QCheckBox("Show in editor")
            self._cb_editor.setChecked(bool(s["show_editor"]))
            self._cb_editor.toggled.connect(lambda v: self._set("show_editor", bool(v)))
            layout.addWidget(self._cb_editor)
            self._cb_runtime = QCheckBox("Show in play mode")
            self._cb_runtime.setChecked(bool(s["show_runtime"]))
            self._cb_runtime.toggled.connect(lambda v: self._set("show_runtime", bool(v)))
            layout.addWidget(self._cb_runtime)
            self._cb_contacts = QCheckBox("Contacts")
            self._cb_contacts.setChecked(bool(s["show_contacts"]))
            self._cb_contacts.toggled.connect(lambda v: self._set("show_contacts", bool(v)))
            layout.addWidget(self._cb_contacts)
            self._cb_joints = QCheckBox("Joints")
            self._cb_joints.setChecked(bool(s["show_joints"]))
            self._cb_joints.toggled.connect(lambda v: self._set("show_joints", bool(v)))
            layout.addWidget(self._cb_joints)
            self._cb_colliders = QCheckBox("Colliders")
            self._cb_colliders.setChecked(bool(s["show_colliders"]))
            self._cb_colliders.toggled.connect(lambda v: self._set("show_colliders", bool(v)))
            layout.addWidget(self._cb_colliders)
            self._make_scale_row(layout, "Velocity scale", float(s["velocity_scale"]), "velocity_scale")
            self._make_scale_row(layout, "Acceleration scale", float(s["acceleration_scale"]), "acceleration_scale")
            self._make_scale_row(layout, "Moment scale", float(s["moment_scale"]), "moment_scale")
            self._make_scale_row(layout, "Max length", float(s["max_length"]), "max_length")
            self._make_scale_row(layout, "Min magnitude", float(s["min_magnitude"]), "min_magnitude")
            self._make_contact_row(layout, "Contact normal", float(s["contact_normal_length"]), "contact_normal_length")
            self._make_smooth_row(layout, "Smoothing", float(s["smooth"]), "smooth")
            self._make_scale_row(layout, "Accel spike limit", float(s["accel_spike"]), "accel_spike")
            self._make_scale_row(layout, "Moment spike limit", float(s["moment_spike"]), "moment_spike")
            self._make_int_row(layout, "Label cap", int(s["label_cap"]), "label_cap")
            btn = QPushButton("Clear")
            btn.clicked.connect(self._on_clear)
            layout.addWidget(btn)
            layout.addStretch(1)

        def _set(self, key, value):
            try:
                self._plugin.configure({key: value})
            except Exception:
                pass

        def _on_clear(self):
            try:
                self._plugin.clear()
            except Exception:
                pass

        def _make_scale_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.001, 5000.0)
            box.setDecimals(3)
            box.setSingleStep(0.05)
            box.setValue(max(0.001, value))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box

        def _make_smooth_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.02, 0.98)
            box.setDecimals(2)
            box.setSingleStep(0.05)
            box.setValue(min(0.98, max(0.02, value)))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box

        def _make_contact_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.05, 3.0)
            box.setDecimals(2)
            box.setSingleStep(0.05)
            box.setValue(min(3.0, max(0.05, value)))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box

        def _make_int_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QSpinBox()
            box.setRange(0, 500)
            box.setSingleStep(4)
            box.setValue(max(0, value))
            box.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box


def get_plugin():
    return PhysicsVisualisationPlugin()
