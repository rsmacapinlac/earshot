# 0002 — pyannote.audio for Speaker Diarization

**Status:** Accepted

## Context
Speaker diarization (segmenting audio by speaker) is required. Alternatives considered:

| Option | HF account required | Quality | Notes |
|---|---|---|---|
| pyannote.audio | Yes (gated models) | Best | Industry standard |
| simple-diarizer | No | Moderate | Uses resemblyzer + spectral clustering |
| speechbrain | No (most models) | Good | Heavier than pyannote |

## Decision
Use pyannote.audio as the diarization backend.

## Consequences
- Best-in-class diarization quality, including dynamic speaker count detection.
- Requires a one-time Hugging Face account setup and acceptance of model licence terms.
- The installer must prompt for a Hugging Face access token to download the gated models.
- After install, models are cached locally — no HF account or internet required at runtime.
- No audio is sent to Hugging Face at any point; HF is only used for model distribution.
- The diarization backend should be implemented behind an interface to allow future substitution if a better offline-native alternative emerges.
