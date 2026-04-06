"""Tests for transcription subprocess invocation (FR-15)."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from earshot.transcription.process import _ts_to_ms, transcribe_session


class TestTsToMs:
    def test_zero(self):
        assert _ts_to_ms("00:00:00.000") == 0

    def test_seconds(self):
        assert _ts_to_ms("00:00:05.000") == 5_000

    def test_minutes(self):
        assert _ts_to_ms("00:02:05.000") == 125_000

    def test_hours(self):
        assert _ts_to_ms("01:01:01.001") == 3_661_001

    def test_milliseconds(self):
        assert _ts_to_ms("00:00:00.500") == 500


class TestTranscribeSession:
    def _make_session(self, root: Path) -> Path:
        d = root / "20260101T100000"
        d.mkdir()
        (d / "audio-001.opus").write_bytes(b"")
        return d

    def _make_model(self, root: Path) -> Path:
        m = root / "ggml-tiny.en-q5_1.bin"
        m.write_bytes(b"fake model")
        return m

    def test_no_opus_files_returns_none(self, tmp_path):
        d = tmp_path / "empty_session"
        d.mkdir()
        model = self._make_model(tmp_path)
        result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_missing_model_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        missing_model = tmp_path / "no_such_model.bin"
        result = transcribe_session(d, missing_model, threads=1, cancel=threading.Event())
        assert result is None

    def test_ffmpeg_not_found_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)
        with patch("earshot.transcription.process.subprocess.Popen", side_effect=FileNotFoundError("ffmpeg")):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_whisper_nonzero_exit_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        mock_ffmpeg = MagicMock()
        mock_ffmpeg.stdout = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        mock_whisper = MagicMock()
        mock_whisper.poll.side_effect = [None, 1]
        mock_whisper.returncode = 1
        mock_whisper.stdout.read.return_value = b""

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg, mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_cancel_event_terminates_processes(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        cancel = threading.Event()

        mock_ffmpeg = MagicMock()
        mock_ffmpeg.stdout = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        def _poll_side_effect():
            """Return None (running) twice, then set cancel to simulate button press."""
            _poll_side_effect.calls += 1
            if _poll_side_effect.calls == 2:
                cancel.set()
            return None  # always running; cancel event will stop the loop
        _poll_side_effect.calls = 0

        mock_whisper = MagicMock()
        mock_whisper.poll.side_effect = _poll_side_effect
        mock_whisper.wait.return_value = 0

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg, mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=cancel)

        assert result is None
        mock_whisper.terminate.assert_called_once()
        mock_ffmpeg.terminate.assert_called_once()

    def test_parses_segments_from_stdout(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        stdout_text = (
            b"[00:00:00.000 --> 00:00:05.320]  Hello there.\n"
            b"[00:00:05.320 --> 00:00:10.440]  How are you today?\n"
            b"some other line without a timestamp\n"
        )

        mock_ffmpeg = MagicMock()
        mock_ffmpeg.stdout = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        mock_whisper = MagicMock()
        mock_whisper.poll.side_effect = [None, 0]
        mock_whisper.returncode = 0
        mock_whisper.stdout.read.return_value = stdout_text

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg, mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result is not None
        assert len(result) == 2
        assert result[0] == {"from_ms": 0, "to_ms": 5_320, "text": "Hello there."}
        assert result[1] == {"from_ms": 5_320, "to_ms": 10_440, "text": "How are you today?"}

    def test_empty_stdout_returns_empty_list(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        mock_ffmpeg = MagicMock()
        mock_ffmpeg.stdout = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        mock_whisper = MagicMock()
        mock_whisper.poll.side_effect = [None, 0]
        mock_whisper.returncode = 0
        mock_whisper.stdout.read.return_value = b""

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg, mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result == []

    def test_blank_text_segments_excluded(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        stdout_text = b"[00:00:00.000 --> 00:00:02.000]  \n"

        mock_ffmpeg = MagicMock()
        mock_ffmpeg.stdout = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        mock_whisper = MagicMock()
        mock_whisper.poll.side_effect = [None, 0]
        mock_whisper.returncode = 0
        mock_whisper.stdout.read.return_value = stdout_text

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg, mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result == []
