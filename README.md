# Earshot

A Raspberry Pi application that records conversations and uploads audio to an API for transcription and speaker diarization.

## How it works

1. The LED pulsates **white** while booting, then glows solid **green** when ready.
2. Press the button to start recording — the LED pulsates **red**.
3. Press the button again to stop — the LED pulsates **blue** while the audio is encoded.
4. The LED returns to solid **green** when ready. The recording is uploaded to the API when internet is available, where transcription and speaker diarization are performed.

To safely shut down, hold the button for 3 seconds while idle.

## Hardware

- Raspberry Pi 4B (2GB minimum, 4GB recommended)
- Seeed ReSpeaker 2-Mic Pi HAT

## Requirements

- [Raspberry Pi OS Lite 64-bit](https://www.raspberrypi.com/software/)

## Install

### Prerequisites

- **Raspberry Pi OS Lite 64-bit** flashed and booted (Bookworm or later)
- **ReSpeaker 2-Mic Pi HAT** physically attached before first boot
### Install

Run **as your normal login user** (e.g. `ritchie` or `pi`). The script uses `sudo` where it needs root.

```bash
git clone https://github.com/rsmacapinlac/earshot.git ~/earshot
bash ~/earshot/installer/install.sh
```

Updates: `cd ~/earshot && git pull && bash installer/install.sh`

The installer runs in **one session** (interactive prompts, then mostly automated). It enables the `earshot` service but does **not** start it until **after** a reboot, so the ReSpeaker ALSA device can appear cleanly.

Typical order (~10–20 minutes depending on network):

1. Prompts for optional API endpoint
2. Updates system packages and installs git/curl
3. Installs the ReSpeaker HAT kernel driver (HinTak seeed-voicecard fork)
4. Installs Python, ffmpeg, and audio build dependencies
5. Clones the repo to `~/earshot/`, creates a venv, installs Python deps
6. Writes `~/earshot/config.toml`
7. Installs and **enables** the `earshot` systemd service
8. **Reboots** the Pi once at the end

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

## Backlog
