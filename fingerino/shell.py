"""The app around the tracker: Home window, HUD, tray icon and hotkey.

Qt owns the main thread and runs its own event loop, so Home scrolls and
animates smoothly whatever the camera is doing. Tracking is an
engine.Session on a background thread: Start creates one, Stop ends it, and
the camera is only open while one is running. Finished HUD frames and state
changes cross back to this thread as queued Qt signals.

Opening Fingerino shows Home with tracking off. Closing Home while tracking
runs leaves Fingerino in the tray; closing it while tracking is off quits.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
from PySide6.QtCore import (
    Property,
    QObject,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QIcon,
    QImage,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import (
    __version__,
    actions,
    addons,
    config,
    licence,
    settings,
    signs,
    system_actions,
    winui,
)
from .engine import Options, Session
from .gesture_detector import BUILTIN_SIGNS
from .hud import Hud
from .ui_overlay import _GESTURE_ICON_FILES, _asset_root

_QML = Path(__file__).resolve().parent / "qml" / "Home.qml"

REPO_URL = "https://github.com/cky-gitHub/fingerino"
# Per-user name for the "bring the running copy forward" channel.
_SERVER_NAME = f"fingerino-{os.environ.get('USERNAME') or os.environ.get('USER') or 'user'}"


def _style() -> str:
    """The Qt Quick Controls style that looks native here.

    FluentWinUI3 follows the Windows 11 design language and the system accent
    colour; the macOS style is only present in PySide6's Mac wheels.
    """
    if sys.platform.startswith("win"):
        return "FluentWinUI3"
    if sys.platform == "darwin":
        return "macOS"
    return "Fusion"


def text_scale() -> float:
    """Windows' "Text size" accessibility setting, as a factor (1.0 to 2.25).

    Qt doesn't apply it, so Home scales its own type by this. 1.0 elsewhere,
    and whenever the setting can't be read.
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Accessibility") as key:
            value, _ = winreg.QueryValueEx(key, "TextScaleFactor")
        return min(2.25, max(1.0, int(value) / 100))
    except (OSError, ValueError, TypeError):
        return 1.0


def to_pynput(combo: str) -> str:
    """``"ctrl+alt+f"`` -> ``"<ctrl>+<alt>+f"``, the form GlobalHotKeys reads."""
    return "+".join(p if len(p) == 1 else f"<{p}>" for p in combo.split("+"))


def hotkey_label(combo: str) -> str:
    """``"<ctrl>+<alt>+f"`` -> ``"Ctrl+Alt+F"``, for showing to people."""
    parts = []
    for part in combo.split("+"):
        part = part.strip().strip("<>")
        parts.append(part.upper() if len(part) == 1 else part.capitalize())
    return "+".join(parts)


_QT_NAMED_KEYS = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Tab: "tab", Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter", Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page_up", Qt.Key.Key_PageDown: "page_down",
    Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down", Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
}


def combo_from_qt(key: int, modifiers: int) -> str:
    """A key press in Home's shortcut recorder -> ``"ctrl+shift+k"``, or "".

    "" while only modifiers are down, so the recorder waits for the real key.
    Qt calls Cmd "Control" on macOS and Ctrl "Meta"; this undoes that, so
    what is stored is what pynput will press.
    """
    mods = Qt.KeyboardModifier(modifiers)
    mac = sys.platform == "darwin"
    names = set()
    if mods & Qt.KeyboardModifier.ControlModifier:
        names.add("cmd" if mac else "ctrl")
    if mods & Qt.KeyboardModifier.MetaModifier:
        names.add("ctrl" if mac else "cmd")
    if mods & Qt.KeyboardModifier.AltModifier:
        names.add("alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        names.add("shift")
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key).lower()
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F20:
        name = f"f{key - Qt.Key.Key_F1 + 1}"
    elif key in _QT_NAMED_KEYS:
        name = _QT_NAMED_KEYS[Qt.Key(key)]
    elif 0x21 <= key <= 0x7E and chr(key) != "+":
        name = chr(key)                  # punctuation
    else:
        return ""                        # a modifier on its own, or unknown
    return actions.normalize_combo("+".join([*names, name])) or ""


def hud_size(screen_w: int, screen_h: int) -> tuple[int, int]:
    """HUD size covering config.WINDOW_SCREEN_FRACTION of the screen, at the
    camera's aspect ratio."""
    target_area = screen_w * screen_h * config.WINDOW_SCREEN_FRACTION
    aspect = config.CAMERA_WIDTH / config.CAMERA_HEIGHT
    h = max(1, int((target_area / aspect) ** 0.5))
    return max(1, int(h * aspect)), h


def bring_running_instance_forward() -> bool:
    """Ask an already-running Fingerino to show its Home window.

    True if one answered. Used by a second launch, which then just exits --
    double-clicking the icon again should find the app, not complain.
    """
    _ = QApplication.instance() or QApplication([sys.argv[0]])
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show\n")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


class _Relay(QObject):
    """Signals emitted from other threads; Qt queues them onto this one."""
    frame = Signal()
    state = Signal(bool, bool)
    finished = Signal(object, object)       # (session, error message or None)
    hotkey = Signal()
    record = Signal(float, object)          # (progress, signs.Recording or None)
    sign = Signal(str)                      # a sign fired


class Bridge(QObject):
    """What the Home window's QML can read and do. Everything it does is a
    call into Shell, so the tray, the HUD and Home share one code path."""

    stateChanged = Signal()
    settingsChanged = Signal()
    bindingsChanged = Signal()
    signsChanged = Signal()
    recordChanged = Signal()
    signFired = Signal(str)                 # a sign's id, as it fires
    premiumChanged = Signal()

    def __init__(self, shell: Shell) -> None:
        super().__init__()
        self._shell = shell
        self._icons = {icon: (_asset_root() / "tutorial-gestures" / name).as_uri()
                       for icon, name in _GESTURE_ICON_FILES.items()}
        # Built once: the switches change their own state, so the list never
        # needs rebuilding (rebuilding it is what made it stutter).
        self._bindings_version = 0
        self._groups = [
            {"name": name,
             "cursor": any(icon in config.CURSOR_GESTURES for icon, _, _ in rows),
             "rows": [{"icon": icon, "label": label, "desc": desc,
                       "title": config.SIGN_TITLES.get(icon, label),
                       "image": self._icons.get(icon, ""),
                       "cursor": icon in config.CURSOR_GESTURES,
                       "sign": icon in BUILTIN_SIGNS}
                      for icon, label, desc in rows]}
            for name, rows in config.GESTURE_GROUPS]

    # -- live state -------------------------------------------------------------

    def _running(self) -> bool:
        return self._shell.session is not None

    def _paused(self) -> bool:
        return self._shell.paused

    def _hand_seen(self) -> bool:
        return self._shell.hand_seen

    def _preview_hidden(self) -> bool:
        return self._shell.preview_hidden

    def _error(self) -> str:
        return self._shell.error

    running = Property(bool, _running, notify=stateChanged)
    paused = Property(bool, _paused, notify=stateChanged)
    handSeen = Property(bool, _hand_seen, notify=stateChanged)
    previewHidden = Property(bool, _preview_hidden, notify=stateChanged)
    error = Property(str, _error, notify=stateChanged)

    # -- settings ---------------------------------------------------------------

    def _onboarded(self) -> bool:
        return self._shell.prefs.onboarded

    def _start_on_open(self) -> bool:
        return self._shell.prefs.start_on_open

    def _cursor(self) -> bool:
        return self._shell.prefs.cursor

    def _skeleton(self) -> bool:
        return self._shell.prefs.skeleton

    onboarded = Property(bool, _onboarded, notify=settingsChanged)
    cursorEnabled = Property(bool, _cursor, notify=settingsChanged)
    startOnOpen = Property(bool, _start_on_open, notify=settingsChanged)
    showSkeleton = Property(bool, _skeleton, notify=settingsChanged)

    def _theme(self) -> str:
        return self._shell.prefs.theme

    theme = Property(str, _theme, notify=settingsChanged)

    # -- constants --------------------------------------------------------------

    def _groups_(self) -> list:
        return self._groups

    def _version(self) -> str:
        return __version__

    def _hotkey(self) -> str:
        return hotkey_label(self._shell.prefs.hotkey)

    def _action_kinds(self) -> list:
        return [{"kind": k, "label": v} for k, v in actions.KINDS.items()]

    def _builtin_actions(self) -> list:
        return [{"id": k, "label": v} for k, v in actions.BUILTIN_TITLES.items()]

    def _media_keys(self) -> list:
        return [{"id": k, "label": v} for k, v in actions.MEDIA_KEYS.items()]

    def _bindings_version_(self) -> int:
        return self._bindings_version

    def _record_countdown(self) -> int:
        return config.SIGN_RECORD_COUNTDOWN_S

    def _record_seconds(self) -> int:
        return round(config.SIGN_RECORD_S)

    groups = Property(list, _groups_, constant=True)
    recordCountdown = Property(int, _record_countdown, constant=True)
    recordSeconds = Property(int, _record_seconds, constant=True)
    actionKinds = Property(list, _action_kinds, constant=True)
    builtinActions = Property(list, _builtin_actions, constant=True)
    mediaKeys = Property(list, _media_keys, constant=True)
    # Bumped on every rebinding; QML reads it inside bindings that call
    # actionInfo() so they re-evaluate.
    bindingsVersion = Property(int, _bindings_version_, notify=bindingsChanged)
    version = Property(str, _version, constant=True)
    hotkey = Property(str, _hotkey, notify=settingsChanged)

    def _text_scale(self) -> float:
        return self._shell.text_scale

    textScale = Property(float, _text_scale, constant=True)

    # -- actions ----------------------------------------------------------------

    @Slot()
    def start(self) -> None:
        self._shell.start()

    @Slot()
    def stop(self) -> None:
        self._shell.stop()

    @Slot()
    def togglePause(self) -> None:
        self._shell.toggle_pause()

    @Slot()
    def showPreview(self) -> None:
        self._shell.show_preview()

    @Slot(str, result=bool)
    def gestureEnabled(self, icon: str) -> bool:
        return bool(self._shell.prefs.gestures.get(icon, True))

    @Slot(str, bool)
    def setGestureEnabled(self, icon: str, on: bool) -> None:
        if icon in self._shell.prefs.gestures:
            self._shell.prefs.gestures[icon] = on
            self._shell.save()

    @Slot(bool)
    def setCursorEnabled(self, on: bool) -> None:
        self._shell.prefs.cursor = on
        self._shell.save()
        self.settingsChanged.emit()
        self.signsChanged.emit()          # a sign's "looks like pointing" note

    # -- the user's own signs -----------------------------------------------------

    def _custom_signs(self) -> list:
        reg = self._shell.registry
        lib, cursor = self._shell.library, self._shell.prefs.cursor
        return [{"id": s.id, "name": s.name, "enabled": s.enabled,
                 "locked": lib.locked(s.id),
                 "action": actions.describe(reg.action_for(s.id))["label"],
                 "warning": lib.warning(s.id, cursor)}
                for s in lib.signs]

    def _at_sign_limit(self) -> bool:
        return self._shell.library.at_limit()

    def _record_state(self) -> str:
        return self._shell.record_state

    def _record_progress(self) -> float:
        return self._shell.record_progress

    def _record_message(self) -> str:
        return self._shell.record_message

    def _record_warning(self) -> str:
        return self._shell.record_warning

    customSigns = Property(list, _custom_signs, notify=signsChanged)
    # A new sign would be saved locked (switched off by the limit).
    atSignLimit = Property(bool, _at_sign_limit, notify=signsChanged)
    # idle -> capturing -> review (or failed); see Shell.capture_sign.
    recordState = Property(str, _record_state, notify=recordChanged)
    recordProgress = Property(float, _record_progress, notify=recordChanged)
    recordMessage = Property(str, _record_message, notify=recordChanged)
    recordWarning = Property(str, _record_warning, notify=recordChanged)

    @Slot()
    def captureSign(self) -> None:
        self._shell.capture_sign()

    @Slot(str, bool)
    def holdGestures(self, reason: str, on: bool) -> None:
        """Silence gestures for ``reason`` ("record": countdown until the
        record dialog closes; "editor": while the action editor is open)."""
        self._shell.hold_gestures(on, reason)

    @Slot()
    def cancelRecording(self) -> None:
        self._shell.reset_recording()

    @Slot(str, result="QVariantMap")
    def saveSign(self, name: str) -> dict:
        """Keep the reviewed recording as a new sign: {"id": ...} or {"error": ...}."""
        return self._shell.save_sign(name)

    @Slot(str, str)
    def renameSign(self, sign_id: str, name: str) -> None:
        self._shell.library.rename(sign_id, name)
        self._shell.save_signs()
        self.signsChanged.emit()

    @Slot(str, bool)
    def setSignEnabled(self, sign_id: str, on: bool) -> None:
        self._shell.library.set_enabled(sign_id, on)
        self._shell.save_signs()
        self.signsChanged.emit()

    @Slot(str)
    def deleteSign(self, sign_id: str) -> None:
        self._shell.library.delete(sign_id)
        self._shell.registry.forget(sign_id)
        self._shell.save_signs()
        self._shell.save_actions()
        self.signsChanged.emit()

    @Slot(str)
    def useSignInstead(self, sign_id: str) -> None:
        """Make a locked sign the active one; the one it replaces is locked."""
        self._shell.library.move_to_front(sign_id)
        self._shell.save_signs()
        self.signsChanged.emit()

    # -- Premium -----------------------------------------------------------------

    def _premium_plan(self) -> str:
        return self._shell.premium.plan

    def _trial_days_left(self) -> int:
        return self._shell.premium.days_left

    def _licensed_to(self) -> str:
        return self._shell.premium.email

    def _sign_limit(self) -> int:
        return self._shell.premium.sign_limit

    def _free_sign_limit(self) -> int:
        return config.FREE_CUSTOM_SIGNS

    def _premium_sign_limit(self) -> int:
        return config.PREMIUM_CUSTOM_SIGNS

    def _addon_note(self) -> str:
        return self._shell.addon.note

    def _on_sale(self) -> bool:
        return licence.on_sale()

    def _trial_days(self) -> int:
        return config.TRIAL_DAYS

    premiumPlan = Property(str, _premium_plan, notify=premiumChanged)  # premium/trial/free
    trialDaysLeft = Property(int, _trial_days_left, notify=premiumChanged)
    licensedTo = Property(str, _licensed_to, notify=premiumChanged)
    signLimit = Property(int, _sign_limit, notify=premiumChanged)
    freeSignLimit = Property(int, _free_sign_limit, constant=True)
    premiumSignLimit = Property(int, _premium_sign_limit, constant=True)
    addonNote = Property(str, _addon_note, constant=True)
    onSale = Property(bool, _on_sale, constant=True)        # else "Coming soon"
    trialDays = Property(int, _trial_days, constant=True)

    @Slot(str, result=str)
    def enterLicence(self, text: str) -> str:
        """Check and keep a pasted licence key: "" or why it can't be used."""
        return self._shell.enter_licence(text)

    @Slot()
    def removeLicence(self) -> None:
        self._shell.remove_licence()

    @Slot()
    def openPremium(self) -> None:
        # The browser opens the page; Fingerino itself requests nothing.
        if licence.on_sale():
            QDesktopServices.openUrl(QUrl(config.PREMIUM_URL))

    # -- what signs do -----------------------------------------------------------

    def _bindings_edited(self) -> None:
        self._shell.save_actions()
        self._bindings_version += 1
        self.bindingsChanged.emit()
        self.signsChanged.emit()           # custom sign cards show their action

    @Slot(str, result="QVariantMap")
    def actionInfo(self, sign: str) -> dict:
        return actions.describe(self._shell.registry.action_for(sign))

    @Slot(str, str, str, str, result=str)
    def setAction(self, sign: str, kind: str, target: str, name: str) -> str:
        """Bind ``sign`` to a new action; an error message, or "" if done.

        Typing a command here is what approves it.
        """
        made = actions.make_action(kind, target, name, approved=True)
        if isinstance(made, str):
            return made
        self._shell.registry.bind(sign, made)
        self._bindings_edited()
        return ""

    @Slot(str)
    def clearAction(self, sign: str) -> None:
        self._shell.registry.bind(sign, None)
        self._bindings_edited()

    @Slot(str)
    def resetAction(self, sign: str) -> None:
        self._shell.registry.reset(sign)
        self._bindings_edited()

    @Slot(str, str, str, str, result=str)
    def tryAction(self, sign: str, kind: str, target: str, name: str) -> str:
        """Arm "Try it": an error message, or "" once the sign is live."""
        return self._shell.start_trial(sign, kind, target, name)

    @Slot()
    def endTrial(self) -> None:
        self._shell.end_trial()

    @Slot(int, int, result=str)
    def keyCombo(self, key: int, modifiers: int) -> str:
        """The shortcut being pressed, as stored ("ctrl+shift+k"), or ""."""
        return combo_from_qt(key, modifiers)

    @Slot(str, result=str)
    def setHotkey(self, combo: str) -> str:
        """Change the pause shortcut; an error message, or "" once it works."""
        error = self._shell.set_hotkey(combo)
        if not error:
            self.settingsChanged.emit()
        return error

    @Slot(int, int, result=str)
    def comboFromKey(self, key: int, modifiers: int) -> str:
        """The shortcut being pressed, as people write it ("Ctrl+Shift+K")."""
        combo = combo_from_qt(key, modifiers)
        return actions.combo_label(combo) if combo else ""

    @Slot(str, result=str)
    def comboLabel(self, combo: str) -> str:
        return actions.combo_label(combo) if combo else ""

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        if theme in settings.THEMES:
            self._shell.prefs.theme = theme
            self._shell.save()
            self._shell.apply_theme()
            self.settingsChanged.emit()

    @Slot(bool)
    def setShowSkeleton(self, on: bool) -> None:
        self._shell.prefs.skeleton = on
        self._shell.save()
        self.settingsChanged.emit()

    @Slot(bool)
    def setStartOnOpen(self, on: bool) -> None:
        self._shell.prefs.start_on_open = on
        self._shell.save()
        self.settingsChanged.emit()

    @Slot()
    def dismissWelcome(self) -> None:
        self._shell.prefs.onboarded = True
        self._shell.save()
        self.settingsChanged.emit()

    @Slot()
    def homeClosed(self) -> None:
        self._shell.home_closed()

    @Slot(str)
    def openRepo(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl(f"{REPO_URL}{path}"))

    @Slot()
    def openNotices(self) -> None:
        # packaging/build.py writes the file beside the executable; a source
        # checkout has none, so fall back to the README's licence section.
        local = Path(sys.executable).resolve().parent / "THIRD-PARTY-NOTICES.md"
        if getattr(sys, "frozen", False) and local.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(local)))
        else:
            self.openRepo("#license")

    @Slot()
    def openDataFolder(self) -> None:
        os.makedirs(self._shell.data_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._shell.data_dir))

    @Slot()
    def quit(self) -> None:
        self._shell.quit()


class Shell:
    """Owns the QApplication and every window; starts and stops tracking."""

    def __init__(self, prefs: settings.Settings, data_dir: str,
                 icon_path: str | None, options: Options | None = None,
                 on_crash: Callable[[BaseException], str] | None = None,
                 tray: bool = True, hotkey: bool = True) -> None:
        # Our own argv stays out of Qt's hands: it would otherwise try to
        # interpret flags like --debug itself.
        self.app = cast(QApplication,
                        QApplication.instance() or QApplication([sys.argv[0]]))
        # Closing Home doesn't end the app by itself; home_closed() decides.
        self.app.setQuitOnLastWindowClosed(False)
        QQuickStyle.setStyle(_style())

        self.prefs = prefs
        self.data_dir = data_dir
        self.registry = actions.load(data_dir)
        self.library = signs.load(data_dir)
        # Premium: a licence key, or the trial, lifts the sign limit and
        # unlocks the add-on's features (licence.py, addons.py).
        self.licence = licence.load(data_dir)
        self.premium = licence.status(self.licence, prefs.trial_started, date.today())
        self.library.set_limit(self.premium.sign_limit)
        self.addon = addons.load(addons.Host(__version__, self.entitled))
        # Recording a new sign: see capture_sign().
        self.record_state = "idle"
        self.record_progress = 0.0
        self.record_message = ""
        self.record_warning = ""
        self.text_scale = text_scale()
        self._hold_reasons: set[str] = set()    # see hold_gestures()
        self.trial: tuple[str, actions.Action] | None = None   # see start_trial()
        self._recording: signs.Recording | None = None
        self.options = options or Options()
        self._on_crash = on_crash
        self.session: Session | None = None
        self.paused = False
        self.hand_seen = False
        self.preview_hidden = False
        self.error = ""
        self._told_about_tray = False

        self._relay = _Relay()
        self._relay.frame.connect(self._show_latest_frame)
        self._relay.state.connect(self._on_state)
        self._relay.finished.connect(self._on_finished)
        self._relay.hotkey.connect(self._on_hotkey)
        self._relay.record.connect(self._on_record)
        self._relay.sign.connect(self._on_sign)
        # The newest frame from the session thread. Only the latest is kept,
        # so a busy UI thread skips frames instead of queueing them up.
        self._frame_lock = threading.Lock()
        self._latest: QImage | None = None
        self._frame_pending = False

        icon = QIcon(icon_path) if icon_path else QIcon()
        self.app.setWindowIcon(icon)

        self.bridge = Bridge(self)
        self.apply_theme()
        self.engine = QQmlApplicationEngine()
        self.engine.setInitialProperties({"bridge": self.bridge})
        self.engine.load(QUrl.fromLocalFile(str(_QML)))
        roots = self.engine.rootObjects()
        self.window = cast(QQuickWindow, roots[0]) if roots else None

        screen = self.app.primaryScreen().geometry()
        w, h = hud_size(screen.width(), screen.height())
        self.hud = Hud(QSize(w, h))
        # Inset a little, so the shadow and rounded corners show; still the
        # top-left corner.
        self.hud.move(screen.x() + 8, screen.y() + 8)
        self.hud.minimizeRequested.connect(self.hide_preview)
        self.hud.closeRequested.connect(self.stop)

        # Other apps promoting themselves to topmost can bury the HUD, so the
        # claim is checked on a timer -- and only renewed when an ordinary app
        # window covers it, never over menus, Start or Alt+Tab (winui.is_buried).
        self._topmost = QTimer()
        self._topmost.setInterval(int(config.TOPMOST_REASSERT_S * 1000))
        self._topmost.timeout.connect(self._keep_hud_on_top)
        self._topmost.start()

        # Fingerino can run in the tray for days; the trial ends on time.
        self._premium_timer = QTimer()
        self._premium_timer.setInterval(int(config.PREMIUM_RECHECK_S * 1000))
        self._premium_timer.timeout.connect(self.refresh_premium)
        self._premium_timer.start()

        self.tray: QSystemTrayIcon | None = None
        if tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._build_tray(icon)

        self._hotkey_wanted = hotkey
        self._hotkey = (system_actions.listen_hotkey(prefs.hotkey,
                                                     self._relay.hotkey.emit)
                        if hotkey else None)

        # A second launch connects here and asks for Home.
        self._server = QLocalServer()
        QLocalServer.removeServer(_SERVER_NAME)
        if self._server.listen(_SERVER_NAME):
            self._server.newConnection.connect(self._on_second_launch)
        self._refresh()

    # -- tray -------------------------------------------------------------------

    def _build_tray(self, icon: QIcon) -> None:
        tray = QSystemTrayIcon(icon)
        menu = QMenu()
        self._start_action = menu.addAction("Start tracking")
        self._start_action.triggered.connect(
            lambda: self.stop() if self.session else self.start())
        self._pause_action = menu.addAction("Pause tracking")
        self._pause_action.triggered.connect(self.toggle_pause)
        self._preview_action = menu.addAction("Show camera preview")
        self._preview_action.triggered.connect(self.show_preview)
        menu.addSeparator()
        open_action = QAction("Open Fingerino", menu)
        open_action.triggered.connect(self.show_home)
        menu.addAction(open_action)
        menu.addSeparator()
        quit_action = menu.addAction("Quit Fingerino")
        quit_action.triggered.connect(self.quit)
        self._menu = menu            # keep a reference; Qt doesn't
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray = tray

    def _on_tray_activated(self, reason) -> None:
        # A left click opens Home, the way Windows tray apps behave. The
        # context menu is handled by Qt on right click.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_home()

    def _refresh(self) -> None:
        """Push the current state to QML and the tray."""
        self.bridge.stateChanged.emit()
        if self.tray is None:
            return
        running = self.session is not None
        self._start_action.setText("Stop tracking" if running else "Start tracking")
        self._pause_action.setText("Resume tracking" if self.paused else "Pause tracking")
        self._pause_action.setEnabled(running)
        self._preview_action.setVisible(running and self.preview_hidden)
        state = ("off" if not running else "paused" if self.paused else "tracking")
        self.tray.setToolTip(f"{config.WINDOW_NAME} — {state}")

    # -- tracking ----------------------------------------------------------------

    def start(self) -> None:
        if self.session is not None:
            return
        dpr = self.hud.devicePixelRatioF()
        size = self.hud.size()
        self.options.preview_size = (round(size.width() * dpr),
                                     round(size.height() * dpr))
        # The session reads the same object Home writes, so a switch flipped
        # mid-session applies on the next frame.
        session = Session(self.options, self.prefs, self.registry, self.library)
        self.session = session
        session.hold_gestures(self.gestures_held)
        session.set_trial(self.trial)
        self.paused = False
        self.hand_seen = False
        self.error = ""
        self.preview_hidden = False
        threading.Thread(target=self._work, args=(session,), daemon=True,
                         name="fingerino-tracking").start()
        self.hud.show()
        self._refresh()

    def _work(self, session: Session) -> None:
        """Body of the tracking thread."""
        error: str | None
        try:
            error = session.run(self._on_frame, self._relay.state.emit,
                                self._relay.record.emit, self._relay.sign.emit)
        except Exception as exc:
            error = (self._on_crash(exc) if self._on_crash
                     else f"Tracking stopped unexpectedly: {exc}")
        self._relay.finished.emit(session, error)

    def _on_frame(self, frame: np.ndarray) -> None:
        """Session thread: wrap the frame and hand it over, newest wins."""
        h, w = frame.shape[:2]
        img = QImage(frame.data, w, h, frame.strides[0],
                     QImage.Format.Format_BGR888).copy()
        img.setDevicePixelRatio(self.hud.devicePixelRatioF())
        with self._frame_lock:
            self._latest = img
            if self._frame_pending:
                return
            self._frame_pending = True
        self._relay.frame.emit()

    def _show_latest_frame(self) -> None:
        with self._frame_lock:
            img, self._latest = self._latest, None
            self._frame_pending = False
        if img is not None and self.session is not None:
            self.hud.set_frame(img)

    # -- recording a sign ---------------------------------------------------------

    def _record_update(self, state: str, progress: float = 0.0, message: str = "",
                       warning: str = "") -> None:
        self.record_state, self.record_progress = state, progress
        self.record_message, self.record_warning = message, warning
        self.bridge.recordChanged.emit()

    def capture_sign(self) -> None:
        """Start recording the hand for a new sign (tracking must be on)."""
        if self.session is None:
            self._record_update("failed", message="Start Fingerino first, so the "
                                "camera can see your hand.")
            return
        self._recording = None
        self._record_update("capturing")
        self.session.start_recording(config.SIGN_RECORD_S)

    def apply_theme(self) -> None:
        """Light, dark, or whatever Windows is set to. Fluent follows the
        application's colour scheme live, so this applies at once."""
        hints = self.app.styleHints()
        if self.prefs.theme == "light":
            hints.setColorScheme(Qt.ColorScheme.Light)
        elif self.prefs.theme == "dark":
            hints.setColorScheme(Qt.ColorScheme.Dark)
        else:
            hints.unsetColorScheme()

    def set_hotkey(self, combo: str) -> str:
        """Listen for ``combo`` (``"ctrl+alt+f"``) instead of the current
        pause shortcut. Keeps the old one if the new one can't be used."""
        parts = combo.split("+") if combo else []
        if not parts or not ({"ctrl", "alt", "cmd"} & set(parts[:-1])):
            return "Use Ctrl, Alt or Win with another key, so it can't be typed by accident."
        new = to_pynput(combo)
        if self._hotkey_wanted:
            listener = system_actions.listen_hotkey(new, self._relay.hotkey.emit)
            if listener is None:
                return "That shortcut can't be used here. Try another."
            if self._hotkey is not None:
                self._hotkey.stop()
            self._hotkey = listener
        self.prefs.hotkey = new
        self.save()
        return ""

    def hold_gestures(self, on: bool, reason: str = "record") -> None:
        """Silence gestures while any reason holds them.

        Reasons rather than one flag, because recording hands straight over
        to the action editor: the record dialog finishing closing must not
        let go of the hold the editor has just taken. Remembered here as
        well as passed on, so a session that starts meanwhile (the camera
        is still opening) picks it up.
        """
        if on:
            self._hold_reasons.add(reason)
        else:
            self._hold_reasons.discard(reason)
        if self.session is not None:
            self.session.hold_gestures(self.gestures_held)

    @property
    def gestures_held(self) -> bool:
        return bool(self._hold_reasons)

    def start_trial(self, sign: str, kind: str, target: str, name: str) -> str:
        """Let ``sign`` run this unsaved action, and nothing else act, until
        end_trial(). Starts tracking if it is off, since trying needs the
        camera. Returns an error message, or ""."""
        made = actions.make_action(kind, target, name)
        if isinstance(made, str):
            return made
        self.trial = (sign, made)
        if self.session is None:
            self.start()                 # passes the trial on
        else:
            self.session.set_trial(self.trial)
        return ""

    def end_trial(self) -> None:
        self.trial = None
        if self.session is not None:
            self.session.set_trial(None)

    def reset_recording(self) -> None:
        self._recording = None
        self._record_update("idle")

    def _on_record(self, progress: float, result: object) -> None:
        if self.record_state != "capturing":
            return                       # cancelled meanwhile
        if not isinstance(result, signs.Recording):
            self._record_update("capturing", progress)
            return
        if result.error:
            self._record_update("failed", message=result.error)
            return
        self._recording = result
        warning = ""
        if result.builtin:
            warning = (f"This looks like {result.builtin}. Fingerino checks that "
                       "first, so this sign may never be recognised. Try a "
                       "different hand shape.")
        else:
            twin = signs.similar_sign(self.library, result.samples)
            if twin:
                warning = (f"This looks a lot like your sign \u201c{twin}\u201d. Fingerino "
                           "won't be able to tell them apart, so neither may work. "
                           "Try a more different shape.")
        self._record_update("review", 1.0, warning=warning)

    def save_sign(self, name: str) -> dict:
        if self._recording is None:
            return {"error": "Record the sign first."}
        if not name.strip():
            return {"error": "Give the sign a name."}
        sign = self.library.add(name, self._recording.samples, self._recording.builtin)
        self.save_signs()
        self.reset_recording()
        self.bridge.signsChanged.emit()
        return {"id": sign.id}

    def save_signs(self) -> None:
        signs.save(self.data_dir, self.library)

    def _on_sign(self, sign_id: str) -> None:
        self.bridge.signFired.emit(sign_id)

    def _on_state(self, paused: bool, hand_seen: bool) -> None:
        self.paused, self.hand_seen = paused, hand_seen
        self._refresh()

    def _on_finished(self, session: Session, error: str | None) -> None:
        if session is not self.session:
            return                       # an older session, already replaced
        self.session = None
        self.paused = self.hand_seen = False
        self.error = error or ""
        if self.record_state == "capturing":
            self._record_update("failed", message="Tracking stopped before the "
                                "recording finished.")
        self.hud.hide()
        self._refresh()
        # Stopped by the Exit gesture, the HUD's X or an error: make sure
        # there is a window on screen saying so.
        self.show_home()

    def stop(self) -> None:
        if self.session is None:
            return
        self.session.stop()
        self.hud.hide()
        # _on_finished completes the switch once the camera is released.

    def toggle_pause(self) -> None:
        if self.session is not None:
            self.session.toggle_pause()

    def _on_hotkey(self) -> None:
        self.toggle_pause()

    def hide_preview(self) -> None:
        self.preview_hidden = True
        self.hud.hide()
        self._refresh()

    def show_preview(self) -> None:
        if self.session is None:
            return
        self.preview_hidden = False
        self.hud.show()
        self._refresh()

    def _keep_hud_on_top(self) -> None:
        if self.hud.isVisible():
            hwnd = int(self.hud.winId())
            if winui.is_buried(hwnd):
                winui.raise_above_all(hwnd)

    # -- Premium -------------------------------------------------------------------

    def entitled(self, feature: str) -> bool:
        """May the add-on offer ``feature``? Yes with a key or in the trial."""
        return self.premium.premium and feature in self.addon.features

    def refresh_premium(self, today: date | None = None) -> None:
        """Work out the plan again (a key entered or removed, a day passed)
        and apply its sign limit. Quiet when nothing changed."""
        new = licence.status(self.licence, self.prefs.trial_started, today or date.today())
        if new == self.premium:
            return
        self.premium = new
        self.library.set_limit(new.sign_limit)
        self.bridge.premiumChanged.emit()
        self.bridge.signsChanged.emit()

    def enter_licence(self, text: str) -> str:
        found = licence.parse(text)
        if isinstance(found, str):
            return found
        if not licence.save(self.data_dir, text):
            return "Fingerino couldn't save the key in its folder. Check the disk isn't full."
        self.licence = found
        self.refresh_premium()
        return ""

    def remove_licence(self) -> None:
        licence.remove(self.data_dir)
        self.licence = None
        self.refresh_premium()

    # -- windows and lifetime -----------------------------------------------------

    def show_home(self) -> None:
        if self.window is None:
            return
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def home_closed(self) -> None:
        if self.session is None:
            self.quit()
            return
        if self.tray is not None and not self._told_about_tray:
            self._told_about_tray = True
            self.tray.showMessage(
                "Fingerino is still running",
                "Tracking continues in the background. Use the tray icon to "
                "open Fingerino or stop it.",
                QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_second_launch(self) -> None:
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.disconnected.connect(conn.deleteLater)
        self.show_home()

    def save(self) -> None:
        settings.save(self.data_dir, self.prefs)

    def save_actions(self) -> None:
        actions.save(self.data_dir, self.registry)

    def quit(self) -> None:
        self.app.quit()

    def run(self) -> int:
        """Show Home, optionally start tracking, and run until Quit."""
        self.show_home()
        if self.prefs.start_on_open:
            self.start()
        code = self.app.exec()
        self.close()
        return code

    def close(self) -> None:
        """Stop tracking and wait for the camera and mouse to be released."""
        session = self.session
        if session is not None:
            session.stop()
            for t in threading.enumerate():
                if t.name == "fingerino-tracking":
                    t.join(timeout=3)
            self.session = None
        if self._hotkey is not None:
            self._hotkey.stop()
        self._topmost.stop()
        self._premium_timer.stop()
        self._server.close()
        if self.tray is not None:
            self.tray.hide()
        self.hud.close()
        if self.window is not None:
            self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()
