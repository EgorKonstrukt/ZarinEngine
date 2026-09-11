# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class AssetPrefabEntry:
    menu_path: str
    name: str
    asset_path: str
    is_system: bool = False


def collect_system_entries() -> list:
    from core.prefabs.registry import get_system_prefabs
    return list(get_system_prefabs())


def collect_asset_entries() -> list[AssetPrefabEntry]:
    results: list[AssetPrefabEntry] = []
    seen: set[str] = set()
    search_roots: list[tuple[str, bool]] = []
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        core_prefabs = os.path.normpath(os.path.join(here, "..", "..", "core", "prefabs"))
        search_roots.append((core_prefabs, True))
    except Exception:
        pass
    try:
        from core.engine.engine import Engine
        eng = Engine.instance()
        project_root = getattr(eng, "project_root", None) if eng is not None else None
        if project_root and os.path.isdir(str(project_root)):
            search_roots.append((os.path.join(str(project_root), "assets"), False))
            search_roots.append((os.path.join(str(project_root), "prefabs"), False))
        else:
            fallback = os.getcwd()
            if os.path.isdir(os.path.join(fallback, "assets")):
                search_roots.append((os.path.join(fallback, "assets"), False))
    except Exception:
        pass
    for root, is_system in search_roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            try:
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
            except Exception:
                pass
            for filename in filenames:
                if not filename.endswith(".zpep"):
                    continue
                full = os.path.join(dirpath, filename)
                if full in seen:
                    continue
                seen.add(full)
                try:
                    with open(full, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                except Exception:
                    continue
                menu_path = str(data.get("menu_path", "") or "").strip()
                if not menu_path:
                    continue
                name = str(data.get("name", "") or os.path.splitext(filename)[0])
                parts = [p.strip() for p in menu_path.split("/") if p.strip()]
                if not parts:
                    continue
                results.append(AssetPrefabEntry(
                    menu_path="/".join(parts),
                    name=name,
                    asset_path=full,
                    is_system=is_system,
                ))
    try:
        from core.ecs.prefab import PrefabLibrary
        for path, prefab in list(PrefabLibrary.get_all().items()):
            menu_path = str(getattr(prefab, "menu_path", "") or "").strip()
            if not menu_path:
                continue
            if any(e.asset_path == path for e in results):
                continue
            parts = [p.strip() for p in menu_path.split("/") if p.strip()]
            if not parts:
                continue
            results.append(AssetPrefabEntry(
                menu_path="/".join(parts),
                name=getattr(prefab, "name", os.path.basename(path)),
                asset_path=path,
                is_system=False,
            ))
    except Exception:
        pass
    results.sort(key=lambda e: e.menu_path.lower())
    return results


def _split_path(menu_path: str) -> list[str]:
    return [p for p in (s.strip() for s in str(menu_path).split("/")) if p]


def populate_add_menu(menu, on_system: Callable[[str], None],
                      on_asset: Callable[[str], None],
                      on_search: Optional[Callable[[], None]] = None) -> None:
    from PyQt6.QtGui import QAction
    if on_search is not None:
        search_act = QAction("Search...", menu)
        search_act.triggered.connect(on_search)
        menu.addAction(search_act)
        menu.addSeparator()
    system_entries = collect_system_entries()
    asset_entries = collect_asset_entries()
    submenus: dict[str, object] = {}

    def get_submenu(parent_menu, section: str):
        key = f"{id(parent_menu)}:{section}"
        existing = submenus.get(key)
        if existing is not None:
            return existing
        sub = parent_menu.addMenu(section)
        submenus[key] = sub
        return sub

    for entry in system_entries:
        parts = _split_path(entry.menu_path)
        if not parts:
            continue
        target = menu
        for section in parts[:-1]:
            target = get_submenu(target, section)
        leaf = parts[-1]
        act = QAction(leaf, menu)
        tip = entry.menu_path
        if getattr(entry, "description", ""):
            tip = f"{entry.menu_path}\n{entry.description}"
        act.setToolTip(tip)
        act.triggered.connect(lambda checked=False, mp=entry.menu_path: on_system(mp))
        target.addAction(act)
    if asset_entries:
        if system_entries:
            menu.addSeparator()
        for asset in asset_entries:
            parts = _split_path(asset.menu_path)
            if not parts:
                continue
            target = menu
            for section in parts[:-1]:
                target = get_submenu(target, section)
            leaf = parts[-1]
            act = QAction(leaf, menu)
            prefix = "System prefab asset" if asset.is_system else "Prefab asset"
            act.setToolTip(f"{prefix}\n{asset.asset_path}")
            act.triggered.connect(lambda checked=False, ap=asset.asset_path: on_asset(ap))
            target.addAction(act)


try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTreeWidget,
        QTreeWidgetItem, QPushButton, QLabel, QAbstractItemView,
    )
    from PyQt6.QtCore import Qt
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class AddEntityDialog(QDialog):
        def __init__(self, parent=None, title: str = "Add Entity"):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setMinimumSize(420, 520)
            self.resize(480, 600)
            self._system_entries: list = []
            self._asset_entries: list[AssetPrefabEntry] = []
            self.selected_menu_path: Optional[str] = None
            self.selected_asset_path: Optional[str] = None
            self._setup_ui()
            self._reload()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
            self._search = QLineEdit()
            self._search.setPlaceholderText("Search entities...")
            self._search.setClearButtonEnabled(True)
            self._search.textChanged.connect(self._rebuild_tree)
            layout.addWidget(self._search)
            self._tree = QTreeWidget()
            self._tree.setHeaderLabels(["Name"])
            self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self._tree.itemSelectionChanged.connect(self._on_selection)
            self._tree.itemDoubleClicked.connect(lambda _item, _col: self._accept_selection())
            layout.addWidget(self._tree, 1)
            self._hint = QLabel()
            self._hint.setWordWrap(True)
            layout.addWidget(self._hint)
            buttons = QHBoxLayout()
            buttons.setSpacing(6)
            self._create_btn = QPushButton("Create")
            self._create_btn.setEnabled(False)
            self._create_btn.clicked.connect(self._accept_selection)
            buttons.addWidget(self._create_btn)
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            buttons.addWidget(cancel_btn)
            layout.addLayout(buttons)

        def _reload(self):
            self._system_entries = collect_system_entries()
            self._asset_entries = collect_asset_entries()
            self._rebuild_tree()

        def _matches(self, text: str, names: list[str]) -> bool:
            if not text:
                return True
            lowered = text.lower()
            return any(lowered in name.lower() for name in names)

        def _rebuild_tree(self):
            if not hasattr(self, "_tree"):
                return
            text = self._search.text().strip() if hasattr(self, "_search") else ""
            self._tree.clear()
            self._create_btn.setEnabled(False)
            self._hint.setText("")
            groups: dict[str, QTreeWidgetItem] = {}

            def group_item(path_parts: list[str]):
                current_parent = self._tree.invisibleRootItem()
                prefix_parts: list[str] = []
                group = None
                for section in path_parts:
                    prefix_parts.append(section)
                    prefix = "/".join(prefix_parts)
                    existing = groups.get(prefix)
                    if existing is None:
                        existing = QTreeWidgetItem(current_parent)
                        existing.setText(0, section)
                        existing.setFlags(existing.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                        existing.setExpanded(True)
                        groups[prefix] = existing
                    group = existing
                    current_parent = existing
                return current_parent

            for entry in self._system_entries:
                parts = _split_path(entry.menu_path)
                if not parts:
                    continue
                leaf = parts[-1]
                if not self._matches(text, [leaf, entry.menu_path, getattr(entry, "name", "")]):
                    continue
                parent_item = group_item(parts[:-1]) if len(parts) > 1 else self._tree.invisibleRootItem()
                item = QTreeWidgetItem(parent_item)
                item.setText(0, leaf)
                description = getattr(entry, "description", "") or ""
                tip = entry.menu_path + (f"\n{description}" if description else "")
                item.setToolTip(0, tip)
                item.setData(0, Qt.ItemDataRole.UserRole, ("system", entry.menu_path))
                parent_item.setExpanded(True)
            for asset in self._asset_entries:
                parts = _split_path(asset.menu_path)
                if not parts:
                    continue
                leaf = parts[-1]
                if not self._matches(text, [leaf, asset.menu_path, asset.name]):
                    continue
                parent_item = group_item(parts[:-1]) if len(parts) > 1 else self._tree.invisibleRootItem()
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f"{leaf}  [prefab]")
                item.setToolTip(0, f"{asset.menu_path}\n{asset.asset_path}")
                item.setData(0, Qt.ItemDataRole.UserRole, ("asset", asset.asset_path))
                parent_item.setExpanded(True)
            if text:
                self._tree.expandAll()

        def _on_selection(self):
            items = self._tree.selectedItems()
            if not items:
                self._create_btn.setEnabled(False)
                self._hint.setText("")
                return
            payload = items[0].data(0, Qt.ItemDataRole.UserRole)
            if not payload:
                self._create_btn.setEnabled(False)
                self._hint.setText("")
                return
            kind, _value = payload
            tip = items[0].toolTip(0)
            self._hint.setText(tip)
            self._create_btn.setEnabled(True)

        def _accept_selection(self):
            items = self._tree.selectedItems()
            if not items:
                return
            payload = items[0].data(0, Qt.ItemDataRole.UserRole)
            if not payload:
                return
            kind, value = payload
            if kind == "system":
                self.selected_menu_path = value
                self.selected_asset_path = None
            else:
                self.selected_asset_path = value
                self.selected_menu_path = None
            self.accept()
else:
    class AddEntityDialog:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt6 is not available")
