#!/usr/bin/env bash
# Thin entrypoint for curl users. Preferred: clone the repo and run earshot-install.sh.
#
#   git clone https://github.com/rsmacapinlac/earshot.git ~/earshot
#   bash ~/earshot/installer/earshot-install.sh
#
# This file (CDN → full installer):
#   curl -fsSL https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/install.sh | bash

set -euo pipefail

_CANONICAL="https://cdn.jsdelivr.net/gh/rsmacapinlac/earshot@main/installer/earshot-install.sh"

echo "==> Fetching current installer (earshot-install.sh)…" >&2
curl -fsSL "$_CANONICAL" | bash
