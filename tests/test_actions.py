"""Bindable actions: building them, storing them, and carrying them out.

The model and actions.json are standard library only and run in the
dependency-free CI job; the executor tests need pynput and replace the
keyboard and process launching with recorders.
"""

import json

import pytest

from fingerino import actions
from fingerino.actions import Action, Registry, make_action, normalize_combo

# ---------------------------------------------------------------------------
# Shortcuts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("typed", "stored"), [
    ("ctrl+shift+k", "ctrl+shift+k"),
    ("Shift + Ctrl + K", "ctrl+shift+k"),
    ("<cmd>+<alt>+space", "alt+cmd+space"),
    ("Control+Option+Return", "ctrl+alt+enter"),
    ("f5", "f5"),
    ("ctrl+/", "ctrl+/"),
])
def test_shortcuts_are_normalised(typed, stored):
    assert normalize_combo(typed) == stored


@pytest.mark.parametrize("typed", ["", "ctrl", "ctrl+shift", "ctrl+a+b", "ctrl+banana",
                                   "ctrl+ctrl+x"])
def test_bad_shortcuts_are_refused(typed):
    assert normalize_combo(typed) is None


def test_shortcut_labels_read_naturally():
    assert actions.combo_label("ctrl+shift+k") == "Ctrl+Shift+K"
    assert actions.combo_label("alt+page_up") == "Alt+Page Up"


# ---------------------------------------------------------------------------
# make_action
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("kind", "target", "label"), [
    ("hotkey", "ctrl+alt+t", "Ctrl+Alt+T"),
    ("media", "play_pause", "Play / pause"),
    ("open_app", "/Applications/Spotify.app", "Open Spotify"),
    ("open_app", r"C:\Program Files\Spotify\Spotify.exe", "Open Spotify"),
    ("open", "https://open.spotify.com/playlist/37i9", "Open spotify.com"),
    ("open", "https://www.youtube.com/", "Open youtube.com"),
    ("open", "spotify:playlist:37i9", "Open Spotify"),
    ("open", "/home/me/notes.txt", "Open notes.txt"),
    ("open", r"C:\Users\me\notes.txt", "Open notes.txt"),
    ("command", "echo hi", "Run command"),
])
def test_each_kind_gets_a_readable_label(kind, target, label):
    action = make_action(kind, target)
    assert isinstance(action, Action)
    assert action.label == label == action.toast
    assert action.kind == kind
    assert action.approved


def test_a_name_replaces_the_label():
    action = make_action("media", "next", "Skip")
    assert action.label == "Skip" and action.toast == "Skip"


def test_builtins_come_back_as_themselves():
    assert make_action("builtin", "minimize_all") is actions.BUILTIN_ACTIONS["minimize_all"]


@pytest.mark.parametrize(("kind", "target"), [
    ("builtin", "format_disk"), ("hotkey", "ctrl"), ("media", "louder"),
    ("open_app", ""), ("open", "  "), ("command", ""), ("teleport", "x"),
])
def test_invalid_actions_come_back_as_messages(kind, target):
    assert isinstance(make_action(kind, target), str)


def test_every_new_action_has_its_own_id():
    assert make_action("media", "next").id != make_action("media", "next").id


# ---------------------------------------------------------------------------
# Registry editing
# ---------------------------------------------------------------------------

def test_bind_reset_and_do_nothing():
    reg = Registry()
    music = make_action("open", "https://open.spotify.com/x")
    reg.bind("shaka", music)
    assert reg.action_for("shaka") is music
    reg.bind("shaka", None)
    assert reg.action_for("shaka") is None
    reg.reset("shaka")
    assert reg.action_for("shaka").id == "open_ai_chat"


def test_replaced_actions_are_not_kept_around():
    reg = Registry()
    first = make_action("media", "next")
    reg.bind("shaka", first)
    reg.bind("shaka", make_action("media", "previous"))
    assert first.id not in reg.actions
    assert set(actions.BUILTIN_ACTIONS) <= set(reg.actions)


def test_forgetting_a_custom_sign_drops_its_binding():
    reg = Registry()
    reg.bind("sign-1", make_action("media", "mute"))
    reg.forget("sign-1")
    assert "sign-1" not in reg.bindings
    assert reg.action_for("sign-1") is None


# ---------------------------------------------------------------------------
# actions.json
# ---------------------------------------------------------------------------

def test_round_trip(tmp_path):
    reg = Registry()
    reg.bind("shaka", make_action("open", "https://open.spotify.com/x", "Music"))
    reg.bind("flat_right", make_action("hotkey", "ctrl+alt+t"))
    reg.bind("flat_left", None)
    assert actions.save(str(tmp_path), reg)
    back = actions.load(str(tmp_path))
    assert back.action_for("shaka").label == "Music"
    assert back.action_for("shaka").target == "https://open.spotify.com/x"
    assert back.action_for("flat_right").target == "ctrl+alt+t"
    assert back.action_for("flat_left") is None
    assert back.action_for("flat_down").id == "minimize_all"


def test_only_changes_from_the_defaults_are_written():
    data = Registry().to_json()
    assert data["actions"] == [] and data["bindings"] == {}


def test_missing_and_corrupt_files_give_the_defaults(tmp_path):
    assert actions.load(str(tmp_path)).bindings == actions.DEFAULT_BINDINGS
    (tmp_path / actions.FILENAME).write_text("{nope", encoding="utf-8")
    assert actions.load(str(tmp_path)).bindings == actions.DEFAULT_BINDINGS


def test_bad_entries_are_skipped_one_by_one():
    data = {
        "actions": [
            {"id": "user-ok", "kind": "media", "target": "mute", "label": "Mute",
             "approved": True},
            {"id": "user-bad", "kind": "teleport", "target": "x", "label": "X"},
            {"id": "minimize_all", "kind": "hotkey", "target": "a", "label": "Hijack"},
            "not a dict",
            {"id": 3},
        ],
        "bindings": {"shaka": "user-ok", "flat_up": "user-missing", "flat_left": None},
    }
    reg = Registry.from_json(data)
    assert reg.action_for("shaka").id == "user-ok"
    assert reg.action_for("flat_up").id == "restore_all"       # fell back
    assert reg.action_for("flat_left") is None
    assert reg.actions["minimize_all"].label == "Minimize"      # not overwritten
    assert "user-bad" not in reg.actions


def test_a_stored_command_without_approval_loads_unapproved():
    # Fail closed: anything other than an explicit True is "not approved".
    for approved in (False, "yes", None, 1):
        data = {"actions": [{"id": "user-c", "kind": "command", "target": "rm -rf ~",
                             "label": "Clean", "approved": approved}],
                "bindings": {"shaka": "user-c"}}
        assert Registry.from_json(data).action_for("shaka").approved is False


def test_save_reports_an_unwritable_folder(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    assert actions.save(str(blocker / "sub"), Registry()) is False


def test_describe_round_trips_through_the_editor():
    named = make_action("media", "next", "Skip")
    assert actions.describe(named) == {"kind": "media", "target": "next",
                                       "name": "Skip", "label": "Skip"}
    plain = make_action("media", "next")
    assert actions.describe(plain)["name"] == ""
    assert actions.describe(None)["label"] == "Does nothing"


def test_json_is_plain_and_readable(tmp_path):
    reg = Registry()
    reg.bind("shaka", make_action("command", "echo hi"))
    actions.save(str(tmp_path), reg)
    data = json.loads((tmp_path / actions.FILENAME).read_text(encoding="utf-8"))
    assert data["schema"] == actions.SCHEMA
    assert data["actions"][0]["approved"] is True


# ---------------------------------------------------------------------------
# Carrying them out (pynput needed; nothing real is pressed or launched)
# ---------------------------------------------------------------------------

@pytest.fixture
def system(monkeypatch):
    sa = pytest.importorskip("fingerino.system_actions")
    log = []

    class Keyboard:
        def press(self, k):
            log.append(("press", k))

        def release(self, k):
            log.append(("release", k))

    monkeypatch.setattr(sa, "_kb", Keyboard())
    monkeypatch.setattr(sa, "open_target", lambda t: log.append(("open", t)))
    monkeypatch.setattr(sa, "run_command", lambda c: log.append(("command", c)))
    return sa, log


def test_shortcut_presses_then_releases_in_reverse(system):
    sa, log = system
    sa.perform(make_action("hotkey", "ctrl+shift+k"))
    k = sa.Key
    assert log == [("press", k.ctrl), ("press", k.shift), ("press", "k"),
                   ("release", "k"), ("release", k.shift), ("release", k.ctrl)]


def test_media_key_is_tapped(system):
    sa, log = system
    sa.perform(make_action("media", "play_pause"))
    assert log == [("press", sa.Key.media_play_pause), ("release", sa.Key.media_play_pause)]


@pytest.mark.parametrize("name", list(actions.MEDIA_KEYS))
def test_every_media_key_exists_in_pynput(system, name):
    sa, _ = system
    assert hasattr(sa.Key, sa._MEDIA[name])


def test_open_and_command(system):
    sa, log = system
    sa.perform(make_action("open", "https://example.com"))
    sa.perform(make_action("open_app", "/Applications/Spotify.app"))
    sa.perform(make_action("command", "echo hi"))
    assert log == [("open", "https://example.com"), ("open", "/Applications/Spotify.app"),
                   ("command", "echo hi")]


def test_an_unapproved_command_never_runs(system):
    sa, log = system
    action = make_action("command", "echo hi", approved=False)
    with pytest.raises(PermissionError):
        sa.perform(action)
    assert log == []


def test_builtins_still_run_through_perform(system, monkeypatch):
    sa, log = system
    monkeypatch.setitem(sa.BUILTIN, "open_ai_chat", lambda: log.append("chat"))
    sa.perform(actions.BUILTIN_ACTIONS["open_ai_chat"])
    assert log == ["chat"]


def test_open_target_never_uses_a_shell(monkeypatch):
    sa = pytest.importorskip("fingerino.system_actions")
    calls = []
    monkeypatch.setattr(sa.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sa.sys, "platform", "linux")
    monkeypatch.setattr(sa, "_IS_MAC", False)
    sa.open_target("https://example.com/?q=1; rm -rf ~")
    (args, kw), = calls
    assert args[0] == ["xdg-open", "https://example.com/?q=1; rm -rf ~"]
    assert not kw.get("shell")
