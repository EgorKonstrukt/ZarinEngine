# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from .panel import ScriptEditorPanel
from .widget import ScriptEditorWidget, _ScriptEditorWidget
from .tabs import ScriptTab, CloseableTabWidget, _ScriptTab, _CloseableTabWidget
from .editor import CodeEditor, _CodeEditor
from .highlighter import PythonHighlighter
from .diagnostics import analyze_text, Diagnostic
from .doc_provider import get_documentation
from .blame import parse_blame_output, format_label
from .folding import find_import_block
from .vision import compute_usages, compute_complexity

__all__ = [
    "ScriptEditorPanel",
    "ScriptEditorWidget",
    "ScriptTab",
    "CloseableTabWidget",
    "CodeEditor",
    "PythonHighlighter",
    "analyze_text",
    "Diagnostic",
    "get_documentation",
    "parse_blame_output",
    "format_label",
    "find_import_block",
    "compute_usages",
    "compute_complexity",
]

_CodeEditor = CodeEditor
_ScriptTab = ScriptTab
_CloseableTabWidget = CloseableTabWidget
_ScriptEditorWidget = ScriptEditorWidget
_PythonHighlighter = PythonHighlighter
