# Release readiness

Working plan for getting Fingerino to the point where it can be handed to
other people and behave the same way on their machines as it does here.

Status as of 2026-10-28. Phases 0, 1, 3 and 4 are done and merged to `main`
(PR #1, `b32ae58`). CI is green on a real runner for the first time. Next up is
Phase 2, which needs a webcam session.

---

## Done

| Phase | Commit | What it closed |
| --- | --- | --- |
| 0 — security fix | `95536fd` | `winui` matched windows by title across every process; any window called "fingerino" could be restyled and pinned. Now gated on owning PID. |
| 3 — reproducible builds | `13937c9` | Model download had no checksum and no timeout; dependencies were unpinned floors; version lived in two places. |
| 1 — CI | `1d50fd4`, `76f9d7a`, `bf7901f` | No workflow ran on push — only on tag. Now lint + types + tests on every push. The first two runner fixes came later: mypy on Linux rejected `ctypes.WinDLL`, and bare `pytest` could not import the uninstalled package. |
| 4 — trust | `93b24c9` + issue template | README privacy section, `SECURITY.md`, licence notices, local crash report, SHA-256 of release artifacts, bug-report form that asks for `selftest.txt` and `crash.txt`. |

### Verified facts worth not re-deriving

- **Model digest** `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`,
  7,819,105 bytes — confirmed byte-for-byte against Google's CDN, not merely
  trusted from the local copy. Pinned in `fingerino/hand_tracker.py`.
- **OpenCV 5.0.0 still uses the window class `"Main HighGUI class"`**, so
  `winui.find_own_window()` works on the version actually installed here. This
  was a live risk, not hypothetical: `pyproject.toml` says `opencv-python>=4.9`
  and the dev machine resolved to 5.0.0.93.
- **`fingerino/gesture_detector.py` and `fingerino/config.py` import only the
  standard library.** No MediaPipe, no OpenCV, no camera. The most valuable
  logic in the project is therefore testable in ~0.1s anywhere, which is what
  the fast CI job exploits and what makes Phase 2 cheap.
- Pinning did **not** change what ships. CI was already resolving OpenCV 5 and
  MediaPipe 0.10.35; `requirements-build.txt` freezes that rather than moving it.

### Re-verify the gate

```
python -m ruff check fingerino packaging tests
python -m mypy
python -m pytest -q          # 72 passed, 1 skipped
python -m fingerino --selftest
```

Always run `python -m pytest` locally. It puts the cwd on `sys.path`, so it
passes even where CI's bare `pytest` would not — that is how the import bug
above stayed hidden. `pythonpath = ["."]` in `pyproject.toml` now covers both.

---

## Loose ends found while getting CI green

- **Intel Macs are dropped.** The first Release run (2026-08-23) died on the
  Apple Silicon selftest, which the runner's missing Metal GPU explains and
  `release.yml` now tolerates. The second (2026-10-28) passed Windows and Apple
  Silicon but could not install `mediapipe==0.10.35` on Intel: MediaPipe's last
  x86_64 macOS wheel is 0.10.21, which needs NumPy < 2 and protobuf 4. Rather
  than keep a second, untested pin set, Intel was removed from the matrix.
- **No Apple Silicon build has been run on a real Mac yet.** CI can only check
  that the model is in the bundle. Find someone with an M-series Mac.
- **Node 20 deprecation warnings** on `actions/checkout@v4` and
  `actions/setup-python@v5`, in both workflows. Bump to the current majors.

---

## Phase 2 — the rest of the tests

The starter suite covers `DragTrigger`, the "X" geometry, the control-zone
mapping, the One Euro filter, and regression guards for the two security fixes
above. What is missing is the part that needs real data.

**Needs the user, ~5 minutes at a webcam.** The gesture classifiers
(`is_pointing`, `is_shaka`, `is_flat_hand`, `is_two_finger`, `both_flat`,
`is_fist`, `is_thumb_extended`) take 21-point landmark arrays. Hand-writing
those fixtures would test a *model* of the geometry rather than what the
tracker actually emits, so the tests would pass and mean nothing.

Plan: add a `--record-landmarks` flag that dumps timestamped landmark arrays to
JSON while the user performs each of the ten gestures, then write assertions
against the recording. Everything else in this phase needs no hardware.

Also here, once tests exist to catch a slip: convert the `ui` dict in
`fingerino/main.py` to a small dataclass. It is currently annotated
`dict[str, Any]` so mypy passes, which is honest but not the right shape.

## Phase 4 — trust (done)

Context worth keeping in mind: this app reads the webcam continuously and
synthesizes global mouse and keyboard input. That is functionally the
capability set of a RAT, and friends' antivirus will agree. The privacy and
verification story is not decoration here — keep the README's privacy section
true as features are added.

## Phase 5 — performance, measure first

Do not optimise speculatively. Per frame the loop does a `cvtColor`, an
`ascontiguousarray` copy, a MediaPipe submit, a PIL overlay build and
composite, and — with the guide open — a full-frame `cv2.resize` plus a
complete re-render of `render_gesture_panel` including text and icons.
MediaPipe's flow limiter drops frames when busy, so nothing queues unboundedly,
but the convert and copy are paid on every captured frame regardless.

Step 1: extend `--debug` to break the existing `fps` counter into capture /
convert / detect / overlay / imshow. **Needs the user for one run** to read the
numbers back. Step 2 (optimisation) is unblocked once those exist. The likely
win is caching the static guide panel between hover changes; the likely
ceiling is MediaPipe itself, in which case the only lever is input resolution.

## Phase 6 — supply chain

- `actions/attest-build-provenance` in `release.yml` — roughly five lines, and
  yields signed proof that a given `.exe` came from a given commit via a given
  workflow. Strongest available answer to "how do I know this is safe."
- `pip-audit` as a CI step.
- OpenSSF Scorecard workflow. Needs the repo public; may need one repo setting
  flipped for results upload.

## Phase 7 — later, only if people actually use it

- **Update check.** With friends, the dominant support cost is people running
  an old build. A once-a-day check against the GitHub releases API with a toast
  in the existing overlay kills that category.
- **Code signing.** Windows: Azure Trusted Signing, around $10/month — confirm
  current pricing. macOS: Apple Developer, $99/year; `packaging/build.py`
  already handles signing and notarization the moment `APPLE_DEVELOPER_ID` and
  `APPLE_NOTARY_PROFILE` are set as repository secrets. Deliberately deferred:
  ship unsigned with good instructions and published hashes first, pay once
  there is evidence people want it.

---

## Standing advice

- **Resist rewriting code that works.** The architecture is sound and the
  comments explain *why* rather than *what*, which is rarer than it should be.
  The gaps are around the code — tests, CI, pinning, provenance — not in it.
- **Two friends, two different machines, before more polish.** Specifically: a
  machine with no webcam, one with two webcams, and a high-DPI laptop.
- Phase 5 is genuinely risky before Phase 2 exists. That ordering is not
  aesthetic.
