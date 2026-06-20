from __future__ import annotations
from typing import Optional, TYPE_CHECKING
import json
import math
import os
import numpy as np
from core.math3d import Vec3
from core.components.physics.mesh_collider import CollisionMode
from core.engine import Engine

if TYPE_CHECKING:
    from core.ecs import Entity


_mesh_data: dict[str, dict] = {}
_decimated_hull_cache: dict[tuple[str, int], Optional[list]] = {}
_decimated_hull_cache_np: dict[tuple[str, int], Optional[np.ndarray]] = {}
_wire_cache: dict[str, tuple[list, str]] = {}
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "../.."))


def _resolve_mesh_path(path: str) -> Optional[str]:
    if not path:
        return None
    if os.path.exists(path):
        return path
    if os.path.isabs(path):
        eng = Engine.instance()
        root = eng.project_root if eng else _PROJECT_ROOT
        if path[1:2] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return path if os.path.exists(path) else None
    resolved = os.path.normpath(os.path.join(_PROJECT_ROOT, path))
    if os.path.exists(resolved):
        return resolved
    return None


def _load_mesh_data(path: str) -> Optional[dict]:
    resolved = _resolve_mesh_path(path)
    if not resolved:
        return None
    cache_key = resolved.lower()
    if cache_key in _mesh_data:
        return _mesh_data[cache_key]

    from editor.renderer.mesh_loader import MeshLoader
    if cache_key in MeshLoader._shared_import_cache:
        data = MeshLoader._shared_import_cache[cache_key]
    else:
        try:
            from core.asset_importer import load_mesh_future
            fut = load_mesh_future(resolved)
            data = fut.result(timeout=0.01)
        except Exception:
            return None

    scale = 1.0
    import_path = resolved + ".import"
    if os.path.exists(import_path):
        try:
            with open(import_path) as f:
                settings = json.load(f)
            scale = settings.get("scale", 1.0)
        except Exception:
            pass

    if data is None or len(data.vertices) == 0:
        _mesh_data[cache_key] = {"verts": np.empty((0, 3), dtype=np.float32), "edges": [], "num_verts": 0}
        return _mesh_data[cache_key]

    verts = data.vertices.reshape(-1, 3)
    if scale != 1.0:
        verts = verts * scale

    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    center = verts.mean(axis=0)
    radius = float(np.max(np.linalg.norm(verts - center, axis=1)))

    if len(data.indices) == 0:
        result = {
            "verts": verts, "edges": [], "edge_verts_np": np.empty((0, 2, 3), dtype=np.float32),
            "mins": mins, "maxs": maxs,
            "num_verts": len(verts),
            "center": center, "radius": radius,
        }
        _mesh_data[cache_key] = result
        return result

    idxs = data.indices
    edges_set: set[tuple[int, int]] = set()
    for i in range(0, len(idxs), 3):
        if i + 2 >= len(idxs):
            break
        a, b, c = int(idxs[i]), int(idxs[i + 1]), int(idxs[i + 2])
        for ia, ib in ((a, b), (b, c), (c, a)):
            if ia < ib:
                edges_set.add((ia, ib))
            else:
                edges_set.add((ib, ia))

    edges: list[tuple[Vec3, Vec3]] = []
    edge_indices = np.array(list(edges_set), dtype=np.int32)
    edge_verts_np = verts[edge_indices]
    for ia, ib in edges_set:
        r0 = verts[ia]
        r1 = verts[ib]
        edges.append((Vec3(float(r0[0]), float(r0[1]), float(r0[2])),
                      Vec3(float(r1[0]), float(r1[1]), float(r1[2]))))

    result = {
        "verts": verts, "edges": edges, "edge_verts_np": edge_verts_np,
        "mins": mins, "maxs": maxs,
        "num_verts": len(verts),
        "center": center, "radius": radius,
    }
    _mesh_data[cache_key] = result
    return result


def _decimate_verts(verts: np.ndarray, max_vertices: int) -> np.ndarray:
    n = len(verts)
    if n <= max_vertices or max_vertices < 1:
        return verts
    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extent = maxs - mins
    extent = np.where(extent < 1e-8, 1.0, extent)
    target_cell_vol = extent.prod() / max_vertices
    cell_size = target_cell_vol ** (1.0 / 3.0)
    grid_res = np.maximum(1, np.ceil(extent / cell_size).astype(np.int32))
    indices = np.floor((verts - mins) / extent * grid_res).astype(np.int32)
    indices = np.clip(indices, 0, grid_res - 1)
    cell_ids = indices[:, 0] * grid_res[1] * grid_res[2] + indices[:, 1] * grid_res[2] + indices[:, 2]
    unique_ids, inverse = np.unique(cell_ids, return_inverse=True)
    centroids = np.zeros((len(unique_ids), 3), dtype=np.float32)
    np.add.at(centroids, inverse, verts)
    counts = np.bincount(inverse, minlength=len(unique_ids)).astype(np.float32)
    centroids /= counts[:, None]
    return centroids


def _compute_hull_edges_from_verts(verts: np.ndarray) -> Optional[list]:
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(verts)
        edges_set: set[tuple[int, int]] = set()
        for simplex in hull.simplices:
            a, b, c = int(simplex[0]), int(simplex[1]), int(simplex[2])
            for ia, ib in ((a, b), (b, c), (c, a)):
                edges_set.add((ia, ib) if ia < ib else (ib, ia))
        edges: list[tuple[Vec3, Vec3]] = []
        for ia, ib in edges_set:
            r0 = verts[ia]
            r1 = verts[ib]
            edges.append((Vec3(float(r0[0]), float(r0[1]), float(r0[2])),
                          Vec3(float(r1[0]), float(r1[1]), float(r1[2]))))
        return edges
    except Exception:
        return None


def _compute_hull_edges_np(verts: np.ndarray) -> Optional[np.ndarray]:
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(verts)
        edges_set: set[tuple[int, int]] = set()
        for simplex in hull.simplices:
            a, b, c = int(simplex[0]), int(simplex[1]), int(simplex[2])
            for ia, ib in ((a, b), (b, c), (c, a)):
                edges_set.add((ia, ib) if ia < ib else (ib, ia))
        if not edges_set:
            return None
        edge_indices = np.array(list(edges_set), dtype=np.int32)
        return verts[edge_indices]
    except Exception:
        return None


_convex_hull_cache: dict[str, Optional[list]] = {}
_convex_hull_cache_np: dict[str, Optional[np.ndarray]] = {}


def _get_convex_hull_edges(path: str) -> Optional[list]:
    cache_key = path.lower().replace("\\", "/")
    if cache_key in _convex_hull_cache:
        return _convex_hull_cache[cache_key]
    md = _load_mesh_data(path)
    if md is None or md["num_verts"] == 0:
        return None
    result = _compute_hull_edges_from_verts(md["verts"])
    _convex_hull_cache[cache_key] = result
    return result


def _get_convex_hull_edges_np(path: str) -> Optional[np.ndarray]:
    cache_key = path.lower().replace("\\", "/")
    if cache_key in _convex_hull_cache_np:
        return _convex_hull_cache_np[cache_key]
    md = _load_mesh_data(path)
    if md is None or md["num_verts"] == 0:
        return None
    result = _compute_hull_edges_np(md["verts"])
    _convex_hull_cache_np[cache_key] = result
    return result


def _get_decimated_hull_edges(path: str, max_verts: int) -> Optional[list]:
    cache_key = (path.lower().replace("\\", "/"), max_verts)
    if cache_key in _decimated_hull_cache:
        return _decimated_hull_cache[cache_key]
    try:
        md = _load_mesh_data(path)
        if md is None or md["num_verts"] == 0:
            return None
        verts = md["verts"]
        if len(verts) <= max_verts:
            return None
        dv = _decimate_verts(verts, max_verts)
        if len(dv) < 3:
            _decimated_hull_cache[cache_key] = None
            return None
        result = _compute_hull_edges_from_verts(dv)
        _decimated_hull_cache[cache_key] = result
        return result
    except Exception:
        _decimated_hull_cache[cache_key] = None
        return None


def _get_decimated_hull_edges_np(path: str, max_verts: int) -> Optional[np.ndarray]:
    cache_key = (path.lower().replace("\\", "/"), max_verts)
    if cache_key in _decimated_hull_cache_np:
        return _decimated_hull_cache_np[cache_key]
    try:
        md = _load_mesh_data(path)
        if md is None or md["num_verts"] == 0:
            return None
        verts = md["verts"]
        if len(verts) <= max_verts:
            return None
        dv = _decimate_verts(verts, max_verts)
        if len(dv) < 3:
            _decimated_hull_cache_np[cache_key] = None
            return None
        result = _compute_hull_edges_np(dv)
        _decimated_hull_cache_np[cache_key] = result
        return result
    except Exception:
        _decimated_hull_cache_np[cache_key] = None
        return None


def get_collider_wireframe_lines(
    entity: Entity,
    color: list[float] | None = None,
) -> list[tuple[Vec3, Vec3, list[float]]]:
    """Generate green wireframe lines for collider components on an entity.

    Returns list of (start, end, [r,g,b,a]) tuples suitable for
    Renderer.render_gizmo_lines().
    """
    if color is None:
        color = [0.0, 1.0, 0.0, 0.6]

    tr = entity.get_component_by_name("Transform")
    if not tr:
        return []

    pos = tr.local_position
    rot = tr.local_rotation
    sc = tr.local_scale

    cache_key = f"wire_{entity.id}"
    tr_key = f"{pos.x:.4f},{pos.y:.4f},{pos.z:.4f},{rot.x:.4f},{rot.y:.4f},{rot.z:.4f},{sc.x:.4f},{sc.y:.4f},{sc.z:.4f}"
    cached = _wire_cache.get(cache_key)
    if cached is not None and cached[1] == tr_key:
        return cached[0]

    lines: list[tuple[Vec3, Vec3, list[float]]] = []

    for comp in entity.get_all_components():
        cname = type(comp).__name__

        if cname == "BoxCollider":
            sz = comp.scaled_size
            h = Vec3(sz.x * 0.5, sz.y * 0.5, sz.z * 0.5)
            c = pos + rot.rotate_vec3(comp.scaled_center)
            corners = [
                c + Vec3(-h.x, -h.y, -h.z),
                c + Vec3(h.x, -h.y, -h.z),
                c + Vec3(h.x, h.y, -h.z),
                c + Vec3(-h.x, h.y, -h.z),
                c + Vec3(-h.x, -h.y, h.z),
                c + Vec3(h.x, -h.y, h.z),
                c + Vec3(h.x, h.y, h.z),
                c + Vec3(-h.x, h.y, h.z),
            ]
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            for a, b in edges:
                lines.append((corners[a], corners[b], color))

        elif cname == "SphereCollider":
            radius = comp.scaled_radius
            c = pos + rot.rotate_vec3(comp.scaled_center)
            segments = 24
            # Three axis-aligned rings in local space, then rotated
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:  # X-axis ring (YZ plane)
                        pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                    elif axis_idx == 1:  # Y-axis ring (XZ plane)
                        pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                    else:  # Z-axis ring (XY plane)
                        pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                    pts.append(c + rot.rotate_vec3(pt))
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], color))

        elif cname == "CapsuleCollider":
            radius = comp.scaled_radius
            total_height = comp.scaled_height
            half_h = max(0, total_height * 0.5 - radius)
            c = pos + rot.rotate_vec3(comp.scaled_center)
            # Axis direction based on comp.direction (0=X, 1=Y, 2=Z)
            dir_idx = getattr(comp, "direction", 1)
            axis_vecs = [Vec3.right(), Vec3.up(), Vec3.forward()]
            axis = axis_vecs[dir_idx] if dir_idx < 3 else Vec3.up()
            segments = 20

            # Top and bottom hemisphere centers
            top_center = c + rot.rotate_vec3(axis * half_h)
            bottom_center = c - rot.rotate_vec3(axis * half_h)

            # For each ring axis (3 rings), draw top and bottom hemi-circles
            for ring_axis in range(3):
                if ring_axis == dir_idx:
                    continue  # skip the capsule axis ring
                pts_top = []
                pts_bot = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    # Direction vectors for the ring
                    u = Vec3.right()
                    v = Vec3.forward()
                    if ring_axis == 0:
                        u = Vec3(0, 1, 0)
                        v = Vec3(0, 0, 1)
                    elif ring_axis == 1:
                        u = Vec3(1, 0, 0)
                        v = Vec3(0, 0, 1)
                    ring_pt = (u * math.cos(theta) + v * math.sin(theta)) * radius
                    pts_top.append(top_center + rot.rotate_vec3(ring_pt))
                    pts_bot.append(bottom_center + rot.rotate_vec3(ring_pt))
                for i in range(segments):
                    lines.append((pts_top[i], pts_top[i + 1], color))
                    lines.append((pts_bot[i], pts_bot[i + 1], color))

            # Connect top and bottom with vertical lines
            for i in range(8):
                theta = 2.0 * math.pi * i / 8
                u = Vec3.right()
                v = Vec3.forward()
                if dir_idx == 0:
                    u = Vec3(0, 1, 0)
                    v = Vec3(0, 0, 1)
                elif dir_idx == 1:
                    u = Vec3(1, 0, 0)
                    v = Vec3(0, 0, 1)
                ring_pt = (u * math.cos(theta) + v * math.sin(theta)) * radius
                top_pt = top_center + rot.rotate_vec3(ring_pt)
                bot_pt = bottom_center + rot.rotate_vec3(ring_pt)
                lines.append((top_pt, bot_pt, color))

        elif cname == "BoxCollider2D":
            sz = comp.scaled_size
            off_v2 = comp.scaled_offset
            c = pos + rot.rotate_vec3(Vec3(off_v2.x, off_v2.y, 0.0))
            hx, hy = sz.x * 0.5, sz.y * 0.5
            corners = [
                c + rot.rotate_vec3(Vec3(-hx, -hy, 0.0)),
                c + rot.rotate_vec3(Vec3(hx, -hy, 0.0)),
                c + rot.rotate_vec3(Vec3(hx, hy, 0.0)),
                c + rot.rotate_vec3(Vec3(-hx, hy, 0.0)),
            ]
            for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
                lines.append((corners[a], corners[b], color))

        elif cname == "CircleCollider2D":
            radius = comp.scaled_radius
            off_v2 = comp.scaled_offset
            c = pos + rot.rotate_vec3(Vec3(off_v2.x, off_v2.y, 0.0))
            segments = 24
            pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0.0)
                pts.append(c + rot.rotate_vec3(pt))
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))

        elif cname == "MeshCollider":
            mesh_color = [0.0, 0.8, 0.2, 0.6]
            mesh_path = getattr(comp, "mesh_path", "")
            mode = getattr(comp, "collision_mode", CollisionMode.AUTO)
            max_verts = getattr(comp, "max_vertices", 2000)

            md = _load_mesh_data(mesh_path) if mesh_path else None

            def _to_world(v: Vec3) -> Vec3:
                return pos + rot.rotate_vec3(Vec3(v.x * sc.x, v.y * sc.y, v.z * sc.z))

            if mode == CollisionMode.BOX and md is not None and md["num_verts"] > 0:
                size = md["maxs"] - md["mins"]
                if np.all(size < 100.0):
                    ctr_np = (md["mins"] + md["maxs"]) * 0.5
                    ctr = Vec3(float(ctr_np[0]), float(ctr_np[1]), float(ctr_np[2]))
                    s_vec = Vec3(float(size[0]) * 0.5, float(size[1]) * 0.5, float(size[2]) * 0.5)
                    corners = [
                        _to_world(ctr + Vec3(-s_vec.x, -s_vec.y, -s_vec.z)),
                        _to_world(ctr + Vec3(s_vec.x, -s_vec.y, -s_vec.z)),
                        _to_world(ctr + Vec3(s_vec.x, s_vec.y, -s_vec.z)),
                        _to_world(ctr + Vec3(-s_vec.x, s_vec.y, -s_vec.z)),
                        _to_world(ctr + Vec3(-s_vec.x, -s_vec.y, s_vec.z)),
                        _to_world(ctr + Vec3(s_vec.x, -s_vec.y, s_vec.z)),
                        _to_world(ctr + Vec3(s_vec.x, s_vec.y, s_vec.z)),
                        _to_world(ctr + Vec3(-s_vec.x, s_vec.y, s_vec.z)),
                    ]
                    for a, b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
                        lines.append((corners[a], corners[b], mesh_color))
                    for face in [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]:
                        lines.append((corners[face[0]], corners[face[2]], mesh_color))
                        lines.append((corners[face[1]], corners[face[3]], mesh_color))
                else:
                    c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
                    s = 0.5
                    corners = [
                        c + Vec3(-s, -s, -s), c + Vec3(s, -s, -s), c + Vec3(s, s, -s), c + Vec3(-s, s, -s),
                        c + Vec3(-s, -s, s), c + Vec3(s, -s, s), c + Vec3(s, s, s), c + Vec3(-s, s, s),
                    ]
                    for a, b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
                        lines.append((corners[a], corners[b], mesh_color))

            elif mode == CollisionMode.SPHERE and md is not None and md["num_verts"] > 0:
                c = _to_world(Vec3(float(md["center"][0]), float(md["center"][1]), float(md["center"][2])))
                max_sc = max(sc.x, sc.y, sc.z)
                radius = md["radius"] * max_sc
                segments = 24
                for axis_idx in range(3):
                    pts = []
                    for i in range(segments + 1):
                        theta = 2.0 * math.pi * i / segments
                        if axis_idx == 0:
                            pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                        elif axis_idx == 1:
                            pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                        else:
                            pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                        pts.append(c + rot.rotate_vec3(pt))
                    for i in range(segments):
                        lines.append((pts[i], pts[i + 1], mesh_color))

            elif mode == CollisionMode.CONVEX_HULL and md is not None and md["num_verts"] > 0:
                hull_edges = _get_convex_hull_edges(mesh_path)
                if hull_edges is not None:
                    for v0, v1 in hull_edges:
                        tv0 = _to_world(v0)
                        tv1 = _to_world(v1)
                        lines.append((tv0, tv1, mesh_color))
                elif md["edges"]:
                    for v0, v1 in md["edges"]:
                        tv0 = _to_world(v0)
                        tv1 = _to_world(v1)
                        lines.append((tv0, tv1, mesh_color))

            elif mode == CollisionMode.AUTO and md is not None and md["num_verts"] > 0:
                if md["num_verts"] > max_verts:
                    hull_edges = _get_decimated_hull_edges(mesh_path, max_verts)
                    if hull_edges is not None:
                        for v0, v1 in hull_edges:
                            tv0 = _to_world(v0)
                            tv1 = _to_world(v1)
                            lines.append((tv0, tv1, mesh_color))
                    else:
                        size = md["maxs"] - md["mins"]
                        if np.all(size < 100.0):
                            ctr_np = (md["mins"] + md["maxs"]) * 0.5
                            ctr = Vec3(float(ctr_np[0]), float(ctr_np[1]), float(ctr_np[2]))
                            s_vec = Vec3(float(size[0]) * 0.5, float(size[1]) * 0.5, float(size[2]) * 0.5)
                            corners = [
                                _to_world(ctr + Vec3(-s_vec.x, -s_vec.y, -s_vec.z)),
                                _to_world(ctr + Vec3(s_vec.x, -s_vec.y, -s_vec.z)),
                                _to_world(ctr + Vec3(s_vec.x, s_vec.y, -s_vec.z)),
                                _to_world(ctr + Vec3(-s_vec.x, s_vec.y, -s_vec.z)),
                                _to_world(ctr + Vec3(-s_vec.x, -s_vec.y, s_vec.z)),
                                _to_world(ctr + Vec3(s_vec.x, -s_vec.y, s_vec.z)),
                                _to_world(ctr + Vec3(s_vec.x, s_vec.y, s_vec.z)),
                                _to_world(ctr + Vec3(-s_vec.x, s_vec.y, s_vec.z)),
                            ]
                            for a, b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
                                lines.append((corners[a], corners[b], mesh_color))
                            for face in [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]:
                                lines.append((corners[face[0]], corners[face[2]], mesh_color))
                                lines.append((corners[face[1]], corners[face[3]], mesh_color))
                        else:
                            c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
                            s = 0.5
                            corners = [
                                c + Vec3(-s, -s, -s), c + Vec3(s, -s, -s), c + Vec3(s, s, -s), c + Vec3(-s, s, -s),
                                c + Vec3(-s, -s, s), c + Vec3(s, -s, s), c + Vec3(s, s, s), c + Vec3(-s, s, s),
                            ]
                            for a, b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
                                lines.append((corners[a], corners[b], mesh_color))
                else:
                    for v0, v1 in md["edges"]:
                        tv0 = _to_world(v0)
                        tv1 = _to_world(v1)
                        lines.append((tv0, tv1, mesh_color))

            elif md is not None and md["edges"]:
                for v0, v1 in md["edges"]:
                    tv0 = _to_world(v0)
                    tv1 = _to_world(v1)
                    lines.append((tv0, tv1, mesh_color))

            else:
                c = pos + rot.rotate_vec3(Vec3(0, 0, 0))
                s = 0.5
                corners = [
                    c + Vec3(-s, -s, -s), c + Vec3(s, -s, -s), c + Vec3(s, s, -s), c + Vec3(-s, s, -s),
                    c + Vec3(-s, -s, s), c + Vec3(s, -s, s), c + Vec3(s, s, s), c + Vec3(-s, s, s),
                ]
                for a, b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:
                    lines.append((corners[a], corners[b], mesh_color))

    _wire_cache[cache_key] = (lines, tr_key)
    return lines
