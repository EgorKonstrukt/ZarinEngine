# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import editor.icons as qta
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen

from .selection import on_entity_selected
from .prefab import instantiate_prefab

def on_entity_dropped(mw, path_or_type: str, world_pos, entity_under_cursor=None):
    if not mw._engine.scene:
        return
    ext = os.path.splitext(path_or_type)[1].lower()

    if ext == ".zpep":
        instantiate_prefab(mw, path_or_type, world_pos)
        return

    if ext == ".zmat":
        if entity_under_cursor:
            _apply_material_to_entity(mw, path_or_type, entity_under_cursor)
        else:
            _drop_material_on_scene(mw, path_or_type, world_pos)
        mw._hierarchy.refresh()
        return

    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tiff", ".webp"}
    audio_exts = {".wav", ".mp3", ".ogg", ".flac"}
    model_exts = {".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz", ".stp", ".step"}

    if ext in image_exts:
        _drop_image_asset(mw, path_or_type, world_pos, entity_under_cursor)
    elif ext in audio_exts:
        _drop_audio_asset(mw, path_or_type, world_pos)
    elif ext in model_exts:
        _drop_model_asset(mw, path_or_type, world_pos)
    else:
        _drop_generic_asset(mw, path_or_type, world_pos)

    mw._hierarchy.refresh()
    on_entity_selected(mw, mw._engine.scene.get_entity_by_name(os.path.basename(path_or_type) or "Dropped Object"))


def _apply_material_to_entity(mw, path: str, entity):
    if not entity:
        return
    from core.components.rendering.renderers.mesh_renderer import MeshRenderer
    from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
    mr = entity.get_component(MeshRenderer)
    if mr is None:
        mr = entity.get_component(SkinnedMeshRenderer)
    if not mr:
        return
    from core.assets.matp import MaterialLibrary
    mat = MaterialLibrary.load(path)
    if mat:
        mr.materials[0]["path"] = path
        Logger.info(f"Applied material {path} to {entity.name}")


def _drop_material_on_scene(mw, path: str, world_pos):
    from core.components import Transform, MeshFilter, MeshRenderer
    name = os.path.splitext(os.path.basename(path))[0]
    e = mw._engine.scene.create_entity(name)
    t = Transform()
    if world_pos:
        t.local_position = world_pos
    e.add_component(t)
    mf = MeshFilter()
    mf.mesh_name = "cube"
    e.add_component(mf)
    mr = MeshRenderer()
    mr.materials[0]["path"] = path
    e.add_component(mr)
    Logger.info(f"Created entity with material {path}")


def _drop_image_asset(mw, path: str, world_pos, entity_under_cursor):
    if entity_under_cursor:
        from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
        sr = entity_under_cursor.get_component(SpriteRenderer)
        if sr:
            rel = _rel_path(mw, path)
            sr.texture_path = rel or path
            Logger.info(f"Applied texture {path} to {entity_under_cursor.name}")
            return
        from core.components.rendering.renderers.mesh_renderer import MeshRenderer
        mr = entity_under_cursor.get_component(MeshRenderer)
        if mr is None:
            from core.components.rendering.renderers.skinned_mesh_renderer import SkinnedMeshRenderer
            mr = entity_under_cursor.get_component(SkinnedMeshRenderer)
        if mr:
            _create_material_and_apply(mw, path, entity_under_cursor, mr)
            return

    from core.components.rendering.renderers.sprite_renderer import SpriteRenderer
    from core.components import Transform
    name = os.path.splitext(os.path.basename(path))[0]
    e = mw._engine.scene.create_entity(name)
    t = Transform()
    if world_pos:
        t.local_position = world_pos
    e.add_component(t)
    sr = SpriteRenderer()
    rel = _rel_path(mw, path)
    sr.texture_path = rel or path
    e.add_component(sr)
    Logger.info(f"Created sprite entity from {path}")


def _create_material_and_apply(mw, texture_path: str, entity, mr):
    from core.assets.matp import Material
    from core.components import Transform, MeshFilter
    mat_name = os.path.splitext(os.path.basename(texture_path))[0] + "_mat"
    mat = Material(mat_name)
    mat.shader_path = "default"
    rel = _rel_path(mw, texture_path)
    tex_path = rel or texture_path
    mat.properties["_MainTex"] = tex_path
    mat.properties["diffuseMap"] = tex_path
    mats_dir = os.path.join(mw._engine.project_root, "materials")
    os.makedirs(mats_dir, exist_ok=True)
    mat_path = os.path.join(mats_dir, mat_name + ".zmat").replace("\\", "/")
    root = mw._engine.project_root
    try:
        rel_path = os.path.relpath(mat_path, root).replace("\\", "/")
    except ValueError:
        rel_path = mat_path
    mat.save(mat_path, mw._engine.project_root)
    mr.materials[0]["path"] = rel_path
    Logger.info(f"Created material {mat_path} and applied to {entity.name}")


def _drop_audio_asset(mw, path: str, world_pos):
    from core.components.audio.source import AudioSource
    from core.components import Transform
    name = os.path.splitext(os.path.basename(path))[0]
    e = mw._engine.scene.create_entity(name)
    t = Transform()
    if world_pos:
        t.local_position = world_pos
    e.add_component(t)
    src = AudioSource()
    rel = _rel_path(mw, path)
    src.clip_path = rel or path
    src.play_on_awake = False
    e.add_component(src)
    Logger.info(f"Created audio source from {path}")


def _drop_model_asset(mw, path: str, world_pos):
    name = os.path.splitext(os.path.basename(path))[0]
    root = mw._engine.project_root
    try:
        mesh_path = os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        mesh_path = os.path.abspath(path)

    from core.components.rendering.skeleton.skinned_factory import create_skinned_mesh_entity_async
    create_skinned_mesh_entity_async(
        mw._engine.scene, path, name, mesh_path, world_pos,
        callback=lambda ent, is_skinned: _on_model_loaded(mw, name, mesh_path, path, world_pos, ent, is_skinned)
    )


def _attach_blendshapes_if_needed(mw, ent, asset_path: str):
    try:
        from core.assets.importer import load_mesh_future
        fut = load_mesh_future(asset_path)

        def _poll():
            try:
                if not fut.done():
                    QTimer.singleShot(50, _poll)
                    return
                import_data = fut.result()
            except Exception:
                return
            try:
                if not list(getattr(import_data, "blendshape_names", []) or []):
                    return
                scene = mw._engine.scene
                live = scene.get_entity(ent.id) if scene is not None else None
                if live is None:
                    return
                from core.components.rendering.deform.blendshapes import BlendShapes
                if live.get_component(BlendShapes) is not None:
                    return
                bs = BlendShapes()
                bs.sync_with_mesh(import_data)
                live.add_component(bs)
                mw._hierarchy.refresh()
            except Exception:
                pass

        QTimer.singleShot(0, _poll)
    except Exception:
        pass


def _on_model_loaded(mw, name, mesh_path, asset_path, world_pos, ent, is_skinned):
    if not is_skinned:
        from core.components import Transform, MeshFilter, MeshRenderer
        e = mw._engine.scene.create_entity(name)
        t = Transform()
        if world_pos:
            t.local_position = world_pos
        e.add_component(t)
        mf = MeshFilter()
        mf.mesh_name = name
        mf.mesh_path = mesh_path
        e.add_component(mf)
        e.add_component(MeshRenderer())
        ent = e
    _apply_import_materials(ent, asset_path)
    if ent is not None and not is_skinned:
        _attach_blendshapes_if_needed(mw, ent, asset_path)
    mw._hierarchy.refresh()
    if ent:
        on_entity_selected(mw, ent)
    Logger.info(f"Created model entity from {name}")


def _drop_generic_asset(mw, path: str, world_pos):
    from core.components import Transform
    name = os.path.splitext(os.path.basename(path))[0] or "Dropped Object"
    e = mw._engine.scene.create_entity(name)
    t = Transform()
    if world_pos:
        t.local_position = world_pos
    e.add_component(t)


def _rel_path(mw, path: str) -> str:
    try:
        root = mw._engine.project_root
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return ""


def on_import_model(mw, path: str):
    if not mw._engine.scene:
        return
    name = os.path.splitext(os.path.basename(path))[0]
    root = mw._engine.project_root
    try:
        mesh_path = os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        mesh_path = os.path.abspath(path)

    from core.components.rendering.skeleton.skinned_factory import create_skinned_mesh_entity_async
    create_skinned_mesh_entity_async(
        mw._engine.scene, path, name, mesh_path,
        callback=lambda ent, is_skinned: _on_import_model_loaded(mw, name, mesh_path, path, ent, is_skinned)
    )


def _on_import_model_loaded(mw, name, mesh_path, asset_path, ent, is_skinned):
    if not is_skinned:
        from core.components import Transform, MeshFilter, MeshRenderer
        ent = mw._engine.scene.create_entity(name)
        ent.add_component(Transform())
        mf = MeshFilter()
        mf.mesh_name = name
        mf.mesh_path = mesh_path
        ent.add_component(mf)
        ent.add_component(MeshRenderer())
    _apply_import_materials(ent, asset_path)
    if ent is not None and not is_skinned:
        _attach_blendshapes_if_needed(mw, ent, asset_path)
    mw._hierarchy.refresh()
    if ent:
        on_entity_selected(mw, ent)


def _apply_import_materials(ent, asset_path: str):
    if ent is None:
        return
    try:
        from core.assets.importer import _read_mesh_import
        mats = [p for p in _read_mesh_import(asset_path).get("materials", []) if p]
        if not mats:
            return
        comp = None
        for candidate in list(ent._components.values()):
            if type(candidate).__name__ in ("MeshRenderer", "SkinnedMeshRenderer"):
                comp = candidate
                break
        if comp is not None:
            comp.materials = [{"path": p} for p in mats]
    except Exception:
        pass


