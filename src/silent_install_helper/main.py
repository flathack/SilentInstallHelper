from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config_loader import ConfigError, load_config
from .executor import StepExecutor
from .logging_utils import configure_logging
from .models import UiMode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silentinstallhelper",
        description="Execute config-driven installation steps with optional progress UI.",
    )
    parser.add_argument("config", help="Path to the config file (.json, .yml, .yaml).")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional path for the log file. Defaults to ./logs/silentinstallhelper.log",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve()
    log_path = (
        Path(args.log_file).expanduser().resolve()
        if args.log_file
        else Path.cwd() / "logs" / "silentinstallhelper.log"
    )

    try:
        config = load_config(config_path=config_path, log_path=log_path)
    except ConfigError as exc:
        parser.error(str(exc))

    logger = configure_logging(log_path)
    logger.info("Starting SilentInstallHelper.")
    logger.info("Installer path: %s", config.installer_path)
    logger.info("Config path: %s", config_path)
    logger.info("Mode: %s", config.mode.value)

    executor = StepExecutor(config=config, logger=logger)
    if config.mode == UiMode.SILENT:
        return 0 if executor.run().succeeded else 1

    try:
        from .ui import run_app
    except ImportError:
        parser.error(
            "PySide6 is required to run the UI. Install dependencies with 'pip install -e .' "
            "or 'pip install PySide6'."
        )
    return run_app(config=config, executor=executor)


if __name__ == "__main__":
    sys.exit(main())
