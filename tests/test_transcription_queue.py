"""Tests for the implicit transcription queue (FR-14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from earshot.transcription.queue import pending_sessions


def _make_session(root: Path, name: str, *, wav: bool = True, transcript: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    if wav:
        (d / "session.wav").write_bytes(b"")
    if transcript:
        (d / "transcript.md").write_text("# done\n", encoding="utf-8")
    return d


class TestPendingSessions:
    def test_empty_dir_returns_empty(self, tmp_path):
        assert pending_sessions(tmp_path) == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert pending_sessions(tmp_path / "does_not_exist") == []

    def test_session_with_wav_and_no_transcript_is_pending(self, tmp_path):
        _make_session(tmp_path, "20260101T100000")
        result = pending_sessions(tmp_path)
        assert len(result) == 1
        assert result[0].name == "20260101T100000"

    def test_session_with_transcript_is_not_pending(self, tmp_path):
        _make_session(tmp_path, "20260101T100000", wav=True, transcript=True)
        assert pending_sessions(tmp_path) == []

    def test_session_without_wav_is_not_pending(self, tmp_path):
        _make_session(tmp_path, "20260101T100000", wav=False)
        assert pending_sessions(tmp_path) == []

    def test_sessions_returned_fifo(self, tmp_path):
        _make_session(tmp_path, "20260101T120000")
        _make_session(tmp_path, "20260101T100000")
        _make_session(tmp_path, "20260101T140000")
        result = pending_sessions(tmp_path)
        names = [d.name for d in result]
        assert names == ["20260101T100000", "20260101T120000", "20260101T140000"]

    def test_mixed_sessions_only_pending_returned(self, tmp_path):
        _make_session(tmp_path, "20260101T100000", wav=True, transcript=False)
        _make_session(tmp_path, "20260101T110000", wav=True, transcript=True)
        _make_session(tmp_path, "20260101T120000", wav=True, transcript=False)
        result = pending_sessions(tmp_path)
        names = [d.name for d in result]
        assert names == ["20260101T100000", "20260101T120000"]

    def test_non_directory_entries_ignored(self, tmp_path):
        (tmp_path / "stray_file.txt").write_text("x")
        _make_session(tmp_path, "20260101T100000")
        result = pending_sessions(tmp_path)
        assert len(result) == 1

    def test_session_with_wav_is_detected_as_pending(self, tmp_path):
        """Sessions with session.wav (and no transcript) are pending."""
        d = tmp_path / "20260101T100000"
        d.mkdir()
        (d / "session.wav").write_bytes(b"")
        result = pending_sessions(tmp_path)
        assert len(result) == 1
