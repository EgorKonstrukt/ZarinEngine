# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile
from typing import Optional
from core.foundation.logger import Logger
from core.foundation.plugins.base import _platform_matches, _resolve_zplugin, _zarin_user_dir, current_architecture
from core.foundation.plugins.ui_registry import _read_archive_manifest, _read_package_manifest, _scan_provides, _zplugin_fingerprint


class LoaderMixin:
    def _auto_load_components(self, comp_dir: str, plugin_module_name: Optional[str] = None):
        if not os.path.isdir(comp_dir):
            return
        key = (plugin_module_name or "zplugin").replace(".", "_")
        for fname in sorted(os.listdir(comp_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            base = fname[:-3]
            mod = None
            if plugin_module_name:
                try:
                    mod = importlib.import_module(plugin_module_name + ".components." + base)
                except Exception as e:
                    Logger.warning(f"[Plugin] Could not import component '{base}' from {plugin_module_name}: {e}")
                    mod = None
            if mod is None:
                mod_name = "_plugin_comp_" + key + "_" + base
                fpath = os.path.join(comp_dir, fname)
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, fpath)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                except Exception as e:
                    Logger.error(f"[Plugin] Failed to auto-load component module '{fname}': {e}", e)
                    continue
            registered = []
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and obj.__module__ == mod.__name__:
                    from core.ecs import Component, ComponentRegistry
                    if issubclass(obj, Component):
                        ComponentRegistry.register(obj)
                        registered.append(obj.__name__)
            if registered:
                Logger.info(f"[Plugin] Auto-registered components from {fname}: {', '.join(registered)}")

    def load_from_file(self, path: str):
        try:
            if path.endswith(".zplugin"):
                self.load_zplugin(path)
            elif path.endswith(".py"):
                self._load_python_plugin("_zplugin", path)
            elif path.endswith(".pyd"):
                self._load_python_plugin(os.path.splitext(os.path.basename(path))[0], path)
            elif path.endswith(".dll") or path.endswith(".so"):
                lib = ctypes.CDLL(path)
                get_plugin = lib.get_plugin
                get_plugin.restype = ctypes.py_object
                plugin = get_plugin()
                from core.foundation.plugins.base import PluginBase
                if isinstance(plugin, PluginBase):
                    plugin._native_plugin_path = path
                    self.register(plugin)
                else:
                    Logger.error(f"DLL '{path}' get_plugin() must return PluginBase instance.")
        except Exception as e:
            Logger.error(f"Failed to load plugin from '{path}': {e}", e)

    def load_directory(self, dirpath: str):
        if not os.path.isdir(dirpath):
            return
        zplugins, packages, pyfiles = [], [], []
        for fname in sorted(os.listdir(dirpath)):
            fpath = os.path.join(dirpath, fname)
            if fname.endswith(".zplugin") and not fname.startswith("_"):
                zplugins.append(fpath)
            elif fname.endswith(".py") and not fname.startswith("_"):
                pyfiles.append(fpath)
            elif os.path.isdir(fpath):
                init_path = os.path.join(fpath, "__init__.py")
                if os.path.isfile(init_path):
                    packages.append(fpath)
        planned = []
        for path in zplugins:
            planned.append(("zplugin", path, _read_archive_manifest(path)))
        for d in packages:
            planned.append(("package", d, _read_package_manifest(d)))
        libs = [(k, p, m) for k, p, m in planned if m.get("type") == "library"]
        rest = [(k, p, m) for k, p, m in planned if m.get("type") != "library"]
        for kind, path, manifest in libs:
            self._load_planned_entry(kind, path, manifest)
        for kind, path, manifest in self._topo_plan(rest):
            self._load_planned_entry(kind, path, manifest)
        for path in pyfiles:
            self.load_from_file(path)
        self._drain_pending()

    def _activate_bundled_libs(self, libs_dir: str, deps: list, owner: str = ""):
        if not os.path.isdir(libs_dir):
            return
        lib_paths = [libs_dir]
        for entry in sorted(os.listdir(libs_dir)):
            child = os.path.join(libs_dir, entry)
            if os.path.isdir(child) and os.path.isfile(os.path.join(child, "__init__.py")):
                lib_paths.append(os.path.dirname(child))
            elif (os.path.isfile(child) and (entry.endswith(".pyd") or entry.endswith(".so") or entry.endswith(".dll"))):
                lib_paths.append(os.path.dirname(child))
        for lp in lib_paths:
            if os.path.isdir(lp) and lp not in sys.path:
                sys.path.insert(0, lp)
                Logger.info(f"[zplugin] Bundled library path activated: {lp}")
        if owner:
            for mod in _scan_provides(libs_dir):
                self._record_lib_owner(mod, owner, libs_dir)
        if deps:
            missing = []
            for dep in deps:
                name = dep.split(">=")[0].split("==")[0].split("<")[0].strip()
                try:
                    importlib.import_module(name)
                except Exception:
                    missing.append(dep)
            if missing:
                Logger.warning(f"[zplugin] Bundled library missing dependencies: {missing}")

    def _compile_if_needed(self, payload_dir: str, manifest: dict):
        cython_srcs = manifest.get("cython_modules", [])
        if not cython_srcs:
            return True
        outdir = os.path.join(payload_dir, "_native")
        os.makedirs(outdir, exist_ok=True)
        built = []
        for rel in cython_srcs:
            src = os.path.join(payload_dir, rel)
            if not os.path.isfile(src):
                continue
            base = os.path.splitext(os.path.basename(rel))[0]
            target = os.path.join(outdir, base + ".pyd")
            if os.path.isfile(target) and _platform_matches(manifest.get("architecture", "")):
                built.append(target)
                continue
            if self._compile_cython_module(src, outdir):
                built.append(target)
        if built:
            if outdir not in sys.path:
                sys.path.insert(0, outdir)
        return len(built) == len(cython_srcs)

    def _compile_cython_module(self, src: str, outdir: str) -> bool:
        try:
            import Cython
            from setuptools import Extension, setup
        except ImportError as e:
            Logger.error(f"[zplugin] Cython required for cython_modules but not installed: {e}")
            return False
        try:
            from setuptools.command.build_ext import build_ext
            from Cython.Build import cythonize
        except ImportError as e:
            Logger.error(f"[zplugin] Cython build dependencies missing: {e}")
            return False
        import subprocess
        src_dir = os.path.dirname(src)
        pyx = os.path.basename(src)
        setup_py = os.path.join(outdir, "_cython_build_setup.py")
        try:
            import sys as _sys
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from tools.mingwpm import env_with_mingw as _pm_env_with_mingw
            try:
                _pm_env = _pm_env_with_mingw()
            except Exception:
                _pm_env = None
        except ImportError:
            _pm_env = None
        _is_win = __import__("sys").platform == "win32"
        _use_mingw = _pm_env is not None and _is_win
        _opt = "'-O2'" if _use_mingw else ("'/O2'" if _is_win else "'-O3'")
        script = (
            "from setuptools import setup, Extension\n"
            "from Cython.Build import cythonize\n"
            f"setup(ext_modules=cythonize([Extension('zpl_native', [r'{pyx}'], "
            f"extra_compile_args=[{_opt}])], "
            f"build_dir=r'{outdir}'), options={{'build_ext': {{'build_lib': r'{outdir}'}}}})\n"
        )
        with open(setup_py, "w", encoding="utf-8") as f:
            f.write(script)
        try:
            _cmd = [sys.executable, setup_py, "build_ext", "--inplace"]
            if _use_mingw:
                _cmd.insert(3, "--compiler=mingw32")
            result = subprocess.run(
                _cmd,
                capture_output=True, text=True, cwd=src_dir, env=_pm_env or None,
            )
            if result.returncode == 0:
                for f in os.listdir(outdir):
                    if f.endswith(".pyd"):
                        Logger.info(f"[zplugin] Cython module built: {os.path.join(outdir, f)}")
                        return True
            Logger.error(f"[zplugin] Cython compile failed: {result.stderr[-800:]}")
        except Exception as e:
            Logger.error(f"[zplugin] Cython compile error: {e}")
        return False

    def _extract_zplugin(self, path: str) -> dict:
        ok, reason, manifest = self.verify_zplugin_file(path)
        if not ok:
            Logger.error(f"[zplugin] Rejected '{path}': {reason}")
            self._set_status(str(manifest.get("name", os.path.basename(path))), "blocked", reason)
            return {}
        if reason == "unsigned":
            Logger.warning(f"[zplugin] Loading unsigned package '{path}'")
        name = str(manifest.get("name", "unnamed"))
        version = str(manifest.get("version", "0.0.1"))
        dest = _resolve_zplugin(name, version)
        fingerprint = _zplugin_fingerprint(path)
        cached = self._read_zplugin_cache(dest, fingerprint)
        if cached is not None:
            return cached
        tmp = tempfile.mkdtemp(prefix="zpl_", dir=_zarin_user_dir("tmp"))
        try:
            return self._extract_zplugin_payload(path, manifest, name, tmp, dest, fingerprint)
        except Exception as e:
            Logger.error(f"[zplugin] Extraction failed for '{path}': {e}", e)
            self._set_status(name, "blocked", f"extraction failed: {e}")
            shutil.rmtree(tmp, ignore_errors=True)
            return {}

    def _extract_zplugin_payload(self, path: str, manifest: dict, name: str, tmp: str, dest: str,
                                 fingerprint: dict) -> dict:
        safe_names = set()
        if not _platform_matches(manifest.get("architecture", "any")):
            has_native = False
            with zipfile.ZipFile(path) as zf:
                for n in zf.namelist():
                    if n.endswith(".pyd") or n.endswith(".so") or n.endswith(".dll"):
                        has_native = True
                        break
            if has_native and not manifest.get("cython_modules"):
                Logger.error(
                    f"[zplugin] '{name}' targets {manifest.get('architecture')}, "
                    f"current is {current_architecture()} and no source fallback is available."
                )
                shutil.rmtree(tmp, ignore_errors=True)
                return {}
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                target = os.path.join(tmp, n)
                if os.path.isabs(n) or ".." in os.path.normpath(n):
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise ValueError(f"[zplugin] Unsafe path in archive: {n}")
                if n.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(n) as srcf, open(target, "wb") as dstf:
                        shutil.copyfileobj(srcf, dstf)
                    safe_names.add(n)
        entry = manifest.get("entry", "") or ("plugin.py" if manifest.get("type") != "library" else "")
        entry_rel = None
        if entry:
            for n in safe_names:
                if n.endswith("/" + entry) or n == entry:
                    entry_rel = n
                    break
            if entry_rel is None and os.path.isfile(os.path.join(tmp, entry)):
                entry_rel = entry
        if entry_rel is None and manifest.get("type") != "library":
            Logger.error(f"[zplugin] Entry point '{entry}' not found in '{path}'")
            shutil.rmtree(tmp, ignore_errors=True)
            return {}
        if os.path.exists(dest):
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(tmp, dest)
        self._activate_bundled_libs(os.path.join(dest, "libs"), manifest.get("dependencies", []), name)
        self._compile_if_needed(dest, manifest)
        if isinstance(manifest.get("files"), dict):
            problems = self._verify_payload_files(dest, manifest)
            if problems:
                Logger.error(f"[zplugin] Payload verification failed for '{path}': {'; '.join(problems)}")
                self._set_status(name, "blocked", "; ".join(problems))
                shutil.rmtree(dest, ignore_errors=True)
                return {}
        merged = {k: v for k, v in manifest.items()}
        merged["payload_dir"] = dest
        merged["entry_file"] = os.path.join(dest, entry_rel) if entry_rel else ""
        merged["entry_rel"] = entry_rel or ""
        try:
            manifest_cache = {
                "__zpl_meta": True,
                "manifest": merged,
                "payload": dest,
                "fingerprint": fingerprint,
            }
            with open(os.path.join(dest, ".zpl_meta.json"), "w", encoding="utf-8") as f:
                json.dump(manifest_cache, f, indent=2)
        except Exception as e:
            Logger.warning(f"[zplugin] Could not write cache meta: {e}")
        return merged

    def _read_zplugin_cache(self, dest: str, fingerprint: dict) -> Optional[dict]:
        if not fingerprint or not os.path.isdir(dest):
            return None
        try:
            with open(os.path.join(dest, ".zpl_meta.json"), "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            return None
        if not isinstance(cached, dict) or cached.get("__zpl_meta") is not True:
            return None
        if cached.get("fingerprint") != fingerprint:
            return None
        stored = cached.get("manifest")
        if not isinstance(stored, dict):
            return None
        ok, _reason = self.verify_manifest_signature(stored)
        if stored.get("signature") and not ok:
            return None
        if isinstance(stored.get("files"), dict) and self._verify_payload_files(dest, stored):
            return None
        entry_rel = stored.get("entry_rel", "")
        full_entry = os.path.join(dest, entry_rel) if entry_rel else ""
        if entry_rel and not os.path.isfile(full_entry):
            return None
        self._activate_bundled_libs(os.path.join(dest, "libs"), stored.get("dependencies", []),
                                    str(stored.get("name", "")))
        self._compile_if_needed(dest, stored)
        merged = {k: v for k, v in stored.items()}
        merged["payload_dir"] = dest
        merged["entry_file"] = full_entry
        return merged

    def load_zplugin(self, path: str):
        try:
            pre = _read_archive_manifest(path)
            if pre and not self._gate_or_defer("zplugin", path, pre):
                return
            manifest = self._extract_zplugin(path)
            if not manifest or ("entry_file" not in manifest and manifest.get("type") != "library"):
                return
            entry_file = manifest.get("entry_file", "")
            payload_dir = manifest.get("payload_dir", "") or (os.path.dirname(entry_file) if entry_file else "")
            libs_dir = os.path.join(payload_dir, "libs")
            self._activate_bundled_libs(libs_dir, manifest.get("dependencies", []),
                                        str(manifest.get("name", "")))
            arch = manifest.get("architecture", "any")
            arch_ok = _platform_matches(arch)
            loaded = False
            pkg = manifest.get("module")
            if entry_file and pkg and entry_file.endswith(".py"):
                if payload_dir not in sys.path:
                    sys.path.insert(0, payload_dir)
                try:
                    mod = importlib.import_module(pkg)
                    loaded = self._register_instances(
                        mod, os.path.join(payload_dir, pkg), libs_dir, manifest, payload_dir)
                except Exception as e:
                    Logger.error(f"[zplugin] Package import failed for '{pkg}': {e}", e)
            if not loaded and entry_file.endswith(".pyd") and not arch_ok:
                base = os.path.splitext(entry_file)[0]
                if os.path.isfile(base + ".py"):
                    entry_file = base + ".py"
            if entry_file and not loaded:
                if entry_file.endswith(".pyd") or entry_file.endswith(".so") or entry_file.endswith(".dll"):
                    self._load_python_plugin(os.path.splitext(os.path.basename(entry_file))[0],
                                             entry_file, libs_dir, manifest)
                    loaded = True
                elif entry_file.endswith(".py"):
                    self._load_python_plugin("_zplugin", entry_file, libs_dir, manifest)
                    loaded = True
            if not loaded and manifest.get("type") != "library":
                Logger.error(f"[zplugin] '{manifest.get('name')}' not loadable on {current_architecture()}")
            if manifest.get("type") == "library":
                self._register_library_archive(manifest, manifest.get("payload_dir", ""))
            name = manifest.get("name", "unknown")
            Logger.info(f"[zplugin] Loaded package '{name}' v{manifest.get('version', '')} from {os.path.basename(path)}")
        except Exception as e:
            Logger.error(f"Failed to load zplugin '{path}': {e}", e)

    def load_package(self, dirpath: str):
        try:
            basename = os.path.basename(dirpath)
            if basename.startswith("_"):
                return
            manifest = _read_package_manifest(dirpath)
            if manifest and not self._gate_or_defer("package", dirpath, manifest):
                return
            try:
                from core.foundation.plugin_cython import ensure_extensions as _ensure_pyx
                _ensure_pyx(dirpath, background=True)
            except Exception:
                pass
            canon = "plugins." + basename
            mod = None
            try:
                mod = importlib.import_module(canon)
            except Exception:
                init_path = os.path.join(dirpath, "__init__.py")
                pkg_name = "_plugin_" + basename
                spec = importlib.util.spec_from_file_location(pkg_name, init_path)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[pkg_name] = mod
                spec.loader.exec_module(mod)
            if manifest.get("type") == "library":
                self._register_library_package(dirpath, manifest)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                from core.foundation.plugins.base import PluginBase
                if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                    inst = obj()
                    inst._native_plugin_path = dirpath
                    self.register(inst)
            comp_dir = os.path.join(dirpath, "components")
            self._auto_load_components(comp_dir, canon)
        except Exception as e:
            Logger.error(f"Failed to load plugin package '{dirpath}': {e}")

    def load_module(self, module_name: str):
        try:
            mod = importlib.import_module(module_name)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                from core.foundation.plugins.base import PluginBase
                if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                    inst = obj()
                    inst._native_plugin_path = module_name
                    self.register(inst)
        except Exception as e:
            Logger.error(f"Failed to load plugin module '{module_name}': {e}", e)
