# 0008 — systemd for Service Management

**Status:** Accepted

## Context
The application needs to start automatically on boot, restart on failure, and be manageable on a headless Pi without a user session.

## Decision
Run Earshot as a systemd service, installed and enabled by the one-line installer.

## Consequences
- Starts automatically on boot without any user interaction.
- Automatically restarts on crash.
- Logs are accessible via `journalctl -u earshot`.
- Standard `systemctl start / stop / restart / status earshot` commands work as expected.
- No additional process supervisor (e.g. supervisor, pm2) required.
