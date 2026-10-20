# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SIZES = (16, 32, 48, 256)
_BAD = '<>:"/\\|?*'
_ICON_EXTS = (".svg", ".png", ".bmp", ".jpg", ".jpeg", ".ico")


def exe_name(game_title: str) -> str:
    try:
        name = "".join("_" if c in _BAD else c for c in str(game_title or "")).strip().strip(".")
    except Exception:
        name = ""
    return name or "ZarinPlayer"


def resolve_icon_source(icon_opt, base: Path):
    cands = []
    if icon_opt:
        try:
            rel = Path(str(icon_opt))
            cands.append(rel if rel.is_absolute() else Path(base) / rel)
            cands.append(ROOT / rel)
        except Exception:
            pass
    cands.append(ROOT / "zarin_logo.svg")
    for cand in cands:
        try:
            if cand.is_file() and cand.suffix.lower() in _ICON_EXTS:
                return cand
        except Exception:
            continue
    return None


def _square(img, size: int):
    from PySide6.QtGui import QImage, QPainter, QColor
    from PySide6.QtCore import Qt
    scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if scaled.width() == size and scaled.height() == size:
        return scaled
    out = QImage(size, size, QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))
    p = QPainter(out)
    p.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def _raster(src: Path, size: int):
    from PySide6.QtGui import QImage, QPainter, QColor
    if src.suffix.lower() == ".svg":
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(str(src))
        if not renderer.isValid():
            return None
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        renderer.render(p)
        p.end()
        return img
    img = QImage(str(src))
    if img.isNull():
        return None
    return _square(img, size)


def _png_bytes(img) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data().data())


def make_ico(src: Path, dest: Path) -> bool:
    try:
        if src.suffix.lower() == ".ico":
            dest.write_bytes(src.read_bytes())
            return True
        imgs = []
        for size in _SIZES:
            img = _raster(src, size)
            if img is None or img.isNull():
                return False
            imgs.append(img)
        blobs = [_png_bytes(img) for img in imgs]
        with open(dest, "wb") as f:
            f.write(struct.pack("<HHH", 0, 1, len(imgs)))
            offset = 6 + 16 * len(imgs)
            for img, blob in zip(imgs, blobs):
                w = img.width() if img.width() < 256 else 0
                h = img.height() if img.height() < 256 else 0
                f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset))
                offset += len(blob)
            for blob in blobs:
                f.write(blob)
        return True
    except Exception:
        return False


def prepare_game_icon(icon_opt, base, work: Path):
    try:
        src = resolve_icon_source(icon_opt, Path(base))
    except Exception:
        src = None
    if src is None:
        return None, None
    try:
        ico = Path(work) / "_build_game.ico"
        if not make_ico(src, ico):
            return None, None
        return str(ico), (str(src), "game_icon" + src.suffix.lower())
    except Exception:
        return None, None
