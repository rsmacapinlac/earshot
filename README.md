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

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/earshot/main/install.sh | bash
```

The installer will:
- Update the system and install dependencies
- Install the ReSpeaker HAT driver (requires a reboot, after which install continues automatically)
- Set up the Python environment and download on-device models
- Configure Earshot to run as a service on boot
- Optionally configure an API endpoint for result sync

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
