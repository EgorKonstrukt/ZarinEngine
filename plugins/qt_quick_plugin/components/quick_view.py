# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.ecs.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField


QUICK_VIEW_TYPES: list = []

BILLBOARD_OPTIONS = ["Off", "Full", "Y"]


@ComponentRegistry.register
class QuickView(Component):
    _gizmo_icon_color = (65, 150, 200)
    _gizmo_icon_label = "Q"
    _show_gizmo_icon = True
    _allow_multiple = True

    DEFAULT_QML = ""
    DEFAULT_W = 512
    DEFAULT_H = 512
    DEFAULT_SX = 1.0
    DEFAULT_SY = 1.0
    TO_QML: dict = {}
    FROM_QML: dict = {}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("qml_text", "QML", FieldType.TEXTAREA),
            InspectorField("qml_file", "QML File", FieldType.RESOURCE_PATH, file_filter="QML (*.qml)"),
            InspectorField("width_px", "Width Px", FieldType.INT, min_val=32, max_val=2048, step=1),
            InspectorField("height_px", "Height Px", FieldType.INT, min_val=32, max_val=2048, step=1),
            InspectorField("size_x", "Size X m", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.05, decimals=3),
            InspectorField("size_y", "Size Y m", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.05, decimals=3),
            InspectorField("transparent", "Transparent", FieldType.BOOL),
            InspectorField("billboard", "Billboard", FieldType.ENUM, enum_options=BILLBOARD_OPTIONS),
            InspectorField("interactive", "Interactive", FieldType.BOOL),
            InspectorField("opacity", "Opacity", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("render_order", "Render Order", FieldType.INT, min_val=-100, max_val=100, step=1),
            InspectorField("double_sided", "Double Sided", FieldType.BOOL),
            InspectorField("animated", "Animated", FieldType.BOOL),
            InspectorField("tint", "Tint", FieldType.COLOR),
        ]

    def __init__(self):
        super().__init__()
        self.qml_text: str = ""
        self.qml_file: str = ""
        self.width_px: int = int(type(self).DEFAULT_W)
        self.height_px: int = int(type(self).DEFAULT_H)
        self.size_x: float = float(type(self).DEFAULT_SX)
        self.size_y: float = float(type(self).DEFAULT_SY)
        self.transparent: bool = True
        self.billboard: str = "Off"
        self.interactive: bool = True
        self.opacity: float = 1.0
        self.render_order: int = 0
        self.double_sided: bool = True
        self.animated: bool = False
        self.tint: list = [1.0, 1.0, 1.0, 1.0]
        self._dirty: bool = True
        self._qml_hash: int = 0
        self._poll_cache: dict = {}
        self._anim_accum: float = 0.0

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "QuickView" and cls not in QUICK_VIEW_TYPES:
            QUICK_VIEW_TYPES.append(cls)

    def mark_dirty(self):
        self._dirty = True

    def effective_qml(self) -> str:
        if self.qml_file:
            try:
                import os

                path = self.qml_file
                if not os.path.isabs(path):
                    try:
                        from core.engine.engine import Engine

                        eng = Engine.instance()
                        base = getattr(eng, "_project_path", "") or ""
                        if base:
                            cand = os.path.join(base, path)
                            if os.path.isfile(cand):
                                path = cand
                    except Exception:
                        pass
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                    if text.strip():
                        return text
            except Exception:
                pass
        if self.qml_text and self.qml_text.strip():
            return self.qml_text
        default = getattr(type(self), "DEFAULT_QML", "")
        if default and default.strip():
            return default
        try:
            from plugins.qt_quick_plugin.quick_qml import default_qml_for

            return default_qml_for(type(self).__name__)
        except Exception:
            return ""

    def effective_px(self) -> tuple:
        w = int(self.width_px) if int(self.width_px) >= 32 else 32
        h = int(self.height_px) if int(self.height_px) >= 32 else 32
        if w > 2048:
            w = 2048
        if h > 2048:
            h = 2048
        return (w, h)

    def on_update(self, dt: float):
        if self.animated:
            self._anim_accum += float(dt)
            if self._anim_accum >= 0.05:
                self._anim_accum = 0.0
                self._dirty = True

    def intersect_ray(self, origin, direction) -> tuple:
        try:
            tr = self.transform
            if tr is None:
                return (False, 0.0, 0.0, 0.0)
            center = tr.position
            right = tr.right
            up = tr.up
            fwd = tr.forward
            nx = float(fwd.x)
            ny = float(fwd.y)
            nz = float(fwd.z)
            dx = float(direction.x)
            dy = float(direction.y)
            dz = float(direction.z)
            denom = dx * nx + dy * ny + dz * nz
            if abs(denom) < 1e-8:
                return (False, 0.0, 0.0, 0.0)
            ox = float(origin.x) - float(center.x)
            oy = float(origin.y) - float(center.y)
            oz = float(origin.z) - float(center.z)
            t = -(ox * nx + oy * ny + oz * nz) / denom
            if t < 0.0:
                return (False, 0.0, 0.0, 0.0)
            hx = float(origin.x) + dx * t - float(center.x)
            hy = float(origin.y) + dy * t - float(center.y)
            hz = float(origin.z) + dz * t - float(center.z)
            rx = float(right.x)
            ry = float(right.y)
            rz = float(right.z)
            ux = float(up.x)
            uy = float(up.y)
            uz = float(up.z)
            rlen = (rx * rx + ry * ry + rz * rz) ** 0.5
            ulen = (ux * ux + uy * uy + uz * uz) ** 0.5
            if rlen < 1e-8 or ulen < 1e-8:
                return (False, 0.0, 0.0, 0.0)
            lx = (hx * rx + hy * ry + hz * rz) / (rlen * rlen)
            ly = (hx * ux + hy * uy + hz * uz) / (ulen * ulen)
            sx = float(self.size_x)
            sy = float(self.size_y)
            try:
                sc = tr.local_scale
                sx = sx * abs(float(sc.x))
                sy = sy * abs(float(sc.y))
            except Exception:
                pass
            if abs(lx) > sx * 0.5 or abs(ly) > sy * 0.5:
                return (False, 0.0, 0.0, 0.0)
            u = lx / sx + 0.5 if sx > 1e-8 else 0.5
            v = ly / sy + 0.5 if sy > 1e-8 else 0.5
            return (True, float(u), float(v), float(t))
        except Exception:
            return (False, 0.0, 0.0, 0.0)

    def gizmo_lines(self):
        try:
            tr = self.transform
            if tr is None:
                return []
            from core.maths.math3d import Vec3

            c = tr.position
            r = tr.right
            u = tr.up
            sx = float(self.size_x) * 0.5
            sy = float(self.size_y) * 0.5
            try:
                sc = tr.local_scale
                sx = sx * abs(float(sc.x))
                sy = sy * abs(float(sc.y))
            except Exception:
                pass
            rnx = float(r.x)
            rny = float(r.y)
            rnz = float(r.z)
            rl = (rnx * rnx + rny * rny + rnz * rnz) ** 0.5
            if rl > 1e-8:
                rnx /= rl
                rny /= rl
                rnz /= rl
            unx = float(u.x)
            uny = float(u.y)
            unz = float(u.z)
            ul = (unx * unx + uny * uny + unz * unz) ** 0.5
            if ul > 1e-8:
                unx /= ul
                uny /= ul
                unz /= ul
            cx = float(c.x)
            cy = float(c.y)
            cz = float(c.z)
            p1 = Vec3(cx - rnx * sx - unx * sy, cy - rny * sx - uny * sy, cz - rnz * sx - unz * sy)
            p2 = Vec3(cx + rnx * sx - unx * sy, cy + rny * sx - uny * sy, cz + rnz * sx - unz * sy)
            p3 = Vec3(cx + rnx * sx + unx * sy, cy + rny * sx + uny * sy, cz + rnz * sx + unz * sy)
            p4 = Vec3(cx - rnx * sx + unx * sy, cy - rny * sx + uny * sy, cz - rnz * sx + unz * sy)
            col = [0.25, 0.6, 0.85, 1.0]
            return [(p1, p2, col), (p2, p3, col), (p3, p4, col), (p4, p1, col)]
        except Exception:
            return []

    def serialize(self) -> dict:
        d = super().serialize()
        d.update(
            {
                "qml_text": self.qml_text,
                "qml_file": self.qml_file,
                "width_px": int(self.width_px),
                "height_px": int(self.height_px),
                "size_x": float(self.size_x),
                "size_y": float(self.size_y),
                "transparent": bool(self.transparent),
                "billboard": str(self.billboard),
                "interactive": bool(self.interactive),
                "opacity": float(self.opacity),
                "render_order": int(self.render_order),
                "double_sided": bool(self.double_sided),
                "animated": bool(self.animated),
                "tint": [float(self.tint[0]), float(self.tint[1]), float(self.tint[2]), float(self.tint[3])] if self.tint and len(self.tint) >= 4 else [1.0, 1.0, 1.0, 1.0],
            }
        )
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = cls()
        inst.enabled = bool(data.get("enabled", True))
        inst.qml_text = str(data.get("qml_text", "") or "")
        inst.qml_file = str(data.get("qml_file", "") or "")
        inst.width_px = int(data.get("width_px", cls.DEFAULT_W))
        inst.height_px = int(data.get("height_px", cls.DEFAULT_H))
        inst.size_x = float(data.get("size_x", cls.DEFAULT_SX))
        inst.size_y = float(data.get("size_y", cls.DEFAULT_SY))
        inst.transparent = bool(data.get("transparent", True))
        inst.billboard = str(data.get("billboard", "Off"))
        inst.interactive = bool(data.get("interactive", True))
        inst.opacity = float(data.get("opacity", 1.0))
        inst.render_order = int(data.get("render_order", 0))
        inst.double_sided = bool(data.get("double_sided", True))
        inst.animated = bool(data.get("animated", False))
        tint = data.get("tint", [1.0, 1.0, 1.0, 1.0])
        try:
            inst.tint = [float(tint[0]), float(tint[1]), float(tint[2]), float(tint[3])]
        except Exception:
            inst.tint = [1.0, 1.0, 1.0, 1.0]
        inst._dirty = True
        return inst
