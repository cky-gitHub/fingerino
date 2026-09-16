Phase	Work	Effort	Why now
0	Commit the winui.py security fix	15 min	Finished work, currently protecting nobody
1	ci.yml: ruff + mypy + pytest + Windows selftest	Half day	Everything downstream depends on this
2	Tests for gesture_detector + DragTrigger	1–2 days	This is "consistent performance"
3	Pin build deps; unify version; SHA-256 the model in both places, add timeouts	Half day	Reproducible, verifiable builds
4	README privacy section, SECURITY.md, issue template, release hashes	Half day	Trust — friends will ask
5	Instrument --debug timings, then optimise what's actually slow	1 day	Measure first
6	Build provenance attestation, pip-audit, Scorecard	Half day	Polish; genuinely impressive
7	Update check; code signing	Later	Only once people actually use it