# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt, QSettings
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPen

from .flame import compute_tick_metrics, draw_frame_chart, draw_spike_box, draw_tick_chart
from .stats import _fmt_bytes, _fmt_count, _fmt_vram_mb, _short_gpu


_STATS_FONT = QFont("Consolas", 9)
_STATS_FONT.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
_STATS_FM_CACHE: tuple = (None, None)
_RAM_CACHE = (0.0, 0.0)
_stats_adv_cache: dict = {}
_LAST_STATS_TEXT = ""
_COLLAPSED: set | None = None
_LAST_STATS_GEOM: dict = {"headers": [], "panel": (0, 0, 0, 0)}


VALUE_COLORS = {
    "FPS": QColor(100, 220, 100),
    "Avg": QColor(140, 230, 140),
    "1%": QColor(255, 200, 100),
    "0.1%": QColor(255, 150, 100),
    "Min": QColor(255, 120, 120),
    "CPU": QColor(100, 200, 255),
    "GPU": QColor(100, 200, 255),
    "Render": QColor(100, 200, 255),
    "Gizmos": QColor(160, 220, 255),
    "Overlay": QColor(190, 230, 255),
    "Paint": QColor(210, 210, 210),
    "RAM": QColor(180, 255, 180),
    "VRAM": QColor(255, 180, 255),
    "GC": QColor(180, 180, 255),
    "TPS": QColor(180, 255, 180),
    "TPS1": QColor(255, 200, 100),
    "TPS01": QColor(255, 150, 100),
    "TS": QColor(180, 255, 180),
    "DSP": QColor(255, 255, 180),
    "Sounds": QColor(180, 255, 255),
    "Entities": QColor(255, 180, 180),
    "Draw": QColor(200, 200, 200),
    "Tris": QColor(200, 220, 255),
    "Verts": QColor(200, 220, 255),
    "Fill": QColor(200, 255, 220),
    "Cull": QColor(255, 200, 150),
    "Batches": QColor(200, 200, 200),
    "Inst": QColor(200, 200, 200),
    "Particles": QColor(255, 220, 180),
    "Draws": QColor(200, 220, 255),
    "Lines": QColor(200, 220, 255),
    "Mesh": QColor(200, 220, 255),
    "Upload": QColor(255, 255, 150),
    "Full": QColor(255, 180, 180),
    "Part": QColor(180, 255, 180),
    "Res": QColor(180, 200, 255),
    "GL": QColor(200, 200, 200),
    "MRays": QColor(255, 200, 100),
    "Opq": QColor(180, 255, 200),
    "Trn": QColor(180, 220, 255),
    "MeshQ": QColor(255, 255, 150),
    "Comp": QColor(255, 200, 200),
    "Bodies": QColor(150, 255, 200),
    "Fixed": QColor(150, 200, 255),
    "Pt": QColor(255, 220, 150),
    "Spot": QColor(255, 220, 150),
    "Casc": QColor(255, 200, 150),
    "ShRes": QColor(255, 200, 150),
    "Hot": QColor(255, 220, 150),
    "Net": QColor(150, 220, 255),
    "PostFX": QColor(220, 180, 255),
    "Cache": QColor(200, 200, 200),
    "DPR": QColor(180, 200, 255),
    "RS": QColor(180, 200, 255),
}


def _collapsed_sections() -> set:
    global _COLLAPSED
    if _COLLAPSED is None:
        _COLLAPSED = set()
        try:
            raw = QSettings("Zarin", "Editor").value("stats/collapsed", [])
            if isinstance(raw, (list, tuple)):
                _COLLAPSED = set(str(s) for s in raw)
            elif isinstance(raw, str) and raw:
                _COLLAPSED = {raw}
        except Exception:
            pass
    return _COLLAPSED


def toggle_stats_section(header: str) -> None:
    try:
        s = _collapsed_sections()
        if header in s:
            s.discard(header)
        else:
            s.add(header)
        try:
            QSettings("Zarin", "Editor").setValue("stats/collapsed", sorted(s))
        except Exception:
            pass
    except Exception:
        pass


def stats_header_at(px: int, py: int):
    try:
        for hdr, x0, y0, x1, y1 in _LAST_STATS_GEOM.get("headers", []):
            if x0 <= px <= x1 and y0 <= py <= y1:
                return hdr
    except Exception:
        pass
    return None


def stats_text() -> str:
    return _LAST_STATS_TEXT


def _health_key(value: float, good_key: str, warn_key: str) -> str:
    try:
        v = float(value)
    except Exception:
        return good_key
    if v >= 50.0:
        return good_key
    if v >= 25.0:
        return warn_key
    return "Min"


def build_stats_rows(m: dict, st: dict, timings: dict) -> list:
    for _k, _v in (('opaque_draws', 0), ('trans_draws', 0), ('mesh_pending', 0),
                   ('mesh_built', 0), ('shadow_pt', 0), ('shadow_spot', 0),
                   ('shadow_casc', 0), ('shadow_res', 0), ('shadow_dist', 0.0),
                   ('bodies', 0), ('fixed_steps', 0), ('fixed_accum_ms', 0.0),
                   ('postfx', 0), ('shader_progs', 0), ('cached_tex', 0),
                   ('components', 0), ('render_scale', 1.0)):
        st.setdefault(_k, _v)
    cull_total = st['culled_total']
    cull_str = f"{st['culled_visible']}/{cull_total}"
    if cull_total > 0:
        cull_str += f" ({100.0 * st['culled_visible'] / cull_total:.0f}%)"
    fill_mpx = 0.0
    try:
        _res = str(timings.get('res', ''))
        if 'x' in _res:
            _rw, _rh = _res.lower().split('x')
            fill_mpx = float(_rw) * float(_rh) * m['fps'] / 1e6
    except Exception:
        fill_mpx = 0.0
    tri_mts = st['triangles'] * m['fps'] / 1e6
    tm = compute_tick_metrics(st.get('tick_dts'))
    frame_kvs = [
        ("FPS", f"{m['fps']:.1f}", _health_key(m['fps'], "FPS", "1%")),
        ("1%", f"{m['p1_fps']:.1f}", "1%"),
        ("0.1%", f"{m['p01_fps']:.1f}", "0.1%"),
        ("Min", f"{m['min_fps']:.1f}", "Min"),
        ("CPU", f"{timings['cpu_ms']:.1f}ms", "CPU"),
        ("GPU", f"{timings['render_ms']:.1f}ms", "GPU"),
    ]
    if st['rt_rays_per_frame'] > 0:
        rt_mrays = st['rt_rays_per_frame'] * m['fps'] / 1e6
        frame_kvs.append(("MRays", f"{rt_mrays:.1f}MR/s", "MRays"))
    rows: list = [
        ("h", "Frame"),
        ("kv", frame_kvs),
        ("h", "Timing"),
        ("kv", [
            ("Render", f"{timings['render_ms']:.2f}ms", "Render"),
            ("Gizmos", f"{timings['gizmo_ms']:.2f}ms", "Gizmos"),
            ("Overlay", f"{timings['overlay_ms']:.2f}ms", "Overlay"),
            ("Paint", f"{timings['paint_ms']:.2f}ms", "Paint"),
        ]),
        ("h", "Scene"),
        ("kv", [
            ("Draw", f"{st['draw_calls']}", "Draw"),
            ("Opq", f"{st['opaque_draws']}", "Opq"),
            ("Trn", f"{st['trans_draws']}", "Trn"),
            ("Tris", f"{_fmt_count(st['triangles'])}", "Tris"),
            ("Verts", f"{_fmt_count(st['vertices'])}", "Verts"),
            ("Fill", f"{fill_mpx:.0f}MP/s", "Fill"),
            ("Tris/s", f"{tri_mts:.0f}MT/s", "Tris"),
            ("Cull", cull_str, "Cull"),
        ]),
        ("h", "Batches"),
        ("kv", [
            ("Batches", f"{st['batches']}", "Batches"),
            ("Inst", f"{_fmt_count(st['instanced'])}", "Inst"),
            ("Particles", f"{_fmt_count(st['particles'])}", "Particles"),
            ("MeshQ", f"{st['mesh_pending']}/{st['mesh_built']}", "MeshQ"),
        ]),
        ("h", "Shadows"),
        ("kv", [
            ("Pt", f"{st['shadow_pt']}", "Pt"),
            ("Spot", f"{st['shadow_spot']}", "Spot"),
            ("Casc", f"{st['shadow_casc']}", "Casc"),
            ("Res", f"{st['shadow_res']}", "ShRes"),
            ("Dist", f"{st['shadow_dist']:.0f}", "ShRes"),
        ]),
        ("h", "Sim"),
        ("kv", [
            ("Bodies", f"{st['bodies']}", "Bodies"),
            ("Fixed", f"{st['fixed_steps']}st/{st['fixed_accum_ms']:.0f}ms", "Fixed"),
            ("PostFX", f"{st['postfx']}", "PostFX"),
        ]),
        ("h", "Memory"),
        ("kv", [
            ("RAM", f"{st['ram_mb']:.0f}MB", "RAM"),
            ("VRAM", f"{_fmt_vram_mb(st['vram_used'])}/{_fmt_vram_mb(st['vram_total'])}", "VRAM"),
            ("GC", f"{st['gc0']}/{st['gc1']}/{st['gc2']}", "GC"),
            ("Shaders", f"{st['shader_progs']}", "Cache"),
            ("Tex", f"{st['cached_tex']}", "Cache"),
        ]),
        ("h", "Gizmo"),
        ("kv", [
            ("Draws", f"{st['gizmo_draws']}", "Draws"),
            ("Lines", f"{_fmt_count(st['gizmo_lines'])}", "Lines"),
            ("Inst", f"{_fmt_count(st['gizmo_instances'])}", "Inst"),
            ("Mesh", f"{_fmt_count(st['gizmo_mesh_verts'])}", "Mesh"),
            ("Upload", f"{_fmt_bytes(st['gizmo_upload_bytes'])}", "Upload"),
            ("Full", f"{st['gizmo_upload_full']}", "Full"),
            ("Part", f"{st['gizmo_upload_partial']}", "Part"),
        ]),
        ("h", "Engine"),
        ("kv", [
            ("TPS", f"{st['tps']:.0f}", _health_key(st['tps'], "TPS", "TPS1")),
            ("1%", f"{tm['tps_p1']:.0f}", "TPS1"),
            ("0.1%", f"{tm['tps_p01']:.0f}", "TPS01"),
            ("TS", f"{st['time_scale']:.2f}", "TS"),
            ("Entities", f"{st['entities']}", "Entities"),
            ("Comp", f"{st['components']}", "Comp"),
            ("DSP", f"{st['dsp_load']:.0f}%", "DSP"),
            ("Sounds", f"{st['active_sounds']}/{st['total_sounds']}", "Sounds"),
        ]),
        ("h", "Device"),
        ("kv", [
            ("GPU", _short_gpu(st['gl_renderer']), "GPU"),
            ("GL", st['gl_version'].split()[0] if st['gl_version'] else "?", "GL"),
            ("Res", timings['res'], "Res"),
            ("DPR", f"{float(timings.get('dpr', 1.0) or 1.0):.2f}", "DPR"),
            ("RS", f"{st['render_scale']:.2f}", "RS"),
        ]),
    ]
    hot = st.get('hot') or []
    if hot:
        rows.append(("h", "Hot"))
        rows.append(("kv", [(name, f"{ms:.2f}ms", "Hot") for name, ms in hot[:3]]))
    net = st.get('net')
    if net:
        rows.append(("h", "Net"))
        rows.append(("kv", [
            ("Role", "Host" if net.get('host') else "Client", "Net"),
            ("Peers", f"{net.get('peers', 0)}", "Net"),
            ("Ping", f"{net.get('ping', 0.0):.0f}ms", "Net"),
        ]))
    try:
        lines = []
        cur_hdr = ""
        for row in rows:
            if row[0] == "h":
                cur_hdr = row[1]
            else:
                lines.append(cur_hdr + ": " + " | ".join(f"{lab}: {val}" for lab, val, _ in row[1]))
        global _LAST_STATS_TEXT
        _LAST_STATS_TEXT = "\n".join(lines)
    except Exception:
        pass
    return rows


def draw_stats_panel(painter, rows: list, frame_times_ms, spike_log: list, tick_times_ms=None):
    fnt = painter.font()
    if fnt.family() != _STATS_FONT.family() or fnt.pointSize() != _STATS_FONT.pointSize():
        painter.setFont(_STATS_FONT)
    fm = QFontMetrics(_STATS_FONT)
    adv_cache = _stats_adv_cache
    def adv(text: str) -> int:
        hit = adv_cache.get(text)
        if hit is None:
            hit = fm.horizontalAdvance(text)
            if len(adv_cache) > 2048:
                adv_cache.clear()
            adv_cache[text] = hit
        return hit
    padding = 6
    line_h = 15
    sections = []
    cur = None
    for row in rows:
        if row[0] == "h":
            cur = [row[1], []]
            sections.append(cur)
        else:
            if cur is not None:
                cur[1].extend(row[1])
    view_w = painter.device().width()
    wrap_at = max(360, min(view_w - 16 - padding * 2, 880))
    cont_indent = 16
    collapsed = _collapsed_sections()
    vlines: list = []
    for hdr, kvs in sections:
        if hdr in collapsed:
            vlines.append((hdr, []))
            continue
        hw = adv(hdr + ": ")
        cur_line: list = []
        cur_w = hw
        first = True
        for lab, val, key in kvs:
            w = adv(lab + ": ") + adv(val) + (adv(" | ") if cur_line else 0)
            if cur_line and cur_w + w > wrap_at:
                vlines.append((hdr if first else None, cur_line))
                first = False
                cur_line = []
                cur_w = 0
                w = adv(lab + ": ") + adv(val)
            cur_line.append((lab, val, key))
            cur_w += w
        if cur_line:
            vlines.append((hdr if first else None, cur_line))
    max_w = padding * 2
    for hdr, kvs in vlines:
        if not kvs:
            w = adv(hdr + ": [+]")
        else:
            w = 0 if hdr is None else adv(hdr + ": ")
            if hdr is None:
                w = cont_indent
            for li, (_lab, _val, _key) in enumerate(kvs):
                w += adv(_lab + ": ") + adv(_val)
                if li < len(kvs) - 1:
                    w += adv(" | ")
        max_w = max(max_w, w + padding * 2)
    max_w = max(max_w, 480)
    if max_w > view_w - 16:
        max_w = max(view_w - 16, 120)
    x = 8
    y = 35
    total_h = len(vlines) * line_h + padding * 2
    view_h = painter.device().height()
    show_chart = True
    show_tick = bool(tick_times_ms)
    show_spike = bool(spike_log)
    while (y + total_h + (36 if show_chart else 0) + (28 if show_tick else 0) + (72 if show_spike else 0)) > view_h:
        if show_spike:
            show_spike = False
        elif show_tick:
            show_tick = False
        elif show_chart:
            show_chart = False
        else:
            break
    bg = QColor(0, 0, 0, 160)
    border = QColor(80, 80, 80, 200)
    rect = QRect(x, y, int(max_w), total_h)
    painter.fillRect(rect, bg)
    painter.setPen(QPen(border, 1))
    painter.drawRect(rect)
    label_color = QColor(160, 160, 160)
    header_color = QColor(120, 180, 255)
    text_color = QColor(255, 255, 255)
    for i, (hdr, kvs) in enumerate(vlines):
        cy = y + padding + i * line_h
        cx = x + padding
        if hdr is not None:
            hs = hdr + ": "
            painter.setPen(header_color)
            painter.drawText(QRect(cx, cy, adv(hs), line_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, hs)
            cx += adv(hs)
            if not kvs:
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(QRect(cx, cy, adv("[+]"), line_h),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "[+]")
        else:
            cx += cont_indent
        for ki, (lab, val, key) in enumerate(kvs):
            lab_s = lab + ": "
            painter.setPen(label_color)
            painter.drawText(QRect(cx, cy, adv(lab_s), line_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lab_s)
            cx += adv(lab_s)
            painter.setPen(VALUE_COLORS.get(key, text_color))
            painter.drawText(QRect(cx, cy, adv(val), line_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, val)
            cx += adv(val)
            if ki < len(kvs) - 1:
                painter.setPen(QColor(100, 100, 100))
                sep = " | "
                painter.drawText(QRect(cx, cy, adv(sep), line_h),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sep)
                cx += adv(sep)
        nxt = vlines[i + 1][0] if i + 1 < len(vlines) else None
        if nxt is not None:
            painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
            painter.drawLine(x + padding, cy + line_h - 3, int(x + max_w - padding), cy + line_h - 3)
    try:
        _LAST_STATS_GEOM["headers"] = [
            (hdr, x + padding, cy0, int(x + max_w - padding), cy0 + line_h)
            for j, (hdr, _k) in enumerate(vlines) if hdr is not None
            for cy0 in (y + padding + j * line_h,)
        ]
        _LAST_STATS_GEOM["panel"] = (x, y, int(max_w), total_h)
    except Exception:
        pass
    if show_chart:
        chart_bottom = draw_frame_chart(painter, frame_times_ms, x, y + total_h + 6, int(max_w))
        if show_tick:
            chart_bottom = draw_tick_chart(painter, tick_times_ms, x, chart_bottom + 6, int(max_w))
        if show_spike:
            draw_spike_box(painter, spike_log[-1], x, chart_bottom + 6, int(max_w))
