# Earshot

A Raspberry Pi application that records conversations, identifies individual speakers, and transcribes what was said — all on-device, with no cloud processing required.

## How it works

1. The LED pulsates **white** while booting, then glows solid **green** when ready.
2. Press the button to start recording — the LED pulsates **red**.
3. Press the button again to stop — the LED pulsates **blue** while processing.
4. The recording is transcribed and separated by speaker automatically.
5. The LED returns to solid **green** when done. Results are saved locally and synced to an API when internet is available.

To safely shut down, hold the button for 3 seconds while idle.

## Hardware

- Raspberry Pi 4B (2GB minimum, 4GB recommended)
- Seeed ReSpeaker 2-Mic Pi HAT

## Requirements

- [Raspberry Pi OS Lite 64-bit](https://www.raspberrypi.com/software/)
- A [Hugging Face](https://huggingface.co) account (required once during install to download diarization models)

## Install

### Prerequisites

- **Raspberry Pi OS Lite 64-bit** flashed and booted (Bookworm or later)
- **ReSpeaker 2-Mic Pi HAT** physically attached before first boot
- **[Hugging Face](https://huggingface.co) account** — a read-only access token is needed once during install to download the speaker diarization model; no account or internet connection is needed after that
  - Get a token at: https://huggingface.co/settings/tokens
  - Accept the model terms at: https://hf.co/pyannote/speaker-diarization-3.1 and https://hf.co/pyannote/segmentation-3.0

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/rsmacapinlac/earshot/main/installer/install.sh | bash
```

Run that **as your normal login user** (e.g. `ritchie` or `pi`). The script uses `sudo` where it needs root. **Do not use `sudo curl … | bash`** — only `curl` would run as root; `bash` would still be unprivileged and cannot create `/var/lib/earshot-install`.

The installer runs in two phases separated by a reboot.

**Phase 1** (interactive, ~5 minutes):
1. Updates system packages
2. Prompts for your Hugging Face token and optional API endpoint
3. Installs the ReSpeaker HAT kernel driver
4. Reboots to activate the driver

After reboot, Phase 2 starts automatically — no interaction needed.

**Phase 2** (automatic, ~20–40 minutes depending on network speed):
1. Installs Python, ffmpeg, and audio libraries
2. Clones the Earshot repository to `~/earshot/`
3. Creates a Python virtual environment and installs dependencies
4. Downloads the Whisper speech model (~150 MB) and pyannote diarization model (~1 GB)
5. Writes `~/earshot/config.toml` with your settings
6. Installs and starts the `earshot` systemd service

### Monitoring Phase 2

Phase 2 runs as a systemd service. Follow its progress with:

```bash
journalctl -u earshot-install-continue -f
```

If Phase 2 fails, retry with:

```bash
sudo systemctl restart earshot-install-continue
```

## Docs

- [Requirements](docs/requirements/README.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Development Workflow](docs/development-workflow.md)

## Managing the service

```bash
sudo systemctl status earshot
sudo systemctl restart earshot
journalctl -u earshot -f
```

## Releases

Versions follow `major.minor` — e.g. `v0.1`, `v0.2`. Releases are tagged on `main`:

```bash
git tag v0.1 && git push --tags
```

`0.x` = pre-stable. `1.0` marks the first stable release.
