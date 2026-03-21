from __future__ import annotations

import logging
from pathlib import Path

import pytest

from silent_install_helper.logging_utils import configure_logging


@pytest.fixture()
def installer_file(tmp_path: Path) -> Path:
    installer = tmp_path / "installer.exe"
    installer.write_text("dummy", encoding="utf-8")
    return installer


@pytest.fixture()
def installer_name(installer_file: Path) -> str:
    return installer_file.name


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "test.log"


@pytest.fixture()
def test_logger(log_file: Path) -> logging.Logger:
    return configure_logging(log_file)
