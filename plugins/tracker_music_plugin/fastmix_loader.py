# Lazy loader for the compiled fastmix extension.
#
# Keeps normal startup cheap: import attempt only, no compiler invocation.
# Heavy auto-build (subprocess) is opt-in via ensure_fastmix(auto_build=True),
# called from the audio render hot path in a worker thread.

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))

_lock = threading.Lock()
_cached = {"mod": None, "tried_build": False}


def _try_import():
    # 1) normal package-relative import (works when loaded as a package)
    try:
        return importlib.import_module(".fastmix", __package__ or "tracker_music_plugin")
    except Exception:
        pass
    # 2) fully-qualified fallbacks for different plugin load schemes
    for name in ("plugins.tracker_music_plugin.fastmix", "tracker_music_plugin.fastmix"):
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    # 3) direct file load from this directory (no sys.path side effects)
    try:
        import importlib.machinery as _mach

        for fn in os.listdir(_HERE):
            if fn.startswith("fastmix.") and (fn.endswith(".pyd") or fn.endswith(".so")):
                path = os.path.join(_HERE, fn)
                loader = _mach.ExtensionFileLoader("zarin_tracker_fastmix", path)
                spec = _mach.ModuleSpec("zarin_tracker_fastmix", loader, origin=path)
                mod = importlib.util.module_from_spec(spec)
                loader.exec_module(mod)
                return mod
    except Exception:
        pass
    return None


def get_fastmix():
    """Return compiled fastmix module or None (no build attempted)."""
    if _cached["mod"] is not None:
        return _cached["mod"]
    with _lock:
        if _cached["mod"] is not None:
            return _cached["mod"]
        mod = _try_import()
        if mod is not None:
            _cached["mod"] = mod
        return mod


def ensure_fastmix(auto_build: bool = True, timeout: int = 300):
    """Return fastmix module, optionally building it once via subprocess.

    Safe to call from render worker threads. Never raises.
    """
    mod = get_fastmix()
    if mod is not None:
        return mod
    if not auto_build:
        return None
    with _lock:
        if _cached["mod"] is not None:
            return _cached["mod"]
        if _cached["tried_build"]:
            return None
        _cached["tried_build"] = True
    try:
        script = os.path.join(_HERE, "build_fastmix.py")
        if not os.path.isfile(script):
            return None
        subprocess.run(
            [sys.executable, script],
            cwd=_HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None
    with _lock:
        _cached["tried_build"] = False  # allow retry once per process is fine
        mod = _try_import()
        if mod is not None:
            _cached["mod"] = mod
        else:
            _cached["tried_build"] = True
        return mod
