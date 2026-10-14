# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from editor.hover.preview import HoverPreview
from editor.hover.preview import _get_popup
from editor.hover.preview import _hover_delay
from editor.hover.preview import _fmt_size
from editor.hover.preview import _type_name
from editor.hover.preview import _display_path
from editor.hover.preview import _resolve_path
from editor.hover.preview import _candidate_sizes
from editor.hover.preview import _peek_cached
from editor.hover.preview import _PREVIEW_SIZE
from editor.hover.preview import _PREVIEW_SQUARE
from editor.hover.preview import _POPUP_WIDTH
from editor.hover.preview import _SHOW_MS
from editor.hover.preview import _HIDE_MS
from editor.hover.resource import _resource_info
from editor.hover.resource import _resource_preview
from editor.hover.resource import _ResourceHover
from editor.hover.resource import attach_resource_hover
from editor.hover.entity import _entity_info
from editor.hover.entity import _entity_preview
from editor.hover.entity import _EntityHover
from editor.hover.entity import attach_entity_hover
from editor.hover.project import _ProjectHover
from editor.hover.project import attach_project_list_hover
from editor.hover.project import attach_project_tree_hover
__all__ = ["HoverPreview", "attach_resource_hover", "attach_entity_hover", "attach_project_list_hover", "attach_project_tree_hover"]
