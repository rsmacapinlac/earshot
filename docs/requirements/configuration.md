# Configuration

Earshot is configured via a `config.toml` file located at `~/earshot/config.toml`. The installer creates this file via an interactive prompt — no manual setup is required before running `installer/install.sh`.

All values shown below are defaults. Omitting a key uses the default.

---

## `[hardware]`

| Key | Type | Default | Values | Description |
|---|---|---|---|---|
| `hardware.hat` | string | `"respeaker"` | `"respeaker"` | Audio HAT to use. |

---

## `[recording]`

| Key | Type | Default | Description |
|---|---|---|---|
| `recording.chunk_duration_seconds` | integer | `900` | Duration of each audio chunk in seconds (default: 15 minutes). Recording continues seamlessly across chunks. |
| `recording.min_duration_seconds` | integer | `3` | Minimum recording duration. Sessions shorter than this are discarded. |

---

## `[encoding]`

| Key | Type | Default | Description |
|---|---|---|---|
| `encoding.bitrate_kbps` | integer | `32` | Opus encoding bitrate in kbps. 32 kbps is appropriate for speech. Higher values increase file size with diminishing quality returns. |

---

## `[storage]`

| Key | Type | Default | Description |
|---|---|---|---|
| `storage.recordings_dir` | string | `"~/earshot/recordings"` | Directory where session folders are written. Must be on a filesystem with adequate space. |
| `storage.disk_threshold_percent` | integer | `90` | Disk usage percentage at which new recordings are blocked. Prevents the SD card from filling completely. |

---

## `[transcription]`

On-device transcription using faster-whisper (CTranslate2). Enabled by default — the installer prompts during setup.

| Key | Type | Default | Description |
|---|---|---|---|
| `transcription.enabled` | boolean | `true` | Enable on-device transcription. Requires faster-whisper and a model file to be installed. Set to `false` to disable. |
| `transcription.model` | string | `"tiny.en"` | Whisper model to use. `"tiny.en"` (INT8, ~35 MB) is the default and the only supported model on Pi Zero 2W. `"base.en"` (INT8, ~60 MB) is recommended on Pi 4B for better accuracy. |
| `transcription.threads` | integer | `2` | CPU threads allocated to faster-whisper inference. Default of 2 leaves headroom for recording and other operations on the 4-core CPU. |

---

## `[shutdown]`

| Key | Type | Default | Description |
|---|---|---|---|
| `shutdown.hold_duration_seconds` | integer | `3` | Duration in seconds the button must be held while idle to trigger a safe shutdown. |

---

## Example `config.toml`

```toml
[hardware]
hat = "respeaker"

[recording]
chunk_duration_seconds = 900
min_duration_seconds = 3

[encoding]
bitrate_kbps = 32

[storage]
recordings_dir = "~/earshot/recordings"
disk_threshold_percent = 90

[transcription]
enabled = true
model = "tiny.en"
threads = 2

[shutdown]
hold_duration_seconds = 3
```
