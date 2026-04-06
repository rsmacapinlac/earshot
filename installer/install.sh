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
# Installs whisper-cli + model, patches config.toml, restarts service.
# Use this on an already-installed device when upgrading from v0.1.0 to v0.2.0.

if $TRANSCRIPTION_ONLY; then
    WHISPER_VERSION="v1.7.5"
    WHISPER_BIN_URL="https://github.com/ggerganov/whisper.cpp/releases/download/${WHISPER_VERSION}/whisper-linux-aarch64.tar.gz"
    MODELS_DIR="$INSTALL_HOME/.local/share/earshot/models"
    MODEL_FILE="ggml-tiny.en-q5_1.bin"
    MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_FILE}"

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   Earshot v0.2.0 — transcription setup  ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    # 1. Re-install Python package to pick up new earshot.transcription module.
    log "Updating Python package..."
    "$VENV_DIR/bin/pip" install --quiet -e "${REPO_DIR}[pi]"

    # 2. Install whisper-cli if not already present.
    if command -v whisper-cli &>/dev/null; then
        info "whisper-cli already installed: $(command -v whisper-cli)"
    else
        log "Installing whisper.cpp binary (${WHISPER_VERSION})..."
        _tmp_dir=$(mktemp -d)
        if curl --silent --fail --location "$WHISPER_BIN_URL" \
                | tar xz -C "$_tmp_dir" 2>/dev/null; then
            _bin=$(find "$_tmp_dir" -name "whisper-cli" -type f | head -1)
            if [ -n "$_bin" ]; then
                sudo install -m 755 "$_bin" /usr/local/bin/whisper-cli
                info "whisper-cli installed from pre-built binary."
            else
                info "Binary not found in archive — building from source..."
                _bin=""
            fi
        else
            info "Pre-built download failed — building from source..."
            _bin=""
        fi
        rm -rf "$_tmp_dir"

        if [ -z "${_bin:-}" ]; then
            log "Building whisper.cpp from source (this takes a few minutes)..."
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cmake
            _src_dir=$(mktemp -d)
            git clone --depth=1 \
                --branch "$WHISPER_VERSION" \
                https://github.com/ggerganov/whisper.cpp.git \
                "$_src_dir"
            cmake -B "$_src_dir/build" -S "$_src_dir" \
                -DWHISPER_BUILD_TESTS=OFF \
                -DBUILD_SHARED_LIBS=OFF
            cmake --build "$_src_dir/build" --config Release --target whisper-cli -j "$(_build_jobs)"
            sudo install -m 755 "$_src_dir/build/bin/whisper-cli" /usr/local/bin/whisper-cli
            rm -rf "$_src_dir"
            info "whisper-cli installed from source."
        fi
    fi

    # 3. Download model if not already present.
    log "Downloading whisper model ($MODEL_FILE)..."
    mkdir -p "$MODELS_DIR"
    if [ ! -f "$MODELS_DIR/$MODEL_FILE" ]; then
        curl --fail --location --output "$MODELS_DIR/$MODEL_FILE" "$MODEL_URL"
        info "Model saved to $MODELS_DIR/$MODEL_FILE"
    else
        info "Model already present: $MODELS_DIR/$MODEL_FILE"
    fi

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

echo "Which HAT is connected?"
echo "  1) Seeed ReSpeaker 2-Mic Pi HAT"
echo "  2) Whisplay HAT (PiSugar)"
echo ""
while true; do
    read -rp "Enter 1 or 2: " hat_choice
    case "$hat_choice" in
        1) HAT="respeaker"; break ;;
        2) HAT="whisplay";  break ;;
        *) echo "  Please enter 1 or 2." ;;
    esac
done
echo ""
log "Selected HAT: $HAT"

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

else
    # Whisplay HAT: upstream WM8960 driver (different from seeed-voicecard).
    # The WM8960 codec driver (snd_soc_wm8960) is already compiled into the
    # Raspberry Pi kernel — no DKMS or kernel headers needed.
    log "Configuring Whisplay WM8960 dtoverlay..."
    # The upstream WM8960 driver is enabled via dtoverlay — no custom DKMS needed.
    if [ -n "$_boot_cfg" ]; then
        if ! grep -q "dtoverlay=wm8960-soundcard" "$_boot_cfg"; then
            log "Adding dtoverlay=wm8960-soundcard to $_boot_cfg..."
            echo "dtoverlay=wm8960-soundcard" | sudo tee -a "$_boot_cfg" >/dev/null
        else
            info "dtoverlay=wm8960-soundcard already present."
        fi
        # Enable SPI (required for the ST7789 LCD via luma.lcd).
        if grep -q "^#dtparam=spi=on" "$_boot_cfg"; then
            log "Enabling SPI (uncommenting dtparam=spi=on)..."
            sudo sed -i "s/^#dtparam=spi=on/dtparam=spi=on/" "$_boot_cfg"
        elif ! grep -q "^dtparam=spi=on" "$_boot_cfg"; then
            log "Adding dtparam=spi=on to $_boot_cfg..."
            echo "dtparam=spi=on" | sudo tee -a "$_boot_cfg" >/dev/null
        else
            info "dtparam=spi=on already present."
        fi
        # Pi Zero 2W: enable OTG gadget mode (FR-12).
        # Check only in [all] section — the [cm5] section may have dwc2,dr_mode=host
        # which only applies to CM5 and must not suppress the Zero's dwc2 entry.
        if ! awk "/^\[all\]/,/^\[/" "$_boot_cfg" | grep -q "dtoverlay=dwc2"; then
            log "Adding dtoverlay=dwc2 (USB gadget mode) to $_boot_cfg..."
            sudo sed -i "/^\[all\]/a dtoverlay=dwc2" "$_boot_cfg"
        else
            info "dtoverlay=dwc2 already present in [all] section."
        fi
    else
        err "Could not find Pi boot config.txt — add 'dtoverlay=wm8960-soundcard' manually."
    fi

    # Pi Zero 2W: load dwc2 module at boot for USB gadget mode (FR-12).
    _cmdline=""
    for _f in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
        [ -f "$_f" ] && _cmdline="$_f" && break
    done
    if [ -n "$_cmdline" ]; then
        if ! grep -q "modules-load=dwc2" "$_cmdline"; then
            log "Adding modules-load=dwc2 to $_cmdline..."
            sudo sed -i 's/$/ modules-load=dwc2/' "$_cmdline"
        else
            info "modules-load=dwc2 already present in $_cmdline."
        fi
    else
        err "Could not find cmdline.txt — add 'modules-load=dwc2' to kernel cmdline manually."
    fi

    ALSA_PCM="plughw:CARD=wm8960soundcard,DEV=0"

    # The WM8960 driver defaults leave the input boost preamp disconnected from
    # the ADC, producing near-silence on capture.  Enable the boost path and
    # persist via alsactl so the setting survives reboots.
    log "Configuring WM8960 capture mixer (enabling input boost path)..."
    if command -v amixer &>/dev/null; then
        amixer -c wm8960soundcard sset "Left Input Mixer Boost"  on >/dev/null
        amixer -c wm8960soundcard sset "Right Input Mixer Boost" on >/dev/null
        sudo alsactl store
        info "WM8960 capture mixer configured and saved."
    else
        err "amixer not found — run manually after reboot:"
        err "  amixer -c wm8960soundcard sset 'Left Input Mixer Boost' on"
        err "  amixer -c wm8960soundcard sset 'Right Input Mixer Boost' on"
        err "  sudo alsactl store"
    fi
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

# ── whisper.cpp (FR-18) ──────────────────────────────────────────────────────

WHISPER_VERSION="v1.7.5"
WHISPER_BIN_URL="https://github.com/ggerganov/whisper.cpp/releases/download/${WHISPER_VERSION}/whisper-linux-aarch64.tar.gz"
MODELS_DIR="$INSTALL_HOME/.local/share/earshot/models"
MODEL_FILE="ggml-tiny.en-q5_1.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_FILE}"

if $SKIP_TRANSCRIPTION; then
    log "Skipping whisper.cpp and model download (--no-transcription)."
    TRANSCRIPTION_ENABLED=false
else
    TRANSCRIPTION_ENABLED=true

    if command -v whisper-cli &>/dev/null; then
        info "whisper-cli already installed: $(command -v whisper-cli)"
    else
        log "Installing whisper.cpp binary (${WHISPER_VERSION})..."
        _tmp_dir=$(mktemp -d)
        if curl --silent --fail --location "$WHISPER_BIN_URL" \
                | tar xz -C "$_tmp_dir" 2>/dev/null; then
            # Archive contains a single binary or a directory — find whisper-cli.
            _bin=$(find "$_tmp_dir" -name "whisper-cli" -type f | head -1)
            if [ -n "$_bin" ]; then
                sudo install -m 755 "$_bin" /usr/local/bin/whisper-cli
                info "whisper-cli installed from pre-built binary."
            else
                err "whisper-cli binary not found in release archive — falling back to build."
                _bin=""
            fi
        else
            info "Pre-built binary download failed — building whisper.cpp from source..."
            _bin=""
        fi
        rm -rf "$_tmp_dir"

        if [ -z "$_bin" ]; then
            # Build from source.
            log "Building whisper.cpp from source (requires cmake)..."
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cmake
            _src_dir=$(mktemp -d)
            git clone --depth=1 \
                --branch "$WHISPER_VERSION" \
                https://github.com/ggerganov/whisper.cpp.git \
                "$_src_dir"
            cmake -B "$_src_dir/build" -S "$_src_dir" \
                -DWHISPER_BUILD_TESTS=OFF \
                -DBUILD_SHARED_LIBS=OFF
            cmake --build "$_src_dir/build" --config Release --target whisper-cli -j "$(_build_jobs)"
            sudo install -m 755 "$_src_dir/build/bin/whisper-cli" /usr/local/bin/whisper-cli
            rm -rf "$_src_dir"
            info "whisper-cli installed from source."
        fi
    fi

    log "Downloading whisper model ($MODEL_FILE, ~31 MB)..."
    mkdir -p "$MODELS_DIR"
    if [ ! -f "$MODELS_DIR/$MODEL_FILE" ]; then
        curl --silent --fail --location --output "$MODELS_DIR/$MODEL_FILE" "$MODEL_URL"
        info "Model saved to $MODELS_DIR/$MODEL_FILE"
    else
        info "Model already present: $MODELS_DIR/$MODEL_FILE"
    fi
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
    "# hardware.hat — connected HAT: 'respeaker' or 'whisplay'\n"
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
    "# transcription.model  — 'tiny.en' (default, Pi Zero 2W safe) or 'base.en' (Pi 4B).\n"
    "# transcription.threads — whisper-cli thread count (default: 2).\n\n"
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
else
    # FR-12: Pi Zero 2W gadget mode — install helper scripts + narrow sudoers rules.
    # We install helpers to /usr/local/bin so sudoers can reference fixed absolute
    # paths with no wildcards (Debian Trixie visudo rejects wildcard mount args).
    log "Installing USB gadget helper scripts..."

    sudo install -m 755 /dev/stdin /usr/local/bin/earshot-gadget-on <<'GADGETON'
#!/bin/bash
# Earshot FR-12: USB gadget helper — probe detection and mass-storage activation.
# Runs with CAP_SYS_MODULE and CAP_SYS_ADMIN inherited from the earshot service.
#
# Usage:
#   earshot-gadget-on probe             — load g_zero to detect VBUS
#   earshot-gadget-on activate <dir>    — create FAT32 image from <dir>, load g_mass_storage
set -euo pipefail
export PATH="/usr/sbin:/sbin:/usr/bin:/bin:$PATH"

CMD="${1:-activate}"
# Use /tmp so the service user can write without root ownership issues.
IMAGE="/tmp/earshot-recordings.img"

case "$CMD" in
  probe)
    # Load a minimal gadget so the UDC can report VBUS / host connection state.
    # Runs with CAP_SYS_MODULE inherited from the earshot service.
    modprobe g_zero 2>/dev/null || true
    ;;

  activate)
    RECORDINGS_DIR="${2:?recordings dir required for activate}"

    # Calculate required image size: recordings content + 20 % margin, min 32 MB.
    USED_KB=$(du -sk "$RECORDINGS_DIR" 2>/dev/null | awk '{print $1}')
    USED_KB=${USED_KB:-0}
    SIZE_KB=$(( (USED_KB * 12 / 10) + 32768 ))   # +20% then +32 MB floor
    [ "$SIZE_KB" -lt 32768 ] && SIZE_KB=32768

    # Unload probe gadget if still present.
    modprobe -r g_zero 2>/dev/null || true

    # Create sparse FAT32 image (seek= makes it sparse; no data written for count=0).
    dd if=/dev/zero of="$IMAGE" bs=1024 count=0 seek="$SIZE_KB" 2>/dev/null
    /sbin/mkfs.fat -F 32 -n EARSHOT "$IMAGE" >/dev/null 2>&1

    # Copy recordings into the image using mtools (no loop-mount or root needed).
    # MTOOLS_SKIP_CHECK=1 suppresses disk-geometry warnings on sparse images.
    export MTOOLS_SKIP_CHECK=1
    for entry in "$RECORDINGS_DIR"/*/; do
        [ -d "$entry" ] || continue
        session_name=$(basename "$entry")
        mmd -i "$IMAGE" "::$session_name" 2>/dev/null || true
        mcopy -i "$IMAGE" -s "$entry"* "::$session_name/" 2>/dev/null || true
    done

    # Expose the image as a USB mass storage device (read-write so the user
    # can delete sessions on the laptop; deletions are synced back on disconnect).
    modprobe g_mass_storage "file=$IMAGE" ro=0 removable=1
    ;;

  *)
    echo "Usage: $0 {probe|activate <recordings-dir>}" >&2
    exit 1
    ;;
esac
GADGETON

    sudo install -m 755 /dev/stdin /usr/local/bin/earshot-gadget-off <<'GADGETOFF'
#!/bin/bash
# Earshot FR-12: deactivate USB gadget and clean up image.
# Runs with CAP_SYS_MODULE inherited from the earshot service.
set -euo pipefail
export PATH="/usr/sbin:/sbin:/usr/bin:/bin:$PATH"
modprobe -r g_mass_storage 2>/dev/null || true
modprobe -r g_zero 2>/dev/null || true
rm -f /tmp/earshot-recordings.img
GADGETOFF

    log "Installing sudoers rules for USB gadget mode..."
    SUDOERS_FILE="/etc/sudoers.d/earshot-gadget"
    cat <<SUDOERS | sudo tee "$SUDOERS_FILE" >/dev/null
# Earshot: allow service user to manage USB gadget without a password (FR-12).
$INSTALL_USER ALL=(ALL) NOPASSWD: /usr/local/bin/earshot-gadget-on
$INSTALL_USER ALL=(ALL) NOPASSWD: /usr/local/bin/earshot-gadget-off
SUDOERS
    sudo chmod 440 "$SUDOERS_FILE"
    info "sudoers rule written to $SUDOERS_FILE"
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
if [ "$HAT" = "whisplay" ]; then
echo "║                                                              ║"
echo "║  Whisplay HAT: plug into a laptop USB port to offload       ║"
echo "║  recordings via USB mass storage (FR-12).                   ║"
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
