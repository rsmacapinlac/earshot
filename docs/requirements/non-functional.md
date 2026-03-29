# Non-Functional Requirements

## NFR-1: Offline-First
The device must be fully functional with no internet connection. API sync is opportunistic.

## NFR-2: On-Device Processing
All audio processing (diarization + transcription) runs on the Pi 4B. No audio is sent to external services for processing.

## NFR-3: Model Size Constraints
Given Pi 4B hardware constraints (4GB RAM, no GPU):
- STT model: Whisper `small` or `base` (configurable, default `base`)
- Diarization: pyannote.audio with CPU-optimised settings

## NFR-4: Resilience
- A crash or power loss after recording but before processing must not lose the raw audio.
- On restart, any unprocessed recordings are detected and processed automatically.

## NFR-5: Startup Time
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
