# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, re, threading
from PyQt6.QtGui import QFont, QFontMetrics, QMouseEvent, QPainter
from core.config.editor_scale import scale
from .. import doc_provider as docs
from .. import diagnostics as diags
from .. import vision as vis
from .. import blame as blame_mod
class SearchMixin:
    def _schedule_analysis(self):
        try:
            if self._analysis_timer.isActive():
                return
            try:
                bc = self.blockCount()
            except Exception:
                bc = 0
            delay = 350
            if bc > 3000:
                delay = 900
            elif bc > 1000:
                delay = 600
            self._analysis_timer.start(delay)
        except Exception:
            pass
    def _run_analysis(self):
        try:
            self._analysis_version += 1
            ver = self._analysis_version
            try:
                bc = self.blockCount()
            except Exception:
                bc = 0
            if bc > 8000:
                try:
                    self._inspection.set_counts(0, 0)
                except Exception:
                    pass
                return
            text = self.toPlainText()
            path = self._vcs_file_path or ""
            def _work():
                try:
                    errs, warns = diags.analyze_text(text, path)
                    lines = text.splitlines()
                    usages = vis.compute_usages(text, lines)
                    comp = vis.compute_complexity(lines)
                    try:
                        self.analysis_ready.emit(ver, (len(text), hash(text)), errs, warns, usages, comp)
                    except Exception:
                        pass
                except Exception:
                    pass
            threading.Thread(target=_work, daemon=True).start()
        except Exception:
            pass
    def _apply_analysis(self, ver: int, sig, errs, warns, usages, comp):
        try:
            if ver != self._analysis_version:
                return
            if sig is not None and sig == getattr(self, "_analysis_applied_sig", None):
                try:
                    self._inspection.set_counts(len(errs), len(warns))
                except Exception:
                    pass
                return
            try:
                self._analysis_applied_sig = sig
            except Exception:
                pass
            self._diagnostic_errors = errs
            self._diagnostic_warnings = warns
            self._vision_usages = usages
            self._vision_complexity = comp
            try:
                self._inspection.set_counts(len(errs), len(warns))
            except Exception:
                pass
            try:
                self.diagnostics_changed.emit(len(errs), len(warns))
            except Exception:
                pass
            try:
                lines = self.toPlainText().splitlines()
                self._ensure_import_fold(lines)
                try:
                    fold: set = set()
                    cls: set = set()
                    dfn: set = set()
                    for idx, ln in enumerate(lines):
                        if len(ln) < 4:
                            continue
                        s = ln.strip()
                        if s.startswith("class "):
                            fold.add(idx)
                            cls.add(idx)
                        elif s.startswith("def "):
                            fold.add(idx)
                            dfn.add(idx)
                        elif s.startswith("import ") or s.startswith("from ") or s.startswith("try:"):
                            fold.add(idx)
                        if len(fold) > 4000:
                            break
                    self._foldable_set = fold
                    self._class_lines = cls
                    self._def_lines = dfn
                except Exception:
                    pass
            except Exception:
                pass
            self._rebuild_diag_selections()
            self._update_current_line_only()
            try:
                self.viewport().update()
                self._line_number.update()
                self._minimap_cache = None
                self._minimap.update()
            except Exception:
                pass
        except Exception:
            pass
    def _draw_code_vision(self, event, painter=None):
        if not self._vision_usages and not self._vision_complexity:
            return
        own = False
        if painter is None:
            painter = QPainter(self.viewport())
            own = True
        small_font = QFont(self.font().family(), 9)
        painter.setFont(small_font)
        fm_small = QFontMetrics(small_font)
        fm_main = QFontMetrics(self.font())
        block = self.firstVisibleBlock()
        try:
            vh = self.viewport().height()
            coff = self.contentOffset()
            try:
                lh = self._cached_line_height()
            except Exception:
                lh = fm_main.height()
            try:
                y0 = int(self.blockBoundingGeometry(block).translated(coff).top())
            except Exception:
                y0 = 0
            asc_main = fm_main.ascent()
            asc_small = fm_small.ascent()
            space_w = fm_main.horizontalAdvance(" ")
            vidx = 0
            mark = chr(11377)
            mark_w = fm_small.horizontalAdvance(mark + " ")
            while block.isValid():
                if not block.isVisible():
                    block = block.next()
                    continue
                top = y0 + vidx * lh
                vidx += 1
                if top > vh:
                    break
                if top + lh < 0:
                    block = block.next()
                    continue
                ln = block.blockNumber()
                has_u = ln in self._vision_usages
                has_c = ln in self._vision_complexity
                if not has_u and not has_c:
                    block = block.next()
                    continue
                txt = block.text()
                stripped = txt.strip()
                if has_u:
                    usages = self._vision_usages[ln]
                    if len(txt) > 300:
                        base_w = space_w * 60.0
                    else:
                        base_w = fm_main.horizontalAdvance(txt)
                    x_u = int(coff.x() + base_w + scale(14))
                    painter.setPen(self._pen_lens)
                    painter.drawText(x_u, top + asc_main, usages)
                    blame = self._vcs_blame_data.get(ln)
                    if blame and blame.get("author"):
                        x_a = x_u + fm_small.horizontalAdvance(usages) + scale(14)
                        painter.setPen(self._pen_lens)
                        painter.drawText(x_a, top + asc_main, mark + " " + str(blame.get("author", ""))[:40])
                    if stripped.startswith("class "):
                        painter.setPen(self._pen_lens_blue)
                        painter.drawText(scale(2), top + asc_main, chr(9424))
                if has_c:
                    comp = self._vision_complexity[ln]
                    indent = len(txt) - len(txt.lstrip())
                    x_ind = int(coff.x() + space_w * indent)
                    painter.setPen(self._pen_lens_green)
                    painter.drawText(x_ind, top + asc_small, mark)
                    painter.setPen(self._pen_lens)
                    painter.drawText(x_ind + mark_w, top + asc_small, comp)
                block = block.next()
        except Exception:
            pass
        if own:
            painter.end()
    def line_number_mouse_move(self, event: QMouseEvent, area):
        try:
            y = int(event.position().y())
            block = self._find_block_at_y(y)
            if block is not None:
                line = block.blockNumber()
                diags_here: list[str] = []
                try:
                    cached = self._diag_map.get(line, [])
                except Exception:
                    cached = []
                for d in cached:
                    try:
                        diags_here.append(str(d.kind) + ": " + str(d.message))
                    except Exception:
                        continue
                if line in self._vcs_blame_data:
                    info = self._vcs_blame_data[line]
                    tip_parts: list[str] = []
                    if diags_here:
                        tip_parts.extend(diags_here)
                    author = info.get("author", "")
                    when = info.get("time_str", "")
                    msg = info.get("message", "")
                    if author or when or msg:
                        tip_parts.append(str(author) + "  " + str(when) + "  " + str(msg))
                    self.setToolTip(chr(10).join(tip_parts))
                else:
                    if diags_here:
                        self.setToolTip(chr(10).join(diags_here))
                    else:
                        self.setToolTip("")
            area.update()
        except Exception:
            pass
    def line_number_mouse_press(self, event: QMouseEvent, area):
        try:
            y = int(event.position().y())
            if event.position().x() > area.width() - scale(16):
                block = self._find_block_at_y(y)
                if block is not None:
                    self._toggle_fold(block.blockNumber())
                    event.accept()
                    return
        except Exception:
            pass
    def line_number_mouse_leave(self, event):
        self.setToolTip("")
    def _find_block_at_y(self, y: int):
        block = self.firstVisibleBlock()
        while block.isValid():
            if not block.isVisible():
                block = block.next()
                continue
            geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
            top = int(geom.top())
            bottom = top + int(self.blockBoundingRect(block).height())
            if top <= y <= bottom:
                return block
            if top > y:
                return None
            block = block.next()
        return None
    def minimap_pressed(self, y: int):
        self._minimap_scroll_to(y)
    def minimap_dragged(self, y: int):
        self._minimap_scroll_to(y)
    def _minimap_scroll_to(self, y: int):
        vsb = self.verticalScrollBar()
        if vsb is None:
            return
        total = vsb.maximum() + vsb.pageStep()
        if total <= 0:
            return
        mh = max(1, self._minimap.height())
        ratio = max(0.0, min(1.0, y / mh))
        target = int(ratio * total - vsb.pageStep() * 0.5)
        vsb.setValue(max(0, min(vsb.maximum(), target)))
    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        try:
            tc = self.cursorForPosition(event.pos())
            if tc.isNull():
                return
            blk = tc.block()
            txt = blk.text()
            off = tc.positionInBlock()
            word = docs.word_at(txt, off)
            if word and docs.is_doc_trigger(word):
                self.setToolTip("Press Ctrl+Q for documentation")
            else:
                lst = self._diag_map.get(blk.blockNumber(), [])
                if lst:
                    msgs: list[str] = []
                    for d in lst[:4]:
                        try:
                            msgs.append(str(d.kind) + ": " + str(d.message))
                        except Exception:
                            continue
                    self.setToolTip(chr(10).join(msgs))
                else:
                    self.setToolTip("")
        except Exception:
            pass
    def vcs_set_git(self, git):
        self._vcs_git = git
    def vcs_set_file(self, path: str):
        self._vcs_file_path = path
        self.vcs_refresh()
    def vcs_refresh(self):
        self._vcs_blame_data = {}
        self._vcs_diff_data = {}
        self._vcs_status = ""
        self._vcs_branch = ""
        if self._vcs_git is None:
            self._update_extra()
            return
        try:
            if not self._vcs_git.available or not self._vcs_git.repo_root:
                self._update_extra()
                return
        except Exception:
            self._update_extra()
            return
        if not self._vcs_file_path:
            self._update_extra()
            return
        try:
            rel = os.path.relpath(self._vcs_file_path, self._vcs_git.repo_root)
        except ValueError:
            self._update_extra()
            return
        rel = rel.replace("\\", "/")
        if self._vcs_refreshing:
            self._vcs_pending = True
            return
        self._vcs_refreshing = True
        threading.Thread(
            target=self._vcs_worker,
            args=(self._vcs_git, rel, self._vcs_file_path, self._show_blame),
            daemon=True,
        ).start()
    def _vcs_worker(self, git, rel: str, file_path: str, show_blame: bool):
        result: dict = {"branch": "", "status": "", "diff_data": {}, "blame_data": {}}
        try:
            result["branch"] = git.current_branch()
            rc, out, _ = git.status()
            if rc == 0:
                for entry in out.strip().split("\n"):
                    entry = entry.rstrip()
                    if not entry or len(entry) < 3:
                        continue
                    xy = entry[:2]
                    path = entry[3:]
                    if path == rel:
                        if xy[0] == "?" and xy[1] == "?":
                            result["status"] = "untracked"
                        elif xy[0] == "M" or xy[1] == "M" or xy[0] == "A":
                            result["status"] = "modified"
                        elif xy[0] == "D" or xy[1] == "D":
                            result["status"] = "deleted"
                        elif xy[0] == "U" or xy[1] == "U":
                            result["status"] = "conflict"
                        break
            diff_text = git.file_diff(rel)
            if diff_text:
                current = None
                for line in diff_text.split("\n"):
                    if line.startswith("@@ "):
                        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                        if m:
                            current = int(m.group(1))
                    elif line.startswith("+"):
                        if current is not None:
                            result["diff_data"][current - 1] = "added"
                        current = (current or 0) + 1
                    elif line.startswith("-"):
                        pass
                    elif line.startswith(" "):
                        if current is not None:
                            current += 1
            if show_blame:
                try:
                    if "GIT_AUTHOR_NAME" not in os.environ:
                        os.environ["GIT_AUTHOR_NAME"] = ""
                    if "GIT_COMMITTER_NAME" not in os.environ:
                        os.environ["GIT_COMMITTER_NAME"] = ""
                    blame_text = git.blame(file_path)
                    parsed = blame_mod.parse_blame_output(blame_text if blame_text else "")
                    parsed = blame_mod.enrich_with_log(parsed, git)
                    result["blame_data"] = parsed
                except Exception:
                    result["blame_data"] = {}
        except Exception:
            pass
        try:
            self._vcs_result_ready.emit(result)
        except Exception:
            try:
                self.vcs_result_ready.emit(result)
            except Exception:
                pass
    def _on_vcs_result(self, result: dict):
        self._vcs_refreshing = False
        try:
            self._vcs_branch = result.get("branch", "")
            self._vcs_status = result.get("status", "")
            self._vcs_diff_data = result.get("diff_data", {})
            self._vcs_blame_data = result.get("blame_data", {})
            self._update_extra()
            self._line_number.update()
            self._blame_gutter.update()
            self.viewport().update()
        except RuntimeError:
            pass
        if self._vcs_pending:
            self._vcs_pending = False
            self.vcs_refresh()
    def vcs_set_blame_visible(self, visible: bool):
        self._show_blame = visible
        self.vcs_refresh()
        self._update_extra()
        self._blame_gutter.update()
        self.viewport().update()
    def vcs_is_blame_visible(self) -> bool:
        return self._show_blame
    def vcs_branch(self) -> str:
        return self._vcs_branch
    def vcs_file_status(self) -> str:
        return self._vcs_status
