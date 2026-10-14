# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import importlib.machinery
import importlib.util
import os
import re
import shutil
import sys
from core.components.scripting.cythonp.build import _activate_toolchain
from core.components.scripting.cythonp.build import _build_subdir
from core.components.scripting.cythonp.build import _find_built_pyd
from core.components.scripting.cythonp.build import _numpy_include
from core.components.scripting.cythonp.build import _prune_versions
from core.components.scripting.cythonp.build import _setup_flags
from core.components.scripting.cythonp.build import _source_fingerprint
from core.components.scripting.cythonp.build import _warn_once
from core.components.scripting.cythonp.build import build_root
CYTHON_TEMPLATE = '''\x23 cython: language_level=3
\x23 cython: boundscheck=False
\x23 cython: wraparound=False
\x23 cython: cdivision=True
"""MODULENAME.pyx - Cython companion module.

Use it from the plain script in the same folder:

    import MODULENAME

    def on_update(self, dt):
        self.total = MODULENAME.add(self.total, dt)

The engine builds this file automatically on first import and rebuilds it
when it changes (hot-reload works too). No manual build step needed.
"""
import numpy as np
cimport numpy as cnp

cnp.import_array()


cpdef double add(double a, double b):
    return a + b


def moving_average(cnp.ndarray[cnp.float64_t, ndim=1] values):
    cdef Py_ssize_t i, n = values.shape[0]
    cdef double total = 0.0
    for i in range(n):
        total += values[i]
    return total / n if n > 0 else 0.0
'''
_finder = None
class _ZarinPyxLoader(importlib.machinery.ExtensionFileLoader):
    def __init__(self, pyx_path: str, build_root_path: str, setup_args: dict):
        modname = os.path.splitext(os.path.basename(pyx_path))[0]
        super().__init__(modname, pyx_path)
        self._pyx_path = pyx_path
        self._build_root_path = build_root_path
        self._setup_args = dict(setup_args)
    def create_module(self, spec):
        try:
            from pyximport.pyxbuild import pyx_to_dll
        except Exception as e:
            raise ImportError(f"Zarin: Cython support needs the 'pyximport' package: {e}") from e
        base = _build_subdir(self._build_root_path, os.path.dirname(self._pyx_path))
        modname = os.path.splitext(os.path.basename(self._pyx_path))[0]
        fingerprint = _source_fingerprint(self._pyx_path)
        version_dir = os.path.join(base, fingerprint)
        so_path = _find_built_pyd(version_dir, modname)
        if not so_path:
            try:
                os.makedirs(version_dir, exist_ok=True)
            except Exception:
                pass
            try:
                try:
                    import Cython.Build.Dependencies as _deps
                    _deps._dep_tree = None
                except Exception:
                    pass
                from distutils.extension import Extension
                ext = Extension(
                    name=spec.name,
                    sources=[self._pyx_path],
                    include_dirs=_numpy_include(),
                )
                so_path = pyx_to_dll(
                    self._pyx_path,
                    ext,
                    pyxbuild_dir=version_dir,
                    setup_args=dict(self._setup_args),
                )
            except BaseException as e:
                try:
                    shutil.rmtree(version_dir, ignore_errors=True)
                except Exception:
                    pass
                raise ImportError(
                    f"Zarin: failed building Cython module '{spec.name}' "
                    f"from {self._pyx_path}: {e}"
                ) from e
            _prune_versions(base)
            so_path = _find_built_pyd(version_dir, modname) or so_path
            try:
                gen_c = os.path.join(
                    os.path.dirname(self._pyx_path), modname + ".c"
                )
                if os.path.isfile(gen_c):
                    os.remove(gen_c)
            except Exception:
                pass
        spec.origin = so_path
        self.path = so_path
        return super().create_module(spec)
class _ZarinPyxFinder:
    def __init__(self):
        self.dirs: list[str] = []
    def add_dir(self, script_dir: str):
        norm = os.path.normcase(os.path.abspath(script_dir))
        existing = [os.path.normcase(os.path.abspath(d)) for d in self.dirs]
        if norm not in existing:
            self.dirs.insert(0, norm)
    def find_spec(self, fullname, path=None, target=None):
        if "." in fullname:
            return None
        if fullname in sys.builtin_module_names:
            return None
        try:
            if fullname in sys.stdlib_module_names:
                return None
        except Exception:
            pass
        for d in self.dirs:
            cand = os.path.join(d, fullname + ".pyx")
            try:
                is_file = os.path.isfile(cand)
            except Exception:
                continue
            if is_file:
                return importlib.util.spec_from_file_location(
                    fullname,
                    cand,
                    loader=_ZarinPyxLoader(
                        cand,
                        _setup_flags.get("build_root", "") or build_root(),
                        _setup_flags.get("setup_args", {}),
                    ),
                )
        return None
def _get_finder() -> _ZarinPyxFinder:
    global _finder
    if _finder is None:
        _finder = _ZarinPyxFinder()
        sys.meta_path.insert(0, _finder)
    elif _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    return _finder
def ensure_search_path(script_dir: str) -> str:
    d = os.path.abspath(script_dir)
    if d not in sys.path:
        sys.path.insert(0, d)
    try:
        _get_finder().add_dir(d)
    except Exception:
        pass
    return d
def ensure_builder(build_root_path: str | None = None) -> bool:
    try:
        import Cython
    except Exception:
        _warn_once("no-cython", "Zarin: 'cython' package not found, companion .pyx modules will not build")
        return False
    root = build_root(build_root_path)
    compiler = _activate_toolchain()
    setup_args: dict = {}
    inc = _numpy_include()
    if inc:
        setup_args["include_dirs"] = inc
    if sys.platform == "win32" and compiler == "mingw":
        setup_args["options"] = {"build_ext": {"compiler": "mingw32"}}
    _setup_flags["compiler"] = compiler
    _setup_flags["build_root"] = root
    _setup_flags["setup_args"] = setup_args
    _get_finder()
    return True
def prepare_script_imports(script_py_path: str, build_root_path: str | None = None) -> str:
    script_dir = ensure_search_path(os.path.dirname(os.path.abspath(script_py_path)))
    try:
        if not ensure_builder(build_root_path):
            _warn_once(
                "no-builder",
                "Zarin: Cython auto-build unavailable, 'import <name>' of a .pyx companion will fail",
            )
    except Exception as e:
        _warn_once("builder-failed", f"Zarin: Cython auto-build setup failed: {e}")
    return script_dir
def _is_extension_path(origin: str) -> bool:
    base = re.sub(r"\.reload\d+$", "", origin or "")
    return os.path.splitext(base)[1].lower() in (".pyd", ".so")
def find_companion_pyx(script_dir: str) -> list[str]:
    try:
        names = sorted(
            f for f in os.listdir(script_dir)
            if f.endswith(".pyx") and os.path.isfile(os.path.join(script_dir, f))
        )
    except Exception:
        return []
    return names
def snapshot_ext_modules(script_dir: str) -> dict:
    out: dict = {}
    try:
        items = list(sys.modules.items())
    except Exception:
        return out
    for name, mod in items:
        if "." in name:
            continue
        try:
            origin = getattr(getattr(mod, "__spec__", None), "origin", "") or getattr(mod, "__file__", "")
            if not origin:
                continue
            if not _is_extension_path(origin):
                continue
            cand = os.path.join(script_dir, name + ".pyx")
            if not os.path.isfile(cand):
                continue
            out[name] = (cand, os.path.getmtime(cand))
        except Exception:
            continue
    return out
def ext_sources_changed(ext_sources: dict) -> bool:
    for _name, (src, mtime) in (ext_sources or {}).items():
        try:
            cur = os.path.getmtime(src)
        except Exception:
            return True
        if cur != mtime:
            return True
    return False
def unload_ext_modules(names) -> None:
    for n in list(names or []):
        try:
            sys.modules.pop(n, None)
        except Exception:
            pass
