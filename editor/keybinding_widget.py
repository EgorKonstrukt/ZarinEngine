from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence


_KEY_NAMES = {
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Delete: "Del",
    Qt.Key.Key_Insert: "Ins",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PgUp",
    Qt.Key.Key_PageDown: "PgDown",
    Qt.Key.Key_Up: "\u2191",
    Qt.Key.Key_Down: "\u2193",
    Qt.Key.Key_Left: "\u2190",
    Qt.Key.Key_Right: "\u2192",
    Qt.Key.Key_Shift: "Shift",
    Qt.Key.Key_Control: "Ctrl",
    Qt.Key.Key_Alt: "Alt",
    Qt.Key.Key_Meta: "Meta",
}


def _key_name(key: Qt.Key) -> str:
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    name = QKeySequence(key).toString()
    if name:
        return name
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(ord("A") + (key - Qt.Key.Key_A))
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(ord("0") + (key - Qt.Key.Key_0))
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        return f"F{key - Qt.Key.Key_F1 + 1}"
    return f"Key({int(key)})"


def _mod_prefix(modifiers: Qt.KeyboardModifier) -> str:
    parts = []
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Meta")
    return "+".join(parts) + "+" if parts else ""


def _format_binding(key: Qt.Key, modifiers: Qt.KeyboardModifier) -> str:
    return _mod_prefix(modifiers) + _key_name(key)


class KeybindingWidget(QPushButton):
    bindingChanged = pyqtSignal(str)

    def __init__(self, binding: str = "", parent=None):
        super().__init__(parent)
        self._binding = binding
        self._listening = False
        self._update_text()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(100)
        self.clicked.connect(self._start_listening)

    def _update_text(self):
        if self._listening:
            self.setText("Press a key...")
            self.setStyleSheet(
                "color: #5a9cf5; background: #2a2a2a; border: 1px solid #5a9cf5;"
                " border-radius: 3px; padding: 3px 8px; font-size: 11px;"
            )
        elif self._binding:
            self.setText(self._binding)
            self.setStyleSheet(
                "color: #cccccc; background: #2a2a2a; border: 1px solid #4a4a4a;"
                " border-radius: 3px; padding: 3px 8px; font-size: 11px;"
            )
        else:
            self.setText("None")
            self.setStyleSheet(
                "color: #888888; background: #2a2a2a; border: 1px solid #4a4a4a;"
                " border-radius: 3px; padding: 3px 8px; font-size: 11px;"
            )

    def _start_listening(self):
        self._listening = True
        self.grabKeyboard()
        self._update_text()

    def keyPressEvent(self, event: QKeyEvent):
        if not self._listening:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._listening = False
            self.releaseKeyboard()
            self._update_text()
            event.accept()
            return
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        mods = event.modifiers()
        binding = _format_binding(key, mods)
        self._listening = False
        self.releaseKeyboard()
        self._binding = binding
        self._update_text()
        self.bindingChanged.emit(self._binding)
        event.accept()

    def focusOutEvent(self, event):
        if self._listening:
            self._listening = False
            self.releaseKeyboard()
            self._update_text()

    def set_binding(self, binding: str):
        self._binding = binding
        self._update_text()

    def get_binding(self) -> str:
        return self._binding
