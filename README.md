# 🖐️ Fingerino

**Control your computer with webcam hand gestures.** Move the cursor with your
thumb, click by pointing, drag by holding the point, scroll with two fingers,
and run window shortcuts with a wave — no extra hardware, just your laptop's
built-in camera.

![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-lightgrey)

Built on MediaPipe's `HandLandmarker` (live-stream, two hands), OpenCV for
capture + a clean HUD, `pynput` for cursor/scroll/keyboard control, and a One
Euro Filter so the cursor glides instead of shaking.

---

## Gestures

| Gesture | Action |
| --- | --- |
| **Thumb** tip | Move the cursor |
| **Point** — index out, middle in | Left click (flick the index out and back) |
| **Hold the point** ~0.5s | Drag — the button goes down and stays down |
| **Two fingers** — index + middle out | Scroll (move the hand up / down) |
| **Flat hand**, swipe **down** | Minimize everything (show desktop) |
| **Flat hand**, swipe **up** | Restore the windows |
| **Flat hand**, swipe **left** | Switch window (Alt+Tab) |
| **Shaka** — thumb + pinky out ("call me") | Open a new AI chat (Alt+Space) |
| **Both palms up**, held still ~1s | Hold: pause every gesture — again to resume |
| **Cross both hands** into an "X", hold | Quit the app |

A quick point is a plain click and holds nothing down — so the cursor drift of
your hand changing shape can't smear it into a stray drag. Keep the index out
for about half a second and the reticle's ring fills round like a clock; once
it closes, the button is down and stays down until you relax the finger, so
you can drag a file, a slider or a selection. The reticle turns gold while the
button is held.

Rest with your fingers relaxed to stay in plain **Move** mode. The status pill
(top-left) turns green when a hand is tracked; the pill beside it shows the
current mode.

**Hold** is the master switch, for when you want your hands back: raise both
palms, keep them still for about a second, and everything stops driving the
computer — the pill goes grey and reads *Paused*. Do it again and control comes
back with exactly the gestures that were switched on before; pausing never
changes what you picked in the guide. One open hand still swipes as usual, so
the two never collide, and the countdown restarts if your palms drift, so a
two-handed wave can't pause you by accident.

## Download

Grab the installer for your machine from the
[latest release](https://github.com/cky-gitHub/fingerino/releases/latest) —
no Python, no terminal, nothing else to install.

| Your machine | File | What to do |
| --- | --- | --- |
| Windows 10 / 11 | `Fingerino-*-windows-x64-Setup.exe` | Run it. Fingerino lands in your Start menu. |
| Mac — Apple Silicon | `Fingerino-*-macos-arm64.dmg` | Open it, drag Fingerino to Applications. |
| Mac — Intel | `Fingerino-*-macos-intel.dmg` | Open it, drag Fingerino to Applications. |

Which Mac do you have? **Apple menu › About This Mac** — "Apple M-something" is
Apple Silicon, "Intel" is Intel.

### The first launch

These builds are not code-signed (a certificate costs real money per year), so
your OS will stop you exactly once:

- **Windows** — SmartScreen shows a blue "Windows protected your PC" box.
  Click **More info**, then **Run anyway**.
- **macOS** — the app is blocked as being from an unidentified developer. Open
  **System Settings › Privacy & Security**, scroll to the bottom, and press
  **Open Anyway** next to Fingerino.

Then grant the permissions it asks for:

- **Camera** — both platforms, prompted on first launch. Nothing is recorded
  and no video leaves your machine.
- **Accessibility** — **macOS only**, and Fingerino cannot move your cursor
  without it. It shows you a dialog with a shortcut to the right settings
  page; switch Fingerino on there, then start it again.

> **Windows Smart App Control.** If Windows refuses to run the app at all —
> "An Application Control policy has blocked this file", with no *Run anyway*
> button — that is Smart App Control, which is stricter than SmartScreen and
> only trusts signed, established software. Turning it off is permanent (you
> can't turn it back on without reinstalling Windows), so the better route is
> to install from source instead, below.

## Other ways to install

**[`pipx`](https://pipx.pypa.io)** (installs it in its own isolated
environment and puts a `fingerino` command on your PATH):

```bash
pipx install git+https://github.com/cky-gitHub/fingerino.git
fingerino
```

**With `pip`:**

```bash
pip install git+https://github.com/cky-gitHub/fingerino.git
fingerino
```

**From source** (best if you want to tweak the tuning in `fingerino/config.py`):

```bash
git clone https://github.com/cky-gitHub/fingerino.git
cd fingerino
pip install -e .
fingerino
```

Python **3.10+**. First launch downloads the hand-landmark model (~7 MB) into a
per-user cache and reuses it after that. You'll be asked for **camera
permission** the first time.

> Not on PyPI yet — once it is, `pipx install fingerino` will be all you need.

## Usage

```bash
fingerino            # clean HUD, controls the OS
fingerino --debug    # also draw the raw skeleton + FPS counter
fingerino --no-move  # track & show the HUD without driving the OS (safe test mode)
fingerino --camera 1 # pick a different camera index
fingerino --selftest # check the install (no camera, no window), then exit
```

`python -m fingerino` works the same way. Press **Esc** (or make the Exit
gesture, or close the window) to quit. Keep your hand inside the on-screen
**control-zone rectangle** — that region maps to your whole screen.

## How it works

| Module | Responsibility |
| --- | --- |
| `main.py` | Camera loop; wires everything together, routes modes. |
| `hand_tracker.py` | Wraps `HandLandmarker` (LIVE_STREAM); returns landmarks per hand. |
| `cursor_controller.py` | Thumb → screen mapping, One Euro smoothing, `pynput` move + button + scroll. |
| `gesture_detector.py` | `GestureEngine`: posture → mode + click / drag / scroll / swipe / shaka / hold / exit. |
| `system_actions.py` | OS keyboard shortcuts (minimize / restore / Alt+Tab / new chat). |
| `ui_overlay.py` | All HUD drawing (flat, professional theme). |
| `config.py` | Every threshold, the control-zone rect, smoothing + gesture params. |
| `winui.py` | Windows window chrome: icon, taskbar identity, always-on-top. |
| `macui.py` | macOS Accessibility permission gate + error dialogs. |
| `branding.py` | Draws the app icon (no binary asset in the repo). |

Each frame, `GestureEngine` classifies the primary hand's posture into a
**mode** and emits discrete events. Every posture test is built from distances
to the wrist, so it's rotation-invariant. Debouncing keeps triggers honest: a
point is resolved when it *ends* — short means a click, longer than
`DRAG_HOLD_S` means the button goes down for a drag — it's rate-limited, and
nothing fires until the finger has been seen released once (so starting or
re-entering the frame mid-gesture is silent). Letting go is debounced too, with
a longer grace once the button is actually down, so a mis-landmarked frame
can't drop a drag halfway. The button is released from a single path that also
runs when the hand leaves the frame and on every shutdown, and it never stays
down longer than `DRAG_MAX_S`. Destructive gestures (Exit, and the shaka
new-chat) must be **held** briefly to guard against accidents.

Two-hand postures are resolved before anything else: crossed hands are Exit,
two open palms are Hold, and both shut the one-hand paths out entirely — which
is why raising both hands to pause can't wave a window away on the way up. Hold
is a mode rather than a mass toggle, so the per-gesture switches in the guide
are left untouched and resuming restores exactly the set that was live.

## Tuning

Everything worth adjusting is in [`fingerino/config.py`](fingerino/config.py)
(do an editable install, `pip install -e .`, so your edits take effect):

- **Cursor feel** — `ONE_EURO_MIN_CUTOFF` (lower = steadier when still),
  `ONE_EURO_BETA` (higher = snappier when moving fast).
- **Reach** — `CONTROL_ZONE_*_MARGIN` shrink/grow the mapped rectangle.
- **Cursor source** — `CURSOR_LANDMARK` (`4` = thumb tip, `8` = index tip).
- **Clicks + drag** — `DRAG_HOLD_S` (how long a point must be held before it
  becomes a drag instead of a click), `CLICK_COOLDOWN_S`,
  `INDEX_EXTEND_MARGIN`, `CLICK_RELEASE_GRACE_S` / `DRAG_RELEASE_GRACE_S` (how
  forgiving each is about dropped frames), `DRAG_MAX_S`.
- **Scroll** — `SCROLL_GAIN` (speed), `SCROLL_INVERT` (flip direction).
- **Flat-hand swipes** — `WAVE_MIN_TRAVEL` / `WAVE_WINDOW_S` (how deliberate),
  `MINIMIZE_ACTION` (`show_desktop` = Win+D, `minimize_all` = Win+M).
- **Shaka** — `AI_CHAT_MODIFIER` + `AI_CHAT_KEY` set the hotkey it sends
  (default **Alt+Space**).
- **Hold** — `HOLD_TOGGLE_S` (how long both palms must be up), `HOLD_MAX_DRIFT`
  (how still they must be), `HOLD_COOLDOWN_S`.

## Platform support

The core — cursor move, click, drag, scroll — works on **Windows, macOS, and
Linux**.
Installers are published for Windows and macOS; Linux is a source install.

The **window-management gestures** send different keys per platform, in
[`system_actions.py`](fingerino/system_actions.py):

| Gesture | Windows | macOS |
| --- | --- | --- |
| Minimize / restore | Win+D (toggle desktop) | F11 (Show Desktop, toggles) |
| Switch window | Alt+Tab | Cmd+Tab |
| New chat (shaka) | Alt+Space | Alt+Space (Option+Space) |

On macOS, F11 only works if **Show Desktop** is still bound to it in System
Settings › Keyboard › Keyboard Shortcuts › Mission Control. Linux sends the
Windows set; remap it in `system_actions.py` for your desktop.

macOS also needs **Accessibility** permission before any of this works — see
[The first launch](#the-first-launch). DPI-aware screen sizing is applied
automatically on Windows.

## Troubleshooting

- **It won't start / the window never appears** — run `fingerino --selftest`
  (or `Fingerino.exe --selftest`). It loads everything except the camera and
  writes a report to `%LOCALAPPDATA%\fingerino\selftest.txt` on Windows,
  `~/Library/Caches/fingerino/selftest.txt` on macOS. Attach that to an issue.
- **"could not open camera 0"** — another app is using the webcam, or it's on a
  different index. Try `fingerino --camera 1` (or 2).
- **macOS: it tracks my hand but the cursor doesn't move** — Accessibility
  permission is missing. System Settings › Privacy & Security › Accessibility,
  switch Fingerino on, then restart it. Toggling it off and on again fixes the
  case where macOS remembers a stale entry from an older build.
- **Cursor is jittery** — raise `ONE_EURO_MIN_CUTOFF`. **Laggy when moving
  fast** — raise `ONE_EURO_BETA`.
- **Clicks misfire** — make the point cleaner (index out, other fingers in), or
  raise `INDEX_EXTEND_MARGIN`.
- **Shaka doesn't open a chat** — Alt+Space only works if your ChatGPT/Claude
  desktop app has registered it as a global quick-launcher; otherwise set
  `AI_CHAT_MODIFIER` / `AI_CHAT_KEY` to whatever your app uses.
- **Best results** with even, front-on lighting and your hands well inside the
  control-zone rectangle.

## Development

```bash
git clone https://github.com/cky-gitHub/fingerino.git
cd fingerino
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e .
fingerino --debug
```

The `--debug` flag overlays the raw skeleton, FPS, and current mode — handy for
tuning thresholds.

## Building the installers

```bash
pip install -e ".[build]"
python packaging/build.py            # current platform, into dist/release/
python packaging/build.py --console  # same, but with a console for tracebacks
```

PyInstaller can't cross-compile, so each target has to be built on its own
machine — that's what [`.github/workflows/release.yml`](.github/workflows/release.yml)
is for. Push a tag and it builds all three and publishes a release:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

| File | What it does |
| --- | --- |
| [`packaging/build.py`](packaging/build.py) | The whole build: model, icons, PyInstaller, installer. |
| [`packaging/fingerino.spec`](packaging/fingerino.spec) | What goes in the bundle, and the macOS `Info.plist`. |
| [`packaging/launcher.py`](packaging/launcher.py) | Entry script (a frozen app can't use `__main__.py`). |
| [`packaging/fingerino.iss`](packaging/fingerino.iss) | Inno Setup script for the Windows installer. |
| [`packaging/entitlements.plist`](packaging/entitlements.plist) | Hardened-runtime entitlements, for signed Mac builds. |

Windows installers need [Inno Setup](https://jrsoftware.org/isdl.php); without
it the build still produces the portable `.zip`.

### Code signing

Unsigned builds work, but every user pays for it once — a SmartScreen warning
on Windows, a Gatekeeper block on macOS — and Windows Smart App Control
refuses them outright, with no override. If Fingerino is going out to people
who aren't going to read instructions, signing is what fixes that:

- **macOS** — a Developer ID certificate ([Apple Developer
  Program](https://developer.apple.com/programs/), $99/year). Set
  `APPLE_DEVELOPER_ID` and `APPLE_NOTARY_PROFILE` (from `xcrun notarytool
  store-credentials`) and `build.py` signs, hardens, notarizes and staples the
  `.dmg` on its own. Nothing else changes.
- **Windows** — an Authenticode certificate. [Azure Trusted
  Signing](https://azure.microsoft.com/products/trusted-signing) is the cheap
  route for individuals; a traditional OV certificate costs a few hundred a
  year and still needs to build reputation before SmartScreen goes quiet.
  Sign `dist/Fingerino/Fingerino.exe` and the finished `Setup.exe`.

## License

[MIT](LICENSE) © cky
