# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF
from core.config.constants import APP_VERSION_DISPLAY
from core.input.constants import (KEY_W, KEY_A, KEY_S, KEY_D, KEY_Q, KEY_E, KEY_R, KEY_F,
                                  KEY_SHIFT, KEY_DELETE, KEY_CTRL, KEY_ALT, KEY_SPACE,
                                  MOUSE_L, MOUSE_R, MOUSE_M, MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE)

IPC_HOST = "127.0.0.1"
IPC_PORT = 9101

PROJECTS_DB_PATH = os.path.join(str(Path.home()), ".zarin", "projects.json")

MIN_THUMB = 24
MAX_THUMB = 128
VIEW_ICON = 0
VIEW_LIST = 1
VIEW_DETAILS = 2

THUMB_SIZE = 80
PREVIEW_SIZE = 160

EXTENSIONS = {
    ".zpes": {
        "description": "Zarin Engine Scene",
        "prog_id": "ZarinEngine.Scene",
    },
    ".zpep": {
        "description": "Zarin Engine Prefab",
        "prog_id": "ZarinEngine.Prefab",
    },
    ".zterr": {
        "description": "Zarin Engine Terrain Graph",
        "prog_id": "ZarinEngine.TerrainGraph",
    },
}

SPLASH_WIDTH = 640
SPLASH_HEIGHT = 420
SPLASH_RADIUS = 18
SPLASH_OPACITY = 1.0
SPLASH_WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint |
    Qt.WindowType.WindowStaysOnTopHint |
    Qt.WindowType.SplashScreen
)

LOGO_TARGET_WIDTH = 620
LOGO_VIEWBOX = QRectF(0, 0, 700, 260)

PROGRESS_BAR_WIDTH = 582
PROGRESS_BAR_HEIGHT = 12
PROGRESS_BAR_Y_OFFSET = 60
PROGRESS_BAR_RADIUS = 4
PROGRESS_FILL_RADIUS = 3

STATUS_TEXT_Y_OFFSET = 85
STATUS_TEXT_MARGIN = 30

LOGO_Y = 12
DID_YOU_KNOW_Y = 245
VERSION_Y = 275
ACCENT_BAR_Y = 305

DID_YOU_KNOW_WIDTH_MAX = 620

TIPS = [
    "Did you know? Press Ctrl+S to save — scenes are JSON, safe to commit to git.",
    "Did you know? Shift+F10 toggles Play — Pause + Step to debug frame by frame.",
    "Did you know? Hold right mouse + WASD to fly, Q/E down/up, Shift for speed.",
    "Did you know? Press F to focus selection, Delete to remove, F2 to rename.",
    "Did you know? Press Q/W/E/R for No/Move/Rotate/Scale gizmo modes.",
    "Did you know? Snap is ON — hold Ctrl while dragging to move freely.",
    "Did you know? Tune snap steps T/R/S in the viewport toolbar for precise layout.",
    "Did you know? Ctrl+D duplicates, Ctrl+C/Ctrl+V copy-pastes entities.",
    "Did you know? Right-click the viewport - Create spawns lights, physics, UI.",
    "Did you know? Drag a .zpep from Project into the viewport to instantiate it.",
    "Did you know? Save any subtree as prefab to reuse enemies, pickups, UI.",
    "Did you know? Edit scripts during Play — hot-reload keeps Inspector values.",
    "Did you know? Annotate float with Range(0,10) to get a slider in Inspector.",
    "Did you know? Add _inspector_buttons to call script methods from Inspector.",
    "Did you know? Type a field as 'Entity' to get an entity picker in Inspector.",
    "Did you know? Input, KeyCode, Vec3 work in scripts with zero imports.",
    "Did you know? Double-click a .py in Project to edit it, Check validates it.",
    "Did you know? Lower the TS slider to 0.1 for slow-motion physics debugging.",
    "Did you know? Prefer Box/Sphere colliders — MeshCollider is for static only.",
    "Did you know? Freeze Rigidbody axes for top-down games and 2.5D platformers.",
    "Did you know? Use CharacterController for move, jump, slope limit and steps.",
    "Did you know? Audio min/max spheres show 3D falloff directly in viewport.",
    "Did you know? Spatial blend 0 = flat 2D sound, 1 = full 3D positional audio.",
    "Did you know? Profiler finds the slow system — export SVG flamegraph to share.",
    "Did you know? Console groups duplicates — filter by level to find real errors.",
    "Did you know? Click any Undo History entry to jump the scene to that state.",
    "Did you know? Ctrl+Z / Ctrl+Shift+Z undoes entities, Inspector and files.",
    "Did you know? Corner Axis Gizmo clicks snap the camera to that axis.",
    "Did you know? Drag in empty viewport to area-select multiple entities.",
    "Did you know? Shaded+Wireframe mode reveals z-fighting and hidden geometry.",
    "Did you know? Toggle 2D / Ortho in the toolbar for UI and pixel-perfect work.",
    "Did you know? .import files remember scale, normals, filter per asset.",
    "Did you know? Drop FBX, GLTF, OBJ or BLEND into Project to import it.",
    "Did you know? Host Collaboration to co-edit — peers see cursors and gizmos.",
    "Did you know? Shaders recompile live — edit .shader and see it instantly.",
    "Did you know? Ctrl+Shift+B builds a standalone exe via Nuitka.",
    "Did you know? Tags, layers and parenting filter logic, cameras and search.",
    "Did you know? Draw debug lines from any script via gizmo_lines(), no Play needed.",
    "Did you know? Curve editor: double-click adds a key, F fits the view.",
    "Did you know? Script Editor: Ctrl+Q for docs, Ctrl+= / Ctrl+- to zoom.",
]

BG_GRADIENT = [
    (0.00, 140, 110, 200, 170),
    (0.20, 110, 85, 165, 172),
    (0.45, 70, 60, 120, 175),
    (0.70, 42, 40, 78, 175),
    (1.00, 24, 24, 48, 175),
]

GLOW_SPOTS = [
    (255, 140, 0, 55),
    (220, 20, 60, 45),
    (139, 195, 74, 40),
    (120, 144, 156, 35),
]

LOGO_GLOW = (200, 150, 255, 50)
CENTER_GLOW = (208, 208, 232, 18)

TEXT_TIP = (180, 195, 220, 255)
TEXT_VERSION = (255, 210, 100, 255)
TEXT_STATUS = (208, 208, 232, 255)

ACCENT_BAR_COLORS = [
    (0.00, 255, 140, 0, 255),
    (0.25, 220, 20, 60, 255),
    (0.50, 139, 195, 74, 255),
    (0.75, 120, 144, 156, 255),
    (1.00, 255, 140, 0, 255),
]

PB_TRACK = (62, 62, 100, 255)
PB_TRACK_FILL = (24, 24, 48, 255)

PB_FILL_COLORS = [
    (0.00, 255, 179, 71, 255),
    (0.40, 220, 20, 60, 255),
    (0.70, 139, 195, 74, 255),
    (1.00, 120, 144, 156, 255),
]
