from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class UiMode(str, Enum):
    FULL = "FULL"
    BASIC = "BASIC"
    SILENT = "SILENT"


class ThemeMode(str, Enum):
    LIGHT = "LIGHT"
    DARK = "DARK"


class ExecutionStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class StepConfig:
    id: str
    label: str
    command: str
    output_mode: str = "AUTO"
    optional: bool = False
    continue_on_error: bool = False
    success_codes: list[int] = field(default_factory=lambda: [0])
    working_directory: str | None = None
    timeout: int | None = None
    estimated_duration: float | None = None


@dataclass(slots=True)
class AppConfig:
    title: str
    mode: UiMode
    theme: ThemeMode
    progress_color: str | None
    variables: dict[str, str]
    steps: list[StepConfig]
    installer_path: Path
    log_path: Path


@dataclass(slots=True)
class StepResult:
    step: StepConfig
    return_code: int
    succeeded: bool
    output: str
    error_output: str
