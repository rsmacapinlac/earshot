# Install

## FR-8: One-Line Install
- Full setup on a fresh Raspberry Pi OS install via **`git clone` + `bash installer/install.sh`** (run as a normal user; the script uses `sudo` for privileged steps).
- The installer must:
  - Prompt the user to select their HAT (see below), then write `hardware.hat` to `config.toml`
  - Do an apt update & apt upgrade
  - Install the ReSpeaker audio driver
  - Install system-level audio and ffmpeg dependencies (`ffmpeg`, `dosfstools`, `mtools`)
  - Install faster-whisper and download the default transcription model (see [transcription.md](transcription.md) FR-18 for details; pass `--no-transcription` to skip)
  - Set up a Python 3.11 virtual environment and install all Python dependencies
  - Install and enable a systemd service so Earshot starts on boot
- A reboot at the end of install is required — the audio driver does not appear in ALSA until after reboot.

### HAT Configuration

The installer configures the Seeed ReSpeaker 2-Mic Pi HAT automatically. The HAT choice is written to `config.toml` as `hardware.hat = "respeaker"`.

## FR-10: Phone Hotspot Setup (Optional)

For portable use, a phone hotspot can be added as a second WiFi network. This must be done via SSH while the device is connected to the primary (rpi-imager-configured) network.

```bash
sudo nmcli connection add type wifi con-name "phone-hotspot" ssid "HotspotSSID" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "YourPassword" \
  connection.autoconnect yes
```

- The hotspot does **not** need to be active when this command is run — the profile is saved and used automatically when the hotspot comes into range.
- This creates a new NetworkManager profile alongside the existing one. The primary network profile is untouched.
- NetworkManager will automatically connect to whichever configured network is in range.
- No reboot required.

> **Note:** `nmcli` sets the required file permissions (`root:root`, mode `600`) automatically. NetworkManager silently ignores connection files with incorrect permissions.
