from __future__ import annotations
import os
import struct
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer

from editor.constants import EXTENSIONS

ICON_DIR = Path(os.path.expanduser("~")) / ".zarin"
ICON_PATH = ICON_DIR / "zarin_icon.ico"


def _generate_ico(svg_path: str, ico_path: str, sizes: list[int] = None) -> Optional[str]:
    if sizes is None:
        sizes = [32, 64, 256]
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        return None
    ico_path = str(ico_path)
    images = []
    for size in sizes:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(p)
        p.end()
        images.append(img)
    _write_ico(ico_path, images)
    return ico_path


def _write_ico(path: str, images: list[QImage]):
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        offset = 6 + 16 * len(images)
        for img in images:
            data = _qimage_to_bgra_png(img)
            w = img.width() if img.width() < 256 else 0
            h = img.height() if img.height() < 256 else 0
            f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
            offset += len(data)
        for img in images:
            f.write(_qimage_to_bgra_png(img))


def _qimage_to_bgra_png(img: QImage) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return buf.data().data()


def _python_exe() -> str:
    return sys.executable


def _editor_script() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))


def _register_extensions(icon_path: str) -> list[str]:
    import winreg
    registered = []
    for ext, info in EXTENSIONS.items():
        prog_id = info["prog_id"]
        description = info["description"]
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, description)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\DefaultIcon") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, icon_path)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open\command") as key:
                cmd = f'"{_python_exe()}" "{_editor_script()}" "%1"'
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd)
            registered.append(ext)
        except Exception:
            continue
    return registered


def _unregister_extensions() -> list[str]:
    import winreg
    unregistered = []
    for ext, info in EXTENSIONS.items():
        prog_id = info["prog_id"]
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}")
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open\command")
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open")
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell")
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\DefaultIcon")
        except Exception:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}")
        except Exception:
            pass
        unregistered.append(ext)
    return unregistered


def register(svg_path: str) -> list[str]:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    icon_path = _generate_ico(svg_path, str(ICON_PATH))
    if not icon_path:
        return []
    return _register_extensions(icon_path)


def unregister() -> list[str]:
    return _unregister_extensions()


def _is_registered(ext: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}", 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, "")
            return True
    except Exception:
        return False


def status() -> dict[str, bool]:
    return {ext: _is_registered(ext) for ext in EXTENSIONS}
