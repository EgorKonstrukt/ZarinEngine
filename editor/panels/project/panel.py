# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, queue, sys, threading
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFileIconProvider, QToolButton, QSlider, QFrame, QMenu
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from typing import Optional, TYPE_CHECKING
from core.config.editor_scale import scale, scale_xy
from editor.constants import MIN_THUMB, MAX_THUMB, VIEW_ICON, VIEW_LIST, VIEW_DETAILS
from .icons import _qta_icon, qta
from .widgets import FolderTreeWidget; from .pane import _FilePane, _NavBar, _StatusBar
from .navigation import NavigationMixin; from .fs_ops import FsOpsMixin; from .dnd import DndMixin; from .vcs import VcsMixin; from .openers import OpenersMixin; from .creation import CreationMixin
if TYPE_CHECKING:
    from core.engine.engine import Engine
class ProjectPanel(NavigationMixin, FsOpsMixin, DndMixin, VcsMixin, OpenersMixin, CreationMixin, QDockWidget):
    file_double_clicked = pyqtSignal(str)
    prefab_drag_started = pyqtSignal(str)
    import_model_requested = pyqtSignal(str)
    file_selected = pyqtSignal(str)
    _vcs_result_ready = pyqtSignal(dict)
    _dir_size_ready = pyqtSignal(str, int, int)
    def __init__(self, engine: Engine, project_root: str = "assets", parent=None):
        super().__init__("Project", parent)
        self._engine = engine
        self._open_scene_callback = None
        self._project_root = os.path.abspath(project_root)
        self._thumb_size = 64
        self._icon_provider = QFileIconProvider()
        self._view_mode = VIEW_DETAILS
        self._dual_pane = False
        self._history = [[], []]
        self._history_index = 0
        self._nav_bar = None
        self._status_bar = None
        self._file_undo: list = []
        self._file_redo: list = []
        self._in_file_undo = False
        self._restoring_state = False
        self._sort_col = 0
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._sort_guard = False
        self._dir_size_cache: dict[str, int] = {}
        self._dir_size_gen = 0
        self._dir_size_queue: queue.Queue = queue.Queue()
        self._dir_size_thread: threading.Thread | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_state_now)
        self._vcs_status: dict[str, str] = {}
        self._vcs_refreshing: bool = False
        self._vcs_pending: bool = False
        self._vcs_timer = QTimer(self)
        self._vcs_timer.timeout.connect(self._refresh_vcs_status)
        self._vcs_timer.start(10000)
        self._vcs_result_ready.connect(self._on_vcs_result)
        try:
            self._dir_size_ready.connect(self._on_dir_size_ready, Qt.ConnectionType.QueuedConnection)
        except Exception:
            pass
        self._refresh_vcs_status()
        self._setup_ui()
        self._populate_tree()
        self._push_history(self._project_root)
        try:
            self._pane_splitter.splitterMoved.connect(lambda *a: self._schedule_save())
        except Exception:
            pass
    def load_config(self, config) -> None:
        try:
            thumb_size = config.get("project.thumb_size", self._thumb_size)
            self._thumb_size = max(MIN_THUMB, min(int(thumb_size), MAX_THUMB))
        except Exception:
            pass
        try:
            vm = int(config.get("project.view_mode", self._view_mode))
            if vm in (VIEW_ICON, VIEW_LIST, VIEW_DETAILS):
                self._view_mode = vm
        except Exception:
            pass
        try:
            self._dual_pane = bool(config.get("project.dual_pane", False))
        except Exception:
            pass
        try:
            sc = int(config.get("project.sort_column", 0))
            if sc in (0, 1, 2, 3):
                self._sort_col = sc
        except Exception:
            pass
        try:
            so = int(config.get("project.sort_order", 0))
            self._sort_order = Qt.SortOrder.DescendingOrder if so == 1 else Qt.SortOrder.AscendingOrder
        except Exception:
            pass
        if hasattr(self, "_zoom_slider"):
            try:
                self._zoom_slider.blockSignals(True)
                self._zoom_slider.setValue(self._thumb_size)
                self._zoom_slider.blockSignals(False)
            except Exception:
                pass
        if hasattr(self, "_dual_pane_btn"):
            try:
                self._dual_pane_btn.blockSignals(True)
                self._dual_pane_btn.setChecked(self._dual_pane)
                self._dual_pane_btn.blockSignals(False)
            except Exception:
                pass
        self._restoring_state = True
        try:
            self._apply_dual_pane_state()
            self._apply_view_mode()
            self._update_view_mode_icon()
            self._restore_pane_dirs(config)
        finally:
            self._restoring_state = False
        try:
            self._update_nav_buttons()
        except Exception:
            pass
    def save_config(self, config) -> None:
        config.set("project.thumb_size", self._thumb_size)
        config.set("project.dual_pane", self._dual_pane)
        config.set("project.view_mode", self._view_mode)
        try:
            config.set("project.sort_column", int(self._sort_col))
        except Exception:
            pass
        try:
            config.set("project.sort_order", 1 if self._sort_order == Qt.SortOrder.DescendingOrder else 0)
        except Exception:
            pass
        try:
            config.set("project.pane_a_dir", self._rel_or_abs(self._pane_a._current_dir))
        except Exception:
            pass
        try:
            if self._pane_b is not None:
                config.set("project.pane_b_dir", self._rel_or_abs(self._pane_b._current_dir))
            else:
                config.set("project.pane_b_dir", self._rel_or_abs(self._pane_a._current_dir))
        except Exception:
            pass
        try:
            if hasattr(self, "_pane_splitter") and self._pane_b is not None:
                config.set("project.splitter", list(self._pane_splitter.sizes()))
        except Exception:
            pass
    def _rel_or_abs(self, path: str) -> str:
        try:
            rel = os.path.relpath(os.path.normpath(path), self._project_root)
            if rel == ".":
                return "."
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except Exception:
            pass
        return os.path.normpath(path)
    def _abs_from_saved(self, saved) -> str:
        if not saved:
            return self._project_root
        try:
            s = str(saved).replace("/", os.sep)
            cand = s
            if not os.path.isabs(cand):
                cand = os.path.normpath(os.path.join(self._project_root, cand))
            else:
                cand = os.path.normpath(cand)
            try:
                common = os.path.commonpath([cand, self._project_root])
            except Exception:
                return self._project_root
            if common != self._project_root:
                return self._project_root
            if os.path.isdir(cand):
                return cand
        except Exception:
            pass
        return self._project_root
    def _restore_pane_dirs(self, config):
        try:
            a_dir = self._abs_from_saved(config.get("project.pane_a_dir", self._project_root))
        except Exception:
            a_dir = self._project_root
        try:
            b_dir = self._abs_from_saved(config.get("project.pane_b_dir", a_dir))
        except Exception:
            b_dir = a_dir
        try:
            self._pane_a._hist_back = []
            self._pane_a._hist_fwd = []
            self._pane_a.populate_files(a_dir)
        except Exception:
            pass
        if self._pane_b is not None:
            try:
                self._pane_b._hist_back = []
                self._pane_b._hist_fwd = []
                self._pane_b.populate_files(b_dir)
            except Exception:
                pass
        try:
            sizes = config.get("project.splitter", None)
            if self._pane_b is not None and isinstance(sizes, (list, tuple)) and len(sizes) == 2:
                self._pane_splitter.setSizes([int(sizes[0]), int(sizes[1])])
        except Exception:
            pass
        try:
            self._set_active_pane(self._pane_a)
        except Exception:
            pass
    def _get_file_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path)[1].lower()
        ext_map = {
            ".py": "fa5s.file-code", ".txt": "fa5s.file-alt", ".json": "fa5s.file-code",
            ".xml": "fa5s.file-code", ".csv": "fa5s.file-csv", ".ini": "fa5s.file-code",
            ".cfg": "fa5s.file-code", ".toml": "fa5s.file-code", ".yaml": "fa5s.file-code",
            ".yml": "fa5s.file-code",
        }
        if ext in ext_map:
            return _qta_icon(ext_map[ext], "#d4d4d4")
        if ext == ".zpes":
            from editor.resource_picker import _draw_scene_icon
            return QIcon(_draw_scene_icon(self._thumb_size))
        if ext == ".zpep":
            from editor.resource_picker import _draw_prefab_icon
            return QIcon(_draw_prefab_icon(self._thumb_size))
        if ext == ".mat":
            from editor.resource_picker import _get_material_thumbnail, _draw_material_icon
            pm = _get_material_thumbnail(path, self._thumb_size)
            if pm:
                return QIcon(pm)
            return QIcon(_draw_material_icon(self._thumb_size))
        if ext in (".animclip", ".animcontroller"):
            from editor.resource_picker import _draw_file_icon
            return QIcon(_draw_file_icon(self._thumb_size))
        return None
    def _active_pane(self) -> _FilePane:
        try:
            if self._dual_pane and self._pane_b is not None and self._pane_b._active:
                return self._pane_b
        except Exception:
            pass
        return self._pane_a
    def _set_active_pane(self, pane) -> None:
        if pane is None:
            return
        if pane is not self._pane_a and pane is not getattr(self, "_pane_b", None):
            return
        other = self._pane_b if pane is self._pane_a else self._pane_a
        pane.set_active(True)
        if other is not None:
            other.set_active(False)
        try:
            if self._nav_bar:
                self._nav_bar.update_address(pane._current_dir)
                self._nav_bar._back_btn.setEnabled(len(pane._hist_back) > 0)
                self._nav_bar._forward_btn.setEnabled(len(pane._hist_fwd) > 0)
            if self._status_bar:
                self._status_bar.update_path(pane._current_dir)
                try:
                    entries = os.listdir(pane._current_dir)
                    visible = [e for e in entries if not e.startswith(".") and not e.endswith(".import")]
                    self._status_bar.update_counts(len(visible))
                except Exception:
                    pass
        except Exception:
            pass
    def _set_active_pane_by_widget(self, widget) -> None:
        try:
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                if widget is pane._file_list or widget is pane._detail_tree or widget is pane._breadcrumb_bar or widget is pane:
                    if not pane._active:
                        self._set_active_pane(pane)
                    return
                try:
                    if widget in pane._file_list.children() or widget in pane._detail_tree.children():
                        if not pane._active:
                            self._set_active_pane(pane)
                        return
                except Exception:
                    pass
            obj = widget
            while obj is not None:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is not None and obj is pane:
                        if not pane._active:
                            self._set_active_pane(pane)
                        return
                try:
                    obj = obj.parent()
                except Exception:
                    break
        except Exception:
            pass
    def _is_inside_root(self, path: str) -> bool:
        try:
            ap = os.path.normpath(os.path.abspath(path))
            root = os.path.normpath(self._project_root)
            return os.path.commonpath([ap, root]) == root
        except Exception:
            return False
    def _schedule_save(self) -> None:
        try:
            if self._restoring_state:
                return
            if not self._save_timer.isActive():
                self._save_timer.start()
        except Exception:
            pass
    def _save_state_now(self) -> None:
        try:
            if self._restoring_state:
                return
            from core.config.config import get_global_config
            cfg = get_global_config()
            self.save_config(cfg)
            try:
                cfg.save()
            except Exception:
                pass
        except Exception:
            pass
    def _setup_ui(self):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        toolbar = QWidget()
        toolbar.setFixedHeight(scale(38))
        toolbar.setStyleSheet(f" QWidget {{ }} ")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(scale(8), scale(4), scale(8), scale(4))
        toolbar_layout.setSpacing(scale(6))
        create_btn = QToolButton()
        if qta is not None:
            create_btn.setIcon(qta.icon("fa5s.plus", color="#9ccc65"))
            create_btn.setIconSize(QSize(*scale_xy(18, 18)))
        create_btn.setText(" New")
        create_btn.setToolTip("Create new asset")
        create_btn.setFixedHeight(scale(30))
        create_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        create_btn.setStyleSheet(f" QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; font-size: 12px; padding: 0 10px; }} QToolButton:hover {{ }} QToolButton:pressed {{ background: #444; }} ")
        create_menu = QMenu(self)
        for name, cb in [
            ("Folder", self._create_new_folder),
            ("Scene", self._create_new_scene),
            ("Material", self._create_new_material),
            ("Physic Material", self._create_new_physic_material),
            ("Animation Clip", self._create_new_animclip),
            ("Animator Controller", self._create_new_animcontroller),
            ("Python Script", self._create_new_script),
            ("Cython Script", self._create_new_cython_script),
        ]:
            a = QAction(name, self)
            a.triggered.connect(cb)
            create_menu.addAction(a)
        create_btn.setMenu(create_menu)
        toolbar_layout.addWidget(create_btn)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedWidth(1)
        toolbar_layout.addWidget(sep1)
        self._view_mode_btn = QToolButton()
        self._view_mode_btn.setFixedSize(scale(32), scale(30))
        self._view_mode_btn.setToolTip("View Mode")
        self._view_mode_btn.clicked.connect(self._toggle_view_mode)
        self._update_view_mode_icon()
        self._view_mode_btn.setStyleSheet(f" QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; font-size: 13px; padding: 2px; }} QToolButton:hover {{ }} ")
        toolbar_layout.addWidget(self._view_mode_btn)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setFixedWidth(scale(110))
        self._zoom_slider.setRange(MIN_THUMB, MAX_THUMB)
        self._zoom_slider.setValue(self._thumb_size)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar_layout.addWidget(self._zoom_slider)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFixedWidth(1)
        toolbar_layout.addWidget(sep2)
        self._dual_pane_btn = QToolButton()
        self._dual_pane_btn.setFixedSize(scale(32), scale(30))
        self._dual_pane_btn.setToolTip("Dual Pane")
        self._dual_pane_btn.setCheckable(True)
        self._dual_pane_btn.setChecked(False)
        if qta is not None:
            self._dual_pane_btn.setIcon(qta.icon("fa5s.columns", color="#d4d4d4"))
            self._dual_pane_btn.setIconSize(QSize(*scale_xy(18, 18)))
        self._dual_pane_btn.toggled.connect(self._toggle_dual_pane)
        self._dual_pane_btn.setStyleSheet(f" QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 4px; font-size: 11px; padding: 2px; }} QToolButton:hover {{ }} QToolButton:checked {{ }} ")
        toolbar_layout.addWidget(self._dual_pane_btn)
        refresh_btn = QToolButton()
        refresh_btn.setFixedSize(scale(32), scale(30))
        refresh_btn.setToolTip("Refresh (F5)")
        if qta is not None:
            refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#d4d4d4"))
            refresh_btn.setIconSize(QSize(*scale_xy(18, 18)))
        refresh_btn.clicked.connect(self._refresh)
        refresh_btn.setStyleSheet(f" QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 3px; font-size: 14px; }} QToolButton:hover {{ }} ")
        toolbar_layout.addWidget(refresh_btn)
        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar)
        self._nav_bar = _NavBar(self)
        main_layout.addWidget(self._nav_bar)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self._folder_tree = FolderTreeWidget(self)
        self._folder_tree.setMinimumWidth(scale(100))
        self._folder_tree.setMaximumWidth(scale(240))
        self._folder_tree.itemClicked.connect(self._on_folder_selected)
        self._folder_tree.setDragEnabled(True)
        content_layout.addWidget(self._folder_tree)
        tree_separator = QFrame()
        tree_separator.setFrameShape(QFrame.Shape.VLine)
        tree_separator.setFixedWidth(1)
        content_layout.addWidget(tree_separator)
        self._pane_a = _FilePane(self)
        self._pane_a.set_active(True)
        self._install_pane_focus(self._pane_a)
        self._pane_b = None
        self._pane_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._pane_splitter.setHandleWidth(1)
        self._pane_splitter.setStyleSheet(f" QSplitter::handle {{ }} QSplitter::handle:horizontal {{ width: 1px; }} ")
        self._pane_splitter.addWidget(self._pane_a)
        self._setup_shortcuts()
        self._apply_view_mode()
        content_layout.addWidget(self._pane_splitter, 1)
        main_layout.addWidget(content, 1)
        self._status_bar = _StatusBar(self)
        main_layout.addWidget(self._status_bar)
        self.setWidget(w)
        from editor.resource_picker import _get_thumb_service
        from editor.thumb_cache import cache_root_for_project
        _get_thumb_service().set_cache_dir(cache_root_for_project(self._project_root))
        self._connect_mesh_loader()
        self._pane_a.populate_files(self._project_root)
    def eventFilter(self, obj, event):
        try:
            t = event.type()
            if t == QEvent.Type.FocusIn:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is not None and (pane._file_list is obj or pane._detail_tree is obj or pane._breadcrumb_bar is obj):
                        self._set_active_pane(pane)
                        break
            elif t == QEvent.Type.MouseButtonPress:
                for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                    if pane is None:
                        continue
                    match = False
                    try:
                        if obj is pane or obj is pane._file_list or obj is pane._detail_tree or obj is pane._breadcrumb_bar:
                            match = True
                        elif obj is pane._file_list.viewport() or obj is pane._detail_tree.viewport():
                            match = True
                    except Exception:
                        pass
                    if match:
                        self._set_active_pane(pane)
                        break
        except Exception:
            pass
        return super().eventFilter(obj, event)
    def _setup_shortcuts(self):
        sc = Qt.ShortcutContext.WidgetWithChildrenShortcut
        mapping = {
            "Ctrl+C": self._copy_selected,
            "Ctrl+X": self._cut_selected,
            "Ctrl+V": self._paste_clipboard,
            "Ctrl+D": self._duplicate_selected,
            "Ctrl+A": lambda: self._active_widget().selectAll(),
            "Ctrl+Shift+N": self._create_new_folder,
            "Alt+Left": self._go_back,
            "Alt+Right": self._go_forward,
            "Alt+Up": self._go_to_parent,
        }
        for seq_str, cb in mapping.items():
            s = QShortcut(QKeySequence(seq_str), self)
            s.activated.connect(cb)
            s.setContext(sc)
        for seq_str, cb in [("Ctrl+Z", self._undo_file_op), ("Ctrl+Y", self._redo_file_op), ("Ctrl+Shift+Z", self._redo_file_op)]:
            s = QShortcut(QKeySequence(seq_str), self)
            s.setContext(sc)
            s.activated.connect(cb)
    def _active_widget(self):
        return self._active_pane().active_widget()
