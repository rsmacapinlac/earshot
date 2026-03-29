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

Use **`earshot-install.sh`** (canonical). Some CDNs cache `install.sh` for a long time; if you see errors mentioning `/var/lib/earshot-install`, you are on a **stale** `install.sh` — use the URL below.

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh | bash
```

The shorter `install.sh` URL is a stub that downloads `earshot-install.sh` and may help once your CDN serves the updated stub:

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/install.sh | bash
```

Run that **as your normal login user** (e.g. `ritchie` or `pi`). The script uses `sudo` where it needs root. **Do not use `sudo curl … | bash`** — only `curl` would run as root; `bash` would still be unprivileged.

The installer runs in **one session** (interactive prompts, then mostly automated). It enables the `earshot` service but does **not** start it until **after** a reboot, so the ReSpeaker ALSA device can appear cleanly.

Typical order (~25–50 minutes depending on network):

1. Prompts for your Hugging Face token and optional API endpoint
2. Updates system packages and installs git/curl
3. Installs the ReSpeaker HAT kernel driver (HinTak seeed-voicecard fork)
4. Installs Python, ffmpeg, and audio build dependencies
5. Clones the repo to `~/earshot/`, creates a venv, installs PyTorch (CPU) and Python deps
6. Downloads the Whisper `base` model (~150 MB) and pyannote diarization model (~1 GB)
7. Writes `~/earshot/config.toml`
8. Installs and **enables** the `earshot` systemd service
9. **Reboots** the Pi once at the end

After boot, check the service and audio:

```bash
sudo systemctl status earshot
journalctl -u earshot -f
arecord -l
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
