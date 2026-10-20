# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
import json
import os
import shutil
import time
from pathlib import Path
from .config import ROOT


def _rmtree_robust(path):
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt < 4:
                time.sleep(0.5)
                continue
            try:
                trash = str(path) + ".old_" + str(int(time.time()))
                os.rename(str(path), trash)
                shutil.rmtree(trash, ignore_errors=True)
                return
            except Exception:
                shutil.rmtree(str(path), ignore_errors=True)
                return


def _plugin_include_options(names: list[str]) -> list[str]:
    opts: list[str] = ["--include-module=plugins"]
    seen: set[str] = {"plugins"}
    for name in names:
        full = name if name.startswith("plugins.") else "plugins." + name
        parts = full.split(".")
        for i in range(1, len(parts) - 1):
            pkg = ".".join(parts[:i + 1])
            if pkg in seen:
                continue
            pkg_dir = ROOT / Path(*pkg.split("."))
            if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
                opts.append(f"--include-module={pkg}")
                seen.add(pkg)
        leaf_dir = ROOT / Path(*parts)
        if leaf_dir.is_dir() and (leaf_dir / "__init__.py").exists():
            opts.append(f"--include-package={full}")
        else:
            opts.append(f"--include-module={full}")
    return opts


def _scan_scene_assets(scene_path: str) -> set[str]:
    PATH_FIELDS = {"mesh_path", "material_path", "clip_path", "script_path", "texture_path", "ply_path", "shader_path", "env_path", "svg_path", "font_path", "video_path", "graph_path"}
    assets = set()
    try:
        with open(scene_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entities = data.get("entities", {})
        jobs: list[dict] = []
        for edata in entities.values():
            try:
                comps = edata.get("components", [])
            except Exception:
                continue
            jobs.extend(comps)

        def scan_comp(comp: dict):
            found: set[str] = set()
            try:
                for key, val in comp.items():
                    if key in PATH_FIELDS and isinstance(val, str) and val:
                        found.add(val)
            except Exception:
                pass
            return found
        if len(jobs) > 32:
            with ThreadPoolExecutor(max_workers=min(8, max(2, os.cpu_count() or 4))) as ex:
                for part in ex.map(scan_comp, jobs):
                    assets.update(part)
        else:
            for comp in jobs:
                assets.update(scan_comp(comp))
    except Exception as e:
        print(f"  WARNING: failed to scan {scene_path}: {e}")
    return assets


def _resolve_one(a: str, project_root: Path, assets_dir: Path) -> set[Path]:
    out: set[Path] = set()
    try:
        if os.path.isabs(a):
            p = Path(a)
            if p.exists():
                if p.is_dir():
                    for root, dirs, files in os.walk(p):
                        for fn in files:
                            out.add(Path(root) / fn)
                    out.add(p)
                else:
                    out.add(p)
        else:
            candidates = [
                project_root / a,
                assets_dir / a,
                assets_dir / Path(a).name,
            ]
            for c in candidates:
                if c.exists():
                    if c.is_dir():
                        for root, dirs, files in os.walk(c):
                            for fn in files:
                                out.add(Path(root) / fn)
                        out.add(c)
                    else:
                        out.add(c)
                    break
    except Exception:
        pass
    return out


def _resolve_assets(assets: set[str], project_root: Path) -> set[Path]:
    resolved = set()
    assets_dir = project_root / "assets"
    lst = list(assets)
    if len(lst) <= 8:
        for a in lst:
            resolved.update(_resolve_one(a, project_root, assets_dir))
        return resolved
    with ThreadPoolExecutor(max_workers=min(8, max(2, os.cpu_count() or 4))) as ex:
        futs = [ex.submit(_resolve_one, a, project_root, assets_dir) for a in lst]
        for fu in as_completed(futs):
            try:
                resolved.update(fu.result())
            except Exception:
                pass
    return resolved


def _collect_asset_dirs(assets: set[Path], project_root: Path) -> dict[str, str]:
    dirs: dict[str, set[str]] = {}
    assets_dir = project_root / "assets"
    for a in assets:
        try:
            rel = a.relative_to(assets_dir)
            parent = rel.parent
            dirs.setdefault(str(assets_dir / parent), set()).add(str(a.name))
        except ValueError:
            dirs.setdefault(str(a.parent), set()).add(str(a.name))
    return dirs
