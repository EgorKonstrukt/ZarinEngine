from __future__ import annotations
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import threading

_DIRECTIVES = {
    "boundscheck": False,
    "wraparound": False,
    "cdivision": True,
    "nonecheck": False,
    "initializedcheck": False,
}

_SKIP_DIRS = frozenset([
    "libs",
    "__pycache__",
    "build",
    "dist",
    ".git",
    ".hg",
    ".svn",
    "tests",
    "test",
    "docs",
    "examples",
    "assets",
])

_BUILDING = set()
_DONE = set()
_LOCK = threading.Lock()


def _suffix():
    try:
        suffixes = importlib.machinery.EXTENSION_SUFFIXES
        if suffixes:
            return suffixes[0]
    except Exception:
        pass
    if os.name == "nt":
        return ".pyd"
    return ".so"


def _target_for(pyx_path):
    parent = os.path.dirname(pyx_path)
    stem = os.path.splitext(os.path.basename(pyx_path))[0]
    try:
        for entry in os.listdir(parent):
            if entry.startswith(stem + ".") and (entry.endswith(".pyd") or entry.endswith(".so")):
                return os.path.join(parent, entry)
    except Exception:
        pass
    return os.path.join(parent, stem + _suffix())


def is_up_to_date(pyx_path):
    try:
        if not os.path.isfile(pyx_path):
            return False
        target = _target_for(pyx_path)
        if not os.path.isfile(target):
            return False
        return os.path.getmtime(target) >= os.path.getmtime(pyx_path)
    except Exception:
        return False


def find_pyx_files(plugin_dir):
    found = []
    try:
        for root, dirs, files in os.walk(plugin_dir):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
            for name in sorted(files):
                if name.endswith(".pyx") and not name.startswith("."):
                    found.append(os.path.join(root, name))
    except Exception:
        pass
    return found


def _setup_code(module_name, pyx_base, directives):
    return (
        "import sys\n"
        "sys.argv = [" + repr("setup.py") + ", " + repr("build_ext") + ", " + repr("--inplace") + "]\n"
        "import numpy\n"
        "from Cython.Build import cythonize\n"
        "from setuptools import Extension, setup\n"
        "ext = Extension(" + repr(module_name) + ", [" + repr(pyx_base) + "], include_dirs=[numpy.get_include()], define_macros=[(" + repr("NPY_NO_DEPRECATED_API") + ", " + repr("NPY_1_7_API_VERSION") + ")])\n"
        "setup(name=" + repr("zarin-plugin-cython") + ", ext_modules=cythonize([ext], language_level=3, compiler_directives=" + repr(dict(directives)) + "), script_args=[" + repr("build_ext") + ", " + repr("--inplace") + "])\n"
    )


def build_file(pyx_path, timeout=300):
    try:
        if is_up_to_date(pyx_path):
            return True
        parent = os.path.dirname(os.path.abspath(pyx_path))
        base = os.path.basename(pyx_path)
        stem = os.path.splitext(base)[0]
        try:
            import numpy
        except Exception:
            return False
        try:
            import Cython
        except Exception:
            return False
        code = _setup_code(stem, base, _DIRECTIVES)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return False
        return is_up_to_date(pyx_path)
    except Exception:
        return False


def _build_list_and_release(anchor, pyx_files, timeout):
    try:
        per = timeout // max(1, len(pyx_files))
        if per < 60:
            per = 60
        for pyx in pyx_files:
            try:
                build_file(pyx, timeout=per)
            except Exception:
                pass
    finally:
        with _LOCK:
            _BUILDING.discard(anchor)
            _DONE.add(anchor)


def ensure_extensions(plugin_dir, background=False, timeout=600):
    try:
        anchor = os.path.abspath(plugin_dir or "")
    except Exception:
        return False
    try:
        if not anchor or not os.path.isdir(anchor):
            return False
        pyx_files = find_pyx_files(anchor)
        if not pyx_files:
            return True
        pending = [p for p in pyx_files if not is_up_to_date(p)]
        if not pending:
            return True
        if background:
            with _LOCK:
                if anchor in _BUILDING or anchor in _DONE:
                    return True
                _BUILDING.add(anchor)
            worker = threading.Thread(
                target=_build_list_and_release,
                args=(anchor, pending, timeout),
                daemon=True,
            )
            worker.start()
            return True
        with _LOCK:
            if anchor in _BUILDING:
                return False
            _BUILDING.add(anchor)
        try:
            per = timeout // max(1, len(pending))
            if per < 60:
                per = 60
            ok = True
            for pyx in pending:
                if not build_file(pyx, timeout=per):
                    ok = False
            return ok
        finally:
            with _LOCK:
                _BUILDING.discard(anchor)
                _DONE.add(anchor)
    except Exception:
        return False


def import_extension(package, module_name, fallback_dir=""):
    try:
        if package:
            return importlib.import_module("." + module_name, package)
        return importlib.import_module(module_name)
    except Exception:
        pass
    try:
        if fallback_dir and os.path.isdir(fallback_dir):
            for entry in os.listdir(fallback_dir):
                if entry.startswith(module_name + ".") and (entry.endswith(".pyd") or entry.endswith(".so")):
                    path = os.path.join(fallback_dir, entry)
                    qualname = (package + "." + module_name) if package else module_name
                    loader = importlib.machinery.ExtensionFileLoader(qualname, path)
                    spec = importlib.machinery.ModuleSpec(qualname, loader, origin=path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[qualname] = module
                    loader.exec_module(module)
                    return module
    except Exception:
        pass
    return None
