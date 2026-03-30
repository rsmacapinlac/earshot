"""CLI entry point (`python -m earshot`) used by systemd."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from earshot.app import EarshotApp
from earshot.config import config_file_path, load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="earshot")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.toml (default: $EARSHOT_CONFIG or ./config.toml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging on stderr",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    path = config_file_path(args.config)
    cfg = load_config(path)
    EarshotApp(cfg).run()


if __name__ == "__main__":
    main()
