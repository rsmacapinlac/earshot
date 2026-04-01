# Storage

## FR-6: Local Storage
- Recordings are saved locally and remain on the device until offloaded via USB.
- Default storage path: `~/earshot/recordings/<YYYYMMDDTHHMMSS>/` (e.g. `20260329T143022`)
- The recordings directory is configurable via `storage.recordings_dir` in `config.toml`.
- Within each session directory, chunks are stored as sequentially numbered files:
  - `audio_001.opus`, `audio_002.opus`, … — encoded chunks
  - `audio_NNN.wav` — chunk currently being recorded or awaiting encoding

### Disk Space Management
- Disk space is checked before each new recording begins.
- If the configurable threshold is reached, the LED pulsates **orange** and new recordings are blocked.
- The device recovers automatically once files are manually removed and disk space drops below the threshold.
- Threshold is configurable (default: 90% disk usage) to avoid completely filling the SD card.

### Recording Pipeline
1. Capture audio to a numbered WAV file (e.g. `audio_001.wav`).
2. When the chunk duration is reached (or recording stops), close the WAV and encode to Opus.
3. Delete the WAV once the `.opus` file is confirmed written.
4. If recording continues, begin the next chunk (`audio_002.wav`, etc.) while encoding runs in the background.

### Filesystem as State
The filesystem is the source of truth for recording state — no database is used.

| Directory contents | Meaning |
|---|---|
| `audio_NNN.wav` only | Chunk currently recording or interrupted before encode |
| `audio_NNN.wav` + `audio_NNN.opus` | Chunk encode in progress |
| `audio_NNN.opus` only | Chunk successfully encoded |
| `audio_NNN.wav` + `.failed_NNN` marker | Encoding failed for that chunk; WAV retained |

On boot, any session directory containing a WAV with no corresponding Opus (and no `.failed` marker) is treated as interrupted — encoding is retried automatically.

---

## FR-11: USB Stick Offload (Pi 4B)

Allows a user to retrieve recordings by inserting a FAT32-formatted USB stick into a USB-A port on the Pi 4B.

### Behaviour

- The device monitors for USB storage insertion via udev.
- **If no recording session is active on insertion:** the move begins immediately.
- **If a recording session is active on insertion:** the stick is registered and the move is deferred. The device continues recording normally (LED remains **red**). When the user presses the button to end the session (and the final chunk finishes encoding), the move begins.
- On move start:
  1. The LED pulsates **blue** (slow) — shared with encoding state.
  2. Session directories are moved to the stick one at a time: write → verify → delete from Pi.
  3. Partial and crashed sessions (WAVs with no Opus) are moved as-is.
  4. If the stick fills up mid-move, the transfer stops, remaining recordings are left on the Pi, and the LED pulsates **orange** (error state). The error state clears when the stick is removed.
- On move complete:
  1. The stick filesystem is flushed and unmounted cleanly.
  2. The LED flashes **blue** once (transfer complete).
  3. The device returns to idle (solid **green**). The stick is safe to remove.
- If a USB stick is already inserted at boot, the move is triggered immediately after the device reaches idle state.

### Stick Requirements

- Filesystem: FAT32
- No drivers or software required on the receiving computer — the stick is standard USB mass storage.

---

## FR-12: USB Gadget Mode Offload (Pi Zero 2W)

Allows a user to retrieve recordings by plugging a micro-USB OTG cable from the Pi Zero 2W into a laptop. The device exposes the recordings directory as a USB mass storage device.

### Behaviour

- The device monitors for USB host connection via VBUS detection (polling `/sys/class/power_supply/` or a udev rule).
- On connection:
  1. Any active recording is stopped immediately.
  2. The recordings partition/directory is remounted read-only.
  3. The `g_mass_storage` USB gadget module is loaded, backed by the recordings partition.
  4. LED indicates offload mode (colour TBD).
- The laptop sees a standard USB mass storage device — no drivers or software required.
- On disconnection:
  1. `g_mass_storage` is unloaded.
  2. The recordings partition is remounted read-write.
  3. The device returns to idle state (FR-1).

### Prerequisites

- `dtoverlay=dwc2` must be present in `/boot/config.txt` (handled by the installer, FR-8).
- Power is supplied via the dedicated power micro-USB port; the OTG micro-USB port is used for data.

### Constraints

- The device does not record while in offload mode.
- The user must safely eject the drive on the laptop before unplugging to avoid filesystem corruption.
