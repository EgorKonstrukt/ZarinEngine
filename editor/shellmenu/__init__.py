# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from .interop import (CMF_EXPLORE, CMF_NORMAL, CMIC_MASK_UNICODE, CMINVOKECOMMANDINFOEX,
                      COINIT_APARTMENTTHREADED, GUID, IID_IContextMenu, IID_IContextMenu2,
                      IID_IContextMenu3, IID_IShellFolder, MF_ENABLED, MF_SEPARATOR, MF_STRING,
                      SW_NORMAL, S_OK, TPM_RETURNCMD, TPM_RIGHTBUTTON, WNDCLASSEX, WM_DRAWITEM,
                      WM_INITMENUPOPUP, WM_MEASUREITEM, WM_MENUCHAR, WS_POPUP, _com_initialized,
                      _ensure_com, _iid_from_string, _query_interface, _release, _vt_call,
                      kernel32, ole32, shell32, user32)
from .menu import (_CTX_BY_HWND, _OWNER_CLASS, _apply_menu_theme, _class_registered,
                   _create_owner_window, _ensure_owner_class, _hinstance, _owner_class_name_buf,
                   _owner_wnd_proc, _owner_wnd_proc_ref, _show_impl, _system_uses_light_theme,
                   _uxtheme_ordinal, show_shell_context_menu)
__all__ = ["CMF_EXPLORE", "CMF_NORMAL", "CMIC_MASK_UNICODE", "CMINVOKECOMMANDINFOEX",
           "COINIT_APARTMENTTHREADED", "GUID", "IID_IContextMenu", "IID_IContextMenu2",
           "IID_IContextMenu3", "IID_IShellFolder", "MF_ENABLED", "MF_SEPARATOR", "MF_STRING",
           "SW_NORMAL", "S_OK", "TPM_RETURNCMD", "TPM_RIGHTBUTTON", "WNDCLASSEX", "WM_DRAWITEM",
           "WM_INITMENUPOPUP", "WM_MEASUREITEM", "WM_MENUCHAR", "WS_POPUP", "_CTX_BY_HWND",
           "_OWNER_CLASS", "_apply_menu_theme", "_class_registered", "_com_initialized",
           "_create_owner_window", "_ensure_com", "_ensure_owner_class", "_hinstance",
           "_iid_from_string", "_owner_class_name_buf", "_owner_wnd_proc", "_owner_wnd_proc_ref",
           "_query_interface", "_release", "_show_impl", "_system_uses_light_theme",
           "_uxtheme_ordinal", "_vt_call", "kernel32", "ole32", "shell32",
           "show_shell_context_menu", "user32"]
