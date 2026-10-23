import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from excalidraw_generator.storage import StorageError, publish_scene


SCENE = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}, "files": {}}


def test_publish_roundtrip(tmp_path):
    result = publish_scene(SCENE, tmp_path, "Local/Work/excalidraw")
    assert result["relative_path"] == f"Local/Work/excalidraw/{result['filename']}"
    assert result["filename"].endswith(".excalidraw")
    assert result["element_count"] == 0
    assert json.loads((tmp_path / result["filename"]).read_text()) == SCENE


def test_dev_prefix_and_generated_name(tmp_path):
    result = publish_scene(SCENE, tmp_path, "Local/Work/excalidraw-dev")
    assert result["relative_path"].startswith("Local/Work/excalidraw-dev/")
    assert ".." not in result["filename"]


def test_two_concurrent_writers_do_not_overwrite(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish_scene(SCENE, tmp_path, "Local/Work/excalidraw"), range(2)))
    assert results[0]["filename"] != results[1]["filename"]
    assert len(list(tmp_path.iterdir())) == 2


def test_existing_target_is_not_overwritten(tmp_path, monkeypatch):
    import excalidraw_generator.storage as storage
    monkeypatch.setattr(storage, "_filename", lambda: "same.excalidraw")
    target = tmp_path / "same.excalidraw"
    target.write_text("original")
    with pytest.raises(StorageError):
        publish_scene(SCENE, tmp_path, "Local/Work/excalidraw")
    assert target.read_text() == "original"
    assert list(tmp_path.iterdir()) == [target]


def test_missing_or_symlink_directory(tmp_path):
    with pytest.raises(StorageError):
        publish_scene(SCENE, tmp_path / "missing", "Local/Work/excalidraw")
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(StorageError):
        publish_scene(SCENE, link, "Local/Work/excalidraw")
    assert list(tmp_path.iterdir()) == [link]


def test_write_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    import excalidraw_generator.storage as storage
    monkeypatch.setattr(storage.os, "link", lambda *_: (_ for _ in ()).throw(OSError("disk error")))
    with pytest.raises(StorageError):
        publish_scene(SCENE, tmp_path, "Local/Work/excalidraw")
    assert list(tmp_path.iterdir()) == []
