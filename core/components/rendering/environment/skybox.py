# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import os
import time
import numpy as np
import moderngl
from core.ecs.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.maths.math3d import Mat4, Vec3
from core.components.rendering.environment.sky_ibl import get_sky_ibl

_SKYBOX_TEX_CACHE: dict[str, tuple[float, object]] = {}
_SKYBOX_IBL_COOLDOWN = 0.15

_LDR_EXTS = frozenset((".png", ".jpg", ".jpeg", ".tga", ".bmp"))


def _resolve_skybox_path(path: str) -> str:
    if not path:
        return ""
    if os.path.exists(path):
        return os.path.abspath(path)
    if not os.path.isabs(path):
        try:
            from core.engine.engine import Engine
            eng = Engine.instance()
            root = eng.project_root if eng and eng.project_root else os.getcwd()
        except Exception:
            root = os.getcwd()
        candidate = os.path.normpath(os.path.join(root, path))
        if os.path.exists(candidate):
            return candidate
    return path


def _load_skybox_float(path: str):
    from core.components.rendering.environment.sky import _load_env_float
    arr = _load_env_float(path)
    if arr is None:
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in _LDR_EXTS:
        try:
            if float(arr.max()) > 1.0:
                arr = (arr / 255.0).astype(np.float32)
        except Exception:
            pass
    return np.ascontiguousarray(arr)


def _get_skybox_texture(ctx: moderngl.Context, path: str):
    if not path:
        return None
    abs_path = _resolve_skybox_path(path)
    if not abs_path or not os.path.exists(abs_path):
        return None
    mtime = os.path.getmtime(abs_path)
    cached = _SKYBOX_TEX_CACHE.get(abs_path)
    if cached is not None:
        cm, tex = cached
        if abs(mtime - cm) < 0.001:
            return tex
        if tex is not None:
            try:
                tex.release()
            except Exception:
                pass
    arr = _load_skybox_float(abs_path)
    if arr is None:
        _SKYBOX_TEX_CACHE[abs_path] = (mtime, None)
        return None
    h, w = arr.shape[:2]
    tex = ctx.texture((w, h), 3, arr.tobytes(), dtype="f4")
    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    try:
        tex.build_mipmaps()
    except Exception:
        pass
    tex.repeat_x = True
    tex.repeat_y = True
    _SKYBOX_TEX_CACHE[abs_path] = (mtime, tex)
    return tex


def _rotation_matrix_bytes(yaw_deg: float, pitch_deg: float, roll_deg: float) -> bytes:
    cy = math.cos(math.radians(yaw_deg))
    sy = math.sin(math.radians(yaw_deg))
    cx = math.cos(math.radians(pitch_deg))
    sx = math.sin(math.radians(pitch_deg))
    cz = math.cos(math.radians(roll_deg))
    sz = math.sin(math.radians(roll_deg))
    r00 = cy * cz + sy * sx * sz
    r01 = -cy * sz + sy * sx * cz
    r02 = sy * cx
    r10 = cx * sz
    r11 = cx * cz
    r12 = -sx
    r20 = -sy * cz + cy * sx * sz
    r21 = sy * sz + cy * sx * cz
    r22 = cy * cx
    return np.array([r00, r10, r20, r01, r11, r21, r02, r12, r22], dtype=np.float32).tobytes()


@ComponentRegistry.register
class Skybox(Component):
    _icon = "Sky.png"
    _batch_versioned_fields = frozenset(("skybox_path",))

    def __setattr__(self, name: str, value):
        object.__setattr__(self, name, value)
        if name in Skybox._batch_versioned_fields:
            try:
                ent = self.__dict__.get("_entity", None)
                sc = ent._scene if ent is not None else None
                if sc is not None:
                    sc._render_version += 1
            except Exception:
                pass

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "HDRI Skybox", FieldType.HEADER),
            InspectorField("skybox_path", "HDRI / EXR", FieldType.RESOURCE_PATH, file_filter="HDR / EXR (*.hdr *.exr)"),
            InspectorField("show_background", "Show Background", FieldType.BOOL),
            InspectorField("affect_environment", "Affect Environment (IBL)", FieldType.BOOL),
            InspectorField("", "Image", FieldType.HEADER),
            InspectorField("exposure", "Exposure (EV)", FieldType.SLIDER, min_val=-10.0, max_val=10.0, step=0.1, decimals=2),
            InspectorField("intensity", "Intensity", FieldType.SLIDER, min_val=0.0, max_val=8.0, step=0.05, decimals=2),
            InspectorField("tint", "Tint", FieldType.COLOR),
            InspectorField("saturation", "Saturation", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("blur", "Background Blur", FieldType.SLIDER, min_val=0.0, max_val=8.0, step=0.1, decimals=1),
            InspectorField("flip_y", "Flip Y", FieldType.BOOL),
            InspectorField("", "Orientation", FieldType.HEADER),
            InspectorField("rotation", "Rotation Yaw/Pitch/Roll (deg)", FieldType.VEC3),
        ]

    def __init__(self):
        super().__init__()
        self.material_path: str = "core/shaders/Skybox.shader"
        self.skybox_path: str = ""
        self.show_background: bool = True
        self.affect_environment: bool = True
        self.exposure: float = 0.0
        self.intensity: float = 1.0
        self.tint: list[float] = [1.0, 1.0, 1.0]
        self.saturation: float = 1.0
        self.blur: float = 0.0
        self.flip_y: bool = False
        self.rotation: Vec3 = Vec3.zero()
        self._sky_ibl = None
        self._prog_names = None
        self._prog_id = None
        self._ibl_grade_done = None
        self._ibl_last_t = 0.0

    def _uniform_names(self, prog) -> frozenset:
        pid = id(prog)
        if self._prog_names is None or self._prog_id != pid:
            self._prog_names = frozenset(prog)
            self._prog_id = pid
        return self._prog_names

    def _grade_key(self) -> tuple:
        try:
            t = self.tint
            tint = (round(float(t[0]), 3), round(float(t[1]), 3), round(float(t[2]), 3))
        except Exception:
            tint = (1.0, 1.0, 1.0)
        try:
            rot = self.rotation
            rotation = (round(float(rot.x), 2), round(float(rot.y), 2), round(float(rot.z), 2))
        except Exception:
            rotation = (0.0, 0.0, 0.0)
        try:
            exposure = round(float(self.exposure), 3)
        except Exception:
            exposure = 0.0
        try:
            intensity = round(float(self.intensity), 3)
        except Exception:
            intensity = 1.0
        try:
            saturation = round(float(self.saturation), 3)
        except Exception:
            saturation = 1.0
        return (exposure, intensity, tint, saturation, rotation, bool(self.flip_y))

    def _grade_uniforms(self, key: tuple) -> dict:
        exposure, intensity, tint, saturation, rotation, flip_y = key
        return {
            "exposure": exposure,
            "intensity": intensity,
            "tint": tint,
            "saturation": saturation,
            "rotation": _rotation_matrix_bytes(rotation[0], rotation[1], rotation[2]),
            "flip_y": 1.0 if flip_y else 0.0,
        }

    def render_sky(self, ctx, shaders, view_mat, proj_mat, dir_light, cube_mesh):
        tex = _get_skybox_texture(ctx, self.skybox_path) if self.skybox_path else None
        if self.affect_environment and tex is not None:
            gk = self._grade_key()
            cur = self._sky_ibl
            live = cur is not None and getattr(cur, "ready", False)
            now = time.perf_counter()
            if (gk != self._ibl_grade_done or not live) and now - self._ibl_last_t >= _SKYBOX_IBL_COOLDOWN:
                self._ibl_last_t = now
                try:
                    self._sky_ibl = get_sky_ibl(ctx, _resolve_skybox_path(self.skybox_path), tex,
                                                grade_key=repr(gk), grade=self._grade_uniforms(gk))
                    self._ibl_grade_done = gk
                except Exception:
                    pass
        else:
            self._sky_ibl = None
        if not self.show_background:
            return
        prog = shaders.get_or_compile(self.material_path) if shaders else None
        if not prog or cube_mesh is None:
            return
        names = self._uniform_names(prog)
        if "u_equirect" in names:
            if tex is not None:
                tex.use(0)
                prog["u_equirect"].value = 0
            if "u_use_env" in names:
                prog["u_use_env"].value = 1.0 if tex is not None else 0.0
        if "u_exposure" in names:
            prog["u_exposure"].value = float(self.exposure)
        if "u_intensity" in names:
            prog["u_intensity"].value = float(self.intensity)
        if "u_tint" in names:
            t = self.tint
            try:
                prog["u_tint"].write(np.array([float(t[0]), float(t[1]), float(t[2])], dtype=np.float32).tobytes())
            except Exception:
                pass
        if "u_saturation" in names:
            prog["u_saturation"].value = float(self.saturation)
        if "u_blur" in names:
            prog["u_blur"].value = max(0.0, float(self.blur))
        if "u_flip_y" in names:
            prog["u_flip_y"].value = 1.0 if self.flip_y else 0.0
        if "u_rotation" in names:
            try:
                prog["u_rotation"].write(_rotation_matrix_bytes(self.rotation.x, self.rotation.y, self.rotation.z))
            except Exception:
                pass
        sky_view = np.eye(4, dtype=np.float64)
        sky_view[:3, :3] = view_mat._d[:3, :3].copy()
        mvp = Mat4(sky_view) * proj_mat
        if "u_mvp" in names:
            prog["u_mvp"].write(mvp.to_f32().tobytes())
        ctx.disable(moderngl.CULL_FACE)
        ctx.disable(moderngl.DEPTH_TEST)
        cube_mesh.render(prog)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)

    def serialize(self) -> dict:
        d = super().serialize()
        d["material_path"] = self.material_path
        d["skybox_path"] = self.skybox_path
        d["show_background"] = self.show_background
        d["affect_environment"] = self.affect_environment
        d["exposure"] = self.exposure
        d["intensity"] = self.intensity
        d["tint"] = list(self.tint)
        d["saturation"] = self.saturation
        d["blur"] = self.blur
        d["flip_y"] = self.flip_y
        d["rotation"] = self.rotation.to_list()
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Skybox:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.material_path = data.get("material_path", "core/shaders/Skybox.shader")
        c.skybox_path = data.get("skybox_path", "")
        c.show_background = data.get("show_background", True)
        c.affect_environment = data.get("affect_environment", True)
        c.exposure = data.get("exposure", 0.0)
        c.intensity = data.get("intensity", 1.0)
        c.tint = data.get("tint", [1.0, 1.0, 1.0])
        c.saturation = data.get("saturation", 1.0)
        c.blur = data.get("blur", 0.0)
        c.flip_y = data.get("flip_y", False)
        c.rotation = Vec3(*data.get("rotation", [0.0, 0.0, 0.0]))
        return c
