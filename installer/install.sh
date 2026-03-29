#!/usr/bin/env bash
# Earshot installer
# Usage: curl -fsSL https://raw.githubusercontent.com/rsmacapinlac/earshot/main/installer/install.sh | bash
#
# Phase 1 (interactive): apt update/upgrade, seeed-voicecard driver, reboot
# Phase 2 (automatic):   system deps, Python venv, model download, service install

set -euo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_URL="https://raw.githubusercontent.com/rsmacapinlac/earshot/main/installer/install.sh"
REPO_URL="https://github.com/rsmacapinlac/earshot.git"
SEEED_URL="https://github.com/HinTak/seeed-voicecard.git"

STATE_DIR="/var/lib/earshot-install"
STATE_FILE="$STATE_DIR/state"
SAVED_SCRIPT="$STATE_DIR/install.sh"

TORCH_VERSION="2.2.2"
TORCH_AUDIO_VERSION="2.2.2"

# ─── Helpers ──────────────────────────────────────────────────────────────────

log()  { echo "==> $*"; }
info() { echo "    $*"; }
err()  { echo "ERROR: $*" >&2; }

error_handler() {
    local exit_code=$1
    local line=$2
    err "Install failed on line $line (exit code: $exit_code)"
    echo ""
    if [ -f "$STATE_FILE" ] && grep -q "^PHASE=2$" "$STATE_FILE" 2>/dev/null; then
        echo "To retry Phase 2:  sudo systemctl restart earshot-install-continue"
        echo "Check logs:        journalctl -u earshot-install-continue -n 50"
    else
        echo "To retry from scratch:"
        echo "  sudo rm -rf $STATE_DIR"
        echo "  curl -fsSL $SCRIPT_URL | bash"
    fi
}

trap 'error_handler $? $LINENO' ERR

# ─── Step 1: Self-save ────────────────────────────────────────────────────────
# When run via `curl | bash`, stdin is the pipe so `read` prompts won't work
# and the script has no path on disk. Download ourselves and re-exec from disk
# so stdin is restored to the terminal.

if [ "${EARSHOT_SAVED:-0}" != "1" ]; then
    if ! command -v curl &>/dev/null; then
        err "curl is required. Install it with: sudo apt-get install -y curl"
        exit 1
    fi
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    curl -fsSL "$SCRIPT_URL" -o "$SAVED_SCRIPT"
    chmod +x "$SAVED_SCRIPT"
    export EARSHOT_SAVED=1
    exec bash "$SAVED_SCRIPT" "$@"
fi

# ─── Step 2: Root check ───────────────────────────────────────────────────────

if [ "$(id -u)" -ne 0 ]; then
    exec sudo EARSHOT_SAVED=1 bash "$0" "$@"
fi

# ─── Dispatcher ───────────────────────────────────────────────────────────────
# Read PHASE from state file. If PHASE=2, run phase 2. Otherwise run phase 1.

if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    if [ "${PHASE:-1}" = "2" ]; then
        phase2
        exit 0
    fi
fi

# ─── Phase 1 ──────────────────────────────────────────────────────────────────

phase1() {
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║         Earshot Installer v0.1           ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    # ── Capture install user ──────────────────────────────────────────────────
    # Must be done before sudo loses the original user context.
    # Never hardcode "pi" — the user may have a different username.

    if [ -n "${SUDO_USER:-}" ]; then
        INSTALL_USER="$SUDO_USER"
    elif INSTALL_USER=$(logname 2>/dev/null); then
        : # logname succeeded
    else
        err "Cannot determine the non-root user. Run as a regular user with sudo."
        exit 1
    fi

    INSTALL_HOME=$(getent passwd "$INSTALL_USER" | cut -d: -f6)
    if [ -z "$INSTALL_HOME" ]; then
        err "Cannot find home directory for user '$INSTALL_USER'."
        exit 1
    fi

    log "Installing for user: $INSTALL_USER (home: $INSTALL_HOME)"

    # ── apt update / upgrade ──────────────────────────────────────────────────

    log "Updating system packages..."
    apt-get update -y
    apt-get upgrade -y
    apt-get install -y git curl

    # ── Prompts ───────────────────────────────────────────────────────────────
    # Collect everything interactive here so Phase 2 can run fully unattended.

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

    # ── Install seeed-voicecard driver ────────────────────────────────────────
    # Using HinTak/seeed-voicecard — the community-maintained fork that supports
    # Raspberry Pi OS Bookworm and kernel 6.x. The original Seeed repo does not
    # reliably support these versions.

    log "Installing ReSpeaker seeed-voicecard driver..."
    local seeed_dir
    seeed_dir=$(mktemp -d)
    git clone --depth=1 "$SEEED_URL" "$seeed_dir"
    bash "$seeed_dir/install.sh"
    rm -rf "$seeed_dir"

    # ── Write state file ──────────────────────────────────────────────────────
    # chmod 600 so the HF token is only readable by root.

    log "Saving install state..."
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"

    (
        umask 077
        cat > "$STATE_FILE" <<EOF
INSTALL_USER=$INSTALL_USER
INSTALL_HOME=$INSTALL_HOME
HF_TOKEN=$HF_TOKEN
API_ENDPOINT=$API_ENDPOINT
API_SECRET=$API_SECRET
PHASE=2
EOF
    )

    # ── Install continuation service ──────────────────────────────────────────

    log "Installing post-reboot continuation service..."
    cat > /etc/systemd/system/earshot-install-continue.service <<'UNIT'
[Unit]
Description=Earshot Install Continuation (post-reboot)
After=network-online.target
Wants=network-online.target
ConditionPathExists=/var/lib/earshot-install/state

[Service]
Type=oneshot
ExecStart=/bin/bash /var/lib/earshot-install/install.sh
StandardOutput=journal+console
StandardError=journal+console
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable earshot-install-continue.service

    # ── Reboot ────────────────────────────────────────────────────────────────

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Phase 1 complete — rebooting to activate the HAT driver    ║"
    echo "║                                                              ║"
    echo "║  Installation will continue automatically after reboot.     ║"
    echo "║  Monitor progress with:                                     ║"
    echo "║    journalctl -u earshot-install-continue -f                ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    sleep 5
    reboot
}

# ─── Phase 2 ──────────────────────────────────────────────────────────────────

phase2() {
    # State file was already sourced by the dispatcher before calling phase2().
    # Variables available: INSTALL_USER, INSTALL_HOME, HF_TOKEN, API_ENDPOINT,
    # API_SECRET, PHASE.

    echo ""
    log "Earshot install — Phase 2 (post-reboot)"
    echo ""

    REPO_DIR="$INSTALL_HOME/earshot"
    VENV_DIR="$REPO_DIR/.venv"

    # ── Verify seeed driver loaded ────────────────────────────────────────────

    log "Verifying ReSpeaker driver..."
    if ! arecord -l 2>/dev/null | grep -qi "seeed\|respeaker\|voicecard"; then
        err "ReSpeaker ALSA device not found after reboot."
        err "Diagnostics:"
        err "  arecord -l"
        err "  dmesg | grep -i snd"
        err "  lsmod | grep snd"
        exit 1
    fi
    info "ReSpeaker device detected."

    # ── System dependencies ───────────────────────────────────────────────────

    log "Installing system dependencies..."
    apt-get update -y
    apt-get install -y \
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

    # ── Add user to hardware groups ───────────────────────────────────────────

    log "Adding $INSTALL_USER to hardware groups..."
    usermod -aG audio,gpio,spi,i2c "$INSTALL_USER"

    # ── Clone repository ──────────────────────────────────────────────────────

    log "Cloning Earshot repository..."
    if [ ! -d "$REPO_DIR/.git" ]; then
        sudo -u "$INSTALL_USER" git clone "$REPO_URL" "$REPO_DIR"
    else
        info "Repository already exists — pulling latest..."
        sudo -u "$INSTALL_USER" git -C "$REPO_DIR" pull
    fi

    # Create data directories (gitignored — not in the repo)
    sudo -u "$INSTALL_USER" mkdir -p \
        "$REPO_DIR/recordings" \
        "$REPO_DIR/tmp"

    # ── Python venv ───────────────────────────────────────────────────────────

    log "Creating Python virtual environment..."
    if [ ! -f "$VENV_DIR/bin/python" ]; then
        sudo -u "$INSTALL_USER" python3 -m venv "$VENV_DIR"
    else
        info "Virtual environment already exists — skipping creation."
    fi

    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/pip" install --quiet --upgrade pip wheel setuptools

    # ── PyTorch (CPU-only wheel) ──────────────────────────────────────────────
    # IMPORTANT: Must use --index-url to get the CPU-only build.
    # The default PyPI torch includes CUDA binaries (~2.5GB) — useless on Pi.

    log "Installing PyTorch (CPU build)..."
    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/pip" install --quiet \
        "torch==$TORCH_VERSION" \
        "torchaudio==$TORCH_AUDIO_VERSION" \
        --index-url https://download.pytorch.org/whl/cpu

    # ── Python dependencies ───────────────────────────────────────────────────

    log "Installing Python dependencies..."
    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/pip" install --quiet \
        -r "$REPO_DIR/installer/requirements.txt"

    # ── Download models ───────────────────────────────────────────────────────
    # Models are cached to ~/.cache/huggingface/ on the install user's account.
    # The HF token is only needed for this one-time download — not at runtime.

    log "Downloading Whisper base model (~150MB)..."
    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/python" - <<'PYEOF'
import whisper
whisper.load_model("base")
print("    Whisper base model ready.")
PYEOF

    log "Downloading pyannote speaker diarization model..."
    sudo -u "$INSTALL_USER" HF_TOKEN="$HF_TOKEN" "$VENV_DIR/bin/python" - <<PYEOF
import os
from pyannote.audio import Pipeline
Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=os.environ["HF_TOKEN"],
)
print("    pyannote model ready.")
PYEOF

    # ── Write config.toml ─────────────────────────────────────────────────────

    log "Writing configuration file..."
    local config_path="$REPO_DIR/config.toml"

    sudo -u "$INSTALL_USER" tee "$config_path" > /dev/null <<TOML
# Earshot Configuration
# Edit this file to customise behaviour.
# Apply changes: sudo systemctl restart earshot

[audio]
sample_rate = 16000    # Hz — ReSpeaker native rate, matches Whisper/pyannote input
channels = 2           # Stereo (both mics captured, downmixed to mono before processing)
bit_depth = 16
mp3_bitrate = 128      # kbps for ffmpeg MP3 encoding

[recording]
max_duration_seconds = 3600  # Stop recording automatically after this duration (1 hour)
min_duration_seconds = 3     # Discard recordings shorter than this
shutdown_hold_seconds = 3    # Hold button this long to trigger safe shutdown

[processing]
whisper_model = "base"  # Options: tiny | base | small
                        # base:  ~150MB model, ~500MB RAM
                        # small: ~500MB model, ~1GB RAM

[storage]
data_dir = "~/earshot"
disk_threshold_percent = 90  # Block new recordings above this disk usage %

[api]
endpoint = "$API_ENDPOINT"
TOML

    if [ -n "$API_SECRET" ]; then
        echo "secret = \"$API_SECRET\"" | \
            sudo -u "$INSTALL_USER" tee -a "$config_path" > /dev/null
    fi

    # ── Install earshot.service ───────────────────────────────────────────────

    log "Installing Earshot systemd service..."
    sed \
        -e "s|__INSTALL_USER__|$INSTALL_USER|g" \
        -e "s|__INSTALL_HOME__|$INSTALL_HOME|g" \
        -e "s|__VENV_DIR__|$VENV_DIR|g" \
        "$REPO_DIR/installer/earshot.service.template" \
        > /etc/systemd/system/earshot.service

    systemctl daemon-reload
    systemctl enable earshot.service
    systemctl start earshot.service

    # ── Cleanup ───────────────────────────────────────────────────────────────

    log "Cleaning up installer state..."
    systemctl disable earshot-install-continue.service
    rm -f /etc/systemd/system/earshot-install-continue.service
    systemctl daemon-reload

    # Remove state dir — this deletes the stored HF token from disk.
    rm -rf "$STATE_DIR"

    # ── Done ──────────────────────────────────────────────────────────────────

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                Earshot installation complete!               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    systemctl status earshot --no-pager || true
    echo ""
    echo "Useful commands:"
    echo "  journalctl -u earshot -f            # Follow logs"
    echo "  sudo systemctl restart earshot      # Restart service"
    echo "  nano $REPO_DIR/config.toml          # Edit config"
    echo "  arecord -l                          # List audio devices"
    echo ""
}

# ─── Entry point ──────────────────────────────────────────────────────────────

phase1
