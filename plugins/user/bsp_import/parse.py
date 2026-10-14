# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import struct
import numpy as np
BSP_LUMP_VERTICES = 3
BSP_LUMP_TEXINFO = 6
BSP_LUMP_FACES = 7
BSP_LUMP_EDGES = 12
BSP_LUMP_SURFEDGES = 13
BSP_LUMP_TEXDATA = 2
BSP_LUMP_TEXDATA_STRING_DATA = 43
BSP_LUMP_TEXDATA_STRING_TABLE = 44
_FACE_FMT = struct.Struct('<HBBiHHhHi')
_LUMP_DIR_FMT = struct.Struct('<IIII')
class BSPFile:
    def __init__(self, path: str):
        self.path = path
        self.version = 0
        self.lumps: dict[int, tuple[int, int]] = {}
        self.vertices: list[tuple[float, float, float]] = []
        self.edges: list[tuple[int, int]] = []
        self.surfedges: list[int] = []
        self.faces: list[dict] = []
        self.texinfo: list[dict] = []
        self.texdata: list[dict] = []
        self.texdata_string_data: bytes = b''
        self.texdata_string_table: list[int] = []
        self._parse()
    def _read_lump(self, data: bytes, lump_id: int) -> bytes:
        lump = self.lumps.get(lump_id)
        if not lump:
            return b''
        off, length = lump
        return data[off:off + length]
    def _parse(self):
        with open(self.path, 'rb') as f:
            data = f.read()
        if len(data) < 8 or data[:4] != b'VBSP':
            raise ValueError(f"Not a valid BSP file: {self.path}")
        self.version = struct.unpack_from('<I', data, 4)[0]
        for i in range(64):
            off = 8 + i * 16
            offset, length, ver, fourcc = _LUMP_DIR_FMT.unpack_from(data, off)
            self.lumps[i] = (offset, length)
        raw = self._read_lump(data, BSP_LUMP_VERTICES)
        self.vertices = [struct.unpack_from('<fff', raw, i * 12) for i in range(len(raw) // 12)]
        raw = self._read_lump(data, BSP_LUMP_EDGES)
        raw_len = len(raw)
        n_vert = len(self.vertices) if self.vertices else 0
        if self.version >= 20 and raw_len >= 8:
            n8 = raw_len // 8
            good_8 = 0
            for i in range(min(200, n8)):
                v0, v1 = struct.unpack_from('<ii', raw, i * 8)
                if 0 <= v0 < n_vert and 0 <= v1 < n_vert:
                    good_8 += 1
            if good_8 >= min(200, n8) * 0.75:
                self.edges = [struct.unpack_from('<ii', raw, i * 8) for i in range(n8)]
            else:
                self.edges = [struct.unpack_from('<HH', raw, i * 4) for i in range(raw_len // 4)]
        else:
            self.edges = [struct.unpack_from('<HH', raw, i * 4) for i in range(raw_len // 4)]
        raw = self._read_lump(data, BSP_LUMP_SURFEDGES)
        self.surfedges = [struct.unpack_from('<i', raw, i * 4)[0] for i in range(len(raw) // 4)]
        raw = self._read_lump(data, BSP_LUMP_FACES)
        for i in range(len(raw) // 20):
            planenum, side, onnode, firstedge, numedges, texinfo, dispinfo, surfaceflags, smoothgroups = \
                _FACE_FMT.unpack_from(raw, i * 20)
            self.faces.append(dict(planenum=planenum, side=side, onnode=onnode,
                                   firstedge=firstedge, numedges=numedges,
                                   texinfo=texinfo, dispinfo=dispinfo,
                                   surfaceflags=surfaceflags, smoothgroups=smoothgroups))
        raw = self._read_lump(data, BSP_LUMP_TEXINFO)
        self.texinfo = []
        for i in range(len(raw) // 72):
            p = i * 72
            tv0 = struct.unpack_from('<4f', raw, p)
            tv1 = struct.unpack_from('<4f', raw, p + 16)
            flags, td_idx = struct.unpack_from('<ii', raw, p + 64)
            self.texinfo.append(dict(textureVecs=(tv0, tv1), flags=flags, texdata=td_idx))
        raw = self._read_lump(data, BSP_LUMP_TEXDATA)
        self.texdata = []
        for i in range(len(raw) // 32):
            p = i * 32
            name_id, w, h, vw, vh = struct.unpack_from('<iiiii', raw, p + 12)
            self.texdata.append(dict(nameStringTableID=name_id, width=w, height=h,
                                     view_width=vw, view_height=vh))
        self.texdata_string_data = self._read_lump(data, BSP_LUMP_TEXDATA_STRING_DATA)
        raw = self._read_lump(data, BSP_LUMP_TEXDATA_STRING_TABLE)
        self.texdata_string_table = [struct.unpack_from('<i', raw, i * 4)[0] for i in range(len(raw) // 4)]
    def get_texture_name(self, texdata_index: int) -> str:
        if texdata_index < 0 or texdata_index >= len(self.texdata):
            return "unknown"
        td = self.texdata[texdata_index]
        name_id = td['nameStringTableID']
        if name_id < 0 or name_id >= len(self.texdata_string_table):
            return f"tex_{texdata_index}"
        offset = self.texdata_string_table[name_id]
        if offset >= len(self.texdata_string_data):
            return f"tex_{texdata_index}"
        end = self.texdata_string_data.find(b'\0', offset)
        if end < 0:
            end = len(self.texdata_string_data)
        name = self.texdata_string_data[offset:end].decode('ascii', errors='replace')
        clean = name.replace('/', '_').replace('\\', '_').replace('.', '_')
        clean = ''.join(c for c in clean if c.isalnum() or c == '_')
        return clean if clean else f"tex_{texdata_index}"
    def extract_mesh_groups(self, settings: dict, progress=None) -> list[dict]:
        convert_coords = settings.get('convert_coords', True)
        scale = settings.get('scale', 1.0)
        merge_by_material = settings.get('merge_by_material', True)
        center_pivot = settings.get('center_pivot', False)
        total = len(self.faces)
        if progress:
            progress(15, f"Processing {total} faces...")
        texdata_len = len(self.texdata)
        texinfo_len = len(self.texinfo)
        surfedges_len = len(self.surfedges)
        edges_len = len(self.edges)
        vertices_len = len(self.vertices)
        cached_tex_name = {}
        face_infos = []
        report_interval = max(1, total // 50)
        for fi, face in enumerate(self.faces):
            if fi % report_interval == 0 and progress:
                pct = 15 + int((fi / total) * 30)
                progress(pct, f"Reading faces: {fi}/{total}")
            if face['dispinfo'] >= 0:
                face_infos.append(None)
                continue
            ti_idx = face['texinfo']
            if ti_idx < 0 or ti_idx >= texinfo_len:
                face_infos.append(None)
                continue
            td_idx = self.texinfo[ti_idx]['texdata']
            if td_idx in cached_tex_name:
                tex_name = cached_tex_name[td_idx]
            elif td_idx < texdata_len:
                tex_name = self.get_texture_name(td_idx)
                cached_tex_name[td_idx] = tex_name
            else:
                tex_name = f"tex_{td_idx}"
                cached_tex_name[td_idx] = tex_name
            firstedge = face['firstedge']
            numedges = face['numedges']
            vi_list = []
            for i in range(numedges):
                se_idx = firstedge + i
                if se_idx < surfedges_len:
                    se = self.surfedges[se_idx]
                    edge_idx = abs(se)
                    if edge_idx < edges_len:
                        edge = self.edges[edge_idx]
                        vi = edge[1] if se >= 0 else edge[0]
                        if vi < vertices_len:
                            vi_list.append(vi)
            if len(vi_list) < 3:
                face_infos.append(None)
                continue
            verts = [self.vertices[vi] for vi in vi_list]
            if convert_coords:
                verts_zp = [(v[0] * scale, v[2] * scale, -v[1] * scale) for v in verts]
            else:
                verts_zp = [(v[0] * scale, v[1] * scale, v[2] * scale) for v in verts]
            ti = self.texinfo[ti_idx]
            s_vec = ti['textureVecs'][0]
            t_vec = ti['textureVecs'][1]
            uvs = [(v[0] * s_vec[0] + v[1] * s_vec[1] + v[2] * s_vec[2] + s_vec[3],
                    v[0] * t_vec[0] + v[1] * t_vec[1] + v[2] * t_vec[2] + t_vec[3])
                   for v in verts]
            face_infos.append(dict(tex_name=tex_name, verts=verts_zp, uvs=uvs))
        if progress:
            progress(48, "Grouping by material...")
        if merge_by_material:
            groups: dict[str, list] = {}
            for fd in face_infos:
                if fd is None:
                    continue
                name = fd['tex_name']
                if name not in groups:
                    groups[name] = []
                groups[name].append(fd)
        else:
            groups = {}
            for fi, fd in enumerate(face_infos):
                if fd is None:
                    continue
                name = f"{fd['tex_name']}_face{fi}"
                groups[name] = [fd]
        if progress:
            progress(52, f"Building {len(groups)} mesh groups...")
        result = []
        group_items = list(groups.items())
        for gi, (tex_name, face_list) in enumerate(group_items):
            if progress:
                pct = 52 + int((gi / len(group_items)) * 8)
                progress(pct, f"Building: {tex_name}")
            all_verts = []
            all_uvs = []
            all_indices = []
            base = 0
            for fd in face_list:
                n = len(fd['verts'])
                for i in range(1, n - 1):
                    all_indices.append(base)
                    all_indices.append(base + i + 1)
                    all_indices.append(base + i)
                all_verts.extend(fd['verts'])
                all_uvs.extend(fd['uvs'])
                base += n
            if len(all_verts) < 3 or len(all_indices) < 3:
                continue
            verts_arr = np.array(all_verts, dtype=np.float32)
            uvs_arr = np.array(all_uvs, dtype=np.float32)
            idx_arr = np.array(all_indices, dtype=np.uint32)
            n_verts = len(verts_arr)
            n_idx = len(idx_arr)
            normals = np.zeros((n_verts, 3), dtype=np.float32)
            for i in range(0, n_idx, 3):
                i0, i1, i2 = idx_arr[i], idx_arr[i + 1], idx_arr[i + 2]
                v0, v1, v2 = verts_arr[i0], verts_arr[i1], verts_arr[i2]
                e1 = v1 - v0
                e2 = v2 - v0
                n = np.cross(e1, e2)
                nl = np.linalg.norm(n)
                if nl > 1e-10:
                    n = n / nl
                normals[i0] += n
                normals[i1] += n
                normals[i2] += n
            nl = np.linalg.norm(normals, axis=1, keepdims=True)
            nl[nl < 1e-10] = 1.0
            normals = normals / nl
            aabb_min = verts_arr.min(axis=0)
            aabb_max = verts_arr.max(axis=0)
            centroid = verts_arr.mean(axis=0)
            if center_pivot:
                verts_arr = verts_arr - centroid
            result.append(dict(
                name=tex_name,
                vertices=verts_arr,
                uvs=uvs_arr,
                normals=normals,
                indices=idx_arr,
                aabb_min=aabb_min,
                aabb_max=aabb_max,
                centroid=centroid,
            ))
        return result
