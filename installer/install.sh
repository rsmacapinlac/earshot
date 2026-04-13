#!/usr/bin/env bash
# Earshot installer
#
# Run as your normal login user — the script calls sudo where it needs root:
#
#   sudo apt install -y git
#   git clone https://github.com/rsmacapinlac/earshot.git ~/earshot
#   bash ~/earshot/installer/install.sh
#
# Updates: cd ~/earshot && git pull && bash installer/install.sh

set -euo pipefail

REPO_URL="https://github.com/rsmacapinlac/earshot.git"
SEEED_URL="https://github.com/HinTak/seeed-voicecard.git"

# ─── Helpers ──────────────────────────────────────────────────────────────────

log()  { echo "==> $*"; }
info() { echo "    $*"; }

# Return a safe job count for cmake builds.  On devices with < 1 GB RAM
# (e.g. Pi Zero 2W) parallel cc1plus processes exhaust memory; cap at 2.
_build_jobs() {
    local total_kb
    total_kb=$(awk '/^MemTotal/ { print $2 }' /proc/meminfo)
    if [ "${total_kb:-0}" -lt 1048576 ]; then
        echo 2
    else
        nproc
    fi
}
err()  { echo "ERROR: $*" >&2; }

error_handler() {
    err "Install failed on line $2 (exit code: $1)"
    echo ""
    echo "Re-run from your clone:"
    echo "  cd ~/earshot && git pull && bash installer/install.sh"
}
trap 'error_handler $? $LINENO' ERR

if [ "$(id -u)" -eq 0 ]; then
    err "Run this installer as a normal user (e.g. ritchie or pi), not as root."
    err "The script will use sudo when it needs elevated privileges."
    exit 1
fi

INSTALL_USER="$(id -un)"
INSTALL_HOME="$HOME"
INSTALL_UID="$(id -u)"
INSTALL_GID="$(id -g)"
REPO_DIR="$INSTALL_HOME/earshot"
VENV_DIR="$REPO_DIR/.venv"

SKIP_TRANSCRIPTION=false
TRANSCRIPTION_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --no-transcription)   SKIP_TRANSCRIPTION=true ;;
        --transcription-only) TRANSCRIPTION_ONLY=true ;;
        *) err "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Transcription-only upgrade path ──────────────────────────────────────────
# Downloads faster_whisper model, patches config.toml, restarts service.
# Use this on an already-installed device when upgrading to v0.3.0+.

if $TRANSCRIPTION_ONLY; then
    MODELS_DIR="$INSTALL_HOME/.local/share/earshot/models"
    TX_MODEL="${TX_MODEL:-tiny.en}"

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   Earshot — transcription setup         ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    # 1. Re-install Python package to pick up faster_whisper dependency.
    log "Updating Python package..."
    "$VENV_DIR/bin/pip" install --quiet -e "${REPO_DIR}[pi]"

    # 2. Pre-download faster_whisper model.
    log "Pre-downloading faster_whisper model ($TX_MODEL)..."
    mkdir -p "$MODELS_DIR"
    export MODELS_DIR TX_MODEL
    "$VENV_DIR/bin/python" - <<'PYMODEL'
import os
import sys

try:
    from faster_whisper import WhisperModel
except ImportError as e:
    print(f"    ERROR: failed to import faster_whisper: {e}", file=sys.stderr)
    sys.exit(1)

models_dir = os.environ.get("MODELS_DIR")
tx_model = os.environ.get("TX_MODEL", "tiny.en")

try:
    print(f"    Loading {tx_model} model (this may take a minute on first run)...")
    WhisperModel(tx_model, device="cpu", download_root=models_dir)
    print(f"    Model cached at {models_dir}")
except Exception as e:
    print(f"    ERROR: failed to download model: {e}", file=sys.stderr)
    sys.exit(1)
PYMODEL

    # 4. Add [transcription] section to config.toml if missing.
    log "Patching config.toml..."
    "$VENV_DIR/bin/python" - <<'PYCFG'
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
import tomli_w

config_path = Path.home() / "earshot" / "config.toml"
raw = config_path.read_bytes()
cfg = tomllib.loads(raw.decode())

if "transcription" not in cfg:
    cfg["transcription"] = {"enabled": True, "model": "tiny.en", "threads": 2}
    config_path.write_bytes(tomli_w.dumps(cfg).encode())
    print("    Added [transcription] section to config.toml")
else:
    print("    [transcription] already present — no changes made")
PYCFG

    # 5. Restart service to load new code and config.
    log "Restarting earshot service..."
    sudo systemctl restart earshot.service
    sleep 2
    systemctl is-active earshot.service && info "earshot is running." || info "earshot failed to start — check: journalctl -u earshot -n 30"

    echo ""
    echo "Done. Transcription is enabled."
    echo "The device will transcribe completed sessions after 3 minutes of idle."
    echo "LED turns amber while transcribing."
    echo ""
    exit 0
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Earshot Installer v0.5           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
log "Installing for user: $INSTALL_USER (home: $INSTALL_HOME)"
if $SKIP_TRANSCRIPTION; then
    info "Transcription support: skipped (--no-transcription)"
fi
echo ""

# ── HAT selection ────────────────────────────────────────────────────────────

HAT="respeaker"
log "HAT: Seeed ReSpeaker 2-Mic Pi HAT"

# ── System packages ─────────────────────────────────────────────────────────

log "Updating system packages..."
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --fix-missing || true
sudo apt-get install -y git curl

# ── HAT audio driver (mutually exclusive) ────────────────────────────────────

_boot_cfg=""
for _f in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "$_f" ] && _boot_cfg="$_f" && break
done

if [ "$HAT" = "respeaker" ]; then
    # HinTak/seeed-voicecard — Bookworm / kernel 6.x friendly fork.
    log "Installing ReSpeaker seeed-voicecard driver..."
    seeed_dir=$(mktemp -d)
    git clone --depth=1 "$SEEED_URL" "$seeed_dir"
    # Patch seeed-voicecard.c for kernel 6.6+: rtd->id was replaced by rtd->num.
    sed -i 's/rtd->id/rtd->num/g' "$seeed_dir/seeed-voicecard.c"
    (cd "$seeed_dir" && sudo bash install.sh)
    rm -rf "$seeed_dir"

    if [ -n "$_boot_cfg" ]; then
        if ! grep -q "dtoverlay=seeed-2mic-voicecard" "$_boot_cfg"; then
            log "Adding dtoverlay=seeed-2mic-voicecard to $_boot_cfg..."
            echo "dtoverlay=seeed-2mic-voicecard" | sudo tee -a "$_boot_cfg" >/dev/null
        else
            info "dtoverlay=seeed-2mic-voicecard already present."
        fi
    else
        err "Could not find Pi boot config.txt — add 'dtoverlay=seeed-2mic-voicecard' manually."
    fi

    ALSA_PCM="plughw:CARD=seeed2micvoicec,DEV=0"
fi

# ── System dependencies ─────────────────────────────────────────────────────

log "Installing system dependencies..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    swig \
    ffmpeg \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    liblgpio-dev \
    python3-lgpio \
    dosfstools \
    mtools

log "Adding $INSTALL_USER to hardware groups..."
sudo usermod -aG audio,gpio,spi,i2c "$INSTALL_USER"

# ── Earshot repo ────────────────────────────────────────────────────────────

log "Cloning Earshot repository..."
if [ ! -d "$REPO_DIR/.git" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
else
    info "Repository already exists — pulling latest..."
    git -C "$REPO_DIR" pull
fi

# ── Python venv ─────────────────────────────────────────────────────────────

log "Creating Python virtual environment..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
else
    info "Virtual environment already exists — skipping creation."
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel setuptools

log "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/installer/requirements.txt"

log "Installing Earshot package (editable) with Pi extras..."
"$VENV_DIR/bin/pip" install --quiet -e "${REPO_DIR}[pi]"

# ── transcription (faster_whisper) ──────────────────────────────────────────

MODELS_DIR="$INSTALL_HOME/.local/share/earshot/models"
TX_MODEL="${TX_MODEL:-tiny.en}"

if $SKIP_TRANSCRIPTION; then
    log "Skipping faster_whisper model download (--no-transcription)."
    TRANSCRIPTION_ENABLED=false
else
    TRANSCRIPTION_ENABLED=true

    log "Pre-downloading faster_whisper model ($TX_MODEL)..."
    mkdir -p "$MODELS_DIR"
    export MODELS_DIR TX_MODEL
    "$VENV_DIR/bin/python" - <<'PYMODEL'
import os
import sys

try:
    from faster_whisper import WhisperModel
except ImportError as e:
    print(f"    ERROR: failed to import faster_whisper: {e}", file=sys.stderr)
    sys.exit(1)

models_dir = os.environ.get("MODELS_DIR")
tx_model = os.environ.get("TX_MODEL", "tiny.en")

try:
    print(f"    Loading {tx_model} model...")
    WhisperModel(tx_model, device="cpu", download_root=models_dir)
    print(f"    Model cached at {models_dir}")
except Exception as e:
    print(f"    ERROR: failed to download model: {e}", file=sys.stderr)
    sys.exit(1)
PYMODEL
fi

# ── config.toml ─────────────────────────────────────────────────────────────

log "Writing configuration file..."
export CONFIG_PATH="$REPO_DIR/config.toml"
export HAT_VALUE="$HAT"
export ALSA_PCM_VALUE="$ALSA_PCM"
export TRANSCRIPTION_ENABLED_VALUE="$TRANSCRIPTION_ENABLED"
"$VENV_DIR/bin/python" - <<'PYCFG'
import os
from pathlib import Path

import tomli_w

config_path = Path(os.environ["CONFIG_PATH"])
hat = os.environ["HAT_VALUE"]
alsa_pcm = os.environ["ALSA_PCM_VALUE"]
transcription_enabled = os.environ["TRANSCRIPTION_ENABLED_VALUE"].lower() == "true"

cfg = {
    "hardware": {
        "hat": hat,
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 2,
        "bit_depth": 16,
        "opus_bitrate": 32,
        "alsa_pcm": alsa_pcm,
    },
    "recording": {
        "chunk_duration_seconds": 900,  # 15 minutes
        "min_duration_seconds": 3,
        "shutdown_hold_seconds": 3,
    },
    "storage": {
        "data_dir": "~/earshot",
        "disk_threshold_percent": 90,
    },
    "display": {
        "brightness": 80,
    },
    "transcription": {
        "enabled": transcription_enabled,
        "model": "tiny.en",
        "threads": 2,
    },
}

header = (
    "# Earshot Configuration\n"
    "# Edit this file to customise behaviour.\n"
    "# Apply changes: sudo systemctl restart earshot\n"
    "#\n"
    "# hardware.hat — connected HAT: 'respeaker'\n"
    "#\n"
    "# audio.alsa_pcm — ALSA capture device for arecord (preferred on Pi).\n"
    "#   Run: arecord -l   Use plughw:CARD,DEVICE (rate conversion).\n"
    "#\n"
    "# recording.chunk_duration_seconds — length of each audio chunk (default: 900 = 15 min).\n"
    "#\n"
    "# storage.recordings_dir — override recordings destination (default: data_dir/recordings).\n"
    "#   Example: recordings_dir = \"/mnt/usb/earshot-recordings\"\n"
    "#\n"
    "# transcription.enabled — set to false to disable on-device transcription.\n"
    "# transcription.model  — 'tiny.en' (default) or 'base.en'.\n"
    "# transcription.threads — faster_whisper cpu_threads (default: 2).\n\n"
)

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, "wb") as f:
    f.write(header.encode())
    tomli_w.dump(cfg, f)
PYCFG
chmod 600 "$REPO_DIR/config.toml"

# ── USB offload setup ────────────────────────────────────────────────────────

if [ "$HAT" = "respeaker" ]; then
    # FR-11: Pi 4B USB stick — udev triggers a systemd template service to mount.
    # Using a systemd unit (rather than RUN{program}) ensures the device is fully
    # ready before mount runs (BindsTo/After guarantee ordering) and handles
    # unmount cleanly on removal via ExecStop.
    log "Installing USB auto-mount service and udev rule..."
    sudo mkdir -p /mnt/earshot-usb

    MOUNT_SERVICE="/etc/systemd/system/earshot-usb@.service"
    cat <<SERVICE | sudo tee "$MOUNT_SERVICE" >/dev/null
[Unit]
Description=Mount earshot USB stick (%I)
BindsTo=dev-%i.device
After=dev-%i.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/mount -o uid=$INSTALL_UID,gid=$INSTALL_GID /dev/%I /mnt/earshot-usb
ExecStop=/usr/bin/umount -l /mnt/earshot-usb
SERVICE
    sudo systemctl daemon-reload

    UDEV_RULE="/etc/udev/rules.d/99-earshot-usb.rules"
    cat <<UDEV | sudo tee "$UDEV_RULE" >/dev/null
# Earshot: auto-mount FAT32 USB stick for recording offload (FR-11).
# On Pi 4B, USB drives enumerate as sd*; the system SD card is mmcblk0.
SUBSYSTEM=="block", KERNEL=="sd?[0-9]", ENV{ID_FS_TYPE}=="vfat", TAG+="systemd", ENV{SYSTEMD_WANTS}+="earshot-usb@%k.service"
UDEV
    sudo udevadm control --reload-rules
    info "udev rule written to $UDEV_RULE"
fi

# ── systemd ──────────────────────────────────────────────────────────────────
# Enable only — ALSA/HAT needs a reboot before the first start works cleanly.

log "Installing Earshot systemd service..."
sudo sed \
    -e "s|__INSTALL_USER__|$INSTALL_USER|g" \
    -e "s|__INSTALL_HOME__|$INSTALL_HOME|g" \
    -e "s|__VENV_DIR__|$VENV_DIR|g" \
    -e "s|__INSTALL_UID__|$INSTALL_UID|g" \
    "$REPO_DIR/installer/earshot.service.template" \
    | sudo tee /etc/systemd/system/earshot.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable earshot.service
info "Service enabled (will start after reboot)."

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Install complete — rebooting the Pi                        ║"
echo "║                                                              ║"
echo "║  After boot:  sudo systemctl status earshot                 ║"
echo "║               journalctl -u earshot -f                       ║"
echo "║               arecord -l   # confirm audio card             ║"
if ! $SKIP_TRANSCRIPTION; then
    echo "║                                                              ║"
    echo "║  Transcription: amber LED pulsates while transcribing.      ║"
    echo "║  Disable: set transcription.enabled = false in config.toml ║"
fi
echo "║                                                              ║"
echo "║  Optional: add a phone hotspot for SSH access on the go:   ║"
echo "║    sudo nmcli connection add type wifi con-name hotspot \\   ║"
echo "║      ssid \"YourHotspot\" wifi-sec.key-mgmt wpa-psk \\        ║"
echo "║      wifi-sec.psk \"password\" connection.autoconnect yes     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
sleep 5
sudo reboot
