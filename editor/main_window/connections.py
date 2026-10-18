# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from editor.main_window.handlersp import (
    on_entity_selected,
    on_entities_selected,
    on_entity_selected_from_viewport,
    on_entities_selected_from_viewport,
    on_entity_double_clicked,
    on_entity_dropped,
    on_gizmo_mode_changed,
    on_gizmo_space_changed,
    on_multigizmo_toggled,
    on_multigizmo_align_changed,
    on_multigizmo_lock_toggled,
    on_multigizmo_visible_toggled,
    on_grid_toggled,
    on_snap_toggled,
    on_snap_t_changed,
    on_snap_r_changed,
    on_snap_s_changed,
    on_render_mode_changed,
    on_skybox_toggled,
    on_effects_toggled,
    on_camera_projection_changed,
    on_camera_2d_toggled,
    on_camera_type_changed,
    on_camera_2d_changed,
    on_import_model,
    on_file_selected,
    on_project_file_double_clicked,
    open_scene_in_tab,
    on_open_prefab_editor,
    on_undo_history_navigated,
)


def _matches_toolbar_key(key: str) -> bool:
    try:
        from editor.toolbar_registry import get_toolbar_defs
        for entry in get_toolbar_defs():
            try:
                keys = [entry.get("config_key")] + list(entry.get("mirror_keys", []) or [])
                if key in keys:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def connect_signals(mw):
    mw._hierarchy.entity_selected.connect(lambda e: on_entity_selected(mw, e))
    mw._hierarchy.entities_selected.connect(lambda es: on_entities_selected(mw, es))
    mw._hierarchy.entity_double_clicked.connect(lambda eid: on_entity_double_clicked(mw, eid))
    mw._viewport.entity_selected.connect(lambda e: on_entity_selected_from_viewport(mw, e))
    mw._viewport.entities_selected.connect(lambda es: on_entities_selected_from_viewport(mw, es))
    mw._viewport.entity_dropped.connect(lambda p, w, e: on_entity_dropped(mw, p, w, e))
    mw._viewport.scene_modified.connect(mw._hierarchy.refresh)
    mw._scene_toolbar.gizmo_mode_changed.connect(lambda m: on_gizmo_mode_changed(mw, m))
    mw._scene_toolbar.gizmo_space_changed.connect(lambda s: on_gizmo_space_changed(mw, s))
    mw._scene_toolbar.multigizmo_toggled.connect(lambda e: on_multigizmo_toggled(mw, e))
    mw._scene_toolbar.multigizmo_align_changed.connect(lambda a: on_multigizmo_align_changed(mw, a))
    mw._scene_toolbar.multigizmo_lock_toggled.connect(lambda l: on_multigizmo_lock_toggled(mw, l))
    mw._scene_toolbar.multigizmo_visible_toggled.connect(lambda v: on_multigizmo_visible_toggled(mw, v))
    mw._render_toolbar.render_mode_changed.connect(lambda m: on_render_mode_changed(mw, m))
    mw._render_toolbar.skybox_toggled.connect(lambda e: on_skybox_toggled(mw, e))
    mw._render_toolbar.effects_toggled.connect(lambda e: on_effects_toggled(mw, e))
    mw._render_toolbar.camera_projection_changed.connect(lambda: on_camera_projection_changed(mw))
    mw._render_toolbar.mode_2d_toggled.connect(lambda: on_camera_2d_toggled(mw))
    mw._render_toolbar.grid_toggled.connect(lambda e: on_grid_toggled(mw, e))
    mw._render_toolbar.snap_toggled.connect(lambda e: on_snap_toggled(mw, e))
    mw._render_toolbar.snap_translate_changed.connect(lambda v: on_snap_t_changed(mw, v))
    mw._render_toolbar.snap_rotate_changed.connect(lambda v: on_snap_r_changed(mw, v))
    mw._render_toolbar.snap_scale_changed.connect(lambda v: on_snap_s_changed(mw, v))
    mw._viewport.camera._on_projection_changed = lambda: on_camera_type_changed(mw)
    mw._viewport.camera._on_2d_mode_changed = lambda: on_camera_2d_changed(mw)
    mw._project.import_model_requested.connect(lambda p: on_import_model(mw, p))
    mw._project.file_selected.connect(lambda p: on_file_selected(mw, p))
    mw._project.file_double_clicked.connect(lambda p: on_project_file_double_clicked(mw, p))
    mw._project._open_scene_callback = lambda p: open_scene_in_tab(mw, p)
    mw._hierarchy.select_prefab_asset.connect(lambda p: on_file_selected(mw, p))
    mw._hierarchy.open_prefab_editor.connect(lambda p: on_open_prefab_editor(mw, p))
    mw._inspector.open_prefab_editor.connect(lambda p: on_open_prefab_editor(mw, p))
    from core.config.config import get_global_config
    cfg = get_global_config()
    try:
        from editor.main_window.toolbar import load_main_toolbar_state, apply_toolbar_runtime_state
        load_main_toolbar_state(mw)
        apply_toolbar_runtime_state(mw)
    except Exception:
        pass
    mw._undo_history.history_navigated.connect(lambda: on_undo_history_navigated(mw))

    def _on_toolbar_cfg(key, value):
        try:
            if _matches_toolbar_key(key):
                from editor.toolbar_registry import get_toolbar_registry
                reg = get_toolbar_registry(mw)
                reg.sync_key(key, mw)
        except Exception:
            pass
    cfg.on_changed(_on_toolbar_cfg)
