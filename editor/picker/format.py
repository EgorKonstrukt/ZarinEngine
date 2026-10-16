# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import json
import math
import os
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

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

def _draw_audio_icon(size: int) -> QPixmap:
    return _make_icon_bg(QColor(80, 180, 80), size)

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

def _draw_font_placeholder(size: int) -> QPixmap:
    pm = _make_icon_bg(QColor(70, 120, 200), size)
    p = QPainter(pm)
    _draw_text_centered(p, "Aa", QRect(0, 0, size, size), QColor(255, 255, 255))
    p.end()
    return pm

def _draw_vector_placeholder(path: str, size: int) -> Optional[QPixmap]:
    if os.path.isdir(path):
        return _draw_folder_icon(size)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff",
               ".webp", ".hdr"):
        return _draw_image_icon(size)
    if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
        return _draw_mesh_icon(size)
    if ext in (".wav", ".mp3", ".ogg", ".flac", ".aiff", ".m4a"):
        return _draw_audio_icon(size)
    if ext == ".py":
        return _draw_script_icon(size)
    if ext == ".zpes":
        return _draw_scene_icon(size)
    if ext == ".zpep":
        return _draw_prefab_icon(size)
    if ext in (".mat", ".zpem"):
        return _draw_material_icon(size)
    if ext in (".shader", ".vert", ".frag", ".compute"):
        return _draw_shader_icon(size)
    if ext in (".animclip", ".animcontroller"):
        return _draw_file_icon(size)
    if ext in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"):
        return _draw_font_placeholder(size)
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
