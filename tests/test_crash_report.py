"""The crash handler.

A packaged build has no console, so without this an unhandled exception makes
the window vanish leaving nothing on screen and nothing on disk. These tests
pin the parts that make a crash reportable.
"""

import pytest

pytest.importorskip("cv2", exc_type=ImportError,
                    reason="main imports OpenCV")

from fingerino import main as fmain


@pytest.fixture
def quiet_dialogs(monkeypatch):
    """Capture the dialog text instead of putting a modal box on screen."""
    shown = []
    monkeypatch.setattr(fmain.winui, "alert", lambda title, text: shown.append(text))
    monkeypatch.setattr(fmain.macui, "alert", lambda title, text: None)
    return shown


def test_a_crash_is_reported_not_swallowed(tmp_path, monkeypatch, quiet_dialogs):
    monkeypatch.setattr(fmain, "cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fmain, "_run", lambda: 1 / 0)

    assert fmain.main() == 1

    report = (tmp_path / "crash.txt").read_text(encoding="utf-8")
    assert "ZeroDivisionError" in report
    assert "Traceback" in report
    assert fmain.__version__ in report          # which build broke
    assert "frozen:" in report                  # packaged or from source

    assert quiet_dialogs, "the user was never told"
    assert "crash.txt" in quiet_dialogs[0]      # ...and where to find it


def test_an_unwritable_cache_still_shows_the_dialog(monkeypatch, quiet_dialogs):
    # Never fail twice. If the report cannot be saved, the dialog is all the
    # user gets, so it still has to appear.
    def no_cache():
        raise OSError("read-only")

    monkeypatch.setattr(fmain, "cache_dir", no_cache)
    monkeypatch.setattr(fmain, "_run", lambda: 1 / 0)

    assert fmain.main() == 1
    assert quiet_dialogs
    assert "ZeroDivisionError" in quiet_dialogs[0]


def test_sys_exit_is_not_a_crash(monkeypatch, quiet_dialogs):
    # argparse --help and --version exit this way; they are not failures and
    # must not raise a crash dialog.
    def bail():
        raise SystemExit(0)

    monkeypatch.setattr(fmain, "_run", bail)
    with pytest.raises(SystemExit):
        fmain.main()
    assert not quiet_dialogs


def test_ctrl_c_is_not_a_crash(monkeypatch, quiet_dialogs):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(fmain, "_run", interrupt)
    assert fmain.main() == 130
    assert not quiet_dialogs
