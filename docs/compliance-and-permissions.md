# Compliance, privacy and permissions

What Fingerino actually needs, and what it demonstrably does not. Written
2026-09-19 against the state of `hardening/release-readiness`.

Not legal advice. The obligations below are the well-documented terms of the
licences involved; if Fingerino ever becomes commercial, get a lawyer to look
at the LGPL section in particular.

---

## What Fingerino is, for the purposes of all of this

A local desktop application. No backend, no accounts, no website, no browser
surface, no analytics, no telemetry, no crash reporting. Video is processed
in-process and never written to disk or transmitted.

**It makes exactly one network request, ever:** the first run downloads the
7 MB hand-landmark model from `storage.googleapis.com` unless the packaged
build already bundles it (the installers do; a `pip install` does not). That
request reveals the user's IP address to Google, like any download does. It is
the only thing that leaves the machine, and it must be disclosed honestly
rather than glossed as "nothing leaves your computer".

Everything else on this page follows from that shape.

---

## Does not apply — do not build these

Naming them explicitly so the work doesn't get invented later.

| Thing | Why not |
| --- | --- |
| **Cookie banner / cookie policy** | No browser surface whatsoever. Nothing to consent to. (If a GitHub Pages site is added later: Pages sets no cookies unless analytics are added. Don't add analytics.) |
| **Terms of Service / EULA** | No service, no account, no uptime to promise. The MIT `LICENSE` already grants use and disclaims warranty, which is the whole of what a distributed open-source binary needs. |
| **GDPR controller obligations** — DPO, records of processing, DPIA, data-subject request flow | No personal data is collected, stored or transmitted. There is no processing to be controller of. |
| **Privacy policy in the regulatory sense** | Same reason. A plain-English privacy *statement* is still wanted — see below — but as a trust artifact, not a compliance one. |
| **App store review, age ratings, COPPA** | Not distributed through any store. |
| **SOC 2 / ISO 27001 / PCI / HIPAA** | Nothing is held on anyone's behalf. |
| **Accessibility conformance statement (WCAG, EN 301 549)** | Not a web product and not sold into public-sector procurement. |

---

## Required and currently missing

### 1. Third-party licence notices — the one real legal gap

Every installer redistributes a large amount of other people's code, and
**ships no licence text for any of it.** This is the clearest "must fix" on
the page.

| Component | Licence | What it obliges |
| --- | --- | --- |
| MediaPipe | Apache-2.0 | section 4(d): include the licence and retain the NOTICE file |
| OpenCV (`opencv-python`, `opencv-contrib-python`) | Apache-2.0 | same |
| absl-py, flatbuffers | Apache-2.0 | same |
| **pynput** | **LGPL-3.0** | **Strongest obligation here** — see below |
| **FFmpeg** (`opencv_videoio_ffmpeg500_64.dll`, shipped inside the OpenCV wheel) | LGPL-2.1+ | licence text, plus the relinking allowance |
| certifi | MPL-2.0 | file-level copyleft; attribution suffices while unmodified |
| Pillow | MIT-CMU | attribution |
| NumPy, matplotlib, dateutil, kiwisolver, contourpy, cycler | BSD / PSF | attribution |
| six, fonttools | MIT | attribution |
| **Inter font** | **SIL OFL 1.1** | licence must accompany the fonts — **and it currently does not**: `packaging/fingerino.spec` globs `assets/fonts/*.ttf` only, so `OFL-LICENSE.txt` is in the repo but never reaches the bundle |
| `hand_landmarker.task` | Google model terms | cite the model card |

**The LGPL question (pynput, FFmpeg).** LGPL permits use in a non-copyleft
application, but requires that the user be able to replace the LGPL component
with their own version. A PyInstaller bundle compiles pynput to `.pyc` inside
a PYZ archive, which satisfies that poorly. In practice this is manageable and
extremely common:

- Fingerino is itself MIT and fully open source, so the corresponding source
  is already available.
- Ship the LGPL text, state the pynput version, and link to its upstream.
- State that a user may rebuild from source with a replaced pynput, and that
  `packaging/build.py` is the supported way to do it.

That is the standard posture for an open-source Python app, and it is a real
argument that a closed-source one could not make.

**Fix:** generate `THIRD-PARTY-NOTICES.md` at build time from installed
distribution metadata, ship it in all three targets (Inno `[Files]`, the DMG,
and the `.app` Resources), link it from the README, and surface it from an
in-app About. Add `OFL-LICENSE.txt` to the spec's `datas` while doing it.

### 2. Privacy statement

Nothing is collected, which makes this cheap to write and valuable to have —
it is the trust story for an app that reads a webcam and drives the mouse.

Must cover, honestly:

- Video is processed in memory and never recorded, written or transmitted.
- The one network request: what it fetches, from whom, and that it happens
  once. Note that the installers bundle the model so they make no request at
  all.
- What is written to disk and where: the model, a generated `.ico`, and
  `selftest.txt` — all under `%LOCALAPPDATA%\fingerino`,
  `~/Library/Caches/fingerino`, or `$XDG_CACHE_HOME/fingerino`. `selftest.txt`
  is a local diagnostic; nothing sends it anywhere, and a user who pastes it
  into an issue is doing so deliberately.
- No telemetry, no analytics, no crash reporting, no accounts, no update ping
  (true today — revisit if the Phase 7 update check is ever built).

Belongs at the top of the README, not buried. The best sentence in the project
is currently inside `packaging/build.py`'s DMG readme: *"Video is processed on
your Mac and never leaves it."*

### 3. `SECURITY.md`

Missing. Needs a reporting route, a response expectation, and — specific to
this project — a section explaining why SmartScreen and Gatekeeper complain,
so it can be linked rather than re-explained to every friend.

---

## Permission controls — the part that matters most here

Fingerino reads the webcam continuously and synthesizes global mouse and
keyboard input. That is functionally the capability set of a remote-access
trojan, and antivirus software will agree. Permission transparency is not
decoration.

**Already good:**

- macOS `Info.plist` declares `NSCameraUsageDescription` with an honest,
  specific string that states the privacy position in the prompt itself.
- Accessibility is gated properly: the app asks before the window opens, polls
  for the grant, and says "restart to enable control" rather than pretending it
  works — because macOS only hands the permission to a freshly started process.
- `--no-move` runs the whole pipeline without touching the OS. A genuine safe
  mode, and the right thing to point a nervous friend at first.
- The Hold gesture (both palms) is a real kill switch, and per-gesture toggles
  exist in the guide.
- The camera preview window *is* the "camera is live" indicator, and it is
  always-on-top. That is better design than a status-bar dot.
- Windows uninstall removes `%LOCALAPPDATA%\fingerino` via Inno
  `[UninstallDelete]`.

**Gaps:**

| Gap | Why it matters |
| --- | --- |
| Per-gesture toggles reset every launch | Someone who switches off "New chat" because Alt+Space collides with their setup has to do it again every single time. Permission choices that do not persist are not really controls. |
| No documented way to refuse the network call | `FINGERINO_MODEL` already points at a local model and skips the download entirely. It exists, it works, and it is undocumented as the privacy control it is. |
| macOS leaves `~/Library/Caches/fingerino` behind forever | No uninstaller, and the DMG readme does not mention removal. One line of documentation. |
| `open_ai_chat()` sends Alt+Space globally | With no chat app bound to it on Windows, Alt+Space opens the window system menu. Undocumented side effect of a gesture that is on by default. |
| No in-app view of current permission state | The user cannot see what Fingerino currently has. `--selftest` knows; the UI does not. |
| No crash handler | If anything throws mid-loop in a packaged build, the app vanishes with no message and no log. Already flagged in the release plan; still not done. A support problem and a trust problem at once. |

---

## Security posture

**Done** (on `hardening/release-readiness`):

- Window handles are gated on owning PID — the title-only lookup that could
  restyle a stranger's window is gone, with a regression test.
- The model is pinned by SHA-256, verified on every start, with a download
  timeout. A bundled model that fails is reported rather than silently
  replaced.
- Build dependencies pinned; CI runs lint, types and 37 tests on every push.

**Missing**, roughly in order of value:

1. **Crash handler** writing a traceback next to `selftest.txt`, plus a dialog.
   Cheap, and it is the difference between "it crashed" and a report worth
   acting on.
2. **`SECURITY.md`** and a vulnerability reporting route.
3. **Published SHA-256 of release artifacts** in the release notes.
4. **Build provenance** — `actions/attest-build-provenance`, roughly five
   lines, gives signed proof an artifact came from a given commit and workflow.
   The strongest available answer to "how do I know this is safe", and worth
   more than code signing for a technical audience.
5. **`pip-audit`** in CI for dependency CVEs.
6. **Code signing.** Deferred deliberately — see the release plan. Ship
   unsigned with good instructions and published hashes first.

**Reviewed, no action needed:** the single-instance mutex uses the `Local\`
namespace, so it is scoped to the user's login session rather than machine-wide.
Another process in the same session could squat the name and prevent launch,
which is nuisance-level and not worth defending against. A `Global\` mutex
would have been the wrong choice here.

---

## Suggested order

1. `THIRD-PARTY-NOTICES.md` generated at build time, plus shipping
   `OFL-LICENSE.txt`. The only item with an actual legal obligation behind it.
2. README privacy section and `SECURITY.md`.
3. Crash handler.
4. Persist the per-gesture toggles; document `FINGERINO_MODEL` as the
   offline/no-network switch; document the Alt+Space collision and macOS cache
   removal.
5. Release hashes, then provenance, then `pip-audit`.
