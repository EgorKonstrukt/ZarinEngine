# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QLabel, QMdiArea, QMdiSubWindow
from PySide6.QtCore import Qt
from core.gui.wid import get_widget_base_style, get_widget_type_for_object, get_widget_extra_rules
from .component import _BaseWidgetCore

if TYPE_CHECKING:
    from core.ecs import Entity


class GuiWidgetComponentBase(_BaseWidgetCore):
    def on_destroy(self):
        if self._sub_window_ref:
            sw = self._sub_window_ref
            self._sub_window_ref = None
            try:
                mdi = sw.mdiArea()
                if mdi:
                    mdi.removeSubWindow(sw)
                sw.setWidget(None)
                sw.deleteLater()
            except RuntimeError:
                pass
        if self._widget_ref:
            canvas = getattr(self._widget_ref, '_canvas_ref', None)
            if canvas:
                canvas.remove_widget(self._widget_ref)
            else:
                self._widget_ref.setParent(None)
                self._widget_ref.deleteLater()
            self._widget_ref = None

    def _get_parent_widget(self, canvas) -> Optional[QWidget]:
        if not self.entity or not self.entity.parent:
            return canvas.root if canvas else None
        pe = self.entity.parent
        comp = _find_gui_comp_from_entity(pe)
        if comp and comp._widget_ref:
            return comp._widget_ref
        return canvas.root if canvas else None

    def _get_local_offset(self) -> tuple[float, float]:
        if not self.entity or not self.entity.parent:
            return 0.0, 0.0
        pe = self.entity.parent
        pcomp = _find_gui_comp_from_entity(pe)
        if pcomp and pcomp._widget_ref:
            return float(pcomp._widget_ref.x()), float(pcomp._widget_ref.y())
        return 0.0, 0.0

    def _apply_style_to_widget(self):
        w = self._widget_ref
        if not w:
            return
        obj_name = self._widget_obj_name
        qtype = get_widget_type_for_object(obj_name)
        selector = f"{qtype}#{obj_name}"
        base = get_widget_base_style(obj_name)
        parts = [base] if base else []
        bg = self._rgb_to_hex(self._bg_color) if self._bg_color else None
        tc = self._rgb_to_hex(self._text_color) if self._text_color else None
        bc = self._rgb_to_hex(self._border_color) if self._border_color else None
        if bg:
            parts.append(f"background-color: {bg}")
        if tc:
            parts.append(f"color: {tc}")
        if bc:
            parts.append(f"border: {int(self._border_width)}px solid {bc}")
            if self._border_radius > 0:
                parts.append(f"border-radius: {int(self._border_radius)}px")
        if self._font_size != 14:
            parts.append(f"font-size: {int(self._font_size)}px")
        if self._font_bold:
            parts.append("font-weight: bold")
        if self._opacity < 1.0:
            parts.append(f"opacity: {self._opacity}")
        rules = [f"{selector} {{ {'; '.join(parts)} }}"]
        rules.extend(get_widget_extra_rules(obj_name))
        w.setStyleSheet("\n".join(rules))

    def _create_widget(self, canvas):
        if self._widget_ref:
            return
        cls = self._widget_class
        if not cls:
            return
        t = self.transform
        px = int(t.local_position.x) if t else 50
        py = int(t.local_position.y) if t else 50
        pw = self.widget_width
        ph = self.widget_height
        sx, sy, sw, sh = self._logical_to_screen(px, py, pw, ph)
        parent_w = self._get_parent_widget(canvas)
        if isinstance(parent_w, QMdiArea):
            widget = cls(0, 0, sw, sh)
            sub = QMdiSubWindow(parent_w)
            sub.setWidget(widget)
            widget.setMinimumSize(sw, sh)
            sub.setWindowTitle(self.widget_text)
            sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            parent_w.addSubWindow(sub)
            sub.show()
            cm = sub.contentsMargins()
            sub.setGeometry(sx, sy, sw + cm.left() + cm.right(), sh + cm.top() + cm.bottom())
            self._widget_ref = widget
            self._sub_window_ref = sub
            widget._widget_id = self.entity.id if self.entity else None
            widget._canvas_ref = canvas
            widget._anchor = self._anchor
            sub._widget_id = self.entity.id if self.entity else None
            sub._canvas_ref = canvas
            sub._anchor = self._anchor
            if not self._visible:
                sub.setVisible(False)
            canvas.update()
        else:
            widget = cls(sx, sy, sw, sh, parent=parent_w)
            if hasattr(widget, 'setText'):
                try:
                    widget.setText(self.widget_text)
                except Exception:
                    pass
            if isinstance(widget, QLabel):
                widget.setText(self.widget_text)
            widget._widget_id = self.entity.id if self.entity else None
            widget._canvas_ref = canvas
            widget._anchor = self._anchor
            canvas.add_widget(widget, parent_w)
            if not self._visible:
                widget.setVisible(False)
            self._widget_ref = widget
        self._apply_style_to_widget()
        self.sync_to_widget()
        self._connect_edit_signals()

    def sync_to_widget(self):
        ref = self._widget_ref
        if not ref or not self.entity:
            return
        try:
            _ = ref.parent()
        except RuntimeError:
            self._widget_ref = None
            self._sub_window_ref = None
            return
        cr = getattr(ref, '_canvas_ref', None)
        drag = getattr(cr, '_drag_widget', None) if cr else None
        if drag is ref or drag is self._sub_window_ref:
            return
        t = self.transform
        px = int(t.local_position.x) if t else 50
        py = int(t.local_position.y) if t else 50
        sx, sy, sw, sh = self._logical_to_screen(px, py, self.widget_width, self.widget_height)
        parent_w = self._get_parent_widget(cr)
        needs_sub = isinstance(parent_w, QMdiArea)
        sub = self._sub_window_ref
        if sub:
            try:
                _ = sub.parent()
            except RuntimeError:
                self._sub_window_ref = None
                sub = None
        if needs_sub:
            if not sub:
                sub = QMdiSubWindow(parent_w)
                sub.setWidget(ref)
                ref.setMinimumSize(max(1, int(sw)), max(1, int(sh)))
                sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                self._sub_window_ref = sub
                sub._widget_id = self.entity.id if self.entity else None
                sub._canvas_ref = cr
                sub._anchor = self._anchor
            current_mdi = sub.mdiArea()
            if current_mdi is not parent_w:
                if current_mdi:
                    current_mdi.removeSubWindow(sub)
                parent_w.addSubWindow(sub)
                sub.show()
            sub.setWindowTitle(self.widget_text)
            cm = sub.contentsMargins()
            nw = max(50, sw + cm.left() + cm.right())
            nh = max(30, sh + cm.top() + cm.bottom())
            if (sub.x() != sx or sub.y() != sy or sub.width() != nw or sub.height() != nh):
                sub.setGeometry(sx, sy, nw, nh)
            sub.setVisible(self._visible)
            ref.setVisible(True)
        else:
            if sub:
                old_mdi = sub.mdiArea()
                if old_mdi:
                    old_mdi.removeSubWindow(sub)
                sub.setWidget(None)
                sub.deleteLater()
                self._sub_window_ref = None
            if parent_w and ref.parent() is not parent_w:
                ref.setParent(parent_w)
            if not (ref.parent() and ref.parent().layout()):
                if (ref.x() != sx or ref.y() != sy or ref.width() != sw or ref.height() != sh):
                    ref.setGeometry(sx, sy, sw, sh)
            ref._anchor = self._anchor
            ref.setVisible(self._visible)

    def _connect_edit_signals(self):
        ref = self._widget_ref
        if ref is None:
            return
        for sig_name in ("textChanged", "valueChanged", "currentTextChanged",
                          "currentIndexChanged", "toggled", "stateChanged"):
            sig = getattr(ref, sig_name, None)
            if sig is not None:
                try:
                    sig.connect(lambda *a, r=ref: self._on_widget_edited(r))
                except Exception:
                    pass

    def _on_widget_edited(self, ref):
        if ref is None:
            return
        try:
            self.update_from_widget()
        except Exception:
            pass

    def update_from_widget(self):
        sub = self._sub_window_ref
        if sub:
            try:
                _ = sub.parent()
            except RuntimeError:
                self._sub_window_ref = None
                sub = None
        ref = self._widget_ref
        if not ref:
            return
        try:
            _ = ref.parent()
        except RuntimeError:
            self._widget_ref = None
            self._sub_window_ref = None
            return
        if sub:
            try:
                lx, ly, lw, lh = self._screen_to_logical(
                    sub.x(), sub.y(), float(sub.width()), float(sub.height())
                )
            except RuntimeError:
                lx, ly, lw, lh = 0, 0, 100, 100
            if hasattr(ref, 'text'):
                try:
                    self.widget_text = ref.text()
                except Exception:
                    pass
        else:
            lx, ly, lw, lh = self._screen_to_logical(
                ref.x(), ref.y(), float(ref.width()), float(ref.height())
            )
            if hasattr(ref, 'text'):
                try:
                    self.widget_text = ref.text()
                except Exception:
                    pass
        if self.transform:
            tp = self.transform.local_position
            if abs(tp.x - lx) > 1e-4 or abs(tp.y - ly) > 1e-4:
                self.transform.local_position = (lx, ly, 0)
        if abs(self.widget_width - float(lw)) > 1e-4:
            self.widget_width = float(lw)
        if abs(self.widget_height - float(lh)) > 1e-4:
            self.widget_height = float(lh)
        self._anchor = getattr(ref, '_anchor', 0)
        self._visible = (sub or ref).isVisible()

    @classmethod
    def deserialize(cls, data: dict) -> GuiWidgetComponentBase:
        inst = cls()
        inst.widget_text = data.get("widget_text", cls._default_text)
        inst.widget_width = data.get("widget_width", cls._default_w)
        inst.widget_height = data.get("widget_height", cls._default_h)
        inst._bg_color = data.get("_bg_color")
        inst._text_color = data.get("_text_color")
        inst._border_color = data.get("_border_color")
        inst._border_width = data.get("_border_width", 1.0)
        inst._border_radius = data.get("_border_radius", 4.0)
        inst._font_size = data.get("_font_size", 14.0)
        inst._font_bold = data.get("_font_bold", False)
        inst._opacity = data.get("_opacity", 1.0)
        inst._visible = data.get("_visible", True)
        inst._anchor = data.get("_anchor", 0)
        inst.enabled = data.get("enabled", True)
        return inst


def _find_gui_comp_from_entity(entity: Entity):
    from core.components.gui import _ensure_component_map
    for c in _ensure_component_map().values():
        comp = entity.get_component_by_name(c.__name__)
        if comp:
            return comp
    return None
