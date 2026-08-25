"""Windows-specific window chrome: icon, always-on-top, fixed size.

Everything here degrades to a no-op on other platforms, so callers don't need
to guard. OpenCV gives no API for any of this, so it's done through user32.

Note on ctypes: every function used is declared with explicit ``argtypes`` /
``restype``. Without them ctypes guesses 32-bit ints, which mangles HWND
values and pseudo-handles like ``HWND_TOPMOST`` (-1) on 64-bit Windows —
``SetWindowPos`` then fails silently, returning FALSE without raising.
"""

from __future__ import annotations

import sys

_IS_WIN = sys.platform.startswith("win")

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

_GWL_STYLE = -16
_WS_MAXIMIZEBOX = 0x00010000
_WS_THICKFRAME = 0x00040000
_WS_CAPTION = 0x00C00000

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_WM_SETICON = 0x0080
_ICON_SMALL, _ICON_BIG = 0, 1
_GCLP_HICON, _GCLP_HICONSM = -14, -34

_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010

_user32 = None


def _u():
    """Lazily bind user32 with correct signatures. None off-Windows."""
    global _user32
    if not _IS_WIN:
        return None
    if _user32 is not None:
        return _user32

    u = ctypes.WinDLL("user32", use_last_error=True)
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.SetWindowPos.restype = wintypes.BOOL
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               wintypes.UINT]
    u.GetWindowLongW.restype = wintypes.LONG
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowLongW.restype = wintypes.LONG
    u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    u.IsIconic.restype = wintypes.BOOL
    u.IsIconic.argtypes = [wintypes.HWND]
    u.LoadImageW.restype = wintypes.HANDLE
    u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SendMessageW.restype = ctypes.c_void_p
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                               ctypes.c_void_p, ctypes.c_void_p]
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


def find_window(title: str):
    """HWND for a top-level window by exact title, or None."""
    u = _u()
    if not u:
        return None
    return u.FindWindowW(None, title) or None


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


def lock_size(hwnd) -> None:
    """Drop the maximize box and resize grip; keep minimize and close."""
    u = _u()
    if not (u and hwnd):
        return
    style = u.GetWindowLongW(hwnd, _GWL_STYLE)
    u.SetWindowLongW(hwnd, _GWL_STYLE,
                     style & ~(_WS_MAXIMIZEBOX | _WS_THICKFRAME))
    u.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                   _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_FRAMECHANGED)


def make_borderless(hwnd) -> None:
    """Strip the title bar, leaving a plain client-area window.

    WS_SYSMENU is deliberately left alone: it has no visible effect without
    WS_CAPTION (there's no title bar left to host a system-menu icon on),
    but Windows still checks it for Alt+F4 and the taskbar's right-click
    "Close window" -- with no titlebar X left, that's the only OS-level
    close affordance remaining, so it stays.

    Called once at startup, alongside lock_size() -- before that, every
    later cv2.resizeWindow() call (e.g. the gesture guide opening) operates
    on a window whose non-client area is already gone, so window rect and
    client rect are the same thing throughout the session.
    """
    u = _u()
    if not (u and hwnd):
        return
    style = u.GetWindowLongW(hwnd, _GWL_STYLE)
    u.SetWindowLongW(hwnd, _GWL_STYLE, style & ~_WS_CAPTION)
    u.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                   _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_FRAMECHANGED)


def resize_client(hwnd, w: int, h: int) -> None:
    """Fallback if cv2.resizeWindow ever misbehaves on this borderless
    window: sets the window rect directly. Safe to treat window rect as
    client rect here specifically because make_borderless() has already
    removed all non-client chrome -- no AdjustWindowRectEx dance needed,
    unlike a normal bordered window.
    """
    u = _u()
    if not (u and hwnd):
        return
    u.SetWindowPos(hwnd, None, 0, 0, w, h, _SWP_NOMOVE | _SWP_NOACTIVATE)


def raise_above_all(hwnd) -> None:
    """(Re)assert topmost so the window stays visible over focused windows.

    Windows only guarantees topmost ordering among topmost windows, and other
    apps promoting themselves can bury us, so this is called periodically
    rather than once. Never sizes or activates: SWP_NOSIZE keeps OpenCV's
    client sizing (SetWindowPos sizes the *whole* window, which would squash
    the video by the title-bar height), and SWP_NOACTIVATE avoids stealing
    focus from whatever the user is actually typing into.
    """
    u = _u()
    if not (u and hwnd):
        return
    if u.IsIconic(hwnd):
        return  # leave a minimized window alone
    HWND_TOPMOST = wintypes.HWND(-1)
    u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                   _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)


def unpin(hwnd) -> None:
    """Drop the topmost flag, undoing raise_above_all().

    Deliberately the only thing the console-close handler in main.py calls:
    SetWindowPos just posts to the window's own queue, so it's safe from a
    thread other than the one that created the window -- unlike OpenCV or
    camera teardown, which are not.
    """
    u = _u()
    if not (u and hwnd):
        return
    HWND_NOTOPMOST = wintypes.HWND(-2)
    u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                   _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)


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


_console_handler_ref = None


def install_console_handler(callback) -> None:
    """Run `callback` on console close, logoff, or shutdown.

    None of those raise a Python exception, so the try/finally around the
    main loop never runs for them -- only for a normal return, an uncaught
    exception, or the exit gesture/Esc. Without this, closing the terminal
    window leaves the HUD pinned topmost until Windows gets around to tearing
    the process down.

    The handler fires on a thread Windows creates for it, not the main
    thread, so `callback` must stick to things that are safe cross-thread
    (see unpin() above) rather than touching OpenCV or camera state.
    """
    global _console_handler_ref
    if not _IS_WIN:
        return
    HANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def _handler(_ctrl_type):
        try:
            callback()
        except Exception:
            pass
        return False  # False: still let Windows' default handling proceed

    # Keeping this reference alive is load-bearing -- ctypes callback
    # trampolines are freed once nothing in Python still points at them, and
    # Windows calling into freed memory later would crash the process.
    _console_handler_ref = HANDLER_ROUTINE(_handler)
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.SetConsoleCtrlHandler.restype = wintypes.BOOL
        k.SetConsoleCtrlHandler.argtypes = [HANDLER_ROUTINE, wintypes.BOOL]
        k.SetConsoleCtrlHandler(_console_handler_ref, True)
    except Exception:
        pass


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

    def _guid(d1, d2, d3, tail) -> "_GUID":
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


def set_taskbar_icon(hwnd, ico_path: str, app_id: str, display_name: str) -> bool:
    """Point the taskbar button at our own icon.

    Windows 11 resolves a taskbar button's icon from the window's shell
    property store, not from WM_SETICON — without this the button shows
    python.exe's icon no matter what icon the window carries. Setting
    ``RelaunchIconResource`` is the documented way to override it for a
    process that has no registered shortcut.
    """
    if not (_IS_WIN and hwnd and ico_path):
        return False
    try:
        ole32 = ctypes.WinDLL("ole32")
        shell32 = ctypes.WinDLL("shell32")
        ole32.CoInitialize(None)

        store = ctypes.c_void_p()
        shell32.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        hr = shell32.SHGetPropertyStoreForWindow(
            hwnd, ctypes.byref(_IID_IPROPERTYSTORE), ctypes.byref(store))
        if hr != 0 or not store:
            return False

        # Hand-rolled COM vtable dispatch: IPropertyStore slots 2/6/7.
        vtbl = ctypes.cast(store,
                           ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        SetValue = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(_PROPERTYKEY),
            ctypes.POINTER(_PROPVARIANT))(vtbl[6])
        Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])

        def _put(key, text):
            buf = ctypes.create_unicode_buffer(text)
            pv = _PROPVARIANT()
            pv.vt = _VT_LPWSTR
            pv.p = ctypes.cast(buf, ctypes.c_void_p)
            SetValue(store, ctypes.byref(key), ctypes.byref(pv))
            return buf  # keep alive until Commit

        keep = [
            _put(_PKEY_APPUSERMODEL_ID, app_id),
            _put(_PKEY_RELAUNCH_ICON, f"{ico_path},0"),
            _put(_PKEY_RELAUNCH_NAME, display_name),
        ]
        Commit(store)
        del keep
        Release(store)
        return True
    except Exception:
        return False


def apply_icon(hwnd, ico_path: str) -> None:
    """Set the title-bar and taskbar icons from an .ico file."""
    u = _u()
    if not (u and hwnd and ico_path):
        return
    try:
        small = u.LoadImageW(None, ico_path, _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE)
        big = u.LoadImageW(None, ico_path, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
        if small:
            u.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, small)
        if big:
            u.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, big)

        # Also set the class icons — the taskbar falls back to these.
        setter = getattr(u, "SetClassLongPtrW", None) or u.SetClassLongW
        setter.restype = ctypes.c_void_p
        setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        if big:
            setter(hwnd, _GCLP_HICON, big)
        if small:
            setter(hwnd, _GCLP_HICONSM, small)
    except Exception:
        pass  # cosmetic only
