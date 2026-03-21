from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from silent_install_helper.config_loader import load_config
from silent_install_helper.executor import StepExecutor
from silent_install_helper.models import ExecutionStatus


def make_config(
    tmp_path: Path,
    installer_file: Path,
    log_file: Path,
    steps: list[dict[str, object]],
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "title": "Executor Test",
                "mode": "SILENT",
                "installer": installer_file.name,
                "steps": steps,
            }
        ),
        encoding="utf-8",
    )
    return load_config(config_path, log_file)


def test_executor_succeeds_for_valid_step(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [{"id": "one", "label": "One", "command": "cmd /c echo success"}],
    )

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert summary.results[0].succeeded is True


def test_executor_fails_for_invalid_return_code(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [{"id": "fail", "label": "Fail", "command": "cmd /c exit 5"}],
    )

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.FAILED
    assert summary.failed_step is not None
    assert summary.failed_step.id == "fail"


def test_executor_continues_on_error_when_configured(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [
            {
                "id": "fail",
                "label": "Fail",
                "command": "cmd /c exit 5",
                "continue_on_error": True,
            },
            {"id": "next", "label": "Next", "command": "cmd /c echo next"},
        ],
    )

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert len(summary.results) == 2
    assert summary.results[0].succeeded is False
    assert summary.results[1].succeeded is True


def test_executor_can_be_cancelled(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [{"id": "wait", "label": "Wait", "command": "cmd /c ping 127.0.0.1 -n 8 > nul"}],
    )

    executor = StepExecutor(config, test_logger)
    holder: dict[str, object] = {}
    thread = threading.Thread(target=lambda: holder.setdefault("summary", executor.run()), daemon=True)
    thread.start()
    time.sleep(1)
    executor.request_cancel()
    thread.join()

    summary = holder["summary"]
    assert summary.status == ExecutionStatus.CANCELLED
    assert summary.results[0].error_output == "Cancelled by user."


def test_executor_expands_custom_variables(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "title": "Executor Test",
                "mode": "SILENT",
                "installer": installer_file.name,
                "variables": {
                    "target_dir": "C:\\Temp\\App",
                    "install_flag": "/quiet"
                },
                "steps": [
                    {
                        "id": "one",
                        "label": "One",
                        "command": "cmd /c echo {target_dir} {install_flag}"
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path, log_file)

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert "C:\\Temp\\App /quiet" in summary.results[0].output


def test_executor_fails_for_unknown_variable(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [{"id": "bad", "label": "Bad", "command": "cmd /c echo {missing_var}"}],
    )

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.FAILED
    assert "Unknown variable" in summary.results[0].error_output


def test_executor_expands_app_directory_variables(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config = make_config(
        tmp_path,
        installer_file,
        log_file,
        [{"id": "vars", "label": "Vars", "command": "cmd /c echo {app_dir} && echo {seven_zip_exe}"}],
    )

    summary = StepExecutor(config, test_logger).run()

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert "SilentInstallHelper" in summary.results[0].output
    assert "7z.exe" in summary.results[0].output


def test_executor_reports_live_7zip_status(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "title": "Executor Test",
                "mode": "SILENT",
                "installer": installer_file.name,
                "steps": [
                    {
                        "id": "extract",
                        "label": "Extract",
                        "command": "cmd /c echo - app\\file1.txt && echo 42% 1 && echo Everything is Ok",
                        "output_mode": "7ZIP",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path, log_file)

    live_messages: list[str] = []
    live_progress: list[float] = []
    summary = StepExecutor(config, test_logger).run(
        live_status_callback=lambda step, message, progress: (
            live_messages.append(message),
            live_progress.append(progress) if progress is not None else None,
        )
    )

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert "Extrahiere: file1.txt" in live_messages
    assert "Extrahiere: file1.txt (42%)" in live_messages
    assert "Archiv erfolgreich entpackt" in live_messages
    assert 0.42 in live_progress
    assert 1.0 in live_progress


def test_executor_reports_live_icacls_status(
    tmp_path: Path, installer_file: Path, log_file: Path, test_logger
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "title": "Executor Test",
                "mode": "SILENT",
                "installer": installer_file.name,
                "steps": [
                    {
                        "id": "permissions",
                        "label": "Permissions",
                        "command": (
                            "cmd /c echo C:\\Demo\\a.txt NT AUTHORITY\\SYSTEM:(I)(F) "
                            "&& echo C:\\Demo\\b.txt NT AUTHORITY\\SYSTEM:(I)(F) "
                            "&& echo Successfully processed 2 files; Failed processing 0 files"
                        ),
                        "output_mode": "ICACLS",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path, log_file)

    live_messages: list[str] = []
    summary = StepExecutor(config, test_logger).run(
        live_status_callback=lambda step, message, progress: live_messages.append(message)
    )

    assert summary.status == ExecutionStatus.SUCCEEDED
    assert "Bearbeitet: 1 | Aktuell: a.txt" in live_messages
    assert "Bearbeitet: 2 | Aktuell: b.txt" in live_messages
    assert "Bearbeitet: 2 Dateien | Fehler: 0" in live_messages
