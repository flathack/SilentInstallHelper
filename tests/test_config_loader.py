from __future__ import annotations

import json
from pathlib import Path

import pytest

from silent_install_helper.config_loader import ConfigError, load_config
from silent_install_helper.models import ThemeMode, UiMode


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_valid_json_config(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "title": "Demo",
            "mode": "silent",
            "theme": "dunkel",
            "progress_color": "#2e9fff",
            "installer": installer_file.name,
            "variables": {
                "customer_name": "Steve",
                "install_mode": "silent"
            },
            "steps": [
                {
                    "id": "prepare",
                    "label": "Prepare",
                    "command": "cmd /c echo hello",
                    "estimated_duration": 1.5,
                }
            ],
        },
    )

    config = load_config(config_path, log_file)

    assert config.title == "Demo"
    assert config.mode == UiMode.SILENT
    assert config.theme == ThemeMode.DARK
    assert config.progress_color == "#2E9FFF"
    assert config.variables["customer_name"] == "Steve"
    assert len(config.steps) == 1
    assert config.steps[0].id == "prepare"
    assert config.steps[0].estimated_duration == 1.5
    assert config.installer_path == installer_file.resolve()


def test_rejects_duplicate_step_ids(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "steps": [
                {"id": "dup", "label": "One", "command": "cmd /c echo one"},
                {"id": "dup", "label": "Two", "command": "cmd /c echo two"},
            ],
        },
    )

    with pytest.raises(ConfigError, match="Duplicate step ids"):
        load_config(config_path, log_file)


def test_rejects_non_positive_timeout(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "steps": [
                {"id": "prepare", "label": "Prepare", "command": "cmd /c echo one", "timeout": 0}
            ],
        },
    )

    with pytest.raises(ConfigError, match="greater than 0"):
        load_config(config_path, log_file)


def test_loads_yaml_config(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "title: Demo YAML",
                "mode: BASIC",
                "theme: light",
                f"installer: {installer_file.name}",
                "steps:",
                "  - id: prepare",
                "    label: Prepare",
                "    command: cmd /c echo hello",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path, log_file)

    assert config.title == "Demo YAML"
    assert config.mode == UiMode.BASIC
    assert config.theme == ThemeMode.LIGHT


def test_loads_jsonc_config(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.jsonc"
    config_path.write_text(
        "\n".join(
            [
                "// Kommentierte Config",
                "{",
                '  "title": "Demo JSONC",',
                '  "mode": "BASIC",',
                '  "theme": "HELL",',
                f'  "installer": "{installer_file.name}",',
                '  /* Schrittdefinition */',
                '  "steps": [',
                '    {',
                '      "id": "prepare",',
                '      "label": "Prepare",',
                '      "command": "cmd /c echo hello"',
                '    }',
                '  ]',
                '}',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_path, log_file)

    assert config.title == "Demo JSONC"
    assert config.mode == UiMode.BASIC
    assert config.theme == ThemeMode.LIGHT


def test_rejects_missing_installer(log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "steps": [
                {"id": "prepare", "label": "Prepare", "command": "cmd /c echo one"}
            ],
        },
    )

    with pytest.raises(ConfigError, match="must define an 'installer' path"):
        load_config(config_path, log_file)


def test_rejects_invalid_estimated_duration(
    installer_file: Path, log_file: Path, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "steps": [
                {
                    "id": "prepare",
                    "label": "Prepare",
                    "command": "cmd /c echo one",
                    "estimated_duration": 0,
                }
            ],
        },
    )

    with pytest.raises(ConfigError, match="estimated_duration"):
        load_config(config_path, log_file)


def test_rejects_invalid_variable_name(
    installer_file: Path, log_file: Path, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "variables": {
                "bad-name": "x"
            },
            "steps": [
                {"id": "prepare", "label": "Prepare", "command": "cmd /c echo one"}
            ],
        },
    )

    with pytest.raises(ConfigError, match="Invalid variable name"):
        load_config(config_path, log_file)


def test_rejects_reserved_variable_name(
    installer_file: Path, log_file: Path, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "variables": {
                "installer": "x"
            },
            "steps": [
                {"id": "prepare", "label": "Prepare", "command": "cmd /c echo one"}
            ],
        },
    )

    with pytest.raises(ConfigError, match="reserved"):
        load_config(config_path, log_file)


def test_rejects_invalid_progress_color(
    installer_file: Path, log_file: Path, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "progress_color": "blue",
            "steps": [
                {"id": "prepare", "label": "Prepare", "command": "cmd /c echo one"}
            ],
        },
    )

    with pytest.raises(ConfigError, match="progress_color"):
        load_config(config_path, log_file)


def test_loads_output_mode(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "steps": [
                {
                    "id": "extract",
                    "label": "Extract",
                    "command": "cmd /c echo hi",
                    "output_mode": "7zip",
                }
            ],
        },
    )

    config = load_config(config_path, log_file)

    assert config.steps[0].output_mode == "7ZIP"


def test_loads_icacls_output_mode(installer_file: Path, log_file: Path, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    write_json(
        config_path,
        {
            "mode": "BASIC",
            "installer": installer_file.name,
            "steps": [
                {
                    "id": "permissions",
                    "label": "Permissions",
                    "command": "icacls C:\\Temp /grant Users:(OI)(CI)RX /T /C",
                    "output_mode": "icacls",
                }
            ],
        },
    )

    config = load_config(config_path, log_file)

    assert config.steps[0].output_mode == "ICACLS"
