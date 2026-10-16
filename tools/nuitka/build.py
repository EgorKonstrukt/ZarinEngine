# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .assets import _plugin_include_options, _resolve_assets, _rmtree_robust, _scan_scene_assets
from .config import BUILD_EDITOR, CLI_NO_STRIP, CLI_STRIP, ENTRY, NO_CONSOLE, NO_WINRT, ONEFILE, OUTPUT_DIR, ROOT, _ASSIMP_SRC, _get_included_scenes, _load_build_settings, _resolve_physics_solver, _setup_compiler


def _minify_pil():
    import PIL
    pil_dir = Path(PIL.__file__).parent
    src = pil_dir / "__init__.py"
    bak = pil_dir / "__init__.py.__bak__"
    if bak.exists():
        return
    original = src.read_text(encoding="utf-8")
    bak.write_text(original, encoding="utf-8")
    kept = {
        "BmpImagePlugin", "GifImagePlugin", "JpegImagePlugin",
        "PpmImagePlugin", "PngImagePlugin",
    }
    new_plugins = [f'    "{p}",' for p in sorted(kept)]
    import re
    modified = re.sub(
        r'_plugins\s*=\s*\[.*?^\]',
        '_plugins = [\n' + '\n'.join(new_plugins) + '\n]',
        original, flags=re.DOTALL | re.MULTILINE
    )
    src.write_text(modified, encoding="utf-8")
    print(f"  PIL minified: {len(kept)} plugins kept (was {original.count('ImagePlugin')})")


def _restore_pil():
    import PIL
    pil_dir = Path(PIL.__file__).parent
    bak = pil_dir / "__init__.py.__bak__"
    if bak.exists():
        (pil_dir / "__init__.py").write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        bak.unlink()
        print("  PIL restored")


def build():
    print("=== Zarin Engine Nuitka Build ===")
    print(f"Python: {sys.executable}")
    print(f"Root: {ROOT}")
    print()
    bs = _load_build_settings()
    included_scenes = _get_included_scenes(bs)
    build_options = bs.get("build_options", {})
    strip_unused = build_options.get("strip_unused_assets", True)
    if CLI_STRIP:
        strip_unused = True
    if CLI_NO_STRIP:
        strip_unused = False
    print(f"BuildSettings loaded: {bool(bs)}")
    print(f"Scenes in BuildSettings: {bs.get('scenes', [])}")
    print(f"Included scenes: {len(included_scenes)}")
    for s in included_scenes:
        print(f"  -> {s}")
    build_plugins = bs.get("build_plugins", [])
    if not build_plugins:
        plugins_dir = ROOT / "plugins"
        if plugins_dir.is_dir():
            for f in sorted(plugins_dir.iterdir()):
                if f.suffix == ".py" and not f.stem.startswith("_"):
                    build_plugins.append(f.stem)
            user_dir = plugins_dir / "user"
            if user_dir.is_dir():
                for f in sorted(user_dir.iterdir()):
                    if f.suffix == ".py" and not f.stem.startswith("_"):
                        build_plugins.append("user." + f.stem)
        bs["build_plugins"] = build_plugins
        _build_bs_path = ROOT / "_build_BuildSettings.json"
        with open(_build_bs_path, "w", encoding="utf-8") as f:
            json.dump(bs, f, indent=2)
        print(f"Build plugins (auto): {build_plugins}")
    else:
        print(f"Build plugins (config): {build_plugins}")
    all_asset_refs: set[str] = set()
    for scene in included_scenes:
        refs = _scan_scene_assets(scene)
        all_asset_refs.update(refs)
        print(f"  Scene: {Path(scene).name} -> {len(refs)} asset refs")
    resolved_assets = _resolve_assets(all_asset_refs, ROOT)
    print(f"Total referenced assets: {len(resolved_assets)}")
    print(f"strip_unused_assets: {strip_unused}")
    for a in list(resolved_assets)[:10]:
        print(f"  -> {a}")
    if len(resolved_assets) > 10:
        print(f"  ... and {len(resolved_assets) - 10} more")
    print("\nAnalyzing dependencies...")
    from build_analyzer import analyze
    analysis = analyze(verbose=False)
    module_nofollow = analysis["module_nofollow"]
    package_nofollow = analysis["package_nofollow"]
    print(f"Auto-excluded: {len(module_nofollow)} modules, {len(package_nofollow)} packages")
    print()
    physics_solver = _resolve_physics_solver()
    print(f"Physics solver baked into build: {physics_solver}")
    COMPILER_NAME, COMPILER_FLAGS, BUILD_ENV = _setup_compiler()
    print(f"Nuitka compiler flags: {COMPILER_FLAGS}")
    print()
    if OUTPUT_DIR.exists():
        print(f"Cleaning old output: {OUTPUT_DIR}")
        _rmtree_robust(OUTPUT_DIR)
    for stale_dir in [ROOT / "player.build", ROOT / "main.build"]:
        if stale_dir.exists():
            print(f"Cleaning stale build dir: {stale_dir}")
            _rmtree_robust(stale_dir)
    nuitka_cache = Path(os.path.expanduser("~")) / ".cache" / "nuitka"
    if nuitka_cache.exists():
        print(f"Cleaning Nuitka cache: {nuitka_cache}")
        shutil.rmtree(nuitka_cache, ignore_errors=True)
    for pycache in ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache, ignore_errors=True)
        except Exception:
            pass
    print("Cleaned __pycache__ dirs")
    NUITKA_OPTIONS = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--output-dir=" + str(OUTPUT_DIR),
        "--output-filename=" + ("ZarinEditor" if BUILD_EDITOR else "ZarinPlayer"),
        "--enable-plugin=pyside6",
        "--disable-ccache",
        *COMPILER_FLAGS,
        "--include-package=core",
        *_plugin_include_options(build_plugins),
        f"--include-package=physics_solvers.{physics_solver}_solver",
        "--include-data-file=" + _ASSIMP_SRC + "=" + _ASSIMP_SRC,
        "--include-data-file=" + ("_build_BuildSettings.json" if build_plugins != bs.get("build_plugins") else "BuildSettings.json") + "=BuildSettings.json",
        *[f"--nofollow-import-to={m}" for m in module_nofollow],
        *[f"--nofollow-import-to={m}" for m in package_nofollow],
        "--remove-output",
        "--clean-cache=all",
        "--warn-unusual-code",
    ]
    if ONEFILE:
        NUITKA_OPTIONS.append("--onefile")
    if NO_CONSOLE:
        NUITKA_OPTIONS.append("--disable-console")
    if NO_WINRT:
        NUITKA_OPTIONS.append("--include-windows-runtime-dlls=no")
    scenes_dir = ROOT / "scenes"
    if included_scenes:
        temp_scenes = ROOT / "_build_scenes"
        if temp_scenes.exists():
            _rmtree_robust(temp_scenes)
        temp_scenes.mkdir(parents=True)
        for scene in included_scenes:
            dest = temp_scenes / Path(scene).name
            shutil.copy2(scene, dest)
            print(f"  Scene copied: {scene} -> {dest}")
        NUITKA_OPTIONS.append("--include-data-dir=_build_scenes=scenes")
        print(f"Included {len(included_scenes)} scenes")
        print(f"  _build_scenes contents: {[str(p.name) for p in temp_scenes.iterdir()]}")
    else:
        if scenes_dir.exists():
            NUITKA_OPTIONS.append("--include-data-dir=scenes=scenes")
            print(f"No BuildSettings - including ALL scenes ({len(list(scenes_dir.iterdir()))} files)")
    temp_assets = ROOT / "_build_assets"
    if temp_assets.exists():
        _rmtree_robust(temp_assets)
    if strip_unused:
        temp_assets.mkdir(parents=True, exist_ok=True)
        assets_dir = ROOT / "assets"
        copied = 0
        for asset_path in resolved_assets:
            try:
                if asset_path.is_dir():
                    try:
                        rel = asset_path.relative_to(assets_dir)
                        dest = temp_assets / rel
                    except ValueError:
                        dest = temp_assets / asset_path.name
                    shutil.copytree(asset_path, dest, dirs_exist_ok=True)
                    copied += 1
                    print(f"  Asset dir copied: {asset_path}")
                    continue
                rel = asset_path.relative_to(assets_dir)
                dest = temp_assets / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset_path, dest)
                copied += 1
                print(f"  Asset copied: {rel}")
            except ValueError:
                try:
                    if asset_path.is_dir():
                        dest = temp_assets / asset_path.name
                        shutil.copytree(asset_path, dest, dirs_exist_ok=True)
                    else:
                        dest = temp_assets / asset_path.name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(asset_path, dest)
                    copied += 1
                    print(f"  Asset copied (flat): {asset_path.name}")
                except Exception:
                    continue
            except Exception:
                continue
        NUITKA_OPTIONS.append("--include-data-dir=_build_assets=assets")
        print(f"Assets: {copied} referenced files copied (of {len(resolved_assets)} refs)")
        print(f"  _build_assets contents: {[str(p.relative_to(temp_assets)) for p in temp_assets.rglob('*') if p.is_file()]}")
    else:
        if (ROOT / "assets").exists():
            NUITKA_OPTIONS.append("--include-data-dir=assets=assets")
            print("Assets: including ALL (no filtering)")
    if (ROOT / "materials").exists():
        NUITKA_OPTIONS.append("--include-data-dir=materials=materials")
    if (ROOT / "prefabs").exists():
        NUITKA_OPTIONS.append("--include-data-dir=prefabs=prefabs")
    if (ROOT / "core" / "shaders").exists():
        NUITKA_OPTIONS.append("--include-data-dir=core/shaders=core/shaders")
    NUITKA_OPTIONS.append(ENTRY)
    print("\nRunning Nuitka with options:")
    for opt in NUITKA_OPTIONS:
        if opt.startswith("-"):
            print(f"  {opt}")
        else:
            print(f"  ENTRY: {opt}")
    print()
    _minify_pil()
    try:
        result = subprocess.run(NUITKA_OPTIONS, cwd=str(ROOT), env=BUILD_ENV)
    finally:
        _restore_pil()
    temp_bs = ROOT / "_build_BuildSettings.json"
    if temp_bs.exists():
        temp_bs.unlink()
    for d in ["_build_scenes", "_build_assets"]:
        p = ROOT / d
        if p.exists():
            _rmtree_robust(p)
    if result.returncode != 0:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(result.returncode)
    dist_dirs = list(OUTPUT_DIR.glob("*.dist"))
    if dist_dirs:
        dist_dir = dist_dirs[0]
        bs_in_dist = dist_dir / "BuildSettings.json"
        print(f"\nVerifying dist: {dist_dir}")
        print(f"  BuildSettings.json: {'EXISTS' if bs_in_dist.exists() else 'MISSING!'}")
        scene_in_dist = dist_dir / "scenes"
        if scene_in_dist.exists():
            scenes_list = [p.name for p in scene_in_dist.iterdir()]
            print(f"  Scenes: {scenes_list}")
        else:
            print("  Scenes dir: MISSING!")
        assets_in_dist = dist_dir / "assets"
        if assets_in_dist.exists():
            assets_count = len(list(assets_in_dist.rglob("*")))
            print(f"  Assets: {assets_count} files")
        else:
            print("  Assets dir: MISSING!")
    print("\nBuild succeeded!")
    print(f"Output directory: {OUTPUT_DIR}")
