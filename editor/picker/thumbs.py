# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import collections
import os
from typing import Optional
from PyQt6.QtCore import Q_ARG, QMetaObject, QObject, QMutex, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QPixmap
from editor.constants import THUMB_SIZE
from editor.thumb_cache import load_thumb_disk, save_thumb_disk, thumb_disk_key
from editor.picker.format import _draw_audio_icon, _draw_file_icon, _draw_folder_icon, _draw_font_placeholder, _draw_image_icon, _draw_material_icon, _draw_mesh_icon, _draw_prefab_icon, _draw_scene_icon, _draw_script_icon, _draw_shader_icon, _draw_vector_placeholder

_thumbnail_cache: dict[str, QPixmap] = {}
_thumbnail_mutex = QMutex()
_placeholder_cache: dict[str, QPixmap] = {}
_icon_cache: dict[str, QIcon] = {}
_icon_mutex = QMutex()
_placeholder_icon: Optional[QIcon] = None
_MAX_PROCESS_INFLIGHT = 12
_PROCESS_EXTS = (
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp", ".hdr",
    ".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb",
    ".wav", ".mp3", ".ogg", ".flac", ".aiff", ".m4a",
    ".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2",
    ".mat", ".zpem",
)
def _is_process_thumb(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _PROCESS_EXTS
class _ThumbnailProcessService(QObject):
    thumbnail_ready = pyqtSignal(str, int, object)
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._pool = None
        self._inflight: set[tuple[str, int]] = set()
        self._lock = QMutex()
        self._cache_dir: Optional[str] = None
        self._idle_timer: Optional[QTimer] = None
    def set_cache_dir(self, cache_dir: Optional[str]):
        self._cache_dir = cache_dir
    def _ensure_pool(self):
        if self._pool is not None:
            return
        try:
            import multiprocessing as mp
            nproc = max(1, min(4, (mp.cpu_count() or 2)))
            self._pool = mp.Pool(
                processes=nproc,
                initializer=_thumb_worker_init,
            )
        except Exception:
            self._pool = None
    def _arm_idle(self):
        if QThread.currentThread() != self.thread():
            QMetaObject.invokeMethod(
                self, "_arm_idle_main", Qt.ConnectionType.QueuedConnection,
            )
            return
        self._arm_idle_main()
    @pyqtSlot()
    def _arm_idle_main(self):
        if self._idle_timer is None:
            self._idle_timer = QTimer(self)
            self._idle_timer.setSingleShot(True)
            self._idle_timer.timeout.connect(self._on_idle)
        self._idle_timer.start(30000)
    @pyqtSlot()
    def _on_idle(self):
        self._lock.lock()
        has_inflight = len(self._inflight) > 0
        self._lock.unlock()
        if has_inflight:
            self._arm_idle_main()
            return
        self.shutdown()
    def enqueue(self, path: str, size: int):
        cache_key = f"thumb:{path}:{size}"
        _thumbnail_mutex.lock()
        cached = cache_key in _thumbnail_cache
        _thumbnail_mutex.unlock()
        if cached:
            return
        if self._cache_dir:
            try:
                st = os.stat(path)
                dkey = thumb_disk_key(path, size, st.st_mtime, st.st_size,
                                       mode=_thumb_cache_mode())
                png = load_thumb_disk(self._cache_dir, dkey)
                if png:
                    pm = QPixmap()
                    if pm.loadFromData(png, "PNG") and not pm.isNull():
                        _thumbnail_mutex.lock()
                        _thumbnail_cache[cache_key] = pm
                        _thumbnail_mutex.unlock()
                        self.thumbnail_ready.emit(path, size, pm)
                        return
            except OSError:
                pass
        self._lock.lock()
        if (path, size) in self._inflight:
            self._lock.unlock()
            return
        self._inflight.add((path, size))
        self._lock.unlock()
        self._arm_idle()
        self._ensure_pool()
        if self._pool is None:
            return
        try:
            self._pool.apply_async(
                _thumb_render_wrap,
                (path, size, self._cache_dir, _thumb_cache_mode(),
                 _mesh_preview_settings()),
                callback=self._on_pool_result,
                error_callback=self._on_pool_error,
            )
        except Exception:
            self._lock.lock()
            self._inflight.discard((path, size))
            self._lock.unlock()
    def _on_pool_result(self, payload):
        QMetaObject.invokeMethod(
            self, "_deliver", Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, payload),
        )
    def _on_pool_error(self, exc):
        pass
    @pyqtSlot(object)
    def _deliver(self, payload):
        if not isinstance(payload, tuple) or len(payload) != 3:
            return
        path, size, png_bytes = payload
        self._lock.lock()
        self._inflight.discard((path, size))
        idle = len(self._inflight) == 0
        self._lock.unlock()
        pm = None
        if png_bytes:
            pm = QPixmap()
            if not pm.loadFromData(png_bytes, "PNG"):
                pm = None
        if pm is not None:
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            _thumbnail_cache[cache_key] = pm
            _thumbnail_mutex.unlock()
        if idle:
            self._arm_idle()
        self.thumbnail_ready.emit(path, size, pm)
    def shutdown(self):
        if self._pool is not None:
            try:
                self._pool.close()
                self._pool.terminate()
            except Exception:
                pass
            self._pool = None
        self._lock.lock()
        self._inflight.clear()
        self._lock.unlock()
    def invalidate_thumbnails(self):
        _thumbnail_mutex.lock()
        _thumbnail_cache.clear()
        _thumbnail_mutex.unlock()
        _icon_mutex.lock()
        _icon_cache.clear()
        _icon_mutex.unlock()
        if self._cache_dir:
            import shutil
            try:
                shutil.rmtree(self._cache_dir, ignore_errors=True)
            except Exception:
                pass
def _thumb_worker_init():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_thumb_service: Optional[_ThumbnailProcessService] = None
def _thumb_render_wrap(path: str, size: int, cache_dir: Optional[str],
                        mode: str = "metadata",
                        mesh_preview: Optional[dict] = None):
    from editor.thumb_worker import render_thumbnail
    png = render_thumbnail(path, size, cache_dir, mesh_preview=mesh_preview)
    if png and cache_dir:
        try:
            st = os.stat(path)
            dkey = thumb_disk_key(path, size, st.st_mtime, st.st_size,
                                   mode=mode)
            save_thumb_disk(cache_dir, dkey, png)
        except OSError:
            pass
    return (path, size, png)
def _get_thumb_service() -> _ThumbnailProcessService:
    global _thumb_service
    if _thumb_service is None:
        _thumb_service = _ThumbnailProcessService()
    return _thumb_service
def _get_mesh_loader() -> _ThumbnailProcessService:
    return _get_thumb_service()
def _thumb_cache_mode() -> str:
    try:
        from core.config.config import get_global_config
        return get_global_config().get("editor.thumb_cache_mode", "metadata")
    except Exception:
        return "metadata"
def _thumb_resolution() -> int:
    try:
        from core.config.config import get_global_config
        return get_global_config().get("editor.thumb_resolution", 512)
    except Exception:
        return 512
def _mesh_preview_settings() -> dict:
    try:
        from core.config.config import get_global_config
        return get_global_config().get("mesh_preview", {})
    except Exception:
        return {}
def _get_thumbnail(path: str, size: int) -> QPixmap:
    cache_key = f"thumb:{path}:{size}"
    _thumbnail_mutex.lock()
    if cache_key in _thumbnail_cache:
        cached = _thumbnail_cache[cache_key]
        _thumbnail_mutex.unlock()
        return cached
    _thumbnail_mutex.unlock()
    svc = _get_thumb_service()
    if svc._cache_dir:
        try:
            st = os.stat(path)
            dkey = thumb_disk_key(path, size, st.st_mtime, st.st_size,
                                   mode=_thumb_cache_mode())
            png = load_thumb_disk(svc._cache_dir, dkey)
            if png:
                pm = QPixmap()
                if pm.loadFromData(png, "PNG") and not pm.isNull():
                    _thumbnail_mutex.lock()
                    _thumbnail_cache[cache_key] = pm
                    _thumbnail_mutex.unlock()
                    return pm
        except OSError:
            pass
    pm = _get_thumbnail_raw(path, size)
    if pm:
        _thumbnail_mutex.lock()
        _thumbnail_cache[cache_key] = pm
        _thumbnail_mutex.unlock()
    return pm
def _get_cached_icon(path: str, size: int) -> QIcon:
    cache_key = f"icon:{path}:{size}"
    _icon_mutex.lock()
    icon = _icon_cache.get(cache_key)
    _icon_mutex.unlock()
    if icon is not None:
        return icon
    pm = _get_thumbnail(path, size)
    if pm is None:
        return QIcon()
    icon = QIcon(pm)
    _icon_mutex.lock()
    _icon_cache[cache_key] = icon
    _icon_mutex.unlock()
    return icon
def _get_placeholder_icon() -> QIcon:
    global _placeholder_icon
    if _placeholder_icon is None:
        _placeholder_icon = QIcon(_draw_file_icon(THUMB_SIZE))
    return _placeholder_icon
def _get_thumbnail_raw(path: str, size: int, enqueue_mesh: bool = True) -> QPixmap:
    if os.path.isdir(path):
        return _draw_folder_icon(size)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff",
               ".webp", ".hdr"):
        if _is_process_thumb(path):
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            cached = _thumbnail_cache.get(cache_key)
            _thumbnail_mutex.unlock()
            if cached is not None:
                return cached
            _get_thumb_service().enqueue(path, size)
        return _draw_image_icon(size)
    if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
        if _is_process_thumb(path):
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            cached = _thumbnail_cache.get(cache_key)
            _thumbnail_mutex.unlock()
            if cached is not None:
                return cached
            if enqueue_mesh:
                _get_thumb_service().enqueue(path, size)
        return _draw_mesh_icon(size)
    if ext in (".wav", ".mp3", ".ogg", ".flac", ".aiff", ".m4a"):
        if _is_process_thumb(path):
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            cached = _thumbnail_cache.get(cache_key)
            _thumbnail_mutex.unlock()
            if cached is not None:
                return cached
            _get_thumb_service().enqueue(path, size)
        return _draw_audio_icon(size)
    if ext == ".py":
        return _draw_script_icon(size)
    if ext == ".zpes":
        return _draw_scene_icon(size)
    if ext == ".zpep":
        return _draw_prefab_icon(size)
    if ext in (".mat", ".zpem"):
        if _is_process_thumb(path):
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            cached = _thumbnail_cache.get(cache_key)
            _thumbnail_mutex.unlock()
            if cached is not None:
                return cached
            _get_thumb_service().enqueue(path, size)
        return _draw_material_icon(size)
    if ext in (".shader", ".vert", ".frag", ".compute"):
        return _draw_shader_icon(size)
    if ext in (".animclip", ".animcontroller"):
        return _draw_file_icon(size)
    if ext in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"):
        if _is_process_thumb(path):
            cache_key = f"thumb:{path}:{size}"
            _thumbnail_mutex.lock()
            cached = _thumbnail_cache.get(cache_key)
            _thumbnail_mutex.unlock()
            if cached is not None:
                return cached
            _get_thumb_service().enqueue(path, size)
        return _draw_font_placeholder(size)
    return _draw_file_icon(size)
class _ThumbnailLoader(QThread):
    thumbnail_loaded = pyqtSignal(object, object)
    def __init__(self, thumb_size: int):
        super().__init__()
        self._thumb_size = thumb_size
        self._queue: collections.deque[tuple[int, str]] = collections.deque()
        self._queue_mutex = QMutex()
        self._cancelled = False
        self._running = False
    def cancel(self):
        self._cancelled = True
    def enqueue(self, items: list[tuple[int, str]]):
        self._queue_mutex.lock()
        self._queue.extend(items)
        self._queue_mutex.unlock()
    def pending_count(self) -> int:
        self._queue_mutex.lock()
        n = len(self._queue)
        self._queue_mutex.unlock()
        return n
    def run(self):
        self._running = True
        while not self._cancelled:
            self._queue_mutex.lock()
            if not self._queue:
                self._queue_mutex.unlock()
                break
            idx, full_path = self._queue.popleft()
            self._queue_mutex.unlock()
            cache_key = f"thumb:{full_path}:{self._thumb_size}"
            _thumbnail_mutex.lock()
            exists = cache_key in _placeholder_cache
            _thumbnail_mutex.unlock()
            if not exists:
                pm = _draw_vector_placeholder(full_path, self._thumb_size)
                if pm:
                    _thumbnail_mutex.lock()
                    _placeholder_cache[cache_key] = pm
                    _thumbnail_mutex.unlock()
                    self.thumbnail_loaded.emit(idx, pm)
        self._running = False
