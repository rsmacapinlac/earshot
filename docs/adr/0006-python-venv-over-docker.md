# 0006 — Python venv over Docker

**Status:** Accepted

## Context
Dependency isolation is needed for the Python application. Docker was considered as an alternative to a Python virtual environment.

## Decision
Use a Python virtual environment (venv) rather than Docker for the Pi application.

## Consequences
- No Docker daemon overhead (~50–100MB RAM saved, meaningful on the 2GB minimum target).
- Direct access to GPIO, SPI, and ALSA devices without `--privileged` flags or device mounts.
- The seeed-voicecard kernel driver must be installed on the host OS regardless — Docker provides no benefit for this step.
- Simpler systemd service configuration — the service runs the venv Python binary directly.
- For a single-purpose device, Docker's isolation benefits do not outweigh the added complexity.
- Docker remains a good fit for any future companion server or API component, which is a separate concern.
