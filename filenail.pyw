"""FileNail — a nail on the desktop that files can swing from.

Double-click "Start FileNail.vbs", or run:  pyw filenail.pyw

Drag the nail anywhere. Pull the gold ring and let go on a desktop
icon to hook that file. The file hangs off the string and swings
when the nail moves. Click a blank tag to choose a file, or drop
a file from Explorer onto a tag or the nail.

Right-click the nail or a file for more. Ctrl+Shift+Q quits.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import shutil
import sys
import time
import traceback
import uuid
from ctypes import wintypes

# --- Win32 -----------------------------------------------------------------

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32
shlwapi = ctypes.windll.shlwapi
ole32 = ctypes.windll.ole32

HWND = wintypes.HWND
DWORD = wintypes.DWORD
BOOL = wintypes.BOOL
UINT = wintypes.UINT
INT = ctypes.c_int
LONG = wintypes.LONG
LPWSTR = wintypes.LPWSTR
LPCWSTR = wintypes.LPCWSTR
HRESULT = ctypes.HRESULT
LRESULT = ctypes.c_ssize_t
HICON = ctypes.c_void_p
HBITMAP = ctypes.c_void_p
HANDLE = wintypes.HANDLE

GWL_EXSTYLE = -20
GWLP_WNDPROC = -4
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_COLORKEY = 0x00000001
COLORKEY = 0x00FF00FF  # COLORREF magenta, matches #ff00ff
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOCOPYBITS = 0x0100
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_DROPFILES = 0x0233
WM_HOTKEY = 0x0312
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTTRANSPARENT = -1
MOD_SHIFT = 0x0004
MOD_CONTROL = 0x0002
VK_Q = 0x51
LVM_HITTEST = 0x1012
LVM_GETITEMTEXTW = 0x1073
LVIF_TEXT = 0x0001
PROCESS_ACCESS = 0x0008 | 0x0010 | 0x0020 | 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_DISPLAYNAME = 0x000000200
SHGFI_TYPENAME = 0x000000400
SHCONTF_FOLDERS = 0x20
SHCONTF_NONFOLDERS = 0x40
SHCONTF_INCLUDEHIDDEN = 0x80
ERROR_ALREADY_EXISTS = 183

KEY = "#ff00ff"
STATE_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "FileNail")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
LOG_PATH = os.path.join(STATE_DIR, "run.log")
HELD_DIR = os.path.join(STATE_DIR, "held")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

SCALE = 1.0
COM_READY = False


def u(n: float) -> float:
    return n * SCALE


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class LVHITTESTINFO(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("flags", UINT),
        ("iItem", INT),
        ("iSubItem", INT),
        ("iGroup", INT),
    ]


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", UINT),
        ("iItem", INT),
        ("iSubItem", INT),
        ("state", UINT),
        ("stateMask", UINT),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", INT),
        ("iImage", INT),
        ("lParam", ctypes.c_ssize_t),
        ("iIndent", INT),
        ("iGroupId", INT),
        ("cColumns", UINT),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", INT),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class STRRET(ctypes.Structure):
    # Layout that StrRetToBufW accepted on this machine.
    _fields_ = [("uType", UINT), ("data", ctypes.c_byte * 260)]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", HICON),
        ("iIcon", INT),
        ("dwAttributes", DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", BOOL),
        ("xHotspot", DWORD),
        ("yHotspot", DWORD),
        ("hbmMask", HBITMAP),
        ("hbmColor", HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", LONG),
        ("bmWidth", LONG),
        ("bmHeight", LONG),
        ("bmWidthBytes", LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", LONG),
        ("biHeight", LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", LONG),
        ("biYPelsPerMeter", LONG),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


def _fn(dll, restype, name, *argtypes):
    prototype = ctypes.WINFUNCTYPE(restype, *argtypes)
    return prototype((name, dll))


GetWindowLongPtrW = _fn(user32, LRESULT, "GetWindowLongPtrW", HWND, INT)
SetWindowLongPtrW = _fn(user32, LRESULT, "SetWindowLongPtrW", HWND, INT, LRESULT)
CallWindowProcW = _fn(user32, LRESULT, "CallWindowProcW", ctypes.c_void_p, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
SendMessageI = _fn(user32, LRESULT, "SendMessageW", HWND, UINT, ctypes.c_size_t, ctypes.c_ssize_t)
SendMessageP = _fn(user32, LRESULT, "SendMessageW", HWND, UINT, ctypes.c_size_t, ctypes.c_void_p)
FindWindowW = _fn(user32, ctypes.c_void_p, "FindWindowW", LPCWSTR, LPCWSTR)
FindWindowExW = _fn(user32, ctypes.c_void_p, "FindWindowExW", HWND, HWND, LPCWSTR, LPCWSTR)
GetParent = _fn(user32, ctypes.c_void_p, "GetParent", HWND)
GetClassNameW = _fn(user32, INT, "GetClassNameW", HWND, LPWSTR, INT)
SetLayeredWindowAttributes = _fn(user32, BOOL, "SetLayeredWindowAttributes", HWND, DWORD, wintypes.BYTE, DWORD)
SetWindowPos = _fn(user32, BOOL, "SetWindowPos", HWND, HWND, INT, INT, INT, INT, UINT)
RegisterHotKey = _fn(user32, BOOL, "RegisterHotKey", HWND, INT, UINT, UINT)
UnregisterHotKey = _fn(user32, BOOL, "UnregisterHotKey", HWND, INT)
IsWindow = _fn(user32, BOOL, "IsWindow", HWND)
GetWindowThreadProcessId = _fn(user32, DWORD, "GetWindowThreadProcessId", HWND, ctypes.POINTER(DWORD))
ScreenToClient = _fn(user32, BOOL, "ScreenToClient", HWND, ctypes.POINTER(POINT))
GetCursorPos = _fn(user32, BOOL, "GetCursorPos", ctypes.POINTER(POINT))
GetDC = _fn(user32, ctypes.c_void_p, "GetDC", HWND)
ReleaseDC = _fn(user32, INT, "ReleaseDC", HWND, ctypes.c_void_p)
GetIconInfo = _fn(user32, BOOL, "GetIconInfo", HICON, ctypes.POINTER(ICONINFO))
DestroyIcon = _fn(user32, BOOL, "DestroyIcon", HICON)

kernel32.OpenProcess.restype = HANDLE
kernel32.OpenProcess.argtypes = [DWORD, BOOL, DWORD]
kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes = [HANDLE, ctypes.c_void_p, ctypes.c_size_t, DWORD, DWORD]
kernel32.VirtualFreeEx.argtypes = [HANDLE, ctypes.c_void_p, ctypes.c_size_t, DWORD]
kernel32.VirtualFreeEx.restype = BOOL
kernel32.ReadProcessMemory.argtypes = [HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = BOOL
kernel32.WriteProcessMemory.argtypes = [HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.restype = BOOL
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, BOOL, LPCWSTR]
kernel32.CreateMutexW.restype = HANDLE

gdi32.GetObjectW.argtypes = [ctypes.c_void_p, INT, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, UINT, UINT, ctypes.c_void_p, ctypes.c_void_p, UINT]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteObject.restype = BOOL

shell32.SHGetFileInfoW.argtypes = [LPCWSTR, DWORD, ctypes.POINTER(SHFILEINFOW), UINT, UINT]
shell32.SHGetFileInfoW.restype = ctypes.c_size_t
shell32.DragAcceptFiles.argtypes = [HWND, BOOL]
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, UINT, ctypes.c_wchar_p, UINT]
shell32.DragQueryFileW.restype = UINT
shell32.DragQueryPoint.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
shell32.DragQueryPoint.restype = BOOL
shell32.DragFinish.argtypes = [ctypes.c_void_p]
shell32.ILFree.argtypes = [ctypes.c_void_p]
shell32.ShellExecuteW.argtypes = [HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT]
shell32.ShellExecuteW.restype = ctypes.c_void_p

shlwapi.StrRetToBufW.argtypes = [ctypes.POINTER(STRRET), ctypes.c_void_p, LPWSTR, UINT]
shlwapi.StrRetToBufW.restype = HRESULT

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
EnumWindowsProc = ctypes.WINFUNCTYPE(BOOL, HWND, wintypes.LPARAM)


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def detect_scale() -> float:
    try:
        user32.GetDpiForSystem.restype = UINT
        dpi = int(user32.GetDpiForSystem() or 96)
    except Exception:
        dpi = 96
    if dpi < 96:
        dpi = 96
    return dpi / 96.0


def virtual_screen() -> tuple[int, int, int, int]:
    vx = int(user32.GetSystemMetrics(76))
    vy = int(user32.GetSystemMetrics(77))
    vw = int(user32.GetSystemMetrics(78))
    vh = int(user32.GetSystemMetrics(79))
    if vw < 200 or vh < 200:
        vw = int(user32.GetSystemMetrics(0))
        vh = int(user32.GetSystemMetrics(1))
        vx, vy = 0, 0
    return vx, vy, vw, vh


def cursor_pos() -> tuple[int, int]:
    pt = POINT()
    GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def shorten(text: str, width: float, font_px: float) -> str:
    if not text:
        return ""
    max_chars = max(4, int(width / max(font_px * 0.55, 1)))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _inside(path: str, root: str) -> bool:
    path, root = _norm(path), _norm(root)
    return path == root or path.startswith(root + os.sep)


NotifyShell = ctypes.WINFUNCTYPE(None, ctypes.c_long, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p)(("SHChangeNotify", shell32))


def notify_folder(path: str, is_dir: bool = False) -> None:
    """Tell Explorer a file left this folder so the icon disappears immediately."""
    try:
        NotifyShell(0x00000010 if is_dir else 0x00000002, 0x2005, path, None)
        parent = os.path.dirname(path)
        if parent:
            NotifyShell(0x00001000, 0x2005, parent, None)
    except Exception:
        log(traceback.format_exc())


def take_file(path: str) -> tuple[str, str | None]:
    """Move a real file out of its original folder. Returns (held path, original path)."""
    if not path or path.startswith("::") or not os.path.exists(path):
        return path, None
    abs_path = os.path.abspath(path)
    if _inside(abs_path, HELD_DIR):
        return abs_path, None
    if _inside(abs_path, APP_DIR):
        raise PermissionError(abs_path)
    blocked = {
        _norm(os.path.expanduser("~")),
        _norm(os.environ.get("WINDIR") or r"C:\Windows"),
        _norm(os.environ.get("SystemRoot") or r"C:\Windows"),
    }
    if _norm(abs_path) in blocked or len(os.path.abspath(abs_path).rstrip("\\/")) <= 3:
        raise PermissionError(abs_path)
    os.makedirs(HELD_DIR, exist_ok=True)
    name = os.path.basename(abs_path)
    dest = os.path.join(HELD_DIR, name)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(name)
        number = 1
        while os.path.exists(dest):
            dest = os.path.join(HELD_DIR, f"{stem} ({number}){ext}")
            number += 1
    is_dir = os.path.isdir(abs_path)
    shutil.move(abs_path, dest)
    notify_folder(abs_path, is_dir)
    return dest, abs_path


def return_file(held: str, origin: str) -> str:
    """Put a hooked file back where it was taken from."""
    if not held or not origin or held.startswith("::") or not os.path.exists(held):
        return held
    folder = os.path.dirname(origin)
    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)
    dest = origin
    if os.path.exists(dest):
        stem, ext = os.path.splitext(os.path.basename(origin))
        number = 1
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{stem} ({number}){ext}")
            number += 1
    shutil.move(held, dest)
    try:
        NotifyShell(0x00001000, 0x2005, folder, None)
    except Exception:
        log(traceback.format_exc())
    return dest


def log(msg: str) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def ensure_com() -> None:
    global COM_READY
    if not COM_READY:
        ole32.CoInitialize(None)
        COM_READY = True


def make_guid(text: str) -> GUID:
    parsed = uuid.UUID(text)
    return GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version, (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:]))


# --- Desktop icons ---------------------------------------------------------

def find_listview() -> int | None:
    progman = FindWindowW("Progman", None)
    if progman:
        SendMessageI(progman, 0x052C, 0, 0)
        defview = FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if defview:
            lv = FindWindowExW(defview, None, "SysListView32", None)
            if lv:
                return int(lv)
    found: list[int] = []

    def visit(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, buf, 256)
        if buf.value == "WorkerW":
            defview = FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if defview:
                lv = FindWindowExW(defview, None, "SysListView32", None)
                if lv:
                    found.append(int(lv))
        return True

    cb = EnumWindowsProc(visit)
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


class Desktop:
    """Reads the real desktop icon under the cursor, including its file path."""

    def __init__(self) -> None:
        self.lv: int | None = None
        self.proc = None
        self.remote_text = None
        self.remote_blob = None
        self.by_display: dict[str, str] = {}
        self.by_parse: dict[str, str] = {}

    def close(self) -> None:
        if self.proc and self.remote_text:
            kernel32.VirtualFreeEx(self.proc, self.remote_text, 0, MEM_RELEASE)
        if self.proc and self.remote_blob:
            kernel32.VirtualFreeEx(self.proc, self.remote_blob, 0, MEM_RELEASE)
        if self.proc:
            kernel32.CloseHandle(self.proc)
        self.proc = None
        self.remote_text = None
        self.remote_blob = None
        self.lv = None

    def _ensure(self) -> bool:
        if self.lv and IsWindow(self.lv) and self.proc and self.remote_text and self.remote_blob:
            return True
        self.close()
        lv = find_listview()
        if not lv:
            return False
        pid = DWORD()
        GetWindowThreadProcessId(lv, ctypes.byref(pid))
        proc = kernel32.OpenProcess(PROCESS_ACCESS, False, pid.value)
        if not proc:
            return False
        text = kernel32.VirtualAllocEx(proc, None, 1024, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        blob = kernel32.VirtualAllocEx(proc, None, 512, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not text or not blob:
            if text:
                kernel32.VirtualFreeEx(proc, text, 0, MEM_RELEASE)
            if blob:
                kernel32.VirtualFreeEx(proc, blob, 0, MEM_RELEASE)
            kernel32.CloseHandle(proc)
            return False
        self.lv = lv
        self.proc = proc
        self.remote_text = text
        self.remote_blob = blob
        return True

    def _write(self, remote, data, size: int) -> bool:
        done = ctypes.c_size_t()
        return bool(kernel32.WriteProcessMemory(self.proc, remote, data, size, ctypes.byref(done)))

    def _read(self, remote, local, size: int) -> bool:
        done = ctypes.c_size_t()
        return bool(kernel32.ReadProcessMemory(self.proc, remote, local, size, ctypes.byref(done)))

    def refresh(self) -> int:
        """Map desktop display names to parsing paths (files, folders, This PC, …)."""
        ensure_com()
        folder = ctypes.c_void_p()
        if shell32.SHGetDesktopFolder(ctypes.byref(folder)) != 0 or not folder.value:
            return 0
        vtable = ctypes.cast(folder, ctypes.POINTER(ctypes.c_void_p))[0]
        funcs = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))
        enum_objects = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, HWND, DWORD, ctypes.POINTER(ctypes.c_void_p))(funcs[4])
        get_name = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, DWORD, ctypes.c_void_p)(funcs[11])
        release_folder = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(funcs[2])
        enum = ctypes.c_void_p()
        hr = enum_objects(folder, None, SHCONTF_FOLDERS | SHCONTF_NONFOLDERS | SHCONTF_INCLUDEHIDDEN, ctypes.byref(enum))
        by_display: dict[str, str] = {}
        by_parse: dict[str, str] = {}
        count = 0
        if hr == 0 and enum.value:
            evtable = ctypes.cast(enum, ctypes.POINTER(ctypes.c_void_p))[0]
            efuncs = ctypes.cast(evtable, ctypes.POINTER(ctypes.c_void_p))
            next_item = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ulong))(efuncs[3])
            release_enum = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(efuncs[2])
            for _ in range(800):
                pidl = ctypes.c_void_p()
                fetched = ctypes.c_ulong()
                if next_item(enum, 1, ctypes.byref(pidl), ctypes.byref(fetched)) != 0 or not fetched.value:
                    break
                try:
                    display = self._strret(get_name, folder, pidl, 0)
                    parsing = self._strret(get_name, folder, pidl, 0x8000)
                finally:
                    if pidl.value:
                        shell32.ILFree(pidl)
                if not display or not parsing:
                    continue
                count += 1
                previous = by_display.get(display)
                if previous and os.path.exists(previous):
                    continue
                by_display[display] = parsing
                by_parse[parsing] = display
            release_enum(enum)
        release_folder(folder)
        self.by_display = by_display
        self.by_parse = by_parse
        return count

    @staticmethod
    def _strret(get_name, folder, pidl, flags: int) -> str:
        sr = STRRET()
        if get_name(folder, pidl, flags, ctypes.byref(sr)) != 0:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        if shlwapi.StrRetToBufW(ctypes.byref(sr), pidl, buf, 1024) != 0:
            return ""
        return buf.value

    def lookup(self, display_name: str) -> str | None:
        if display_name in self.by_display:
            return self.by_display[display_name]
        folded = display_name.casefold()
        for key, value in self.by_display.items():
            if key.casefold() == folded:
                return value
        return None

    def display_for(self, parsing: str) -> str | None:
        return self.by_parse.get(parsing)

    def _item_name(self, index: int) -> str:
        blank = ctypes.create_unicode_buffer(260)
        self._write(self.remote_text, blank, 520)
        item = LVITEMW()
        item.mask = LVIF_TEXT
        item.iSubItem = 0
        item.pszText = self.remote_text
        item.cchTextMax = 260
        if not self._write(self.remote_blob, ctypes.byref(item), ctypes.sizeof(item)):
            return ""
        SendMessageP(self.lv, LVM_GETITEMTEXTW, index, self.remote_blob)
        buf = ctypes.create_unicode_buffer(260)
        if not self._read(self.remote_text, buf, 520):
            return ""
        return buf.value

    def _hit_index(self, sx: int, sy: int) -> int:
        if not self._ensure():
            return -1
        pt = POINT(int(sx), int(sy))
        ScreenToClient(self.lv, ctypes.byref(pt))
        info = LVHITTESTINFO()
        info.pt.x = pt.x
        info.pt.y = pt.y
        info.iItem = -1
        if not self._write(self.remote_blob, ctypes.byref(info), ctypes.sizeof(info)):
            return -1
        SendMessageP(self.lv, LVM_HITTEST, 0, self.remote_blob)
        if not self._read(self.remote_blob, ctypes.byref(info), ctypes.sizeof(info)):
            return -1
        return int(info.iItem)

    def under_cursor(self, sx: int, sy: int, forgive: bool = False) -> tuple[str, str] | None:
        offsets = [(0, 0)]
        if forgive:
            offsets += [(0, -24), (0, 18), (-18, 0), (18, 0), (-14, -16), (14, -16), (-14, 14), (14, 14)]
        seen: set[int] = set()
        for dx, dy in offsets:
            index = self._hit_index(sx + dx, sy + dy)
            if index < 0 or index in seen:
                continue
            seen.add(index)
            name = self._item_name(index)
            if not name:
                continue
            path = self.lookup(name)
            if path is None:
                self.refresh()
                path = self.lookup(name)
            if path:
                return name, path
        return None


# --- Icons -----------------------------------------------------------------

_ICON_CACHE: dict[str, tuple[object, str]] = {}


def _png_rgba(width: int, height: int, bgra) -> bytes:
    import struct
    import zlib

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        base = y * width * 4
        for x in range(width):
            i = base + x * 4
            raw += bytes((bgra[i + 2], bgra[i + 1], bgra[i], bgra[i + 3]))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")


def _bgra_photo(master, width: int, height: int, pixels) -> object:
    import base64
    import tkinter as tk

    encoded = base64.b64encode(_png_rgba(width, height, pixels))
    return tk.PhotoImage(master=master, data=encoded)


def hicon_to_photo(master, hicon) -> object | None:
    import tkinter as tk

    info = ICONINFO()
    if not GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        bmp = BITMAP()
        if not gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp)):
            return None
        width, height = int(bmp.bmWidth), int(bmp.bmHeight)
        if width <= 0 or height <= 0 or width > 256 or height > 256:
            return None
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(header)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        buf = (ctypes.c_ubyte * (width * height * 4))()
        hdc = GetDC(None)
        try:
            gdi32.GetDIBits(hdc, info.hbmColor, 0, height, buf, ctypes.byref(header), 0)
        finally:
            ReleaseDC(None, hdc)
        if max(buf[3::4]) == 0 and info.hbmMask:
            mask_header = BITMAPINFOHEADER()
            mask_header.biSize = ctypes.sizeof(mask_header)
            mask_header.biWidth = width
            mask_header.biHeight = -height
            mask_header.biPlanes = 1
            mask_header.biBitCount = 32
            mask_header.biCompression = 0
            mask = (ctypes.c_ubyte * (width * height * 4))()
            hdc = GetDC(None)
            try:
                gdi32.GetDIBits(hdc, info.hbmMask, 0, height, mask, ctypes.byref(mask_header), 0)
            finally:
                ReleaseDC(None, hdc)
            for i in range(0, width * height * 4, 4):
                white = mask[i] > 200 and mask[i + 1] > 200 and mask[i + 2] > 200
                buf[i + 3] = 0 if white else 255
        image = _bgra_photo(master, width, height, buf)
        if image.width() <= 40:
            image = image.zoom(2, 2)
        elif SCALE >= 1.25 and image.width() < 64:
            image = image.zoom(2, 2)
        return image
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)


def load_icon(master, path: str) -> tuple[object | None, str]:
    cached = _ICON_CACHE.get(path)
    if cached is not None:
        return cached
    info = SHFILEINFOW()
    flags = SHGFI_ICON | SHGFI_LARGEICON | SHGFI_TYPENAME | SHGFI_DISPLAYNAME
    photo = None
    type_name = ""
    if shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), flags):
        type_name = info.szTypeName or ""
        if info.hIcon:
            try:
                photo = hicon_to_photo(master, info.hIcon)
            finally:
                DestroyIcon(info.hIcon)
    _ICON_CACHE[path] = (photo, type_name)
    return photo, type_name


# --- Rope physics ----------------------------------------------------------

class Rope:
    def __init__(self, length: float, ax: float, ay: float, angle: float = 0.05, push: float = 0.0, path: str | None = None, display: str | None = None, user_made: bool = False):
        self.length = max(u(48), float(length))
        self.path = path
        self.display = display or ""
        self.type_name = ""
        self.icon = None
        self.missing = False
        self.flash = 0
        self.user_made = user_made
        self.origin: str | None = None
        self.points: list[list[float]] = []
        self._spawn(ax, ay, angle, push)

    def desired_n(self) -> int:
        seg = max(u(15), 8)
        return max(6, min(28, int(self.length / seg) + 1))

    def _spawn(self, ax: float, ay: float, angle: float, push: float) -> None:
        ex = ax + math.sin(angle) * self.length
        ey = ay + math.cos(angle) * self.length
        self.layout_line(ax, ay, ex, ey, push, 0.0)
        self.length = max(self.length, math.hypot(ex - ax, ey - ay))

    def layout_line(self, ax: float, ay: float, ex: float, ey: float, vx: float = 0.0, vy: float = 0.0) -> None:
        dist = math.hypot(ex - ax, ey - ay)
        self.length = clamp(max(dist, u(36)), u(36), u(980))
        n = self.desired_n()
        pts = []
        sag = min(u(18), self.length * 0.06)
        for i in range(n):
            t = i / (n - 1)
            x = ax + (ex - ax) * t
            y = ay + (ey - ay) * t + math.sin(t * math.pi) * sag
            pts.append([x, y, x - vx * t, y - vy * t])
        self.points = pts

    def set_length(self, ax: float, ay: float, new_len: float) -> None:
        new_len = clamp(float(new_len), u(40), u(980))
        ex, ey = self.end()
        dx, dy = ex - ax, ey - ay
        dist = math.hypot(dx, dy) or 1.0
        if abs(dist - new_len) > 1.5:
            scale = new_len / dist
            end = self.points[-1]
            vx, vy = end[0] - end[2], end[1] - end[3]
            end[0] = ax + dx * scale
            end[1] = ay + dy * scale
            end[2] = end[0] - vx
            end[3] = end[1] - vy
        self.length = new_len
        self._fit_count(ax, ay)

    def end(self) -> tuple[float, float]:
        p = self.points[-1]
        return p[0], p[1]

    def velocity(self) -> tuple[float, float]:
        p = self.points[-1]
        return p[0] - p[2], p[1] - p[3]

    def _fit_count(self, ax: float, ay: float) -> None:
        want = self.desired_n()
        pts = self.points
        if want == len(pts) or len(pts) < 2:
            pts[0][0] = ax
            pts[0][1] = ay
            return
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
        total = cum[-1] or 1.0
        out = []
        for i in range(want):
            dist = total * (i / (want - 1))
            j = 1
            while j < len(cum) - 1 and cum[j] < dist:
                j += 1
            span = (cum[j] - cum[j - 1]) or 1.0
            t = (dist - cum[j - 1]) / span
            a, b = pts[j - 1], pts[j]
            out.append([a[k] + (b[k] - a[k]) * t for k in range(4)])
        out[0][0], out[0][1] = ax, ay
        self.points = out

    def step(self, ax: float, ay: float, hold: tuple[float, float] | None = None, hold_v: tuple[float, float] = (0.0, 0.0), floor_y: float | None = None, left: float | None = None, right: float | None = None) -> None:
        if len(self.points) < 2:
            return
        if hold is not None:
            dist = math.hypot(hold[0] - ax, hold[1] - ay)
            self.length = clamp(dist, u(40), u(980))
        self._fit_count(ax, ay)
        pts = self.points
        n = len(pts)
        g = 0.36 * SCALE
        end_mass = 3.4 if self.path or not hold else 2.2
        limit = u(70)
        for i, p in enumerate(pts):
            if i == 0:
                p[0], p[1], p[2], p[3] = ax, ay, ax, ay
                continue
            if hold is not None and i == n - 1:
                p[0], p[1] = hold
                p[2], p[3] = hold[0] - hold_v[0], hold[1] - hold_v[1]
                continue
            vx = p[0] - p[2]
            vy = p[1] - p[3]
            speed = math.hypot(vx, vy)
            if speed > limit:
                vx *= limit / speed
                vy *= limit / speed
            damp = 0.993 if i == n - 1 else 0.86
            p[2], p[3] = p[0], p[1]
            p[0] += vx * damp
            p[1] += vy * damp + g

        rest = self.length / (n - 1)

        def inv_mass(index: int) -> float:
            if index == 0 or (hold is not None and index == n - 1):
                return 0.0
            if index == n - 1:
                return 1.0 / end_mass
            return 2.4

        for _ in range(16):
            pts[0][0], pts[0][1] = ax, ay
            for i in range(n - 1):
                a = pts[i]
                b = pts[i + 1]
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                dist = math.hypot(dx, dy) or 0.0001
                inv_a = inv_mass(i)
                inv_b = inv_mass(i + 1)
                share = inv_a + inv_b
                if share == 0:
                    continue
                corr = dist - rest
                ux, uy = dx / dist, dy / dist
                a[0] += ux * corr * (inv_a / share)
                a[1] += uy * corr * (inv_a / share)
                b[0] -= ux * corr * (inv_b / share)
                b[1] -= uy * corr * (inv_b / share)
            if hold is not None:
                pts[-1][0], pts[-1][1] = hold
            pts[0][0], pts[0][1] = ax, ay

        end = pts[-1]
        if floor_y is not None and end[1] > floor_y:
            end[1] = floor_y
            if end[3] < end[1]:
                end[3] = end[1]
        if left is not None and end[0] < left:
            end[0] = left
        if right is not None and end[0] > right:
            end[0] = right
        if self.flash:
            self.flash -= 1


def separate_ropes(ropes: list[Rope]) -> None:
    gap = u(36)
    for i, a in enumerate(ropes):
        ax, ay = a.end()
        for b in ropes[i + 1 :]:
            bx, by = b.end()
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy) or 0.001
            if dist >= gap:
                continue
            push = (gap - dist) * 0.35
            ux, uy = dx / dist, dy / dist
            a.points[-1][0] -= ux * push
            a.points[-1][1] -= uy * push
            b.points[-1][0] += ux * push
            b.points[-1][1] += uy * push


# --- App -------------------------------------------------------------------

class Nail:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.squish = 1.0
        self.squish_v = 0.0

    def anchor(self) -> tuple[float, float]:
        return self.x, self.y + u(42)

    def ring(self) -> tuple[float, float]:
        return self.x, self.y + u(32)

    def boing(self, kick: float = 0.22) -> None:
        self.squish_v = kick

    def step(self) -> None:
        self.squish_v += (1.0 - self.squish) * 0.34
        self.squish_v *= 0.7
        self.squish += self.squish_v
        self.squish = clamp(self.squish, 0.82, 1.28)


class App:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.vx, self.vy, self.vw, self.vh = virtual_screen()
        self.topmost = True
        self.hint_done = False
        self.freeze = False
        self.drag_lock = False
        self._ct = None
        self._dying = False
        self.mode = None
        self.active: Rope | None = None
        self.hold = (0.0, 0.0)
        self.down = (0.0, 0.0)
        self.moved = False
        self.down_hit = (None, None)
        self.mvx = 0.0
        self.mvy = 0.0
        self.last_mouse = cursor_pos()
        self.hover_hit = None
        self.hover_at = 0.0
        self.status = ""
        self.status_until = 0.0
        self.blink = 0
        self.sparks: list[dict] = []
        self.seen_hour = time.localtime().tm_hour
        self.next_note = time.time() + random.uniform(45, 80)
        self.t = 0
        self.dirty = False
        self.ropes: list[Rope] = []
        self._hwnd = None
        self._old_proc = None
        self._wndproc = None
        self._mutex = None
        self.desktop = Desktop()
        self._ticks = 0
        self.ox = 0.0
        self.oy = 0.0
        self._win = None
        self._pending_drops: list[tuple[list[str], float, float]] = []
        self._hotkey = False
        self._cursor_kind = None

        cx, cy = self.primary_point(0.5, 0.34)
        self.nail = Nail(cx, cy)
        self._load()

        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as fh:
            fh.write("")
        log(f"start scale={SCALE:.2f} screen={self.vw}x{self.vh} origin={self.vx},{self.vy}")

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.configure(bg=KEY)
        root.attributes("-transparentcolor", KEY)
        root.attributes("-topmost", True)
        self.root = root
        canvas = tk.Canvas(root, width=320, height=420, bg=KEY, highlightthickness=0, bd=0)
        canvas.place(x=0, y=0, width=320, height=420)
        self.canvas = canvas
        canvas.bind("<ButtonPress-1>", self.on_down)
        canvas.bind("<B1-Motion>", self.on_move)
        canvas.bind("<ButtonRelease-1>", self.on_up)
        canvas.bind("<ButtonPress-3>", self.on_right)
        canvas.bind("<Double-Button-1>", self.on_double)
        canvas.bind("<MouseWheel>", self.on_wheel)
        root.bind("<Control-Shift-q>", lambda _e: self.quit())
        root.bind("<Control-Shift-Q>", lambda _e: self.quit())

        self.title_font = ("Segoe UI", max(9, int(round(11 * SCALE))), "bold")
        self.sub_font = ("Segoe UI", max(8, int(round(9 * SCALE))))
        self.hint_font = ("Segoe UI", max(9, int(round(11 * SCALE))), "bold")
        self.small_font = ("Segoe UI", max(8, int(round(9 * SCALE))), "bold")
        self.place_window(force=True)

    def primary_point(self, fx: float, fy: float) -> tuple[float, float]:
        sw = int(user32.GetSystemMetrics(0))
        sh = int(user32.GetSystemMetrics(1))
        return (0 - self.vx) + sw * fx, (0 - self.vy) + sh * fy

    def to_canvas(self, sx: int, sy: int) -> tuple[float, float]:
        return sx - self.vx, sy - self.vy

    def run(self) -> None:
        mutex_dll = ctypes.WinDLL("kernel32", use_last_error=True)
        self._mutex = mutex_dll.CreateMutexW(None, False, "Local\\FileNailDesktopToy")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            log("already running")
            self.root.destroy()
            return
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.update_idletasks()
        self.root.attributes("-transparentcolor", KEY)
        self.root.attributes("-topmost", True)
        self._hwnd = self._resolve_hwnd()
        log(f"hwnd={self._hwnd}")
        if self._hwnd:
            self._install_wndproc()
            shell32.DragAcceptFiles(self._hwnd, True)
            RegisterHotKey(self._hwnd, 1, MOD_CONTROL | MOD_SHIFT, VK_Q)
        self.root.after(16, self.tick)
        self.root.mainloop()

    def _resolve_hwnd(self) -> int | None:
        child = int(self.root.winfo_id())
        parent = GetParent(child)
        names = []
        for hwnd in (child, int(parent) if parent else 0):
            if not hwnd:
                continue
            buf = ctypes.create_unicode_buffer(128)
            GetClassNameW(hwnd, buf, 128)
            names.append(f"{hwnd}:{buf.value}")
        log("hwnds " + ", ".join(names))
        return int(parent) if parent else child

    def _install_wndproc(self) -> None:
        get_ptr = _fn(user32, ctypes.c_void_p, "GetWindowLongPtrW", HWND, INT)
        set_ptr = _fn(user32, ctypes.c_void_p, "SetWindowLongPtrW", HWND, INT, ctypes.c_void_p)
        self._old_proc = get_ptr(self._hwnd, GWLP_WNDPROC)

        def proc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_NCHITTEST:
                    sx = lparam & 0xFFFF
                    sy = (lparam >> 16) & 0xFFFF
                    if sx >= 0x8000:
                        sx -= 0x10000
                    if sy >= 0x8000:
                        sy -= 0x10000
                    kind, _rope = self.pick(sx - self.vx, sy - self.vy, u(8))
                    if kind is None and not self.drag_lock and not self.freeze:
                        return HTTRANSPARENT
                    return HTCLIENT
                if msg == WM_DROPFILES:
                    paths, x, y = self._read_drop(int(wparam))
                    if paths:
                        self._pending_drops.append((paths, x + self.ox, y + self.oy))
                    return 0
                if msg == WM_HOTKEY:
                    self._hotkey = True
                    return 0
                if msg in (WM_QUERYENDSESSION, WM_ENDSESSION):
                    try:
                        self._save()
                    except Exception:
                        log(traceback.format_exc())
            except Exception:
                if msg == WM_NCHITTEST:
                    return HTCLIENT
            return CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(proc)
        set_ptr(self._hwnd, GWLP_WNDPROC, ctypes.cast(self._wndproc, ctypes.c_void_p))

    def set_clickthrough(self, enabled: bool) -> None:
        if not self._hwnd or enabled == self._ct:
            return
        style = GetWindowLongPtrW(self._hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style = (style | WS_EX_LAYERED) & ~WS_EX_TRANSPARENT
        SetWindowLongPtrW(self._hwnd, GWL_EXSTYLE, style)
        SetLayeredWindowAttributes(self._hwnd, COLORKEY, 255, LWA_COLORKEY)
        SetWindowPos(self._hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        self._ct = enabled

    def card_size(self) -> tuple[float, float]:
        icon = 64
        return icon, icon

    def card_top(self, ey: float) -> float:
        return ey + u(6)

    def tick(self) -> None:
        if self._dying:
            return
        try:
            self.step()
            if self._dying:
                return
            self.place_window()
            self.draw()
            if self._ticks == 0:
                log(f"first frame window={self._win}")
            self._ticks += 1
        except Exception:
            log(traceback.format_exc())
            self._bail("FileNail hit a problem and closed. Details are in the FileNail log.")
            return
        self.root.after(16, self.tick)

    def step(self) -> None:
        self.t += 1
        sx, sy = cursor_pos()
        lx, ly = self.last_mouse
        self.mvx = (sx - lx) * 0.65 + self.mvx * 0.35
        self.mvy = (sy - ly) * 0.65 + self.mvy * 0.35
        self.last_mouse = (sx, sy)
        cx, cy = self.to_canvas(sx, sy)

        if self.mode == "nail":
            self.nail.x = clamp(cx + self.hold[0], u(28), self.vw - u(28))
            self.nail.y = clamp(cy + self.hold[1], u(28), self.vh - u(80))
        elif self.mode == "pull" and self.active is not None:
            ax, ay = self.nail.anchor()
            self.active.layout_line(ax, ay, cx, cy, self.mvx, self.mvy)
            if self.t % 3 == 0:
                self.hover_hit = self.desktop.under_cursor(sx, sy, forgive=False)
                self.hover_at = time.time()

        ax, ay = self.nail.anchor()
        floor_pad = self.card_size()[1] + u(16)
        for rope in self.ropes:
            if self.mode == "pull" and rope is self.active:
                continue
            hold = None
            hold_v = (0.0, 0.0)
            if self.mode == "hold" and rope is self.active:
                hold = (cx + self.hold[0], cy + self.hold[1])
                hold_v = (self.mvx, self.mvy)
            rope.step(ax, ay, hold=hold, hold_v=hold_v, floor_y=self.vh - floor_pad, left=u(24), right=self.vw - u(24))
        if self.mode != "pull":
            separate_ropes([r for r in self.ropes if not (self.mode == "hold" and r is self.active)])
        self.nail.step()
        self._joy_tick()

        if self._ticks == 8 and not self.desktop.by_display:
            try:
                count = self.desktop.refresh()
                log(f"desktop icons indexed: {count}")
            except Exception:
                log(traceback.format_exc())

        if self._hotkey:
            self.quit()
            return
        if self._pending_drops:
            queued = self._pending_drops
            self._pending_drops = []
            for paths, dx, dy in queued:
                try:
                    self._receive_drop(paths, dx, dy)
                    log(f"hooked {len(paths)} file(s)")
                except Exception:
                    log(traceback.format_exc())
                    self.say("Couldn't hook that file")

        kind, _obj = self.pick(cx, cy, u(4))
        if kind != self._cursor_kind:
            self._cursor_kind = kind
            self._set_cursor(kind)

        if self.topmost and self.t % 90 == 0:
            self.root.attributes("-topmost", True)
        if self.dirty and self.t % 40 == 0:
            self._save()
            self.dirty = False
        if self.status and time.time() > self.status_until:
            self.status = ""

    def _set_cursor(self, kind) -> None:
        cursor = ""
        if self.mode in ("nail", "nail-pending") or kind == "nail":
            cursor = "fleur"
        elif self.mode in ("pull", "pull-pending") or kind == "ring":
            cursor = "crosshair"
        elif kind in ("card", "blank"):
            cursor = "hand2"
        elif kind == "close":
            cursor = "hand2"
        try:
            self.canvas.configure(cursor=cursor)
        except Exception:
            pass

    def pick(self, x: float, y: float, slop: float = 0.0) -> tuple[str | None, Rope | None]:
        kx, ky = self.nail.x + u(20), self.nail.y - u(22)
        if math.hypot(x - kx, y - ky) <= u(9) + slop:
            return "close", None
        w, h = self.card_size()
        for rope in reversed(self.ropes):
            if self.mode == "pull" and rope is self.active:
                continue
            ex, ey = rope.end()
            top = self.card_top(ey)
            left = ex - w / 2
            if left - slop <= x <= left + w + slop and top - slop <= y <= top + h + slop:
                return ("card" if rope.path else "blank"), rope
        rx, ry = self.nail.ring()
        if math.hypot(x - rx, y - ry) <= u(14) + slop:
            return "ring", None
        if math.hypot(x - self.nail.x, y - self.nail.y) <= u(28) + slop:
            return "nail", None
        return None, None

    def on_down(self, event) -> None:
        sx, sy = event.x_root, event.y_root
        x, y = self.to_canvas(sx, sy)
        kind, rope = self.pick(x, y, u(4))
        self.down = (x, y)
        self.down_hit = (kind, rope)
        self.moved = False
        self.drag_lock = True
        if kind == "close":
            self.mode = "close"
        elif kind == "ring":
            self.mode = "pull-pending"
        elif kind in ("card", "blank"):
            self.mode = "hold-pending"
            self.active = rope
            ex, ey = rope.end()
            self.hold = (ex - x, ey - y)
        elif kind == "nail":
            self.mode = "nail-pending"
            self.hold = (self.nail.x - x, self.nail.y - y)
        else:
            self.mode = None
            self.drag_lock = False

    def on_move(self, event) -> None:
        if not self.mode:
            return
        x, y = self.to_canvas(event.x_root, event.y_root)
        if math.hypot(x - self.down[0], y - self.down[1]) > u(5):
            self.moved = True
        if self.mode == "nail-pending" and self.moved:
            self.mode = "nail"
        elif self.mode == "pull-pending" and self.moved:
            ax, ay = self.nail.anchor()
            rope = Rope(u(48), ax, ay, user_made=True)
            rope.layout_line(ax, ay, x, y, self.mvx, self.mvy)
            self.ropes.append(rope)
            self.active = rope
            self.mode = "pull"
        elif self.mode == "hold-pending" and self.moved:
            self.mode = "hold"

    def on_up(self, event) -> None:
        x, y = self.to_canvas(event.x_root, event.y_root)
        mode = self.mode
        rope = self.active
        self.mode = None
        self.active = None
        self.drag_lock = False
        try:
            if mode == "close" and not self.moved:
                self.quit()
                return
            if mode == "nail-pending" and not self.moved:
                self.nail.boing()
                self._pop(self.nail.x, self.nail.y, 7)
                self.say(random.choice((
                    "Boop.",
                    "Still here.",
                    "Careful, I'm pointy.",
                    "That helped a little.",
                    "Poke received.",
                )))
            elif mode == "nail":
                self.touch()
            elif mode == "pull" and rope is not None:
                self._finish_pull(rope, event.x_root, event.y_root)
            elif mode == "pull-pending":
                self._new_rope_via_dialog()
            elif mode in ("hold-pending", "hold") and rope is not None:
                if not self.moved and rope.path is None:
                    self._browse_into(rope)
                elif self.moved:
                    self.touch()
        finally:
            self.hover_hit = None

    def on_double(self, event) -> None:
        x, y = self.to_canvas(event.x_root, event.y_root)
        kind, rope = self.pick(x, y, u(4))
        if kind == "card" and rope and rope.path:
            self.open_path(rope.path)

    def on_wheel(self, event) -> None:
        x, y = self.to_canvas(event.x_root, event.y_root)
        _kind, rope = self.pick(x, y, u(10))
        if rope is None:
            return
        ax, ay = self.nail.anchor()
        rope.set_length(ax, ay, rope.length - (event.delta / 120.0) * u(36))
        self.touch()

    def on_right(self, event) -> None:
        x, y = self.to_canvas(event.x_root, event.y_root)
        kind, rope = self.pick(x, y, u(6))
        if kind is None:
            return
        menu = self.tk.Menu(self.root, tearoff=0)
        if rope is not None:
            if rope.path:
                menu.add_command(label="Open", command=lambda r=rope: self.open_path(r.path))
            else:
                menu.add_command(label="Hook a file…", command=lambda r=rope: self._browse_into(r))
            menu.add_command(label="Reel in", command=lambda r=rope: self._reel(r, -u(48)))
            menu.add_command(label="Let out", command=lambda r=rope: self._reel(r, u(48)))
            cut_label = "Put the file back" if getattr(rope, "origin", None) else "Cut string"
            menu.add_command(label=cut_label, command=lambda r=rope: self._cut(r))
            menu.add_separator()
        menu.add_command(label="Hook a file onto a new string…", command=self._new_rope_via_dialog)
        menu.add_checkbutton(label="Float above everything", onvalue=True, offvalue=False, variable=self._top_var(), command=self._apply_top)
        if len(self.ropes) > 1:
            menu.add_command(label="Put everything back", command=self._cut_all)
        menu.add_separator()
        menu.add_command(label="Quit    Ctrl+Shift+Q", command=self.quit)
        self.freeze = True
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
            self.freeze = False

    def _top_var(self):
        if not hasattr(self, "_topmost_var"):
            self._topmost_var = self.tk.BooleanVar(value=self.topmost)
        return self._topmost_var

    def _apply_top(self) -> None:
        self.topmost = bool(self._top_var().get())
        self.root.attributes("-topmost", self.topmost)
        self.touch()

    def _reel(self, rope: Rope, delta: float) -> None:
        ax, ay = self.nail.anchor()
        rope.set_length(ax, ay, rope.length + delta)
        self.touch()

    def _put_back(self, rope: Rope, announce: bool = True) -> None:
        origin = getattr(rope, "origin", None)
        if not origin or not rope.path:
            return
        try:
            return_file(rope.path, origin)
            rope.origin = None
            if announce:
                self.say("Put back " + (rope.display or "the file"))
        except Exception:
            log(traceback.format_exc())
            if announce:
                self.say("Couldn't put the file back")

    def _cut(self, rope: Rope) -> None:
        self._put_back(rope)
        if rope in self.ropes:
            self.ropes.remove(rope)
            self.touch()

    def _cut_all(self) -> None:
        for rope in list(self.ropes):
            self._put_back(rope, announce=False)
        self.ropes.clear()
        self.say("Put the files back")
        self.touch()

    def _finish_pull(self, rope: Rope, sx: int, sy: int) -> None:
        if rope.length < u(42):
            if rope in self.ropes:
                self.ropes.remove(rope)
            return
        hit = self.hover_hit if self.hover_hit and (time.time() - self.hover_at) < 0.25 else None
        if hit is None:
            try:
                hit = self.desktop.under_cursor(sx, sy, forgive=True)
            except Exception:
                log(traceback.format_exc())
                hit = None
        if hit:
            name, path = hit
            self._bind_file(rope, path, name)
            self._drop_demo()
            self.say(f"Hooked {name}")
        else:
            rope.user_made = True
            self.say("Let go on a desktop icon, or click the tag")
        self.nail.boing(0.12)
        self.touch()

    def _bind_file(self, rope: Rope, path: str, display: str | None = None) -> None:
        if path and not path.startswith("::") and os.path.exists(path):
            try:
                held, origin = take_file(path)
            except PermissionError:
                self.say("That one has to stay where it is")
                return
            except Exception:
                log(traceback.format_exc())
                self.say("Couldn't pick that file up")
                return
            if origin:
                rope.origin = origin
                path = held
            elif held:
                path = held
        rope.path = path
        rope.user_made = True
        rope.missing = bool(path) and not path.startswith("::") and not os.path.exists(path)
        if display:
            rope.display = display
        elif path.startswith("::"):
            rope.display = self.desktop.display_for(path) or "Desktop item"
        else:
            rope.display = os.path.basename(getattr(rope, "origin", None) or path)
        try:
            rope.icon, rope.type_name = load_icon(self.root, path)
        except Exception:
            log(traceback.format_exc())
            rope.icon, rope.type_name = None, ""
        rope.flash = 24
        end = rope.points[-1]
        end[3] = end[1] + u(7)
        self.nail.boing(0.18)
        self.hint_done = True
        self._pop(end[0], end[1] + u(28), 9)
        self.say(random.choice((
            "I'll swing this one.",
            "Got it. Safe up here.",
            "New friend. Very official.",
            "Hanging this with care.",
        )), 2.8)

    def _drop_demo(self) -> None:
        if any(r.path for r in self.ropes):
            self.ropes = [r for r in self.ropes if r.path or r.user_made]

    def _browse_into(self, rope: Rope) -> None:
        path = self._ask_file()
        if not path:
            return
        self._bind_file(rope, path)
        self._drop_demo()
        self.touch()

    def _new_rope_via_dialog(self) -> None:
        path = self._ask_file()
        if not path:
            return
        ax, ay = self.nail.anchor()
        angle = ((len(self.ropes) % 7) - 3) * 0.18
        rope = Rope(u(210), ax, ay, angle=angle, push=u(3.2), user_made=True)
        self.ropes.append(rope)
        display = os.path.basename(path)
        self._bind_file(rope, path, display)
        self._drop_demo()
        self.touch()

    def _ask_file(self) -> str | None:
        self.freeze = True
        self.root.attributes("-topmost", False)
        try:
            path = self.filedialog.askopenfilename(parent=self.root, title="Hook a file onto the nail")
        finally:
            if self.topmost:
                self.root.attributes("-topmost", True)
            self.freeze = False
        return path or None

    def open_path(self, path: str) -> None:
        if not path.startswith("::") and not os.path.exists(path):
            self.say("That file isn't there anymore")
            return
        try:
            if path.startswith("::"):
                shell32.ShellExecuteW(None, "open", path, None, None, 1)
            else:
                os.startfile(path)
        except Exception:
            log(traceback.format_exc())
            self.say("Couldn't open that")

    def _read_drop(self, hdrop: int) -> tuple[list[str], float, float]:
        paths: list[str] = []
        pt = POINT()
        try:
            count = int(shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0))
            for i in range(min(count, 12)):
                buf = ctypes.create_unicode_buffer(1024)
                shell32.DragQueryFileW(hdrop, i, buf, 1024)
                if buf.value:
                    paths.append(buf.value)
            shell32.DragQueryPoint(hdrop, ctypes.byref(pt))
        finally:
            shell32.DragFinish(hdrop)
        return paths, float(pt.x), float(pt.y)

    def _receive_drop(self, paths: list[str], x: float, y: float) -> None:
        kind, rope = self.pick(x, y, u(30))
        targets = []
        if rope is not None and rope.path is None:
            targets.append(rope)
        for path in paths:
            if targets:
                current = targets.pop(0)
            else:
                ax, ay = self.nail.anchor()
                angle = ((len(self.ropes) % 7) - 3) * 0.2
                current = Rope(max(u(160), math.hypot(x - ax, y - ay)), ax, ay, angle=angle, push=u(2), user_made=True)
                self.ropes.append(current)
            self._bind_file(current, path)
        self._drop_demo()
        self.nail.boing()
        self.touch()

    def say(self, text: str, seconds: float = 2.4) -> None:
        self.status = text
        self.status_until = time.time() + seconds

    def _pop(self, x: float, y: float, count: int) -> None:
        colors = ("#f0c75a", "#e24b4b", "#fff8e8", "#7ec8e3", "#f3a6c8")
        for _ in range(count):
            ang = random.random() * math.tau
            spd = u(0.35) + random.random() * u(1.1)
            life = 14 + random.randrange(10)
            self.sparks.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd,
                "vy": math.sin(ang) * spd - u(0.35),
                "life": life,
                "max": life,
                "color": random.choice(colors),
            })
        if len(self.sparks) > 28:
            self.sparks = self.sparks[-28:]

    def _joy_tick(self) -> None:
        if self.blink > 0:
            self.blink -= 1
        elif self.t % 40 == 0 and random.random() < 0.22:
            self.blink = 4
        for spark in self.sparks:
            spark["x"] += spark["vx"]
            spark["y"] += spark["vy"]
            spark["vy"] -= u(0.02)
            spark["life"] -= 1
        if self.sparks:
            self.sparks = [spark for spark in self.sparks if spark["life"] > 0]
        now = time.localtime()
        hour_changed = now.tm_hour != self.seen_hour
        if hour_changed:
            self.seen_hour = now.tm_hour
        if self.mode or self.status or not self.hint_done:
            return
        if hour_changed:
            line = self._hour_line(now)
            if line:
                self.say(line, 3.4)
                return
        if time.time() < self.next_note:
            return
        self.next_note = time.time() + random.uniform(200, 380)
        line = self._office_note(now)
        if line:
            self.say(line, 3.6)

    def _hour_line(self, now: time.struct_time) -> str:
        if now.tm_wday >= 5 or not (9 <= now.tm_hour < 18):
            return ""
        if now.tm_hour == 12:
            return "Noon. Eat something."
        if now.tm_hour == 17:
            return "Five o'clock. You can start leaving."
        if now.tm_hour == 9:
            return "Nine o'clock. We begin."
        return f"{now.tm_hour} o'clock. Still standing."

    def _office_note(self, now: time.struct_time) -> str:
        hour = now.tm_hour
        if now.tm_wday >= 5:
            return random.choice(("Even nails get weekends.", "This swing is off the clock."))
        if hour < 8 or hour >= 19:
            return ""
        if hour < 11:
            pool = ("You made it in. Heroic.", "Coffee counts as a plan.", "The inbox can wait one swing.")
        elif hour < 14:
            pool = ("Lunch is not a luxury.", "Halfway. The nail is proud.", "Stand up. The file already did.")
        elif hour < 17:
            pool = ("Still going. That's the job.", "One kind email, then a breath.", "You are doing fine. Really.")
        else:
            pool = ("The day is thinning out.", "Go home when you can.", "I'll hold the file. You can go.")
        return random.choice(pool)

    def touch(self) -> None:
        self.dirty = True

    def content_bounds(self) -> tuple[float, float, float, float]:
        # Size from the nail and the string lengths, not from the swinging
        # position, so the window does not resize on every frame.
        ax, ay = self.nail.anchor()
        card_w, card_h = self.card_size()
        reach = u(48)
        for rope in self.ropes:
            reach = max(reach, rope.length)
        extra = max(card_w, card_h) * 0.55 + u(16)
        x0 = min(self.nail.x, ax) - reach - extra
        x1 = max(self.nail.x, ax) + reach + extra
        y0 = self.nail.y - u(52)
        y1 = ay + reach + extra
        if not self.hint_done:
            x1 = max(x1, self.nail.x + u(320))
            y0 = min(y0, self.nail.y - u(28))
        if self.mode == "pull":
            cx, cy = self.to_canvas(*cursor_pos())
            x0 = min(x0, cx - u(30))
            y0 = min(y0, cy - u(30))
            x1 = max(x1, cx + u(180))
            y1 = max(y1, cy + u(48))
        return x0, y0, x1, y1

    def place_window(self, force: bool = False) -> None:
        """Keep a small window around the nail. Don't resize it while dragging.

        Resizing the transparent window on every move leaves a glitch along the sides.
        """
        if self.drag_lock and not force:
            return
        x0, y0, x1, y1 = self.content_bounds()
        pad = u(64)
        edge = u(18)
        if self._win and not force:
            left, top, width, height = self._win
            right, bottom = left + width, top + height
            inside = (x0 - left) >= edge and (y0 - top) >= edge and (right - x1) >= edge and (bottom - y1) >= edge
            roomy = (x0 - left) < u(170) and (y0 - top) < u(170) and (right - x1) < u(170) and (bottom - y1) < u(170)
            if inside and roomy:
                return
        left = int(max(0, x0 - pad))
        top = int(max(0, y0 - pad))
        right = int(min(self.vw, x1 + pad))
        bottom = int(min(self.vh, y1 + pad))
        width = max(48, right - left)
        height = max(48, bottom - top)
        if self._win == (left, top, width, height):
            return
        self._apply_window_rect(left, top, width, height)

    def _apply_window_rect(self, left: int, top: int, width: int, height: int) -> None:
        old = self._win
        self.ox = float(left)
        self.oy = float(top)
        self._win = (int(left), int(top), int(width), int(height))
        sx = int(self.vx + left)
        sy = int(self.vy + top)
        if self._hwnd:
            SetWindowPos(self._hwnd, None, sx, sy, int(width), int(height), SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOCOPYBITS)
        else:
            self.root.geometry(f"{int(width)}x{int(height)}+{sx}+{sy}")
        if not old or old[2] != int(width) or old[3] != int(height):
            self.canvas.configure(width=int(width), height=int(height))
            self.canvas.place(x=0, y=0, width=int(width), height=int(height))

    def draw(self) -> None:
        c = self.canvas
        c.delete("d")
        dizzy = False
        for rope in self.ropes:
            if math.hypot(*rope.velocity()) > u(7):
                dizzy = True
                break
        for rope in self.ropes:
            self._draw_rope(rope)
        self._draw_nail(dizzy)
        self._draw_sparks()
        if not self.hint_done:
            self._draw_hint()
        if self.status:
            self._draw_status()
        if self.mode == "pull" and self.hover_hit:
            sx, sy = cursor_pos()
            x, y = self.to_canvas(sx, sy)
            self._draw_pill(x + u(18), y - u(14), self.hover_hit[0], "#1d1408", "#ffe7a3")
        if self.ox or self.oy:
            c.move("d", -self.ox, -self.oy)

    def _draw_rope(self, rope: Rope) -> None:
        pts = rope.points
        if len(pts) < 2:
            return
        pulling = self.mode == "pull" and rope is self.active
        coords = [v for p in pts for v in (p[0], p[1])]
        color = "#ffe08a" if rope.flash or pulling else "#f3d7a4"
        self.canvas.create_line(*coords, fill="#3a2918", width=max(4, int(u(6))), smooth=True, splinesteps=12, capstyle="round", joinstyle="round", tags="d")
        self.canvas.create_line(*coords, fill=color, width=max(2, int(u(3))), smooth=True, splinesteps=12, capstyle="round", joinstyle="round", tags="d")
        ex, ey = rope.end()
        if pulling:
            self._draw_hook(ex, ey, bool(self.hover_hit))
        else:
            self._draw_card(rope)

    def _draw_hook(self, x: float, y: float, hot: bool) -> None:
        outline = "#8a6a22" if hot else "#3e474f"
        fill = "#ffe08a" if hot else "#e7eef5"
        r = u(8)
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=outline, width=3, fill=fill, tags="d")
        self.canvas.create_arc(x - u(2), y + u(1), x + u(16), y + u(22), start=200, extent=250, style="arc", outline=outline, width=3, tags="d")

    def _draw_card(self, rope: Rope) -> None:
        ex, ey = rope.end()
        size = self.card_size()[0]
        vx, _vy = rope.velocity()
        lean = clamp(vx / u(7), -1.0, 1.0)
        top = self.card_top(ey)
        left = ex - size / 2 + lean * u(5)
        sx, sy = self.last_mouse
        hx, hy = self.to_canvas(sx, sy)
        hovering = left <= hx <= left + size and top <= hy <= top + size
        if hovering or rope.flash:
            pad = u(6)
            self.canvas.create_oval(left - pad, top - pad, left + size + pad, top + size + pad, outline="#e6b84d", width=3, tags="d")
        self.canvas.create_oval(left + u(4), top + size - u(4), left + size - u(2), top + size + u(8), fill="#2a2a2a", outline="", tags="d")
        if rope.icon is not None:
            self.canvas.create_image(left + size / 2, top + u(2), image=rope.icon, anchor="n", tags="d")
        else:
            self._draw_blank_icon(left, top, size, missing=rope.missing)
        self._draw_stupid_face(left, top, size, lean)
        self.canvas.create_oval(ex - u(3.5), ey - u(3.5), ex + u(3.5), ey + u(3.5), fill="#f3d7a4", outline="#3a2918", width=1, tags="d")

    def _draw_blank_icon(self, x: float, y: float, size: float, missing: bool = False) -> None:
        c = self.canvas
        page = "#fffdf6" if not missing else "#eceae4"
        s = size
        c.create_polygon(
            x + s * 0.08, y + s * 0.16,
            x + s * 0.42, y + s * 0.02,
            x + s * 0.78, y + s * 0.10,
            x + s * 0.98, y + s * 0.28,
            x + s * 0.90, y + s * 0.78,
            x + s * 0.62, y + s * 0.98,
            x + s * 0.18, y + s * 0.90,
            x + s * 0.02, y + s * 0.48,
            fill=page, outline="#24180f", width=2, smooth=True, tags="d",
        )
        c.create_polygon(
            x + s * 0.62, y + s * 0.08,
            x + s * 0.78, y + s * 0.10,
            x + s * 0.70, y + s * 0.28,
            fill="#f0d7a4", outline="#24180f", width=2, tags="d",
        )

    def _draw_stupid_face(self, x: float, y: float, size: float, lean: float) -> None:
        c = self.canvas
        s = size
        wander = math.sin(self.t * 0.11) * u(2.2)
        # three dumb hairs
        for i, (hx, hy, dx) in enumerate((
            (0.28, 0.06, -0.10),
            (0.48, -0.02, 0.02),
            (0.70, 0.05, 0.12),
        )):
            c.create_line(
                x + s * hx, y + s * 0.16,
                x + s * (hx + dx), y + s * hy,
                fill="#24180f", width=2, capstyle="round", tags="d",
            )
        # big lazy eye and a smaller one that looks the other way
        if self.blink:
            self._closed_eye(x + s * 0.30, y + s * 0.38, u(11), "#24180f")
            self._closed_eye(x + s * 0.70, y + s * 0.30, u(7), "#24180f")
        else:
            self._googly_eye(x + s * 0.30, y + s * 0.38, u(11), u(9), wander + lean * u(3), u(1.2))
            self._googly_eye(x + s * 0.70, y + s * 0.30, u(7), u(8), -wander * 0.6 + lean * u(1), -u(1.4))
        # crooked open mouth, one tooth, a tongue
        mx, my = x + s * 0.46 + lean * u(2), y + s * 0.66
        mw, mh = u(16), u(9)
        c.create_oval(mx - mw, my - mh * 0.35, mx + mw * 0.85, my + mh, fill="#2a120f", outline="#24180f", width=2, tags="d")
        c.create_rectangle(mx - u(3), my - mh * 0.15, mx + u(2), my + u(4), fill="#fff8ee", outline="", tags="d")
        c.create_oval(mx + u(2), my + u(1), mx + u(12), my + u(9), fill="#e15b73", outline="", tags="d")
        # flappy arms
        arm = lean * u(12)
        self._stupid_arm(x + s * 0.06, y + s * 0.58, -u(16), u(8) - arm)
        self._stupid_arm(x + s * 0.94, y + s * 0.52, u(15), u(11) + arm)

    def _googly_eye(self, cx: float, cy: float, rx: float, ry: float, px: float, py: float) -> None:
        c = self.canvas
        c.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill="#fffef8", outline="#24180f", width=2, tags="d")
        px = clamp(px, -rx * 0.45, rx * 0.45)
        py = clamp(py, -ry * 0.4, ry * 0.4)
        pr = max(u(2.4), min(rx, ry) * 0.38)
        c.create_oval(cx + px - pr, cy + py - pr, cx + px + pr, cy + py + pr, fill="#1a120e", outline="", tags="d")
        c.create_oval(cx + px - pr * 0.35, cy + py - pr * 0.45, cx + px, cy + py - pr * 0.05, fill="#ffffff", outline="", tags="d")

    def _stupid_arm(self, x: float, y: float, dx: float, dy: float) -> None:
        c = self.canvas
        c.create_line(x, y, x + dx, y + dy, fill="#24180f", width=3, capstyle="round", tags="d")
        r = u(4.5)
        c.create_oval(x + dx - r, y + dy - r, x + dx + r, y + dy + r, fill="#f3c07a", outline="#24180f", width=2, tags="d")

    def _draw_nail(self, dizzy: bool) -> None:
        c = self.canvas
        x, y = self.nail.x, self.nail.y
        sx = clamp(self.nail.squish, 0.82, 1.28)
        sy = clamp(2 - sx, 0.82, 1.28)
        hr = u(26)
        c.create_oval(x - hr * 0.8, y + u(18), x + hr * 0.8, y + u(30), fill="#3a3a3a", outline="", tags="d")
        rx, ry = self.nail.ring()
        pulse = 1.0 + (0.07 * math.sin(self.t * 0.18) if self.mode != "pull" else 0.0)
        rr = u(11) * pulse
        c.create_oval(rx - rr, ry - rr, rx + rr, ry + rr, fill="#f0c75a", outline="#8a6418", width=3, tags="d")
        hole = u(4.5)
        c.create_oval(rx - hole, ry - hole, rx + hole, ry + hole, fill=KEY, outline="#8a6418", width=2, tags="d")
        c.create_oval(x - hr * sx, y - hr * sy, x + hr * sx, y + hr * sy, fill="#c5ced6", outline="", tags="d")
        c.create_oval(x - hr * sx * 0.86, y - hr * sy * 0.86, x + hr * sx * 0.86, y + hr * sy * 0.86, fill="#eef2f6", outline="#66707a", width=2, tags="d")
        c.create_oval(x - hr * sx * 0.55, y - hr * sy * 0.62, x - hr * sx * 0.18, y - hr * sy * 0.28, fill="#ffffff", outline="", tags="d")
        if dizzy:
            ang = self.t * 0.45
            dx, dy = math.cos(ang) * u(3.2), math.sin(ang) * u(2.4)
        else:
            mx, my = self.to_canvas(*self.last_mouse)
            dx = clamp((mx - x) / u(36), -1, 1) * u(3.0)
            dy = clamp((my - y) / u(36), -1, 1) * u(2.2)
        for side in (-1, 1):
            ex = x + side * u(8) * sx
            ey = y - u(2) * sy
            if self.blink:
                self._closed_eye(ex, ey, u(5), "#1c1c1c")
            else:
                c.create_oval(ex - u(5), ey - u(5.4), ex + u(5), ey + u(5.4), fill="#1c1c1c", outline="", tags="d")
                c.create_oval(ex - u(3.1) + dx, ey - u(3.3) + dy, ex + u(1.6) + dx, ey + u(1.4) + dy, fill="#f7f7f7", outline="", tags="d")
        if dizzy:
            c.create_oval(x - u(4), y + u(7), x + u(4), y + u(14), outline="#1c1c1c", width=2, tags="d")
        else:
            c.create_arc(x - u(7), y + u(4), x + u(7), y + u(16), start=200, extent=140, style="arc", outline="#1c1c1c", width=2, tags="d")
        kx, ky = x + u(20), y - u(22)
        c.create_oval(kx - u(8), ky - u(8), kx + u(8), ky + u(8), fill="#e24b4b", outline="#6d1d1d", width=2, tags="d")
        c.create_line(kx - u(3.5), ky - u(3.5), kx + u(3.5), ky + u(3.5), fill="white", width=2, tags="d")
        c.create_line(kx + u(3.5), ky - u(3.5), kx - u(3.5), ky + u(3.5), fill="white", width=2, tags="d")

    def _closed_eye(self, cx: float, cy: float, rx: float, color: str) -> None:
        self.canvas.create_line(cx - rx, cy, cx + rx, cy, fill=color, width=2, capstyle="round", tags="d")

    def _draw_sparks(self) -> None:
        c = self.canvas
        for spark in self.sparks:
            scale = 0.45 + spark["life"] / spark["max"]
            r = u(2.4) * scale
            x, y = spark["x"], spark["y"]
            c.create_line(x - r, y, x + r, y, fill=spark["color"], width=2, capstyle="round", tags="d")
            c.create_line(x, y - r, x, y + r, fill=spark["color"], width=2, capstyle="round", tags="d")

    def _draw_hint(self) -> None:
        x = self.nail.x + u(46)
        y = self.nail.y - u(18)
        lines = ["Drag the nail anywhere.", "Pull the gold ring onto a file."]
        w, h = u(250), u(52)
        if x + w > self.vw - u(12):
            x = self.nail.x - u(46) - w
        self.canvas.create_rectangle(x, y, x + w, y + h, fill="#1b140e", outline="#f0c75a", width=2, tags="d")
        self.canvas.create_text(x + u(12), y + u(16), text=lines[0], anchor="w", fill="#fff8e8", font=self.hint_font, tags="d")
        self.canvas.create_text(x + u(12), y + u(36), text=lines[1], anchor="w", fill="#ffe7a3", font=self.small_font, tags="d")

    def _draw_status(self) -> None:
        self._draw_pill(self.nail.x + u(40), self.nail.y + u(48), self.status, "#1b140e", "#fff8e8")

    def _draw_pill(self, x: float, y: float, text: str, bg: str, fg: str) -> None:
        label = shorten(text, u(280), 11 * SCALE)
        w = u(18) + len(label) * u(7.2)
        h = u(28)
        if x + w > self.vw - u(8):
            x = max(u(8), x - w - u(28))
        y = clamp(y, u(8), self.vh - h - u(8))
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=bg, outline="", tags="d")
        self.canvas.create_text(x + w / 2, y + h / 2, text=label, fill=fg, font=self.small_font, tags="d")

    def _bail(self, message: str) -> None:
        if self._dying:
            return
        self._dying = True
        try:
            self.root.attributes("-topmost", False)
            self.root.withdraw()
        except Exception:
            pass
        try:
            self.messagebox.showerror("FileNail", message)
        except Exception:
            pass
        self.quit()

    def quit(self) -> None:
        if self._dying and self.root is None:
            return
        self._dying = True
        try:
            self._save()
        except Exception:
            log(traceback.format_exc())
        try:
            if self._hwnd:
                UnregisterHotKey(self._hwnd, 1)
        except Exception:
            pass
        try:
            self.desktop.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _load(self) -> None:
        if not os.path.exists(STATE_PATH):
            self._spawn_demo()
            return
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            log(traceback.format_exc())
            self._spawn_demo()
            return
        x = float(data.get("x", self.nail.x))
        y = float(data.get("y", self.nail.y))
        if u(10) <= x <= self.vw - u(10) and u(10) <= y <= self.vh - u(10):
            self.nail.x, self.nail.y = x, y
        self.topmost = bool(data.get("topmost", True))
        self.hint_done = bool(data.get("hint_done", False))
        ax, ay = self.nail.anchor()
        for i, item in enumerate(data.get("ropes") or []):
            try:
                length = clamp(float(item.get("length", u(200))), u(48), u(980))
            except Exception:
                continue
            path = item.get("path") or None
            display = item.get("display") or None
            angle = ((i % 7) - 3) * 0.16
            rope = Rope(length, ax, ay, angle=angle, push=u(3.5), path=path, display=display, user_made=True)
            rope.origin = item.get("origin") or None
            if path and not str(path).startswith("::"):
                try:
                    if rope.origin and not os.path.exists(path) and os.path.exists(rope.origin):
                        held, origin = take_file(rope.origin)
                        rope.path = held
                        rope.origin = origin or rope.origin
                    elif not rope.origin:
                        held, origin = take_file(path)
                        rope.path = held
                        if origin:
                            rope.origin = origin
                except Exception:
                    log(traceback.format_exc())
            if rope.path:
                rope.missing = not str(rope.path).startswith("::") and not os.path.exists(rope.path)
            self.ropes.append(rope)
        if not self.ropes:
            self._spawn_demo()

    def _spawn_demo(self) -> None:
        ax, ay = self.nail.anchor()
        rope = Rope(u(190), ax, ay, angle=0.08, push=u(4.5), user_made=False)
        rope.display = ""
        self.ropes.append(rope)

    def _save(self) -> None:
        os.makedirs(STATE_DIR, exist_ok=True)
        ropes = []
        for rope in self.ropes:
            if not rope.user_made and not rope.path:
                continue
            ropes.append({
                "length": rope.length,
                "path": rope.path,
                "display": rope.display,
                "origin": getattr(rope, "origin", None),
            })
        data = {
            "v": 1,
            "x": self.nail.x,
            "y": self.nail.y,
            "topmost": self.topmost,
            "hint_done": self.hint_done,
            "ropes": ropes,
        }
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, STATE_PATH)

    def load_saved_icons(self) -> None:
        for rope in self.ropes:
            if not rope.path:
                continue
            try:
                rope.icon, rope.type_name = load_icon(self.root, rope.path)
            except Exception:
                log(traceback.format_exc())


def run_self_test() -> None:
    import tkinter as tk

    global SCALE
    set_dpi_aware()
    SCALE = 1.0
    assert ctypes.sizeof(LVITEMW) == 88, ctypes.sizeof(LVITEMW)
    assert LVITEMW.pszText.offset == 24

    ax, ay = 400.0, 180.0
    rope = Rope(220.0, ax, ay, angle=0.15, push=6.0, path="C:\\Windows\\notepad.exe", display="notepad")
    max_stretch = 0.0
    samples = []
    for i in range(180):
        ax = 400.0 + math.sin(i / 20.0) * 40.0
        rope.step(ax, ay, floor_y=900, left=0, right=1200)
        ex, ey = rope.end()
        dist = math.hypot(ex - ax, ey - ay)
        max_stretch = max(max_stretch, abs(dist - rope.length) / rope.length)
        if i in (20, 60, 120, 179):
            samples.append((round(ex - ax, 1), round(ey - ay, 1)))
        assert math.isfinite(ex) and math.isfinite(ey)
    assert max_stretch < 0.35, max_stretch
    assert samples[-1][1] > 40

    desktop = Desktop()
    try:
        count = desktop.refresh()
        assert count > 0, count
        assert any(v.startswith("::{20D04FE0-") for v in desktop.by_display.values())
        print("desktop", count, "stretch", round(max_stretch, 3), "samples", samples)
    finally:
        desktop.close()

    root = tk.Tk()
    root.withdraw()
    try:
        photo, type_name = load_icon(root, r"C:\Windows\System32\notepad.exe")
        assert photo is not None
        assert photo.width() >= 32
        print("icon", photo.width(), type_name)
    finally:
        root.destroy()
    print("self-test ok")


def ensure_login_start() -> None:
    """Put a hidden launcher in the user Startup folder so a reboot brings the nail back."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    startup = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
    if not os.path.isdir(startup):
        return
    script = os.path.abspath(os.path.join(APP_DIR, "filenail.pyw"))
    folder = os.path.abspath(APP_DIR)
    body = (
        "' Starts FileNail when Windows signs in.\r\n"
        "Set shell = CreateObject(\"Wscript.Shell\")\r\n"
        f"shell.CurrentDirectory = \"{folder}\"\r\n"
        "Function Found(cmd)\r\n"
        "  Found = (shell.Run(\"cmd /c where \" & cmd & \" >nul 2>&1\", 0, True) = 0)\r\n"
        "End Function\r\n"
        "If Found(\"pyw\") Then\r\n"
        f"  shell.Run \"pyw -3 \"\"{script}\"\"\", 0, False\r\n"
        "ElseIf Found(\"pythonw\") Then\r\n"
        f"  shell.Run \"pythonw \"\"{script}\"\"\", 0, False\r\n"
        "End If\r\n"
    )
    target = os.path.join(startup, "FileNail.vbs")
    try:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as fh:
                if fh.read() == body:
                    return
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(body)
    except Exception:
        log(traceback.format_exc())


def main() -> None:
    if "--self-test" in sys.argv:
        run_self_test()
        return
    ensure_login_start()
    set_dpi_aware()
    global SCALE
    SCALE = detect_scale()
    app = App()
    app.load_saved_icons()
    app.run()


if __name__ == "__main__":
    main()
