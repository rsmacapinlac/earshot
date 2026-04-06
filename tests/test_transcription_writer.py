"""Tests for transcript.md format correctness (FR-16)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from earshot.transcription.writer import _fmt_duration, _fmt_timestamp, write_transcript


class TestFormatTimestamp:
    def test_under_one_hour_uses_mm_ss(self):
        assert _fmt_timestamp(0) == "[00:00]"
        assert _fmt_timestamp(65_000) == "[01:05]"
        assert _fmt_timestamp(3599_000) == "[59:59]"

    def test_one_hour_or_more_uses_hh_mm_ss(self):
        assert _fmt_timestamp(3600_000) == "[01:00:00]"
        assert _fmt_timestamp(3661_000) == "[01:01:01]"
        assert _fmt_timestamp(7322_000) == "[02:02:02]"

    def test_milliseconds_truncated_not_rounded(self):
        # 1999 ms → 1s
        assert _fmt_timestamp(1999) == "[00:01]"


class TestFormatDuration:
    def test_seconds_only(self):
        assert _fmt_duration(5_000) == "0m 5s"

    def test_minutes_and_seconds(self):
        assert _fmt_duration(125_000) == "2m 5s"

    def test_hours_minutes_seconds(self):
        assert _fmt_duration(3_661_000) == "1h 1m 1s"

    def test_zero_duration(self):
        assert _fmt_duration(0) == "0m 0s"


class TestWriteTranscript:
    def _fixed_dt(self) -> datetime:
        return datetime(2026, 4, 1, 14, 30, 22)

    def test_creates_transcript_md(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        segments = [
            {"from_ms": 0, "to_ms": 5_000, "text": "Hello there."},
            {"from_ms": 5_000, "to_ms": 10_000, "text": "How are you?"},
        ]
        out = write_transcript(session_dir, segments, processed_at=self._fixed_dt())
        assert out == session_dir / "transcript.md"
        assert out.exists()

    def test_header_contains_session_date(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "# Recording — 2026-04-01 14:30:22" in text

    def test_no_device_field(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "**Device:**" not in text

    def test_processed_field(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "**Processed:** 2026-04-01 14:30:22" in text

    def test_segments_formatted_correctly(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        segments = [
            {"from_ms": 0, "to_ms": 5_000, "text": "Hello there."},
            {"from_ms": 5_000, "to_ms": 10_240, "text": "Goodbye."},
        ]
        write_transcript(session_dir, segments, processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "[00:00] Hello there." in text
        assert "[00:05] Goodbye." in text

    def test_long_session_uses_hhmmss_timestamps(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        segments = [{"from_ms": 3_661_000, "to_ms": 3_665_000, "text": "Late segment."}]
        write_transcript(session_dir, segments, processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "[01:01:01] Late segment." in text

    def test_duration_derived_from_last_segment_end(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        segments = [{"from_ms": 0, "to_ms": 125_000, "text": "Two minutes five seconds."}]
        write_transcript(session_dir, segments, processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "**Duration:** 2m 5s" in text

    def test_empty_segments_produces_valid_header(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "# Recording" in text
        assert "---" in text

    def test_separator_line_present(self, tmp_path):
        session_dir = tmp_path / "20260401T143022"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "\n---\n" in text

    def test_invalid_directory_name_uses_raw_name(self, tmp_path):
        session_dir = tmp_path / "custom_session_name"
        session_dir.mkdir()
        write_transcript(session_dir, [], processed_at=self._fixed_dt())
        text = (session_dir / "transcript.md").read_text()
        assert "custom_session_name" in text
