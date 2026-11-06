# Fingerino status

Last updated 2026-11-05. Read this first when picking the work up.

## Where things stand

Fingerino is changing from a webcam mouse into a **hand-sign shortcut tool**:
signs like the shaka trigger actions, anyone can record a new sign without
code, and the cursor is an optional module that is off by default.

- **Branch:** `signs-core`, open as [PR #8](https://github.com/cky-gitHub/fingerino/pull/8)
  into `main`. Not merged. Mergeable, CI green (Linux lint/types/pure tests,
  Windows full suite + `--selftest`).
- **Done on that branch** (one commit per slice, slice numbers from the plan
  below):
  1. Signs split from actions (`fingerino/actions.py` registry).
  2. Cursor optional, off by default for everyone, upgraders included.
  3. Bindable actions: hotkey, media key, open app, open URL/file, run
     command, plus the built-ins. Edited in Home, saved to `actions.json`.
  4. Sign matcher (`fingerino/sign_matcher.py`), no UI.
  5. Recording signs in Home (`fingerino/signs.py`, `signs.json`): record,
     name, bind, rename, switch off, delete, "Recognised" feedback.
- **Tests:** 310 pass, 1 skipped, with all dependencies (the dependency-free
  job runs fewer). First real-camera check done on Windows, see below.

## What needs doing next

1. **Camera check, then merge PR #8.** Windows, 2026-11-05, done so far
   (macOS still to do):
   - PASS: cursor off by default on a clean profile, mouse never moves.
   - PASS: shaka rebound to a Spotify link opens it, once, ~0.5 s hold.
   - PASS: recorded sign (thumbs up) named, bound, fires, flashes "Recognised".
   - PASS: shaka / duplicate warnings show. Two follow-ups from this, both
     fixed on this branch: gestures now stay silent from the record
     countdown to the end of the dialog (`Session.hold_gestures`), and a
     saved sign that may never fire gets a quiet "!" with a hover note.
   - HUD arrows for swipes are weak (reported, not changed).
   - Sign cards overflowed in a narrow window, hiding Delete and the switch
     (the "UI a bit messed up" report). Fixed: the card's control slot keeps
     its width, and Rename/Delete moved into a "⋯" menu. Warning yellow is
     now one shared colour (`warnColor` in Home.qml).
   - Delete never opened its confirmation: in `deleteDialog.ask()` the
     bare name `signName` resolved to the record dialog's text field id
     (ids win over properties), so the assignment threw. Fixed and covered
     by a test that drives the real dialog and fails on any QML error.
   - The action editor's five-button row was wider than the dialog and
     pushed the fields past its edge. Now Try it, a "⋯" menu (Reset to
     original, Do nothing), Cancel and Save; the column is capped to the
     dialog's width.
   - "Try it" in the action editor now arms a trial: making the sign runs
     the unsaved action and nothing else acts until the editor closes
     (`Session.set_trial`, `Shell.start_trial`). It used to run the action
     once from Home, which didn't show whether the sign triggers it.
   - Gestures are now silent from the record countdown until the action
     editor closes, with no gap at the hand-over (Home holds per reason:
     "record", "editor"; `Shell.hold_gestures`). The editor also holds when
     opened on its own. Covered by a test that drives the real QML flow.
   - "Try it" feedback on the HUD: once the sign is recognised a constant
     thin green frame stays until the editor closes, and each recognition
     sends a 450 ms gleam from it into the picture (80 ms rise, 370 ms
     ease-out; NN/g's 200-500 ms range). `TRIAL_*` and `COLOR_TRIAL` in
     config.py.
   - PASS: crossed-fingers Exit stopped tracking on the real camera.
   - New setting: "Show the hand skeleton" (settings.json `skeleton`, off by
     default), always drawn while recording a sign.
   - The Exit row's picture still shows crossed hands
     (assets/tutorial-gestures/09-exit.png); needs a crossed-fingers drawing.
   - Exit changed from two crossed hands to **crossed index and middle
     fingers** (`is_crossed_fingers`, `EXIT_CROSS_RATIO` in config.py): the
     crossed hands were not recognised on the real camera, most likely
     because overlapping hands make MediaPipe lose one. Camera-tested: no.
   - Swipes: slow, long ones work; short fast ones do not. Poor camera and
     lighting are a likely contributor. Proposal pending, see chat.
   - Not yet checked: Hold (both palms), macOS.
   - First run needs to reach storage.googleapis.com for the model. A failed
     download used to show as a crash with a report to file; it now shows a
     plain "check your connection and press Start" message
     (`hand_tracker.ModelDownloadError`).

   The checklist, for reference:
   - With the cursor off (default), the mouse never moves.
   - Gestures page → Change on the shaka → *Open a website or file* → a
     Spotify link → Save. A shaka opens it.
   - *Record a sign* (e.g. thumbs up), name it, bind it, hold it ~0.6 s:
     the action runs and the card flashes "Recognised".
   - Recording a shaka, or the same sign twice, shows a warning.
   - Hold (both palms) and Exit (crossed fingers) still work.
   - Repeat the action checks on macOS; there is no macOS CI job.
   - If recognition feels too strict or loose, tune `SIGN_MATCH_MAX_DIST`,
     `SIGN_MAX_ANGLE_DEG` and `SIGN_HOLD_S` in `fingerino/config.py`.
2. **Design review.** Done 2026-11-06 on branch `design-review` (from
   `signs-core`; rebase onto `main` once PR #8 is merged). Review with the
   apple-design skill (installed globally, not vendored: no licence file).
   Fixed: theme-aware status colours (dark/light pairs, >= 4.5:1, guarded by
   tests/test_home_design.py); rows titled by the sign, action underneath;
   pointer switches show off while the cursor is off; one grouped container
   per section; type follows Windows' Text size (`shell.text_scale`);
   ellipses on buttons that open dialogs; editable pause shortcut; Quit on
   Home; "Make your own sign" card on Home and own signs first on Gestures;
   custom-sign pictures drawn from their recorded hand (`SignPictures`
   image provider). Not done, by decision: the warning badge's keyboard
   access (finding 5). Waiting on artwork: crossed-fingers and swipe-right
   pictures, and SVG versions of all drawings that read in light mode
   (the PNG strokes are 2.85:1 on light cards). macOS title case and an app
   menu with Cmd-, are open platform notes.
3. **Security checks** before the next release (also in the README's Next
   steps): `/security-review` on changes since v0.2.0; `pip-audit`;
   Dependabot alerts and secret scanning on GitHub; keep ruff's `S` rules
   passing. Open question: another program running as the user could edit
   `actions.json` and add a command marked `"approved": true`. Consider
   re-confirming commands when the file changed outside Fingerino.
4. **Slice 6, false triggers.** A dry run that logs matches without acting
   (build on `engine.Options(drive=False)`, which already tracks without
   touching the OS), then tune holds and thresholds. Target: five custom
   signs cause fewer than one false trigger per hour of desk use.
5. **Slice 7, always-on mode.** Lower the frame rate with the cursor off;
   recover quietly when a video call takes the camera.
6. **Slice 8, sign packs.** Export/import signs; imported commands load with
   `approved: false` and must show and be approved before they can run (the
   executor already refuses unapproved commands).
7. **Slice 9, launch.** Rewrite the README around signs; change the jitter tip
   to say *lower* `ONE_EURO_MIN_CUTOFF`; remove the gold reticle line; record
   the clip; try PawVis to check positioning. Report recognition accuracy and
   false-trigger rate rather than Fitts numbers.

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
- Custom actions and signs are free; the Premium badge was removed.
- Commands only run when approved; anything typed in Home is approved.
  Opening apps, files and links never goes through a shell.
- Still open: Exit doesn't work while paused (unchanged from v0.2.0).
- Licence (2026-11-06): source-available under FCL-1.0-MIT from the next
  release (branch `license-fcl`); v0.1.0 and v0.2.0 stay MIT. Open core:
  this repo stays public, paid features live in the private repo
  `cky-gitHub/fingerino_premium` and ship in the same official build behind
  an offline-checked licence key. Replaces the earlier "custom signs are
  free" decision: free gets a small number of custom signs (1 to 3, to be
  decided), Premium about 20. The limit is licence-key functionality, which
  FCL forbids circumventing.

## Keep intact

README privacy promises (video stays in memory, nothing recorded or
uploaded, no telemetry, the model download is the only network request);
every file Fingerino writes listed in the README; the single button-release
path, `DRAG_MAX_S`, held confirmation, Hold and Exit; the `mediapipe<1.0` pin;
thresholds in `config.py`; ruff, mypy and pytest passing; Windows and macOS
support without breaking the Linux source install.

## Working on it

```bash
pip install -e ".[dev]"
ruff check fingerino packaging tests && mypy && pytest -q
```

- Camera-free test helpers: `tests/landmarks.py` (synthetic hands, recordings
  with drift and jitter) and `tests/sessionkit.py` (runs the real
  `engine.Session` with a fake camera, tracker, mouse and clock).
- Headless Linux needs `QT_QPA_PLATFORM=offscreen` and
  `PYNPUT_BACKEND=dummy`, plus system packages `libegl1 libgl1 libgles2
  libxkbcommon0 libfontconfig1 libdbus-1-3` for Qt and MediaPipe.
- The `Cannot read property ... of null` QML messages at test teardown are
  noise from the window closing, and predate this branch.
- `Notes.md` is an older phase plan from before the sign direction.
