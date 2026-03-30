# Non-Functional Requirements

## NFR-1: Offline-First Recording
The device must be able to record and store audio with no internet connection. API sync and transcription are opportunistic — recordings are never lost due to lack of connectivity.

## NFR-2: Resilience
- A crash or power loss after recording but before MP3 encoding must not lose the raw audio.
- On restart, any unencoded recordings (WAV present, no MP3) are detected and encoded automatically.
- On restart, any unsynced recordings are re-queued for upload.

## NFR-3: Startup Time
The application should reach the green-light ready state within 60 seconds of boot.

## Out of Scope (v1)
- Wake-word detection (always button-triggered)
- Real-time / live transcription during recording
- Multi-device coordination
- Web UI or local dashboard
- Speaker identification (who a speaker is, not just that they differ)
- Automatic retry of failed processing jobs
- USB mass storage mode (see below)
- Audio feedback / beep on state transitions (requires speaker hardware)

## Future Considerations

### USB Mass Storage Mode
When the Pi is connected to a computer via USB-C, it could present the recordings directory as a USB mass storage device, allowing direct file browsing without SSH or network access. This is achievable via the Pi's USB gadget mode (`dwc2` overlay).

**Constraint:** The Pi 4B's USB-C port is primarily power-in. Enabling USB gadget mode for data requires an alternative power source (e.g. GPIO pins or a powered USB hub) while USB-C is used for the data connection to the host computer.
