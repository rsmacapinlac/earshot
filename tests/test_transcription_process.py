"""Tests for transcription with faster_whisper (FR-15)."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from earshot.transcription.process import transcribe_session


class TestTranscribeSession:
    def _make_session(self, root: Path) -> Path:
        """Create a test session directory with a dummy session.wav file."""
        d = root / "20260101T100000"
        d.mkdir()
        (d / "session.wav").write_bytes(b"dummy wav data")
        return d

    def _make_model(self, segments: list | None = None) -> MagicMock:
        """Return a mock WhisperModel whose transcribe() returns given segments."""
        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_model.transcribe.return_value = (iter(segments or []), mock_info)
        return mock_model

    def _make_segment(self, start: float, end: float, text: str) -> MagicMock:
        """Create a mock faster_whisper Segment with start/end in seconds."""
        seg = MagicMock()
        seg.start = start
        seg.end = end
        seg.text = text
        return seg

    def test_no_session_wav_returns_none(self, tmp_path):
        d = tmp_path / "empty_session"
        d.mkdir()
        model = self._make_model()
        result = transcribe_session(d, model, cancel=threading.Event())
        assert result is None

    def test_cancel_before_transcribe_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model()

        cancel = threading.Event()
        cancel.set()

        result = transcribe_session(d, model, cancel=cancel)
        assert result is None

    def test_parses_segments_from_model(self, tmp_path):
        """Segments from model are converted from float seconds to int milliseconds."""
        d = self._make_session(tmp_path)
        segs = [
            self._make_segment(0.0, 5.32, "Hello there."),
            self._make_segment(5.32, 10.44, "How are you today?"),
        ]
        model = self._make_model(segs)

        result = transcribe_session(d, model, cancel=threading.Event())

        assert result is not None
        assert len(result) == 2
        assert result[0] == {"from_ms": 0, "to_ms": 5320, "text": "Hello there."}
        assert result[1] == {"from_ms": 5320, "to_ms": 10440, "text": "How are you today?"}

    def test_empty_segment_list_returns_empty(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model([])

        result = transcribe_session(d, model, cancel=threading.Event())

        assert result == []

    def test_blank_text_segments_excluded(self, tmp_path):
        d = self._make_session(tmp_path)
        segs = [self._make_segment(0.0, 2.0, "   ")]
        model = self._make_model(segs)

        result = transcribe_session(d, model, cancel=threading.Event())

        assert result == []

    def test_noise_tokens_filtered(self, tmp_path):
        """All four noise tokens are excluded from output."""
        d = self._make_session(tmp_path)
        segs = [
            self._make_segment(0.0, 1.0, "[BLANK_AUDIO]"),
            self._make_segment(1.0, 2.0, "[Music]"),
            self._make_segment(2.0, 3.0, "[Applause]"),
            self._make_segment(3.0, 4.0, "[Laughter]"),
            self._make_segment(4.0, 5.0, "Real speech"),
        ]
        model = self._make_model(segs)

        result = transcribe_session(d, model, cancel=threading.Event())

        assert len(result) == 1
        assert result[0]["text"] == "Real speech"

    def test_cancel_during_segment_iteration_returns_none(self, tmp_path):
        """Cancel event set during segment iteration stops and returns None."""
        d = self._make_session(tmp_path)
        cancel = threading.Event()

        # Create a lazy generator that sets cancel on second iteration
        def _lazy_segments():
            yield self._make_segment(0.0, 1.0, "Hello")
            cancel.set()
            yield self._make_segment(1.0, 2.0, "World")

        model = self._make_model()
        model.transcribe.return_value = (_lazy_segments(), MagicMock())

        result = transcribe_session(d, model, cancel=cancel)

        assert result is None

    def test_model_transcribe_exception_returns_none(self, tmp_path):
        """If model.transcribe() raises, return None."""
        d = self._make_session(tmp_path)
        model = MagicMock()
        model.transcribe.side_effect = RuntimeError("ctranslate2 error")

        result = transcribe_session(d, model, cancel=threading.Event())

        assert result is None

    def test_segment_iteration_exception_returns_none(self, tmp_path):
        """If segment iteration raises, return None."""
        d = self._make_session(tmp_path)
        model = self._make_model()

        def _bad_generator():
            yield self._make_segment(0.0, 1.0, "Hello")
            raise RuntimeError("segment iteration failed")

        model.transcribe.return_value = (_bad_generator(), MagicMock())

        result = transcribe_session(d, model, cancel=threading.Event())

        assert result is None
