# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import os, re
from typing import Optional
from PyQt6.QtCore import QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QImageReader
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget
from core.config.editor_scale import scale_xy
from editor.constants import PREVIEW_SIZE, THUMB_SIZE
from editor.thumb_cache import cache_root_for_project
from editor.picker.format import _format_size
from editor.picker.thumbs import _MAX_PROCESS_INFLIGHT, _ThumbnailLoader, _get_placeholder_icon, _get_thumb_service, _get_thumbnail, _icon_cache, _icon_mutex, _is_process_thumb, _placeholder_cache, _thumb_resolution, _thumbnail_cache, _thumbnail_mutex
from editor.picker.worker import _PopulateWorker

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
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._do_search)
        self._start_populate("")
    def _parse_extensions(self, filter_str: str) -> tuple:
        exts: list[str] = []
        for m in re.finditer(r'\(([^)]+)\)', filter_str or ""):
            raw = m.group(1).strip()
            if raw == "*" or not raw:
                continue
            for p in raw.split():
                if p == "*":
                    continue
                ext = p if p.startswith(".") else p[1:]
                if ext and ext not in exts:
                    exts.append(ext)
        return tuple(exts)
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
        self._list.setLayoutMode(QListView.LayoutMode.Batched)
        self._list.setBatchSize(50)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        self._thumb_scroll_timer = QTimer(self)
        self._thumb_scroll_timer.setSingleShot(True)
        self._thumb_scroll_timer.setInterval(60)
        self._thumb_scroll_timer.timeout.connect(self._schedule_thumbnails)
        self._list.verticalScrollBar().valueChanged.connect(
            lambda _: self._thumb_scroll_timer.start())
        self._list.horizontalScrollBar().valueChanged.connect(
            lambda _: self._thumb_scroll_timer.start())
        self._mesh_pending = 0
        self._mesh_loaded: set[int] = set()
        _get_thumb_service().thumbnail_ready.connect(
            self._on_thumb_ready, Qt.ConnectionType.QueuedConnection)
        _get_thumb_service().thumbnail_ready.connect(
            self._on_thumb_ready_preview, Qt.ConnectionType.QueuedConnection)
        self._preview_path: Optional[str] = None
        list_layout.addWidget(self._list)
        splitter.addWidget(list_container)
        preview_container = QWidget()
        preview_container.setFixedWidth(220)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(8, 0, 0, 0)
        preview_layout.setSpacing(6)
        self._preview_icon = QLabel()
        self._preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_icon.setFixedSize(*scale_xy(PREVIEW_SIZE + 20, PREVIEW_SIZE + 20))
        self._preview_icon.setStyleSheet("background: rgb(42,42,42); border: 1px solid rgb(68,68,68); border-radius: 4px;")
        preview_layout.addWidget(self._preview_icon)
        self._preview_name = QLabel()
        self._preview_name.setWordWrap(True)
        self._preview_name.setStyleSheet("font-weight: bold; font-size: 12px; color: rgb(221,221,221);")
        preview_layout.addWidget(self._preview_name)
        self._preview_info = QLabel()
        self._preview_info.setWordWrap(True)
        self._preview_info.setStyleSheet("font-size: 11px; color: rgb(153,153,153);")
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
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait()
        if hasattr(self, '_loader') and self._loader.isRunning():
            self._loader.cancel()
            self._loader.quit()
            self._loader.wait()
        self._search_text = filter_text
        _get_thumb_service().set_cache_dir(cache_root_for_project(self._project_root))
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        self._list.setUpdatesEnabled(True)
        self._all_items: list[tuple[str, str, str, int]] = []
        self._item_paths: dict[int, str] = {}
        self._batch_queue: list = []
        self._processing_batch = False
        self._placeholder = _get_placeholder_icon()
        self._thumb_queue: list = []
        self._processing_thumbs = False
        self._mesh_pending = 0
        self._mesh_loaded: set[int] = set()
        self._worker = _PopulateWorker(
            self._project_root,
            self._extensions,
            filter_text,
        )
        self._worker.batch_ready.connect(self._on_batch_ready)
        self._worker.start()
    def _on_batch_ready(self, batch: list):
        self._batch_queue.append(batch)
        if not self._processing_batch:
            self._processing_batch = True
            QTimer.singleShot(0, self._process_next_batch)
    def _process_next_batch(self):
        if not self._batch_queue:
            self._processing_batch = False
            self._list.setUpdatesEnabled(True)
            self._start_thumbnail_loader()
            return
        batch = self._batch_queue.pop(0)
        placeholder = self._placeholder
        self._list.setUpdatesEnabled(False)
        for full_path, filename, rel_path, file_size in batch:
            item = QListWidgetItem(QIcon(placeholder), os.path.splitext(filename)[0])
            item.setData(Qt.ItemDataRole.UserRole, full_path)
            item.setToolTip(f"{rel_path}\n{_format_size(file_size)}")
            self._list.addItem(item)
            self._item_paths[self._list.count() - 1] = full_path
        self._list.setUpdatesEnabled(True)
        self._all_items.extend(batch)
        QTimer.singleShot(0, self._process_next_batch)
    def _start_thumbnail_loader(self):
        if not hasattr(self, '_loader') or not self._loader.isRunning():
            if hasattr(self, '_loader'):
                self._loader.cancel()
                self._loader.wait()
            self._loader = _ThumbnailLoader(THUMB_SIZE)
            self._loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)
            self._loader.start()
        self._schedule_thumbnails(force=True)
    def _visible_item_range(self) -> tuple[int, int]:
        count = self._list.count()
        if count == 0:
            return 0, -1
        vp = self._list.viewport()
        rect = vp.rect()
        top_index = self._list.indexAt(rect.topLeft())
        bottom_index = self._list.indexAt(QPoint(rect.left(), rect.bottom() - 2))
        first = top_index.row() if top_index.isValid() else 0
        last = bottom_index.row() if bottom_index.isValid() else count - 1
        if last < first:
            last = first
        buffer = 40
        return max(0, first - buffer), min(count - 1, last + buffer)
    def _schedule_thumbnails(self, force: bool = False):
        if not hasattr(self, '_loader'):
            self._start_thumbnail_loader()
            return
        first, last = self._visible_item_range()
        if last < first:
            return
        vis_first, vis_last = self._visible_item_range_strict()
        to_load: list[tuple[int, str]] = []
        for idx in range(first, last + 1):
            path = self._item_paths.get(idx)
            if not path:
                continue
            cache_key = f"thumb:{path}:{_thumb_resolution()}"
            _thumbnail_mutex.lock()
            cached = cache_key in _thumbnail_cache
            _thumbnail_mutex.unlock()
            if cached:
                cache_key_icon = f"icon:{path}:{_thumb_resolution()}"
                _icon_mutex.lock()
                icon_cached = cache_key_icon in _icon_cache
                _icon_mutex.unlock()
                if not icon_cached:
                    pm = _thumbnail_cache.get(cache_key)
                    if pm and not pm.isNull():
                        icon = QIcon(pm)
                        _icon_mutex.lock()
                        _icon_cache[cache_key_icon] = icon
                        _icon_mutex.unlock()
                        item = self._list.item(idx)
                        if item:
                            item.setIcon(icon)
            else:
                to_load.append((idx, path))
            self._maybe_enqueue_process_thumb(idx, path)
        if to_load:
            if self._loader.isRunning():
                self._loader.enqueue(to_load)
            else:
                self._loader = _ThumbnailLoader(THUMB_SIZE)
                self._loader.thumbnail_loaded.connect(self._on_thumbnail_loaded)
                self._loader.enqueue(to_load)
                self._loader.start()
        if self._thumb_queue and not self._processing_thumbs:
            self._processing_thumbs = True
            QTimer.singleShot(0, self._process_thumb_batch)
    def _visible_item_range_strict(self) -> tuple[int, int]:
        count = self._list.count()
        if count == 0:
            return 0, -1
        vp = self._list.viewport()
        rect = vp.rect()
        top_index = self._list.indexAt(rect.topLeft())
        bottom_index = self._list.indexAt(QPoint(rect.left(), rect.bottom() - 2))
        first = top_index.row() if top_index.isValid() else 0
        last = bottom_index.row() if bottom_index.isValid() else count - 1
        return max(0, first), min(count - 1, last)
    def _maybe_enqueue_process_thumb(self, idx: int, path: str):
        if self._mesh_pending >= _MAX_PROCESS_INFLIGHT:
            return
        if idx in self._mesh_loaded:
            return
        if not _is_process_thumb(path):
            return
        cache_key = f"thumb:{path}:{_thumb_resolution()}"
        _thumbnail_mutex.lock()
        cached = cache_key in _thumbnail_cache
        _thumbnail_mutex.unlock()
        if cached:
            self._mesh_loaded.add(idx)
            self._thumb_queue.append((idx, path))
            if self._thumb_queue and not self._processing_thumbs:
                self._processing_thumbs = True
                QTimer.singleShot(0, self._process_thumb_batch)
            return
        self._mesh_loaded.add(idx)
        self._mesh_pending += 1
        _get_thumb_service().enqueue(path, _thumb_resolution())
    def _on_thumb_ready(self, path: str, size: int, pixmap):
        if size != _thumb_resolution():
            return
        self._mesh_pending = max(0, self._mesh_pending - 1)
        if pixmap is None or pixmap.isNull():
            return
        icon = QIcon(pixmap)
        icon_key = f"icon:{path}:{size}"
        _icon_mutex.lock()
        _icon_cache[icon_key] = icon
        _icon_mutex.unlock()
        for idx, p in self._item_paths.items():
            if p == path and idx < self._list.count():
                item = self._list.item(idx)
                if item:
                    item.setIcon(icon)
    def _on_thumb_ready_preview(self, path: str, size: int, pixmap):
        if size != PREVIEW_SIZE:
            return
        if self._preview_path != path:
            return
        if pixmap is None or pixmap.isNull():
            return
        self._preview_icon.setPixmap(pixmap)
    def _on_thumbnail_loaded(self, batch, _):
        try:
            if isinstance(batch, int):
                idx = batch
                pm = _
                try:
                    bad = pm is None or pm.isNull()
                except Exception:
                    return
                if bad:
                    return
                try:
                    if idx < self._list.count():
                        item = self._list.item(idx)
                        if item is not None:
                            item.setIcon(QIcon(pm))
                except Exception:
                    pass
                return
        except Exception:
            pass
        self._thumb_queue.extend(batch)
        if not self._processing_thumbs:
            self._processing_thumbs = True
            QTimer.singleShot(0, self._process_thumb_batch)
    def _process_thumb_batch(self):
        if not self._thumb_queue:
            self._processing_thumbs = False
            return
        count = 0
        while self._thumb_queue and count < 60:
            idx, path = self._thumb_queue.pop(0)
            if idx < self._list.count():
                pm = None
                cache_key = f"thumb:{path}:{_thumb_resolution()}"
                _thumbnail_mutex.lock()
                pm = _thumbnail_cache.get(cache_key)
                _thumbnail_mutex.unlock()
                if pm is None:
                    ph_key = f"thumb:{path}:{THUMB_SIZE}"
                    _thumbnail_mutex.lock()
                    pm = _placeholder_cache.get(ph_key)
                    _thumbnail_mutex.unlock()
                item = self._list.item(idx)
                if item and pm is not None and not pm.isNull():
                    item.setIcon(QIcon(pm))
            count += 1
        QTimer.singleShot(2, self._process_thumb_batch)
    def _on_search(self, text: str):
        self._search_timer.start()
    def _do_search(self):
        self._start_populate(self._search.text())
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
            self._preview_icon.setStyleSheet("background: rgb(42,42,42); border: 1px solid rgb(68,68,68); border-radius: 4px; color: rgb(102,102,102);")
            self._preview_name.setText("")
            self._preview_info.setText("")
            return
        self._preview_icon.setStyleSheet("background: rgb(42,42,42); border: 1px solid rgb(68,68,68); border-radius: 4px;")
        self._preview_path = path
        thumb = _get_thumbnail(path, PREVIEW_SIZE)
        if thumb.isNull():
            pm = _get_placeholder_icon()
            self._preview_icon.setPixmap(pm)
        else:
            self._preview_icon.setPixmap(thumb)
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        size_str = _format_size(os.path.getsize(path))
        type_map = {
            ".obj": "3D Model", ".fbx": "3D Model", ".stl": "3D Model", ".usdz": "3D Model", ".gltf": "3D Model", ".glb": "3D Model",
            ".wav": "Audio", ".mp3": "Audio", ".ogg": "Audio",
            ".py": "Python Script",
            ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
            ".hdr": "HDRI", ".exr": "HDRI",
            ".zpes": "Scene", ".zpep": "Prefab", ".mat": "Material",
            ".vert": "Vertex Shader", ".frag": "Fragment Shader",
            ".shader": "Shader", ".compute": "Compute Shader",
            ".animclip": "Animation Clip", ".animcontroller": "Animator Controller",
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
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait()
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
