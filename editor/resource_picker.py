from __future__ import annotations
import os
import json
import math
import wave
import struct
import threading
import numpy as np
from typing import Optional, Callable
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                              QListWidget, QListWidgetItem, QLabel,
                              QPushButton, QWidget, QSplitter, QFileDialog,
                              QListWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QSize, QRect, QRectF, QPoint, QThread, pyqtSignal, QTimer, QMutex
from PyQt6.QtGui import (QFont, QPixmap, QPainter, QPainterPath, QColor, QPen, QBrush,
                         QFontMetrics, QLinearGradient, QRadialGradient, QIcon, QPalette,
                         QImageReader, QPolygonF, QImage)

_thumbnail_cache: dict[str, QPixmap] = {}
_thumbnail_mutex = QMutex()

from editor.constants import THUMB_SIZE, PREVIEW_SIZE

EXTENSION_FILTERS = {
    "Models (*.obj *.fbx *.stl *.gltf *.glb *.usdz)": (".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz"),
    "Audio (*.wav *.mp3 *.ogg)": (".wav", ".mp3", ".ogg"),
    "Python Scripts (*.py)": (".py",),
    "All Files (*)": (),
}

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _make_icon_bg(base_color: QColor, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, base_color.lighter(140))
    grad.setColorAt(1.0, base_color)
    p.setBrush(QBrush(grad))
    pen = QPen(base_color.darker(130), 1)
    p.setPen(pen)
    r = size * 0.15
    p.drawRoundedRect(QRect(1, 1, size - 2, size - 2), r, r)
    p.end()
    return pm

def _draw_text_centered(painter: QPainter, text: str, rect: QRect, color: QColor):
    painter.setPen(color)
    f = painter.font()
    f.setPixelSize(int(rect.height() * 0.45))
    f.setBold(True)
    painter.setFont(f)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

def _draw_mesh_preview(path: str, size: int) -> Optional[QPixmap]:
    cache_key = f"mesh:{path}:{size}"
    _thumbnail_mutex.lock()
    cached = _thumbnail_cache.get(cache_key)
    _thumbnail_mutex.unlock()
    if cached is not None:
        return cached
    from core.asset_importer import load_obj_async
    loaded: list[Optional[np.ndarray]] = [None]
    indices_loaded: list[Optional[np.ndarray]] = [None]
    error: list[bool] = [False]

    def _on_loaded(data):
        if data is None or len(data.vertices) < 3 or len(data.indices) < 3:
            error[0] = True
            return
        loaded[0] = data.vertices
        indices_loaded[0] = data.indices

    load_obj_async(path, _on_loaded)
    if error[0]:
        return None
    if loaded[0] is None or indices_loaded[0] is None:
        return None
    pm = _draw_mesh_preview_2d(loaded[0], indices_loaded[0], size)
    _thumbnail_mutex.lock()
    _thumbnail_cache[cache_key] = pm
    _thumbnail_mutex.unlock()
    return pm

def _draw_mesh_preview_2d(verts_flat: np.ndarray, idx: np.ndarray, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if len(verts_flat) < 3:
        return pm
    pts = verts_flat.reshape(-1, 3)

    rot_angle = math.radians(-45)
    cos_a = math.cos(rot_angle)
    sin_a = math.sin(rot_angle)
    rotated_pts = []
    for p in pts:
        rx = p[0] * cos_a - p[2] * sin_a
        rz = p[0] * sin_a + p[2] * cos_a
        ry = p[1]
        rotated_pts.append([rx, ry, rz])
    pts_3d = np.array(rotated_pts)

    pts_2d = pts_3d[:, :2].copy()
    cx, cy = pts_2d.mean(axis=0)
    pts_2d -= [cx, cy]
    max_ext = np.abs(pts_2d).max()
    if max_ext < 1e-8:
        return pm
    margin = 4
    scale_px = (size - 2 * margin) / (2 * max_ext)
    pts_2d *= scale_px
    pts_2d += [size // 2, size // 2]
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 180), 1))
    for i in range(0, len(idx), 3):
        for a, b in [(0, 1), (1, 2), (2, 0)]:
            i1, i2 = idx[i + a], idx[i + b]
            x1, y1 = pts_2d[i1]
            x2, y2 = pts_2d[i2]
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
    p.end()
    return pm


_thumbnail_cache: dict[str, QPixmap] = {}
_thumbnail_mutex = QMutex()


def _get_thumbnail(path: str, size: int) -> QPixmap:
    cache_key = f"thumb:{path}:{size}"
    _thumbnail_mutex.lock()
    if cache_key in _thumbnail_cache:
        cached = _thumbnail_cache[cache_key]
        _thumbnail_mutex.unlock()
        return cached
    _thumbnail_mutex.unlock()
    pm = _get_thumbnail_raw(path, size)
    if pm:
        _thumbnail_mutex.lock()
        _thumbnail_cache[cache_key] = pm
        _thumbnail_mutex.unlock()
    return pm


def _draw_mesh_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(70, 130, 200), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 200), 2))
    cx, cy = size // 2, size // 2
    r = size * 0.28
    for i in range(3):
        a1 = math.radians(i * 120 - 90)
        a2 = math.radians((i + 1) * 120 - 90)
        x1 = cx + r * math.cos(a1); y1 = cy + r * math.sin(a1)
        x2 = cx + r * math.cos(a2); y2 = cy + r * math.sin(a2)
        p.drawLine(int(x1), int(y1), int(x2), int(y2))
    p.end()
    return pm

def _read_audio_data(path: str, num_samples: int = 128) -> Optional[list]:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".wav":
            with wave.open(path, "rb") as wf:
                nframes = wf.getnframes()
                sampwidth = wf.getsampwidth()
                nchannels = wf.getnchannels()
                raw = wf.readframes(nframes)
                if sampwidth == 1:
                    fmt = f"<{len(raw)}B"
                    data = struct.unpack(fmt, raw)
                    data = [v - 128 for v in data]
                elif sampwidth == 2:
                    fmt = f"<{len(raw) // 2}h"
                    data = struct.unpack(fmt, raw)
                else:
                    return None
                step = max(1, len(data) // nchannels // num_samples)
        else:
            try:
                import subprocess, tempfile, struct
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                subprocess.run(["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "22050", "-f", "wav", tmp_path],
                               capture_output=True, timeout=10)
                with wave.open(tmp_path, "rb") as wf:
                    nframes = wf.getnframes()
                    raw = wf.readframes(min(nframes, 44100))
                    fmt_s = f"<{len(raw) // 2}h"
                    data = struct.unpack(fmt_s, raw)
                    step = max(1, len(data) // num_samples)
                os.unlink(tmp_path)
            except Exception:
                return None
        peaks = []
        for i in range(0, len(data), step):
            chunk = abs(data[i])
            if chunk > 32767: chunk = 32767
            peaks.append(chunk)
        max_val = max(peaks) if peaks else 1
        return [p / max_val for p in peaks]
    except Exception:
        return None

def _draw_audio_icon(size: int) -> QPixmap:
    return _make_icon_bg(QColor(80, 180, 80), size)

def _draw_audio_waveform(path: str, size: int) -> QPixmap:
    peaks = _read_audio_data(path, size // 2)
    if peaks is None:
        return _draw_audio_icon(size)
    pm = _make_icon_bg(QColor(40, 90, 40), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 4
    w = size - 2 * margin
    h = size - 2 * margin
    mid_y = size // 2
    bar_w = max(1, w // len(peaks))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(100, 220, 100, 220)))
    for i, peak in enumerate(peaks):
        bar_h = max(1, int(peak * h * 0.45))
        x = margin + i * bar_w
        p.drawRect(x, mid_y - bar_h, bar_w, bar_h * 2)
    p.end()
    return pm

def _draw_script_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(200, 140, 50), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 220), 1))
    lines = [(0.25, 0.3, 0.75, 0.3), (0.25, 0.5, 0.75, 0.5), (0.25, 0.7, 0.6, 0.7)]
    for x1, y1, x2, y2 in lines:
        p.drawLine(int(size * x1), int(size * y1), int(size * x2), int(size * y2))
    p.end()
    return pm

def _draw_image_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(100, 150, 200), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 180), 2))
    m = size * 0.2
    p.drawRect(int(m), int(m), int(size - 2 * m), int(size - 2 * m))
    p.drawLine(int(m * 1.3), int(size - m * 1.2), int(size * 0.45), int(size * 0.5))
    p.drawLine(int(size * 0.45), int(size * 0.5), int(size * 0.65), int(size * 0.65))
    p.drawLine(int(size * 0.65), int(size * 0.65), int(size - m * 1.3), int(size * 0.35))
    p.end()
    return pm

def _draw_scene_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(60, 60, 100), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 180), 2))
    cx, cy = size // 2, size // 2
    r = size * 0.3
    p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
    p.drawLine(int(cx - r), int(cy), int(cx + r), int(cy))
    p.drawLine(int(cx), int(cy - r), int(cx), int(cy + r))
    p.end()
    return pm

def _draw_prefab_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(60, 160, 180), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 200), 2))
    m = size * 0.25
    p.drawRect(int(m), int(m), int(size - 2 * m), int(size - 2 * m))
    p.drawLine(int(size * 0.3), int(size * 0.5), int(size * 0.7), int(size * 0.5))
    p.drawLine(int(size * 0.5), int(size * 0.3), int(size * 0.5), int(size * 0.7))
    p.end()
    return pm

def _draw_material_icon(size: int) -> QPixmap:
    return _draw_material_sphere(size, QColor(160, 80, 180))

def _draw_material_sphere(size: int, color: QColor, texture_path: str = "") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    cx, cy = size // 2, size // 2
    r = size * 0.37
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    path = QPainterPath()
    path.addEllipse(rect)
    p.setClipPath(path)
    if texture_path and os.path.exists(texture_path):
        tex_img = QImage(texture_path)
        if not tex_img.isNull():
            tex_pm = QPixmap.fromImage(tex_img.scaled(size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            tw, th = tex_pm.width(), tex_pm.height()
            p.drawPixmap(int(cx - tw / 2), int(cy - th / 2), tex_pm)
    fill = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.2)
    fill.setColorAt(0.0, QColor(255, 255, 255, 180))
    fill.setColorAt(0.3, QColor(255, 255, 255, 80))
    fill.setColorAt(0.7, QColor(0, 0, 0, 40))
    fill.setColorAt(1.0, QColor(0, 0, 0, 160))
    p.setBrush(QBrush(fill))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(rect)
    spec = QRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.5)
    spec.setColorAt(0.0, QColor(255, 255, 255, 120))
    spec.setColorAt(0.5, QColor(255, 255, 255, 20))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(spec))
    p.drawEllipse(rect)
    p.setClipping(False)
    p.setPen(QPen(color.darker(120), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)
    p.end()
    return pm

def _draw_shader_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(100, 100, 120), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 200), 2))
    m = size * 0.2
    p.drawRect(int(m), int(m), int(size - 2 * m), int(size - 2 * m))
    p.drawLine(int(m * 1.2), int(size * 0.45), int(size - m * 1.2), int(size * 0.45))
    p.drawLine(int(size * 0.55), int(m * 1.2), int(size * 0.55), int(size * 0.4))
    p.drawLine(int(size * 0.45), int(size * 0.6), int(size * 0.45), int(size - m * 1.2))
    p.end()
    return pm

def _draw_file_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(140, 140, 150), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 180), 2))
    m = size * 0.2
    p.drawRect(int(m), int(m), int(size - 2 * m), int(size - 2 * m))
    p.end()
    return pm

def _draw_folder_icon(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(200, 180, 60), size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 160), 1))
    m = size * 0.2
    tab_w = size * 0.25
    tab_h = size * 0.1
    body = QRect(int(m), int(m + tab_h), int(size - 2 * m), int(size - m * 2 - tab_h))
    p.drawRect(body)
    p.drawLine(int(m), int(m + tab_h), int(m + tab_w), int(m + tab_h))
    p.drawLine(int(m + tab_w), int(m + tab_h), int(m + tab_w), int(m))
    p.drawLine(int(m + tab_w), int(m), int(body.right()), int(m))
    p.end()
    return pm

def _get_thumbnail_raw(path: str, size: int) -> QPixmap:
    if os.path.isdir(path):
        return _draw_folder_icon(size)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg"):
        reader = QImageReader(path)
        if reader.canRead():
            img = reader.read()
            if img:
                pm = QPixmap.fromImage(img)
                return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
        if ext == ".obj":
            pm = _draw_mesh_preview(path, size)
            if pm: return pm
        return _draw_mesh_icon(size)
    if ext == ".wav":
        return _draw_audio_waveform(path, size)
    if ext in (".mp3", ".ogg"):
        return _draw_audio_icon(size)
    if ext == ".py":
        return _draw_script_icon(size)
    if ext == ".zpes":
        return _draw_scene_icon(size)
    if ext == ".zpep":
        return _draw_prefab_icon(size)
    if ext == ".mat":
        pm = _get_material_thumbnail(path, size)
        if pm: return pm
        return _draw_material_icon(size)
    if ext in (".vert", ".frag"):
        return _draw_shader_icon(size)
    return _draw_file_icon(size)

def _get_material_thumbnail(path: str, size: int) -> Optional[QPixmap]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        props = data.get("properties", {})
        color = props.get("_BaseColor", props.get("albedo_color", [1.0, 1.0, 1.0, 1.0]))
        tex_path = props.get("_BaseMap", props.get("albedo_texture", ""))
        mat_dir = os.path.dirname(os.path.abspath(path))
        if tex_path and not os.path.isabs(tex_path):
            tex_path = os.path.normpath(os.path.join(mat_dir, tex_path))
        r = _clamp(int(color[0] * 255), 0, 255)
        g = _clamp(int(color[1] * 255), 0, 255)
        b = _clamp(int(color[2] * 255), 0, 255)
        return _draw_material_sphere(size, QColor(r, g, b), tex_path)
    except Exception:
        return None

def _render_material_thumbnail(size: int, albedo: list[float], metallic: float = 0.0,
                                smoothness: float = 0.5, emission: Optional[list[float]] = None,
                                emit_intensity: float = 0.0,
                                texture_path: Optional[str] = None) -> Optional[QPixmap]:
    return None

def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024: return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024: return f"{size_bytes / 1024:.1f} KB"
    else: return f"{size_bytes / (1024 * 1024):.1f} MB"

class _PopulateWorker(QThread):
    items_ready = pyqtSignal(object)

    def __init__(self, project_root: str, extensions: tuple, filter_text: str):
        super().__init__()
        self._project_root = project_root
        self._extensions = extensions
        self._filter_text = filter_text

    def run(self):
        items_data = []
        for root, dirs, files in os.walk(self._project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if self._extensions and ext not in self._extensions:
                    continue
                if self._filter_text and self._filter_text.lower() not in f.lower():
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self._project_root)
                try:
                    file_size = os.path.getsize(full_path)
                except OSError:
                    file_size = 0
                items_data.append((full_path, f, rel_path, file_size))
        self.items_ready.emit(items_data)


class _ThumbnailLoader(QThread):
    thumbnail_loaded = pyqtSignal(int, object)

    def __init__(self, items: list[tuple], thumb_size: int):
        super().__init__()
        self._items = items
        self._thumb_size = thumb_size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        for idx, (full_path, filename, rel_path, file_size) in enumerate(self._items):
            if self._cancelled:
                return
            cache_key = f"thumb:{full_path}:{self._thumb_size}"
            _thumbnail_mutex.lock()
            exists = cache_key in _thumbnail_cache
            _thumbnail_mutex.unlock()
            if not exists:
                pm = _get_thumbnail_raw(full_path, self._thumb_size)
                if pm:
                    _thumbnail_mutex.lock()
                    _thumbnail_cache[cache_key] = pm
                    _thumbnail_mutex.unlock()
            if self._cancelled:
                return
            self.thumbnail_loaded.emit(idx, full_path)


class ResourcePickerDialog(QDialog):
    def __init__(self, title: str, filter_str: str, project_root: str = ".", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 480)
        self.resize(760, 560)
        self._filter_str = filter_str
        self._project_root = os.path.abspath(project_root)
        self._selected_path: Optional[str] = None
        self._extensions = self._parse_extensions(filter_str)
        self._search_text = ""
        self._setup_ui()
        self._start_populate("")

    def _parse_extensions(self, filter_str: str) -> tuple:
        for key, exts in EXTENSION_FILTERS.items():
            if filter_str.lower() in key.lower():
                return exts
        return EXTENSION_FILTERS.get(filter_str, ())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search_layout = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search assets...")
        self._search.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        search_layout.addWidget(browse_btn)
        layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._list.setGridSize(QSize(THUMB_SIZE + 24, THUMB_SIZE + 44))
        self._list.setWordWrap(True)
        self._list.setSpacing(4)
        self._list.setUniformItemSizes(True)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        list_layout.addWidget(self._list)
        splitter.addWidget(list_container)

        preview_container = QWidget()
        preview_container.setFixedWidth(220)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(8, 0, 0, 0)
        preview_layout.setSpacing(6)

        self._preview_icon = QLabel()
        self._preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_icon.setFixedSize(PREVIEW_SIZE + 20, PREVIEW_SIZE + 20)
        self._preview_icon.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")
        preview_layout.addWidget(self._preview_icon)

        self._preview_name = QLabel()
        self._preview_name.setWordWrap(True)
        self._preview_name.setStyleSheet("font-weight: bold; font-size: 12px; color: #ddd;")
        preview_layout.addWidget(self._preview_name)

        self._preview_info = QLabel()
        self._preview_info.setWordWrap(True)
        self._preview_info.setStyleSheet("font-size: 11px; color: #999;")
        preview_layout.addWidget(self._preview_info)

        preview_layout.addStretch()

        self._select_btn = QPushButton("Select")
        self._select_btn.clicked.connect(self._accept_selection)
        self._select_btn.setEnabled(False)
        preview_layout.addWidget(self._select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        preview_layout.addWidget(cancel_btn)

        splitter.addWidget(preview_container)
        splitter.setSizes([500, 220])
        layout.addWidget(splitter, 1)

        self._update_preview(None)

    def _start_populate(self, filter_text: str):
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        if hasattr(self, '_loader') and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait()
        self._search_text = filter_text
        self._list.clear()
        self._pending_items: list[tuple[str, str, str, int]] = []
        self._item_paths: dict[int, str] = {}
        self._worker = _PopulateWorker(
            self._project_root,
            self._extensions,
            filter_text,
        )
        self._worker.items_ready.connect(self._on_items_ready)
        self._worker.start()

    def _on_items_ready(self, items_data: list):
        self._pending_items = items_data
        for idx, (full_path, filename, rel_path, file_size) in enumerate(items_data):
            placeholder = _draw_file_icon(THUMB_SIZE)
            item = QListWidgetItem(QIcon(placeholder), os.path.splitext(filename)[0])
            item.setData(Qt.ItemDataRole.UserRole, full_path)
            item.setToolTip(f"{rel_path}\n{_format_size(file_size)}")
            self._list.addItem(item)
            self._item_paths[self._list.count() - 1] = full_path
        if items_data:
            self._start_thumbnail_loader()

    def _start_thumbnail_loader(self):
        if not self._pending_items:
            return
        if hasattr(self, '_loader') and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait()
        self._loader = _ThumbnailLoader(self._pending_items, THUMB_SIZE)
        self._loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        self._loader.start()

    def _on_thumbnail_loaded(self, idx: int):
        if idx >= self._list.count():
            return
        item = self._list.item(idx)
        path = self._item_paths.get(idx)
        if not path:
            return
        cache_key = f"thumb:{path}:{THUMB_SIZE}"
        _thumbnail_mutex.lock()
        pm = _thumbnail_cache.get(cache_key)
        _thumbnail_mutex.unlock()
        if pm:
            item.setIcon(QIcon(pm))

    def _on_search(self, text: str):
        self._start_populate(text)

    def _on_selection_changed(self):
        items = self._list.selectedItems()
        if items:
            path = items[0].data(Qt.ItemDataRole.UserRole)
            self._update_preview(path)
            self._select_btn.setEnabled(True)
        else:
            self._update_preview(None)
            self._select_btn.setEnabled(False)

    def _update_preview(self, path: Optional[str]):
        if not path or not os.path.isfile(path):
            self._preview_icon.clear()
            self._preview_icon.setText("No selection")
            self._preview_icon.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px; color: #666;")
            self._preview_name.setText("")
            self._preview_info.setText("")
            return

        self._preview_icon.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")
        thumb = _get_thumbnail(path, PREVIEW_SIZE)
        self._preview_icon.setPixmap(thumb)

        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        size_str = _format_size(os.path.getsize(path))

        type_map = {
            ".obj": "3D Model", ".fbx": "3D Model", ".stl": "3D Model", ".usdz": "3D Model", ".gltf": "3D Model", ".glb": "3D Model",
            ".wav": "Audio", ".mp3": "Audio", ".ogg": "Audio",
            ".py": "Python Script",
            ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
            ".zpes": "Scene", ".zpep": "Prefab", ".mat": "Material",
            ".vert": "Vertex Shader", ".frag": "Fragment Shader",
        }
        type_name = type_map.get(ext, "File")

        info_lines = [f"Type: {type_name}", f"Size: {size_str}"]
        if ext in (".png", ".jpg", ".jpeg"):
            reader = QImageReader(path)
            if reader.canRead():
                sz = reader.size()
                info_lines.append(f"Dimensions: {sz.width()}x{sz.height()}")
        info_lines.append(f"Path: {os.path.relpath(path, self._project_root)}")
        self._preview_name.setText(name)
        self._preview_info.setText("\n".join(info_lines))

    def closeEvent(self, event):
        if hasattr(self, '_loader') and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait()
        super().closeEvent(event)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Resource", "", self._filter_str)
        if path:
            self._selected_path = path
            self.accept()

    def _accept_selection(self):
        items = self._list.selectedItems()
        if items:
            self._selected_path = items[0].data(Qt.ItemDataRole.UserRole)
            self.accept()
        elif self._list.count() == 0 and self._search.text():
            self._on_browse()
        else:
            self.reject()

    def selected_path(self) -> Optional[str]:
        return self._selected_path

def pick_resource(parent, title: str, filter_str: str, current_path: str = "",
                  project_root: str = ".") -> Optional[str]:
    if current_path and os.path.exists(current_path):
        project_root = os.path.dirname(current_path)
    dlg = ResourcePickerDialog(title, filter_str, project_root, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selected_path()
    return None
