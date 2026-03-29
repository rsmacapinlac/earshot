#!/usr/bin/env bash
# Thin entrypoint: jsDelivr and similar CDNs often cache installer/install.sh for a long time.
# The real script lives at earshot-install.sh (new path → fresh fetch).
#
# Usage (preferred):
#   curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh | bash
#
# This file:
#   curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/install.sh | bash

set -euo pipefail

_CANONICAL="https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh"

echo "==> Fetching current installer (earshot-install.sh)…" >&2
curl -fsSL "$_CANONICAL" | bash
