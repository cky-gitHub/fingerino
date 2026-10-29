# UI direction: from a camera window to a desktop app

Research and recommendations for making Fingerino look and behave like
professional desktop software. Written 2026-10-29. Nothing here is built yet.

---

## 1. Where the UI is today

Fingerino's whole UI is one OpenCV window: the camera feed, a status pill
("No hand"), the control-zone corner brackets, a side tab that opens the gesture
guide, and the guide itself — a Windows-11-styled settings page drawn pixel by
pixel with OpenCV and PIL in `ui_overlay.py`. `winui.py` and `macui.py` then
reach into the OS with ctypes to make that window borderless, topmost and
iconed.

That has carried the project well, and the HUD's details are thoughtful (text,
not just colour, for hand state; the guide follows Windows settings
vocabulary). But it is at its ceiling:

- **No real controls.** Every widget is hand-drawn. A Home window needs text
  fields, dropdowns, a shortcut recorder, scrolling lists, links — rebuilding
  each one in OpenCV is not a good use of time.
- **No accessibility.** Screen readers see one image. Keyboard focus, tab
  order, high-contrast mode and text scaling don't exist.
- **The window *is* the app.** Close it and Fingerino is gone; there is no
  presence when it isn't on screen, and no place for settings, help or updates.
- **Visually**, the raw webcam frame is the largest thing on screen, which makes
  the window read as a debug view. In low light (as in the screenshot this
  doc was prompted by) it is mostly noise, and the chrome on top of it — pill,
  brackets, side tab — has nothing consistent to sit on.

## 2. Recommendation in one paragraph

Yes, build a Home window — but think of Fingerino as **one app with three
surfaces**, not a launcher plus the current program. The **tray / menu-bar
icon** is how it lives in the background. The **HUD** shrinks to optional live
feedback. The **Home window** is where everything else goes: onboarding,
gestures and remapping, settings, what's new, premium. Double-clicking the
desktop icon still "just runs Fingerino": tracking starts, and Home opens only
on first run or when asked. Build it with **PySide6 (Qt 6)** using Qt Quick and
the FluentWinUI3 style on Windows. Do it in milestones (section 9), after the
Phase 2 gesture tests exist.

---

## 3. The three surfaces

### 3.1 Tray icon (Windows) / menu bar extra (macOS)

Always present while Fingerino runs. This is what professional background tools
do, and it answers "is it running?" without a window.

Menu, in this order:

| Item | Notes |
| --- | --- |
| **Pause tracking** / **Resume tracking** | The single most-used action. Mirrors the global hotkey. |
| **Show camera preview** | Toggles the HUD. Checkmark when on. |
| **Open Fingerino** | Opens Home. Also what a left click does on Windows. |
| — | |
| **Quit Fingerino** | Releases the camera and any held mouse button. |

Icon reflects state: tracking / paused / camera unavailable. Tooltip says the
same in words ("Fingerino — tracking", "Fingerino — paused").

**Platform rules that apply:**

- *Windows:* icons go to the overflow area by default unless the user promotes
  them, so **never rely on the tray icon being visible** — the global hotkey and
  the Start-menu shortcut must also work. Supply the icon at 16 and 32 px (and
  scale variants). Use toast notifications sparingly; users can suppress all of
  an app's notifications, and noisy apps get suppressed. Microsoft's own tray
  guidance dates from Windows 7 but these points still hold.
- *macOS (HIG, "Menu bar extras"):* use a monochrome template symbol so the
  system can tint it for light/dark bars (menu bar height is 24 pt). **Show a
  menu, not a popover.** **Let people decide** whether the menu bar extra is
  shown — a setting in Settings, offered once during onboarding. Don't rely on
  it being visible (the system hides extras when crowded); offer the same
  actions in a **Dock menu** too.

### 3.2 The HUD (today's window, demoted)

Keep it — while learning gestures, seeing what the tracker sees is genuinely
useful — but make it optional and quieter:

- **Default after onboarding: compact.** A small rounded pill (hand state +
  tracking state), with the camera preview behind a toggle. Most experienced
  users never need to see themselves.
- **When the preview is shown:** darken and desaturate the video so landmarks
  and chrome read clearly on top; draw the hand skeleton; 8 px corner radius
  and a soft shadow so it sits on the desktop like a Windows 11 flyout rather
  than a pasted rectangle.
- **The gesture guide moves to Home.** The HUD shows status, not documentation.
- Position remembered; draggable; respects the existing "yield to menus and
  Alt+Tab" topmost logic.

### 3.3 The Home window

A normal, resizable window with a left navigation pane (Windows) or toolbar
panes (macOS — see 6.2). Pages:

| Page | Contents |
| --- | --- |
| **Home** | Big Start / Pause button, live status (camera, hand seen, gestures on), camera picker if more than one, a "Try a gesture" tile, a small What's new card. |
| **Gestures** | Every gesture as a card: sketch, name, how to do it, on/off toggle, and the action it triggers (dropdown). "Test" opens live detection for that one gesture. See section 5. |
| **Tutorial** | The interactive onboarding, re-runnable at any time. |
| **What's new** | Release notes for the installed version; update available banner if update checks are on. |
| **Premium** | Only if and when premium exists (section 7). |
| **Settings** | Pinned to the bottom of the nav pane (Microsoft guidance). Section 6.3. |

### 3.4 "One click from the desktop"

- The Start-menu / desktop / Dock icon launches Fingerino **and starts tracking
  immediately** — exactly today's behaviour from the user's point of view.
- **First run** opens Home on the onboarding flow instead.
- After that, Home opens only from the tray, the Dock, or launching a second
  time while already running (single instance: the second launch just brings
  Home forward).
- A **global hotkey** (default e.g. Ctrl+Alt+F, changeable) toggles tracking.
  This is the escape hatch for when the tray icon is hidden and the hand
  gestures are misbehaving.
- **Start at login**: a setting, **off by default**, offered once at the end of
  onboarding. An app that reads the webcam must not silently auto-start.
- Keep the CLI (`fingerino`, `--camera`, `--selftest`, `--debug`) working.

---

## 4. Onboarding

Apple's HIG onboarding guidance, which matches what good Windows apps do:

- *"Design a flow that's fast, fun, and optional."* Onboarding happens after
  launch, not as part of it.
- *"Teach through interactivity"* — people retain what they perform, not what
  they read.
- If a tutorial is skippable, *don't show it again on later launches*, but keep
  it easy to find (our Tutorial page).
- *"Postpone nonessential setup"*; ship good defaults.
- *"Prefer letting people experience your app … before prompting them for
  ratings or purchases."*
- If the app can't work without a permission, it is fine to request it during
  onboarding, with the reason explained.

Proposed flow — five screens, every one skippable except the camera step:

1. **Welcome.** One line on what Fingerino does, one line on privacy ("Video is
   processed on this computer and never leaves it").
2. **Camera.** A pre-permission explainer, then the system prompt (rules
   below). Then the live preview with a lighting / framing hint ("Sit so your
   hand is inside the frame").
3. **Practice: move and click.** A target on screen; move the cursor to it with
   the thumb, click it by pointing. Celebrate success; offer "Skip" throughout.
4. **Practice: scroll and swipe.** Same pattern.
5. **Done.** Offer: show menu bar / tray icon, start at login (unchecked),
   global hotkey reminder. "Open the guide any time from Home."

**Permission pre-alert rules (Apple HIG, "Privacy").** These apply to the
camera on both platforms and to Accessibility on macOS:

- The custom explainer has **one button**, labelled **Continue** or **Next** —
  never "Allow", and no Cancel or close button. Its only job is to open the
  system prompt.
- Purpose string: a brief, active, specific sentence with a full stop, e.g.
  *"Fingerino uses the camera to follow your hand and turn gestures into mouse
  movement."* — not "Camera access is needed for a better experience."
- If permission is denied, don't nag. Show what's missing and a button that
  opens the right OS settings page (`macui.open_accessibility_settings` already
  does this for Accessibility).

---

## 5. Gestures and remapping

The Xbox Accessibility Guideline 107 ("Input") is the best public standard for
remapping, and its principles carry over: let people operate the product with
the inputs of their choice, let **every action be reassigned**, and look for
**timing barriers** (fast inputs, holds of 2–3 s or more) and offer
adjustments. For Fingerino that means:

- **Per-gesture on/off** — already exists in the guide; moves to Home.
- **Action per gesture.** The action is chosen from a library:
  - Built-ins: click, right-click, drag, scroll, show desktop, restore, switch
    window, pause tracking.
  - **Keyboard shortcut** — with a "press the keys" recorder, not a text field.
  - Media keys (play/pause, volume).
  - Open an app or URL (later).
- **Timing is a setting, not a constant.** Hold-to-drag duration
  (`DRAG_HOLD_S`), click grace periods and swipe sensitivity become sliders
  with a "Default" reset. For people with tremor or limited mobility this is
  what makes the app usable at all.
- **Conflicts are caught on save**: two gestures bound to the same action is
  fine; one gesture bound to two actions is not possible by construction.
- **Test in place.** Each gesture card has a Test button that shows live
  detection and a confidence bar for that gesture only.
- **Reset all to defaults**, always visible at the bottom of the page.

The code is already shaped for this: `system_actions.py` isolates actions,
and `config.GESTURE_GROUPS` already drives the guide. What's missing is a
user-settings file (JSON in the existing cache directory) layered over the
`config.py` defaults, and a dispatch table in `main.py` instead of the
hard-wired `system_actions.*` calls.

---

## 6. Platform guidelines that apply

### 6.1 Windows 11 (Fluent)

- **Principles:** Microsoft names five — Effortless, Calm, Personal, Familiar,
  Complete + Coherent. "Calm" is the relevant one for an always-on app: no
  unnecessary motion, colour or notifications.
- **Material:** **Mica** for the main window background (opaque, tinted by the
  wallpaper). **Acrylic** only for transient surfaces such as menus and
  flyouts.
- **Type and icons:** **Segoe UI Variable** and **Segoe Fluent Icons**.
- **Geometry:** **8 px** corner radius for top-level containers (windows,
  dialogs, flyouts — so also the HUD), **4 px** for in-page controls (buttons,
  cards).
- **Theme:** follow the system by default. If offered as a setting, a combo box
  with exactly *Light / Dark / Use system setting*, plus a "Windows color
  settings" link (`ms-settings:colors`).

### 6.2 macOS

- Settings opens from the app menu with **⌘,**, titled "Fingerino Settings"
  (or the pane name when there are panes), toolbar panes that can't be
  customised, minimise/zoom buttons dimmed, last-viewed pane restored.
- Don't put a settings button in a window toolbar.
- Respect system-wide settings (accessibility, scrolling direction); don't
  duplicate them as app settings.
- Menu bar extra rules: section 3.1.

### 6.3 Settings page (both platforms)

From Microsoft's "Guidelines for app settings" (updated 2026) and Apple's HIG
"Settings", which agree on almost everything:

- **Few settings, good defaults.** Microsoft suggests four or five per group;
  Apple: "minimize the number of settings you offer."
- **Changes apply immediately — no Save button.**
- **Single scrolling column, max width ~1000–1100 px**, related settings
  grouped under short one-word section headers.
- **Controls:** toggle switch for on/off; radio buttons for up to five
  mutually exclusive options; combo box for more; hyperlink for navigation;
  button for immediate actions.
- **Same settings in every context.** If one doesn't apply right now, disable it
  and say why in its description, don't hide it.
- **Advanced options go in an expander**, nested at most one level.
- **About** at the bottom: app name, icon and version in the collapsed header;
  inside it, links to the website, bug reports, licences, privacy statement.
- Task-specific options (e.g. turning one gesture off) belong where the task is
  (the Gestures page), not in Settings.

Proposed Settings groups:

| Group | Settings |
| --- | --- |
| **General** | Start tracking when Fingerino opens · Start at login · Show tray / menu bar icon · Global hotkey |
| **Camera** | Camera (combo) · Show camera preview · Mirror preview |
| **Pointer** | Cursor speed · Smoothing · Control zone size (expander: advanced filter values) |
| **Appearance** | Theme (Light / Dark / Use system setting) · HUD size |
| **Privacy** | Check for updates (off until the user turns it on; says exactly what is sent) |
| **About** | Version, licences, privacy, report a problem (opens the bug template), run self-test |

### 6.4 Accessibility (both platforms)

- Text contrast at least **4.5:1**, UI component and focus-ring contrast at
  least **3:1** (WCAG 2.2, SC 1.4.3 and 1.4.11).
- **Fully usable with keyboard and mouse.** People will install Fingerino
  before they can use gestures, and will need Home when gestures misbehave.
- Every control has an accessible name (Qt exposes these to Narrator and
  VoiceOver).
- Respect **high contrast**, **reduce motion** and **text scaling**.
- Never use colour as the only signal (the HUD pill already does this right).

---

## 7. Premium

Not a UI question first — a trust question. Today's promise, in the README and
`SECURITY.md`, is "no network after the model download, no telemetry, no
account". Premium must not quietly break that.

- **Licence check that works offline.** A signed licence key verified locally
  (public key in the app), not a phone-home on every launch. One network call
  at activation is acceptable if the Privacy section says so.
- **Use a merchant of record** — Paddle or Lemon Squeezy — so VAT and sales tax
  across countries are handled for you. Both charge about 5% + $0.50 per
  sale, with no monthly fee. Lemon Squeezy was acquired by Stripe in 2024; check
  each one's licence-key features before choosing.
- **What to sell — a caution.** Remapping and timing adjustments are
  accessibility features (section 5); putting them behind a paywall would be
  the wrong place to charge. Better candidates: per-app gesture profiles,
  custom gestures, extra action types, multiple cameras or hands.
- **When to ask:** after people have used the app (Apple HIG), never in
  onboarding. A Premium page in Home and a quiet "Pro" badge on locked
  features are enough.

---

## 8. Technology

**Recommended: PySide6 (Qt 6), Qt Quick + Qt Quick Controls.**

- Same language, runs in the same process as the tracker; no second runtime.
- **FluentWinUI3 style** (Qt 6.8+) gives Windows 11 looking controls that follow
  the system accent colour; the macOS style on Mac. Qt's own docs say the style
  is still under development and some controls aren't covered yet, so check
  the control list against the pages above before committing.
- Built-in tray icon (`QSystemTrayIcon`), global shortcuts via platform hooks,
  frameless, translucent, always-on-top windows, high-DPI, dark mode,
  accessibility. That means the ctypes code in `winui.py` and `macui.py`
  could eventually shrink a lot, but that is a later, optional step.
- **Licensing:** PySide6 is LGPLv3, which allows closed-source and paid
  distribution provided Qt is dynamically linked and replaceable, and the
  LGPL notice and source offer ship with it. The PyInstaller *onedir* build
  already used here fits that. Add Qt to `notices`. Get a proper check before
  charging money; this is not legal advice.
- **Cost:** a larger installer (Qt adds tens of MB) and a new dependency to pin
  in `requirements-build.txt`.

**Runner-up: pywebview** (HTML/CSS UI in the system web view). Much lighter and
easy to make look modern, but showing a live 30 fps camera feed through a web
view is awkward, and you'd be maintaining a web front end inside a Python app.
Fine for Home alone; worse for one coherent app.

**Not recommended:** Tkinter (looks dated, weak accessibility), continuing to
hand-draw in OpenCV, or a separate Electron / Tauri app (a second runtime and a
second build pipeline for one developer).

---

## 9. Milestones

Do the release-readiness Phase 2 gesture tests first: milestones 2–4 touch the
main loop, and that is the code the tests protect.

1. **Tray + settings file.** Tray icon with the four menu items, global hotkey,
   single instance, user settings JSON over `config.py` defaults. No new
   window yet. Small, and it already makes Fingerino feel like an installed
   app.
2. **Home shell + Settings + Gestures (on/off).** PySide6 window, nav pane,
   Settings page per 6.3, Gestures page moving the guide out of the HUD. HUD
   gains the compact mode.
3. **Onboarding** per section 4.
4. **Remapping** per section 5.
5. **What's new + update check** (opt-in; ties to Phase 7 of the
   release-readiness plan).
6. **Premium**, only once people use the free version.

---

## Sources

- Microsoft — [Guidelines for app settings](https://learn.microsoft.com/en-us/windows/apps/design/app-settings/guidelines-for-app-settings)
- Microsoft — [Windows 11 design principles](https://learn.microsoft.com/en-my/WINDOWS/APPS/design/design-principles)
- Microsoft — [Geometry in Windows 11](https://learn.microsoft.com/th-th/windows/apps/design/signature-experiences/geometry)
- Microsoft — [Windows app best practices](https://learn.microsoft.com/windows/apps/get-started/best-practices)
- Microsoft — [Notification area (Win32 UX guide)](https://learn.microsoft.com/en-ie/Windows/Win32/uxguide/winenv-notification)
- Microsoft — [Xbox Accessibility Guideline 107: Input](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/107)
- Apple HIG — [The menu bar (menu bar extras)](https://developer.apple.com/design/human-interface-guidelines/the-menu-bar)
- Apple HIG — [Onboarding](https://developer.apple.com/design/human-interface-guidelines/onboarding)
- Apple HIG — [Privacy (requesting permission)](https://developer.apple.com/design/human-interface-guidelines/privacy)
- Apple HIG — [Settings](https://developer.apple.com/design/human-interface-guidelines/settings)
- Qt — [FluentWinUI3 Style](https://doc.qt.io/QT-6/qtquickcontrols-fluentwinui3.html), [Qt for Python commercial use](https://doc.qt.io/qtforpython-6/commercial/index.html)
- Python GUIs — [PyQt6 vs PySide6 licensing](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/)
- Merchant-of-record comparisons (vendor-adjacent, treat with care) — [Dodo Payments](https://dodopayments.com/blogs/paddle-vs-lemon-squeezy/), [apicalculators.com](https://apicalculators.com/compare/paddle-vs-lemonsqueezy)
- W3C — [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
