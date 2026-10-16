# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import json
import numpy as np
from PySide6.QtCore import QThread, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog
from core.foundation.plugins import PluginBase
from core.foundation.logger import Logger
from .parse import BSPFile
from .build import ImportSettingsDialog, _generate_texture_png
class BSPImportPlugin(PluginBase):
    NAME = "BSPImport"
    VERSION = "2.0.0"
    DESCRIPTION = "Import Source Engine BSP maps into the scene (async)"
    SYSTEM = False
    def __init__(self):
        super().__init__()
        self._menu_added = False
        self._thread: QThread | None = None
        self._worker = None
        self._main_window = None
    def on_viewport_ready(self, viewport):
        if self._menu_added:
            return
        main_window = viewport.window()
        if not main_window:
            return
        self._main_window = main_window
        for action in main_window.menuBar().actions():
            if action.text() == "Tools":
                tools_menu = action.menu()
                sep = tools_menu.actions()
                import_act = QAction("Import BSP...", main_window)
                import_act.triggered.connect(lambda: self._on_import_bsp(main_window))
                if sep:
                    tools_menu.insertAction(sep[0], import_act)
                else:
                    tools_menu.addAction(import_act)
                self._menu_added = True
                Logger.info("[BSPImport] Added menu item to Tools")
                break
    def _on_import_bsp(self, parent_widget):
        from core.engine.eng import Engine
        engine = Engine.instance()
        if not engine:
            return
        path, _ = QFileDialog.getOpenFileName(
            parent_widget, "Import Source Engine BSP", "",
            "BSP Files (*.bsp);;All Files (*.*)")
        if not path:
            return
        dlg = ImportSettingsDialog(parent_widget)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dlg.get_settings()
        Logger.info(f"[BSPImport] Importing: {path}")
        try:
            self._import_sync(path, settings, engine, parent_widget)
        except Exception as e:
            Logger.error(f"[BSPImport] Failed: {e}")
            print(f"[BSPImport] Failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            QMessageBox.critical(parent_widget, "BSP Import Error",
                                 f"Import failed:\n{e}")
    def _import_sync(self, path: str, settings: dict, engine, parent):
        from core.components import Transform, MeshFilter, MeshRenderer
        from core.maths.math3d import Vec3
        from core.renderer.meshd import MeshData
        Logger.info("[BSPImport] Parsing BSP file...")
        bsp = BSPFile(path)
        Logger.info(f"[BSPImport] BSP v{bsp.version}, {len(bsp.faces)} faces, {len(bsp.vertices)} verts")
        merge_by_material = settings.get('merge_by_material', True)
        gen_tex = settings.get('generate_textures', True)
        tex_size = settings.get('texture_size', 128)
        center_pivot = settings.get('center_pivot', False)
        convert_coords = settings.get('convert_coords', True)
        scale = settings.get('scale', 1.0)
        materials_dir = os.path.join(engine.project_root, "assets", "materials", "bsp")
        os.makedirs(materials_dir, exist_ok=True)
        def progress_cb(pct, msg):
            pass
        Logger.info("[BSPImport] Extracting mesh groups...")
        groups = bsp.extract_mesh_groups(settings, progress_cb)
        if not groups:
            QMessageBox.information(parent, "BSP Import",
                                    "No valid mesh geometry found.")
            return
        Logger.info(f"[BSPImport] {len(groups)} material groups extracted")
        saved_textures = {}
        if gen_tex:
            Logger.info("[BSPImport] Generating textures...")
            for i, group in enumerate(groups):
                tex_name = group['name']
                png = _generate_texture_png(tex_name, tex_size)
                tex_path = os.path.normpath(
                    os.path.join(materials_dir, f"{tex_name}.png"))
                with open(tex_path, 'wb') as f:
                    f.write(png)
                saved_textures[tex_name] = tex_path
        Logger.info("[BSPImport] Saving material files...")
        for group in groups:
            tex_name = group['name']
            tex_path = saved_textures.get(tex_name, "")
            mat_path = os.path.normpath(
                os.path.join(materials_dir, f"{tex_name}.mat"))
            if not os.path.exists(mat_path) and tex_path:
                rel_tex = os.path.relpath(tex_path, engine.project_root).replace("\\", "/")
                mat_data = {
                    "name": tex_name,
                    "shader_path": "",
                    "properties": {
                        "albedo_texture": rel_tex,
                        "use_albedo_tex": 1,
                    }
                }
                with open(mat_path, 'w', encoding='utf-8') as f:
                    json.dump(mat_data, f, indent=2)
            group['_material_abs'] = mat_path
        Logger.info("[BSPImport] Building scene...")
        bsp_name = os.path.splitext(os.path.basename(path))[0]
        viewport = engine.viewport
        renderer = viewport.renderer if viewport and hasattr(viewport, 'renderer') else None
        ctx = renderer._ctx if renderer and hasattr(renderer, '_ctx') else None
        default_prog = renderer._default_prog if renderer else None
        meshes = renderer._meshes if renderer else None
        scene = engine.scene
        if not scene:
            scene = engine.new_scene("BSPMap")
        root_entity = scene.create_entity(bsp_name)
        root_entity.add_component(Transform())
        imported_count = 0
        for group in groups:
            tex_name = group['name']
            verts = group['vertices']
            normals = group['normals']
            uvs = group['uvs']
            indices = group['indices']
            centroid = group['centroid']
            if len(indices) < 3:
                continue
            mesh = MeshData()
            mesh.vertices = verts.flatten()
            mesh.normals = normals.flatten()
            mesh.uvs = uvs.flatten()
            mesh.indices = indices.astype(np.uint32)
            mesh.compute_aabb()
            if ctx and default_prog:
                try:
                    mesh.build_gl(ctx, default_prog)
                except Exception as e:
                    Logger.error(f"[BSPImport] GL build failed for {tex_name}: {e}")
            mesh_name = f"bsp_{bsp_name}_{tex_name}"
            if meshes is not None:
                meshes[mesh_name] = mesh
                meshes[f"{mesh_name}|s=1.0|cp=False|fu=False"] = mesh
            entity = scene.create_entity(tex_name)
            t = Transform()
            t.position = Vec3(centroid[0], centroid[1], centroid[2])
            entity.add_component(t)
            mf = MeshFilter()
            mf.mesh_name = mesh_name
            entity.add_component(mf)
            mr = MeshRenderer()
            mr.materials[0]["path"] = group.get('_material_abs', '')
            entity.set_parent(root_entity)
            imported_count += 1
        face_count = len(bsp.faces)
        Logger.info(
            f"[BSPImport] Imported {imported_count} groups / "
            f"{face_count} faces from {bsp_name}")
        if self._main_window and hasattr(self._main_window, '_hierarchy'):
            try:
                self._main_window._hierarchy.refresh()
            except Exception:
                pass
        QMessageBox.information(parent, "BSP Import",
                                f"Imported {imported_count} material groups\n"
                                f"({face_count} faces) from {bsp_name}")
        if viewport:
            QTimer.singleShot(0, viewport.update)
    def _on_import_finished(self, result: dict, engine, parent):
        print("[BSP_DEBUG] _on_import_finished start", flush=True)
        from core.components import Transform, MeshFilter, MeshRenderer
        from core.maths.math3d import Vec3
        from core.renderer.meshd import MeshData
        bsp_name = result['bsp_name']
        groups = result['groups']
        face_count = result.get('face_count', 0)
        print(f"[BSP_DEBUG] groups={len(groups)}", flush=True)
        if not groups:
            self._cleanup_import()
            print("[BSP_DEBUG] no groups, cleanup done", flush=True)
            QMessageBox.information(parent, "BSP Import",
                                    "No valid mesh geometry found.")
            return
        viewport = engine.viewport
        renderer = viewport.renderer if viewport and hasattr(viewport, 'renderer') else None
        ctx = renderer._ctx if renderer and hasattr(renderer, '_ctx') else None
        default_prog = renderer._default_prog if renderer else None
        meshes = renderer._meshes if renderer else None
        scene = engine.scene
        if not scene:
            scene = engine.new_scene("BSPMap")
        root_entity = scene.create_entity(bsp_name)
        root_entity.add_component(Transform())
        imported_count = 0
        for group in groups:
            tex_name = group['name']
            verts = group['vertices']
            normals = group['normals']
            uvs = group['uvs']
            indices = group['indices']
            centroid = group['centroid']
            if len(indices) < 3:
                continue
            try:
                mesh = MeshData()
                mesh.vertices = verts.flatten()
                mesh.normals = normals.flatten()
                mesh.uvs = uvs.flatten()
                mesh.indices = indices.astype(np.uint32)
                mesh.compute_aabb()
                if ctx and default_prog:
                    try:
                        mesh.build_gl(ctx, default_prog)
                    except Exception as e:
                        Logger.error(f"[BSPImport] GL build failed for {tex_name}: {e}")
                mesh_name = f"bsp_{bsp_name}_{tex_name}"
                if meshes is not None:
                    meshes[mesh_name] = mesh
                    meshes[f"{mesh_name}|s=1.0|cp=False|fu=False"] = mesh
                entity = scene.create_entity(tex_name)
                t = Transform()
                t.position = Vec3(centroid[0], centroid[1], centroid[2])
                entity.add_component(t)
                mf = MeshFilter()
                mf.mesh_name = mesh_name
                entity.add_component(mf)
                mr = MeshRenderer()
                mr.materials[0]["path"] = group.get('_material_abs', '')
                entity.set_parent(root_entity)
                imported_count += 1
            except Exception as e:
                print(f"[BSP_DEBUG] Failed group {tex_name}: {e}", flush=True)
                Logger.error(f"[BSPImport] Failed group {tex_name}: {e}")
        self._cleanup_import()
        Logger.info(
            f"[BSPImport] Imported {imported_count} groups / "
            f"{face_count} faces from {bsp_name}")
        if self._main_window and hasattr(self._main_window, '_hierarchy'):
            try:
                self._main_window._hierarchy.refresh()
            except Exception:
                pass
        QMessageBox.information(parent, "BSP Import",
                                f"Imported {imported_count} material groups\n"
                                f"({face_count} faces) from {bsp_name}")
        if viewport:
            QTimer.singleShot(0, viewport.update)
    def _cleanup_import(self):
        self._thread = None
        self._worker = None
    def shutdown(self):
        if self._thread and self._thread.isRunning():
            if self._worker:
                self._worker.cancel()
            self._thread.quit()
            self._thread.wait(5000)
        self._cleanup_import()
        Logger.info("[BSPImport] Shutdown.")
