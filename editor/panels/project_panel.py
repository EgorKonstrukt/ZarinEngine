from __future__ import annotations
import os
import shutil
import datetime
from typing import Optional, TYPE_CHECKING
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QTreeWidget, QTreeWidgetItem, QPushButton,
                              QLabel, QLineEdit, QMenu, QFileDialog, QSplitter,
                              QListWidget, QListWidgetItem, QAbstractItemView,
                              QToolButton, QSlider, QStyle, QFileIconProvider,
                              QStackedWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QByteArray, QSize, QFileInfo, QUrl
from PyQt6.QtGui import QAction, QDrag, QIcon, QWheelEvent, QKeyEvent, QGuiApplication, QShortcut, QKeySequence
if TYPE_CHECKING:
    from core.engine import Engine
from editor.resource_picker import _get_thumbnail, _format_size

from editor.constants import MIN_THUMB, MAX_THUMB, VIEW_ICON, VIEW_LIST, VIEW_DETAILS

_file_clipboard: list[str] = []
_clipboard_is_cut: bool = False


class FileListWidget(QListWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0])
            return
        if key == Qt.Key.Key_Delete:
            self._panel._delete_selected()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            items = self.selectedItems()
            if items:
                self._panel._open_item(items[0])
            return
        if key == Qt.Key.Key_Backspace or (event.modifiers() == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Up):
            self._panel._go_to_parent()
            return
        if key == Qt.Key.Key_Home:
            self._panel._go_to_root()
            return
        if key == Qt.Key.Key_F5:
            self._panel._refresh()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_file_list_drop(event)
        else:
            super().dropEvent(event)

    def startDrag(self, supportedActions):
        self._panel._start_drag_list(supportedActions)

    def _open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._panel._open_path(path)


class FileDetailWidget(QTreeWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0], 0)
            return
        if key == Qt.Key.Key_Delete:
            self._panel._delete_selected()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            items = self.selectedItems()
            if items:
                self._panel._open_item_by_path(items[0].data(0, Qt.ItemDataRole.UserRole))
            return
        if key == Qt.Key.Key_Backspace or (event.modifiers() == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Up):
            self._panel._go_to_parent()
            return
        if key == Qt.Key.Key_Home:
            self._panel._go_to_root()
            return
        if key == Qt.Key.Key_F5:
            self._panel._refresh()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_detail_tree_drop(event)
        else:
            super().dropEvent(event)

    def startDrag(self, supportedActions):
        self._panel._start_drag_detail(supportedActions)


class FolderTreeWidget(QTreeWidget):
    def __init__(self, panel: ProjectPanel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            self._panel._on_folder_tree_drop(event)
        else:
            super().dropEvent(event)


class ProjectPanel(QDockWidget):
    file_double_clicked = pyqtSignal(str)
    prefab_drag_started = pyqtSignal(str)
    import_model_requested = pyqtSignal(str)
    file_selected = pyqtSignal(str)

    def __init__(self, engine: Engine, project_root: str = "assets", parent=None):
        super().__init__("Assets", parent)
        self._engine = engine
        self._project_root = os.path.abspath(project_root)
        self._current_dir: str = self._project_root
        self._thumb_size = 64
        self._icon_provider = QFileIconProvider()
        self._view_mode = VIEW_ICON
        self._setup_ui()
        self._populate_tree()

    def load_config(self, config) -> None:
        thumb_size = config.get("project.thumb_size", self._thumb_size)
        self._thumb_size = max(MIN_THUMB, min(thumb_size, MAX_THUMB))

    def save_config(self, config) -> None:
        config.set("project.thumb_size", self._thumb_size)

    def _get_file_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".py", ".txt", ".json", ".xml", ".csv", ".ini", ".cfg", ".toml", ".yaml", ".yml"):
            return self._icon_provider.icon(QFileIconProvider.IconType.File)
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
        return None

    def _setup_ui(self):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)

        toolbar = QHBoxLayout()

        create_btn = QToolButton()
        create_btn.setText("Create")
        create_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        create_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        create_menu = QMenu(self)
        for name, cb in [
            ("Folder", self._create_new_folder),
            ("Scene", self._create_new_scene),
            ("Material", self._create_new_material),
            ("Python Script", self._create_new_script),
        ]:
            a = QAction(name, self)
            a.triggered.connect(cb)
            create_menu.addAction(a)
        create_btn.setMenu(create_menu)
        toolbar.addWidget(create_btn)

        self._breadcrumb = QWidget()
        self._breadcrumb_layout = QHBoxLayout(self._breadcrumb)
        self._breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self._breadcrumb_layout.setSpacing(0)
        toolbar.addWidget(self._breadcrumb, 1)

        self._view_mode_btn = QPushButton()
        self._view_mode_btn.setFixedWidth(28)
        self._view_mode_btn.setToolTip("Toggle View Mode")
        self._view_mode_btn.clicked.connect(self._toggle_view_mode)
        self._update_view_mode_icon()
        toolbar.addWidget(self._view_mode_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setFixedWidth(80)
        self._zoom_slider.setRange(MIN_THUMB, MAX_THUMB)
        self._zoom_slider.setValue(self._thumb_size)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self._zoom_slider)

        refresh_btn = QPushButton()
        refresh_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)
        main_layout.addLayout(toolbar)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search assets...")
        self._search.textChanged.connect(self._on_search)
        main_layout.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._folder_tree = FolderTreeWidget(self)
        self._folder_tree.setHeaderHidden(True)
        self._folder_tree.setMinimumWidth(120)
        self._folder_tree.itemClicked.connect(self._on_folder_selected)
        self._folder_tree.setDragEnabled(True)
        splitter.addWidget(self._folder_tree)

        self._stack = QStackedWidget()

        self._file_list = FileListWidget(self)
        self._file_list.setDragEnabled(True)
        self._file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.itemClicked.connect(self._on_file_single_click)
        self._file_list.itemDoubleClicked.connect(self._on_file_double_click)
        self._file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.customContextMenuRequested.connect(self._show_file_context_menu)
        self._file_list.itemChanged.connect(self._on_list_item_changed)
        self._stack.addWidget(self._file_list)

        self._detail_tree = FileDetailWidget(self)
        self._detail_tree.setHeaderHidden(False)
        self._detail_tree.setColumnCount(4)
        self._detail_tree.setHeaderLabels(["Name", "Size", "Type", "Date Modified"])
        self._detail_tree.setRootIsDecorated(False)
        self._detail_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._detail_tree.setDragEnabled(True)
        self._detail_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._detail_tree.customContextMenuRequested.connect(self._show_file_context_menu)
        self._detail_tree.itemClicked.connect(self._on_file_single_click)
        self._detail_tree.itemDoubleClicked.connect(self._on_file_double_click)
        self._detail_tree.itemChanged.connect(self._on_tree_item_changed)
        self._detail_tree.setSortingEnabled(True)
        header = self._detail_tree.header()
        header.setStretchLastSection(True)
        header.setSectionsClickable(True)
        self._stack.addWidget(self._detail_tree)

        self._setup_shortcuts()

        self._apply_view_mode()
        splitter.addWidget(self._stack)
        splitter.setSizes([150, 350])
        main_layout.addWidget(splitter, 1)
        self.setWidget(w)

    def _setup_shortcuts(self):
        sc = Qt.ShortcutContext.WidgetWithChildrenShortcut
        mapping = {
            "Ctrl+C": self._copy_selected,
            "Ctrl+X": self._cut_selected,
            "Ctrl+V": self._paste_clipboard,
            "Ctrl+D": self._duplicate_selected,
            "Ctrl+A": lambda: self._active_widget().selectAll(),
            "Ctrl+Shift+N": self._create_new_folder,
        }
        for seq_str, cb in mapping.items():
            s = QShortcut(QKeySequence(seq_str), self)
            s.activated.connect(cb)
            s.setContext(sc)

    def _active_widget(self):
        return self._detail_tree if self._view_mode == VIEW_DETAILS else self._file_list

    def _update_view_mode_icon(self):
        icons = {
            VIEW_ICON: QStyle.StandardPixmap.SP_FileDialogContentsView,
            VIEW_LIST: QStyle.StandardPixmap.SP_FileDialogListView,
            VIEW_DETAILS: QStyle.StandardPixmap.SP_FileDialogDetailedView,
        }
        self._view_mode_btn.setIcon(self.style().standardIcon(icons.get(self._view_mode, VIEW_ICON)))

    def _toggle_view_mode(self):
        self._view_mode = (self._view_mode + 1) % 3
        self._apply_view_mode()
        self._update_view_mode_icon()
        self._populate_files(self._current_dir)

    def _apply_view_mode(self):
        is_detail = self._view_mode == VIEW_DETAILS
        self._stack.setCurrentIndex(1 if is_detail else 0)
        self._zoom_slider.setVisible(self._view_mode == VIEW_ICON)
        if not is_detail:
            is_list = self._view_mode == VIEW_LIST
            if is_list:
                self._file_list.setViewMode(QListWidget.ViewMode.ListMode)
                self._file_list.setIconSize(QSize(16, 16))
                self._file_list.setSpacing(0)
                self._file_list.setUniformItemSizes(True)
                self._file_list.setWordWrap(False)
                self._file_list.setGridSize(QSize(0, 0))
            else:
                self._file_list.setViewMode(QListWidget.ViewMode.IconMode)
                self._file_list.setIconSize(QSize(self._thumb_size, self._thumb_size))
                self._file_list.setGridSize(QSize(self._thumb_size + 20, self._thumb_size + 36))
                self._file_list.setWordWrap(True)
                self._file_list.setSpacing(2)
                self._file_list.setUniformItemSizes(True)
                self._file_list.setResizeMode(QListWidget.ResizeMode.Adjust)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 8 if abs(delta) > 120 else 4
                new_val = self._thumb_size + (step if delta > 0 else -step)
                new_val = max(MIN_THUMB, min(MAX_THUMB, new_val))
                self._thumb_size = new_val
                self._zoom_slider.setValue(new_val)
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_zoom_changed(self, val: int):
        self._thumb_size = val
        if self._view_mode == VIEW_ICON:
            self._file_list.setIconSize(QSize(val, val))
            self._file_list.setGridSize(QSize(val + 20, val + 36))
            self._populate_files(self._current_dir)

    def _open_path(self, path: str):
        if os.path.isdir(path):
            self._populate_files(path)
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                self._engine.load_scene(path)
            elif ext == ".zpep":
                self.file_double_clicked.emit(path)
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                self.import_model_requested.emit(path)
            else:
                self.file_double_clicked.emit(path)

    def _open_item_by_path(self, path: str):
        if path:
            self._open_path(path)

    def _go_to_parent(self):
        parent = os.path.dirname(self._current_dir)
        if parent and os.path.commonpath([parent, self._project_root]) == self._project_root:
            self._populate_files(parent)

    def _go_to_root(self):
        self._populate_files(self._project_root)

    def _rebuild_breadcrumb(self):
        for i in reversed(range(self._breadcrumb_layout.count())):
            w = self._breadcrumb_layout.itemAt(i).widget()
            if w: w.deleteLater()
        rel = os.path.relpath(self._current_dir, self._project_root)
        parts = rel.split(os.sep if os.sep else "/") if rel != "." else []
        crumbs = [self._project_root] + [os.path.join(self._project_root, *parts[:i+1]) for i in range(len(parts))]
        for i, p in enumerate(crumbs):
            if i > 0:
                sep = QLabel(" > ")
                sep.setStyleSheet("color: #888; padding: 0 2px;")
                self._breadcrumb_layout.addWidget(sep)
            label = "Assets" if p == self._project_root else os.path.basename(p)
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setStyleSheet("QPushButton { color: #4af; padding: 0 4px; } QPushButton:hover { color: #8cf; }")
            btn.clicked.connect(lambda checked, path=p: self._populate_files(path))
            self._breadcrumb_layout.addWidget(btn)
        self._breadcrumb_layout.addStretch()

    def _populate_tree(self):
        self._folder_tree.clear()
        root_item = QTreeWidgetItem(self._folder_tree)
        root_item.setText(0, "Assets")
        root_item.setData(0, Qt.ItemDataRole.UserRole, self._project_root)
        root_item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
        self._add_subfolders(root_item, self._project_root)
        root_item.setExpanded(True)
        self._populate_files(self._project_root)

    def _add_subfolders(self, parent_item: QTreeWidgetItem, dirpath: str):
        try:
            entries = sorted(os.listdir(dirpath))
        except PermissionError:
            return
        for entry in entries:
            full = os.path.join(dirpath, entry)
            if os.path.isdir(full) and not entry.startswith(".") and entry != "__pycache__":
                item = QTreeWidgetItem(parent_item)
                item.setText(0, entry)
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                self._add_subfolders(item, full)

    def _populate_files(self, dirpath: str, filter_text: str = ""):
        self._current_dir = dirpath
        self._rebuild_breadcrumb()
        try:
            entries = sorted(os.listdir(dirpath))
        except PermissionError:
            return
        if self._view_mode == VIEW_DETAILS:
            self._populate_detail_tree(dirpath, entries, filter_text)
        else:
            self._populate_list_view(dirpath, entries, filter_text)
        self._zoom_slider.setVisible(self._view_mode == VIEW_ICON)

    def _populate_list_view(self, dirpath: str, entries: list[str], filter_text: str):
        widget = self._file_list
        widget.blockSignals(True)
        widget.clear()
        is_icon = self._view_mode == VIEW_ICON
        for entry in entries:
            full = os.path.join(dirpath, entry)
            if entry.startswith("."): continue
            if filter_text and filter_text.lower() not in entry.lower(): continue
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if os.path.isdir(full):
                try:
                    item.setIcon(self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                except Exception:
                    item.setIcon(QIcon())
                item.setText(entry)
                item.setData(Qt.ItemDataRole.UserRole, full)
                item.setToolTip(f"Folder: {full}")
            else:
                if is_icon:
                    std_icon = self._get_file_icon(full)
                    if std_icon:
                        item.setIcon(std_icon)
                    else:
                        pm = _get_thumbnail(full, self._thumb_size)
                        item.setIcon(QIcon(pm))
                else:
                    try:
                        fi = QFileInfo(full)
                        item.setIcon(self._icon_provider.icon(fi))
                    except Exception:
                        item.setIcon(QIcon())
                item.setText(entry)
                item.setData(Qt.ItemDataRole.UserRole, full)
                try:
                    sz = os.path.getsize(full)
                except OSError:
                    sz = 0
                item.setToolTip(f"{entry}\n{_format_size(sz)}")
            widget.addItem(item)
        widget.blockSignals(False)

    def _populate_detail_tree(self, dirpath: str, entries: list[str], filter_text: str):
        widget = self._detail_tree
        widget.setSortingEnabled(False)
        widget.blockSignals(True)
        widget.clear()
        for entry in entries:
            full = os.path.join(dirpath, entry)
            if entry.startswith("."): continue
            if filter_text and filter_text.lower() not in entry.lower(): continue
            item = QTreeWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if os.path.isdir(full):
                try:
                    item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                except Exception:
                    pass
                item.setText(0, entry)
                item.setText(1, "")
                item.setText(2, "File folder")
                item.setToolTip(0, f"Folder: {full}")
            else:
                try:
                    fi = QFileInfo(full)
                    icon = self._icon_provider.icon(fi)
                    if icon and not icon.isNull():
                        item.setIcon(0, icon)
                except Exception:
                    pass
                item.setText(0, entry)
                try:
                    sz = os.path.getsize(full)
                    item.setText(1, _format_size(sz))
                except OSError:
                    item.setText(1, "")
                ext = os.path.splitext(entry)[1].lower()
                type_map = {
                    ".py": "Python Script", ".zpes": "Zarin Scene",
                    ".zpep": "Zarin Prefab",
                    ".mat": "Material", ".obj": "OBJ Model", ".fbx": "FBX Model",
                    ".stl": "3D Model", ".gltf": "3D Model", ".glb": "3D Model", ".usdz": "3D Model",
                    ".png": "PNG Image", ".jpg": "JPEG Image", ".jpeg": "JPEG Image",
                    ".wav": "WAV Audio", ".mp3": "MP3 Audio", ".ogg": "OGG Audio",
                    ".txt": "Text Document", ".json": "JSON File",
                    ".xml": "XML File", ".csv": "CSV File",
                    ".toml": "TOML File", ".yaml": "YAML File", ".yml": "YAML File",
                    ".ini": "INI File", ".cfg": "Configuration",
                    ".vert": "Vertex Shader", ".frag": "Fragment Shader",
                }
                item.setText(2, type_map.get(ext, f"{ext.upper()} File" if ext else "File"))
                try:
                    mtime = os.path.getmtime(full)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    item.setText(3, dt.strftime("%Y-%m-%d %H:%M"))
                except OSError:
                    item.setText(3, "")
                item.setToolTip(0, f"{entry}\n{_format_size(sz) if sz else ''}")
            item.setData(0, Qt.ItemDataRole.UserRole, full)
            widget.addTopLevelItem(item)
        widget.blockSignals(False)
        widget.setSortingEnabled(True)

    def _on_list_item_changed(self, item: QListWidgetItem):
        old_path = item.data(Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text()
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        try:
            os.rename(old_path, new_path)
            item.setData(Qt.ItemDataRole.UserRole, new_path)
            old_tip = item.toolTip()
            if "\n" in old_tip:
                item.setToolTip(new_name + "\n" + old_tip.split("\n", 1)[1])
            else:
                item.setToolTip(new_name)
        except OSError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")
            item.blockSignals(True)
            item.setText(old_name)
            item.blockSignals(False)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, col: int):
        if col != 0:
            return
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text(0)
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        try:
            os.rename(old_path, new_path)
            item.setData(0, Qt.ItemDataRole.UserRole, new_path)
            if not os.path.isdir(new_path):
                ext = os.path.splitext(new_name)[1].lower()
                if ext:
                    type_map = {
                        ".py": "Python Script", ".zpes": "Zarin Scene",
                        ".zpep": "Zarin Prefab",
                        ".mat": "Material", ".obj": "OBJ Model", ".fbx": "FBX Model",
                        ".stl": "3D Model", ".gltf": "3D Model", ".glb": "3D Model", ".usdz": "3D Model",
                        ".png": "PNG Image", ".jpg": "JPEG Image", ".jpeg": "JPEG Image",
                        ".wav": "WAV Audio", ".mp3": "MP3 Audio", ".ogg": "OGG Audio",
                        ".txt": "Text Document", ".json": "JSON File",
                    }
                    item.setText(1, type_map.get(ext, "Renaming..."))
                else:
                    item.setText(1, "")
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.isfile(path):
                self.file_selected.emit(path)
        except OSError:
            pass

    def _on_file_single_click(self, item):
        path = item.data(Qt.ItemDataRole.UserRole) if hasattr(item, 'data') else None
        if path and os.path.isfile(path):
            self.file_selected.emit(path)

    def _on_file_double_click(self, item):
        if isinstance(item, QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
        else:
            path = item.data(Qt.ItemDataRole.UserRole)
        if not path: return
        if os.path.isdir(path):
            self._populate_files(path)
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                self._engine.load_scene(path)
            elif ext == ".zpep":
                self.file_double_clicked.emit(path)
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                self.import_model_requested.emit(path)
            else:
                self._open_path_with_default_app(path)

    def _refresh(self):
        self._populate_tree()

    def _on_search(self, text: str):
        if text:
            self._search_all(text)
        else:
            self._populate_files(self._current_dir)

    def _on_folder_selected(self, item, col):
        dirpath = item.data(0, Qt.ItemDataRole.UserRole)
        if dirpath and os.path.isdir(dirpath):
            self._populate_files(dirpath)

    def _search_all(self, text: str):
        self._file_list.clear()
        self._zoom_slider.setVisible(False)
        if self._view_mode == VIEW_DETAILS:
            self._detail_tree.setSortingEnabled(False)
            self._detail_tree.clear()
        for root, dirs, files in os.walk(self._project_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                if text.lower() in f.lower() and not f.startswith("."):
                    full = os.path.join(root, f)
                    if self._view_mode == VIEW_DETAILS:
                        item = QTreeWidgetItem()
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        try:
                            fi = QFileInfo(full)
                            icon = self._icon_provider.icon(fi)
                            if icon and not icon.isNull():
                                item.setIcon(0, icon)
                        except Exception:
                            pass
                        item.setText(0, f)
                        try:
                            item.setText(1, _format_size(os.path.getsize(full)))
                        except OSError:
                            item.setText(1, "")
                        ext = os.path.splitext(f)[1].lower()
                        type_map = {
                            ".py": "Python Script", ".zpes": "Zarin Scene",
                            ".zpep": "Zarin Prefab",
                            ".mat": "Material", ".obj": "OBJ Model", ".fbx": "FBX Model",
                            ".stl": "3D Model", ".gltf": "3D Model", ".glb": "3D Model", ".usdz": "3D Model",
                            ".png": "PNG Image", ".jpg": "JPEG Image", ".jpeg": "JPEG Image",
                            ".wav": "WAV Audio", ".mp3": "MP3 Audio", ".ogg": "OGG Audio",
                            ".txt": "Text Document", ".json": "JSON File",
                        }
                        item.setText(2, type_map.get(ext, f"{ext.upper()} File" if ext else "File"))
                        item.setData(0, Qt.ItemDataRole.UserRole, full)
                        self._detail_tree.addTopLevelItem(item)
                    else:
                        item = QListWidgetItem()
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        std_icon = self._get_file_icon(full)
                        if std_icon:
                            item.setIcon(std_icon)
                        else:
                            pm = _get_thumbnail(full, self._thumb_size)
                            item.setIcon(QIcon(pm))
                        item.setText(f)
                        item.setData(Qt.ItemDataRole.UserRole, full)
                        self._file_list.addItem(item)
        if self._view_mode == VIEW_DETAILS:
            self._detail_tree.setSortingEnabled(True)

    def _show_file_context_menu(self, pos):
        widget = self.sender()
        item = widget.itemAt(pos) if isinstance(widget, (QTreeWidget, QListWidget)) else None
        menu = QMenu(self)
        if item:
            path = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                    else item.data(Qt.ItemDataRole.UserRole))
            if os.path.isdir(path):
                open_act = QAction("Open", self)
                open_act.triggered.connect(lambda: self._populate_files(path))
                menu.addAction(open_act)
            else:
                ext = os.path.splitext(path)[1].lower() if path else ""
                if ext == ".zpes":
                    act = QAction("Open Scene", self)
                    act.triggered.connect(lambda: self._engine.load_scene(path))
                    menu.addAction(act)
                elif ext == ".zpep":
                    act = QAction("Instantiate Prefab", self)
                    act.triggered.connect(lambda: self._instantiate_prefab(path))
                    menu.addAction(act)
                elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                    act = QAction("Add to Scene", self)
                    act.triggered.connect(lambda p=path: self.import_model_requested.emit(p))
                    menu.addAction(act)
                elif ext in (".py",):
                    act = QAction("Run Script", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".wav", ".mp3", ".ogg"):
                    act = QAction("Play", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".png", ".jpg", ".jpeg"):
                    act = QAction("View Image", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
            menu.addSeparator()
            cut_act = QAction("Cut\tCtrl+X", self)
            cut_act.triggered.connect(lambda: self._cut_selected())
            menu.addAction(cut_act)
            copy_act = QAction("Copy\tCtrl+C", self)
            copy_act.triggered.connect(lambda: self._copy_selected())
            menu.addAction(copy_act)
            paste_act = QAction("Paste\tCtrl+V", self)
            paste_act.triggered.connect(self._paste_clipboard)
            menu.addAction(paste_act)
            menu.addSeparator()
            rename_act = QAction("Rename\tF2", self)
            rename_act.triggered.connect(lambda: self._rename_item(widget, item))
            menu.addAction(rename_act)
            delete_act = QAction("Delete\tDel", self)
            delete_act.triggered.connect(lambda: self._delete_selected())
            menu.addAction(delete_act)
            menu.addSeparator()
            dup_act = QAction("Duplicate\tCtrl+D", self)
            dup_act.triggered.connect(lambda: self._duplicate_selected())
            menu.addAction(dup_act)
            menu.addSeparator()
            reveal_act = QAction("Show in File Manager", self)
            reveal_act.triggered.connect(lambda: self._reveal_file(path))
            menu.addAction(reveal_act)
        menu.addSeparator()
        copy_path_act = QAction("Copy Path", self)
        if item:
            p = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                 else item.data(Qt.ItemDataRole.UserRole))
            copy_path_act.triggered.connect(lambda: self._copy_path(p))
        else:
            copy_path_act.triggered.connect(lambda: self._copy_path(self._current_dir))
        menu.addAction(copy_path_act)
        menu.exec(widget.mapToGlobal(pos))

    def _rename_item(self, widget, item):
        if isinstance(item, QTreeWidgetItem):
            widget.editItem(item, 0)
        else:
            widget.editItem(item)

    def _start_drag_list(self, supported_actions):
        items = self._file_list.selectedItems()
        if not items: return
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in items if i.data(Qt.ItemDataRole.UserRole)]
        if not paths: return
        drag = QDrag(self._file_list)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText(paths[0])
        if len(paths) == 1:
            ext = os.path.splitext(paths[0])[1].lower()
            if ext == ".zpep":
                mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def _on_file_list_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths: return
        self._move_or_copy_files(paths)
        event.acceptProposedAction()

    def _on_detail_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths: return
        self._move_or_copy_files(paths)
        event.acceptProposedAction()

    def _on_folder_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths: return
        target_item = self._folder_tree.itemAt(event.pos())
        if target_item:
            target_path = target_item.data(0, Qt.ItemDataRole.UserRole)
        else:
            root = self._folder_tree.topLevelItem(0)
            target_path = root.data(0, Qt.ItemDataRole.UserRole)
        self._move_or_copy_files(paths, dest_dir=target_path)
        event.acceptProposedAction()

    def _extract_drop_paths(self, event):
        if event.mimeData().hasUrls():
            return [u.toLocalFile() for u in event.mimeData().urls()]
        if event.mimeData().hasText():
            paths = []
            for line in event.mimeData().text().splitlines():
                line = line.strip()
                if line:
                    paths.append(line)
            return paths
        return []

    def _move_or_copy_files(self, paths, dest_dir=None):
        if not dest_dir:
            dest_dir = self._current_dir
        errors = []
        for src in paths:
            if not os.path.exists(src): continue
            name = os.path.basename(src)
            dst = os.path.join(dest_dir, name)
            if src == dst or src.startswith(dst + os.sep): continue
            if os.path.exists(dst):
                base, ext = os.path.splitext(name)
                counter = 1
                while os.path.exists(os.path.join(dest_dir, f"{base} ({counter}){ext}")):
                    counter += 1
                dst = os.path.join(dest_dir, f"{base} ({counter}){ext}")
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError as e:
                errors.append(f"{name}: {e}")
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Import Errors", "\n".join(errors))

    def _open_path_with_default_app(self, path):
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _start_drag_detail(self, supported_actions):
        items = self._detail_tree.selectedItems()
        if not items: return
        paths = [i.data(0, Qt.ItemDataRole.UserRole) for i in items]
        if not paths: return
        drag = QDrag(self._detail_tree)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText(paths[0])
        ext = os.path.splitext(paths[0])[1].lower()
        if len(paths) == 1 and ext == ".zpep":
            mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    def _instantiate_prefab(self, path: str):
        if not self._engine.scene: return
        from core.prefab import Prefab
        from core.engine import Engine
        pref = Prefab.load(path)
        if pref:
            e = pref.instantiate(self._engine.scene, Engine.instance()._component_registry)
            if e: self._engine._emit_event("entity_created", e)

    def _reveal_file(self, path: str):
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _copy_path(self, path: str):
        QGuiApplication.clipboard().setText(path)

    def _get_selected_paths(self):
        widget = self._active_widget()
        paths = []
        for item in widget.selectedItems():
            d = item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem) else item.data(Qt.ItemDataRole.UserRole)
            if d:
                paths.append(d)
        return paths

    def _copy_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = False

    def _cut_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = True

    def _paste_clipboard(self):
        global _file_clipboard, _clipboard_is_cut
        if not _file_clipboard:
            return
        errors = []
        for src in _file_clipboard:
            if not os.path.exists(src):
                continue
            name = os.path.basename(src)
            dst = os.path.join(self._current_dir, name)
            if src == dst:
                continue
            if os.path.exists(dst):
                base, ext = os.path.splitext(name)
                counter = 1
                while os.path.exists(os.path.join(self._current_dir, f"{base} ({counter}){ext}")):
                    counter += 1
                dst = os.path.join(self._current_dir, f"{base} ({counter}){ext}")
            try:
                if _clipboard_is_cut:
                    shutil.move(src, dst)
                else:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            except OSError as e:
                errors.append(f"{name}: {e}")
        if _clipboard_is_cut:
            _file_clipboard = []
            _clipboard_is_cut = False
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Paste Errors", "\n".join(errors))

    def _duplicate_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        errors = []
        for src in paths:
            if not os.path.exists(src):
                continue
            name = os.path.basename(src)
            base, ext = os.path.splitext(name)
            counter = 1
            while os.path.exists(os.path.join(os.path.dirname(src), f"{base} ({counter}){ext}")):
                counter += 1
            dst = os.path.join(os.path.dirname(src), f"{base} ({counter}){ext}")
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError as e:
                errors.append(f"{name}: {e}")
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Duplicate Errors", "\n".join(errors))

    def _delete_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        from PyQt6.QtWidgets import QMessageBox
        names = "\n".join(os.path.basename(p) for p in paths[:10])
        if len(paths) > 10:
            names += f"\n... and {len(paths) - 10} more"
        reply = QMessageBox.question(self, "Delete",
            f"Delete {len(paths)} item(s)?\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            errors = []
            for p in paths:
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                except OSError as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            self._refresh()
            if errors:
                QMessageBox.warning(self, "Delete Errors", "\n".join(errors))

    def _create_new_folder(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Create Folder", "Folder name:")
        if ok and name:
            try:
                os.makedirs(os.path.join(self._current_dir, name), exist_ok=True)
                self._refresh()
            except OSError as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")

    def _create_new_scene(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Scene", self._current_dir, "Scenes (*.zpes)")
        if not path: return
        if not path.endswith(".zpes"): path += ".zpes"
        import json
        data = {"name": os.path.splitext(os.path.basename(path))[0], "entities": {}}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self._refresh()

    def _create_new_material(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Material", self._current_dir, "Materials (*.mat)")
        if not path: return
        ext = os.path.splitext(path)[1].lower()
        if ext != ".mat": path += ".mat"
        from core.material import Material
        mat = Material(os.path.splitext(os.path.basename(path))[0])
        mat.save(path, self._engine.project_root)
        self._refresh()

    def _create_new_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Script", self._current_dir, "Python Scripts (*.py)")
        if not path: return
        if not path.endswith(".py"): path += ".py"
        template = '''from __future__ import annotations
from core.ecs import Component, ComponentRegistry
@ComponentRegistry.register
class NewScript(Component):
    def __init__(self):
        super().__init__()
        self.my_var: float = 0.0
    def update(self, dt: float):
        pass
'''
        with open(path, "w") as f:
            f.write(template)
        self._refresh()

    def set_project_root(self, path: str):
        self._project_root = os.path.abspath(path)
        self._current_dir = self._project_root
        self._populate_tree()
