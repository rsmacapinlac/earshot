# Earshot

```
·
 )
 ))   EARSHOT
 )))
 ))
 )
·
```

A Raspberry Pi application that records conversations locally and offloads audio via USB. No cloud, no network dependency.

## How it works

1. The LED pulsates **white** while booting, then glows solid **green** when ready.
2. Press the button to start recording — the LED pulsates **red**.
3. Press the button again to stop — the LED pulsates **blue** while the audio is encoded.
4. The LED returns to solid **green** when ready.

To safely shut down, hold the button for 3 seconds while idle.

## Hardware

2 use-cases (therefore two sets of hardware):

On the desk:
- Raspberry Pi 4B (2GB minimum, 4GB recommended)
- Seeed ReSpeaker 2-Mic Pi HAT or Whisplay HAT

Portable
- Raspberry Pi Zero 2 W
- Whisplay Hat
- PiSugar S for Zero (or equivalent) — connects via pogo pins, no USB ports occupied

## OS Requirements

- [Raspberry Pi OS Lite 64-bit](https://www.raspberrypi.com/software/)

## Install

### Prerequisites

- See Hardware and OS Requirements

### Install

Run **as your normal login user** (e.g.`pi`). The script uses `sudo` where it needs root.

```bash
git clone https://github.com/rsmacapinlac/earshot.git ~/earshot
bash ~/earshot/installer/install.sh
```

After boot, check the service and audio:

```bash
sudo systemctl status earshot
journalctl -u earshot -f
arecord -l
```

Updates: `cd ~/earshot && git pull && bash installer/install.sh`

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

