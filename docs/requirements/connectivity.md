# Connectivity

## FR-9: WiFi Connectivity

Earshot relies on WiFi for API sync. The device does not manage WiFi configuration — this is fully delegated to the OS (NetworkManager on Raspberry Pi OS Bookworm).

### FR-9.1: Primary Network
- The home or office WiFi network is configured at flash time via rpi-imager.
- rpi-imager writes the credentials as a NetworkManager connection profile at `/etc/NetworkManager/system-connections/preconfigured.nmconnection`.
- The device connects automatically on boot when the network is in range.

### FR-9.2: Secondary Network (Phone Hotspot)
- A phone hotspot can be registered as a second NetworkManager profile via SSH while connected to the primary network.
- Both profiles coexist as independent files under `/etc/NetworkManager/system-connections/`; the primary network profile is never modified.
- NetworkManager connects automatically to whichever configured network is in range.
- See [install.md](install.md) for the setup procedure.

### FR-9.3: Connectivity Detection
- The application polls for network connectivity at a configurable interval while idle.
- On startup, connectivity is checked as part of the boot sequence before entering the idle state.
- When connectivity is detected and the device is idle, any pending uploads are dispatched immediately.

### FR-9.4: Sync Gating
- Sync only runs when the device is in the **idle** state (not recording or encoding).
- If a recording begins while a sync is in progress, the upload is interrupted and re-queued; it resumes when the device returns to idle.
- This constraint applies to both Pi 4B and Pi Zero 2W. Concurrent upload and audio capture is not supported on either target.

## Out of Scope (v1)
- USB tethering
- Bluetooth tethering
- USB cellular modem / LTE dongle
- Captive portal or WiFi onboarding UI
- Adding WiFi networks without SSH access
