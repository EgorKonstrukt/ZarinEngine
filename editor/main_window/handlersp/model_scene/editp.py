# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os


def convert_selected_to_editable(mw) -> bool:
    try:
        from core.foundation.logger import Logger
        from core.assets.importer import load_mesh
        from core.assets.modelp import import_data_to_arrays
        from core.components.mesh_editor import ProBuilderMesh
        ent = _selected_or_model_entity(mw)
        if ent is None:
            try:
                Logger.warning("No model entity selected for conversion")
            except Exception:
                pass
            return False
        pb = ent.get_component(ProBuilderMesh)
        if pb is not None:
            return True
        src = _entity_source_path(mw, ent)
        if not src or not os.path.isfile(src):
            try:
                Logger.warning("Cannot resolve model source for conversion")
            except Exception:
                pass
            return False
        try:
            import_data = load_mesh(src)
        except Exception:
            import_data = None
        if import_data is None:
            try:
                Logger.warning("Cannot load model for conversion: " + src)
            except Exception:
                pass
            return False
        arrays = import_data_to_arrays(import_data)
        if arrays is None:
            return False
        verts, idx, norms, uvs = arrays
        try:
            import numpy as _np
            pb = ProBuilderMesh()
            pb.set_mesh_data(_np.ascontiguousarray(verts.reshape(-1, 3), dtype=_np.float32), _np.ascontiguousarray(idx.reshape(-1, 3), dtype=_np.uint32))
            try:
                if uvs is not None:
                    pb.uvs = _np.ascontiguousarray(uvs.reshape(-1, 2), dtype=_np.float32)
            except Exception:
                pass
            pb.rebuild_normals()
            pb._gpu_dirty = True
            ent.add_component(pb)
        except Exception:
            return False
        try:
            mw._engine.scene.mark_dirty()
        except Exception:
            pass
        try:
            mw._hierarchy.refresh()
        except Exception:
            pass
        try:
            if hasattr(mw, "_mesh_editor") and mw._mesh_editor is not None:
                mw._mesh_editor.set_entity(ent)
        except Exception:
            pass
        try:
            Logger.info("Converted to editable mesh: " + getattr(ent, "name", ""))
        except Exception:
            pass
        return True
    except Exception:
        return False


def export_selected_to_obj(mw, save_path: str = "") -> str:
    try:
        from PySide6.QtWidgets import QFileDialog
        from core.foundation.logger import Logger
        from core.assets.modelp import export_obj
        from core.components.mesh_editor import ProBuilderMesh
        ent = _selected_or_model_entity(mw)
        if ent is None:
            return ""
        pb = ent.get_component(ProBuilderMesh)
        if pb is None:
            try:
                Logger.warning("Select an editable mesh (convert first) to export OBJ")
            except Exception:
                pass
            return ""
        target = (save_path or "").strip()
        if not target:
            default = _default_obj_target(mw)
            target, _ = QFileDialog.getSaveFileName(mw, "Export Model OBJ", default, "OBJ (*.obj)")
            if not target:
                return ""
            if not target.lower().endswith(".obj"):
                target += ".obj"
        try:
            ok = export_obj(target, pb.positions, pb.indices, getattr(pb, "normals", None), getattr(pb, "uvs", None))
        except Exception:
            ok = False
        if not ok:
            try:
                Logger.warning("OBJ export failed: " + target)
            except Exception:
                pass
            return ""
        try:
            Logger.info("Exported OBJ: " + target)
        except Exception:
            pass
        return target
    except Exception:
        return ""


def _selected_or_model_entity(mw):
    try:
        vp = getattr(mw, "_viewport", None)
        sel = list(getattr(vp, "_selected_entities", []) or [])
        if sel:
            return sel[0]
    except Exception:
        pass
    try:
        scene = getattr(mw._engine, "scene", None)
        if scene is None:
            return None
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        found = scene.get_entities_with_component(MeshFilter)
        if found:
            return found[0]
        from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
        found = scene.get_entities_with_component(SkinnedMeshRenderer)
        if found:
            return found[0]
        roots = scene.get_root_entities()
        for e in roots:
            try:
                if not getattr(e, "system", False):
                    return e
            except Exception:
                continue
        if roots:
            return roots[0]
    except Exception:
        pass
    return None


def _entity_source_path(mw, ent) -> str:
    try:
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        from editor.main_window.handlersp.model_scene.openp import active_model_path
        mf = ent.get_component(MeshFilter)
        raw = (getattr(mf, "mesh_path", "") or "") if mf is not None else ""
        if not raw:
            try:
                from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
                smr = ent.get_component(SkinnedMeshRenderer)
                raw = (getattr(smr, "mesh_path", "") or "") if smr is not None else ""
            except Exception:
                raw = ""
        if not raw:
            return active_model_path(mw)
        if os.path.isfile(raw):
            return os.path.abspath(raw)
        try:
            root = getattr(mw._engine, "project_root", "") or os.getcwd()
            cand = os.path.normpath(os.path.join(root, raw))
            if os.path.isfile(cand):
                return cand
        except Exception:
            pass
        mp = active_model_path(mw)
        if mp and os.path.isfile(mp):
            return mp
        return raw
    except Exception:
        return ""


def _default_obj_target(mw) -> str:
    try:
        from editor.main_window.handlersp.model_scene.openp import active_model_path
        mp = active_model_path(mw)
        if mp and mp.lower().endswith(".obj"):
            return mp
        if mp:
            d = os.path.dirname(os.path.abspath(mp))
            base = os.path.splitext(os.path.basename(mp))[0]
            return os.path.join(d, base + ".obj")
    except Exception:
        pass
    try:
        root = getattr(mw._engine, "project_root", "") or os.getcwd()
        return os.path.join(root, "model.obj")
    except Exception:
        return "model.obj"
