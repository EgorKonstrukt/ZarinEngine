# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import sys
import os
import traceback
import json
import multiprocessing
import threading
import time
from datetime import datetime

from PyQt6.QtGui import QSurfaceFormat

try:
    if __compiled__:
        sys.frozen = True
except NameError:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SCENE = "SampleScene.zpes"

_LOG_FILE = None


def _log(msg: str):
    global _LOG_FILE
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line)
    if _LOG_FILE is None:
        try:
            _LOG_FILE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_diag.txt"), "w", encoding="utf-8")
        except Exception:
            pass
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")
        _LOG_FILE.flush()


def excepthook(exc_type, exc_value, exc_traceback):
    from core.foundation.logger import Logger
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    Logger.error(f"Unhandled exception: {exc_value}\n{tb_str}")
    _log(f"Unhandled exception: {exc_value}")


sys.excepthook = excepthook

from editor.bug_report import install_hooks as _install_bug_hooks
_install_bug_hooks()


def _resolve_startup_scene(project_root: str) -> str:
    _log(f"project_root: {project_root}")

    # 1. CLI argument
    if len(sys.argv) > 1:
        arg_path = sys.argv[1]
        _log(f"CLI arg: {arg_path}")
        if os.path.exists(arg_path):
            return arg_path

    # 2. BuildSettings.json вЂ” first scene in list
    build_settings_path = os.path.join(project_root, "BuildSettings.json")
    _log(f"Checking BuildSettings at: {build_settings_path}  exists={os.path.exists(build_settings_path)}")
    if os.path.exists(build_settings_path):
        try:
            with open(build_settings_path, "r") as f:
                bs = json.load(f)
            scenes = bs.get("scenes", [])
            _log(f"BuildSettings scenes: {scenes}")
            if scenes:
                startup = scenes[0]
                _log(f"Raw startup scene: {repr(startup)}")
                for prefix in ("scenes/", "scenes\\"):
                    if startup.startswith(prefix):
                        startup = startup[len(prefix):]
                        break
                if not os.path.isabs(startup):
                    startup = os.path.join(project_root, "scenes", startup)
                _log(f"Resolved scene path: {startup}  exists={os.path.exists(startup)}")
                if os.path.exists(startup):
                    return startup
        except Exception as e:
            _log(f"Error reading BuildSettings: {e}")

    # 3. ProjectSettings.json вЂ” legacy default_scene
    settings_path = os.path.join(project_root, "ProjectSettings.json")
    _log(f"Checking ProjectSettings at: {settings_path}  exists={os.path.exists(settings_path)}")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                ps = json.load(f)
            sp = ps.get("project", {}).get("default_scene", "")
            _log(f"ProjectSettings default_scene: {sp}")
            if sp:
                full = os.path.join(project_root, sp) if not os.path.isabs(sp) else sp
                _log(f"Resolved default_scene: {full}  exists={os.path.exists(full)}")
                if os.path.exists(full):
                    return full
        except Exception as e:
            _log(f"Error reading ProjectSettings: {e}")

    # 4. Fallback
    fallback = os.path.join(project_root, "scenes", DEFAULT_SCENE)
    _log(f"Using fallback: {fallback}  exists={os.path.exists(fallback)}")
    if os.path.exists(fallback):
        return fallback
    return DEFAULT_SCENE


def _deduce_project_root(scene_path: str, fallback: str) -> str:
    try:
        ap = os.path.abspath(scene_path)
        start = os.path.dirname(ap)
        cur = start
        for _ in range(5):
            for marker in ("ProjectSettings.json", "BuildSettings.json"):
                if os.path.isfile(os.path.join(cur, marker)):
                    return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        low = ap.replace("\\", "/").lower()
        for token in ("/assets/", "/scenes/"):
            idx = low.rfind(token)
            if idx > 0:
                return ap[:idx]
        if start:
            return start
    except Exception:
        pass
    return fallback


_DEFERRED_PLUGIN_TOPS = (
    "example_plugin",
    "mesh_editor_plugin",
    "network_plugin",
    "physics_drag_plugin",
    "physics_visualisation_plugin",
    "plotter_plugin",
    "zarin_mcp",
)

_PHYSICS_MODULE = "plugins.physics_plugin"


def _collect_plugin_jobs():
    import importlib
    import pkgutil
    jobs = []
    try:
        pkg = importlib.import_module("plugins")
        try:
            entries = list(pkgutil.iter_modules(pkg.__path__))
        except Exception:
            entries = []
        for _imp, modname, ispkg in entries:
            if modname.startswith("_"):
                continue
            jobs.append("plugins." + modname)
            if ispkg:
                try:
                    subpkg = importlib.import_module("plugins." + modname)
                except Exception as e:
                    _log(f"Plugin package skipped: {modname}: {e}")
                    continue
                try:
                    subs = list(pkgutil.iter_modules(subpkg.__path__))
                except Exception:
                    continue
                for _, subname, _ in subs:
                    if not subname.startswith("_"):
                        jobs.append(f"plugins.{modname}.{subname}")
    except Exception as e:
        _log(f"Plugin scan failed: {e}")
    return jobs


def _split_deferred(jobs):
    critical = []
    deferred = []
    for module_name in jobs:
        top = module_name.split(".")[1] if module_name.startswith("plugins.") else ""
        if top in _DEFERRED_PLUGIN_TOPS:
            deferred.append(module_name)
        else:
            critical.append(module_name)
    return critical, deferred


def _start_physics_load(engine):
    state = {}
    def _run():
        try:
            engine.plugin_manager.load_module(_PHYSICS_MODULE)
            state["ok"] = True
        except Exception as e:
            state["error"] = e
    thr = threading.Thread(target=_run, name="player-physics-load", daemon=True)
    thr.start()
    return thr, state


def _load_deferred(engine, modules, viewport):
    if not modules:
        return
    try:
        before = set(engine.plugin_manager._plugins.keys())
    except Exception:
        before = set()
    for module_name in modules:
        try:
            engine.plugin_manager.load_module(module_name)
        except Exception as e:
            _log(f"Deferred plugin failed: {module_name}: {e}")
    try:
        added = [p for p in engine.plugin_manager.get_all() if p.NAME not in before]
    except Exception:
        added = []
    if not added:
        return
    try:
        scene_now = engine.scene
    except Exception:
        scene_now = None
    try:
        playing = bool(engine.play_mode)
    except Exception:
        playing = False
    for plugin in added:
        try:
            if scene_now is not None:
                plugin.on_scene_loaded(scene_now)
        except Exception as e:
            _log(f"Deferred scene hook failed: {plugin.NAME}: {e}")
        try:
            if viewport is not None:
                plugin.on_viewport_ready(viewport)
        except Exception as e:
            _log(f"Deferred viewport hook failed: {plugin.NAME}: {e}")
        try:
            if playing:
                plugin.on_play_start()
        except Exception as e:
            _log(f"Deferred play hook failed: {plugin.NAME}: {e}")
    _log(f"Deferred plugins ready: {[p.NAME for p in added]}")


def main():
    _t_start = time.perf_counter()
    multiprocessing.freeze_support()
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    QApplication.setAttribute(Qt.ApplicationAttribute(79))
    app = QApplication(sys.argv)
    app.setApplicationName("Zarin Player")
    app.setOrganizationName("Zarin")
    app.setStyle("Fusion")

    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setVersion(4, 6)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    from core.config.config import get_global_config
    _cfg = get_global_config()
    fmt.setSwapInterval(0 if not _cfg.get("rendering.vsync", True) else 1)
    QSurfaceFormat.setDefaultFormat(fmt)

    from core.engine.engine import Engine
    from core.engine.game_viewport import GameViewport
    from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
    from PyQt6.QtCore import QTimer
    from editor.splash import SplashScreen

    splash = SplashScreen(show_tip=False, footer="Powered by Zarin Engine")
    splash.set_total_steps(6)
    splash.show()
    app.processEvents()
    _log(f"Splash shown in {(time.perf_counter() - _t_start) * 1000:.0f}ms")

    code_root = os.path.dirname(os.path.abspath(__file__))
    _log(f"__file__ = {__file__}")
    _log(f"sys.executable = {sys.executable}")
    _log(f"project_root = {code_root}")
    _log(f"CWD = {os.getcwd()}")
    _log(f"args = {sys.argv}")

    splash.advance("Resolving scene...")
    app.processEvents()
    scene_path = _resolve_startup_scene(code_root)
    _log(f"Final scene_path: {scene_path}")
    project_root = _deduce_project_root(scene_path, code_root)
    _log(f"Project root: {project_root}")

    splash.advance("Initializing engine...")
    app.processEvents()
    engine = Engine()
    engine._project_path = code_root
    engine.initialize()
    from core.audio.audio_system import AudioSystem
    audio = AudioSystem.instance()
    if audio:
        audio.apply_project_audio_config()
    build_settings_path = os.path.join(code_root, "BuildSettings.json")
    build_plugins = []
    if os.path.exists(build_settings_path):
        try:
            with open(build_settings_path) as f:
                bs = json.load(f)
            build_plugins = bs.get("build_plugins", [])
        except Exception as e:
            _log(f"Error reading BuildSettings plugins: {e}")
    _log(f"Build plugins: {build_plugins}")
    deferred = []
    if build_plugins:
        for name in build_plugins:
            module_name = "plugins." + name if not name.startswith("plugins.") else name
            try:
                engine.plugin_manager.load_module(module_name)
            except Exception as e:
                _log(f"Plugin failed: {module_name}: {e}")
    else:
        splash.advance("Loading plugins...")
        app.processEvents()
        jobs = _collect_plugin_jobs()
        critical, deferred = _split_deferred(jobs)
        phys_thr = None
        phys_state = {}
        rest = list(critical)
        if _PHYSICS_MODULE in rest:
            rest.remove(_PHYSICS_MODULE)
            phys_thr, phys_state = _start_physics_load(engine)
        for module_name in rest:
            try:
                engine.plugin_manager.load_module(module_name)
            except Exception as e:
                _log(f"Plugin failed: {module_name}: {e}")
        if phys_thr is not None:
            _t_phys = time.perf_counter()
            phys_thr.join()
            _log(f"Physics load joined in {(time.perf_counter() - _t_phys) * 1000:.0f}ms")
            if phys_state.get("error") is not None and engine.plugin_manager.get("PhysicsPlugin") is None:
                try:
                    engine.plugin_manager.load_module(_PHYSICS_MODULE)
                except Exception as e:
                    _log(f"Physics retry failed: {e}")
    _log(f"Registered plugins: {list(engine.plugin_manager._plugins.keys())}")
    physics = engine.plugin_manager.get("PhysicsPlugin")
    if physics:
        _log(f"PhysicsPlugin: solver={type(physics._solver).__name__ if physics._solver else None}, physics_scene={physics._physics_scene is not None}, mode={physics._simulation_mode}, enabled={physics._enabled}")
    else:
        _log("PhysicsPlugin: NOT FOUND")

    engine.project_root = project_root

    splash.advance("Building window...")
    app.processEvents()
    window = QMainWindow()
    window.setWindowTitle("Zarin Player")
    container = QWidget()
    window.setCentralWidget(container)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    viewport = GameViewport(engine, window)
    engine.viewport = viewport
    layout.addWidget(viewport)

    screen = app.primaryScreen()
    if screen:
        window.resize(screen.size() * 0.8)
    else:
        window.resize(1280, 720)

    splash.advance("Loading scene...")
    app.processEvents()
    _log(f"Loading scene: {scene_path}")
    if os.path.exists(scene_path):
        scene = engine.load_scene(scene_path)
        _log(f"engine.load_scene returned: {scene}")
        if scene:
            _log(f"Scene loaded OK: {scene_path}")
        else:
            _log(f"Scene FAILED to load (returned None)")
    else:
        _log(f"Startup scene NOT FOUND: {scene_path}")

    splash.advance("Starting game...")
    app.processEvents()
    _log(f"Starting play after {(time.perf_counter() - _t_start) * 1000:.0f}ms")
    if engine.scene is not None:
        engine.start_play()
        _log(f"start_play done")
        physics = engine.plugin_manager.get("PhysicsPlugin")
        if physics:
            _log(f"After start_play: physics_scene={physics._physics_scene is not None}, bodies_loaded={len(physics._physics_scene._entity_to_body) if physics._physics_scene else 0}")

    window.show()
    SplashScreen.hide_splash()

    if deferred:
        QTimer.singleShot(0, lambda: _load_deferred(engine, deferred, viewport))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
