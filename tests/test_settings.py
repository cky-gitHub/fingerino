"""settings.json: what survives a restart, and what a bad file can't break.

Standard library only, so this runs in the fast dependency-free CI job.
"""

import json

from fingerino import config, settings


def test_defaults_enable_every_gesture():
    s = settings.Settings()
    assert set(s.gestures) == {icon for icon, _ in config.GESTURE_TUTORIAL}
    assert all(s.gestures.values())
    assert s.onboarded is False
    assert s.start_on_open is False       # the camera stays off until Start


def test_round_trip(tmp_path):
    s = settings.Settings()
    s.gestures["shaka"] = False
    s.onboarded = True
    s.start_on_open = True
    assert settings.save(str(tmp_path), s)
    back = settings.load(str(tmp_path))
    assert back.gestures["shaka"] is False
    assert back.gestures["point"] is True
    assert back.onboarded is True
    assert back.start_on_open is True


def test_missing_file_gives_defaults(tmp_path):
    assert settings.load(str(tmp_path)) == settings.Settings()


def test_corrupt_file_gives_defaults(tmp_path):
    (tmp_path / settings.FILENAME).write_text("{not json", encoding="utf-8")
    assert settings.load(str(tmp_path)) == settings.Settings()


def test_wrong_types_fall_back_field_by_field(tmp_path):
    # One bad field must not throw away the good ones next to it.
    data = {"gestures": {"shaka": "no", "cross": False}, "onboarded": "yes",
            "hotkey": 42}
    (tmp_path / settings.FILENAME).write_text(json.dumps(data), encoding="utf-8")
    s = settings.load(str(tmp_path))
    assert s.gestures["shaka"] is True        # "no" is not a bool
    assert s.gestures["cross"] is False
    assert s.onboarded is False
    assert s.hotkey == settings.DEFAULT_HOTKEY


def test_unknown_gestures_are_dropped_and_new_ones_arrive_on():
    s = settings.Settings.from_json({"gestures": {"retired_gesture": False}})
    assert "retired_gesture" not in s.gestures
    assert all(s.gestures.values())


def test_save_leaves_no_temp_file(tmp_path):
    settings.save(str(tmp_path), settings.Settings())
    assert [p.name for p in tmp_path.iterdir()] == [settings.FILENAME]


def test_unwritable_folder_reports_failure(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    # A folder path that runs through a regular file can never be created.
    assert settings.save(str(blocker / "sub"), settings.Settings()) is False
