from enum import Enum
import numpy as np
import moderngl
from core.math3d import Mat4
from core.input_system import Input, KeyCode
from core.compute_shader import ComputeShader
from core.logger import Logger


class RuleType(Enum):
    CLOUDS = "B5678/S45678 (Clouds)"
    BAYS = "B4/S123456 (M.Bays)"
    TENDRILS = "B34/S34 (Tendrils)"
    MID = "B456/S456 (Mid)"
    CORAL = "B34/S456 (Coral)"


_RULES = {
    RuleType.CLOUDS:   (5, 8, 4, 8),
    RuleType.BAYS:     (4, 4, 1, 6),
    RuleType.TENDRILS: (3, 4, 3, 4),
    RuleType.MID:      (4, 6, 4, 6),
    RuleType.CORAL:    (3, 4, 4, 6),
}


class PlacementType(Enum):
    RANDOM = "Random"
    DENSE = "Dense"
    SPARSE = "Sparse"
    CENTER = "Center Ball"
    LAYERS = "Layers"
    CHECKER = "Checker"


_VERT_SRC = """
#version 460 core

layout(std430, binding = 2) buffer GridState {
    uint cells[];
};

uniform uint u_width;
uniform uint u_height;
uniform float u_cell_size;
uniform mat4 u_mvp;

out vec3 v_color;
out vec3 v_normal;

const vec3 corners[8] = vec3[](
    vec3(-0.5, -0.5, -0.5),
    vec3( 0.5, -0.5, -0.5),
    vec3(-0.5,  0.5, -0.5),
    vec3( 0.5,  0.5, -0.5),
    vec3(-0.5, -0.5,  0.5),
    vec3( 0.5, -0.5,  0.5),
    vec3(-0.5,  0.5,  0.5),
    vec3( 0.5,  0.5,  0.5)
);

const int face_corners[24] = int[](
    4,5,7,6,
    1,0,2,3,
    5,1,3,7,
    0,4,6,2,
    6,7,3,2,
    0,1,5,4
);

const vec3 face_normals[6] = vec3[](
    vec3(0,0,1), vec3(0,0,-1),
    vec3(1,0,0), vec3(-1,0,0),
    vec3(0,1,0), vec3(0,-1,0)
);

void main() {
    uint i = gl_InstanceID;
    uint state = cells[i];
    if ((state & 1u) == 0u) {
        gl_Position = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    uint xy = u_width * u_height;
    uint z = i / xy;
    uint r = i % xy;
    uint y = r / u_width;
    uint x = r % u_width;

    float px = float(x) * u_cell_size;
    float py = float(y) * u_cell_size;
    float pz = float(z) * u_cell_size;

    int vi = gl_VertexID;
    int face = vi / 6;
    int tri = (vi % 6) / 3;
    int vlocal = vi % 3;

    int base = face * 4;
    int c0 = face_corners[base + 0];
    int c1 = face_corners[base + 1];
    int c2 = face_corners[base + 2];
    int c3 = face_corners[base + 3];

    vec3 local;
    if (tri == 0) {
        local = (vlocal == 0) ? corners[c0] : (vlocal == 1) ? corners[c1] : corners[c2];
    } else {
        local = (vlocal == 0) ? corners[c0] : (vlocal == 1) ? corners[c2] : corners[c3];
    }

    float hs = u_cell_size * 0.4;
    vec3 wp = vec3(px, py, pz) + local * hs;

    uint gen = (state >> 16u) & 0xFFFFu;
    float phase = float(gen) * 0.2;
    v_color = vec3(
        0.5 + 0.5 * sin(phase),
        0.5 + 0.5 * sin(phase + 2.094),
        0.5 + 0.5 * sin(phase + 4.189)
    );

    v_normal = face_normals[face];
    gl_Position = u_mvp * vec4(wp, 1.0);
}
"""

_FRAG_SRC = """
#version 460 core
in vec3 v_color;
in vec3 v_normal;
out vec4 frag_color;

void main() {
    vec3 n = normalize(v_normal);
    vec3 light_dir = normalize(vec3(2.0, 4.0, 3.0));
    float diff = max(dot(n, light_dir), 0.0);
    float ambient = 0.4;
    float light = ambient + (1.0 - ambient) * diff;
    frag_color = vec4(v_color * light, 1.0);
}
"""


class GameOfLife3D:
    compute_shader_path: str = "assets/shaders/GameOfLife3D.compute"
    grid_width: int = 32
    grid_height: int = 32
    grid_depth: int = 32
    cell_spacing: float = 0.25
    update_interval: float = 0.12
    rule: RuleType = RuleType.CLOUDS
    placement: PlacementType = PlacementType.RANDOM

    def __init__(self):
        self._entity = None
        self._rd = None
        self._wr = None
        self._cs = None
        self._render_prog = None
        self._vao = None
        self._w = 32
        self._h = 32
        self._d = 32
        self._timer = 0.0
        self._paused = False
        self._step_count = 0

    def _get_ctx(self):
        try:
            from core.engine import Engine
            eng = Engine.instance()
            if not eng:
                return None
            vp = eng.viewport
            if vp and hasattr(vp, '_ctx'):
                return vp._ctx
        except Exception:
            pass
        return None

    def _randomize(self):
        n = self._w * self._h * self._d
        rng = np.random.default_rng()
        ptype = self.placement
        if ptype == PlacementType.RANDOM:
            init = (rng.random(n) < 0.2).astype(np.uint32)
        elif ptype == PlacementType.DENSE:
            init = (rng.random(n) < 0.4).astype(np.uint32)
        elif ptype == PlacementType.SPARSE:
            init = (rng.random(n) < 0.08).astype(np.uint32)
        elif ptype == PlacementType.CENTER:
            init = np.zeros(n, dtype=np.uint32)
            cx, cy, cz = self._w // 2, self._h // 2, self._d // 2
            r = min(self._w, self._h, self._d) // 4
            for x in range(max(0, cx - r), min(self._w, cx + r + 1)):
                for y in range(max(0, cy - r), min(self._h, cy + r + 1)):
                    for z in range(max(0, cz - r), min(self._d, cz + r + 1)):
                        dx, dy, dz = x - cx, y - cy, z - cz
                        if dx*dx + dy*dy + dz*dz <= r*r:
                            idx = z * self._w * self._h + y * self._w + x
                            init[idx] = 1 if rng.random() < 0.6 else 0
        elif ptype == PlacementType.LAYERS:
            init = np.zeros(n, dtype=np.uint32)
            for z in range(self._d):
                alive = 1 if (z % 2 == 0) else 0
                for y in range(self._h):
                    for x in range(self._w):
                        if rng.random() < (0.5 if alive else 0.05):
                            idx = z * self._w * self._h + y * self._w + x
                            init[idx] = 1
        elif ptype == PlacementType.CHECKER:
            init = np.zeros(n, dtype=np.uint32)
            for z in range(self._d):
                for y in range(self._h):
                    for x in range(self._w):
                        if (x + y + z) % 2 == 0:
                            idx = z * self._w * self._h + y * self._w + x
                            init[idx] = 1
        else:
            init = (rng.random(n) < 0.2).astype(np.uint32)
        self._rd.write(init.tobytes())
        self._wr.write(b'\x00' * (n * 4))
        self._step_count = 0

    def _clear(self):
        n = self._w * self._h * self._d
        z = b'\x00' * (n * 4)
        self._rd.write(z)
        self._wr.write(z)
        self._step_count = 0

    def on_start(self):
        ctx = self._get_ctx()
        if not ctx:
            Logger.error("GoL3D: нет контекста OpenGL")
            return

        self._w = max(1, self.grid_width)
        self._h = max(1, self.grid_height)
        self._d = max(1, self.grid_depth)
        self._timer = 0.0
        self._paused = False
        self._step_count = 0

        cs = ComputeShader.load_from_file(ctx, self.compute_shader_path)
        if not cs:
            Logger.error(f"GoL3D: {self.compute_shader_path} не загрузился")
            self._cs = None
            return
        self._cs = cs

        self._rd = ctx.buffer(b'\x00' * (self._w * self._h * self._d * 4))
        self._wr = ctx.buffer(b'\x00' * (self._w * self._h * self._d * 4))
        self._randomize()

        self._render_prog = ctx.program(vertex_shader=_VERT_SRC, fragment_shader=_FRAG_SRC)

        self._vao = ctx.vertex_array(self._render_prog, [])

        n = self._w * self._h * self._d
        buf = np.frombuffer(self._rd.read(), dtype=np.uint32)
        alive = int((buf & 1).sum())
        Logger.info(f"GoL3D: {self._w}x{self._h}x{self._d} grid ({n} cells), alive={alive}")
        Logger.info("SPACE=pause R=randomize C=clear +/-=speed")

    def on_update(self, dt: float):
        if not self._cs:
            return

        if Input.GetKeyDown(KeyCode.SPACE):
            self._paused = not self._paused
            Logger.info(f"GoL3D: {'PAUSED' if self._paused else 'RUNNING'}")

        if Input.GetKeyDown(KeyCode.R):
            self._randomize()

        if Input.GetKeyDown(KeyCode.C):
            self._clear()

        if Input.GetKeyDown(KeyCode.EQUAL):
            self.update_interval = max(0.02, self.update_interval - 0.02)
            Logger.info(f"GoL3D: speed {self.update_interval:.2f}s")

        if Input.GetKeyDown(KeyCode.MINUS):
            self.update_interval = min(1.0, self.update_interval + 0.02)
            Logger.info(f"GoL3D: speed {self.update_interval:.2f}s")

    def gizmo_meshes(self):
        if not self._cs or not self._vao:
            return []

        ctx = self._get_ctx()
        if not ctx:
            return []

        ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)

        if not self._paused:
            self._timer += 0.016
            if self.update_interval > 0.0 and self._timer >= self.update_interval:
                self._timer -= self.update_interval
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
        rp["u_height"] = self._h
        rp["u_cell_size"] = self.cell_spacing

        total = self._w * self._h * self._d
        self._vao.render(moderngl.TRIANGLES, vertices=36, instances=total)

        return []

    def _step(self):
        prog = self._cs._program
        w, h, d = self._w, self._h, self._d
        prog["u_width"] = w
        prog["u_height"] = h
        prog["u_depth"] = d

        bmin, bmax, smin, smax = _RULES.get(self.rule, (4, 4, 1, 6))
        prog["u_birth_min"] = bmin
        prog["u_birth_max"] = bmax
        prog["u_survive_min"] = smin
        prog["u_survive_max"] = smax

        self._rd.bind_to_storage_buffer(0)
        self._wr.bind_to_storage_buffer(1)

        total = w * h * d
        groups = (total + 255) // 256
        prog.run(groups, 1, 1)

        self._rd, self._wr = self._wr, self._rd
        self._step_count += 1
        if self._step_count <= 3 or self._step_count % 30 == 0:
            buf = np.frombuffer(self._rd.read(), dtype=np.uint32)
            alive = int((buf & 1).sum())
            Logger.info(f"GoL3D: step={self._step_count} alive={alive}/{total}")

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
        self._rd = None
        self._wr = None
        self._vao = None
        self._render_prog = None
        self._cs = None
