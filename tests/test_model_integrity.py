"""The pinned-checksum path for the hand-landmark model.

These bytes are parsed by MediaPipe's TFLite interpreter in native code, so
"whatever the URL returned" is not an acceptable input. No network is used
here — only the verification logic around it.
"""

import hashlib
import re

import pytest

pytest.importorskip("mediapipe", exc_type=ImportError,
                    reason="hand_tracker imports mediapipe")

from fingerino import hand_tracker as ht


def test_the_pin_is_a_real_sha256():
    assert re.fullmatch(r"[0-9a-f]{64}", ht._MODEL_SHA256)


def test_the_download_has_a_timeout():
    # urlretrieve accepted none, which hung startup forever on a stalled
    # connection — with no console in a packaged build to say so.
    assert isinstance(ht._DOWNLOAD_TIMEOUT_S, (int, float))
    assert 0 < ht._DOWNLOAD_TIMEOUT_S <= 120


def test_sha256_helper_matches_hashlib(tmp_path):
    blob = b"fingerino" * 5000
    f = tmp_path / "blob.bin"
    f.write_bytes(blob)
    assert ht._sha256(str(f)) == hashlib.sha256(blob).hexdigest()


def test_a_bundled_model_that_fails_its_checksum_is_reported_not_replaced(tmp_path):
    # A bundled model came from the installer. Quietly downloading over it
    # would hide exactly the tampering this check exists to catch.
    bad = tmp_path / "hand_landmarker.task"
    bad.write_bytes(b"not a model")
    with pytest.raises(RuntimeError, match="does not match its expected checksum"):
        ht._ensure_model(str(bad), refetch=False)
    assert bad.exists()                      # left in place for inspection


def test_a_good_model_is_accepted_without_touching_the_network(tmp_path, monkeypatch):
    payload = b"pretend model"
    monkeypatch.setattr(ht, "_MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(ht, "_download", lambda *a, **k: pytest.fail("downloaded"))
    good = tmp_path / "hand_landmarker.task"
    good.write_bytes(payload)
    ht._ensure_model(str(good), refetch=True)          # must not raise


def test_a_download_that_fails_its_checksum_is_discarded(tmp_path, monkeypatch):
    target = tmp_path / "hand_landmarker.task"

    def fake_download(url, dest):
        with open(dest, "wb") as fh:
            fh.write(b"wrong bytes")
        return hashlib.sha256(b"wrong bytes").hexdigest()

    monkeypatch.setattr(ht, "_download", fake_download)
    with pytest.raises(RuntimeError, match="does not match its expected checksum"):
        ht._ensure_model(str(target), refetch=True)
    assert not target.exists()                         # never put in place
    assert not target.with_suffix(".task.part").exists()


@pytest.mark.parametrize("failure", [
    TimeoutError("The read operation timed out"),
    ConnectionResetError("reset"),
    __import__("urllib.error", fromlist=["URLError"]).URLError("no route"),
])
def test_a_failed_download_says_so_plainly_and_leaves_nothing(tmp_path, monkeypatch, failure):
    # What a user on a blocked or flaky network saw as a "crash".
    target = tmp_path / "hand_landmarker.task"

    def stalls(url, dest):
        with open(dest, "wb") as fh:
            fh.write(b"half a model")
        raise failure

    monkeypatch.setattr(ht, "_download", stalls)
    with pytest.raises(ht.ModelDownloadError, match="internet connection"):
        ht._ensure_model(str(target), refetch=True)
    assert not target.exists()
    assert not target.with_suffix(".task.part").exists()


def test_a_failed_download_ends_the_session_with_a_message_not_a_crash(monkeypatch):
    pytest.importorskip("cv2")
    pytest.importorskip("pynput")
    import sessionkit

    def offline():
        raise ht.ModelDownloadError("Couldn't download the hand model. Check your "
                                    "internet connection and press Start to try again.")

    world = sessionkit.run(monkeypatch, [[]] * 5, tracker=offline)
    assert world.error and "internet connection" in world.error
    assert world.frames_out == 0
