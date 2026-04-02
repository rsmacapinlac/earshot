# Install

## FR-8: One-Line Install
- Full setup on a fresh Raspberry Pi OS install via **`git clone` + `bash installer/install.sh`** (run as a normal user; the script uses `sudo` for privileged steps).
- The installer must:
  - Prompt the user to select their HAT (see below), then write `hardware.hat` to `config.toml`
  - Do an apt update & apt upgrade
  - Install the appropriate HAT audio driver based on the selection (mutually exclusive — see note below)
  - Install system-level audio and ffmpeg dependencies (`ffmpeg`, `dosfstools`, `mtools`)
  - Set up a Python 3.11 virtual environment and install all Python dependencies
  - Install and enable a systemd service so Earshot starts on boot
  - For Pi Zero 2W (Whisplay): enable `dtoverlay=dwc2` in `/boot/firmware/config.txt`, install USB gadget helper scripts (`earshot-gadget-on`, `earshot-gadget-off`), and configure the systemd service with `CAP_SYS_MODULE` and `CAP_SYS_ADMIN` ambient capabilities for gadget mode
- A reboot at the end of install is required — the audio driver does not appear in ALSA until after reboot.

### HAT Selection Prompt

The installer prompts interactively. No manual `config.toml` setup is required before running.

```
Which HAT is connected?
  1) Seeed ReSpeaker 2-Mic Pi HAT
  2) Whisplay HAT (PiSugar)

Enter 1 or 2:
```

The selection is written to `config.toml` as `hardware.hat` and determines which audio driver is installed.

### HAT Audio Drivers

The two supported HATs use the same WM8960 codec chip but require different, **mutually exclusive** drivers. Installing both causes kernel module conflicts. The installer installs only the driver for the configured HAT.

| HAT | Driver | dtoverlay |
|---|---|---|
| ReSpeaker | seeed-voicecard (custom WM8960 kernel module) | `seeed-2mic-voicecard` |
| Whisplay | Upstream WM8960 driver | `wm8960-soundcard` |

Only one `dtoverlay` entry is written to `/boot/config.txt`. Switching HATs requires re-running the installer with the updated `hardware.hat` value.

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
