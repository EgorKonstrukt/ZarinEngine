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
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen


def on_entity_selected(mw, entity):
    from core.foundation.cmd import get_history
    get_history().set_current_selection(entity)
    mw._hierarchy.set_selected_entity(entity)
    mw._inspector.set_entity(entity)
    mw._viewport.set_selected_entity(entity)
    if hasattr(mw, '_mesh_editor') and mw._mesh_editor:
        mw._mesh_editor.set_entity(entity)
    if hasattr(mw, '_terrain_editor') and mw._terrain_editor:
        mw._terrain_editor.set_entity(entity)
    if hasattr(mw, '_animation') and mw._animation:
        mw._animation.set_entity(entity)


def on_entities_selected(mw, entities):
    from core.foundation.cmd import get_history
    get_history().set_current_selection(list(entities) if entities else None)
    mw._viewport.set_selected_entities(entities)
    if entities:
        mw._inspector.set_selected_entities(entities)
    if hasattr(mw, '_animation') and mw._animation:
        mw._animation.set_entity(entities[0] if entities else None)
    if hasattr(mw, '_terrain_editor') and mw._terrain_editor:
        mw._terrain_editor.set_entity(entities[0] if entities else None)


def on_entity_selected_from_viewport(mw, entity):
    from core.foundation.cmd import get_history
    get_history().set_current_selection(entity)
    mw._inspector.set_entity(entity)
    mw._hierarchy.set_selected_entity(entity)
    if hasattr(mw, '_mesh_editor') and mw._mesh_editor:
        mw._mesh_editor.set_entity(entity)
    if hasattr(mw, '_terrain_editor') and mw._terrain_editor:
        mw._terrain_editor.set_entity(entity)
    if hasattr(mw, '_animation') and mw._animation:
        mw._animation.set_entity(entity)


def on_entities_selected_from_viewport(mw, entities):
    from core.foundation.cmd import get_history
    get_history().set_current_selection(list(entities) if entities else None)
    if entities:
        mw._inspector.set_selected_entities(entities)
        mw._hierarchy.set_selected_entities(entities)
    else:
        mw._inspector.set_entity(None)
        mw._hierarchy.set_selected_entity(None)
    if hasattr(mw, '_animation') and mw._animation:
        mw._animation.set_entity(entities[0] if entities else None)


def on_entity_double_clicked(mw, eid: str):
    if not mw._engine.scene:
        return
    entity = mw._engine.scene.get_entity(eid)
    if not entity:
        return
    t = entity.transform
    if not t:
        return
    try:
        from editor.entframe import compute_entity_frame
        vp = getattr(mw, "_viewport", None)
        renderer = getattr(vp, "_renderer", None) if vp is not None else None
        if renderer is None and vp is not None:
            try:
                renderer = vp.renderer
            except Exception:
                renderer = None
        center, radius = compute_entity_frame(entity, renderer)
        mw._viewport.camera.frame_bounds(center, radius)
    except Exception:
        try:
            mw._viewport.camera.frame_bounds(t.position)
        except Exception:
            pass


def sync_after_undo(mw):
    from core.foundation.cmd import get_history
    h = get_history()
    sel = h.current_selection if isinstance(getattr(h, 'current_selection', None), list) else (h.last_affected_entity or h.current_selection)
    scene = mw._engine.scene
    if isinstance(sel, list):
        if scene:
            resolved = []
            for e in sel:
                if e:
                    live = scene.get_entity(e.id)
                    if live:
                        resolved.append(live)
            sel = resolved
        else:
            sel = []
    elif sel and scene:
        live = scene.get_entity(sel.id)
        if live:
            sel = live
        else:
            sel = None
    mw._hierarchy.refresh()
    mw._hierarchy.blockSignals(True)
    if isinstance(sel, list):
        mw._hierarchy.set_selected_entities(sel)
        mw._inspector.set_selected_entities(sel)
        mw._viewport.set_selected_entities(sel)
    elif sel:
        mw._hierarchy.set_selected_entity(sel)
        mw._inspector.setUpdatesEnabled(False)
        mw._inspector.set_entity(sel)
        mw._inspector.setUpdatesEnabled(True)
        mw._viewport.set_selected_entity(sel)
        if hasattr(mw, '_animation') and mw._animation:
            mw._animation.set_entity(sel)
    else:
        sel_ent = mw._hierarchy._selected_entity
        mw._inspector.set_entity(sel_ent if sel_ent else None)
        mw._viewport.set_selected_entity(sel_ent if sel_ent else None)
        if hasattr(mw, '_animation') and mw._animation:
            mw._animation.set_entity(sel_ent if sel_ent else None)
    mw._hierarchy.blockSignals(False)
    if scene:
        scene.mark_dirty()


def undo(mw):
    from core.foundation.cmd import get_history
    get_history().undo()
    sync_after_undo(mw)


def redo(mw):
    from core.foundation.cmd import get_history
    get_history().redo()
    sync_after_undo(mw)


def on_undo_history_navigated(mw):
    sync_after_undo(mw)


def on_file_selected(mw, path: str):
    mw._inspector.show_import_settings(path)


