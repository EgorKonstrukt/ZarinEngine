# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
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

_OWNER_CLASS = "ZarinShellMenuOwner"
_owner_class_name_buf = ctypes.create_unicode_buffer(_OWNER_CLASS)
_hinstance = None
_owner_wnd_proc_ref = None
_class_registered = False
_CTX_BY_HWND: dict[int, tuple] = {}


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


def _owner_wnd_proc(hwnd, msg, wparam, lparam):
    try:
        entry = _CTX_BY_HWND.get(int(hwnd) if hwnd else 0)
        if entry is not None and msg in (WM_INITMENUPOPUP, WM_MEASUREITEM, WM_DRAWITEM, WM_MENUCHAR):
            icm2, icm3 = entry
            if icm3:
                res = c_void_p()
                hr = _vt_call(icm3, 7, c_int,
                              [c_uint, c_void_p, c_void_p, POINTER(c_void_p)],
                              msg, wparam, lparam, byref(res))
                if hr == S_OK:
                    return int(res.value) if res.value else 0
            elif icm2:
                hr = _vt_call(icm2, 6, c_int, [c_uint, c_void_p, c_void_p],
                              msg, wparam, lparam)
                if hr == S_OK:
                    return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    except Exception:
        try:
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        except Exception:
            return 0


def _ensure_owner_class() -> bool:
    global _hinstance, _owner_wnd_proc_ref, _class_registered
    if _class_registered:
        return True
    try:
        _hinstance = kernel32.GetModuleHandleW(None)
        proto = WINFUNCTYPE(c_int64, c_void_p, c_uint, c_void_p, c_void_p)
        _owner_wnd_proc_ref = proto(_owner_wnd_proc)
        cls = WNDCLASSEX()
        cls.cbSize = ctypes.sizeof(WNDCLASSEX)
        cls.style = 0
        cls.lpfnWndProc = cast(_owner_wnd_proc_ref, c_void_p)
        cls.cbClsExtra = 0
        cls.cbWndExtra = 0
        cls.hInstance = _hinstance
        cls.hIcon = None
        cls.hCursor = None
        cls.hbrBackground = None
        cls.lpszMenuName = None
        cls.lpszClassName = cast(_owner_class_name_buf, c_void_p)
        cls.hIconSm = None
        atom = user32.RegisterClassExW(byref(cls))
        if not atom:
            err = kernel32.GetLastError() if hasattr(kernel32, "GetLastError") else 0
            if err not in (0, 1410):
                return False
        _class_registered = True
        return True
    except Exception:
        return False


def _create_owner_window():
    try:
        if not _ensure_owner_class():
            return None
        hwnd = user32.CreateWindowExW(0, cast(_owner_class_name_buf, c_void_p),
                                      "", WS_POPUP, 0, 0, 1, 1,
                                      None, None, _hinstance, None)
        return hwnd or None
    except Exception:
        return None


def show_shell_context_menu(paths, hwnd_owner_int, x, y, extra_actions=None):
    try:
        if not paths:
            return False
        dirs = [os.path.dirname(os.path.abspath(p)) for p in paths]
        try:
            parent_dir = os.path.commonpath(dirs)
        except ValueError:
            return False
        if not parent_dir or not os.path.isdir(parent_dir):
            return False
        _ensure_com()
        return bool(_show_impl(paths, int(x), int(y), extra_actions or []))
    except Exception:
        return False


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


def _system_uses_light_theme() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) != 0
    except Exception:
        return False


def _uxtheme_ordinal(index: int):
    try:
        lib = ctypes.windll.uxtheme
        return lib[index]
    except Exception:
        return None


def _apply_menu_theme(owner_hwnd) -> None:
    try:
        light = _system_uses_light_theme()
    except Exception:
        light = False
    try:
        import ctypes as _ct
        uxtheme = _ct.windll.uxtheme
        uxtheme.SetWindowTheme.argtypes = [c_void_p, wt.LPCWSTR, wt.LPCWSTR]
        uxtheme.SetWindowTheme.restype = c_int
        if light:
            try:
                uxtheme.SetWindowTheme(owner_hwnd, "Explorer", None)
            except Exception:
                pass
            allow = _uxtheme_ordinal(133)
            if allow is not None:
                try:
                    allow.argtypes = [c_void_p, c_int]
                    allow.restype = c_int
                    allow(owner_hwnd, 0)
                except Exception:
                    pass
        else:
            allow = _uxtheme_ordinal(133)
            if allow is not None:
                try:
                    allow.argtypes = [c_void_p, c_int]
                    allow.restype = c_int
                    allow(owner_hwnd, 1)
                except Exception:
                    pass
            try:
                uxtheme.SetWindowTheme(owner_hwnd, "DarkMode_Explorer", None)
            except Exception:
                pass
            refresh = _uxtheme_ordinal(104)
            if refresh is not None:
                try:
                    refresh.argtypes = []
                    refresh.restype = None
                    refresh()
                except Exception:
                    pass
        try:
            dwmapi = _ct.windll.dwmapi
            dwmapi.DwmSetWindowAttribute.argtypes = [c_void_p, c_uint, POINTER(c_int), c_uint]
            dwmapi.DwmSetWindowAttribute.restype = c_int
            dwm_value = c_int(0 if light else 1)
            dwmapi.DwmSetWindowAttribute(owner_hwnd, 20, byref(dwm_value),
                                         _ct.sizeof(c_int))
        except Exception:
            pass
    except Exception:
        pass


def _show_impl(paths, x, y, extra_actions):
    owner_hwnd = None
    parent_folder = None
    bound: list = []
    child_pidls: list = []
    hmenu = None
    icm = icm2 = icm3 = None
    try:
        owner_hwnd = _create_owner_window()
        if not owner_hwnd:
            return False
        _apply_menu_theme(owner_hwnd)
        invoke_dir = ""
        try:
            invoke_dir = os.path.dirname(os.path.abspath(paths[0]))
        except Exception:
            invoke_dir = ""
        for p in paths:
            abs_pidl = c_void_p()
            hr = shell32.SHParseDisplayName(
                ctypes.create_unicode_buffer(os.path.abspath(p)),
                None, byref(abs_pidl), 0, byref(c_ulong(0)))
            if hr < 0 or not abs_pidl:
                continue
            par = c_void_p()
            child = c_void_p()
            bhr = shell32.SHBindToParent(abs_pidl, byref(IID_IShellFolder),
                                         byref(par), byref(child))
            if bhr < 0 or not par or not child:
                shell32.ILFree(abs_pidl)
                if par:
                    _release(par)
                continue
            if parent_folder is None:
                parent_folder = par
            elif par.value != parent_folder.value:
                shell32.ILFree(abs_pidl)
                _release(par)
                continue
            else:
                _release(par)
            bound.append(abs_pidl)
            child_pidls.append(child)
        if not parent_folder or not child_pidls:
            return False
        arr = (c_void_p * len(child_pidls))(*child_pidls)
        icm = c_void_p()
        hr = _vt_call(parent_folder, 10, c_int,
                      [wt.HWND, c_uint, POINTER(c_void_p), POINTER(GUID),
                       c_void_p, POINTER(c_void_p)],
                      owner_hwnd, len(child_pidls), arr, byref(IID_IContextMenu),
                      None, byref(icm))
        for abs_pidl in bound:
            shell32.ILFree(abs_pidl)
        bound.clear()
        if hr < 0 or not icm:
            return False
        icm2 = _query_interface(icm, IID_IContextMenu2)
        icm3 = _query_interface(icm, IID_IContextMenu3)
        ctx_ptr = icm3 or icm2 or icm
        _CTX_BY_HWND[int(owner_hwnd)] = (icm2, icm3)
        try:
            hmenu = user32.CreatePopupMenu()
            if not hmenu:
                return False
            added = _vt_call(ctx_ptr, 3, c_int,
                             [wt.HWND, c_uint, c_uint, c_uint, c_uint],
                             hmenu, 0, 1, 0x6FFF, CMF_EXPLORE)
            if added < 0:
                return False
            extra_base = 0x7000
            if extra_actions:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                for i, (label, _cb) in enumerate(extra_actions):
                    user32.AppendMenuW(hmenu, MF_STRING | MF_ENABLED,
                                       extra_base + i, ctypes.create_unicode_buffer(label))
            cmd = user32.TrackPopupMenuEx(hmenu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                          x, y, owner_hwnd, None)
        finally:
            _CTX_BY_HWND.pop(int(owner_hwnd), None)
        if cmd and extra_actions and cmd >= extra_base:
            idx = cmd - extra_base
            if 0 <= idx < len(extra_actions):
                _label, cb = extra_actions[idx]
                cb()
        elif cmd:
            info = CMINVOKECOMMANDINFOEX()
            info.cbSize = ctypes.sizeof(CMINVOKECOMMANDINFOEX)
            info.fMask = CMIC_MASK_UNICODE
            info.hwnd = owner_hwnd
            offset = cmd - 1
            info.lpVerb = cast(offset, wt.LPCWSTR)
            info.lpVerbW = cast(offset, wt.LPCWSTR)
            if invoke_dir and os.path.isdir(invoke_dir):
                info.lpDirectory = invoke_dir
                info.lpDirectoryW = invoke_dir
            info.nShow = SW_NORMAL
            _vt_call(ctx_ptr, 4, c_int, [POINTER(CMINVOKECOMMANDINFOEX)], byref(info))
        return True
    except Exception:
        return False
    finally:
        try:
            if hmenu:
                user32.DestroyMenu(hmenu)
        except Exception:
            pass
        try:
            if owner_hwnd:
                _CTX_BY_HWND.pop(int(owner_hwnd), None)
                user32.DestroyWindow(owner_hwnd)
        except Exception:
            pass
        for abs_pidl in bound:
            try:
                shell32.ILFree(abs_pidl)
            except Exception:
                pass
        _release(parent_folder)
        _release(icm)
        _release(icm2)
        _release(icm3)


def _release(pv):
    try:
        if pv:
            _vt_call(pv, 2, c_int, [], )
    except Exception:
        pass
