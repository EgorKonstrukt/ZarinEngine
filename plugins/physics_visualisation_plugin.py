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
        self._velocity_color = (0.25, 0.95, 0.30, 1.0)
        self._acceleration_color = (1.0, 0.80, 0.15, 1.0)
        self._moment_color = (1.0, 0.30, 0.75, 1.0)
        self._prev = {}
        self._panel = None
        self._timer = None
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
        self._purge_gizmos()
        self._last_draw = 0.0

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
        self._collect_and_submit(entities, selected, now)

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

    def _collect_and_submit(self, entities, selected, now):
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
                    labels.append((ox, oy, oz, svx, svy, svz, vmag))
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
        vscale = self._velocity_scale
        maxlen = self._max_length
        for ox, oy, oz, vx, vy, vz, vmag in labels:
            try:
                sx = vx * vscale
                sy = vy * vscale
                sz = vz * vscale
                L = math.sqrt(sx * sx + sy * sy + sz * sz)
                if L > maxlen and L > 1e-12:
                    kk = maxlen / L
                    sx *= kk
                    sy *= kk
                    sz *= kk
                Gizmos.draw_label(
                    (ox + sx, oy + sy, oz + sz),
                    f"{vmag:.2f}",
                    color=self._velocity_color,
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
            self._make_scale_row(layout, "Velocity scale", float(s["velocity_scale"]), "velocity_scale")
            self._make_scale_row(layout, "Acceleration scale", float(s["acceleration_scale"]), "acceleration_scale")
            self._make_scale_row(layout, "Moment scale", float(s["moment_scale"]), "moment_scale")
            self._make_scale_row(layout, "Max length", float(s["max_length"]), "max_length")
            self._make_scale_row(layout, "Min magnitude", float(s["min_magnitude"]), "min_magnitude")
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
