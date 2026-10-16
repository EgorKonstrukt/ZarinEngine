# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Signal
from .shaders import _collect_shaders
from .dialog_ui import _DialogUiMixin
from .dialog_tex import _DialogTexturesMixin
from .dialog_out import _DialogOutputMixin


class MaterialWizardDialog(QDialog, _DialogUiMixin, _DialogTexturesMixin, _DialogOutputMixin):
    materials_created = Signal(list)

    def __init__(self, project_root: str = "", parent=None, submesh_names: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Material Wizard")
        self.setMinimumSize(700, 620)
        self.resize(780, 680)
        self._project_root = project_root or os.getcwd()
        self._shader_data: list[tuple[str, str]] = _collect_shaders(self._project_root)
        self._assignments: dict[str, str] = {}
        self._submesh_names: list[str] = list(submesh_names) if submesh_names else []
        self._setup_ui()
        self._populate_shaders()
        self._refresh_preview()
