# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.zplug.verify import _copy_dist_info
from tools.zplug.verify import _dist_version
from tools.zplug.verify import _excluded
from tools.zplug.verify import _freeze_stage
from tools.zplug.verify import _normalize_mod_name
from tools.zplug.verify import _pin_installed_versions
from tools.zplug.verify import _resolve_bundle_modules
from tools.zplug.verify import _scan_stage_libs
from tools.zplug.verify import _sign_manifest
from tools.zplug.verify import _wheel_name_version
from tools.zplug.verify import _wheel_top_levels
from tools.zplug.verify import _PM_OK
from tools.zplug.verify import current_architecture
from tools.zplug.verify import DEFAULT_EXCLUDES
from tools.zplug.verify import load_source_manifest

try:
    from tools.mingwpm import env_with_mingw as _env_with_mingw
    from tools.mingwpm import nuitka_flags as _nuitka_flags
except Exception:
    _env_with_mingw = None
    _nuitka_flags = None

def _zpl_build_env() -> dict | None:
    if _env_with_mingw is None:
        return None
    try:
        return _env_with_mingw()
    except Exception as e:
        print(f"WARNING: MinGW-w64 setup failed: {e}")
        return None

def _iter_package_modules(pkg_dir: str) -> list[str]:
    mods = []
    for root, _dirs, files in os.walk(pkg_dir):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, pkg_dir)
            if fn == "__init__.py":
                continue
            mods.append(rel)
    return mods

def _compile_tree_cython(stage_root: str, module: str, pkg_dir: str) -> bool:
    try:
        import Cython
    except ImportError:
        print("Cython not installed. Run: pip install cython")
        return False
    rels = _iter_package_modules(pkg_dir)
    if not rels:
        return True
    ext_lines = []
    for rel in rels:
        dotted = module + "." + rel[:-3].replace(os.sep, ".")
        src = os.path.join(module, rel).replace(os.sep, "/")
        ext_lines.append(f'Extension("{dotted}", [r"{src}"])')
    setup_path = os.path.join(stage_root, "_zpl_cython_setup.py")
    with open(setup_path, "w", encoding="utf-8") as f:
        f.write(
            "from setuptools import setup, Extension\n"
            "from Cython.Build import cythonize\n"
            "setup(ext_modules=cythonize([\n" + ",\n".join(ext_lines) + "\n]))\n"
        )
    try:
        cython_env = _zpl_build_env()
        cython_cmd = [sys.executable, setup_path, "build_ext", "--inplace"]
        if cython_env is not None and sys.platform == "win32":
            cython_cmd.insert(3, "--compiler=mingw32")
        result = subprocess.run(
            cython_cmd,
            capture_output=True, text=True, cwd=stage_root, env=cython_env or None,
        )
    finally:
        if os.path.isfile(setup_path):
            os.remove(setup_path)
    if result.returncode != 0:
        print(f"Cython build failed:\n{result.stderr[-2000:]}")
        return False
    ok = True
    for rel in rels:
        base = os.path.splitext(os.path.basename(rel))[0]
        d = os.path.join(pkg_dir, os.path.dirname(rel))
        found = [f for f in os.listdir(d) if f.startswith(base + ".") and f.endswith((".pyd", ".so"))]
        if found:
            print(f"  cython: {rel} -> {found[0]}")
        else:
            print(f"  cython: {rel} produced no extension module")
            ok = False
    for root, dirs, _files in os.walk(stage_root):
        for d in [x for x in dirs if x == "build"]:
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    return ok

def _compile_tree_nuitka(stage_root: str, module: str, pkg_dir: str) -> bool:
    try:
        import nuitka
    except ImportError:
        print("Nuitka not installed. Run: pip install nuitka")
        return False
    rels = _iter_package_modules(pkg_dir)
    if not rels:
        return True
    ok = True
    for rel in rels:
        src = os.path.join(pkg_dir, rel)
        outdir = os.path.dirname(src)
        nuitka_cmd = [
            sys.executable, "-m", "nuitka", "--module",
            *(_nuitka_flags() if _nuitka_flags else []),
            f"--output-dir={outdir}", src,
        ]
        result = subprocess.run(
            nuitka_cmd,
            capture_output=True, text=True, cwd=stage_root, env=_zpl_build_env() or None,
        )
        base = os.path.splitext(os.path.basename(rel))[0]
        found = [f for f in os.listdir(outdir) if f.startswith(base + ".") and f.endswith((".pyd", ".so"))]
        for d in os.listdir(outdir):
            if d.startswith(base + ".build") or d.startswith(base + ".dist"):
                shutil.rmtree(os.path.join(outdir, d), ignore_errors=True)
        if result.returncode == 0 and found:
            print(f"  nuitka: {rel} -> {found[0]}")
        else:
            print(f"  nuitka failed for {rel}:\n{(result.stderr or '')[-2000:]}")
            ok = False
    return ok

def download_wheels(requirements, dest_dir, python_version=None, platform=None,
                    abi=None, implementation="cp") -> list:
    cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:",
           "-d", dest_dir]
    if python_version or platform or abi:
        if python_version:
            cmd += ["--python-version", str(python_version)]
        if platform:
            cmd += ["--platform", str(platform)]
        if abi:
            cmd += ["--abi", str(abi)]
        cmd += ["--implementation", str(implementation or "cp")]
    cmd += list(requirements or [])
    if not cmd[-len(list(requirements or [])):]:
        raise ValueError("download_wheels needs at least one requirement")
    os.makedirs(dest_dir, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip().splitlines()
        raise RuntimeError("pip download failed:\n" + "\n".join(tail[-15:]))
    wheels = sorted(f for f in os.listdir(dest_dir) if f.endswith(".whl"))
    if not wheels:
        raise RuntimeError("pip download produced no wheels")
    return [os.path.join(dest_dir, w) for w in wheels]

def vendor_wheels(wheel_paths, libs_dir, exclude=()) -> dict:
    excluded = {_normalize_mod_name(e) for e in (exclude or [])}
    provides = {}
    os.makedirs(libs_dir, exist_ok=True)
    for whl in wheel_paths or []:
        dist_name, dist_version = _wheel_name_version(whl)
        if _normalize_mod_name(dist_name) in excluded:
            print(f"  vendor: {dist_name} excluded")
            continue
        try:
            with zipfile.ZipFile(whl) as zf:
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    parts = member.split("/")
                    if parts[0].endswith(".data"):
                        if len(parts) < 3 or parts[1] not in ("purelib", "platlib"):
                            continue
                        rel = "/".join(parts[2:])
                    else:
                        rel = member
                    if not rel:
                        continue
                    target = os.path.join(libs_dir, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as srcf, open(target, "wb") as dstf:
                        shutil.copyfileobj(srcf, dstf)
            for top in _wheel_top_levels(whl):
                provides.setdefault(top, dist_version)
            print(f"  vendor: {dist_name} ({dist_version})")
        except Exception as e:
            print(f"  vendor: '{os.path.basename(whl)}' failed: {e}")
    return provides

def _bundle_into_stage(stage: str, modules) -> dict:
    provides = {}
    libs = os.path.join(stage, "libs")
    os.makedirs(libs, exist_ok=True)
    for top in _resolve_bundle_modules(modules):
        try:
            spec = importlib.util.find_spec(top)
        except Exception:
            spec = None
        if spec is None:
            print(f"  bundle: '{top}' not installed, skipped")
            continue
        version = _dist_version(top)
        try:
            locations = list(spec.submodule_search_locations or [])
            if locations:
                dst = os.path.join(libs, top)
                if os.path.isdir(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(locations[0], dst,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"))
                _copy_dist_info(top, libs)
            elif spec.origin and spec.origin.endswith(".py"):
                shutil.copy2(spec.origin, os.path.join(libs, top + ".py"))
            else:
                print(f"  bundle: '{top}' has no copyable source, skipped")
                continue
            provides[top] = version
            print(f"  bundle: {top} ({version})")
        except Exception as e:
            print(f"  bundle: '{top}' failed: {e}")
    return provides

def create_library_pack(name: str, version: str, modules, output_dir: str = "dist",
                        arch: str = "any", python_requires: str = "",
                        engine_api: str = ">=1", description: str = "",
                        sign_key: str = "", install_dir: str | None = None,
                        download: bool = False, download_requires=None,
                        target=None, exclude=("numpy",)) -> str | None:
    if arch == "current":
        arch = current_architecture()
    if download and not download_requires:
        download_requires = [f"{m}=={v}" for m, v in _pin_installed_versions(modules)]
    excluded = set(exclude or ()) if download or download_requires else set()
    src = tempfile.mkdtemp(prefix="libpack_src_")
    try:
        meta = {"name": name, "version": version, "description": description,
                "architecture": arch, "entry": "", "module": name,
                "dependencies": ["numpy>=1"] if "numpy" in excluded else [],
                "requires": [],
                "engine_api": engine_api, "python_requires": python_requires,
                "type": "library", "provides": {},
                "exclude": list(DEFAULT_EXCLUDES)}
        with open(os.path.join(src, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        archive = build_zplugin(src, output_dir, "source", bundle=list(modules or []),
                                sign_key=sign_key, ptype="library", freeze=True,
                                download=download, download_requires=download_requires,
                                target=target, exclude=excluded)
        if archive and install_dir:
            os.makedirs(install_dir, exist_ok=True)
            dest = os.path.join(install_dir, os.path.basename(archive))
            shutil.copy2(archive, dest)
            return dest
        return archive
    finally:
        shutil.rmtree(src, ignore_errors=True)

def build_zplugin(plugin_src: str, output_dir: str = "dist", mode: str = "source",
                  bundle=(), sign_key: str = "", ptype: str | None = None,
                  freeze: bool = True, download: bool = False,
                  download_requires=None, target=None, exclude=()) -> str | None:
    plugin_src = os.path.abspath(plugin_src)
    if os.path.isfile(plugin_src) and plugin_src.endswith(".py"):
        raise ValueError("build_zplugin needs a plugin package directory, not a single .py file")
    if not os.path.isdir(plugin_src):
        print(f"Error: {plugin_src} not found")
        return None
    meta = load_source_manifest(plugin_src)
    name = str(meta["name"])
    version = str(meta.get("version", "0.0.1"))
    module = str(meta.get("module", name))
    ptype = ptype or str(meta.get("type", "plugin"))
    if ptype not in ("plugin", "library"):
        print(f"Unknown type: {ptype}")
        return None
    entry = str(meta.get("entry", f"{module}/__init__.py" if ptype == "plugin" else ""))
    excludes = list(meta.get("exclude", [])) + DEFAULT_EXCLUDES
    if mode not in ("source", "cython", "nuitka"):
        print(f"Unknown mode: {mode}")
        return None
    stage = tempfile.mkdtemp(prefix="zplugin_build_")
    try:
        pkg_stage = os.path.join(stage, module)
        for root, _dirs, files in os.walk(plugin_src):
            rel_root = os.path.relpath(root, plugin_src)
            for fn in files:
                rel = fn if rel_root == "." else os.path.join(rel_root, fn)
                if _excluded(rel, excludes):
                    continue
                if fn == "manifest.json" and rel_root == ".":
                    continue
                src = os.path.join(root, fn)
                dst = os.path.join(pkg_stage, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        src_libs = os.path.join(plugin_src, "libs")
        if os.path.isdir(src_libs):
            dst_libs = os.path.join(stage, "libs")
            shutil.copytree(src_libs, dst_libs, ignore=shutil.ignore_patterns(*excludes))
        arch = str(meta.get("architecture", "any") or "any")
        if mode in ("cython", "nuitka"):
            compiler = _compile_tree_cython if mode == "cython" else _compile_tree_nuitka
            if compiler(stage, module, pkg_stage):
                arch = current_architecture()
            else:
                print(f"WARNING: {mode} compile failed, falling back to source mode.")
        bundled = _bundle_into_stage(stage, bundle) if bundle else {}
        dl_conf = dict(meta.get("download", {}) or {}) if download else {}
        reqs = list(download_requires or [])
        if download and not reqs:
            reqs = list(dl_conf.get("requires", []) or [])
        triple = dict(target or {})
        for key in ("python_version", "platform", "abi", "implementation"):
            if key not in triple and dl_conf.get(key):
                triple[key] = dl_conf[key]
        if reqs:
            dl_dir = tempfile.mkdtemp(prefix="zplugin_dl_")
            try:
                wheels = download_wheels(reqs, dl_dir,
                                         python_version=triple.get("python_version"),
                                         platform=triple.get("platform"),
                                         abi=triple.get("abi"),
                                         implementation=triple.get("implementation", "cp"))
                downloaded = vendor_wheels(wheels, os.path.join(stage, "libs"),
                                           exclude=set(exclude or ()) | set(dl_conf.get("exclude", []) or []))
            except RuntimeError as e:
                print(f"Error: {e}")
                return None
            finally:
                shutil.rmtree(dl_dir, ignore_errors=True)
        else:
            downloaded = {}
        provides = dict(meta.get("provides", {}) or {})
        for key, val in list(bundled.items()) + list(downloaded.items()):
            provides.setdefault(key, val)
        if ptype == "library":
            for key, val in _scan_stage_libs(os.path.join(stage, "libs")).items():
                provides.setdefault(key, val)
        manifest = {
            "name": name,
            "version": version,
            "description": meta.get("description", ""),
            "architecture": arch,
            "entry": entry,
            "module": module,
            "dependencies": meta.get("dependencies", []),
            "requires": meta.get("requires", []),
            "engine_api": meta.get("engine_api", ""),
            "python_requires": meta.get("python_requires", ""),
            "type": ptype,
            "provides": provides,
        }
        if freeze or sign_key:
            manifest["files"] = _freeze_stage(stage)
        if sign_key:
            if not _PM_OK:
                print("Error: signing needs core.foundation.ed25519; run from the engine root.")
                return None
            try:
                _sign_manifest(manifest, sign_key)
            except Exception as e:
                print(f"Error: signing failed: {e}")
                return None
        with open(os.path.join(stage, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        outdir = os.path.abspath(output_dir)
        os.makedirs(outdir, exist_ok=True)
        archive = os.path.join(outdir, f"{name}-{version}.zplugin")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(stage):
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, stage).replace(os.sep, "/")
                    zf.write(full, arc)
        print(f"OK: {archive} (mode={mode}, arch={arch})")
        return archive
    finally:
        shutil.rmtree(stage, ignore_errors=True)
