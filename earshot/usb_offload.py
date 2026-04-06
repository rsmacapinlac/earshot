"""USB offload: FR-11 stick offload (Pi 4B) and FR-12 gadget mode (Pi Zero 2W)."""

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

# Transient FAT32 image backing g_mass_storage (written by earshot-gadget-on).
_GADGET_IMAGE = Path("/tmp/earshot-recordings.img")

# UDC sysfs state path (Pi Zero 2W DWC2 OTG controller).
# Exposes connection state: "not attached" | "attached" | "default" | "addressed" | "configured".
_UDC_STATE_PATH = Path("/sys/class/udc/3f980000.usb/state")


def _udc_state() -> str:
    """Read the current UDC connection state, or 'unavailable' on error."""
    try:
        return _UDC_STATE_PATH.read_text().strip()
    except OSError:
        return "unavailable"


def _gadget_suspended() -> bool:
    """Return True if the USB gadget bus is suspended by the host.

    macOS safe-ejects the drive without physically unplugging — the UDC stays
    in "configured" state but the host suspends the bus.  The gadget.0/suspended
    sysfs attribute reflects this.  We resolve the UDC symlink to find the
    actual device directory so this works on Pi 4B and Pi Zero 2W alike.
    """
    try:
        udc_real = Path(os.path.realpath(str(_UDC_STATE_PATH.parent)))
        return (udc_real / "gadget.0" / "suspended").read_text().strip() == "1"
    except OSError:
        return False


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
        # Set when a USB host has actually enumerated the gadget (UDC → configured).
        # Distinct from ``pending`` (which fires on VBUS / cable-detect) so the
        # app can show IDLE while g_mass_storage is loading and TRANSFER only
        # once the laptop actually sees the drive.
        self.host_connected = threading.Event()
        # Sessions exported into the current image (populated by activate()).
        # _sync_deletions uses this to avoid deleting sessions that were never
        # in the image (e.g. recorded while the gadget was active, or when the
        # image was built from an empty/corrupt state).
        self._exported_sessions: set[str] = set()
        # True once UDC reports "not attached" after a deactivation — prevents
        # the monitor from immediately re-arming pending if the cable is still
        # physically connected when the gadget is deactivated.
        self._saw_detach: bool = True  # guarded by _lock

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
        """Create a FAT32 image of the recordings dir and load g_mass_storage.

        On Pi Zero 2W the helper script (earshot-gadget-on activate) builds a
        sparse FAT32 image, copies recordings into it, then loads g_mass_storage
        backed by that image (read-only).  The image approach avoids remounting
        the live recordings directory read-only, so new recordings can proceed
        once the gadget is deactivated.
        """
        with self._lock:
            if self._active:
                return True
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        # Record which sessions exist now — only these can be deleted by the user.
        self._exported_sessions = {
            d.name for d in self._recordings_dir.iterdir() if d.is_dir()
        } if self._recordings_dir.exists() else set()
        try:
            subprocess.run(
                ["/usr/local/bin/earshot-gadget-on", "activate", str(self._recordings_dir)],
                check=True,
                timeout=120.0,  # image creation + copy may take a while for large recordings
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            _log.error(
                "gadget: earshot-gadget-on failed: %s",
                exc.stderr.decode().strip() if exc.stderr else exc,
            )
            self._exported_sessions = set()
            return False

        with self._lock:
            self._active = True
        _log.info("gadget: g_mass_storage active — waiting for host connection")
        return True

    def deactivate(self) -> None:
        """Unload g_mass_storage and clean up the recordings image."""
        self._deactivate()

    # ── internals ─────────────────────────────────────────────────────────────

    def _sync_deletions(self) -> None:
        """Mirror file deletions from the gadget image back to the Pi.

        The image was a read-write snapshot of the recordings directory.  When
        the user deletes session folders on the laptop, those deletions are
        reflected in the FAT32 image.  Before unloading g_mass_storage, read
        the image with ``mdir`` and remove any session that was exported but is
        no longer present in the image.
        """
        if not _GADGET_IMAGE.exists():
            return
        try:
            env = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}
            result = subprocess.run(
                ["mdir", "-b", "-i", str(_GADGET_IMAGE), "::"],
                capture_output=True,
                text=True,
                timeout=10.0,
                env=env,
            )
            # mdir -b -i IMAGE :: output: one path per line, e.g. "::/20260402T101613".
            # Strip the "::" drive prefix that mtools adds when using the -i flag.
            image_sessions: set[str] = set()
            for line in result.stdout.splitlines():
                name = line.strip().lstrip(":").lstrip("/").rstrip("/").upper()
                if name:
                    image_sessions.add(name)
        except Exception as exc:
            _log.warning("gadget: sync: mdir failed — skipping deletion sync: %s", exc)
            return

        if not self._recordings_dir.exists():
            return

        # If the image appears empty but we exported sessions, something went
        # wrong with the image (e.g. stale module loaded with no backing file).
        # Skip sync entirely rather than deleting sessions the user never saw.
        if not image_sessions and self._exported_sessions:
            _log.warning(
                "gadget: sync: image appears empty but %d session(s) were exported — "
                "skipping deletion sync to avoid data loss",
                len(self._exported_sessions),
            )
            return

        removed = 0
        for session_dir in sorted(self._recordings_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            # Only delete sessions that were actually in the image.
            # Sessions recorded after activation are never touched.
            if session_dir.name not in self._exported_sessions:
                continue
            if session_dir.name.upper() not in image_sessions:
                _log.info("gadget: sync: removing %s (deleted on laptop)", session_dir.name)
                shutil.rmtree(session_dir, ignore_errors=True)
                removed += 1

        if removed:
            _log.info("gadget: sync: %d session(s) removed from Pi", removed)
        else:
            _log.debug("gadget: sync: no deletions detected")

    def _deactivate(self) -> None:
        with self._lock:
            if not self._active:
                return
        # Sync deletions before unloading the module (image must be accessible).
        self._sync_deletions()
        try:
            subprocess.run(
                ["/usr/local/bin/earshot-gadget-off"],
                check=False,
                timeout=15.0,
                capture_output=True,
            )
        except Exception as exc:
            _log.warning("gadget: earshot-gadget-off failed: %s", exc)
        with self._lock:
            self._active = False
            self._saw_detach = False  # require physical unplug before re-arming
        self.host_connected.clear()
        _log.info("gadget: disconnected")

    def _direct_vbus(self) -> bool:
        """Return True if VBUS is readable via power_supply sysfs (Pi 4B path)."""
        try:
            return _VBUS_PATH.read_text().strip() == "1"
        except OSError:
            return False

    def _monitor_loop(self) -> None:
        """Detect USB host connection and manage the gadget lifecycle.

        On Pi 4B the power_supply sysfs path gives VBUS directly.
        On Pi Zero 2W that path is absent, so we load the lightweight ``g_zero``
        probe gadget which allows the UDC to report connection state; once the
        host enumerates it we swap in ``g_mass_storage`` via the activate path.
        """
        probe_loaded = False
        prev_active = False

        while not self._stop_event.wait(2.0):
            with self._lock:
                active = self._active

            # Detect active→inactive transition regardless of which thread
            # caused the deactivation (monitor disconnect vs app button press).
            # Without this, a button-press deactivation leaves probe_loaded=True
            # and g_zero never gets reloaded after earshot-gadget-off unloads it.
            if prev_active and not active:
                probe_loaded = False
            prev_active = active

            if active:
                # Post-activation: watch UDC state for actual host connect/disconnect.
                udc = _udc_state()
                # "suspended" (gadget.0/suspended == 1) means the host suspended the
                # bus — macOS does this on safe-eject without physical unplug.
                # UDC stays "configured" in that case, so check both.
                bus_suspended = _gadget_suspended()
                connected = udc in ("configured", "addressed") and not bus_suspended
                if connected and not self.host_connected.is_set():
                    _log.info("gadget: USB host enumerated (UDC=%s)", udc)
                    self.host_connected.set()
                elif not connected and self.host_connected.is_set():
                    reason = f"UDC={udc}, suspended={bus_suspended}"
                    _log.info("gadget: USB host disconnected (%s)", reason)
                    self.host_connected.clear()
                    self.pending.clear()
                    self._deactivate()
                    probe_loaded = False  # probe was cleared by earshot-gadget-off

            else:
                # Pre-activation: detect cable insertion.

                # Update saw_detach: once UDC reports no cable, we can re-arm.
                udc_now = _udc_state()
                with self._lock:
                    if udc_now in ("not attached", "unavailable"):
                        self._saw_detach = True
                    saw_detach = self._saw_detach

                # Pi 4B: direct VBUS sysfs path.
                if self._direct_vbus():
                    if not self.pending.is_set() and saw_detach:
                        _log.info("gadget: VBUS detected via power_supply sysfs")
                        self.pending.set()
                    continue

                # Pi Zero 2W: load g_zero probe so the UDC can report state.
                if not probe_loaded:
                    try:
                        subprocess.run(
                            ["/usr/local/bin/earshot-gadget-on", "probe"],
                            check=True,
                            capture_output=True,
                            timeout=5.0,
                        )
                        probe_loaded = True
                        _log.info("gadget: g_zero probe loaded")
                    except Exception as exc:
                        _log.warning("gadget: g_zero probe failed: %s", exc)
                    continue

                # Probe loaded — check if a host has connected.
                # Guard with saw_detach: don't re-arm if cable was never removed
                # after the last deactivation (prevents immediate re-trigger after
                # button press or host-disconnect while cable stays plugged in).
                if udc_now in ("configured", "addressed") and not self.pending.is_set() and saw_detach:
                    _log.info("gadget: VBUS detected via g_zero probe")
                    self.pending.set()
                    # g_zero stays loaded; earshot-gadget-on activate will swap it out.


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
