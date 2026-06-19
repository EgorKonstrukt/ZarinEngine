import numpy as np
import moderngl
from core.math3d import Mat4
from core.input_system import Input, KeyCode
from core.compute_shader import ComputeShader
from core.logger import Logger


_VERT_SRC = """
#version 460 core
in vec2 in_offset;
layout(std430, binding = 2) buffer GridState {
    uint cells[];
};
uniform uint u_width;
uniform float u_cell_size;
uniform mat4 u_mvp;

out vec3 v_color;

void main() {
    uint i = gl_InstanceID;
    uint state = cells[i];
    if ((state & 1u) == 0u) {
        gl_Position = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }
    uint x = i % u_width;
    uint y = i / u_width;
    float px = float(x) * u_cell_size;
    float py = float(y) * u_cell_size;
    float hs = u_cell_size * 0.45;
    vec2 p = vec2(px, py) + in_offset * hs;

    uint gen = (state >> 16u) & 0xFFFFu;
    float t = min(float(gen) / 80.0, 1.0);
    v_color = vec3(0.2 + t * 0.8, 0.9 - t * 0.7, 0.3 + t * 0.5);

    gl_Position = u_mvp * vec4(p, 0.0, 1.0);
}
"""

_FRAG_SRC = """
#version 460 core
in vec3 v_color;
out vec4 frag_color;
void main() {
    frag_color = vec4(v_color, 1.0);
}
"""


class GameOfLife:
    compute_shader_path: str = "assets/shaders/GameOfLife.compute"
    grid_width: int = 64
    grid_height: int = 64
    cell_spacing: float = 0.12
    update_interval: float = 0.1

    def __init__(self):
        self._entity = None
        self._ctx = None
        self._cs = None
        self._render_prog = None
        self._vao = None
        self._rd = None
        self._wr = None
        self._w = 64
        self._h = 64
        self._timer = 0.0
        self._paused = False

    def _get_ctx(self):
        if self._ctx:
            return self._ctx
        try:
            from core.engine import Engine
            eng = Engine.instance()
            if not eng:
                return None
            vp = eng.viewport
            if vp and hasattr(vp, '_ctx'):
                self._ctx = vp._ctx
                return self._ctx
        except Exception:
            pass
        return None

    def _randomize(self):
        n = self._w * self._h
        rng = np.random.default_rng()
        init = rng.integers(0, 2, n, dtype=np.uint32).tobytes()
        self._rd.write(init)
        self._wr.write(b'\x00' * (n * 4))

    def _clear(self):
        n = self._w * self._h
        z = b'\x00' * (n * 4)
        self._rd.write(z)
        self._wr.write(z)

    def on_start(self):
        ctx = self._get_ctx()
        if not ctx:
            Logger.error("GoL: нет контекста OpenGL")
            return

        self._w = max(1, self.grid_width)
        self._h = max(1, self.grid_height)
        self._timer = 0.0
        self._paused = False

        cs = ComputeShader.load_from_file(ctx, self.compute_shader_path)
        if not cs:
            Logger.error(f"GoL: {self.compute_shader_path} не загрузился")
            return
        self._cs = cs

        n = self._w * self._h
        rng = np.random.default_rng()
        init = rng.integers(0, 2, n, dtype=np.uint32)
        self._rd = ctx.buffer(init.tobytes())
        self._wr = ctx.buffer(b'\x00' * (n * 4))

        self._render_prog = ctx.program(vertex_shader=_VERT_SRC, fragment_shader=_FRAG_SRC)

        corners = np.array([
            -1.0, -1.0,  1.0, -1.0,  1.0,  1.0,
            -1.0, -1.0,  1.0,  1.0, -1.0,  1.0,
        ], dtype=np.float32)
        vbo = ctx.buffer(corners.tobytes())
        self._vao = ctx.vertex_array(self._render_prog, [(vbo, "2f", "in_offset")])

        Logger.info(f"GoL: {self._w}x{self._h} grid, {n} cells")
        Logger.info("GoL: SPACE = pause, R = randomize, C = clear")

    def on_update(self, dt: float):
        if not self._cs:
            return

        if Input.GetKeyDown(KeyCode.SPACE):
            self._paused = not self._paused
            Logger.info(f"GoL: {'PAUSED' if self._paused else 'RUNNING'}")

        if Input.GetKeyDown(KeyCode.R):
            self._randomize()

        if Input.GetKeyDown(KeyCode.C):
            self._clear()

    def gizmo_meshes(self):
        if not self._cs or not self._vao:
            return []

        ctx = self._ctx
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

        if not self._paused:
            self._timer += 0.016
            if self.update_interval > 0.0:
                if self._timer >= self.update_interval:
                    self._timer -= self.update_interval
                    self._step()
            else:
                if self._timer >= 0.0:
                    self._timer = 0.0
                    self._step()

        ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)

        self._rd.bind_to_storage_buffer(2)

        try:
            from core.engine import Engine
            eng = Engine.instance()
            vp = eng.viewport
            cam = vp.camera
            fw, fh = vp._get_physical_dims()
            aspect = fw / max(1, fh)
            view = cam.get_view_matrix()
            proj = cam.get_projection_matrix(aspect)
            mvp = view * proj
        except Exception:
            mvp = Mat4()

        rp = self._render_prog
        rp["u_mvp"].write(mvp.to_f32().tobytes())
        rp["u_width"] = self._w
        rp["u_cell_size"] = self.cell_spacing

        ctx.disable(moderngl.DEPTH_TEST)
        self._vao.render(moderngl.TRIANGLES, vertices=6, instances=self._w * self._h)
        ctx.enable(moderngl.DEPTH_TEST)

        ctx.disable(moderngl.BLEND)

        return []

    def _step(self):
        prog = self._cs._program
        w, h = self._w, self._h
        prog["u_width"] = w
        prog["u_height"] = h

        self._rd.bind_to_storage_buffer(0)
        self._wr.bind_to_storage_buffer(1)

        groups = (w * h + 255) // 256
        prog.run(groups, 1, 1)

        self._rd, self._wr = self._wr, self._rd

    def on_destroy(self):
        for buf in (self._rd, self._wr):
            if buf:
                buf.release()
        if self._vao:
            self._vao.release()
        if self._render_prog:
            self._render_prog.release()
        if self._cs:
            self._cs.release()
