# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ctypes
import ctypes.wintypes as wt
from ctypes import (POINTER, byref, c_void_p, c_uint, c_int, c_ulong, c_wchar,
                    c_ubyte, c_ushort, c_int64, Structure, WINFUNCTYPE, cast)
shell32 = ctypes.windll.shell32
ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
class GUID(Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort),
                ("Data4", c_ubyte * 8)]
class WNDCLASSEX(Structure):
    _fields_ = [
        ("cbSize", c_uint),
        ("style", c_uint),
        ("lpfnWndProc", c_void_p),
        ("cbClsExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", c_void_p),
        ("hIcon", c_void_p),
        ("hCursor", c_void_p),
        ("hbrBackground", c_void_p),
        ("lpszMenuName", c_void_p),
        ("lpszClassName", c_void_p),
        ("hIconSm", c_void_p),
    ]
ole32.IIDFromString.argtypes = [wt.LPCWSTR, POINTER(GUID)]
ole32.IIDFromString.restype = c_int
ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
ole32.CoInitializeEx.restype = c_int
ole32.OleInitialize.argtypes = [c_void_p]
ole32.OleInitialize.restype = c_int
ole32.CoUninitialize.argtypes = []
ole32.CoUninitialize.restype = None
shell32.SHParseDisplayName.argtypes = [wt.LPCWSTR, c_void_p, POINTER(c_void_p), wt.ULONG, POINTER(wt.ULONG)]
shell32.SHParseDisplayName.restype = c_int
shell32.SHGetDesktopFolder.argtypes = [POINTER(c_void_p)]
shell32.SHGetDesktopFolder.restype = c_int
shell32.SHBindToParent.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p), POINTER(c_void_p)]
shell32.SHBindToParent.restype = c_int
shell32.ILFree.argtypes = [c_void_p]
shell32.ILFree.restype = None
user32.CreatePopupMenu.restype = wt.HMENU
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.DestroyMenu.restype = c_int
user32.AppendMenuW.argtypes = [wt.HMENU, c_uint, c_uint, wt.LPCWSTR]
user32.AppendMenuW.restype = c_int
user32.GetMenuItemCount.argtypes = [wt.HMENU]
user32.GetMenuItemCount.restype = c_int
user32.GetMenuStringW.argtypes = [wt.HMENU, c_int, wt.LPCWSTR, c_int, c_uint]
user32.GetMenuStringW.restype = c_int
user32.TrackPopupMenuEx.argtypes = [wt.HMENU, c_uint, c_int, c_int, wt.HWND, c_void_p]
user32.TrackPopupMenuEx.restype = c_uint
user32.RegisterClassExW.argtypes = [POINTER(WNDCLASSEX)]
user32.RegisterClassExW.restype = c_ushort
user32.CreateWindowExW.argtypes = [c_uint, c_void_p, wt.LPCWSTR, c_uint,
                                   c_int, c_int, c_int, c_int, c_void_p, c_void_p, c_void_p, c_void_p]
user32.CreateWindowExW.restype = wt.HWND
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = c_int
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE
user32.DefWindowProcW.argtypes = [c_void_p, c_uint, c_void_p, c_void_p]
user32.DefWindowProcW.restype = c_int64
COINIT_APARTMENTTHREADED = 0x2
CMF_NORMAL = 0x0
CMF_EXPLORE = 0x4
CMIC_MASK_UNICODE = 0x4000
SW_NORMAL = 1
TPM_RETURNCMD = 0x100
TPM_RIGHTBUTTON = 0x2
WM_INITMENUPOPUP = 0x117
WM_MEASUREITEM = 0x2C
WM_DRAWITEM = 0x2B
WM_MENUCHAR = 0x120
MF_STRING = 0x0
MF_SEPARATOR = 0x800
MF_ENABLED = 0x0
WS_POPUP = 0x80000000
S_OK = 0
def _iid_from_string(text: str) -> GUID:
    g = GUID()
    ole32.IIDFromString(ctypes.create_unicode_buffer(text), byref(g))
    return g
IID_IShellFolder = _iid_from_string("{000214E6-0000-0000-C000-000000000046}")
IID_IContextMenu = _iid_from_string("{000214E4-0000-0000-C000-000000000046}")
IID_IContextMenu2 = _iid_from_string("{000214F4-0000-0000-C000-000000000046}")
IID_IContextMenu3 = _iid_from_string("{000214F1-0000-0000-C000-000000000046}")
class CMINVOKECOMMANDINFOEX(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("fMask", wt.DWORD),
        ("hwnd", wt.HWND),
        ("lpVerb", wt.LPCWSTR),
        ("lpParameters", wt.LPCWSTR),
        ("lpDirectory", wt.LPCWSTR),
        ("nShow", c_int),
        ("dwHotKey", wt.DWORD),
        ("hIcon", wt.HANDLE),
        ("lpTitle", wt.LPCWSTR),
        ("lpVerbW", wt.LPCWSTR),
        ("lpParametersW", wt.LPCWSTR),
        ("lpDirectoryW", wt.LPCWSTR),
        ("lpTitleW", wt.LPCWSTR),
        ("ptInvoke", wt.POINT),
    ]
def _vt_call(pv, index, restype, argtypes, *args):
    obj = cast(pv, POINTER(c_void_p))
    vtbl = cast(obj[0], POINTER(c_void_p))
    fptr = vtbl[index]
    proto = WINFUNCTYPE(restype, *([c_void_p] + list(argtypes)))
    func = cast(fptr, proto)
    return func(pv, *args)
def _query_interface(pv, iid) -> c_void_p | None:
    out = c_void_p()
    hr = _vt_call(pv, 0, c_int, [POINTER(type(iid)), POINTER(c_void_p)],
                  byref(iid), byref(out))
    if hr < 0 or not out:
        return None
    return out
_com_initialized = False
def _ensure_com():
    global _com_initialized
    if _com_initialized:
        return
    try:
        ole32.OleInitialize(None)
    except Exception:
        try:
            ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        except Exception:
            pass
    _com_initialized = True
def _release(pv):
    try:
        if pv:
            _vt_call(pv, 2, c_int, [], )
    except Exception:
        pass
