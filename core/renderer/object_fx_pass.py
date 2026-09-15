# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Per-object graphics effects."""

from __future__ import annotations
import time
import numpy as np
from core.foundation.logger import Logger
from core.components.rendering.effects.object_effect import ObjectEffect
from core.components.rendering.effects.voxelize_effect import VoxelizeEffect


class ObjectFxPassMixin:
    """Per-object graphics effects."""


    _FX_PASSTHROUGH_GEOM = """#version 330 core
layout(triangles) in;
layout(triangle_strip, max_vertices = 3) out;
in vec3 gs_world_pos[3];
in vec3 gs_normal[3];
in vec2 gs_uv[3];
in vec3 gs_view_pos[3];
in vec3 gs_local_pos[3];
out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
out vec3 v_local_pos;
void main() {
    for (int i = 0; i < 3; i++) {
        gl_Position = gl_in[i].gl_Position;
        v_world_pos = gs_world_pos[i];
        v_normal = gs_normal[i];
        v_uv = gs_uv[i];
        v_view_pos = gs_view_pos[i];
        v_local_pos = gs_local_pos[i];
        EmitVertex();
    }
    EndPrimitive();
}
"""


    def _find_object_effect(self, ent) -> list:
        result = []
        for comp in ent.get_all_components():
            if isinstance(comp, ObjectEffect) and comp.enabled:
                result.append(comp)
        return result


    def _render_object_effects(self, entries, view_f32, proj_f32, cam_pos, lights,
                                 selected_entities, outline_queue):
        if not entries:
            return
        t = time.time()
        by_prog: dict = {}
        for entry in entries:
            fx_list = entry[6] if len(entry) > 6 else None
            if not fx_list:
                continue
            key = tuple(sorted(type(fx).__name__ for fx in fx_list))
            by_prog.setdefault(key, []).append(entry)
        for key, group in by_prog.items():
            fx_list = group[0][6]
            prog = self._get_fx_program(fx_list)
            if prog is None:
                continue
            self._set_scene_uniforms(prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=False)
            for entry in group:
                ent, tr, mesh, mr = entry[:4]
                wm = entry[4]
                try:
                    mat = self._materials.load_material(mr.get_material_path(0))
                    model_f32 = wm.to_f32()
                    if "u_model" in prog:
                        prog["u_model"].write(model_f32.tobytes())
                    nm = np.eye(3, dtype=np.float32).T
                    try:
                        m3 = wm._d[:3, :3].copy()
                        m3[:, 0] /= max(1e-10, float(np.linalg.norm(m3[:, 0])))
                        m3[:, 1] /= max(1e-10, float(np.linalg.norm(m3[:, 1])))
                        m3[:, 2] /= max(1e-10, float(np.linalg.norm(m3[:, 2])))
                        nm = m3.T.astype(np.float32)
                    except Exception:
                        pass
                    if "u_normal_matrix" in prog:
                        prog["u_normal_matrix"].write(nm.tobytes())
                    center = [wm._d[0, 3], wm._d[1, 3], wm._d[2, 3]]
                    scale = max(
                        float(np.linalg.norm(wm._d[:3, 0])),
                        float(np.linalg.norm(wm._d[:3, 1])),
                        float(np.linalg.norm(wm._d[:3, 2])),
                        1e-4,
                    )
                    if "u_obj_center" in prog:
                        prog["u_obj_center"].write(np.array(center, dtype=np.float32).tobytes())
                    if "u_obj_scale" in prog:
                        prog["u_obj_scale"].value = scale
                    if "u_use_instancing" in prog:
                        prog["u_use_instancing"].value = 0
                    if "u_use_skinning" in prog:
                        prog["u_use_skinning"].value = 0
                    self._materials.apply_material(mat, prog, mr)
                    ObjectEffect.reset_all_defaults(prog)
                    for fx in fx_list:
                        fx.bind(prog, t)
                    vox = next((f for f in fx_list if isinstance(f, VoxelizeEffect)), None)
                    ds = any(getattr(fx, 'double_sided', False) for fx in fx_list)
                    show_base = (vox is None) or (not vox.enabled) or vox.show_base_mesh
                    if show_base:
                        self._render_mesh_double_sided(prog, mesh, ds)
                    if vox is not None and vox.enabled and vox.amount > 0.0:
                        self._render_voxel_instances(entry, vox, view_f32, proj_f32, cam_pos)
                    if selected_entities and ent in selected_entities:
                        outline_queue.append((mesh, wm))
                except Exception as e:
                    Logger.error(f"ObjectEffect render failed on '{getattr(ent, 'name', '?')}': {e}", e)
