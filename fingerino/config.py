"""Central configuration for the hand-tracking mouse.

Everything tunable lives here so the behavioural feel can be adjusted
without touching the logic in the other modules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
# Mirror the frame so moving your hand right moves the cursor right.
FLIP_HORIZONTAL = True

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
MODEL_FILENAME = "hand_landmarker.task"
NUM_HANDS = 2                       # 2 so the cross-hands "X" exit can be seen
MIN_HAND_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5

# ---------------------------------------------------------------------------
# Control zone
# ---------------------------------------------------------------------------
# The rectangle inside the camera frame that maps to the whole screen.
# Expressed as fractions of the frame (0..1). The central region is used
# because tracking degrades near the edges and reaching there is awkward.
CONTROL_ZONE_X_MARGIN = 0.20   # trims 20% from left and right -> central 60%
CONTROL_ZONE_Y_MARGIN = 0.20   # trims 20% from top and bottom -> central 60%

# ---------------------------------------------------------------------------
# One Euro Filter (cursor smoothing)
# ---------------------------------------------------------------------------
# Lower min_cutoff  -> more smoothing at low speed (less jitter when still).
# Higher beta       -> less lag when moving fast (more responsive).
ONE_EURO_MIN_CUTOFF = 1.0
ONE_EURO_BETA = 0.02
ONE_EURO_D_CUTOFF = 1.0

# ---------------------------------------------------------------------------
# Cursor source
# ---------------------------------------------------------------------------
# Which hand landmark drives the cursor. 4 = thumb tip, 8 = index fingertip.
CURSOR_LANDMARK = 4

# ---------------------------------------------------------------------------
# Finger posture
# ---------------------------------------------------------------------------
# A finger counts as "extended" when its tip is farther from the wrist than
# its PIP joint by this margin (fraction of hand size); the margin is a
# deadzone so a half-curled finger doesn't flicker between states.
FINGER_EXTEND_MARGIN = 0.08
# The thumb travels sideways, so it gets its own (looser) margin.
THUMB_EXTEND_MARGIN = 0.02

# ---------------------------------------------------------------------------
# Click + drag gesture: point (index out, middle in)
# ---------------------------------------------------------------------------
INDEX_EXTEND_MARGIN = 0.10          # how firmly the index must straighten
CLICK_COOLDOWN_S = 0.30             # min time between button actions

# A point that ends before this is an ordinary click and never puts the button
# down -- so the cursor drift of the hand changing shape can't smear a click
# into a stray one-pixel drag. Keep the index out for longer and the button
# goes down and stays down, which drags exactly like a held mouse button.
DRAG_HOLD_S = 0.50                  # how long to hold the point before it drags
# Debounce for letting go, with a longer window once the button is actually
# down: a click arriving a frame late is cheap, dropping a drag halfway is not.
CLICK_RELEASE_GRACE_S = 0.06        # ~2 frames -- swallows a mis-landmarked one
DRAG_RELEASE_GRACE_S = 0.15
# Safety valve: never hold the button longer than this, whatever the tracker
# thinks it sees. A stuck mouse button is far worse than a lost drag.
DRAG_MAX_S = 20.0

# ---------------------------------------------------------------------------
# Scroll gesture: two fingers (index + middle out)
# ---------------------------------------------------------------------------
# Wheel steps per full-frame vertical hand travel; higher = faster scroll.
SCROLL_GAIN = 42.0
SCROLL_INVERT = False               # flip if up/down feels backwards

# ---------------------------------------------------------------------------
# Flat-hand swipes (open palm): down = minimize, up = restore, left = Alt+Tab
# ---------------------------------------------------------------------------
WAVE_WINDOW_S = 0.5                 # look-back window for the swipe
WAVE_MIN_TRAVEL = 0.22              # min dominant-axis travel (fraction of frame)
SWIPE_COOLDOWN_S = 0.8             # min time between flat-hand swipe actions
# "show_desktop" -> Win+D (toggle desktop) ; "minimize_all" -> Win+M / Win+Shift+M.
MINIMIZE_ACTION = "show_desktop"

# ---------------------------------------------------------------------------
# Shaka / "call me" sign (thumb + pinky out) -> open a new AI chat
# ---------------------------------------------------------------------------
SHAKA_HOLD_S = 0.25                 # hold the sign this long before it fires
SHAKA_COOLDOWN_S = 1.5
# Hotkey sent to summon the chat app (ChatGPT / Claude desktop quick-launcher).
AI_CHAT_MODIFIER = "alt"            # alt | ctrl | cmd | shift
AI_CHAT_KEY = "space"              # e.g. "space", or a letter like "j"

# ---------------------------------------------------------------------------
# Exit gesture: cross both hands into an "X"
# ---------------------------------------------------------------------------
EXIT_HOLD_S = 0.7                   # hold the X this long to quit (safety)
EXIT_MIN_ANGLE_DEG = 25.0           # the two hands must actually cross, not align

# ---------------------------------------------------------------------------
# UI / theme  — clean, flat, professional (no glow, restrained colour)
# ---------------------------------------------------------------------------
WINDOW_NAME = "Fingerino"

# Shrink the window to this fraction of the screen's area on startup and dock
# it to the top-left corner. Pinning above other windows is Windows-only.
WINDOW_SCREEN_FRACTION = 1 / 16
WINDOW_ALWAYS_ON_TOP = True
# How often to renew the topmost claim, in seconds of wall-clock time. Paced
# by real time rather than frame count so it stays responsive even when
# MediaPipe's per-frame cost pulls the loop well under 30 fps -- a frame-count
# cadence would otherwise let another window sit in front for several seconds.
TOPMOST_REASSERT_S = 0.5

# BGR colours (OpenCV order). Cool neutral greys + one restrained accent.
COLOR_PANEL = (22, 20, 18)          # near-black panel fill
COLOR_PANEL_BORDER = (74, 68, 62)   # hairline panel border
COLOR_STROKE = (104, 100, 96)       # muted grey (control zone, inactive)
COLOR_STROKE_ACTIVE = (198, 178, 148)  # accent-tinted (control zone, tracking)
COLOR_TEXT = (242, 241, 240)
COLOR_TEXT_DIM = (158, 154, 150)
COLOR_TEXT_FAINT = (116, 112, 108)  # section labels, keycap glyphs
COLOR_CURSOR = (242, 241, 240)      # near-white cursor mark
COLOR_ACCENT = (196, 162, 112)      # muted steel blue, used sparingly
COLOR_OK = (126, 186, 134)          # muted green status dot
COLOR_IDLE = (110, 108, 112)        # grey status dot
COLOR_DIVIDER = (52, 48, 44)        # hairline rule inside panels

PANEL_ALPHA = 0.80                  # opacity of the flat panels
SHADOW_ALPHA = 0.28                 # soft drop shadow behind panels

# Gesture legend shown in the collapsible side menu (Tab to toggle).
GESTURE_LEGEND = (
    ("Thumb", "Move cursor"),
    ("Point", "Click"),
    ("Hold point", "Drag"),
    ("Two fingers", "Scroll"),
    ("Swipe down", "Minimize"),
    ("Swipe up", "Restore"),
    ("Swipe left", "Switch window"),
    ("Shaka", "New chat"),
    ("Cross hands", "Exit"),
)

# Feedback timings (seconds).
CLICK_FLASH_S = 0.16
TOAST_S = 1.2
