from __future__ import annotations
import math
import numpy as np
import moderngl
from typing import Optional
from core.math3d import Vec3


class GridRenderer:
    """Renders the viewport grid with adaptive sizing."""

    def __init__(self, ctx: moderngl.Context, grid_prog: moderngl.Program):
        self._ctx = ctx
        self._prog = grid_prog
        self._grid_vbo: Optional[moderngl.Buffer] = None
        self._grid_ibo: Optional[moderngl.Buffer] = None
        self._grid_vao: Optional[moderngl.VertexArray] = None
        self._show_grid: bool = True
        self._grid_world_size: float = 2000.0
        self._grid_2d_mode: bool = False
        self._grid_zoom_distance: float = 5.0
        self._grid_size: float = 10.0
        self._build()

    def _build(self):
        s = self._grid_world_size
        v = np.array([-s, 0.0, -s,  s, 0.0, -s,  s, 0.0, s,  -s, 0.0, s], dtype=np.float32)
        idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
        self._grid_vbo = self._ctx.buffer(v.tobytes(), dynamic=True)
        self._grid_ibo = self._ctx.buffer(idx.tobytes())
        self._grid_vao = self._ctx.vertex_array(
            self._prog,
            [(self._grid_vbo, "3f", "in_position")],
            self._grid_ibo
        )

    def compute_grid_step(self, cam_pos: Vec3) -> float:
        if self._grid_2d_mode:
            view_size = self._grid_zoom_distance * math.tan(math.radians(60.0) * 0.5)
            step_raw = view_size / 2.0
        else:
            step_raw = max(abs(cam_pos.y) * 0.5, 1.0)
        mag = 10 ** math.floor(math.log10(max(step_raw, 1e-10)))
        norm = step_raw / mag
        if norm < 1.5:
            norm = 1.0
        elif norm < 3.5:
            norm = 2.0
        elif norm < 7.5:
            norm = 5.0
        else:
            norm = 10.0
        return mag * norm

    def render(self, view_f32: np.ndarray, proj_f32: np.ndarray, cam_pos: Vec3):
        if not self._show_grid:
            return
        s = self._grid_world_size
        if self._grid_2d_mode:
            v = np.array([-s, -s, 0.0,  s, -s, 0.0,  s, s, 0.0,  -s, s, 0.0], dtype=np.float32)
        else:
            v = np.array([-s, 0.0, -s,  s, 0.0, -s,  s, 0.0, s,  -s, 0.0, s], dtype=np.float32)
        self._grid_vbo.write(v.tobytes())
        grid_step = self.compute_grid_step(cam_pos)
        if "u_view" in self._prog:
            self._prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in self._prog:
            self._prog["u_proj"].write(proj_f32.tobytes())
        if "u_camera_pos" in self._prog:
            self._prog["u_camera_pos"].write(
                np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes()
            )
        if "u_grid_size" in self._prog:
            self._prog["u_grid_size"].value = float(grid_step)
        if "u_grid_2d" in self._prog:
            self._prog["u_grid_2d"].value = 1.0 if self._grid_2d_mode else 0.0
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = False
        self._grid_vao.render(moderngl.TRIANGLES)
        self._ctx.depth_mask = True
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._ctx.enable(moderngl.CULL_FACE)

    @property
    def show(self) -> bool:
        return self._show_grid

    @show.setter
    def show(self, v: bool):
        self._show_grid = v

    @property
    def grid_2d_mode(self) -> bool:
        return self._grid_2d_mode

    @grid_2d_mode.setter
    def grid_2d_mode(self, v: bool):
        self._grid_2d_mode = v

    @property
    def grid_zoom_distance(self) -> float:
        return self._grid_zoom_distance

    @grid_zoom_distance.setter
    def grid_zoom_distance(self, v: float):
        self._grid_zoom_distance = v

    @property
    def grid_size(self) -> float:
        return self._grid_size

    @grid_size.setter
    def grid_size(self, v: float):
        self._grid_size = max(0.01, v)
