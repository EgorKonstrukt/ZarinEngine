# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

if sys.platform == "win32":
    _ASSIMP_SRC = "assimp-vc143-mt.dll"
else:
    _ASSIMP_SRC = "libassimp.so.6.0.5"

parser = argparse.ArgumentParser(description="Zarin Engine Nuitka build")
parser.add_argument("--editor", action="store_true", help="Build editor (main.py) instead of player (player.py)")
parser.add_argument("--output-dir", default=str(ROOT / "build_output"), help="Output directory (default: build_output)")
parser.add_argument("--no-console", action="store_true", help="Disable console window")
parser.add_argument("--onefile", action="store_true", help="Single file build")
parser.add_argument("--strip-unused", action="store_true", default=None, help="Strip unused assets (scans scenes)")
parser.add_argument("--no-strip-unused", action="store_true", dest="no_strip", help="Include all assets")
parser.add_argument("--no-winrt", action="store_true", help="Disable Windows Runtime DLL inclusion (smaller distributable)")
parser.add_argument("--compiler", choices=("auto", "mingw", "msvc"), default="auto",
                    help="C compiler for Nuitka (default: auto = MinGW-w64, auto-downloaded; "
                         "no heavy MSVC install needed). Use 'msvc' to force Visual Studio.")
parser.add_argument("--physics", choices=("culverin", "pybullet", "physx"), default=None,
                     help="Physics solver baked into the build (default: from ProjectSettings.json, "
                          "fallback: culverin (Jolt Physics))")
parser.add_argument("--project-dir", default=None,
                    help="Project root whose BuildSettings.json, scenes and assets are packaged "
                         "(default: engine root)")

_args, remaining = parser.parse_known_args()

OUTPUT_DIR = Path(_args.output_dir)
ENTRY = str(ROOT / "main.py" if _args.editor else "player.py")
BUILD_EDITOR = _args.editor
NO_CONSOLE = _args.no_console
ONEFILE = _args.onefile
CLI_STRIP = _args.strip_unused
CLI_NO_STRIP = _args.no_strip
NO_WINRT = _args.no_winrt
COMPILER_CHOICE = _args.compiler
PHYSICS_CHOICE = _args.physics
PROJECT_DIR = Path(_args.project_dir) if _args.project_dir else None

print("=== " + ("EDITOR BUILD" if BUILD_EDITOR else "PLAYER BUILD") + " ===")


def _resolve_physics_solver() -> str:
    if PHYSICS_CHOICE:
        return PHYSICS_CHOICE
    try:
        from physics_solvers.registry import normalize, DEFAULT_SOLVER
    except ImportError:
        normalize = None
        DEFAULT_SOLVER = "culverin"
    ps_path = ROOT / "ProjectSettings.json"
    if not ps_path.exists():
        return DEFAULT_SOLVER
    try:
        with open(ps_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        solver = data.get("physics", {}).get("solver", DEFAULT_SOLVER)
        if normalize is not None:
            return normalize(solver)
        return solver if solver in ("pybullet", "physx", "culverin") else DEFAULT_SOLVER
    except Exception:
        return DEFAULT_SOLVER


def _setup_compiler() -> tuple[str, list[str], dict]:
    sys.path.insert(0, str(ROOT))
    try:
        from tools.mingwpm import ensure_mingw, nuitka_flags, resolve_compiler, activate
    except ImportError:
        return "unknown", ["--assume-yes-for-downloads"], dict(os.environ)
    compiler = resolve_compiler(COMPILER_CHOICE if COMPILER_CHOICE != "auto" else None)
    print(f"C compiler: {compiler} (MinGW-w64 is compact, MSVC would need several GB)")
    env = dict(os.environ)
    if sys.platform == "win32" and compiler == "mingw":
        try:
            bin_dir = ensure_mingw()
            env = activate(bin_dir)
        except Exception as e:
            print(f"  WARNING: MinGW-w64 auto-download failed: {e}")
            print("  Falling back to Nuitka's own toolchain download.")
    return compiler, nuitka_flags(COMPILER_CHOICE if COMPILER_CHOICE != "auto" else None), env


def _load_build_settings() -> dict:
    for bs_path in ([PROJECT_DIR / "BuildSettings.json"] if PROJECT_DIR is not None else []) + [ROOT / "BuildSettings.json"]:
        if bs_path.exists():
            with open(bs_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def _resolve_scene_path(s: str, base: Path) -> Path | None:
    try:
        if os.path.isabs(s):
            full = Path(s)
            return full if full.exists() else None
        for cand in (base / s, base / "scenes" / s):
            if cand.exists():
                return cand
    except Exception:
        pass
    return None


def _get_included_scenes(bs: dict, base=None) -> list[str]:
    scenes = bs.get("scenes", [])
    root = base or ROOT
    included = []
    for s in scenes:
        if os.path.isabs(s):
            full = Path(s)
        else:
            s_stripped = s
            for prefix in ("scenes/", "scenes\\"):
                if s_stripped.startswith(prefix):
                    s_stripped = s_stripped[len(prefix):]
                    break
            probe = _resolve_scene_path(s, root)
            if probe is None:
                probe = _resolve_scene_path(s_stripped, root)
            full = probe if probe is not None else root / "scenes" / s_stripped
        if full.exists():
            included.append(str(full))
        else:
            print(f"  WARNING: scene not found: {full}")
    return included
