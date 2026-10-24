import os

import pytest

from smart_home_qa_harness.file_state import atomic_write_text


def test_atomic_write_replaces_target_with_complete_content(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("old")

    atomic_write_text(path, "new")

    assert path.read_text() == "new"
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_atomic_write_preserves_target_and_cleans_temporary_on_failure(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "state.json"
    path.write_text("original")

    def fail_replace(source, target):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        atomic_write_text(path, "incomplete update")

    assert path.read_text() == "original"
    assert list(tmp_path.glob(".state.json.*.tmp")) == []
