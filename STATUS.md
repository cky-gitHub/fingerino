# Fingerino status

Last updated 2026-11-07. Read this first when picking the work up.

## Where things stand

Fingerino is a **hand-sign shortcut tool**: signs like the shaka trigger
actions, anyone can record a new sign without code, and the cursor is an
optional module that is off by default.

- **`main`** has everything below; there are no open feature branches.
  (`ccr-2c0750c7-uhrknd` and `claude/apollo-rocket-controls-igrhf0` on the
  remote were not made in this work; leave them alone unless the owner says.)
- **Released:** v0.2.1 (2026-11-07) is the latest release: v0.2.0 plus the
  MediaPipe telemetry fix, cut from the `v0.2.0` tag, MIT licence. Nothing
  from slices 1 to 5 or the redesign has been released yet; the next release
  will be v0.3.0 under FCL-1.0-MIT.
- **Done on `main` since v0.2.0** (PRs #8, #9, #10):
  1. Signs split from actions (`fingerino/actions.py` registry).
  2. Cursor optional, off by default for everyone, upgraders included.
  3. Bindable actions: hotkey, media key, open app, open URL/file, run
     command, plus the built-ins. Edited in Home, saved to `actions.json`.
  4. Sign matcher (`fingerino/sign_matcher.py`).
  5. Recording signs in Home (`fingerino/signs.py`, `signs.json`): record,
     name, bind, rename, switch off, delete, "Recognised" feedback.
  - Exit is **crossed index and middle fingers** (`is_crossed_fingers`,
    `EXIT_CROSS_RATIO`); two crossed hands weren't recognised on a real camera.
  - "Try it" in the action editor arms a trial: only that sign acts, with the
    unsaved action, until the editor closes; the HUD shows a thin green frame
    and a 450 ms gleam per recognition (`TRIAL_*`, `COLOR_TRIAL`).
  - Gestures are silent from the record countdown until the action editor
    closes (`Shell.hold_gestures`, per reason "record" / "editor").
  - Design review (apple-design skill, installed globally, not vendored):
    theme-aware colours (>= 4.5:1, tests/test_home_design.py), rows titled by
    the sign, grouped sections, Windows text size, editable pause shortcut,
    Theme setting (system / light / dark), skeleton setting, Quit on Home,
    "Make your own sign" on Home and first on Gestures. Only built-in signs
    have a picture; custom signs have none, by decision.
  - Licence: FCL-1.0-MIT (official text from fcl.dev); v0.1.0, v0.2.0 and the
    v0.2.1 hotfix stay MIT.
  - MediaPipe pinned to <= 0.10.33 in `pyproject.toml` and
    `requirements-build.txt`, guarded by `tests/test_no_telemetry.py` (see
    Decisions).
- **Tests:** 313 collected; all pass with every dependency installed
  (1 skipped). CI: Linux lint/types/pure tests, Windows full suite and
  `--selftest`.
- **Camera-checked on Windows (2026-11-05/07):** cursor off by default, shaka
  rebound to a link, recording and binding a sign, recording warnings, "Try
  it", crossed-fingers Exit, the redesigned Home. **Not yet checked:** Hold
  (both palms), anything on macOS, recognition on MediaPipe 0.10.33 beyond a
  quick try.
- **Security check (2026-11-07):** `pip-audit` clean in both repos; Gitleaks
  found no secrets in either history; Semgrep and `/security-review` found no
  exploitable issue since v0.2.0. Follow-ups are next steps 1 and 6 below.
- **Private repo** `cky-gitHub/fingerino_premium`: skeleton only (package,
  closed licence, README with the architecture and plan, Linux-only CI).

## What needs doing next

1. **Finish the security follow-ups.** Branch `ci/pin-actions`: GitHub
   Actions pinned to commit SHAs in both repos, and `.github/dependabot.yml`
   (actions weekly, pip weekly with MediaPipe ignored on purpose). The owner
   switches on, in Settings → Code security: Dependabot alerts and security
   updates, secret scanning with push protection, CodeQL "Default" setup
   (Python and Actions), private vulnerability reporting; and in Settings →
   Branches a rule for `main` (require a PR and passing CI). On the private
   repo only Dependabot alerts are free; use Semgrep and Gitleaks locally.
2. **Premium foundation, in this public repo.**
   - An add-on hook: at start-up Fingerino looks for an installed
     `fingerino_premium` package and asks which features it provides. The
     free app must work fully without it.
   - An offline licence check: a signed key file verified locally (no network
     request; the README's privacy promise stands). Pick the signature scheme
     and the payment provider (Lemon Squeezy, Paddle or Gumroad; compare them
     first and let the owner choose).
   - The free tier as decided (see Decisions): 1 custom sign, a 14-day
     Premium trial for new installs, extra signs kept but switched off
     afterwards with "Unlock with Premium", a short note at the limit. The
     limit is licence-key functionality in the public code.
   - Tests for all of it, camera-free.
3. **Premium features, in `fingerino_premium`.** Wispr Flow first: a new
   action kind "hold a key while the sign is held" (press when the sign
   starts, release when it ends) so a shaka holds Wispr's push-to-talk key.
   Then the MCP server, which needs its own security design (what it may do,
   confirmation for risky actions, local only) before any code.
4. **Slice 6, false triggers.** A dry run that logs matches without acting
   (build on `engine.Options(drive=False)`), then tune on the owner's camera.
   Includes the swipe report: slow long swipes work, short fast ones don't
   (proposal: `WAVE_MIN_TRAVEL` 0.22 → 0.16, `WAVE_WINDOW_S` 0.5 → 0.35, a
   0.1 s grace for a dropped open-hand frame; measure first). HUD swipe
   arrows are weak. Target: five custom signs cause fewer than one false
   trigger per hour of desk use.
5. **Release v0.3.0** once 1 and 2 are in and the camera checks above pass
   (Hold, macOS if a Mac is available). First FCL release.
6. **Before slice 8 (sign packs) ships:** `open` and `open_app` actions are
   not approval-gated (only `command` is), so imported ones must be gated or
   limited to http/https; run every imported action through `make_action`;
   show imported names with `textFormat: Text.PlainText`.
7. **Later slices.** 7: always-on mode (lower frame rate with the cursor off,
   recover when a video call takes the camera). 8: sign packs (see 6).
   9: launch (README around signs, clip, report accuracy and false-trigger
   rate).

Waiting on the owner: pictures for Exit (crossed fingers) and Swipe right,
ideally every gesture picture as SVG in a dark (#6c9cbd) and light (#2f5f80)
stroke, since the PNGs are 2.85:1 on light cards; a Mac for the macOS check;
the payment provider.

## Decisions already made

- Signs and actions are separate concepts, stored separately
  (`signs.json` and `actions.json`).
- Non-coders first: record a sign in Home, no training step.
- Matching: normalise landmarks (aspect ratio, wrist origin, hand size,
  left hand mirrored to right), nearest neighbour over samples, reject weak
  or ambiguous matches. Shape is compared upright; orientation separately, so
  thumbs up and thumbs down stay distinct.
- Built-in signs (shaka, swipes) and Hold/Exit are checked before custom
  signs, so a recorded sign can't take them over. With the cursor on,
  pointing stays a click.
- Cursor off by default, for upgraders too.
- Commands only run when approved; anything typed in Home is approved.
  Opening apps, files and links never goes through a shell.
- `actions.json` edited by another program: no "re-confirm on outside
  change". Anything that can write that file already runs as the user, so it
  would protect nothing; the real boundary is sign-pack import (next step 6).
- Open core (2026-11-06): this repo stays public under FCL-1.0-MIT (each
  version becomes MIT two years after release; forbids competing products
  and getting around licence-key checks). Paid features live in the private
  `cky-gitHub/fingerino_premium` and ship in the same official build, locked
  behind an offline-checked licence key.
- Free tier (2026-11-07): 1 custom sign plus every built-in sign. New
  installs get a 14-day Premium trial; when it ends, extra signs stay but are
  switched off with "Unlock with Premium", never deleted. Reaching the limit
  shows a short note on what Premium adds, not a hard block. The trial start
  is stored locally and can be reset; that is accepted. Premium: about 20
  custom signs, the Wispr Flow hold, the MCP server.
- MediaPipe telemetry (2026-11-07): Google's PyPI builds from 0.10.35 on
  contain a "Clearcut" uploader to play.googleapis.com with no off switch
  (google-ai-edge/mediapipe#6291). v0.1.0 and v0.2.0 shipped it; v0.2.1
  removed it and says so in its release notes and the README. Stay on
  0.10.33 until Google offers a way to turn it off; Dependabot ignores
  MediaPipe for this reason.
- Commits use the owner's GitHub no-reply address (set per repo).
- Still open: Exit doesn't work while paused (unchanged from v0.2.0).

## Keep intact

README privacy promises (video stays in memory, nothing recorded or
uploaded, no telemetry, the model download is the only network request);
every file Fingerino writes listed in the README; the single button-release
path, `DRAG_MAX_S`, held confirmation, Hold and Exit; the
`mediapipe<=0.10.33` pin and `tests/test_no_telemetry.py`; thresholds in
`config.py`; ruff, mypy and pytest passing; Windows and macOS support
without breaking the Linux source install.

## Working on it

```bash
pip install -e ".[dev]"
ruff check fingerino packaging tests && mypy && pytest -q
```

- Camera-free test helpers: `tests/landmarks.py` (synthetic hands, recordings
  with drift and jitter) and `tests/sessionkit.py` (runs the real
  `engine.Session` with a fake camera, tracker, mouse and clock).
- Screenshots without a screen: render Home offscreen with
  `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:/Windows/Fonts`, then
  `window.grabWindow()`. Offscreen can't show light mode; the real Windows
  platform can (`styleHints().setColorScheme`).
- Headless Linux needs `QT_QPA_PLATFORM=offscreen` and
  `PYNPUT_BACKEND=dummy`, plus system packages `libegl1 libgl1 libgles2
  libxkbcommon0 libfontconfig1 libdbus-1-3` for Qt and MediaPipe.
- Releasing, including hotfixing an older release from its tag:
  `docs/releasing.md`.
- The `Cannot read property ... of null` QML messages at test teardown are
  noise from the window closing.
- `Notes.md` is an older phase plan from before the sign direction.
