"""USB offload for recordings via USB-A stick (FR-11)."""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

_log = logging.getLogger(__name__)

# Mount point written by the udev rule installed by the earshot installer.
_EARSHOT_MOUNT = Path("/mnt/earshot-usb")


def find_usb_device() -> tuple[str, str | None] | None:
    """Return ``(device_path, mountpoint_or_None)`` for the first removable vfat
    partition, or ``None`` if no removable vfat device is present.

    Used by the monitor loop to detect insertion/removal without side-effects.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,RM,FSTYPE,MOUNTPOINT"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5.0,
        )
        data = json.loads(result.stdout)
        for device in data.get("blockdevices", []):
            for child in device.get("children", []):
                if child.get("rm") and child.get("fstype") == "vfat":
                    return f"/dev/{child['name']}", child.get("mountpoint") or None
    except Exception as exc:
        _log.debug("lsblk error: %s", exc)
    return None


def find_usb_mount() -> Path | None:
    """Return the mount point of the removable vfat stick, or ``None``.

    The stick is auto-mounted by the udev rule installed by the earshot
    installer — this function only reads the existing mountpoint, it does
    not attempt to mount anything.
    """
    info = find_usb_device()
    if info is None:
        return None
    _, mountpoint = info
    return Path(mountpoint) if mountpoint else None


def eject_usb_device(device: str) -> None:
    """Sync buffers and stop the systemd mount service for *device*.

    The earshot-usb@.service unit handles unmounting via ExecStop when
    stopped or when the device is removed.  Falls back gracefully if the
    service or stick is already gone.
    """
    try:
        subprocess.run(["sync"], check=False, timeout=10.0)
    except Exception:
        pass
    # Derive the systemd instance name from the device basename (e.g. sda1).
    instance = Path(device).name
    try:
        subprocess.run(
            ["systemctl", "stop", f"earshot-usb@{instance}.service"],
            check=True,
            timeout=15.0,
            capture_output=True,
        )
        _log.info("Unmounted %s", device)
    except Exception as exc:
        _log.warning("Unmount failed (stick may already be removed): %s", exc)


def move_recordings_to_stick(recordings_root: Path, mount: Path) -> None:
    """Move all session directories from *recordings_root* to *mount*.

    Processes session directories one at a time.  Within each directory,
    each file is copied to the stick, size-verified, then removed from the
    Pi.  Raises ``OSError`` with ``errno.ENOSPC`` if the stick fills up,
    leaving any remaining sessions intact on the Pi.
    """
    if not recordings_root.exists():
        return

    session_dirs = sorted(d for d in recordings_root.iterdir() if d.is_dir())
    for session_dir in session_dirs:
        dest = mount / session_dir.name
        _move_session(session_dir, dest)
        _log.info("Offloaded session %s", session_dir.name)


def _move_session(src: Path, dest: Path) -> None:
    """Copy all files from *src* to *dest*, verify sizes, then remove originals.

    Moves all session files to USB:
    - session.wav: concatenated raw audio
    - recording-*.wav: individual chunks
    - session.opus: compressed audio for offload
    - transcript.md: transcription results
    - transcript_raw.json: raw segment data
    - status.json: metadata
    """
    dest.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(src.iterdir()):
        if src_file.is_dir():
            continue
        dest_file = dest / src_file.name
        try:
            shutil.copy2(str(src_file), str(dest_file))
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise
            raise OSError(exc.errno, f"copy failed for {src_file.name}: {exc}") from exc
        if dest_file.stat().st_size != src_file.stat().st_size:
            dest_file.unlink(missing_ok=True)
            raise OSError(errno.EIO, f"Size mismatch copying {src_file.name}")
        src_file.unlink()
    try:
        src.rmdir()
    except OSError:
        pass  # Non-empty if new file written during offload — leave it.
