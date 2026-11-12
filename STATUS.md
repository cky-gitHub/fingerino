# Fingerino status

Last updated 2026-11-12. Read this first when picking the work up.

## Where things stand

Fingerino is a **hand-sign shortcut tool**: signs like the shaka trigger
actions, anyone can record a new sign without code, and the cursor is an
optional module that is off by default.

- **`main`** has everything below, including the premium foundation (PR
  #19) and the v0.3.0 release (PR #21: the limit and trial live, "Get
  Premium" reads "Coming soon", the new shaka logo, "Made by CKY").
  Private repo: `feat/licence-issuer` (PR #2) waits for merge.
  (`ccr-2c0750c7-uhrknd` and `claude/apollo-rocket-controls-igrhf0` on the
  remote were not made in this work; leave them alone unless the owner says.)
- **Released:** v0.3.0 (2026-11-09) is the latest release, the first under
  FCL-1.0-MIT: slices 1 to 5, the redesign, Free/Premium with the trial,
  the new logo. The README links the installers through
  `releases/latest/download/<version-less name>`, so its links always fetch
  the newest release. Earlier: v0.2.1 (2026-11-07, MIT).
- **v0.3.1 (branch `fix/hud-size-and-icons`, not released):** fixes seen on
  another Windows 11 laptop (100% scale). The HUD was laggy and its chrome
  too small: it was drawn on the full camera frame (28 ms a frame at
  1280x720, 66 ms at 1080p, on the owner's laptop) and sized for 1280x720
  even when the camera sent more. Now the frame is shrunk to the HUD first
  (4 ms) and the chrome scales with the HUD width (`HUD_DESIGN_WIDTH`).
  The nav icons and the HUD's caption buttons were boxes there (Segoe icon
  font not found); both are now drawn by Fingerino. `--debug` shows the
  camera's real resolution. Not yet confirmed on that laptop.
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
- **Premium foundation (step 2, merged):** `fingerino/licence.py`
  (offline Ed25519 key check, trial, plan), `fingerino/addons.py` (the
  add-on hook), the sign limit in `signs.Library`, Home's locked sign rows,
  the note at the limit, Settings › Premium, `licence.key` and the trial
  start in the README; the key issuer `python -m fingerino_premium.issue`
  in the private repo. `--selftest` checks the licence library loads.
- **Tests:** 377 collected; all pass with every dependency installed
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

1. **Security follow-ups: done.** `ci/pin-actions` is merged (PR #11); the
   owner switches on the GitHub settings (Dependabot alerts and security
   updates, secret scanning with push protection, CodeQL default setup,
   private vulnerability reporting, a PR-and-CI rule for `main`). On the
   private repo only Dependabot alerts are free; use Semgrep and Gitleaks
   locally.
2. **Premium foundation: done.** Left over, before the first sale (the
   owner's business isn't registered yet, so v0.3.0 ships "coming soon"):
   - The owner picks the shop (Paddle recommended, Lemon Squeezy as the
     fallback, Gumroad the simplest but dearest; compared 2026-11-07). Then
     set `config.PREMIUM_URL` to its checkout and release: that alone opens
     sales ("Coming soon" becomes "Get Premium"). Update the README's
     Premium section ("goes on sale soon") at the same time.
   - A blocklist of leaked keys (owner, 2026-11-08): order ids (hashed) in
     `licence.py`, refused like a bad signature, so a key posted online
     stops working from the next update; the honest buyer gets a new key.
     Offline, about 30 lines plus tests. Leaks are otherwise deterred by the
     buyer's email shown in Settings, and taken down by request.
   - The automatic issuer: the shop's sale webhook → a small function that
     holds the signing key → emails the key. Same `licence.make_key` as the
     manual command. Needs its own security care (it holds the key).
   - Camera check: record past the limit on a free install, "Use this one
     instead", enter a key, remove it.
3. ~~Release v0.3.0~~ — done 2026-11-09 (tag `v0.3.0` on `8eef7b8`).
4. **Premium features, in `fingerino_premium`.** Wispr Flow first: a new
   action kind "hold a key while the sign is held" (press when the sign
   starts, release when it ends) so a shaka holds Wispr's push-to-talk key.
   Then the MCP server, which needs its own security design (what it may do,
   confirmation for risky actions, local only) before any code.
5. **Slice 6, false triggers.** A dry run that logs matches without acting
   (build on `engine.Options(drive=False)`), then tune on the owner's camera.
   Includes the swipe report: slow long swipes work, short fast ones don't
   (proposal: `WAVE_MIN_TRAVEL` 0.22 → 0.16, `WAVE_WINDOW_S` 0.5 → 0.35, a
   0.1 s grace for a dropped open-hand frame; measure first). HUD swipe
   arrows are weak. Target: five custom signs cause fewer than one false
   trigger per hour of desk use.
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
the payment provider; a backup of the licence signing key (below).

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
  is stored locally and can be reset; that is accepted. Premium: 30
  custom signs, the Wispr Flow hold, the MCP server.
- MediaPipe telemetry (2026-11-07): Google's PyPI builds from 0.10.35 on
  contain a "Clearcut" uploader to play.googleapis.com with no off switch
  (google-ai-edge/mediapipe#6291). v0.1.0 and v0.2.0 shipped it; v0.2.1
  removed it and says so in its release notes and the README. Stay on
  0.10.33 until Google offers a way to turn it off; Dependabot ignores
  MediaPipe for this reason.
- Premium mechanics (2026-11-07):
  - Until the shop opens (`config.PREMIUM_URL` empty) only "Get Premium"
    waits: it reads "Coming soon". The limit and the trial already apply
    (owner, 2026-11-08, accepting that free users can't buy more signs
    until the shop opens); keys work, for the owner's dry run.
  - One-time purchase; keys never expire.
  - Key: `fingerino1.<base64url JSON>.<base64url Ed25519 signature>`, JSON
    `{v, id, email, plan, issued}`, pasted into Settings › Premium and kept
    as `licence.key`. Checked offline with `cryptography` (a dependency
    since this step); keys can't be revoked, the email deters sharing.
  - The signing key is `~/.fingerino-premium/signing-key.txt` on the
    owner's PC (created 2026-11-07), never in a repo; its public half is
    `licence.PUBLIC_KEY`. Losing it means no new keys until a release ships
    a new public key. Back it up in a password manager.
  - The trial starts on the first launch of a version that has it,
    upgraders included (they have no custom signs: recording was never
    released). Stored as `trial_started` in settings.json.
  - The limit counts switched-on signs in list order; the rest are
    "locked": still on in signs.json, left out of the matcher. "Use this
    one instead" moves a sign to the top. Switching a sign on at the limit
    does the same. Unlocking changes nothing on disk.
  - The sign limit depends only on the licence (a source build with a key
    gets 20 too); the add-on only adds features (`wispr_hold`,
    `mcp_server`), each allowed through `host.entitled()`.
  - Add-on hook: a plain `import fingerino_premium` (PyInstaller builds
    carry no entry-point metadata), contract `ADDON_API = 1`; any failure
    leaves the free app with a note in Settings.
- Premium's limit is 30 signs, not unlimited (owner, 2026-11-08).
- Commits use the owner's GitHub no-reply address (set per repo).
- Still open: Exit doesn't work while paused (unchanged from v0.2.0).

## Keep intact

README privacy promises (video stays in memory, nothing recorded or
uploaded, no telemetry, the model download is the only network request,
licence keys checked offline);
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
