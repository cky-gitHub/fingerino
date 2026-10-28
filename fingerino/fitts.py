"""Fitts' law harness — measure whether a pointing change actually helped.

    python -m fingerino.fitts                # 24 trials, then a summary
    python -m fingerino.fitts --trials 40
    python -m fingerino.fitts --label "palm + anchor"

Deliberately knows nothing about Fingerino's internals. It shows a target,
listens for a click anywhere on screen, and records where the click landed and
how long it took. So it measures whatever is driving the cursor — run it with
an ordinary mouse first to get a baseline, then with Fingerino, and compare.

That matters because gesture control is exactly the domain where intuition
misleads: every change feels better for the first two minutes. Throughput does
not care how a change feels.

What comes out:

    Throughput (bits/s)   Fitts' index of difficulty divided by movement time.
                          Higher is better. A mouse is usually 3.7-4.9; a
                          decent gesture system is a fraction of that.
    Error rate            Clicks that missed the target.
    Overshoot             Median distance from the click to the target centre,
                          as a fraction of the target radius. This is the
                          number click anchoring is meant to move.

Each run appends a CSV next to the model cache so runs can be compared later.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import config
from .hand_tracker import cache_dir

_WINDOW = "Fingerino — target practice"

# Target diameters in pixels. Deliberately spans "toolbar icon" to "big
# button": the small end is where a gesture pointer falls apart, and an
# average that hides it is not worth having.
_WIDTHS = (24, 40, 64, 96)


@dataclass
class Trial:
    index: int
    target_x: int
    target_y: int
    width: int             # diameter, px
    distance: float        # from the previous click, px
    click_x: int
    click_y: int
    seconds: float
    hit: bool

    @property
    def index_of_difficulty(self) -> float:
        """Shannon formulation, ID = log2(D/W + 1)."""
        return math.log2(self.distance / self.width + 1.0)

    @property
    def throughput(self) -> float:
        return self.index_of_difficulty / self.seconds if self.seconds > 0 else 0.0

    @property
    def offset(self) -> float:
        return math.hypot(self.click_x - self.target_x, self.click_y - self.target_y)


def _next_target(screen_w: int, screen_h: int, previous: tuple[int, int],
                 rng: random.Random) -> tuple[int, int, int]:
    """A target far enough from the last click to be a real movement.

    Kept clear of the top-left corner, which is where Fingerino parks its own
    always-on-top HUD — a target underneath it cannot be clicked.
    """
    width = rng.choice(_WIDTHS)
    margin = width + 40
    hud_w, hud_h = screen_w // 3, screen_h // 3
    for _ in range(200):
        x = rng.randint(margin, screen_w - margin)
        y = rng.randint(margin, screen_h - margin)
        if x < hud_w and y < hud_h:
            continue                       # under the HUD
        if math.hypot(x - previous[0], y - previous[1]) < 250:
            continue                       # too close to be a movement
        return x, y, width
    return screen_w // 2, screen_h // 2, width


def _draw(canvas, target, width, hit_count, total, label):
    canvas[:] = (16, 14, 14)
    x, y = target
    radius = width // 2

    cv2.circle(canvas, (x, y), radius, (240, 237, 237), -1, cv2.LINE_AA)
    cv2.circle(canvas, (x, y), max(2, radius // 5), (16, 14, 14), -1, cv2.LINE_AA)

    cv2.putText(canvas, f"{hit_count}/{total}   {width}px", (24, 44),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (163, 155, 155), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"{label}   —   Esc to stop", (24, 76),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (101, 92, 92), 1, cv2.LINE_AA)


def _summarise(trials: list[Trial], label: str) -> str:
    if not trials:
        return "no trials recorded"

    hits = [t for t in trials if t.hit]
    # Throughput is only meaningful over hits; a miss did not acquire the
    # target, so its movement time is not the time to acquire the target.
    throughput = statistics.mean(t.throughput for t in hits) if hits else 0.0
    times = [t.seconds for t in hits] or [0.0]
    offsets = [t.offset / (t.width / 2) for t in trials]

    small = [t for t in trials if t.width <= 40]
    small_error = (100.0 * sum(not t.hit for t in small) / len(small)) if small else 0.0

    lines = [
        "",
        f"  {label}",
        f"  {'-' * max(len(label), 44)}",
        f"  trials              {len(trials)}",
        f"  error rate          {100.0 * sum(not t.hit for t in trials) / len(trials):.1f}%",
        f"    on small targets  {small_error:.1f}%   (<= 40 px)",
        f"  throughput          {throughput:.2f} bits/s   (higher is better)",
        f"  median time         {statistics.median(times):.2f} s",
        f"  median offset       {statistics.median(offsets):.2f} x target radius",
        "",
        f"  cursor source       {config.CURSOR_SOURCE}",
        f"  click anchoring     {'on' if config.CLICK_ANCHOR else 'off'}"
        f"   (lookback {config.CLICK_ANCHOR_LOOKBACK_S:.2f}s)",
        f"  freeze while aiming {'on' if config.FREEZE_WHILE_AIMING else 'off'}",
        "",
    ]
    return "\n".join(lines)


def _append_csv(trials: list[Trial], label: str) -> str | None:
    path = os.path.join(cache_dir(), "fitts.csv")
    try:
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if new:
                writer.writerow([
                    "run", "label", "cursor_source", "click_anchor", "freeze",
                    "trial", "width_px", "distance_px", "seconds", "hit",
                    "offset_px", "index_of_difficulty", "throughput",
                ])
            run = time.strftime("%Y-%m-%dT%H:%M:%S")
            for t in trials:
                writer.writerow([
                    run, label, config.CURSOR_SOURCE, config.CLICK_ANCHOR,
                    config.FREEZE_WHILE_AIMING, t.index, t.width,
                    f"{t.distance:.1f}", f"{t.seconds:.4f}", int(t.hit),
                    f"{t.offset:.1f}", f"{t.index_of_difficulty:.3f}",
                    f"{t.throughput:.3f}",
                ])
        return path
    except OSError:
        return None


def run(trials_wanted: int, label: str, seed: int | None) -> int:
    from pynput import mouse

    from .cursor_controller import _get_screen_size

    # S311: target placement, not cryptography — and seedable on purpose,
    # so two runs can be given the identical sequence to compare.
    rng = random.Random(seed)  # noqa: S311
    screen_w, screen_h = _get_screen_size()

    clicks: list[tuple[int, int, float]] = []

    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            clicks.append((int(x), int(y), time.perf_counter()))

    listener = mouse.Listener(on_click=on_click)
    listener.start()

    cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(_WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    canvas = np.zeros((screen_h, screen_w, 3), np.uint8)

    results: list[Trial] = []
    previous = (screen_w // 2, screen_h // 2)
    aborted = False

    try:
        for i in range(trials_wanted):
            x, y, width = _next_target(screen_w, screen_h, previous, rng)
            clicks.clear()
            _draw(canvas, (x, y), width, len(results), trials_wanted, label)
            cv2.imshow(_WINDOW, canvas)
            cv2.waitKey(1)
            started = time.perf_counter()

            while not clicks:
                cv2.imshow(_WINDOW, canvas)
                if (cv2.waitKey(16) & 0xFF) == 27:
                    aborted = True
                    break
                if cv2.getWindowProperty(_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    aborted = True
                    break
            if aborted:
                break

            cx, cy, when = clicks[0]
            hit = math.hypot(cx - x, cy - y) <= width / 2
            results.append(Trial(
                index=i + 1, target_x=x, target_y=y, width=width,
                distance=math.hypot(x - previous[0], y - previous[1]),
                click_x=cx, click_y=cy, seconds=when - started, hit=hit,
            ))
            previous = (cx, cy)
    finally:
        listener.stop()
        cv2.destroyAllWindows()

    print(_summarise(results, label))
    path = _append_csv(results, label)
    if path:
        print(f"  appended {len(results)} rows to {path}\n")
    if aborted:
        print("  (stopped early)\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure pointing performance. Run it with a mouse for a "
                    "baseline, then with Fingerino, and compare throughput.")
    parser.add_argument("--trials", type=int, default=24,
                        help="how many targets (default %(default)s)")
    parser.add_argument("--label", default="",
                        help="name this run in the summary and the CSV")
    parser.add_argument("--seed", type=int, default=None,
                        help="fix the target sequence so two runs are comparable")
    args = parser.parse_args(argv)

    label = args.label or f"{config.CURSOR_SOURCE}, anchor={config.CLICK_ANCHOR}"
    print("\n  Click each target as quickly and accurately as you can.")
    print("  Esc stops early and still reports what was collected.\n")
    return run(args.trials, label, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
