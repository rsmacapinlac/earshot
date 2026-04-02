# Storage

> See [device-state.md](device-state.md) for LED colours during USB transfer states.

## FR-7: Local Storage
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

Allows a user to retrieve recordings by plugging a micro-USB OTG cable from the Pi Zero 2W into a laptop. The device exposes the recordings as a USB mass storage device labelled **EARSHOT**.

### Behaviour

- The device monitors for USB host connection using a `g_zero` probe gadget: a minimal USB gadget is loaded at idle so the UDC (USB Device Controller) can report VBUS and connection state. When the UDC transitions to `configured`, a host is connected.
- **If no recording session is active on connection:** offload begins immediately (steps 1–4 below).
- **If a recording session is active on connection:** the connection is registered and offload is deferred. The device continues recording normally (LED remains **red**). On the Whisplay HAT, Zone D of the display shows `USB pending`. When the user presses the button to end the session (and the final chunk finishes encoding), offload begins.
  - **Note:** The laptop will not see a USB mass storage device until the deferred offload begins — this is expected behaviour. The cable should remain plugged in.
- On offload start:
  1. A sparse FAT32 image (`/tmp/earshot-recordings.img`) is created, sized to the current recordings content.
  2. All session directories are copied into the image using `mtools` (no root or loop-mount required).
  3. The `g_mass_storage` kernel module is loaded with the image as its backing file (**read-write**, volume label `EARSHOT`).
  4. The LED pulsates **blue** (slow).
  5. The laptop sees a standard USB mass storage device — no drivers or software required. Sessions can be deleted from the laptop.
- On disconnection:
  1. The image is scanned with `mdir` to find which session directories remain.
  2. Any session that was exported but is no longer present in the image (deleted on the laptop) is deleted from the Pi's recordings directory.
  3. `g_mass_storage` is unloaded and the image file is deleted.
  4. The `g_zero` probe is reloaded, ready for the next connection.
  5. The device returns to idle state (FR-1).

### Prerequisites

- `dtoverlay=dwc2` must be present in `/boot/firmware/config.txt` under the `[all]` section (added by the installer, FR-8). The `[cm4]` and `[cm5]` conditional sections may also be present but do not affect the Pi Zero 2W.
- Power is supplied via the dedicated **PWR IN** micro-USB port; the **USB** (OTG data) micro-USB port is used for this feature.
- `dosfstools` and `mtools` must be installed (handled by the installer, FR-8).
- The systemd service requires `CAP_SYS_MODULE` (to load/unload `g_zero` and `g_mass_storage`) set as an ambient capability — configured automatically by the service unit.

### Constraints

- The device does not record while in active offload mode (once `g_mass_storage` is loaded). If the user presses the button to record, the gadget is deactivated first.
- The USB volume is a **snapshot** of recordings at the time the cable was connected. Files recorded after connection are not visible until the next connection.
- Deletions made on the laptop are synced back to the Pi on disconnect — deleting a session folder on the laptop causes it to be removed from the Pi after the cable is unplugged.
- The user must safely eject the drive on the laptop before unplugging to avoid filesystem corruption.
