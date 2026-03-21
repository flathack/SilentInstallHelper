from __future__ import annotations

import logging
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import AppConfig, ExecutionStatus, StepConfig, StepResult


ProgressCallback = Callable[[int, int, StepConfig, str], None]
LiveStatusCallback = Callable[[StepConfig, str, float | None], None]


@dataclass(slots=True)
class ExecutionSummary:
    status: ExecutionStatus
    completed_steps: int
    total_steps: int
    failed_step: StepConfig | None
    active_step: StepConfig | None
    results: list[StepResult]

    @property
    def succeeded(self) -> bool:
        return self.status == ExecutionStatus.SUCCEEDED

    @property
    def cancelled(self) -> bool:
        return self.status == ExecutionStatus.CANCELLED


class StepExecutor:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self._cancel_requested = threading.Event()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None
        self._step_live_state: dict[str, dict[str, str]] = {}

    def run(
        self,
        progress_callback: ProgressCallback | None = None,
        live_status_callback: LiveStatusCallback | None = None,
    ) -> ExecutionSummary:
        self._cancel_requested.clear()
        results: list[StepResult] = []
        total_steps = len(self.config.steps)

        for index, step in enumerate(self.config.steps, start=1):
            if self._cancel_requested.is_set():
                return ExecutionSummary(
                    status=ExecutionStatus.CANCELLED,
                    completed_steps=index - 1,
                    total_steps=total_steps,
                    failed_step=None,
                    active_step=step,
                    results=results,
                )

            if progress_callback is not None:
                progress_callback(index - 1, total_steps, step, "running")

            result = self._run_step(step, live_status_callback=live_status_callback)
            results.append(result)
            self._step_live_state.pop(step.id, None)

            if self._cancel_requested.is_set():
                if progress_callback is not None:
                    progress_callback(index - 1, total_steps, step, "cancelled")
                return ExecutionSummary(
                    status=ExecutionStatus.CANCELLED,
                    completed_steps=index - 1,
                    total_steps=total_steps,
                    failed_step=None,
                    active_step=step,
                    results=results,
                )

            if progress_callback is not None:
                state = "success" if result.succeeded else "failed"
                progress_callback(index, total_steps, step, state)

            if not result.succeeded and not (step.optional or step.continue_on_error):
                return ExecutionSummary(
                    status=ExecutionStatus.FAILED,
                    completed_steps=index - 1,
                    total_steps=total_steps,
                    failed_step=step,
                    active_step=step,
                    results=results,
                )

        return ExecutionSummary(
            status=ExecutionStatus.SUCCEEDED,
            completed_steps=total_steps,
            total_steps=total_steps,
            failed_step=None,
            active_step=None,
            results=results,
        )

    def request_cancel(self) -> None:
        self.logger.warning("Cancellation requested by user.")
        self._cancel_requested.set()
        with self._process_lock:
            if self._active_process is not None and self._active_process.poll() is None:
                try:
                    self._active_process.terminate()
                    self.logger.warning("Termination signal sent to active step process.")
                except OSError:
                    self.logger.exception("Failed to terminate active step process cleanly.")

    def _run_step(
        self,
        step: StepConfig,
        live_status_callback: LiveStatusCallback | None = None,
    ) -> StepResult:
        try:
            command = self._expand_command(step.command)
            cwd = Path(step.working_directory) if step.working_directory else self.config.installer_path.parent
            self.logger.info("Starting step '%s': %s", step.id, command)

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self._process_lock:
                self._active_process = process

            output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stdout, "stdout", output_queue),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stderr, "stderr", output_queue),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            output_mode = self._resolve_output_mode(step, command)

            started_at = time.monotonic()
            while True:
                self._drain_output_queue(
                    output_queue=output_queue,
                    step=step,
                    output_mode=output_mode,
                    stdout_lines=stdout_lines,
                    stderr_lines=stderr_lines,
                    live_status_callback=live_status_callback,
                )

                if self._cancel_requested.is_set():
                    process.terminate()
                    process.wait(timeout=5)
                    stdout_thread.join(timeout=1)
                    stderr_thread.join(timeout=1)
                    self._drain_output_queue(
                        output_queue=output_queue,
                        step=step,
                        output_mode=output_mode,
                        stdout_lines=stdout_lines,
                        stderr_lines=stderr_lines,
                        live_status_callback=live_status_callback,
                    )
                    stdout = "".join(stdout_lines)
                    stderr = "".join(stderr_lines)
                    self.logger.warning("Step '%s' was cancelled.", step.id)
                    return StepResult(
                        step=step,
                        return_code=-1,
                        succeeded=False,
                        output=stdout,
                        error_output="Cancelled by user." if not stderr else stderr,
                    )

                if step.timeout is not None and time.monotonic() - started_at > step.timeout:
                    process.kill()
                    process.wait(timeout=5)
                    stdout_thread.join(timeout=1)
                    stderr_thread.join(timeout=1)
                    self._drain_output_queue(
                        output_queue=output_queue,
                        step=step,
                        output_mode=output_mode,
                        stdout_lines=stdout_lines,
                        stderr_lines=stderr_lines,
                        live_status_callback=live_status_callback,
                    )
                    stdout = "".join(stdout_lines)
                    stderr = "".join(stderr_lines)
                    self.logger.exception("Step '%s' timed out.", step.id)
                    return StepResult(
                        step=step,
                        return_code=-1,
                        succeeded=False,
                        output=stdout,
                        error_output=f"Timeout after {step.timeout} seconds.",
                    )

                return_code = process.poll()
                if return_code is not None:
                    stdout_thread.join(timeout=1)
                    stderr_thread.join(timeout=1)
                    self._drain_output_queue(
                        output_queue=output_queue,
                        step=step,
                        output_mode=output_mode,
                        stdout_lines=stdout_lines,
                        stderr_lines=stderr_lines,
                        live_status_callback=live_status_callback,
                    )
                    stdout = "".join(stdout_lines)
                    stderr = "".join(stderr_lines)
                    succeeded = return_code in step.success_codes
                    self.logger.info(
                        "Finished step '%s' with return code %s.",
                        step.id,
                        return_code,
                    )
                    if stdout:
                        self.logger.info("stdout for '%s': %s", step.id, stdout.strip())
                    if stderr:
                        self.logger.warning("stderr for '%s': %s", step.id, stderr.strip())
                    return StepResult(
                        step=step,
                        return_code=return_code,
                        succeeded=succeeded,
                        output=stdout,
                        error_output=stderr,
                    )

                time.sleep(0.1)
        except OSError as exc:
            self.logger.exception("Step '%s' failed to start.", step.id)
            return StepResult(
                step=step,
                return_code=-1,
                succeeded=False,
                output="",
                error_output=str(exc),
            )
        except ValueError as exc:
            self.logger.exception("Step '%s' has invalid placeholders.", step.id)
            return StepResult(
                step=step,
                return_code=-1,
                succeeded=False,
                output="",
                error_output=str(exc),
            )
        finally:
            with self._process_lock:
                self._active_process = None

    def _expand_command(self, command: str) -> str:
        app_dir = self._runtime_directory()
        variables = {
            "installer": str(self.config.installer_path),
            "installer_dir": str(self.config.installer_path.parent),
            "installer_name": self.config.installer_path.name,
            "log_path": str(self.config.log_path),
            "app_dir": str(app_dir),
            "seven_zip_exe": str(app_dir / "7z.exe"),
        }
        variables.update(self.config.variables)
        try:
            return command.format(**variables)
        except KeyError as exc:
            raise ValueError(f"Unknown variable in command: {exc.args[0]}") from exc

    def _runtime_directory(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[2]

    def _read_stream(
        self,
        stream,
        stream_name: str,
        output_queue: queue.Queue[tuple[str, str | None]],
    ) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                output_queue.put((stream_name, line))
        finally:
            stream.close()
            output_queue.put((stream_name, None))

    def _drain_output_queue(
        self,
        output_queue: queue.Queue[tuple[str, str | None]],
        step: StepConfig,
        output_mode: str,
        stdout_lines: list[str],
        stderr_lines: list[str],
        live_status_callback: LiveStatusCallback | None,
    ) -> None:
        while True:
            try:
                stream_name, line = output_queue.get_nowait()
            except queue.Empty:
                return

            if line is None:
                continue

            if stream_name == "stdout":
                stdout_lines.append(line)
                self.logger.info("stdout line for '%s': %s", step.id, line.rstrip())
            else:
                stderr_lines.append(line)
                self.logger.warning("stderr line for '%s': %s", step.id, line.rstrip())

            status_line, progress_ratio = self._format_live_status(step, line, output_mode)
            if status_line and live_status_callback is not None:
                live_status_callback(step, status_line, progress_ratio)

    def _resolve_output_mode(self, step: StepConfig, expanded_command: str) -> str:
        if step.output_mode != "AUTO":
            return step.output_mode

        lowered = expanded_command.lower()
        if "icacls" in lowered:
            return "ICACLS"
        if "7z.exe" in lowered or re.search(r"(^|[\\\\/ ])7z($|[\\\\/ ])", lowered):
            return "7ZIP"
        return "RAW"

    def _format_live_status(
        self,
        step: StepConfig,
        line: str,
        output_mode: str,
    ) -> tuple[str | None, float | None]:
        stripped = line.strip()
        if not stripped or output_mode == "NONE":
            return None, None
        if output_mode == "RAW":
            return stripped, None
        if output_mode == "7ZIP":
            return self._parse_7zip_status(step, stripped)
        if output_mode == "ICACLS":
            return self._parse_icacls_status(step, stripped)
        return stripped, None

    def _parse_7zip_status(self, step: StepConfig, line: str) -> tuple[str | None, float | None]:
        state = self._step_live_state.setdefault(step.id, {})
        keyword_map = {
            "extracting": "Extrahiere",
            "inflating": "Entpacke",
            "creating": "Erstelle",
            "updating": "Aktualisiere",
            "testing": "Pruefe",
        }
        for keyword, prefix in keyword_map.items():
            match = re.search(rf"{keyword}\s+(.+)$", line, re.IGNORECASE)
            if match:
                path = match.group(1).strip()
                state["current_path"] = path
                state["current_name"] = Path(path).name or path
                return f"{prefix}: {state['current_name']}", None

        dash_match = re.match(r"^-\s+(.+)$", line)
        if dash_match:
            path = dash_match.group(1).strip()
            state["current_path"] = path
            state["current_name"] = Path(path).name or path
            return f"Extrahiere: {state['current_name']}", None

        percent_match = re.match(r"^(?P<percent>\d+%)\s+(?P<rest>.+)$", line)
        if percent_match:
            percent = percent_match.group("percent")
            progress_ratio = min(max(int(percent.rstrip("%")) / 100.0, 0.0), 1.0)
            current_name = state.get("current_name")
            if current_name:
                return f"Extrahiere: {current_name} ({percent})", progress_ratio
            rest = percent_match.group("rest").strip()
            if rest:
                return f"{percent} {rest}", progress_ratio

        if line.lower().startswith("everything is ok"):
            return "Archiv erfolgreich entpackt", 1.0

        return line, None

    def _parse_icacls_status(self, step: StepConfig, line: str) -> tuple[str | None, float | None]:
        state = self._step_live_state.setdefault(step.id, {})
        lowered = line.lower()

        summary_match = re.search(
            r"successfully processed\s+(?P<ok>\d+)\s+files;\s+failed processing\s+(?P<failed>\d+)\s+files",
            lowered,
        )
        if summary_match:
            ok_count = int(summary_match.group("ok"))
            failed_count = int(summary_match.group("failed"))
            state["processed_count"] = str(ok_count)
            return f"Bearbeitet: {ok_count} Dateien | Fehler: {failed_count}", None

        if lowered.startswith("processed file:"):
            path = line.split(":", 1)[1].strip()
            count = int(state.get("processed_count", "0")) + 1
            state["processed_count"] = str(count)
            state["current_path"] = path
            state["current_name"] = Path(path).name or path
            return f"Bearbeitet: {count} | Aktuell: {state['current_name']}", None

        path_match = re.match(
            r"^(?P<path>(?:[A-Za-z]:\\|\\\\).+?)(?:\s+.+:\(|$)",
            line,
        )
        if path_match and "successfully processed" not in lowered and "failed processing" not in lowered:
            path = path_match.group("path").strip()
            count = int(state.get("processed_count", "0")) + 1
            state["processed_count"] = str(count)
            state["current_path"] = path
            state["current_name"] = Path(path).name or path
            return f"Bearbeitet: {count} | Aktuell: {state['current_name']}", None

        if "access is denied" in lowered:
            current_name = state.get("current_name", "Eintrag")
            return f"Zugriff verweigert bei: {current_name}", None

        return None, None
