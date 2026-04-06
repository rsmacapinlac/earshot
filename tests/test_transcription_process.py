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

    def _mock_ffmpeg(self, returncode: int = 0) -> MagicMock:
        """ffmpeg Popen mock: no stdout pipe (writes to temp WAV file by path)."""
        mock = MagicMock()
        mock.poll.side_effect = [None, returncode]
        mock.returncode = returncode
        mock.wait.return_value = returncode
        return mock

    def _mock_whisper(self, stdout: bytes = b"", returncode: int = 0) -> MagicMock:
        mock = MagicMock()
        mock.poll.side_effect = [None, returncode]
        mock.returncode = returncode
        mock.stdout.read.return_value = stdout
        mock.wait.return_value = returncode
        return mock

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
        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=FileNotFoundError("ffmpeg"),
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_ffmpeg_nonzero_exit_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(returncode=1)],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_whisper_nonzero_exit_returns_none(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(), self._mock_whisper(returncode=1)],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())
        assert result is None

    def test_cancel_during_ffmpeg_terminates_process(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        cancel = threading.Event()
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.wait.return_value = 0

        def _poll():
            _poll.calls += 1
            if _poll.calls == 2:
                cancel.set()
            return None
        _poll.calls = 0
        mock_ffmpeg.poll.side_effect = _poll

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[mock_ffmpeg],
        ):
            result = transcribe_session(d, model, threads=1, cancel=cancel)

        assert result is None
        mock_ffmpeg.terminate.assert_called_once()

    def test_cancel_during_whisper_terminates_process(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        cancel = threading.Event()
        mock_whisper = MagicMock()
        mock_whisper.wait.return_value = 0

        def _poll():
            _poll.calls += 1
            if _poll.calls == 2:
                cancel.set()
            return None
        _poll.calls = 0
        mock_whisper.poll.side_effect = _poll

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(), mock_whisper],
        ):
            result = transcribe_session(d, model, threads=1, cancel=cancel)

        assert result is None
        mock_whisper.terminate.assert_called_once()

    def test_parses_segments_from_stdout(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        stdout_text = (
            b"[00:00:00.000 --> 00:00:05.320]  Hello there.\n"
            b"[00:00:05.320 --> 00:00:10.440]  How are you today?\n"
            b"some other line without a timestamp\n"
        )

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[
                self._mock_ffmpeg(),
                self._mock_whisper(stdout=stdout_text),
            ],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result is not None
        assert len(result) == 2
        assert result[0] == {"from_ms": 0, "to_ms": 5_320, "text": "Hello there."}
        assert result[1] == {"from_ms": 5_320, "to_ms": 10_440, "text": "How are you today?"}

    def test_empty_stdout_returns_empty_list(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(), self._mock_whisper()],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result == []

    def test_blank_text_segments_excluded(self, tmp_path):
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[
                self._mock_ffmpeg(),
                self._mock_whisper(stdout=b"[00:00:00.000 --> 00:00:02.000]  \n"),
            ],
        ):
            result = transcribe_session(d, model, threads=1, cancel=threading.Event())

        assert result == []

    def test_uses_concat_demuxer_not_concat_protocol(self, tmp_path):
        """ffmpeg must use -f concat demuxer, not the concat: protocol.

        The concat: protocol raw-concatenates bytes which corrupts OGG/Opus
        container streams.  The concat demuxer opens each file properly.
        """
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(), self._mock_whisper()],
        ) as mock_popen:
            transcribe_session(d, model, threads=1, cancel=threading.Event())

        ffmpeg_args = mock_popen.call_args_list[0][0][0]
        assert "-f" in ffmpeg_args
        concat_idx = ffmpeg_args.index("-f")
        assert ffmpeg_args[concat_idx + 1] == "concat"
        assert not any(a.startswith("concat:") for a in ffmpeg_args)

    def test_whisper_reads_from_wav_file_not_stdin(self, tmp_path):
        """whisper-cli must be given a real file path, not /dev/stdin.

        whisper-cli uses fseek() internally when reading WAV, which fails on
        non-seekable file descriptors like /dev/stdin.
        """
        d = self._make_session(tmp_path)
        model = self._make_model(tmp_path)

        with patch(
            "earshot.transcription.process.subprocess.Popen",
            side_effect=[self._mock_ffmpeg(), self._mock_whisper()],
        ) as mock_popen:
            transcribe_session(d, model, threads=1, cancel=threading.Event())

        whisper_args = mock_popen.call_args_list[1][0][0]
        f_idx = whisper_args.index("-f")
        wav_arg = whisper_args[f_idx + 1]
        assert wav_arg != "/dev/stdin"
        assert wav_arg.endswith(".wav")
