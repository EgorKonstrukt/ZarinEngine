# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

import moderngl
import numpy as np

from core.assets.matp import Material, MaterialLibrary
from core.assets.texture_import_settings import TextureImportSettings
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.foundation.progress import task_complete, task_set_detail, task_start

from core.renderer.mats.cache import MaterialCacheMixin
from core.renderer.mats.props import MaterialPropsMixin
from core.renderer.mats.shader import MaterialShaderMixin

class MaterialManager(MaterialCacheMixin, MaterialShaderMixin, MaterialPropsMixin):

    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._material_cache: dict[str, Material] = {}
        self._missing_warned: set[str] = set()
        self._prog_uniform_names: dict[int, frozenset] = {}
        self._prog_tex_active_names: dict[int, dict] = {}
        self._texture_cache: dict[str, Any] = {}
        self._tex_alpha_cache: dict[str, tuple] = {}
        self._tex_wrap_cache: dict[str, bool] = {}
        self._tex_path_cache: dict[str, str] = {}
        self._transparency_cache: dict[tuple, bool] = {}
        self._pending_texture_queue: list = []
        try:
            self._async_lock = threading.Lock()
        except Exception:
            self._async_lock = None
        self._tex_mtime_checked: dict[str, float] = {}
        self._tex_inflight: set[str] = set()
        self._tex_missing: dict[str, float] = {}
        self._transmission_bg = None
        self._default_white = ctx.texture((1, 1), 4, b'\xff\xff\xff\xff')

    def set_async_lock(self, lock):
        self._async_lock = lock

    def load_material(self, path: str) -> Optional[Material]:
        if not path:
            return None
        cached = self._material_cache.get(path)
        if cached is not None:
            return cached
        eng = Engine.instance()
        root = eng.project_root if eng and eng.project_root else os.getcwd()
        abs_path = self._resolve_material_path(path, root)
        if not os.path.exists(abs_path):
            if os.path.splitext(os.path.basename(path))[0] == "ProBuilderPrototype":
                synth = self._synth_prototype_material(path)
                if synth is not None:
                    return synth
            if abs_path not in self._missing_warned:
                self._missing_warned.add(abs_path)
                Logger.warning(f"Material file not found: '{path}', using default")
            return None
        self._missing_warned.discard(abs_path)
        lib_mat = MaterialLibrary._materials.get(abs_path)
        if lib_mat is not None:
            self._material_cache[path] = lib_mat
            return lib_mat
        m = Material.load(abs_path, root)
        if m:
            self._material_cache[path] = m
        return m

    def _synth_prototype_material(self, path: str) -> Optional[Material]:
        try:
            eng_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tex = os.path.join(eng_root, "assets", "textures", "prototype_texture.png")
            if not os.path.exists(tex):
                tex = os.path.join(eng_root, "prototype_texture.png")
            m = Material("ProBuilderPrototype")
            m.shader_path = "default"
            m.properties = {
                "_BaseColor": [1.0, 1.0, 1.0, 1.0],
                "_Metallic": 0.0,
                "_Smoothness": 0.5,
                "_EmissionColor": [0.0, 0.0, 0.0, 0.0],
                "_EmissionIntensity": 0.0,
            }
            if os.path.exists(tex):
                m.properties["albedo_texture"] = tex
            self._material_cache[path] = m
            return m
        except Exception:
            return None

    def _resolve_material_path(self, path: str, root: str) -> str:
        if os.path.isabs(path):
            return os.path.normpath(path)
        if os.path.exists(path):
            return os.path.normpath(os.path.abspath(path))
        if len(path) > 1 and path[1] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c
            return os.path.normpath(os.path.join(root, path))
        return os.path.normpath(os.path.join(root, path))

    def clear_caches(self):
        for _mtime, tex in self._texture_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        self._texture_cache.clear()
        self._material_cache.clear()
        self._tex_alpha_cache.clear()
        self._tex_wrap_cache.clear()
        self._tex_path_cache.clear()
        self._transparency_cache.clear()

    def release(self):
        for _mtime, tex in self._texture_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        try:
            self._default_white.release()
        except Exception:
            pass

