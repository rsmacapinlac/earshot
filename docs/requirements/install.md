# Install

## FR-8: One-Line Install
- A single `curl | bash` command handles full setup on a fresh Raspberry Pi OS install.
- The installer must:
  - Do an apt update & apt upgrade
  - Install the seeed-voicecard driver (requires reboot)
  - Install system-level audio and ffmpeg dependencies
  - Set up the Python environment and install all dependencies
  - Prompt for a Hugging Face access token and download on-device models (STT, diarization)
  - Install and enable a systemd service so Earshot starts on boot
  - Prompt for API endpoint configuration (can be skipped)
