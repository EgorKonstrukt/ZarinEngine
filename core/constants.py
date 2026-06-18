from __future__ import annotations

APP_VERSION = "1.0.0"
APP_VERSION_DISPLAY = f"v{APP_VERSION}"

MAX_FIXED_STEPS = 5

PATH_FIELDS = frozenset({"mesh_path", "material_path", "clip_path", "script_path"})

FRAME_HEADER_SIZE = 4

LOGGER_MAX_ENTRIES = 2000
