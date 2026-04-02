# Configuration

Earshot is configured via a `config.toml` file located at `~/earshot/config.toml`. The installer creates this file via an interactive prompt — no manual setup is required before running `installer/install.sh`.

All values shown below are defaults. Omitting a key uses the default.

---

## `[hardware]`

| Key | Type | Default | Values | Description |
|---|---|---|---|---|
| `hardware.hat` | string | — | `"respeaker"`, `"whisplay"` | **Required.** The connected audio HAT. Determines driver installation and HAL implementation at startup. |

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

## `[audio]` *(v2)*

Audio feedback via the Whisplay HAT speaker is deferred to v2. No `[audio]` keys are used in v1.

---

## `[display]`

Applies to Whisplay HAT only. Ignored (no-op) on ReSpeaker HAT.

| Key | Type | Default | Description |
|---|---|---|---|
| `display.brightness` | integer | `80` | LCD backlight brightness (0–100). Set to `0` to turn the display off entirely. |

---

## `[shutdown]`

| Key | Type | Default | Description |
|---|---|---|---|
| `shutdown.hold_duration_seconds` | integer | `3` | Duration in seconds the button must be held while idle to trigger a safe shutdown. |

---

## Example `config.toml`

```toml
[hardware]
hat = "whisplay"

[recording]
chunk_duration_seconds = 900
min_duration_seconds = 3

[encoding]
bitrate_kbps = 32

[storage]
recordings_dir = "~/earshot/recordings"
disk_threshold_percent = 90

[display]
brightness = 80

[shutdown]
hold_duration_seconds = 3
```
