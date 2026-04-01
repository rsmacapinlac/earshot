"""USB stick detection and recording offload (FR-11, Pi 4B)."""

from __future__ import annotations

import errno
import json
import logging
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)

# Mount point used when the stick is not already auto-mounted.
_EARSHOT_MOUNT = Path("/mnt/earshot-usb")


def find_usb_device() -> tuple[str, str | None] | None:
    """Return ``(device_path, mountpoint_or_None)`` for the first removable vfat
    partition, or ``None`` if no removable vfat device is present.

    Used by the monitor loop to detect insertion/removal without triggering
    a mount attempt.
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
    """Return the mount point of the removable vfat stick, mounting it if needed.

    If the stick is already mounted (e.g. auto-mounted by udisks2) that path
    is returned directly.  Otherwise the stick is mounted at ``_EARSHOT_MOUNT``
    using ``sudo -n mount``.  Returns ``None`` if no stick is present or
    mounting fails.
    """
    info = find_usb_device()
    if info is None:
        return None
    device, mountpoint = info
    if mountpoint:
        return Path(mountpoint)
    return _mount_device(device)


def unmount_usb_stick() -> None:
    """Unmount the earshot USB mount point if it is mounted."""
    try:
        subprocess.run(
            ["sudo", "-n", "umount", str(_EARSHOT_MOUNT)],
            check=True,
            timeout=10.0,
            capture_output=True,
        )
        _log.info("Unmounted %s", _EARSHOT_MOUNT)
    except Exception as exc:
        _log.warning("umount failed (may already be unmounted): %s", exc)


def _mount_device(device: str) -> Path | None:
    """Mount *device* at ``_EARSHOT_MOUNT`` using ``sudo -n mount``.

    ``_EARSHOT_MOUNT`` is pre-created by the installer so no runtime mkdir
    is needed.  Only ``mount`` and ``umount`` require elevated privilege,
    restricted via ``/etc/sudoers.d/earshot``.
    """
    try:
        subprocess.run(
            ["sudo", "-n", "mount", device, str(_EARSHOT_MOUNT)],
            check=True,
            timeout=10.0,
            capture_output=True,
        )
        _log.info("Mounted %s at %s", device, _EARSHOT_MOUNT)
        return _EARSHOT_MOUNT
    except Exception as exc:
        _log.error("Failed to mount %s: %s", device, exc)
        return None


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
    """Copy all files from *src* to *dest*, verify sizes, then remove originals."""
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
        pass  # Non-empty (e.g. new file written during offload) — leave it.
