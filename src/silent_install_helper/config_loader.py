from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .models import AppConfig, StepConfig, ThemeMode, UiMode


try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_OUTPUT_MODES = {"AUTO", "NONE", "RAW", "7ZIP", "ICACLS"}


def load_config(config_path: Path, log_path: Path) -> AppConfig:
    raw = _load_raw(config_path)
    mode = _parse_mode(raw.get("mode", "BASIC"))
    theme = _parse_theme(raw.get("theme", "LIGHT"))
    progress_color = _parse_progress_color(raw.get("progress_color"))
    title = str(raw.get("title", "SilentInstallHelper")).strip() or "SilentInstallHelper"
    installer_path = _parse_installer_path(raw.get("installer"), config_path)
    variables = _parse_variables(raw.get("variables", {}))
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ConfigError("The configuration must contain a non-empty 'steps' list.")

    steps = [_parse_step(index, item) for index, item in enumerate(raw_steps, start=1)]
    _validate_unique_step_ids(steps)
    return AppConfig(
        title=title,
        mode=mode,
        theme=theme,
        progress_color=progress_color,
        variables=variables,
        steps=steps,
        installer_path=installer_path,
        log_path=log_path,
    )


def _load_raw(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    suffix = config_path.suffix.lower()
    text = config_path.read_text(encoding="utf-8-sig")
    if suffix in {".json", ".jsonc"}:
        try:
            json_text = _strip_json_comments(text) if suffix == ".jsonc" else text
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON config: {exc}") from exc
    elif suffix in {".yml", ".yaml"}:
        if yaml is None:
            raise ConfigError(
                "YAML support requires 'PyYAML'. Install it or use a JSON config instead."
            )
        try:
            data = yaml.safe_load(text)
        except Exception as exc:  # pragma: no cover - depends on optional parser
            raise ConfigError(f"Invalid YAML config: {exc}") from exc
    else:
        raise ConfigError("Unsupported config format. Use .json, .jsonc, .yml, or .yaml.")

    if not isinstance(data, dict):
        raise ConfigError("The config root element must be an object.")
    return data


def _parse_mode(raw_mode: Any) -> UiMode:
    try:
        return UiMode(str(raw_mode).upper())
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in UiMode)
        raise ConfigError(f"Invalid mode '{raw_mode}'. Allowed values: {allowed}.") from exc


def _parse_theme(raw_theme: Any) -> ThemeMode:
    normalized = str(raw_theme).strip().upper()
    aliases = {
        "LIGHT": ThemeMode.LIGHT,
        "HELL": ThemeMode.LIGHT,
        "DARK": ThemeMode.DARK,
        "DUNKEL": ThemeMode.DARK,
    }
    theme = aliases.get(normalized)
    if theme is None:
        allowed = ", ".join(["LIGHT", "DARK", "HELL", "DUNKEL"])
        raise ConfigError(f"Invalid theme '{raw_theme}'. Allowed values: {allowed}.")
    return theme


def _parse_installer_path(raw_installer: Any, config_path: Path) -> Path:
    installer = str(raw_installer or "").strip()
    if not installer:
        raise ConfigError("The configuration must define an 'installer' path.")

    installer_path = Path(installer).expanduser()
    if not installer_path.is_absolute():
        installer_path = (config_path.parent / installer_path).resolve()
    else:
        installer_path = installer_path.resolve()

    if not installer_path.exists():
        raise ConfigError(f"Installer path does not exist: {installer_path}")

    return installer_path


def _parse_progress_color(raw_color: Any) -> str | None:
    if raw_color is None:
        return None
    color = str(raw_color).strip()
    if not color:
        return None
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        raise ConfigError(
            f"Invalid progress_color '{raw_color}'. Expected a hex color like '#2E9FFF'."
        )
    return color.upper()


def _parse_variables(raw_variables: Any) -> dict[str, str]:
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, dict):
        raise ConfigError("The 'variables' section must be an object.")

    reserved_names = {
        "installer",
        "installer_dir",
        "installer_name",
        "log_path",
        "app_dir",
        "seven_zip_exe",
    }
    variables: dict[str, str] = {}
    for raw_name, raw_value in raw_variables.items():
        name = str(raw_name).strip()
        if not name:
            raise ConfigError("Variable names must not be empty.")
        if not VARIABLE_NAME_PATTERN.match(name):
            raise ConfigError(
                f"Invalid variable name '{name}'. Use letters, digits, and underscores only."
            )
        if name in reserved_names:
            raise ConfigError(f"Variable name '{name}' is reserved and cannot be overridden.")
        if isinstance(raw_value, (dict, list)):
            raise ConfigError(f"Variable '{name}' must be a scalar value, not an object or list.")
        variables[name] = "" if raw_value is None else str(raw_value)
    return variables


def _parse_step(index: int, item: Any) -> StepConfig:
    if not isinstance(item, dict):
        raise ConfigError(f"Step {index} must be an object.")

    step_id = str(item.get("id", f"step-{index}")).strip()
    label = str(item.get("label", f"Step {index}")).strip()
    command = str(item.get("command", "")).strip()
    if not command:
        raise ConfigError(f"Step {step_id} is missing a command.")

    success_codes = item.get("success_codes", [0])
    if not isinstance(success_codes, list) or not all(isinstance(code, int) for code in success_codes):
        raise ConfigError(f"Step {step_id} has invalid success_codes. Expected a list of integers.")

    timeout = item.get("timeout")
    if timeout is not None and not isinstance(timeout, int):
        raise ConfigError(f"Step {step_id} has invalid timeout. Expected an integer number of seconds.")
    if isinstance(timeout, int) and timeout <= 0:
        raise ConfigError(f"Step {step_id} has invalid timeout. Expected a value greater than 0.")

    estimated_duration = item.get("estimated_duration")
    if estimated_duration is not None and not isinstance(estimated_duration, (int, float)):
        raise ConfigError(
            f"Step {step_id} has invalid estimated_duration. Expected a number of seconds."
        )
    if isinstance(estimated_duration, (int, float)) and estimated_duration <= 0:
        raise ConfigError(
            f"Step {step_id} has invalid estimated_duration. Expected a value greater than 0."
        )

    working_directory = item.get("working_directory")
    if working_directory is not None and not isinstance(working_directory, str):
        raise ConfigError(f"Step {step_id} has invalid working_directory. Expected a string path.")

    output_mode = str(item.get("output_mode", "AUTO")).strip().upper() or "AUTO"
    if output_mode not in ALLOWED_OUTPUT_MODES:
        allowed = ", ".join(sorted(ALLOWED_OUTPUT_MODES))
        raise ConfigError(
            f"Step {step_id} has invalid output_mode '{item.get('output_mode')}'. "
            f"Allowed values: {allowed}."
        )

    return StepConfig(
        id=step_id,
        label=label,
        command=command,
        output_mode=output_mode,
        optional=bool(item.get("optional", False)),
        continue_on_error=bool(item.get("continue_on_error", False)),
        success_codes=success_codes,
        working_directory=working_directory,
        timeout=timeout,
        estimated_duration=float(estimated_duration) if estimated_duration is not None else None,
    )


def _validate_unique_step_ids(steps: list[StepConfig]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for step in steps:
        if step.id in seen:
            duplicates.append(step.id)
        seen.add(step.id)
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise ConfigError(f"Duplicate step ids are not allowed: {duplicate_list}.")


def _strip_json_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    string_quote = ""
    escape = False
    i = 0
    length = len(text)

    while i < length:
        char = text[i]
        next_char = text[i + 1] if i + 1 < length else ""

        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == string_quote:
                in_string = False
            i += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            string_quote = char
            result.append(char)
            i += 1
            continue

        if char == "/" and next_char == "/":
            i += 2
            while i < length and text[i] not in "\r\n":
                i += 1
            continue

        if char == "/" and next_char == "*":
            i += 2
            while i + 1 < length and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        result.append(char)
        i += 1

    return "".join(result)
