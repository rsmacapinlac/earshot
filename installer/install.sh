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
REPO_DIR="$INSTALL_HOME/earshot"
VENV_DIR="$REPO_DIR/.venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Earshot Installer v0.3           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
log "Installing for user: $INSTALL_USER (home: $INSTALL_HOME)"
echo ""

echo "── API Sync (optional) ──────────────────────────────────────────────"
echo "Earshot uploads audio to a remote API for transcription."
echo "Leave blank to skip — recordings are stored locally until configured."
echo ""
read -rp "API endpoint URL (blank to skip): " API_ENDPOINT

API_SECRET=""
if [ -n "$API_ENDPOINT" ]; then
    read -rsp "API secret/key (blank if none): " API_SECRET
    echo
fi

# ── System packages ─────────────────────────────────────────────────────────

log "Updating system packages..."
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --fix-missing || true
sudo apt-get install -y git curl

# ── ReSpeaker driver ────────────────────────────────────────────────────────
# HinTak/seeed-voicecard — Bookworm / kernel 6.x friendly fork.

log "Installing ReSpeaker seeed-voicecard driver..."
seeed_dir=$(mktemp -d)
git clone --depth=1 "$SEEED_URL" "$seeed_dir"
# Patch seeed-voicecard.c for kernel 6.6+: rtd->id was replaced by rtd->num.
# Without this patch, DKMS fails to build on kernel 6.12+ with:
#   error: 'struct snd_soc_pcm_runtime' has no member named 'id'
sed -i 's/rtd->id/rtd->num/g' "$seeed_dir/seeed-voicecard.c"
(cd "$seeed_dir" && sudo bash install.sh)
rm -rf "$seeed_dir"

# ── Ensure seeed-2mic-voicecard dtoverlay is in config.txt ───────────────────
# The HinTak install.sh writes i2s-mmap/dtparam=i2s=on but may omit the
# seeed-2mic-voicecard overlay that creates the ALSA sound card device node.
# The MCLK itself is provided by the DKMS kernel module above; the dtoverlay
# is needed so the card appears in arecord -l and PipeWire can discover it.
_boot_cfg=""
for _f in /boot/firmware/config.txt /boot/config.txt; do
    [ -f "$_f" ] && _boot_cfg="$_f" && break
done
if [ -n "$_boot_cfg" ]; then
    if ! grep -q "dtoverlay=seeed-2mic-voicecard" "$_boot_cfg"; then
        log "Adding dtoverlay=seeed-2mic-voicecard to $_boot_cfg..."
        echo "dtoverlay=seeed-2mic-voicecard" | sudo tee -a "$_boot_cfg" >/dev/null
    else
        info "dtoverlay=seeed-2mic-voicecard already present in $_boot_cfg."
    fi
else
    err "Could not find Pi boot config.txt — add 'dtoverlay=seeed-2mic-voicecard' manually."
fi

# ── System dependencies ─────────────────────────────────────────────────────
# Do NOT remove seeed-voicecard from DKMS. The DKMS kernel module
# (snd_soc_seeed_voicecard) is the machine driver that ties the WM8960 codec
# to the BCM2835 I2S interface and provides MCLK. Without it, the ALSA card
# enumerates but every hw_params call fails with "No MCLK configured".
# Kernel upgrades will trigger a DKMS rebuild automatically.

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
export API_ENDPOINT="${API_ENDPOINT:-}"
export API_SECRET="${API_SECRET:-}"
"$VENV_DIR/bin/python" - <<'PYCFG'
import os
from pathlib import Path

import tomli_w

config_path = Path(os.environ["CONFIG_PATH"])
api_endpoint = os.environ.get("API_ENDPOINT", "")
secret = os.environ.get("API_SECRET", "").strip()

cfg = {
    "audio": {
        "sample_rate": 16000,
        "channels": 2,
        "bit_depth": 16,
        "opus_bitrate": 32,
        # ReSpeaker: bypass PipeWire and capture directly via ALSA (works from a system
        # service without a user session). Use arecord -l to confirm the card name.
        "alsa_pcm": "plughw:CARD=seeed2micvoicec,DEV=0",
    },
    "recording": {
        "max_duration_seconds": 7200,
        "min_duration_seconds": 3,
        "shutdown_hold_seconds": 3,
    },
    "storage": {
        "data_dir": "~/earshot",
        "disk_threshold_percent": 90,
    },
    "api": {
        "endpoint": api_endpoint,
    },
}
if secret:
    cfg["api"]["secret"] = secret

header = (
    "# Earshot Configuration\n"
    "# Edit this file to customise behaviour.\n"
    "# Apply changes: sudo systemctl restart earshot\n"
    "#\n"
    "# audio.alsa_pcm — ALSA capture device for arecord (preferred on Pi).\n"
    "#   Run: arecord -l   Use plughw:CARD,DEVICE (rate conversion).\n"
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

# ── systemd ──────────────────────────────────────────────────────────────────
# Enable only — ALSA/HAT needs a reboot before the first start works cleanly.

log "Installing Earshot systemd service..."
INSTALL_UID="$(id -u)"
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
echo "║               arecord -l   # confirm ReSpeaker              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
sleep 5
sudo reboot
