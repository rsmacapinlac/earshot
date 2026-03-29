#!/usr/bin/env bash
# Earshot installer (canonical script — use this URL if install.sh is CDN-stale)
# Usage: curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh | bash
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
    echo "Fix the issue above, then re-run:"
    echo "  curl -fsSL $SCRIPT_URL | bash"
    echo ""
    echo "If you see /dev/tty or permission errors over SSH, use a login TTY:"
    echo "  ssh -t user@pi"
    echo "Or save and run locally:"
    echo "  curl -fsSL $SCRIPT_URL -o ~/earshot-install.sh && bash ~/earshot-install.sh"
}

trap 'error_handler $? $LINENO' ERR

# ─── Bootstrap (curl | bash) ──────────────────────────────────────────────────
# stdin is the pipe, so interactive prompts would read EOF. Download a copy and run
# it with bash (no execute bit needed — avoids noexec-on-/tmp and chmod confusion).
#
# Do NOT use `exec bash … </dev/tty` — if /dev/tty cannot be opened (non-interactive
# SSH, some IDE terminals), the shell reports "Permission denied". We try /dev/tty
# only when it is readable+writable; otherwise we warn and continue (prompts may
# fail unless you use `ssh -t` or run from a real TTY).

if [ "${EARSHOT_BOOTSTRAP_DONE:-0}" != "1" ]; then
    if ! command -v curl &>/dev/null; then
        err "curl is required. Install it with: sudo apt-get install -y curl"
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

# ── DKMS: avoid kernel upgrade hook failure (see installer comments in v0.1) ──

log "Removing seeed-voicecard from DKMS to prevent kernel hook failures..."
sudo dkms remove seeed-voicecard/0.3 --all 2>/dev/null || true

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

log "Installing Earshot package (editable)..."
"$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR"

# ── Models ───────────────────────────────────────────────────────────────────

log "Downloading Whisper base model (~150MB)..."
"$VENV_DIR/bin/python" - <<'PYEOF'
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
    kwargs.setdefault("weights_only", False)
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
    "# Apply changes: sudo systemctl restart earshot\n\n"
)

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, "wb") as f:
    f.write(header.encode())
    tomli_w.dump(cfg, f)
PYCFG
chmod 600 "$REPO_DIR/config.toml"

# ── systemd: enable only (ALSA/HAT may need a reboot before first start works) ─

log "Installing Earshot systemd service..."
sudo sed \
    -e "s|__INSTALL_USER__|$INSTALL_USER|g" \
    -e "s|__INSTALL_HOME__|$INSTALL_HOME|g" \
    -e "s|__VENV_DIR__|$VENV_DIR|g" \
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
