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
# Click gesture: point (index out, middle in)
# ---------------------------------------------------------------------------
INDEX_EXTEND_MARGIN = 0.10          # how firmly the index must straighten
CLICK_COOLDOWN_S = 0.30             # min time between clicks

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

# BGR colours (OpenCV order). Neutral greys + one restrained steel-blue accent.
COLOR_PANEL = (26, 24, 22)          # near-black panel fill
COLOR_PANEL_BORDER = (58, 55, 52)   # hairline panel border
COLOR_STROKE = (120, 118, 112)      # muted grey (control zone, inactive)
COLOR_STROKE_ACTIVE = (206, 204, 200)  # near-white grey (control zone, tracking)
COLOR_TEXT = (234, 233, 231)
COLOR_TEXT_DIM = (150, 148, 146)
COLOR_CURSOR = (238, 236, 234)      # near-white cursor mark
COLOR_ACCENT = (176, 148, 108)      # muted steel blue, used sparingly
COLOR_OK = (120, 176, 128)          # muted green status dot
COLOR_IDLE = (120, 118, 122)        # grey status dot

PANEL_ALPHA = 0.62                  # opacity of the flat panels

# Concise gesture legend.
HINT_TEXT = ("Thumb: move    Point: click    Two fingers: scroll    "
             "Flat swipe  down/up/left = min/restore/switch    "
             "Shaka: new chat    Cross hands: exit")

# Feedback timings (seconds).
CLICK_FLASH_S = 0.16
TOAST_S = 1.2
