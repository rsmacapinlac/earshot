# Connectivity

Earshot has no network dependency for application functionality. WiFi is used exclusively for SSH access during setup and configuration.

## FR-9: WiFi Setup

WiFi configuration is fully delegated to the OS (NetworkManager on Raspberry Pi OS Bookworm). The application does not manage network connectivity.

### FR-9.1: Primary Network
- The home or office WiFi network is configured at flash time via rpi-imager.
- rpi-imager writes the credentials as a NetworkManager connection profile at `/etc/NetworkManager/system-connections/preconfigured.nmconnection`.
- The device connects automatically on boot when the network is in range.

### FR-9.2: Secondary Network (Phone Hotspot)
- A phone hotspot can be registered as a second NetworkManager profile via SSH while connected to the primary network.
- Both profiles coexist as independent files under `/etc/NetworkManager/system-connections/`; the primary network profile is never modified.
- NetworkManager connects automatically to whichever configured network is in range.
- See [install.md](install.md) for the setup procedure.

## Out of Scope (v1)
- USB tethering
- Bluetooth tethering
- USB cellular modem / LTE dongle
- Captive portal or WiFi onboarding UI
- Adding WiFi networks without SSH access
