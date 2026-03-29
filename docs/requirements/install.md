# Install

## FR-8: One-Line Install
- A single `curl | bash` command handles full setup on a fresh Raspberry Pi OS install (run as a normal user; the script uses `sudo` for privileged steps).
- The installer must:
  - Do an apt update & apt upgrade
  - Install the seeed-voicecard driver
  - Install system-level audio and ffmpeg dependencies
  - Set up the Python environment and install all dependencies
  - Prompt for a Hugging Face access token and download on-device models (STT, diarization)
  - Install and enable a systemd service so Earshot starts on boot after a final reboot
  - Prompt for API endpoint configuration (can be skipped)
- A reboot at the **end** of install is acceptable (ReSpeaker may not appear in ALSA until after reboot; the service is enabled but not started until the first boot completes).
