#!/usr/bin/env bash
# Earshot installer
#
# Preferred (avoids curl/CDN issues):
#   git clone https://github.com/rsmacapinlac/earshot.git ~/earshot
#   bash ~/earshot/installer/earshot-install.sh
#
# Alternative: curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh | bash
#
# Single session: prompts, driver, system packages, Python env, models, systemd, then reboot.
# Run as a normal login user; the script calls sudo for root-only steps.

set -euo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_URL="https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh"
REPO_URL="https://github.com/rsmacapinlac/earshot.git"
SEEED_URL="https://github.com/HinTak/seeed-voicecard.git"

TORCH_VERSION="2.6.0"
TORCH_AUDIO_VERSION="2.6.0"

# ─── Helpers ──────────────────────────────────────────────────────────────────

log()  { echo "==> $*"; }
info() { echo "    $*"; }
err()  { echo "ERROR: $*" >&2; }

error_handler() {
    local exit_code=$1
    local line=$2
    err "Install failed on line $line (exit code: $exit_code)"
    echo ""
    echo "Re-run from your clone:"
    echo "  cd ~/earshot && git pull && bash installer/earshot-install.sh"
    echo ""
    echo "Or one-liner (needs curl):"
    echo "  curl -fsSL $SCRIPT_URL | bash"
}

trap 'error_handler $? $LINENO' ERR

# ─── Bootstrap (curl | bash only) ─────────────────────────────────────────────
# When you run `bash ~/earshot/installer/earshot-install.sh` from a clone, this path
# is skipped — no curl, no /dev/tty workaround.
#
# When stdin is a pipe (curl | bash), download a copy to ~/.cache and re-run it
# with stdin from the terminal so prompts work.

if [ "${EARSHOT_BOOTSTRAP_DONE:-0}" != "1" ]; then
    _self_path=$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)
    if [[ "$_self_path" == */installer/earshot-install.sh ]] && [ -f "$_self_path" ]; then
        export EARSHOT_BOOTSTRAP_DONE=1
    fi
fi

if [ "${EARSHOT_BOOTSTRAP_DONE:-0}" != "1" ]; then
    if ! command -v curl &>/dev/null; then
        err "curl is not installed. Clone the repo and run the installer locally:"
        err "  git clone $REPO_URL ~/earshot && bash ~/earshot/installer/earshot-install.sh"
        exit 1
    fi
    if [ -z "${HOME:-}" ]; then
        err "HOME is not set. Log in as a normal user and try again."
        exit 1
    fi
    _bcache="${XDG_CACHE_HOME:-$HOME/.cache}/earshot"
    mkdir -p "$_bcache"
    _bootstrap_script="$_bcache/install-bootstrap.sh"
    umask 077
    curl -fsSL "$SCRIPT_URL" -o "$_bootstrap_script"
    chmod 600 "$_bootstrap_script"
    export EARSHOT_BOOTSTRAP_DONE=1

    _bootstrap_status=0
    if [ -r /dev/tty ] && [ -w /dev/tty ]; then
        bash "$_bootstrap_script" </dev/tty "$@" || _bootstrap_status=$?
    else
        echo "" >&2
        echo "WARNING: no usable /dev/tty (use: ssh -t user@host for a TTY)." >&2
        echo "         Hugging Face / API prompts may not work from this session." >&2
        echo "" >&2
        bash "$_bootstrap_script" "$@" || _bootstrap_status=$?
    fi
    exit "$_bootstrap_status"
fi

# ─── Main install ─────────────────────────────────────────────────────────────

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
echo "║         Earshot Installer v0.2           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
log "Installing for user: $INSTALL_USER (home: $INSTALL_HOME)"
echo ""

echo "── Hugging Face ─────────────────────────────────────────────────────"
echo "pyannote.audio requires a one-time Hugging Face access token to"
echo "download the speaker diarization model. After install, no account"
echo "or internet connection is needed."
echo ""
echo "Get a token at: https://huggingface.co/settings/tokens"
echo "Accept model terms at:"
echo "  https://hf.co/pyannote/speaker-diarization-3.1"
echo "  https://hf.co/pyannote/segmentation-3.0"
echo ""

HF_TOKEN=""
while [ -z "$HF_TOKEN" ]; do
    read -rsp "Hugging Face access token: " HF_TOKEN
    echo
    if [ -z "$HF_TOKEN" ]; then
        echo "Token cannot be empty."
    fi
done

echo ""
echo "── API Sync (optional) ──────────────────────────────────────────────"
echo "Earshot can sync transcripts to a remote API when internet is"
echo "available. Leave blank to skip — the device works fully offline."
echo ""
read -rp "API endpoint URL (blank to skip): " API_ENDPOINT

API_SECRET=""
if [ -n "$API_ENDPOINT" ]; then
    read -rsp "API secret/key (blank if none): " API_SECRET
    echo
fi

# ── Remove legacy two-phase installer (if present) ────────────────────────────

if [ -f /etc/systemd/system/earshot-install-continue.service ]; then
    log "Removing legacy earshot-install-continue service..."
    sudo systemctl disable earshot-install-continue.service 2>/dev/null || true
    sudo systemctl stop earshot-install-continue.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/earshot-install-continue.service
    sudo systemctl daemon-reload
fi
sudo rm -rf /var/lib/earshot-install 2>/dev/null || true

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

# ── DKMS: seeed-voicecard provides the ASoC machine driver that configures MCLK ─
# Do NOT remove seeed-voicecard from DKMS. The DKMS kernel module
# (snd_soc_seeed_voicecard) is the machine driver that ties the WM8960 codec
# to the BCM2835 I2S interface and provides MCLK. Without it, the ALSA card
# enumerates but every hw_params call fails with "No MCLK configured".
# Kernel upgrades will trigger a DKMS rebuild automatically — this is correct
# behaviour, not a problem to work around.

log "Installing system dependencies..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    ffmpeg \
    libsndfile1 \
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

mkdir -p "$REPO_DIR/recordings" "$REPO_DIR/tmp"

# ── Python venv ─────────────────────────────────────────────────────────────

log "Creating Python virtual environment..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
else
    info "Virtual environment already exists — skipping creation."
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel setuptools

log "Installing PyTorch (CPU build)..."
"$VENV_DIR/bin/pip" install --quiet \
    "torch==$TORCH_VERSION" \
    "torchaudio==$TORCH_AUDIO_VERSION" \
    --index-url https://download.pytorch.org/whl/cpu

log "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/installer/requirements.txt"

log "Installing Earshot package (editable) with Pi extras..."
"$VENV_DIR/bin/pip" install --quiet -e "${REPO_DIR}[pi]"

# ── Models ───────────────────────────────────────────────────────────────────

log "Downloading Whisper base model (~150MB)..."
"$VENV_DIR/bin/python" - <<'PYEOF'
import torch

_real_torch_load = torch.load

def _patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _real_torch_load(*args, **kwargs)

torch.load = _patched_load

import whisper
whisper.load_model("base")
print("    Whisper base model ready.")
PYEOF

log "Downloading pyannote speaker diarization model..."
HF_TOKEN="$HF_TOKEN" "$VENV_DIR/bin/python" - <<'PYEOF'
import os

import torch

# PyTorch 2.6+ defaults torch.load(weights_only=True). pyannote / lightning checkpoints
# embed types that fail that path; HF model weights are a trusted source here.
_real_torch_load = torch.load

def _torch_load_for_pyannote_checkpoints(*args, **kwargs):
    # lightning_fabric passes weights_only=True explicitly; setdefault would not override.
    kwargs["weights_only"] = False
    return _real_torch_load(*args, **kwargs)

torch.load = _torch_load_for_pyannote_checkpoints

from huggingface_hub import login
from pyannote.audio import Pipeline

login(token=os.environ["HF_TOKEN"])
Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
print("    pyannote model ready.")
PYEOF

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
        "mp3_bitrate": 128,
        # ReSpeaker: bypass PipeWire and capture directly via ALSA (works from a system
        # service without a user session). Use arecord -l to confirm the card name.
        "alsa_pcm": "plughw:CARD=seeed2micvoicec,DEV=0",
    },
    "recording": {
        "max_duration_seconds": 3600,
        "min_duration_seconds": 3,
        "shutdown_hold_seconds": 3,
    },
    "processing": {
        "whisper_model": "base",
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
    "#   Run: arecord -l   Use plughw:CARD,DEVICE (rate conversion).\n\n"
)

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, "wb") as f:
    f.write(header.encode())
    tomli_w.dump(cfg, f)
PYCFG
chmod 600 "$REPO_DIR/config.toml"

# ── systemd: enable only (ALSA/HAT may need a reboot before first start works) ─

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
echo "║  Software install complete — rebooting the Pi               ║"
echo "║                                                              ║"
echo "║  After boot:  sudo systemctl status earshot                 ║"
echo "║               journalctl -u earshot -f                       ║"
echo "║               arecord -l   # confirm ReSpeaker              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
sleep 5
sudo reboot
