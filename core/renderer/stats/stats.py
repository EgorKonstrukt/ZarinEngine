# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import gc as _gc
import subprocess
import threading
import time


_RAM_CACHE_VAL = 0.0
_RAM_CACHE_T = 0.0


_expensive = {}
_expensive_t = 0.0
_vram = (0.0, 0.0)
_vram_t = 0.0
_vram_busy = False
_scene_counts_cache: dict = {}
_gl_info_cache = ["", "", 0.0]


def _fmt_count(n) -> str:
    try:
        n = int(n)
    except Exception:
        n = 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_bytes(b) -> str:
    try:
        b = int(b)
    except Exception:
        b = 0
    if b >= 1 << 20:
        return f"{b / (1 << 20):.1f}MB"
    if b >= 1 << 10:
        return f"{b / (1 << 10):.1f}KB"
    return f"{b}B"


def _fmt_vram_mb(mb) -> str:
    try:
        mb = float(mb)
    except Exception:
        return "0MB"
    if mb >= 2048:
        return f"{mb / 1024.0:.1f}GB"
    return f"{mb:.0f}MB"


def _short_gpu(name) -> str:
    name = str(name).split("/")[0].strip()
    for prefix in ("NVIDIA GeForce ", "AMD Radeon ", "Intel "):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name or "?"


def _get_ram_mb() -> float:
    global _RAM_CACHE_VAL, _RAM_CACHE_T
    now = time.time()
    if now - _RAM_CACHE_T < 1.0 and _RAM_CACHE_VAL > 0:
        return _RAM_CACHE_VAL
    try:
        import psutil as _psutil
        v = _psutil.Process().memory_info().rss / (1024 * 1024)
        _RAM_CACHE_VAL = v
        _RAM_CACHE_T = now
        return v
    except Exception:
        pass
    try:
        import resource as _resource
        v = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss / 1024
        _RAM_CACHE_VAL = v
        _RAM_CACHE_T = now
        return v
    except Exception:
        pass
    try:
        import ctypes as _ctypes

        class _PMC(_ctypes.Structure):
            _fields_ = [
                ('cb', _ctypes.c_uint32),
                ('PageFaultCount', _ctypes.c_uint32),
                ('PeakWorkingSetSize', _ctypes.c_size_t),
                ('WorkingSetSize', _ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', _ctypes.c_size_t),
                ('QuotaPagedPoolUsage', _ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', _ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', _ctypes.c_size_t),
                ('PagefileUsage', _ctypes.c_size_t),
                ('PeakPagefileUsage', _ctypes.c_size_t),
            ]

        _psapi = _ctypes.windll.psapi
        _psapi.GetProcessMemoryInfo.argtypes = [_ctypes.c_void_p, _ctypes.c_void_p, _ctypes.c_uint32]
        _psapi.GetProcessMemoryInfo.restype = _ctypes.c_int
        pmc = _PMC()
        pmc.cb = _ctypes.sizeof(_PMC)
        h = _ctypes.c_void_p(-1)
        if _psapi.GetProcessMemoryInfo(h, _ctypes.byref(pmc), _ctypes.sizeof(pmc)):
            v = pmc.WorkingSetSize / (1024 * 1024)
            _RAM_CACHE_VAL = v
            _RAM_CACHE_T = now
            return v
    except Exception:
        pass
    return _RAM_CACHE_VAL if _RAM_CACHE_VAL else 0.0


def _query_vram_mb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        line = out.stdout.strip().splitlines()[0]
        used_s, total_s = line.split(",")
        used = float(used_s.strip().split()[0])
        total = float(total_s.strip().split()[0])
        if total > 0:
            return used, total
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=2,
        )
        used = total = 0.0
        for ln in out.stdout.splitlines():
            ln = ln.strip()
            if "Used memory" in ln:
                used = float(ln.split(":")[1].strip().split()[0])
            elif "Total memory" in ln:
                total = float(ln.split(":")[1].strip().split()[0])
        if total > 0:
            return used, total
    except Exception:
        pass
    return 0.0, 0.0


def _refresh_vram_async():
    global _vram_busy
    if _vram_busy:
        return
    _vram_busy = True

    def worker():
        global _vram, _vram_t, _vram_busy
        try:
            _vram = _query_vram_mb()
        except Exception:
            pass
        _vram_t = time.time()
        _vram_busy = False

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        _vram_busy = False


def collect_expensive_stats() -> dict:
    global _expensive_t
    now = time.time()
    if _expensive and (now - _expensive_t) < 10.0:
        return _expensive
    _expensive_t = now
    if (now - _vram_t) > 10.0:
        _refresh_vram_async()
    vram_used, vram_total = _vram
    try:
        gc0, gc1, gc2 = _gc.get_count()
    except Exception:
        gc0 = gc1 = gc2 = 0
    dsp_load = 0.0
    active_sounds = 0
    total_sounds = 0
    try:
        from core.audio.sys import AudioSourceManager
        mgr = AudioSourceManager.instance()
        if mgr:
            dsp_load = mgr.get_dsp_load()
            active_sounds = mgr.get_active_sound_count()
            total_sounds = mgr.get_total_sound_count()
    except Exception:
        pass
    _expensive.update({
        'ram_mb': _get_ram_mb(),
        'vram_used': vram_used,
        'vram_total': vram_total,
        'gc0': gc0, 'gc1': gc1, 'gc2': gc2,
        'dsp_load': dsp_load,
        'active_sounds': active_sounds,
        'total_sounds': total_sounds,
    })
    return _expensive


def collect_render_stats(engine, renderer) -> dict:
    st = {}
    for out_key, attr in (
            ('draw_calls', '_draw_calls'),
            ('triangles', '_triangles_drawn'),
            ('vertices', '_vertices_drawn'),
            ('particles', '_particle_count'),
            ('culled_visible', '_culled_visible'),
            ('culled_total', '_culled_total')):
        st[out_key] = getattr(renderer, attr, 0) or 0
    batcher = getattr(renderer, '_batcher', None)
    st['batches'] = batcher.batches if batcher is not None else 0
    st['instanced'] = batcher.instanced if batcher is not None else 0
    gizmo = getattr(renderer, '_gizmo', None)
    gizmo_keys = ('gizmo_draws', 'gizmo_lines', 'gizmo_instances', 'gizmo_mesh_verts',
                  'gizmo_upload_bytes', 'gizmo_upload_full', 'gizmo_upload_partial')
    if gizmo is not None:
        for gk, attr in zip(gizmo_keys, ('_stat_draws', '_stat_lines', '_stat_instances',
                                         '_stat_mesh_verts', '_stat_upload_bytes',
                                         '_stat_upload_full', '_stat_upload_partial')):
            st[gk] = getattr(gizmo, attr, 0) or 0
    else:
        for gk in gizmo_keys:
            st[gk] = 0
    st['tps'] = getattr(engine, 'tps', 0.0) or 0.0
    try:
        _dts = getattr(engine, '_tick_dts', None)
        st['tick_dts'] = list(_dts) if _dts else []
    except Exception:
        st['tick_dts'] = []
    st['time_scale'] = getattr(engine, 'time_scale', 1.0) or 1.0
    st['entities'] = 0
    scene = getattr(engine, 'scene', None)
    if scene is not None:
        try:
            _ents = getattr(scene, '_entities', None)
            if _ents is not None:
                st['entities'] = len(_ents)
            else:
                st['entities'] = len(scene.get_all_entities())
        except Exception:
            pass
    ctx = getattr(renderer, '_ctx', None)
    st['gl_renderer'] = _gl_info_cache[0]
    st['gl_version'] = _gl_info_cache[1]
    if ctx is not None and (_gl_info_cache[2] == 0.0 or (time.time() - _gl_info_cache[2]) > 10.0):
        try:
            info = getattr(ctx, 'info', None) or {}
            _gl_info_cache[0] = str(info.get('GL_RENDERER', ''))
            _gl_info_cache[1] = str(info.get('GL_VERSION', ''))
            _gl_info_cache[2] = time.time()
            st['gl_renderer'] = _gl_info_cache[0]
            st['gl_version'] = _gl_info_cache[1]
        except Exception:
            pass
    st['rt_rays_per_frame'] = getattr(renderer, '_rt_rays_per_frame', 0)
    st['opaque_draws'] = getattr(renderer, '_opaque_draws', 0) or 0
    st['trans_draws'] = getattr(renderer, '_trans_draws', 0) or 0
    st['render_scale'] = float(getattr(renderer, '_render_scale', 1.0) or 1.0)
    st['exposure'] = float(getattr(renderer, '_exposure', 0.0) or 0.0)
    st['frame_no'] = int(getattr(renderer, '_render_count', 0) or 0)
    st['fixed_steps'] = int(getattr(engine, '_fixed_steps_last', 0) or 0)
    st['fixed_accum_ms'] = float(getattr(engine, '_fixed_accum', 0.0) or 0.0) * 1000.0
    st['bodies'] = 0
    try:
        _pm = getattr(engine, '_plugin_manager', None)
        _plugins = _pm.get_all() if _pm is not None else []
        for _pp in _plugins:
            _pscn = getattr(_pp, 'physics_scene', None)
            if _pscn is None:
                continue
            try:
                _solver = getattr(_pscn, '_solver', None)
                if _solver is not None:
                    st['bodies'] = int(_solver.body_count())
                else:
                    st['bodies'] = len(getattr(_pscn, '_entity_to_body', {}) or {})
            except Exception:
                try:
                    st['bodies'] = len(getattr(_pscn, '_entity_to_body', {}) or {})
                except Exception:
                    st['bodies'] = 0
            break
    except Exception:
        st['bodies'] = 0
    st['shadow_pt'] = 0
    st['shadow_spot'] = 0
    try:
        _sh = getattr(renderer, '_shadows', None)
        if _sh is not None:
            st['shadow_pt'] = int(getattr(_sh, '_point_shadow_count', 0) or 0)
            st['shadow_spot'] = int(getattr(_sh, '_spot_shadow_count', 0) or 0)
    except Exception:
        pass
    st['shadow_casc'] = int(getattr(renderer, '_cascade_count', 0) or 0)
    st['shadow_res'] = int(getattr(renderer, '_shadow_resolution', 0) or 0)
    st['shadow_dist'] = float(getattr(renderer, '_shadow_distance', 0.0) or 0.0)
    st['mesh_pending'] = 0
    st['mesh_built'] = 0
    try:
        _ml = getattr(renderer, '_mesh_loader', None)
        if _ml is not None:
            st['mesh_pending'] = int(getattr(_ml, '_pending_async_loads', 0) or 0)
            st['mesh_built'] = int(getattr(_ml, '_built_count', 0) or 0)
    except Exception:
        pass
    st['postfx'] = 0
    try:
        from core.components.rendering.postfx.graphics_effect import GraphicsEffect
        _nfx = 0
        for _fx in list(GraphicsEffect._registry):
            try:
                if _fx.enabled and _fx.entity is not None and _fx.entity.active:
                    _nfx += 1
            except Exception:
                continue
        st['postfx'] = _nfx
    except Exception:
        pass
    st['components'] = 0
    try:
        if scene is not None:
            try:
                _rv = scene._render_version
            except Exception:
                _rv = None
            try:
                _ents_d = getattr(scene, '_entities', None)
                _n_ents = len(_ents_d) if _ents_d is not None else -1
            except Exception:
                _ents_d = None
                _n_ents = -1
            _cc_key = (id(scene), _rv, _n_ents)
            _cc_hit = _scene_counts_cache.get(_cc_key) if _rv is not None else None
            if _cc_hit is not None:
                st['entities'] = _cc_hit[0]
                st['components'] = _cc_hit[1]
            else:
                try:
                    _ents = scene.get_all_entities()
                except Exception:
                    _ents = getattr(scene, '_entities', None) or []
                _nc = 0
                _iter = _ents.values() if isinstance(_ents, dict) else _ents
                for _e in _iter:
                    try:
                        _nc += len(getattr(_e, '_components', {}) or {})
                    except Exception:
                        continue
                st['components'] = _nc
                if _rv is not None:
                    try:
                        if len(_scene_counts_cache) > 8:
                            _scene_counts_cache.clear()
                        _scene_counts_cache[_cc_key] = (st['entities'], _nc)
                    except Exception:
                        pass
    except Exception:
        pass
    st['shader_progs'] = 0
    st['cached_tex'] = 0
    try:
        _sm = getattr(renderer, '_shaders', None)
        if _sm is not None:
            st['shader_progs'] = len(getattr(_sm, '_cache', {}) or {})
    except Exception:
        pass
    try:
        _nt = 0
        for _holder in (getattr(renderer, '_icons', None), getattr(renderer, '_particles', None)):
            if _holder is not None:
                try:
                    _nt += len(getattr(_holder, '_textures', {}) or {})
                except Exception:
                    continue
        st['cached_tex'] = _nt
    except Exception:
        pass
    st.update(collect_expensive_stats())
    try:
        flat = None
        prof = getattr(engine, '_profiler', None)
        if prof is not None and getattr(prof, 'enabled', False):
            cf = getattr(prof, '_current_frame', None)
            if cf is not None:
                flat = getattr(cf, 'flat_data', None)
            if not flat:
                frames = getattr(prof, 'frames', None)
                if frames:
                    flat = getattr(frames[-1], 'flat_data', None)
        hot: list = []
        if flat:
            items = sorted(((k, v) for k, v in flat.items() if isinstance(v, (int, float))),
                           key=lambda kv: -kv[1])[:3]
            hot = [(str(k), float(v)) for k, v in items if float(v) > 0.01]
        st['hot'] = hot
    except Exception:
        st['hot'] = []
    try:
        st['net'] = None
        cm = getattr(engine, 'collab_manager', None)
        if cm is not None and bool(cm.connected):
            peers = getattr(cm, 'peers', {}) or {}
            st['net'] = {
                'host': bool(cm.is_host),
                'peers': len(peers),
                'ping': float(cm.latency_ms()),
            }
    except Exception:
        st['net'] = None
    return st
