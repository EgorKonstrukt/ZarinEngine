# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.engine.eng import Engine
from core.maths.math3d import Mat4
from core.components.rendering.renderers.video_renderer import VideoRenderer
from core.renderer.videor.player import VideoPlayer


class VideoRendererGL:
    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._players: dict[str, VideoPlayer] = {}
        self._build_buffers()

    def _build_buffers(self):
        quad = np.array([
            -0.5, -0.5, 0.0, 0.0, 0.0,
             0.5, -0.5, 0.0, 1.0, 0.0,
             0.5,  0.5, 0.0, 1.0, 1.0,
            -0.5,  0.5, 0.0, 0.0, 1.0,
        ], dtype=np.float32)
        idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
        self._vbo = self._ctx.buffer(quad.tobytes())
        self._ibo = self._ctx.buffer(idx.tobytes())
        self._vao = self._ctx.vertex_array(
            self._prog,
            [(self._vbo, "3f 2f", "in_position", "in_uv")],
            self._ibo
        )

    def _player_key(self, entity_id: str, video_path: str) -> str:
        return f"{entity_id}|{video_path}"

    def ensure_player(self, entity_id: str, video_path: str,
                       loop: bool, volume: float, offset: float = 0.0,
                       audio_source_entity_id: str = "") -> VideoPlayer:
        key = self._player_key(entity_id, video_path)
        player = self._players.get(key)
        if player is None:
            player = VideoPlayer(self._ctx, video_path, loop, volume, offset, audio_source_entity_id)
            self._players[key] = player
        return player

    def remove_player(self, entity_id: str, video_path: str):
        key = self._player_key(entity_id, video_path)
        player = self._players.pop(key, None)
        if player:
            player.dispose()

    def _dispose_all(self):
        for player in self._players.values():
            player.dispose()
        self._players.clear()

    def _remove_stale_players(self, active_keys: set[str]):
        stale = [k for k in self._players if k not in active_keys]
        for k in stale:
            p = self._players.pop(k, None)
            if p:
                p.dispose()

    def render_snapshot(self, video_items: list, view_mat: Mat4, proj_mat: Mat4):
        if not self._prog or not self._vao:
            return
        eng = Engine.instance()
        is_play = eng is not None and eng.play_mode
        if not is_play:
            self._dispose_all()
            return
        if not video_items:
            self._dispose_all()
            return
        active_keys: set[str] = set()
        prog = self._prog
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = True
        for item in video_items:
            player_key = self._player_key(item.entity_id, item.video_path)
            active_keys.add(player_key)
            player = self._players.get(player_key)
            if player is None:
                player = self.ensure_player(
                    item.entity_id, item.video_path,
                    item.loop, item.volume, item.offset,
                    item.audio_source_entity_id
                )
                active_keys.add(player_key)
            if not player.is_playing() and not player.is_finished():
                player.play()
            player.set_loop(item.loop)
            player.set_volume(item.volume)
            player.set_offset(item.offset)
            player.update_texture()
            tex = player.get_texture()
            if tex is None:
                continue
            model_f32 = item.world_matrix.to_f32()
            if "u_model" in prog:
                prog["u_model"].write(model_f32.tobytes())
            if "u_color" in prog:
                prog["u_color"].write(np.array(item.color, dtype=np.float32).tobytes())
            if "u_flip" in prog:
                prog["u_flip"].write(np.array(
                    [1.0 if item.flip_x else 0.0, 1.0 if item.flip_y else 0.0],
                    dtype=np.float32
                ).tobytes())
            if "u_alpha_cutoff" in prog:
                prog["u_alpha_cutoff"].value = 0.01
            tex.use(0)
            if "u_texture" in prog:
                prog["u_texture"].value = 0
            self._vao.render(moderngl.TRIANGLES)
        self._ctx.enable(moderngl.CULL_FACE)
        self._remove_stale_players(active_keys)

    def render(self, scene, view_mat: Mat4, proj_mat: Mat4):
        if not self._prog or not self._vao:
            return
        eng = Engine.instance()
        is_play = eng is not None and eng.play_mode
        if not is_play:
            self._dispose_all()
            return
        prog = self._prog
        view_f32 = view_mat.to_f32()
        proj_f32 = proj_mat.to_f32()
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = True
        for ent in scene.get_entities_with_component(VideoRenderer):
            if not ent.active:
                continue
            vr = ent.get_component(VideoRenderer)
            if not vr or not vr.enabled:
                continue
            tr = ent.transform
            if not tr:
                continue
            player_key = self._player_key(ent._id, vr.video_path)
            active_keys.add(player_key)
            if not vr.video_path:
                continue
            player = self._players.get(player_key)
            if player is None:
                player = self.ensure_player(ent._id, vr.video_path, vr.loop, vr.volume, vr.offset, vr.audio_source_entity_id)
                active_keys.add(player_key)
            if not player.is_playing() and not player.is_finished():
                player.play()
            player.set_loop(vr.loop)
            player.set_volume(vr.volume)
            player.set_offset(vr.offset)
            player.update_texture()
            tex = player.get_texture()
            if tex is None:
                continue
            model_f32 = tr.world_matrix.to_f32()
            if "u_model" in prog:
                prog["u_model"].write(model_f32.tobytes())
            color = vr.color
            if "u_color" in prog:
                prog["u_color"].write(np.array(color, dtype=np.float32).tobytes())
            if "u_flip" in prog:
                prog["u_flip"].write(np.array(
                    [1.0 if vr.flip_x else 0.0, 1.0 if vr.flip_y else 0.0],
                    dtype=np.float32
                ).tobytes())
            if "u_alpha_cutoff" in prog:
                prog["u_alpha_cutoff"].value = 0.01
            tex.use(0)
            if "u_texture" in prog:
                prog["u_texture"].value = 0
            self._vao.render(moderngl.TRIANGLES)
        self._ctx.enable(moderngl.CULL_FACE)
        self._remove_stale_players(active_keys)

    def release(self):
        for player in self._players.values():
            player.dispose()
        self._players.clear()
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._ibo:
            self._ibo.release()
