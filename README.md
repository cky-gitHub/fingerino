# 🖐️ Fingerino

**Control your computer with webcam hand gestures.** Move the cursor with your
thumb, click by pointing, scroll with two fingers, and run window shortcuts with
a wave — no extra hardware, just your laptop's built-in camera.

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
| **Point** — index out, middle in | Left click (flick the index out) |
| **Two fingers** — index + middle out | Scroll (move the hand up / down) |
| **Flat hand**, swipe **down** | Minimize everything (show desktop) |
| **Flat hand**, swipe **up** | Restore the windows |
| **Flat hand**, swipe **left** | Switch window (Alt+Tab) |
| **Shaka** — thumb + pinky out ("call me") | Open a new AI chat (Alt+Space) |
| **Cross both hands** into an "X", hold | Quit the app |

Rest with your fingers relaxed to stay in plain **Move** mode. The status pill
(top-left) turns green when a hand is tracked; the pill beside it shows the
current mode.

## Install

**Recommended — [`pipx`](https://pipx.pypa.io)** (installs it in its own
isolated environment and puts a `fingerino` command on your PATH):

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
```

`python -m fingerino` works the same way. Press **Esc** (or make the Exit
gesture, or close the window) to quit. Keep your hand inside the on-screen
**control-zone rectangle** — that region maps to your whole screen.

## How it works

| Module | Responsibility |
| --- | --- |
| `main.py` | Camera loop; wires everything together, routes modes. |
| `hand_tracker.py` | Wraps `HandLandmarker` (LIVE_STREAM); returns landmarks per hand. |
| `cursor_controller.py` | Thumb → screen mapping, One Euro smoothing, `pynput` move + scroll. |
| `gesture_detector.py` | `GestureEngine`: posture → mode + click / scroll / swipe / shaka / exit. |
| `system_actions.py` | OS keyboard shortcuts (minimize / restore / Alt+Tab / new chat). |
| `ui_overlay.py` | All HUD drawing (flat, professional theme). |
| `config.py` | Every threshold, the control-zone rect, smoothing + gesture params. |

Each frame, `GestureEngine` classifies the primary hand's posture into a
**mode** and emits discrete events. Every posture test is built from distances
to the wrist, so it's rotation-invariant. Debouncing keeps triggers honest:
clicks fire only on the rising edge of the point posture, are rate-limited, and
won't fire until the finger has been seen released once (so starting or
re-entering the frame mid-gesture is silent). Destructive gestures (Exit, and
the shaka new-chat) must be **held** briefly to guard against accidents.

## Tuning

Everything worth adjusting is in [`fingerino/config.py`](fingerino/config.py)
(do an editable install, `pip install -e .`, so your edits take effect):

- **Cursor feel** — `ONE_EURO_MIN_CUTOFF` (lower = steadier when still),
  `ONE_EURO_BETA` (higher = snappier when moving fast).
- **Reach** — `CONTROL_ZONE_*_MARGIN` shrink/grow the mapped rectangle.
- **Cursor source** — `CURSOR_LANDMARK` (`4` = thumb tip, `8` = index tip).
- **Clicks** — `CLICK_COOLDOWN_S`, `INDEX_EXTEND_MARGIN`.
- **Scroll** — `SCROLL_GAIN` (speed), `SCROLL_INVERT` (flip direction).
- **Flat-hand swipes** — `WAVE_MIN_TRAVEL` / `WAVE_WINDOW_S` (how deliberate),
  `MINIMIZE_ACTION` (`show_desktop` = Win+D, `minimize_all` = Win+M).
- **Shaka** — `AI_CHAT_MODIFIER` + `AI_CHAT_KEY` set the hotkey it sends
  (default **Alt+Space**).

## Platform support

The core — cursor move, click, scroll — works on **Windows, macOS, and Linux**.
The **window-management gestures** (minimize / restore / switch / new chat) send
Windows-style shortcuts and are tuned for Windows; on macOS/Linux, remap them in
`config.py` / `system_actions.py` to your desktop's equivalents. DPI-aware
screen sizing is applied automatically on Windows.

## Troubleshooting

- **"could not open camera 0"** — another app is using the webcam, or it's on a
  different index. Try `fingerino --camera 1` (or 2).
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

## License

[MIT](LICENSE) © cky
