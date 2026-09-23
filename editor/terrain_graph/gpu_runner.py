# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Dict
from core.foundation.logger import Logger

_ctx: Optional[moderngl.Context] = None
_program: Optional[moderngl.ComputeShader] = None
_buf: Optional[moderngl.Buffer] = None
_last_res: int = 0
_last_source: str = ""

_preview_programs: dict = {}
_preview_order: list = []
_preview_buffers: dict = {}
_preview_cache_max = 24


def _ensure_ctx() -> bool:
    global _ctx
    if _ctx is not None:
        return True
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
        if eng is not None:
            vp = getattr(eng, "viewport", None)
            if vp is not None:
                renderer = getattr(vp, "renderer", None)
                if renderer is not None and getattr(renderer, "_ctx", None) is not None:
                    _ctx = renderer._ctx
                    try:
                        _ctx.pixel_alignment = 1
                    except Exception:
                        pass
                    return True
    except Exception:
        pass
    try:
        _ctx = moderngl.create_standalone_context(require=430)
        _ctx.pixel_alignment = 1
        return True
    except Exception as e:
        Logger.error(f"TerrainNodeGPU: cannot create GL context: {e}", e)
        return False


def run_shader(source: str, resolution: int, uniforms: Optional[Dict[str, float]] = None) -> Optional[np.ndarray]:
    global _program, _buf, _last_res, _last_source

    if not _ensure_ctx():
        return None

    resolution = max(16, min(2048, resolution))
    resolution = (resolution // 16) * 16
    if resolution < 16:
        resolution = 16

    if source != _last_source:
        if _program is not None:
            try:
                _program.release()
            except Exception:
                pass
            _program = None
        try:
            _program = _ctx.compute_shader(source)
            _last_source = source
        except Exception as e:
            Logger.error(f"TerrainNodeGPU: shader compile error: {e}", e)
            _program = None
            return None

    if _program is None:
        return None

    n = resolution * resolution
    if _buf is None or _last_res != resolution:
        if _buf is not None:
            try:
                _buf.release()
            except Exception:
                pass
        _buf = _ctx.buffer(reserve=n * 4)
        _last_res = resolution

    _buf.bind_to_storage_buffer(0)

    try:
        _program["u_resolution"].value = int(resolution)
    except Exception as e:
        Logger.error(f"TerrainNodeGPU: failed to set u_resolution: {e}", e)

    if uniforms:
        for name, value in uniforms.items():
            try:
                if isinstance(value, str):
                    value = float(value)
                _program[name].value = value
            except Exception as e:
                Logger.error(f"TerrainNodeGPU: failed to set uniform '{name}'={value!r}: {e}", e)

    groups = (resolution + 15) // 16
    _program.run(groups, groups, 1)
    _ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)

    raw = _buf.read()
    return np.frombuffer(raw, dtype=np.float32).reshape(resolution, resolution).copy()


def run_preview_shader(source: str, resolution: int, uniforms: Optional[Dict[str, float]] = None) -> Optional[np.ndarray]:
    if not _ensure_ctx():
        return None
    resolution = max(16, min(64, resolution))
    resolution = (resolution // 16) * 16
    if resolution < 16:
        resolution = 16
    prog = _preview_programs.get(source)
    if prog is None:
        try:
            prog = _ctx.compute_shader(source)
        except Exception as e:
            Logger.warning(f"TerrainNodeGPU: preview compile error: {e}", e)
            return None
        _preview_programs[source] = prog
        _preview_order.append(source)
        while len(_preview_order) > _preview_cache_max:
            old = _preview_order.pop(0)
            op = _preview_programs.pop(old, None)
            if op is not None:
                try:
                    op.release()
                except Exception:
                    pass
    buf = _preview_buffers.get(resolution)
    if buf is None:
        try:
            buf = _ctx.buffer(reserve=resolution * resolution * 4)
        except Exception:
            return None
        _preview_buffers[resolution] = buf
    buf.bind_to_storage_buffer(0)
    try:
        prog["u_resolution"].value = int(resolution)
    except Exception:
        pass
    if uniforms:
        for name, value in uniforms.items():
            try:
                if isinstance(value, str):
                    value = float(value)
                prog[name].value = value
            except Exception:
                pass
    groups = (resolution + 15) // 16
    prog.run(groups, groups, 1)
    _ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)
    raw = buf.read()
    return np.frombuffer(raw, dtype=np.float32).reshape(resolution, resolution).copy()


def release():
    global _ctx, _program, _buf, _last_res, _last_source
    if _buf is not None:
        try:
            _buf.release()
        except Exception:
            pass
        _buf = None
    for _k, _p in list(_preview_programs.items()):
        try:
            _p.release()
        except Exception:
            pass
    _preview_programs.clear()
    _preview_order.clear()
    for _k, _b in list(_preview_buffers.items()):
        try:
            _b.release()
        except Exception:
            pass
    _preview_buffers.clear()
    if _program is not None:
        try:
            _program.release()
        except Exception:
            pass
        _program = None
    _ctx = None
    _last_res = 0
    _last_source = ""


def clear_cache():
    global _program, _last_source
    if _program is not None:
        try:
            _program.release()
        except Exception:
            pass
        _program = None
    _last_source = ""
