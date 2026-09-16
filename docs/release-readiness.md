# Release readiness

Working plan for getting Fingerino to the point where it can be handed to
other people and behave the same way on their machines as it does here.

Status as of 2026-09-16. Phases 0, 1 and 3 are done and sit on the branch
`hardening/release-readiness` (three commits, **not yet pushed**). `main` is
still at `81d8a7f`.

---

## Done

| Phase | Commit | What it closed |
| --- | --- | --- |
| 0 — security fix | `95536fd` | `winui` matched windows by title across every process; any window called "fingerino" could be restyled and pinned. Now gated on owning PID. |
| 3 — reproducible builds | `13937c9` | Model download had no checksum and no timeout; dependencies were unpinned floors; version lived in two places. |
| 1 — CI | `1d50fd4` | No workflow ran on push — only on tag. Now lint + types + tests on every push, plus a 37-test starter suite. |

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
python -m pytest -q          # 37 passed, 1 skipped
python -m fingerino --selftest
```

---

## Next: push and confirm CI

Nothing below should start until a real runner has proven `ci.yml`. It has
only ever been validated locally and against a simulated dependency-free
environment.

```
git push -u origin hardening/release-readiness
```

Then merge if green.

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

## Phase 4 — trust

All of this is writing, no hardware, no blockers.

- **README privacy section, prominent.** The strongest sentence in the project
  is currently buried in `packaging/build.py`'s DMG readme: *"Video is
  processed on your Mac and never leaves it."* It belongs at the top of the
  README with a table of which permission is needed and why (camera;
  Accessibility on macOS; network exactly once, for a 7 MB model).
- **`SECURITY.md`** — how to report, plus a "why does SmartScreen flag this"
  section to point friends at.
- **Issue template** that asks for `%LOCALAPPDATA%\fingerino\selftest.txt`.
  That diagnostic file already exists; make sure it reaches the maintainer.
- **Publish SHA-256 of release artifacts** in the release notes — one CI step,
  lets a cautious friend verify their download.

Context worth keeping in mind: this app reads the webcam continuously and
synthesizes global mouse and keyboard input. That is functionally the
capability set of a RAT, and friends' antivirus will agree. The privacy and
verification story is not decoration here.

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
