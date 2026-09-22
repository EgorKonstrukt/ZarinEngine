from __future__ import annotations
import math
import time
from core.foundation.plugin_manager import PluginBase
from core.foundation.logger import Logger
from core.gizmo.api import Gizmos
try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
    _HAS_QT = True
except Exception:
    _HAS_QT = False
_TAG = "physics_visualisation"


class PhysicsVisualisationPlugin(PluginBase):
    NAME = "PhysicsVisualisation"
    VERSION = "1.0.0"
    DESCRIPTION = "Physics vectors visualisation with gizmo arrows: velocity, acceleration, moment."
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
        self._velocity_scale = 0.5
        self._acceleration_scale = 0.1
        self._moment_scale = 0.1
        self._max_length = 5.0
        self._min_magnitude = 0.05
        self._velocity_color = (0.25, 0.95, 0.30, 1.0)
        self._acceleration_color = (1.0, 0.80, 0.15, 1.0)
        self._moment_color = (1.0, 0.30, 0.75, 1.0)
        self._prev = {}
        self._panel = None
        self._timer = None

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
        }

    def initialize(self, engine):
        super().initialize(engine)
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
        try:
            Gizmos.clear_tag(_TAG)
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
            if not bool(value):
                try:
                    Gizmos.clear_tag(_TAG)
                except Exception:
                    pass
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

    def _redraw(self):
        try:
            Gizmos.clear_tag(_TAG)
        except Exception:
            pass
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
            return
        if not playing and not self._show_editor:
            return
        if not self._show_velocity and not self._show_acceleration and not self._show_moment:
            return
        try:
            entities = scene.get_all_entities()
        except Exception:
            return
        selected = None
        if self._only_selected:
            selected = self._selected_ids(eng)
            if not selected:
                return
        now = time.perf_counter()
        for entity in entities:
            try:
                self._draw_entity(entity, selected, now)
            except Exception:
                continue

    def _draw_entity(self, entity, selected, now):
        if not getattr(entity, "_active", True):
            return
        try:
            eid = entity.id
        except Exception:
            return
        if selected is not None and eid not in selected:
            return
        comps = getattr(entity, "_components", None)
        if not comps:
            return
        tr = comps.get("Transform", None)
        if tr is None:
            return
        rb = comps.get("Rigidbody", None)
        if rb is not None and getattr(rb, "enabled", True):
            self._draw_rigidbody(eid, tr, rb, now, False)
            return
        rb2d = comps.get("Rigidbody2D", None)
        if rb2d is not None and getattr(rb2d, "enabled", True):
            self._draw_rigidbody(eid, tr, rb2d, now, True)

    def _draw_rigidbody(self, eid, tr, rb, now, is_2d):
        try:
            p = tr.position
            ox = float(p.x)
            oy = float(p.y)
            oz = float(p.z)
        except Exception:
            return
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
            return
        if not math.isfinite(ox + oy + oz + vx + vy + vz + wx + wy + wz):
            return
        if mass <= 0.0:
            mass = 1.0
        if self._show_velocity:
            self._push(ox, oy, oz, vx, vy, vz, self._velocity_scale, self._velocity_color)
        prev = self._prev.get(eid, None)
        acc_ok = False
        ax = 0.0
        ay = 0.0
        az = 0.0
        alx = 0.0
        aly = 0.0
        alz = 0.0
        if prev is not None:
            try:
                dt = now - prev[6]
            except Exception:
                dt = 0.0
            if dt >= 1e-4 and dt <= 1.0:
                try:
                    ax = (vx - prev[0]) / dt
                    ay = (vy - prev[1]) / dt
                    az = (vz - prev[2]) / dt
                    alx = (wx - prev[3]) / dt
                    aly = (wy - prev[4]) / dt
                    alz = (wz - prev[5]) / dt
                    acc_ok = True
                except Exception:
                    acc_ok = False
        try:
            self._prev[eid] = (vx, vy, vz, wx, wy, wz, now)
            if len(self._prev) > 4096:
                self._prev.clear()
                self._prev[eid] = (vx, vy, vz, wx, wy, wz, now)
        except Exception:
            pass
        if acc_ok and self._show_acceleration:
            self._push(ox, oy, oz, ax, ay, az, self._acceleration_scale, self._acceleration_color)
        if acc_ok and self._show_moment:
            self._push(ox, oy, oz, alx * mass, aly * mass, alz * mass, self._moment_scale, self._moment_color)

    def _push(self, ox, oy, oz, vx, vy, vz, scale, color):
        try:
            mag = math.sqrt(vx * vx + vy * vy + vz * vz)
        except Exception:
            return
        if not mag > self._min_magnitude:
            return
        sx = vx * scale
        sy = vy * scale
        sz = vz * scale
        try:
            length = math.sqrt(sx * sx + sy * sy + sz * sz)
        except Exception:
            return
        if not length > 1e-6:
            return
        if length > self._max_length:
            k = self._max_length / length
            sx *= k
            sy *= k
            sz *= k
        ex = ox + sx
        ey = oy + sy
        ez = oz + sz
        try:
            Gizmos.draw_arrow((ox, oy, oz), (ex, ey, ez), color=color, thickness=2.0, arrow_size=0.0, tag=_TAG)
        except Exception:
            return
        if self._show_labels:
            try:
                Gizmos.draw_label((ex, ey, ez), f"{mag:.2f}", color=color, font_size=12, tag=_TAG)
            except Exception:
                pass


if _HAS_QT:
    class _PhysicsVisualisationPanel(QWidget):
        def __init__(self, plugin, parent=None):
            super().__init__(parent)
            self._plugin = plugin
            self._lock = False
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
            self._sp_vel = self._make_scale_row(layout, "Velocity scale", float(s["velocity_scale"]), "velocity_scale")
            self._sp_acc = self._make_scale_row(layout, "Acceleration scale", float(s["acceleration_scale"]), "acceleration_scale")
            self._sp_mom = self._make_scale_row(layout, "Moment scale", float(s["moment_scale"]), "moment_scale")
            self._sp_max = self._make_scale_row(layout, "Max length", float(s["max_length"]), "max_length")
            self._sp_min = self._make_scale_row(layout, "Min magnitude", float(s["min_magnitude"]), "min_magnitude")
            btn = QPushButton("Clear")
            btn.clicked.connect(self._on_clear)
            layout.addWidget(btn)
            layout.addStretch(1)

        def _set(self, key, value):
            if self._lock:
                return
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
            box.setRange(0.001, 50.0)
            box.setDecimals(3)
            box.setSingleStep(0.05)
            box.setValue(max(0.001, value))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box


def get_plugin():
    return PhysicsVisualisationPlugin()
