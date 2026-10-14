# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import hashlib
import os
import shutil
import sys
import tempfile
CACHE_SUBDIR = os.path.join("cache", "cython")
_BUILD_SCHEME = "zarin-cy-v1"
_KEEP_VERSIONS = 3
_warned: set[str] = set()
_setup_flags: dict = {"compiler": "system", "build_root": ""}
def _warn_once(key: str, message: str):
    if key in _warned:
        return
    _warned.add(key)
    try:
        from core.foundation.logger import Logger
        Logger.warning(message)
    except Exception:
        pass
def project_root() -> str:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
    except Exception:
        eng = None
    root = getattr(eng, "project_root", "") if eng is not None else ""
    return root or ""
def build_root(explicit: str | None = None) -> str:
    if explicit:
        root = explicit
    else:
        proot = project_root()
        if proot:
            root = os.path.join(proot, CACHE_SUBDIR)
        else:
            root = os.path.join(tempfile.gettempdir(), "zarin_cython")
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root
def _build_subdir(build_root_path: str, script_dir: str) -> str:
    digest = hashlib.sha256(os.path.abspath(script_dir).encode("utf-8")).hexdigest()[:16]
    sub = os.path.join(build_root_path, "build", digest)
    try:
        os.makedirs(sub, exist_ok=True)
    except Exception:
        pass
    return sub
def _source_fingerprint(pyx_path: str) -> str:
    try:
        import Cython
        cy_version = getattr(Cython, "__version__", "?")
    except Exception:
        cy_version = "?"
    try:
        with open(pyx_path, "rb") as f:
            content = f.read()
    except Exception:
        content = b""
    compiler = str(_setup_flags.get("compiler", "system"))
    h = hashlib.sha256()
    h.update(_BUILD_SCHEME.encode("utf-8"))
    h.update(b"\x00" + cy_version.encode("utf-8"))
    h.update(b"\x00" + compiler.encode("utf-8"))
    h.update(b"\x00" + content)
    try:
        base, _ext = os.path.splitext(pyx_path)
        if os.path.isfile(base + ".pxd"):
            with open(base + ".pxd", "rb") as f:
                h.update(b"\x00" + f.read())
    except Exception:
        pass
    return h.hexdigest()[:12]
def _find_built_pyd(version_dir: str, modname: str) -> str:
    try:
        for root, _dirs, files in os.walk(version_dir):
            for fn in files:
                if not fn.endswith((".pyd", ".so")):
                    continue
                stem = fn.split(".")[0]
                if stem == modname:
                    return os.path.join(root, fn)
    except Exception:
        pass
    return ""
def _prune_versions(base_dir: str, keep: int = _KEEP_VERSIONS):
    try:
        entries = []
        for name in os.listdir(base_dir):
            full = os.path.join(base_dir, name)
            if os.path.isdir(full):
                try:
                    entries.append((os.path.getmtime(full), full))
                except Exception:
                    continue
        entries.sort()
        for _mtime, full in entries[:-max(keep, 1)]:
            try:
                shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass
def _numpy_include() -> list:
    try:
        import numpy
        return [numpy.get_include()]
    except Exception:
        return []
def _activate_toolchain() -> str:
    if sys.platform != "win32":
        for cc in ("cc", "gcc", "clang"):
            if shutil.which(cc):
                return "system"
        return "none"
    try:
        from tools.mingwpm import is_available, activate
    except Exception:
        return "system"
    try:
        if is_available():
            activate()
            return "mingw"
    except Exception:
        pass
    return "system"
def toolchain_status(build_root_path: str | None = None) -> dict:
    try:
        import Cython
        cy_version = getattr(Cython, "__version__", "?")
        has_cython = True
    except Exception:
        cy_version = None
        has_cython = False
    compiler = _setup_flags.get("compiler", "system")
    if compiler == "system" and sys.platform != "win32":
        if not any(shutil.which(cc) for cc in ("cc", "gcc", "clang")):
            compiler = "none"
    return {
        "cython": has_cython,
        "cython_version": cy_version,
        "compiler": compiler,
        "build_root": build_root(build_root_path),
    }
def check_pyx_errors(pyx_path: str) -> list:
    try:
        from Cython.Build import cythonize
        from Cython.Compiler.Errors import CompileError
    except Exception:
        return [f"{pyx_path}:0: 'cython' package not found, cannot validate"]
    tmpd = tempfile.mkdtemp(prefix="zarin_pyx_check_")
    try:
        try:
            cythonize([pyx_path], build_dir=tmpd, language_level=3)
        except CompileError as e:
            return [str(e)]
        except SystemExit as e:
            return [f"{pyx_path}:0: Cython validation failed (exit {e})"]
        except Exception as e:
            return [f"{pyx_path}:0: {type(e).__name__}: {e}"]
        return []
    finally:
        try:
            shutil.rmtree(tmpd, ignore_errors=True)
        except Exception:
            pass
