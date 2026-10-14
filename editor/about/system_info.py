# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import platform
import sys
import time
import datetime
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtSvg import QSvgRenderer
from core.config.constants import APP_VERSION_DISPLAY


def _read_engine_optimization() -> dict:
    try:
        from pathlib import Path
        settings = Path.home() / ".zarin" / "settings.json"
        if settings.exists():
            with open(settings) as f:
                data = json.load(f)
            return data.get("engine", {})
    except Exception:
        pass
    return {}


def _render_logo(target_w: int) -> QPixmap | None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "zarin_logo.svg")
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    vb = renderer.viewBoxF()
    if vb.isEmpty():
        vb = QRectF(0, 0, 512, 512)
    target_h = round(target_w * vb.height() / vb.width())
    pm = QPixmap(target_w, target_h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, target_w, target_h))
    p.end()
    return pm


def _render_icon(size: int) -> QPixmap | None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "zarin_icon.svg")
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def _collect_system_info(parent=None) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("Zarin Engine — System Info")
    lines.append("=" * 60)
    lines.append("")
    lines.append("[Application]")
    lines.append(f"  Version:       {APP_VERSION_DISPLAY}")
    lines.append(f"  Built:         {time.ctime(os.path.getmtime(os.path.abspath(__file__)))}")
    lines.append("")
    lines.append("[Platform]")
    lines.append(f"  OS:            {platform.system()} {platform.release()}")
    lines.append(f"  OS Version:    {platform.version()}")
    lines.append(f"  Machine:       {platform.machine()}")
    lines.append(f"  Processor:     {platform.processor() or 'N/A'}")
    lines.append(f"  Node:          {platform.node()}")
    lines.append("")
    lines.append("[CPU]")
    lines.append(f"  Cores:         {os.cpu_count() or 'N/A'}")
    lines.append("")
    lines.append("[Python]")
    lines.append(f"  Version:       {sys.version.split()[0]}")
    lines.append(f"  Build:         {sys.version.split('(', 1)[1].rstrip(')') if '(' in sys.version else sys.version.split()[1] if len(sys.version.split()) > 1 else 'N/A'}")
    lines.append(f"  Implementation:{sys.version.split('[')[1].split(']')[0] if '[' in sys.version else 'CPython'}")
    gil_enabled = getattr(sys, '_is_gil_enabled', lambda: True)()
    lines.append(f"  GIL:           {'Enabled' if gil_enabled else 'Disabled (nogil)'}")
    jit_enabled = getattr(sys, '_jit_enabled', False)
    lines.append(f"  JIT:           {'Active' if jit_enabled else 'Off'}")
    lines.append(f"  Executable:    {sys.executable}")
    lines.append(f"  Prefix:        {sys.prefix}")
    lines.append("")
    lines.append("[Interpreter Flags]")
    fl = sys.flags
    lines.append(f"  debug:                  {fl.debug}")
    lines.append(f"  inspect:                {fl.inspect}")
    lines.append(f"  interactive:            {fl.interactive}")
    lines.append(f"  optimize:               {fl.optimize}")
    lines.append(f"  dont_write_bytecode:    {fl.dont_write_bytecode}")
    lines.append(f"  no_user_site:           {fl.no_user_site}")
    lines.append(f"  no_site:                {fl.no_site}")
    lines.append(f"  ignore_environment:     {fl.ignore_environment}")
    lines.append(f"  verbose:                {fl.verbose}")
    lines.append(f"  bytes_warning:          {fl.bytes_warning}")
    lines.append(f"  quiet:                  {fl.quiet}")
    lines.append(f"  hash_randomization:     {fl.hash_randomization}")
    lines.append(f"  isolated:               {getattr(fl, 'isolated', 'N/A')}")
    lines.append(f"  dev_mode:               {getattr(fl, 'dev_mode', 'N/A')}")
    lines.append(f"  utf8_mode:              {getattr(fl, 'utf8_mode', 'N/A')}")
    lines.append(f"  warn_default_encoding:  {getattr(fl, 'warn_default_encoding', 'N/A')}")
    lines.append(f"  safe_path:              {getattr(fl, 'safe_path', 'N/A')}")
    lines.append(f"  int_max_str_digits:     {getattr(fl, 'int_max_str_digits', 'N/A')}")
    lines.append("")
    lines.append("[Optimization Config]")
    _eng_cfg = _read_engine_optimization()
    lines.append(f"  python_jit:             {_eng_cfg.get('python_jit', False)}")
    lines.append(f"  python_optimize:        {_eng_cfg.get('python_optimize', 0)}")
    lines.append(f"  python_unbuffered:      {_eng_cfg.get('python_unbuffered', False)}")
    lines.append(f"  python_no_bytecode:     {_eng_cfg.get('python_no_bytecode', False)}")
    lines.append(f"  PYTHON_JIT env:         {os.environ.get('PYTHON_JIT', '(unset)')}")
    lines.append(f"  PYTHONUNBUFFERED env:   {os.environ.get('PYTHONUNBUFFERED', '(unset)')}")
    lines.append(f"  PYTHONDONTWRITEBYTECODE env: {os.environ.get('PYTHONDONTWRITEBYTECODE', '(unset)')}")
    lines.append("")
    gl_info = {}
    gl_exts = []
    try:
        if parent is not None:
            vp = getattr(parent, '_viewport', None)
            if vp is not None:
                gl_info = getattr(vp, '_gl_info_cache', {}) or {}
                gl_exts = getattr(vp, '_gl_extensions_cache', []) or []
    except Exception:
        pass
    lines.append("[OpenGL]")
    lines.append(f"  Renderer:      {gl_info.get('GL_RENDERER', 'Unknown')}")
    lines.append(f"  Vendor:        {gl_info.get('GL_VENDOR', 'Unknown')}")
    lines.append(f"  Version:       {gl_info.get('GL_VERSION', 'Unknown')}")
    major = gl_info.get("GL_MAJOR_VERSION", "?")
    minor = gl_info.get("GL_MINOR_VERSION", "?")
    lines.append(f"  Profile:       Core {major}.{minor}")
    lines.append(f"  Double Buf:    {gl_info.get('GL_DOUBLEBUFFER', '?')}")
    lines.append(f"  Max Texture:   {gl_info.get('GL_MAX_TEXTURE_SIZE', '?')}")
    lines.append(f"  Max Viewport:  {gl_info.get('GL_MAX_VIEWPORT_DIMS', '?')}")
    lines.append(f"  Max Renderbuf: {gl_info.get('GL_MAX_RENDERBUFFER_SIZE', '?')}")
    lines.append(f"  Max Samples:   {gl_info.get('GL_MAX_SAMPLES', '?')}")
    lines.append(f"  Max Draw Bufs: {gl_info.get('GL_MAX_DRAW_BUFFERS', '?')}")
    lines.append(f"  Max Tex Units: {gl_info.get('GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS', '?')}")
    lines.append(f"  Max Vert Atts: {gl_info.get('GL_MAX_VERTEX_ATTRIBS', '?')}")
    lines.append(f"  Max UBO Bind:  {gl_info.get('GL_MAX_UNIFORM_BUFFER_BINDINGS', '?')}")
    lines.append(f"  Uniform Align: {gl_info.get('GL_UNIFORM_BUFFER_OFFSET_ALIGNMENT', '?')}")
    lines.append("")
    if gl_exts:
        lines.append("[OpenGL Extensions]")
        for ext in sorted(gl_exts):
            lines.append(f"  {ext}")
        lines.append("")
    lines.append("[Display]")
    try:
        app = QApplication.instance()
        if app is not None:
            screens = app.screens()
            lines.append(f"  Monitors:      {len(screens)}")
            for i, scr in enumerate(screens):
                g = scr.geometry()
                dpr = scr.devicePixelRatio()
                dpi = scr.logicalDotsPerInch()
                lines.append(f"    [{i}] {scr.name()}: {g.width()}x{g.height()} @ {dpr}x  ({dpi:.0f} DPI)")
            primary = app.primaryScreen()
            if primary:
                g = primary.geometry()
                lines.append(f"  Primary:       {primary.name()} ({g.width()}x{g.height()})")
        else:
            lines.append("  (QApplication not available)")
    except Exception as e:
        lines.append(f"  (unavailable: {e})")
    lines.append("")
    lines.append("[Locale / Timezone]")
    try:
        lines.append(f"  Locale:        {platform.locale()}")
    except Exception:
        lines.append(f"  Locale:        N/A")
    try:
        lines.append(f"  Timezone:      {datetime.datetime.now().astimezone().tzinfo}")
    except Exception:
        lines.append(f"  Timezone:      N/A")
    lines.append("")
    engine = None
    try:
        if parent is not None:
            engine = getattr(parent, '_engine', None)
    except Exception:
        pass
    scene = None
    entity_count = 0
    scene_name = "None"
    if engine is not None:
        scene = getattr(engine, 'scene', None)
        if scene is not None:
            try:
                entity_count = len(scene.get_all_entities())
            except Exception:
                pass
            scene_name = getattr(scene, 'name', 'Unnamed')
    lines.append("[Engine]")
    lines.append(f"  Scene:         {scene_name}")
    lines.append(f"  Entities:      {entity_count}")
    render_mode = "N/A"
    try:
        if parent is not None:
            vp = getattr(parent, '_viewport', None)
            r = getattr(vp, '_renderer', None) if vp is not None else None
            if r is not None:
                rm = r.render_mode
                render_mode = rm.value if hasattr(rm, 'value') else str(rm)
    except Exception:
        pass
    lines.append(f"  Render Mode:   {render_mode}")
    play_mode = False
    try:
        if engine is not None:
            play_mode = getattr(engine, 'play_mode', False)
    except Exception:
        pass
    lines.append(f"  Play Mode:     {play_mode}")
    time_scale = 1.0
    try:
        if engine is not None:
            time_scale = getattr(engine, 'time_scale', 1.0)
    except Exception:
        pass
    lines.append(f"  Time Scale:    {time_scale}")
    lines.append("")
    try:
        from core.ecs import ComponentRegistry
        registered = list(ComponentRegistry._registry.keys())
        lines.append("[ECS Components]")
        lines.append(f"  Registered:    {len(registered)}")
        for name in sorted(registered):
            lines.append(f"    - {name}")
        lines.append("")
    except Exception:
        pass
    lines.append("[Plugins]")
    from editor.about.dialogs import AboutDialog
    lines.append(f"  Count:         {AboutDialog._count_plugins()}")
    plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "plugins")
    try:
        for d in sorted(os.listdir(plugins_dir)):
            full = os.path.join(plugins_dir, d)
            if os.path.isdir(full) and not d.startswith("_"):
                lines.append(f"    - {d}")
    except FileNotFoundError:
        lines.append("    (none found)")
    lines.append("")
    lines.append("[Python Packages]")
    try:
        from importlib.metadata import distributions
        for dist in sorted(distributions(), key=lambda d: d.metadata["Name"].lower()):
            lines.append(f"  {dist.metadata['Name']:30s} {dist.version}")
    except Exception:
        lines.append("  (unavailable)")
    lines.append("")
    lines.append("[Environment]")
    lines.append(f"  PYTHONPATH:    {os.environ.get('PYTHONPATH', '(not set)')}")
    path_val = os.environ.get("PATH", "")
    if len(path_val) > 120:
        path_val = path_val[:120] + "..."
    lines.append(f"  PATH:          {path_val}")
    lines.append(f"  TEMP:          {os.environ.get('TEMP', 'N/A')}")
    lines.append(f"  HOME:          {os.environ.get('HOME') or os.environ.get('USERPROFILE', 'N/A')}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
