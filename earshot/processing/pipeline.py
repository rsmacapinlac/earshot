"""On-device diarization (pyannote) + transcription (Whisper)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_whisper_model = None
_diarization_pipeline = None


def _patch_torch_load_for_pyannote() -> None:
    import torch

    real_load = torch.load

    def _load(*args: Any, **kwargs: Any) -> Any:
        kwargs["weights_only"] = False
        return real_load(*args, **kwargs)

    torch.load = _load  # type: ignore[method-assign]


def _get_whisper(model_name: str) -> Any:
    global _whisper_model
    if _whisper_model is None:
        import whisper

        _log.info("loading Whisper model %r…", model_name)
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def _get_diarization_pipeline() -> Any:
    global _diarization_pipeline
    if _diarization_pipeline is None:
        _patch_torch_load_for_pyannote()
        from pyannote.audio import Pipeline

        _log.info("loading pyannote diarization pipeline…")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
        )
        import torch

        if hasattr(_diarization_pipeline, "to"):
            _diarization_pipeline.to(torch.device("cpu"))
    return _diarization_pipeline


def warm_processing_models(whisper_model_name: str) -> None:
    """Pre-load ML weights so the device reaches idle within NFR-5 startup budget."""
    if os.environ.get("EARSHOT_DUMMY_PROCESSING", "").strip() in ("1", "true", "yes"):
        return
    _get_whisper(whisper_model_name)
    _get_diarization_pipeline()


def _load_mono_16k_numpy(mp3_path: Path) -> tuple[Any, int]:
    import numpy as np
    import torch
    import torchaudio

    waveform, sample_rate = torchaudio.load(str(mp3_path))
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
        sample_rate = 16000
    audio = waveform.squeeze(0).numpy().astype(np.float32)
    return audio, sample_rate


def _write_temp_wav(audio: Any, sample_rate: int) -> Path:
    import torch
    import torchaudio

    tmp = Path(tempfile.mkdtemp(prefix="earshot-diar-")) / "mono.wav"
    wav_tensor = torch.from_numpy(audio).unsqueeze(0)
    torchaudio.save(str(tmp), wav_tensor, sample_rate)
    return tmp


def process_mp3(
    mp3_path: Path,
    result_path: Path,
    *,
    recording_id: str,
    recorded_at: str,
    whisper_model_name: str,
) -> dict[str, Any]:
    if os.environ.get("EARSHOT_DUMMY_PROCESSING", "").strip() in ("1", "true", "yes"):
        payload = {
            "recording_id": recording_id,
            "recorded_at": recorded_at,
            "segments": [
                {
                    "speaker": "SPEAKER_DUMMY",
                    "start": 0.0,
                    "end": 0.5,
                    "text": "",
                }
            ],
            "dummy": True,
        }
        result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    t0 = time.monotonic()
    audio, sr = _load_mono_16k_numpy(mp3_path)
    duration_s = float(len(audio) / sr)
    tmp_wav = _write_temp_wav(audio, sr)
    tmp_dir = tmp_wav.parent
    turns: list[Any] = []
    try:
        pipeline = _get_diarization_pipeline()
        try:
            diarization = pipeline(str(tmp_wav))
        except Exception:
            diarization = pipeline({"audio": str(tmp_wav)})
        ann: Any = getattr(diarization, "speaker_diarization", diarization)
        turns = list(ann.itertracks(yield_label=True))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    model = _get_whisper(whisper_model_name)
    segments_out: list[dict[str, Any]] = []
    if not turns:
        text = model.transcribe(audio, fp16=False, language=None).get("text", "").strip()
        segments_out.append(
            {
                "speaker": "SPEAKER_00",
                "start": 0.0,
                "end": round(duration_s, 3),
                "text": text,
            }
        )
    else:
        for turn, _track, speaker in turns:
            start = float(turn.start)
            end = float(turn.end)
            i0 = max(0, int(start * sr))
            i1 = min(len(audio), int(end * sr))
            chunk = audio[i0:i1]
            if chunk.size < sr // 10:
                text = ""
            else:
                text = model.transcribe(chunk, fp16=False, language=None).get("text", "").strip()
            segments_out.append(
                {
                    "speaker": str(speaker),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                }
            )

    payload = {
        "recording_id": recording_id,
        "recorded_at": recorded_at,
        "segments": segments_out,
        "processing_seconds": round(time.monotonic() - t0, 3),
    }
    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
