"""CLI entry point (`python -m earshot`) used by systemd."""

from __future__ import annotations

import sys
import time


def main() -> None:
    # Placeholder until the full application is implemented; keeps the
    # installer-delivered systemd unit in a valid running state.
    sys.stderr.write(
        "Earshot is running in placeholder mode until the full application ships.\n"
    )
    sys.stderr.flush()
    while True:
        time.sleep(86400)


if __name__ == "__main__":
    main()
