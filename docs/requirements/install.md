# Install

## FR-8: One-Line Install
- Full setup on a fresh Raspberry Pi OS install via **`git clone` + `bash installer/earshot-install.sh`** (recommended), or optionally `curl | bash` (run as a normal user; the script uses `sudo` for privileged steps).
- The installer must:
  - Do an apt update & apt upgrade
  - Install the seeed-voicecard driver
  - Install system-level audio and ffmpeg dependencies
  - Set up the Python environment and install all dependencies
  - Install and enable a systemd service so Earshot starts on boot after a final reboot
- A reboot at the **end** of install is acceptable (ReSpeaker may not appear in ALSA until after reboot; the service is enabled but not started until the first boot completes).

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
