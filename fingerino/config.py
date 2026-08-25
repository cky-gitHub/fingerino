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
# Hold gesture: both palms up and still -> pause / resume every other gesture
# ---------------------------------------------------------------------------
# One flat hand swipes; two of them, held still, are the master switch. While
# paused nothing drives the OS, and the same gesture hands control back with
# exactly the set of gestures that was enabled before.
HOLD_TOGGLE_S = 1.2                 # keep both palms up this long to toggle
HOLD_COOLDOWN_S = 1.0               # min time between toggles
# Debounce for the posture breaking, the same idea as the button trigger's:
# MediaPipe drops the second hand for a frame often enough that resetting the
# countdown on sight would make a one-second hold hard to actually finish.
HOLD_RELEASE_GRACE_S = 0.20
# Palm travel that restarts the countdown, as a fraction of the frame, so a
# two-handed wave or a hand on its way somewhere can never add up to a pause.
HOLD_MAX_DRIFT = 0.07

# ---------------------------------------------------------------------------
# Exit gesture: cross both hands into an "X"
# ---------------------------------------------------------------------------
EXIT_HOLD_S = 0.7                   # hold the X this long to quit (safety)
EXIT_MIN_ANGLE_DEG = 25.0           # the two hands must actually cross, not align

# ---------------------------------------------------------------------------
# UI / theme  — clean, flat, professional (no glow, restrained colour)
# ---------------------------------------------------------------------------
WINDOW_NAME = "Fingerino"

# Shrink the (collapsed) window to this fraction of the screen's area on
# startup and dock it to the top-left corner. The window grows to fit the
# gesture guide when that's open (see UIOverlay.expanded_layout) and shrinks
# back to this size when it closes. Pinning above other windows is
# Windows-only.
WINDOW_SCREEN_FRACTION = 1 / 16
WINDOW_ALWAYS_ON_TOP = True
# How often to renew the topmost claim, in seconds of wall-clock time. Paced
# by real time rather than frame count so it stays responsive even when
# MediaPipe's per-frame cost pulls the loop well under 30 fps -- a frame-count
# cadence would otherwise let another window sit in front for several seconds.
TOPMOST_REASSERT_S = 0.5

# BGR colours (OpenCV order). Neutral greys throughout -- state is carried by
# brightness, not hue. The one exception is the status dot on the camera HUD,
# which stays green/grey because it reports a live condition rather than
# decorating anything.
COLOR_APP_BG = (13, 11, 11)         # window ground behind everything  #0B0B0D
COLOR_PANEL = (22, 19, 19)          # gesture-panel surface            #131316
COLOR_CARD = (30, 26, 26)           # one settings row                 #1A1A1E
COLOR_CARD_HOVER = (40, 35, 35)     # the row under the pointer        #232328
COLOR_PANEL_BORDER = (58, 51, 51)   # hairline border / rule           #33333A
COLOR_DIVIDER = (58, 51, 51)        # hairline rule inside panels      #33333A

COLOR_TEXT = (240, 237, 237)        # row label, panel title           #EDEDF0
COLOR_TEXT_DIM = (163, 155, 155)    # descriptions, section headers    #9B9BA3
COLOR_TEXT_FAINT = (101, 92, 92)    # a disabled row, faint icon tint  #5C5C65

COLOR_STROKE = (125, 116, 116)      # control-zone brackets, idle      #74747D
COLOR_STROKE_ACTIVE = (240, 237, 237)  # control-zone brackets, tracking
COLOR_CURSOR = (240, 237, 237)      # cursor reticle
COLOR_ACCENT = (240, 237, 237)      # was a gold accent; now near-white. Marks
                                     # an active state -- a live drag, scroll
                                     # chevrons, the exit progress bar.
COLOR_OK = (126, 186, 134)          # muted green status dot (live state)
COLOR_IDLE = (101, 92, 92)          # grey status dot

# Toggle switch. "On" is a lit white track with a dark knob, so the armed
# state reads from fill rather than from knob position alone.
COLOR_TOGGLE_TRACK_ON = (240, 237, 237)   # #EDEDF0
COLOR_TOGGLE_KNOB_ON = (22, 19, 19)       # #131316
COLOR_TOGGLE_TRACK_OFF = (49, 43, 43)     # #2B2B31
COLOR_TOGGLE_KNOB_OFF = (125, 116, 116)   # #74747D

PANEL_ALPHA = 0.80                  # opacity of the flat panels
SHADOW_ALPHA = 0.28                 # soft drop shadow behind panels

# ---------------------------------------------------------------------------
# Gesture panel geometry, in design units
# ---------------------------------------------------------------------------
# Every value below is multiplied by the panel scale (see UIOverlay.fs and
# ui_overlay.panel_scale_for), which is worked out once at startup from the
# screen size. The panel therefore keeps its proportions everywhere instead
# of being frozen in raw pixels -- the old fixed layout wanted 1182px of
# height on every display, which overflows a 1080p screen and gets squashed.
PANEL_DESIGN_W = 340                # width the type scale is designed against
PANEL_PAD = 14                      # panel edge padding
PANEL_HEADER_H = 40                 # title + subtitle block
PANEL_SECTION_H = 28                # section label band
PANEL_SECTION_GAP = 12              # between one section and the next
PANEL_CARD_GAP = 4                  # between adjacent rows (Windows 11 spacing)
PANEL_ROW_H_COMFORTABLE = 46        # two-line row: label + description
PANEL_ROW_H_COMPACT = 34            # single-line row, label only
PANEL_ICON = 30                     # gesture sketch, square
PANEL_ICON_GAP = 10                 # sketch to label
PANEL_CARD_PAD = 11                 # row's own left/right padding
PANEL_RADIUS = 4                    # row corner radius
PANEL_TOGGLE_W = 28
PANEL_TOGGLE_H = 16

PANEL_FONT_TITLE = 16               # "Gestures"
PANEL_FONT_SUB = 11                 # "8 of 9 enabled"
PANEL_FONT_SECTION = 12             # "Pointer"
PANEL_FONT_LABEL = 13               # row label
PANEL_FONT_DESC = 11                # row description

# Screen height to leave free below the expanded window (taskbar + breathing
# room) when working out how big the panel is allowed to be.
PANEL_SCREEN_MARGIN = 48
PANEL_SCALE_MIN = 0.85
PANEL_SCALE_MAX = 2.5
# Downscaling a 1024px line drawing to ~37px leaves its ~14px strokes at well
# under a pixel, which washes them out; this multiplies the resized alpha to
# put the weight back without blurring.
PANEL_ICON_ALPHA_GAIN = 1.6

# Gesture guide shown as a full page (Tab to toggle), grouped the way a
# settings page groups related options rather than as one flat run of nine.
# Each row is (icon id, what it does, how you do it) -- the icon id looks up
# both the sketch in assets/tutorial-gestures/ (see
# UIOverlay._GESTURE_ICON_FILES) and the per-gesture enabled/disabled toggle
# state (see main.py). The descriptions restate the behaviour configured
# above, so keep them in step with e.g. DRAG_HOLD_S.
GESTURE_GROUPS = (
    ("Pointer", (
        ("thumb", "Move cursor", "Thumb tip steers the pointer"),
        ("point", "Click", "Point with your index finger"),
        ("point_hold", "Drag", "Hold the point for half a second"),
        ("two_finger", "Scroll", "Index and middle finger, move up or down"),
    )),
    ("Windows", (
        ("flat_down", "Minimize", "Open palm, swipe down"),
        ("flat_up", "Restore", "Open palm, swipe up"),
        ("flat_left", "Switch window", "Open palm, swipe left"),
    )),
    ("Shortcuts", (
        ("shaka", "New chat", "Thumb and pinky out"),
        ("cross", "Exit", "Cross both hands into an X"),
    )),
    ("Session", (
        ("both_flat", "Hold", "Both palms up to pause all"),
    )),
)

# Flat (icon id, label) view of GESTURE_GROUPS in display order. The gesture
# gating and the per-gesture toggle state iterate over this, so the grouping
# above stays purely a presentation concern.
GESTURE_TUTORIAL = tuple(
    (icon, label) for _, rows in GESTURE_GROUPS for icon, label, _ in rows
)

# Feedback timings (seconds).
CLICK_FLASH_S = 0.16
TOAST_S = 1.2
