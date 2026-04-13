"""On-device transcription using faster_whisper (ADR-0010)."""

from earshot.transcription.process import transcribe_session
from earshot.transcription.queue import pending_sessions
from earshot.transcription.writer import write_transcript, write_transcript_raw

__all__ = ["pending_sessions", "transcribe_session", "write_transcript", "write_transcript_raw"]
