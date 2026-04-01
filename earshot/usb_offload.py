"""USB stick detection and recording offload (FR-11, Pi 4B)."""

from __future__ import annotations

import errno
import json
import logging
import shutil
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)


def find_usb_mount() -> Path | None:
    """Return the mount point of the first removable vfat partition, or None.

    Uses ``lsblk`` to enumerate block devices and finds the first removable
    partition formatted as vfat (FAT32) that is already mounted.  On
    Raspberry Pi OS with udisks2, removable drives are auto-mounted to
    ``/media/<user>/<label>`` when inserted.
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
                    mp = child.get("mountpoint")
                    if mp:
                        return Path(mp)
    except Exception as exc:
        _log.debug("lsblk error: %s", exc)
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
            # Re-raise ENOSPC so the caller can set the error LED; for other
            # errors wrap with context.
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
