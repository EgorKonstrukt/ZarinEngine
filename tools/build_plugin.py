# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""
Plugin packaging tool.

Builds a plugin into a distributable binary (.dll / .pyd) using Nuitka or Cython.
All dependencies are bundled into the single binary.

Usage:
    python tools/build_plugin.py path/to/plugin.py
    python tools/build_plugin.py path/to/plugin_dir/  --name MyPlugin
    python tools/build_plugin.py plugins/example_plugin.py --output dist/
"""

import sys
import os
import shutil
import subprocess
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from tools.mingw import env_with_mingw as _env_with_mingw
    from tools.mingw import nuitka_flags as _nuitka_flags
except ImportError:
    _env_with_mingw = None
    _nuitka_flags = None


def _build_env() -> dict | None:
    """Env with auto-downloaded MinGW-w64 on PATH (None = unchanged)."""
    if _env_with_mingw is None:
        return None
    try:
        return _env_with_mingw()
    except Exception as e:
        print(f"WARNING: MinGW-w64 setup failed: {e}")
        return None


def find_nuitka():
    try:
        import nuitka
        return True
    except ImportError:
        return False


def find_cython():
    try:
        import Cython
        return True
    except ImportError:
        return False


def build_with_nuitka(plugin_path: str, output_dir: str, plugin_name: str):
    """Build a plugin .pyd using Nuitka (recommended)."""
    if not find_nuitka():
        print("Nuitka not installed. Run: pip install nuitka")
        return False

    out = os.path.abspath(output_dir)
    os.makedirs(out, exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--module",
        *(_nuitka_flags() if _nuitka_flags else []),
        f"--output-dir={out}",
        plugin_path,
    ]

    print(f"Building {plugin_path} -> {out}/{plugin_name}.pyd ...")
    result = subprocess.run(cmd, capture_output=True, text=True, env=_build_env() or None)
    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        return False

    built = os.path.join(out, f"{plugin_name}.pyd")
    if os.path.isfile(built):
        print(f"OK: {built}")
        return True

    # Nuitka may produce different name
    for f in os.listdir(out):
        if f.endswith(".pyd") and plugin_name in f:
            print(f"OK: {os.path.join(out, f)}")
            return True
    print(f"Build completed but .pyd not found in {out}")
    return False


def build_with_cython(plugin_path: str, output_dir: str, plugin_name: str):
    """Build a plugin .pyd using Cython."""
    if not find_cython():
        print("Cython not installed. Run: pip install cython")
        return False

    out = os.path.abspath(output_dir)
    os.makedirs(out, exist_ok=True)

    # Generate setup.py
    setup_path = os.path.join(out, "_build_setup.py")
    rel = os.path.relpath(plugin_path, out)
    with open(setup_path, "w") as f:
        f.write(f"""
from setuptools import setup, Extension
from Cython.Build import cythonize
setup(
    ext_modules=cythonize([Extension("{plugin_name}", [r"{rel}"])]),
)
""")

    print(f"Cythonizing {plugin_path} ...")
    cmd = [sys.executable, setup_path, "build_ext", "--inplace"]
    build_env = _build_env()
    if build_env is not None and sys.platform == "win32":
        # Prefer compact MinGW-w64 over MSVC when available.
        cmd.insert(3, "--compiler=mingw32")
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, cwd=out, env=build_env or None,
    )
    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}")
        return False

    for f in os.listdir(out):
        if f.endswith(".pyd") and plugin_name in f:
            print(f"OK: {os.path.join(out, f)}")
            return True
    print("Build completed but .pyd not found")
    return False


def build_plugin(plugin_path: str, output_dir: str = "dist", backend: str = "auto"):
    """Package a plugin into a distributable .pyd (native extension).

    The .pyd can be loaded by PluginManager.load_from_file() just like a .py file.
    """
    plugin_path = os.path.abspath(plugin_path)
    if not os.path.exists(plugin_path):
        print(f"Error: {plugin_path} not found")
        return False

    if os.path.isdir(plugin_path):
        # Plugin directory вЂ” package it
        plugin_name = os.path.basename(plugin_path)
        init = os.path.join(plugin_path, "__init__.py")
        if os.path.isfile(init):
            plugin_path = init
        else:
            print(f"Error: {plugin_path} has no __init__.py")
            return False
    else:
        plugin_name = os.path.splitext(os.path.basename(plugin_path))[0]

    if backend == "auto":
        if find_nuitka():
            backend = "nuitka"
        elif find_cython():
            backend = "cython"
        else:
            print("No build backend found. Install: pip install nuitka")
            print("Or install: pip install cython")
            return False

    if backend == "nuitka":
        return build_with_nuitka(plugin_path, output_dir, plugin_name)
    elif backend == "cython":
        return build_with_cython(plugin_path, output_dir, plugin_name)
    else:
        print(f"Unknown backend: {backend}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Build Zarin Engine plugin to .pyd")
    parser.add_argument("plugin", help="Path to plugin.py or plugin directory")
    parser.add_argument("--output", "-o", default="dist", help="Output directory")
    parser.add_argument("--backend", choices=["nuitka", "cython", "auto"], default="auto",
                        help="Build backend (default: auto)")
    args = parser.parse_args()

    success = build_plugin(args.plugin, args.output, args.backend)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
