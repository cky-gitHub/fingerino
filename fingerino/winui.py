"""Windows-specific window behaviour Qt doesn't cover: keeping the HUD on top
without covering menus, its drop shadow, the taskbar identity, the
single-instance lock and the last-resort error dialog.

Everything here degrades to a no-op on other platforms, so callers don't need
to guard.

Ownership invariant: every function below that changes a window first checks
that the handle belongs to *this* process (see ``_owned``). Nothing but
Fingerino's own windows can be re-ordered or restyled, no matter what handle a
caller passes in.

Note on ctypes: every function used is declared with explicit ``argtypes`` /
``restype``. Without them ctypes guesses 32-bit ints, which mangles HWND
values and pseudo-handles like ``HWND_TOPMOST`` (-1) on 64-bit Windows —
``SetWindowPos`` then fails silently, returning FALSE without raising.
"""

from __future__ import annotations

import os
import sys

_IS_WIN = sys.platform.startswith("win")

if _IS_WIN:
    import ctypes
    from ctypes import wintypes


_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010


_user32 = None


def _u():
    """Lazily bind user32 with correct signatures. None off-Windows."""
    global _user32
    if not _IS_WIN:
        return None
    if _user32 is not None:
        return _user32

    u = ctypes.WinDLL("user32", use_last_error=True)
    # FindWindowW is deliberately not bound: matching on title alone is what
    # once let this module grab a stranger's window. Handles now come from Qt.
    u.GetClassNameW.restype = ctypes.c_int
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                           ctypes.POINTER(wintypes.DWORD)]
    u.SetWindowPos.restype = wintypes.BOOL
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               wintypes.UINT]
    u.GetWindowLongW.restype = wintypes.LONG
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.IsIconic.restype = wintypes.BOOL
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindow.restype = wintypes.HWND
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindowRect.restype = wintypes.BOOL
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32 = u
    return _user32


_MB_ICONERROR = 0x00000010
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000


def alert(title: str, text: str) -> None:
    """Show a modal error dialog.

    A packaged app has no console, so a startup failure printed to stderr goes
    nowhere and the app just seems not to open.
    """
    if not _IS_WIN:
        return
    try:
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.UINT]
        u.MessageBoxW(None, text, title,
                      _MB_ICONERROR | _MB_SETFOREGROUND | _MB_TOPMOST)
    except Exception:
        pass




def _owned(hwnd) -> bool:
    """True only for a live top-level window belonging to *this* process.

    Every function below that changes a window is gated on this, so a handle
    that isn't ours can never be restyled, resized, re-iconed or re-ordered,
    whatever the caller passes in. GetWindowThreadProcessId returns 0 for a
    handle that is dead or was never valid, so this also rejects an HWND that
    Windows has since recycled to somebody else's window -- which is what
    would otherwise let the topmost reassert loop latch onto a stranger.
    """
    u = _u()
    if not u or not hwnd:
        return False
    pid = wintypes.DWORD()
    if not u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        return False
    return pid.value == os.getpid()




def set_app_id(app_id: str) -> None:
    """Give the process its own taskbar identity.

    Without this the window inherits python.exe's taskbar grouping and icon,
    so a custom icon would never show there. Must run before the window exists.
    """
    if not _IS_WIN:
        return
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass  # cosmetic only








def raise_above_all(hwnd) -> None:
    """(Re)assert topmost so the window stays visible over focused windows.

    Windows only guarantees topmost ordering among topmost windows, and other
    apps promoting themselves can bury us, so this is called periodically
    rather than once. Never moves, sizes or activates: Qt owns the geometry,
    and SWP_NOACTIVATE avoids stealing focus from whatever the user is
    actually typing into.
    """
    u = _u()
    if not (u and _owned(hwnd)):
        return
    if u.IsIconic(hwnd):
        return  # leave a minimized window alone
    HWND_TOPMOST = wintypes.HWND(-1)
    u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                   _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)


_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_GW_HWNDPREV = 3
_DWMWA_CLOAKED = 14

# Topmost system UI that opens briefly over everything and has to stay over
# everything while it is open -- the HUD included. Re-pinning above these is
# what made menus, the Start menu and Alt+Tab open *underneath* the HUD.
_TRANSIENT_CLASSES = frozenset({
    "#32768",                               # every popup / context menu
    "tooltips_class32",
    "ComboLBox",                            # an open dropdown's list
    "Windows.UI.Core.CoreWindow",           # Start, search, Action Center, toasts
    "XamlExplorerHostIslandWindow",         # Alt+Tab, Task View (Windows 11)
    "MultitaskingViewFrame",                # Alt+Tab (Windows 10)
    "TaskSwitcherWnd",
    "ForegroundStaging",
    "Shell_TrayWnd",                        # the taskbar
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",             # tray overflow
    "TopLevelWindowForOverflowXamlIsland",
    "Xaml_WindowedPopupClass",              # XAML flyouts and menus
})


def _yields_to(cls: str, exstyle: int) -> bool:
    """Should the HUD let this window sit above it?

    Yes for the shell's own transient UI, and for tool and no-activate
    windows, which is how apps mark their menus, tooltips and floating
    palettes. No for anything else: that is an app window covering the HUD.
    """
    if cls in _TRANSIENT_CLASSES:
        return True
    return bool(exstyle & (_WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE))


def is_buried(hwnd) -> bool:
    """True when the HUD needs re-pinning: it lost its topmost flag, or an
    ordinary app window is sitting over it.

    Reads other windows but never changes them. Only topmost windows can be
    above a topmost HUD, so the walk up the z-order is a short one.
    """
    u = _u()
    if not (u and _owned(hwnd)) or u.IsIconic(hwnd):
        return False
    if not (u.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST):
        return True
    ours = wintypes.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(ours)):
        return False
    cls = ctypes.create_unicode_buffer(256)
    other = wintypes.RECT()
    above = u.GetWindow(hwnd, _GW_HWNDPREV)
    for _ in range(512):  # a z-order can change under us mid-walk
        if not above:
            return False
        if (u.IsWindowVisible(above) and not _cloaked(above)
                and u.GetWindowRect(above, ctypes.byref(other))
                and other.left < ours.right and ours.left < other.right
                and other.top < ours.bottom and ours.top < other.bottom):
            u.GetClassNameW(above, cls, 256)
            exstyle = u.GetWindowLongW(above, _GWL_EXSTYLE) & 0xFFFFFFFF
            if not _yields_to(cls.value, exstyle):
                return True
        above = u.GetWindow(above, _GW_HWNDPREV)
    return False


def _cloaked(hwnd) -> bool:
    """Visible to user32 but hidden by DWM -- suspended UWP apps, other
    virtual desktops. Those cover nothing, so they never count."""
    try:
        value = wintypes.DWORD()
        ctypes.WinDLL("dwmapi").DwmGetWindowAttribute(
            hwnd, _DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
        return bool(value.value)
    except Exception:
        return False




_DWMWA_NCRENDERING_POLICY = 2
_DWMNCRP_ENABLED = 2
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def add_shadow(hwnd) -> None:
    """Give a borderless window the drop shadow ordinary windows have, and
    the rounded corners Windows 11 gives them.

    DWM only draws a shadow for windows with a frame. Turning non-client
    rendering on and extending a 1 px frame into the client area is the
    documented way to get it back on a frameless one; the app paints over that
    pixel anyway. The corner preference is a no-op before Windows 11.
    """
    if not (_u() and _owned(hwnd)):
        return

    # Declared here, not at module level: ctypes is only imported on Windows.
    class _MARGINS(ctypes.Structure):
        _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                    ("top", ctypes.c_int), ("bottom", ctypes.c_int)]

    try:
        dwm = ctypes.WinDLL("dwmapi")
        hwnd = wintypes.HWND(hwnd)
        value = ctypes.c_int(_DWMNCRP_ENABLED)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_NCRENDERING_POLICY,
                                  ctypes.byref(value), ctypes.sizeof(value))
        margins = _MARGINS(1, 1, 1, 1)
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        corner = ctypes.c_int(_DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
                                  ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass  # cosmetic; never worth failing over


_instance_mutex = None


def acquire_single_instance(app_id: str) -> bool:
    """Claim a named mutex; False means another instance already holds it.

    A second launch left running behind the one you can see is the usual way
    the topmost pin outlives what looks like "closing the app" -- the first
    instance is still alive and still reasserting it. The mutex is owned by
    the process and Windows releases it automatically on exit, including a
    crash or a Task Manager kill, so there's nothing to release explicitly.
    """
    global _instance_mutex
    if not _IS_WIN:
        return True
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        _instance_mutex = k.CreateMutexW(None, False, f"Local\\{app_id}")
        if not _instance_mutex:
            return True  # couldn't check -- don't block launch over it
        ERROR_ALREADY_EXISTS = 183
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
    except Exception:
        return True






if _IS_WIN:
    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class _PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]

    class _PROPVARIANT(ctypes.Structure):
        # Only VT_LPWSTR is used; the trailing pointers cover the union.
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                    ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                    ("p", ctypes.c_void_p), ("p2", ctypes.c_void_p)]

    def _guid(d1, d2, d3, tail) -> _GUID:
        return _GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*tail))

    # IID_IPropertyStore
    _IID_IPROPERTYSTORE = _guid(0x886D8EEB, 0x8CF2, 0x4446,
                                (0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))
    # PKEY_AppUserModel_* share this format id.
    _FMTID_APPUSERMODEL = _guid(0x9F4C2855, 0x9F79, 0x4B39,
                                (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3))
    _PKEY_RELAUNCH_ICON = _PROPERTYKEY(_FMTID_APPUSERMODEL, 3)
    _PKEY_RELAUNCH_NAME = _PROPERTYKEY(_FMTID_APPUSERMODEL, 4)
    _PKEY_APPUSERMODEL_ID = _PROPERTYKEY(_FMTID_APPUSERMODEL, 5)
    _VT_LPWSTR = 31




