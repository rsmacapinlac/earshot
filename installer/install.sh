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

# ─── Ensure on-disk copy for systemd continuation ─────────────────────────────
# `curl | bash` saves to $SAVED_SCRIPT and re-execs. If the user runs a local copy
# with EARSHOT_SAVED=1 (e.g. /tmp/install.sh), that path is skipped — but Phase 1
# still enables earshot-install-continue.service, which always runs $SAVED_SCRIPT.
# Copy our script there whenever we are not already executing from that path.

ensure_saved_install_script_on_disk() {
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    local src
    src=$(readlink -f "${BASH_SOURCE[0]}")
    case "$src" in
        /bin/bash | /usr/bin/bash) return 0 ;;
    esac
    if [ ! -f "$src" ]; then
        return 0
    fi
    local dest
    dest=$(readlink -f "$SAVED_SCRIPT" 2>/dev/null) || dest="$SAVED_SCRIPT"
    if [ "$src" != "$dest" ]; then
        install -m 700 "$src" "$SAVED_SCRIPT"
    fi
}

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

ensure_saved_install_script_on_disk

# ─── Dispatcher ───────────────────────────────────────────────────────────────
# Read PHASE from state file and record which phase to run.
# The actual call is deferred to the entry point after all functions are defined.

_RUN_PHASE=1
if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    if [ "${PHASE:-1}" = "2" ]; then
        _RUN_PHASE=2
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
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --fix-missing || true
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
    # Must cd into the seeed dir — install.sh uses relative paths when copying
    # source files into /usr/src/seeed-voicecard-*/
    (cd "$seeed_dir" && bash install.sh)
    rm -rf "$seeed_dir"

    # ── Write state for Phase 2 ────────────────────────────────────────────────
    # Secrets are stored as single-line files (not sourced as shell) so Hugging Face
    # tokens containing quotes, $, etc. do not break the continuation script.

    log "Saving install state..."
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"

    (
        umask 077
        printf '%s\n' "$INSTALL_USER" > "$STATE_DIR/install_user"
        printf '%s\n' "$INSTALL_HOME" > "$STATE_DIR/install_home"
        printf '%s\n' "$API_ENDPOINT" > "$STATE_DIR/api_endpoint"
        printf '%s' "$HF_TOKEN" > "$STATE_DIR/hf_token"
        rm -f "$STATE_DIR/api_secret"
        if [ -n "$API_SECRET" ]; then
            printf '%s' "$API_SECRET" > "$STATE_DIR/api_secret"
        fi
        echo "PHASE=2" > "$STATE_FILE"
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
Environment=EARSHOT_SAVED=1
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
    # Dispatcher sourced only PHASE from $STATE_FILE. Load the rest from root-only
    # files under $STATE_DIR (written in Phase 1).

    echo ""
    log "Earshot install — Phase 2 (post-reboot)"
    echo ""

    read -r INSTALL_USER < "$STATE_DIR/install_user" || true
    read -r INSTALL_HOME < "$STATE_DIR/install_home" || true
    read -r API_ENDPOINT < "$STATE_DIR/api_endpoint" || true
    read -r HF_TOKEN < "$STATE_DIR/hf_token" || true
    API_SECRET=""
    if [ -f "$STATE_DIR/api_secret" ]; then
        read -r API_SECRET < "$STATE_DIR/api_secret" || true
    fi

    if [ -z "${INSTALL_USER:-}" ] || [ -z "${INSTALL_HOME:-}" ] || [ -z "${HF_TOKEN:-}" ]; then
        err "Install state is incomplete (missing user, home, or Hugging Face token)."
        err "Remove $STATE_DIR and re-run the installer from Phase 1."
        exit 1
    fi

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
    # Remove seeed-voicecard from DKMS before installing audio/kernel dev packages.
    # libasound2-dev pulls in new kernel images; their post-install hook would try
    # to auto-build seeed-voicecard, which fails on kernel 6.x, breaking the whole
    # dpkg transaction. Removing the DKMS module here prevents that hook from firing.

    log "Removing seeed-voicecard from DKMS to prevent kernel hook failures..."
    dkms remove seeed-voicecard/0.3 --all 2>/dev/null || true

    log "Installing system dependencies..."
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
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
    # Public HTTPS URL — no TTY required (runs headlessly from systemd).

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

    log "Installing Earshot package (editable)..."
    sudo -u "$INSTALL_USER" "$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR"

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
    sudo -u "$INSTALL_USER" env HF_TOKEN="$HF_TOKEN" "$VENV_DIR/bin/python" - <<PYEOF
import os
from huggingface_hub import login
from pyannote.audio import Pipeline
login(token=os.environ["HF_TOKEN"])
Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
print("    pyannote model ready.")
PYEOF

    # ── Write config.toml ─────────────────────────────────────────────────────
    # Use tomli_w so API URL and secret cannot break TOML syntax or inject keys.

    log "Writing configuration file..."
    local config_path="$REPO_DIR/config.toml"
    export CONFIG_PATH="$config_path"
    export API_ENDPOINT="${API_ENDPOINT:-}"
    export API_SECRET_PATH="$STATE_DIR/api_secret"
    "$VENV_DIR/bin/python" - <<'PYCFG'
import os
from pathlib import Path

import tomli_w

config_path = Path(os.environ["CONFIG_PATH"])
api_endpoint = os.environ.get("API_ENDPOINT", "")
secret_path = Path(os.environ["API_SECRET_PATH"])
secret = secret_path.read_text().strip() if secret_path.is_file() else ""

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
    chown "$INSTALL_USER:$INSTALL_USER" "$config_path"
    chmod 600 "$config_path"

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

if [ "$_RUN_PHASE" = "2" ]; then
    phase2
else
    phase1
fi
