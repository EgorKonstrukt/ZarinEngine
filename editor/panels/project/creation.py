# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, sys
from PySide6.QtWidgets import QFileDialog, QMenu, QTreeWidget, QListWidget, QTreeWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from .icons import _qta_icon
try:
    from editor.shellmenu import show_shell_context_menu
    _HAS_SHELL_MENU = (sys.platform == "win32")
except Exception:
    show_shell_context_menu = None
    _HAS_SHELL_MENU = False
class CreationMixin:
    def _create_new_folder(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Create Folder", "Folder name:")
        if ok and name:
            try:
                target = os.path.join(self._current_dir(), name)
                os.makedirs(target, exist_ok=True)
                self._push_file_undo({"kind": "create", "paths": [target], "label": "Create folder"})
                self._refresh()
            except OSError as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")
    def _create_new_scene(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Scene", self._current_dir(), "Scenes (*.zpes)")
        if not path:
            return
        if not path.endswith(".zpes"):
            path += ".zpes"
        import json
        data = {"name": os.path.splitext(os.path.basename(path))[0], "entities": {}}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create scene"})
        self._refresh()
    def _create_new_material(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Material", self._current_dir(), "Materials (*.mat)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext != ".mat":
            path += ".mat"
        from core.assets.matp import Material
        mat = Material(os.path.splitext(os.path.basename(path))[0])
        mat.save(path, self._engine.project_root)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create material"})
        self._refresh()
    def _create_new_physic_material(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Physic Material", self._current_dir(), "Physics Materials (*.zphysmat)")
        if not path:
            return
        if not path.endswith(".zphysmat"):
            path += ".zphysmat"
        from core.assets.physics_material import PhysicsMaterial
        mat = PhysicsMaterial(os.path.splitext(os.path.basename(path))[0])
        mat.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create material"})
        self._refresh()
    def _create_new_animclip(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Animation Clip", self._current_dir(), "Animation Clips (*.animclip)")
        if not path:
            return
        if not path.endswith(".animclip"):
            path += ".animclip"
        from core.components.animation.animation_clip import AnimationClip
        clip = AnimationClip(os.path.splitext(os.path.basename(path))[0])
        clip.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create clip"})
        self._refresh()
    def _create_new_animcontroller(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Animator Controller", self._current_dir(), "Animator Controllers (*.animcontroller)")
        if not path:
            return
        if not path.endswith(".animcontroller"):
            path += ".animcontroller"
        from core.components.animation.animator_controller import AnimatorController
        ctrl = AnimatorController(os.path.splitext(os.path.basename(path))[0])
        ctrl.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create controller"})
        self._refresh()
    def _create_new_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Script", self._current_dir(), "Python Scripts (*.py)")
        if not path:
            return
        if not path.endswith(".py"):
            path += ".py"
        base = os.path.splitext(os.path.basename(path))[0]
        class_name = "".join(ch if ch.isalnum() else "_" for ch in base).strip("_") or "NewScript"
        if class_name[0].isdigit():
            class_name = "Script_" + class_name
        class_name = class_name[0].upper() + class_name[1:]
        template = "from core.maths.math3d import Vec3 class CLASSNAME: speed: float = 90.0 def on_awake(self): pass def on_start(self): pass def on_update(self, dt: float): t = self._entity.transform if t: t.rotate(Vec3(0.0, self.speed * dt, 0.0)) ".replace("CLASSNAME", class_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(template)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create script"})
        self._refresh()
        self.file_double_clicked.emit(path)
    def _create_new_cython_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create Cython Script", self._current_dir(), "Cython Scripts (*.pyx)")
        if not path:
            return
        if not path.endswith(".pyx"):
            path += ".pyx"
        try:
            from core.components.scripting.cythonp import CYTHON_TEMPLATE
        except Exception:
            CYTHON_TEMPLATE = None
        base = os.path.splitext(os.path.basename(path))[0]
        mod_name = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in base).strip("_") or "fast_module"
        if mod_name[0].isdigit():
            mod_name = "fast_" + mod_name
        if CYTHON_TEMPLATE:
            template = CYTHON_TEMPLATE.replace("MODULENAME", mod_name)
        else:
            template = '# cython: language_level=3\ncpdef double add(double a, double b):\n    return a + b\n'
        with open(path, "w", encoding="utf-8") as f:
            f.write(template)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create cython script"})
        self._refresh()
        self.file_double_clicked.emit(path)
    def _resolve_resource_path(self, path: str) -> str:
        if not path:
            return ""
        if os.path.exists(path) or os.path.isabs(path):
            return path
        root = self._engine.project_root if self._engine else None
        if root:
            cand = os.path.normpath(os.path.join(root, path))
            if os.path.exists(cand):
                return cand
        return path
    def set_project_root(self, path: str):
        self._project_root = os.path.abspath(path)
        try:
            self._dir_size_cache.clear()
            self._dir_size_gen += 1
        except Exception:
            pass
        a_dir = self._project_root
        b_dir = self._project_root
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            try:
                a_dir = self._abs_from_saved(cfg.get("project.pane_a_dir", self._project_root))
            except Exception:
                pass
            try:
                b_dir = self._abs_from_saved(cfg.get("project.pane_b_dir", a_dir))
            except Exception:
                pass
        except Exception:
            pass
        try:
            self._pane_a._hist_back = []
            self._pane_a._hist_fwd = []
            self._pane_a._current_dir = a_dir
            self._pane_a.populate_files(a_dir)
        except Exception:
            pass
        if getattr(self, "_pane_b", None):
            try:
                self._pane_b._hist_back = []
                self._pane_b._hist_fwd = []
                self._pane_b._current_dir = b_dir
                self._pane_b.populate_files(b_dir)
            except Exception:
                pass
        try:
            self._set_active_pane(self._pane_a)
        except Exception:
            pass
        self._refresh_vcs_status()
        self._populate_tree()
        try:
            self._update_nav_buttons()
        except Exception:
            pass
        try:
            self._apply_sort_indicators()
        except Exception:
            pass
    def _show_file_context_menu(self, pos):
        widget = self.sender()
        item = widget.itemAt(pos) if isinstance(widget, (QTreeWidget, QListWidget)) else None
        if _HAS_SHELL_MENU and show_shell_context_menu is not None:
            if item:
                path = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                        else item.data(Qt.ItemDataRole.UserRole))
            else:
                path = None
            if path:
                paths = self._get_selected_paths() or [path]
            else:
                paths = [self._active_pane()._current_dir]
            if paths:
                try:
                    from PySide6.QtGui import QCursor
                    cursor_pos = QCursor.pos()
                    if cursor_pos is not None and not cursor_pos.isNull():
                        try:
                            inside = widget.rect().contains(widget.mapFromGlobal(cursor_pos))
                        except Exception:
                            inside = True
                        if inside:
                            menu_x, menu_y = int(cursor_pos.x()), int(cursor_pos.y())
                        else:
                            mapped = widget.mapToGlobal(pos)
                            menu_x, menu_y = int(mapped.x()), int(mapped.y())
                    else:
                        mapped = widget.mapToGlobal(pos)
                        menu_x, menu_y = int(mapped.x()), int(mapped.y())
                    if show_shell_context_menu(
                            paths, int(self.winId()), menu_x, menu_y,
                            self._build_shell_extra_actions(path)):
                        return
                except Exception:
                    pass
        menu = QMenu(self)
        if item:
            path = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                    else item.data(Qt.ItemDataRole.UserRole))
            if not path:
                pass
            elif os.path.isdir(path):
                open_act = QAction("Open", self)
                open_act.triggered.connect(lambda p=path: self._navigate_to(self._active_pane(), p, record=True))
                menu.addAction(open_act)
            else:
                ext = os.path.splitext(path)[1].lower() if path else ""
                if ext == ".zpes":
                    act = QAction("Open Scene", self)
                    act.triggered.connect(lambda: self._open_scene_file(path))
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
                elif ext in (".wav", ".mp3", ".ogg", ".flac"):
                    act = QAction("Play", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".png", ".jpg", ".jpeg"):
                    act = QAction("View Image", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext in (".animclip", ".animcontroller"):
                    act = QAction("Open", self)
                    act.triggered.connect(lambda: self.file_double_clicked.emit(path))
                    menu.addAction(act)
                elif ext == ".zterr":
                    act = QAction("Open in Terrain Editor", self)
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
                status = self._vcs_status_of(path) if path else ""
                if status:
                    label = {"untracked": "Untracked", "added": "Added",
                             "modified": "Modified", "deleted": "Deleted",
                             "conflict": "Conflict", "renamed": "Renamed"}
                    info = QAction(f"VCS: {label.get(status, status)}", self)
                    info.setEnabled(False)
                    menu.addAction(info)
                if status in ("untracked", "modified", "deleted"):
                    add_act = QAction("Add to VCS", self)
                    add_act.triggered.connect(lambda p=path: self._git_add_file(p))
                    menu.addAction(add_act)
                if status == "added":
                    unstage_act = QAction("Unstage", self)
                    unstage_act.triggered.connect(lambda p=path: self._git_unstage_file(p))
                    menu.addAction(unstage_act)
                ignore_act = QAction("Ignore in Git", self)
                ignore_act.triggered.connect(lambda p=path: self._git_ignore_file(p))
                menu.addAction(ignore_act)
        menu.addSeparator()
        copy_path_act = QAction("Copy Path", self)
        if item:
            p = (item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem)
                 else item.data(Qt.ItemDataRole.UserRole))
            copy_path_act.triggered.connect(lambda: self._copy_path(p))
        else:
            copy_path_act.triggered.connect(lambda: self._copy_path(self._active_pane()._current_dir))
        menu.addAction(copy_path_act)
        menu.exec(widget.mapToGlobal(pos))
    def _build_shell_extra_actions(self, path):
        actions = []
        if not path:
            actions.append(("Copy Path", lambda: self._copy_path(self._active_pane()._current_dir)))
            return actions
        if not os.path.isdir(path):
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                actions.append(("Open Scene", lambda: self._open_scene_file(path)))
            elif ext == ".zpep":
                actions.append(("Instantiate Prefab", lambda: self._instantiate_prefab(path)))
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                actions.append(("Add to Scene", lambda p=path: self.import_model_requested.emit(p)))
            elif ext == ".py":
                actions.append(("Open Script", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".wav", ".mp3", ".ogg", ".flac"):
                actions.append(("Play", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".png", ".jpg", ".jpeg"):
                actions.append(("View Image", lambda: self.file_double_clicked.emit(path)))
            elif ext in (".animclip", ".animcontroller"):
                actions.append(("Open", lambda: self.file_double_clicked.emit(path)))
            elif ext == ".zterr":
                actions.append(("Open in Terrain Editor", lambda: self.file_double_clicked.emit(path)))
            actions.append(("Show in File Manager", lambda p=path: self._reveal_file(p)))
            actions.append(("Copy Path", lambda p=path: self._copy_path(p)))
        else:
            actions.append(("Copy Path", lambda p=path: self._copy_path(p)))
        return actions
