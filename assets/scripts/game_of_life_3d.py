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
    AMOEBA = "B23456/S45 (Amoeba)"
    R5766 = "B6/S567 (Rule 5766)"
    R4555 = "B5/S45 (Rule 4555)"
    ARCH = "B3/S456 (Architecture)"
    PYRO = "B678/S4567 (Pyroclastic)"
    STABLE = "B14-19/S13-26 (Stable)"
    R445 = "B4/S4 (Rule 445)"
    MAZE = "B3/S12345 (Maze)"
    CRYSTAL = "B4/S123 (Crystal)"
    WORMS = "B45/S1234 (Worms)"
    SPHERES = "B67/S5678 (Spheres)"
    CONWAY3D = "B3/S23 (Conway 3D)"
    EXPLOSION = "B678/S345678 (Explosion)"
    GEODE = "B4567/S45678 (Geode)"
    BUBBLES = "B56/S456 (Bubbles)"
_RULES = {RuleType.CLOUDS: (5, 8, 4, 8), RuleType.BAYS: (4, 4, 1, 6), RuleType.TENDRILS: (3, 4, 3, 4), RuleType.MID: (4, 6, 4, 6), RuleType.CORAL: (3, 4, 4, 6), RuleType.AMOEBA: (2, 6, 4, 5), RuleType.R5766: (6, 6, 5, 7), RuleType.R4555: (5, 5, 4, 5), RuleType.ARCH: (3, 3, 4, 6), RuleType.PYRO: (6, 8, 4, 7), RuleType.STABLE: (14, 19, 13, 26), RuleType.R445: (4, 4, 4, 4), RuleType.MAZE: (3, 3, 1, 5), RuleType.CRYSTAL: (4, 4, 1, 3), RuleType.WORMS: (4, 5, 1, 4), RuleType.SPHERES: (6, 7, 5, 8), RuleType.CONWAY3D: (3, 3, 2, 3), RuleType.EXPLOSION: (6, 8, 3, 8), RuleType.GEODE: (4, 7, 4, 8), RuleType.BUBBLES: (5, 6, 4, 6)}
class PlacementType(Enum):
    RANDOM = "Random"
    DENSE = "Dense"
    SPARSE = "Sparse"
    CENTER = "Center Ball"
    LAYERS = "Layers"
    CHECKER = "Checker"
    CROSS = "3D Cross"
    PLANES = "3 Planes"
    HOLLOW_SPHERE = "Hollow Sphere"
    SOLID_CUBE = "Solid Cube"
    DIAGONALS = "Diagonals"
    TORUS = "Torus"
    HELIX = "Double Helix"
    GRID = "3D Grid"
    CORNERS = "Corners"
    EDGES = "Edges"
_VERT_SRC = """#version 460 core
layout(std430, binding = 2) buffer GridState { uint cells[]; };
uniform uint u_width; uniform uint u_height; uniform float u_cell_size; uniform float u_cell_scale; uniform float u_alpha; uniform mat4 u_mvp;
out vec3 v_color; out vec3 v_normal; out float v_alpha;
const vec3 corners[8] = vec3[](vec3(-0.5,-0.5,-0.5),vec3(0.5,-0.5,-0.5),vec3(-0.5,0.5,-0.5),vec3(0.5,0.5,-0.5),vec3(-0.5,-0.5,0.5),vec3(0.5,-0.5,0.5),vec3(-0.5,0.5,0.5),vec3(0.5,0.5,0.5));
const int face_corners[24] = int[](4,5,7,6,1,0,2,3,5,1,3,7,0,4,6,2,6,7,3,2,0,1,5,4);
const vec3 face_normals[6] = vec3[](vec3(0,0,1),vec3(0,0,-1),vec3(1,0,0),vec3(-1,0,0),vec3(0,1,0),vec3(0,-1,0));
void main() {
    uint i = gl_InstanceID; uint state = cells[i];
    if ((state & 1u) == 0u) { gl_Position = vec4(0.0); return; }
    uint xy = u_width * u_height; uint z = i / xy; uint r = i % xy; uint y = r / u_width; uint x = r % u_width;
    float px = float(x) * u_cell_size; float py = float(y) * u_cell_size; float pz = float(z) * u_cell_size;
    int vi = gl_VertexID; int face = vi / 6; int tri = (vi % 6) / 3; int vlocal = vi % 3; int base = face * 4;
    int c0 = face_corners[base]; int c1 = face_corners[base+1]; int c2 = face_corners[base+2]; int c3 = face_corners[base+3];
    vec3 local = (tri == 0) ? ((vlocal == 0) ? corners[c0] : (vlocal == 1) ? corners[c1] : corners[c2]) : ((vlocal == 0) ? corners[c0] : (vlocal == 1) ? corners[c2] : corners[c3]);
    float hs = u_cell_size * u_cell_scale * 0.4; vec3 wp = vec3(px, py, pz) + local * hs;
    uint gen = (state >> 16u) & 0xFFFFu; float phase = float(gen) * 0.2;
    v_color = vec3(0.5 + 0.5 * sin(phase), 0.5 + 0.5 * sin(phase + 2.094), 0.5 + 0.5 * sin(phase + 4.189));
    v_normal = face_normals[face]; v_alpha = u_alpha; gl_Position = u_mvp * vec4(wp, 1.0);
}"""
_FRAG_SRC = """#version 460 core
in vec3 v_color; in vec3 v_normal; in float v_alpha; out vec4 frag_color;
void main() {
    vec3 n = normalize(v_normal); vec3 light_dir = normalize(vec3(2.0, 4.0, 3.0));
    float diff = max(dot(n, light_dir), 0.0); float ambient = 0.4;
    float light = ambient + (1.0 - ambient) * diff; frag_color = vec4(v_color * light, v_alpha);
}"""
class GameOfLife3D:
    compute_shader_path: str = "assets/shaders/GameOfLife3D.compute"
    grid_width: int = 32
    grid_height: int = 32
    grid_depth: int = 32
    cell_spacing: float = 0.25
    cell_scale: float = 1.0
    cell_alpha: float = 1.0
    update_interval: float = 0.12
    rule: RuleType = RuleType.CLOUDS
    placement: PlacementType = PlacementType.RANDOM
    def __init__(self):
        self._entity = None; self._rd = None; self._wr = None; self._cs = None
        self._render_prog = None; self._vao = None; self._w = 32; self._h = 32
        self._d = 32; self._timer = 0.0; self._paused = False; self._step_count = 0
    def _get_ctx(self):
        try:
            from core.engine import Engine; eng = Engine.instance()
            if not eng: return None
            vp = eng.viewport
            if vp and hasattr(vp, '_ctx'): return vp._ctx
        except Exception: pass
        return None
    def _randomize(self):
        w, h, d = self._w, self._h, self._d; n = w * h * d; rng = np.random.default_rng()
        x, y, z = np.meshgrid(np.arange(w), np.arange(h), np.arange(d), indexing='ij')
        cx, cy, cz = w // 2, h // 2, d // 2; dx, dy, dz = x - cx, y - cy, z - cz
        dist2 = dx*dx + dy*dy + dz*dz; r = min(w, h, d) // 4; p = self.placement
        if p == PlacementType.RANDOM: mask = rng.random((w, h, d)) < 0.2
        elif p == PlacementType.DENSE: mask = rng.random((w, h, d)) < 0.4
        elif p == PlacementType.SPARSE: mask = rng.random((w, h, d)) < 0.08
        elif p == PlacementType.CENTER: mask = (dist2 <= r*r) & (rng.random((w, h, d)) < 0.6)
        elif p == PlacementType.LAYERS: mask = ((z % 2 == 0) & (rng.random((w, h, d)) < 0.5)) | ((z % 2 != 0) & (rng.random((w, h, d)) < 0.05))
        elif p == PlacementType.CHECKER: mask = (x + y + z) % 2 == 0
        elif p == PlacementType.CROSS: mask = ((x == cx) & (y == cy)) | ((y == cy) & (z == cz)) | ((x == cx) & (z == cz))
        elif p == PlacementType.PLANES: mask = (x == cx) | (y == cy) | (z == cz)
        elif p == PlacementType.HOLLOW_SPHERE: mask = (dist2 <= (r+1)**2) & (dist2 >= (r-1)**2)
        elif p == PlacementType.SOLID_CUBE: mask = (np.abs(dx) <= r) & (np.abs(dy) <= r) & (np.abs(dz) <= r)
        elif p == PlacementType.DIAGONALS: mask = (np.abs(dx) == np.abs(dy)) & (np.abs(dy) == np.abs(dz))
        elif p == PlacementType.TORUS:
            rt, rb = r * 1.5, r * 0.5; dxz = np.sqrt(dx**2 + dz**2)
            mask = ((dxz - rt)**2 + dy**2) <= rb**2
        elif p == PlacementType.HELIX:
            mask = np.zeros((w, h, d), dtype=bool)
            for z_idx in range(d):
                angle = z_idx * 0.3
                for rx, ry in [(np.cos(angle), np.sin(angle)), (-np.cos(angle), -np.sin(angle))]:
                    hx, hy = int(cx + r*rx), int(cy + r*ry)
                    for ddx in range(-1, 2):
                        for ddy in range(-1, 2):
                            if 0 <= hx+ddx < w and 0 <= hy+ddy < h: mask[hx+ddx, hy+ddy, z_idx] = True
        elif p == PlacementType.GRID:
            spacing = max(2, min(w, h, d) // 8)
            mask = (x % spacing == 0) | (y % spacing == 0) | (z % spacing == 0)
        elif p == PlacementType.CORNERS:
            cr = max(1, r // 2)
            mask = (np.abs(dx) >= w//2 - cr) & (np.abs(dy) >= h//2 - cr) & (np.abs(dz) >= d//2 - cr)
        elif p == PlacementType.EDGES:
            e = 1
            mask = ((np.abs(dx) >= w//2 - e) & (np.abs(dy) >= h//2 - e)) | ((np.abs(dy) >= h//2 - e) & (np.abs(dz) >= d//2 - e)) | ((np.abs(dx) >= w//2 - e) & (np.abs(dz) >= d//2 - e))
        else: mask = rng.random((w, h, d)) < 0.2
        init = mask.astype(np.uint32).flatten()
        self._rd.write(init.tobytes()); self._wr.write(b'\x00' * (n * 4)); self._step_count = 0
    def _clear(self):
        n = self._w * self._h * self._d; z = b'\x00' * (n * 4)
        self._rd.write(z); self._wr.write(z); self._step_count = 0
    def on_start(self):
        ctx = self._get_ctx()
        if not ctx: Logger.error("GoL3D: нет контекста OpenGL"); return
        self._w = max(1, self.grid_width); self._h = max(1, self.grid_height)
        self._d = max(1, self.grid_depth); self._timer = 0.0
        self._paused = False; self._step_count = 0
        cs = ComputeShader.load_from_file(ctx, self.compute_shader_path)
        if not cs: Logger.error(f"GoL3D: {self.compute_shader_path} не загрузился"); self._cs = None; return
        self._cs = cs
        self._rd = ctx.buffer(b'\x00' * (self._w * self._h * self._d * 4))
        self._wr = ctx.buffer(b'\x00' * (self._w * self._h * self._d * 4))
        self._randomize()
        self._render_prog = ctx.program(vertex_shader=_VERT_SRC, fragment_shader=_FRAG_SRC)
        self._vao = ctx.vertex_array(self._render_prog, [])
        n = self._w * self._h * self._d; buf = np.frombuffer(self._rd.read(), dtype=np.uint32)
        alive = int((buf & 1).sum())
        Logger.info(f"GoL3D: {self._w}x{self._h}x{self._d} grid ({n} cells), alive={alive}")
        Logger.info("SPACE=pause R=randomize C=clear +/-=speed")
    def on_update(self, dt: float):
        if not self._cs: return
        if Input.GetKeyDown(KeyCode.SPACE):
            self._paused = not self._paused
            Logger.info(f"GoL3D: {'PAUSED' if self._paused else 'RUNNING'}")
        if Input.GetKeyDown(KeyCode.R): self._randomize()
        if Input.GetKeyDown(KeyCode.C): self._clear()
        if Input.GetKeyDown(KeyCode.EQUAL):
            self.update_interval = max(0.02, self.update_interval - 0.02)
            Logger.info(f"GoL3D: speed {self.update_interval:.2f}s")
        if Input.GetKeyDown(KeyCode.MINUS):
            self.update_interval = min(1.0, self.update_interval + 0.02)
            Logger.info(f"GoL3D: speed {self.update_interval:.2f}s")
    def gizmo_meshes(self):
        if not self._cs or not self._vao: return []
        ctx = self._get_ctx()
        if not ctx: return []
        ctx.enable(moderngl.DEPTH_TEST); ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        ctx.disable(moderngl.CULL_FACE)
        if not self._paused:
            self._timer += 0.016
            if self.update_interval > 0.0 and self._timer >= self.update_interval:
                self._timer -= self.update_interval; self._step()
        ctx.memory_barrier(moderngl.SHADER_STORAGE_BARRIER_BIT)
        self._rd.bind_to_storage_buffer(2)
        try:
            from core.engine import Engine; eng = Engine.instance()
            vp = eng.viewport; cam = vp.camera
            fw, fh = vp._get_physical_dims(); aspect = fw / max(1, fh)
            view = cam.get_view_matrix(); proj = cam.get_projection_matrix(aspect); mvp = view * proj
        except Exception: mvp = Mat4()
        rp = self._render_prog
        rp["u_mvp"].write(mvp.to_f32().tobytes()); rp["u_width"] = self._w
        rp["u_height"] = self._h; rp["u_cell_size"] = self.cell_spacing
        rp["u_cell_scale"] = max(0.01, self.cell_scale); rp["u_alpha"] = max(0.0, min(1.0, self.cell_alpha))
        total = self._w * self._h * self._d
        self._vao.render(moderngl.TRIANGLES, vertices=36, instances=total)
        ctx.disable(moderngl.BLEND)
        return []
    def _step(self):
        prog = self._cs._program; w, h, d = self._w, self._h, self._d
        prog["u_width"] = w; prog["u_height"] = h; prog["u_depth"] = d
        bmin, bmax, smin, smax = _RULES.get(self.rule, (4, 4, 1, 6))
        prog["u_birth_min"] = bmin; prog["u_birth_max"] = bmax
        prog["u_survive_min"] = smin; prog["u_survive_max"] = smax
        self._rd.bind_to_storage_buffer(0); self._wr.bind_to_storage_buffer(1)
        total = w * h * d; groups = (total + 255) // 256; prog.run(groups, 1, 1)
        self._rd, self._wr = self._wr, self._rd; self._step_count += 1
        if self._step_count <= 3 or self._step_count % 30 == 0:
            buf = np.frombuffer(self._rd.read(), dtype=np.uint32); alive = int((buf & 1).sum())
            Logger.info(f"GoL3D: step={self._step_count} alive={alive}/{total}")
    def on_destroy(self):
        for buf in (self._rd, self._wr):
            if buf: buf.release()
        if self._vao: self._vao.release()
        if self._render_prog: self._render_prog.release()
        if self._cs: self._cs.release()
        self._rd = None; self._wr = None; self._vao = None
        self._render_prog = None; self._cs = None