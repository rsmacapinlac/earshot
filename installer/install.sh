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

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Earshot Installer v0.4           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
log "Installing for user: $INSTALL_USER (home: $INSTALL_HOME)"
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
        # Pi Zero 2W: enable OTG gadget mode (FR-12)
        if ! grep -q "dtoverlay=dwc2" "$_boot_cfg"; then
            log "Adding dtoverlay=dwc2 (USB gadget mode) to $_boot_cfg..."
            echo "dtoverlay=dwc2" | sudo tee -a "$_boot_cfg" >/dev/null
        else
            info "dtoverlay=dwc2 already present."
        fi
    else
        err "Could not find Pi boot config.txt — add 'dtoverlay=wm8960-soundcard' manually."
    fi

    ALSA_PCM="plughw:CARD=wm8960soundcard,DEV=0"
fi

# ── System dependencies ─────────────────────────────────────────────────────

log "Installing system dependencies..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    ffmpeg \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0

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

# ── config.toml ─────────────────────────────────────────────────────────────

log "Writing configuration file..."
export CONFIG_PATH="$REPO_DIR/config.toml"
export HAT_VALUE="$HAT"
export ALSA_PCM_VALUE="$ALSA_PCM"
"$VENV_DIR/bin/python" - <<'PYCFG'
import os
from pathlib import Path

import tomli_w

config_path = Path(os.environ["CONFIG_PATH"])
hat = os.environ["HAT_VALUE"]
alsa_pcm = os.environ["ALSA_PCM_VALUE"]

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
    "#   Example: recordings_dir = \"/mnt/usb/earshot-recordings\"\n\n"
)

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, "wb") as f:
    f.write(header.encode())
    tomli_w.dump(cfg, f)
PYCFG
chmod 600 "$REPO_DIR/config.toml"

# ── USB offload setup ────────────────────────────────────────────────────────

if [ "$HAT" = "respeaker" ]; then
    # FR-11: Pi 4B USB stick — udev auto-mount rule
    log "Installing USB auto-mount rule and creating mount point..."
    sudo mkdir -p /mnt/earshot-usb
    UDEV_RULE="/etc/udev/rules.d/99-earshot-usb.rules"
    cat <<UDEV | sudo tee "$UDEV_RULE" >/dev/null
# Earshot: auto-mount FAT32 USB stick for recording offload (FR-11).
# On Pi 4B, USB drives enumerate as sd*; the system SD card is mmcblk0.
SUBSYSTEM=="block", ACTION=="add", KERNEL=="sd?[0-9]", ENV{ID_FS_TYPE}=="vfat", RUN{program}+="/usr/bin/mount -o uid=$INSTALL_UID,gid=$INSTALL_GID /dev/%k /mnt/earshot-usb"
SUBSYSTEM=="block", ACTION=="remove", KERNEL=="sd?[0-9]", RUN{program}+="/usr/bin/umount -l /mnt/earshot-usb"
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
# Earshot FR-12: activate USB mass storage gadget.
set -euo pipefail
RECORDINGS_DIR="${1:?recordings dir required}"
/usr/bin/mount -o remount,ro "$RECORDINGS_DIR"
/usr/sbin/modprobe g_mass_storage "file=$RECORDINGS_DIR" ro=1 removable=1
GADGETON
    sudo install -m 755 /dev/stdin /usr/local/bin/earshot-gadget-off <<'GADGETOFF'
#!/bin/bash
# Earshot FR-12: deactivate USB mass storage gadget.
set -euo pipefail
RECORDINGS_DIR="${1:?recordings dir required}"
/usr/sbin/modprobe -r g_mass_storage || true
/usr/bin/mount -o remount,rw "$RECORDINGS_DIR" || true
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
