# Security

## Reporting a problem

Please report security issues privately rather than in a public issue:

- **Preferred:** [open a private security advisory](https://github.com/cky-gitHub/fingerino/security/advisories/new)
- Or email the address on the commits in this repository.

Tell me what you did, what happened, and which build you were on
(`Fingerino --selftest` prints the version and where it loaded the model from).
I am one person doing this in my spare time, so I cannot promise a response
time — but I will read it, and I would much rather hear about a problem than
not.

Fixes land on `main` and go out in the next tagged release. If something is
serious enough to warrant it, I will cut a release for it alone.

## What Fingerino can do, and why your antivirus cares

Fingerino continuously reads your webcam and synthesizes mouse and keyboard
input. That combination is, functionally, what remote-access malware does, and
security software is right to look twice at it.

What that means in practice, and what limits it:

- **Video never leaves your machine.** It is processed in memory and never
  written to disk or transmitted.
- **The app makes exactly one network request, ever** — the first run
  downloads the hand-landmark model, unless you installed one of the released
  installers, which bundle it and so make no request at all. There is no
  telemetry, no analytics, no crash reporting and no update check.
- **That download is checksum-pinned.** The model is verified against a
  SHA-256 recorded in the source on every single start, not just when it is
  first fetched. A file that does not match is refused rather than loaded.
- **It only touches its own windows.** Every Windows API call that restyles,
  resizes or reorders a window first checks the window belongs to this
  process.
- **`--no-move` runs everything except the part that controls your computer.**
  If you want to watch what it does before trusting it, start there.
- **Every gesture can be switched off individually** in the guide (press Tab),
  and holding both palms up pauses all of them at once.

## Why the installers are not signed

Code-signing certificates cost money per year, and this is a free hobby
project. So:

- **Windows** shows a SmartScreen warning. Click **More info → Run anyway**.
- **macOS** blocks the app on first launch. **System Settings → Privacy &
  Security**, scroll down, **Open Anyway**.

Neither warning means anything is wrong with the file. Both mean the same
thing: the developer has not paid for a certificate, so the OS has no reputation
to go on.

If you would rather not take that on faith, you have better options than
trusting me:

1. **Check the hash.** Every release lists the SHA-256 of each file. On
   Windows, `Get-FileHash <file>`; on macOS, `shasum -a 256 <file>`.
2. **Read the source.** It is all here, and it is not a large project.
3. **Build it yourself.** `python packaging/build.py` produces the same
   installers, from dependency versions pinned in `requirements-build.txt`.

## Scope

In scope: anything that lets Fingerino be used to compromise the machine it is
installed on, take input it should not, or run code it should not.

Out of scope: the SmartScreen and Gatekeeper warnings above (expected, see
why), and gesture misrecognition — that is a bug, and a welcome one to report,
but a normal public issue is the right place for it.
