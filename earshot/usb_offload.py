"""USB offload: FR-11 stick offload (Pi 4B) and FR-12 gadget mode (Pi Zero 2W)."""

from __future__ import annotations

import errno
import json
import logging
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
    """Sync buffers then power-off *device* via udisksctl.

    Powers down the USB port so the stick LED goes dark, giving a clear
    visual signal that it is safe to remove.  Falls back gracefully if
    udisksctl is unavailable or the stick is already gone.
    """
    try:
        subprocess.run(["sync"], check=False, timeout=10.0)
    except Exception:
        pass
    try:
        subprocess.run(
            ["udisksctl", "power-off", "-b", device],
            check=True,
            timeout=15.0,
            capture_output=True,
        )
        _log.info("Ejected %s", device)
    except Exception as exc:
        _log.warning("Eject failed (stick may already be removed): %s", exc)


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


# ── FR-12: Pi Zero 2W USB gadget mode ────────────────────────────────────────

# VBUS detection: the Pi Zero 2W OTG port presents VBUS on /sys when a USB
# host (laptop) connects.  We watch this path to detect connect/disconnect.
_VBUS_PATH = Path("/sys/class/power_supply/usb/present")

# g_mass_storage backing file — must be a directory exposed as a FAT32 image,
# or a pre-formatted loop image.  We use the raw recordings directory path
# together with a loop device created at connect time.
_GADGET_MODULE = "g_mass_storage"


class GadgetOffload:
    """Pi Zero 2W USB mass-storage gadget offload (FR-12).

    On USB host connect: remounts ``recordings_dir`` read-only and loads
    ``g_mass_storage`` so the host can read recordings as a USB drive.
    On disconnect: unloads the module and restores read-write access.

    Usage::

        go = GadgetOffload(recordings_dir)
        go.start()          # begins monitoring in background
        ...
        go.stop()           # call before process exit

    The ``pending`` property is set while a recording session is in progress
    at the time of USB connect.  The caller should check it and trigger
    ``activate()`` once the session ends.
    """

    def __init__(self, recordings_dir: Path) -> None:
        self._recordings_dir = recordings_dir
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._lock = threading.Lock()
        self.pending = threading.Event()

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin monitoring for USB host connection in a background thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="earshot-gadget",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring; deactivate gadget if active."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._active:
            self._deactivate()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def activate(self) -> bool:
        """Remount read-only and load g_mass_storage.  Returns True on success."""
        with self._lock:
            if self._active:
                return True
        try:
            self._recordings_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["sudo", "mount", "-o", "remount,ro", str(self._recordings_dir)],
                check=True,
                timeout=10.0,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            _log.warning(
                "gadget: remount read-only failed: %s — skipping gadget activation",
                exc.stderr.decode().strip() if exc.stderr else exc,
            )
            return False

        try:
            subprocess.run(
                [
                    "sudo",
                    "modprobe",
                    _GADGET_MODULE,
                    f"file={self._recordings_dir}",
                    "ro=1",
                    "removable=1",
                ],
                check=True,
                timeout=15.0,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            _log.error(
                "gadget: modprobe %s failed: %s",
                _GADGET_MODULE,
                exc.stderr.decode().strip() if exc.stderr else exc,
            )
            self._remount_rw()
            return False

        with self._lock:
            self._active = True
        _log.info("gadget: g_mass_storage active — recordings exposed to host")
        return True

    def deactivate(self) -> None:
        """Unload g_mass_storage and restore read-write mount."""
        self._deactivate()

    # ── internals ─────────────────────────────────────────────────────────────

    def _deactivate(self) -> None:
        with self._lock:
            if not self._active:
                return
        try:
            subprocess.run(
                ["sudo", "modprobe", "-r", _GADGET_MODULE],
                check=False,
                timeout=10.0,
                capture_output=True,
            )
        except Exception as exc:
            _log.warning("gadget: modprobe -r failed: %s", exc)
        self._remount_rw()
        with self._lock:
            self._active = False
        _log.info("gadget: disconnected — recordings read-write restored")

    def _remount_rw(self) -> None:
        try:
            subprocess.run(
                ["sudo", "mount", "-o", "remount,rw", str(self._recordings_dir)],
                check=False,
                timeout=10.0,
                capture_output=True,
            )
        except Exception as exc:
            _log.warning("gadget: remount read-write failed: %s", exc)

    def _vbus_present(self) -> bool:
        """Return True if a USB host is providing VBUS (5V) on the OTG port."""
        try:
            return _VBUS_PATH.read_text().strip() == "1"
        except OSError:
            return False

    def _monitor_loop(self) -> None:
        was_connected = False
        while not self._stop_event.wait(2.0):
            now_connected = self._vbus_present()
            if now_connected and not was_connected:
                _log.info("gadget: USB host connected")
                self.pending.set()  # caller activates when session allows
            elif not now_connected and was_connected:
                _log.info("gadget: USB host disconnected")
                self.pending.clear()
                if self._active:
                    self._deactivate()
            was_connected = now_connected


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
