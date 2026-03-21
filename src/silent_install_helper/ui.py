from __future__ import annotations

from dataclasses import dataclass
import time

from PySide6.QtCore import QObject, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCloseEvent, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .executor import ExecutionSummary, StepExecutor
from .models import AppConfig, ExecutionStatus, ThemeMode, UiMode


PROGRESS_UNITS = 1000
STEP_HOLD_RATIO = 0.96
APP_VERSION = "v0.1.0"


def build_segment_boundaries(segments: int) -> list[float]:
    safe_segments = max(segments, 1)
    if safe_segments == 1:
        return [0.0, 1.0]

    weights = [1.0] * safe_segments
    if safe_segments >= 3:
        weights[0] = 0.72
        weights[-1] = 0.72

    total_weight = sum(weights)
    boundaries = [0.0]
    current = 0.0
    for weight in weights:
        current += weight / total_weight
        boundaries.append(current)
    boundaries[-1] = 1.0
    return boundaries


@dataclass(slots=True)
class ProgressEvent:
    completed: int
    total: int
    label: str
    state: str
    estimated_duration: float | None = None


class ExecutionWorker(QObject):
    progress = Signal(object)
    live_status = Signal(str)
    live_progress = Signal(float)
    finished = Signal(object)

    def __init__(self, executor: StepExecutor) -> None:
        super().__init__()
        self.executor = executor

    def run(self) -> None:
        summary = self.executor.run(
            progress_callback=self._emit_progress,
            live_status_callback=self._emit_live_status,
        )
        self.finished.emit(summary)

    def _emit_progress(self, completed: int, total: int, step, state: str) -> None:
        self.progress.emit(
            ProgressEvent(
                completed=completed,
                total=total,
                label=step.label,
                state=state,
                estimated_duration=step.estimated_duration,
            )
        )

    def _emit_live_status(self, step, message: str, progress_ratio: float | None) -> None:
        self.live_status.emit(message)
        if progress_ratio is not None:
            self.live_progress.emit(progress_ratio)


class SegmentedProgressBar(QWidget):
    def __init__(
        self,
        segments: int,
        theme: ThemeMode,
        progress_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.segments = max(segments, 1)
        self.theme = theme
        self.progress_color = progress_color
        self.progress_units = 0.0
        self.animation_phase = 0.0
        self.boundaries = build_segment_boundaries(self.segments)
        self.setMinimumHeight(28)
        self.setMaximumHeight(28)

    def set_progress(self, progress_units: float) -> None:
        self.progress_units = max(0.0, min(float(PROGRESS_UNITS), progress_units))
        self.update()

    def advance_animation(self, step: float = 0.03) -> None:
        self.animation_phase = (self.animation_phase + step) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(1, 2, -1, -2)
        radius = 8
        if self.theme == ThemeMode.DARK:
            background = QColor("#13181d")
            border = QColor("#394653")
            segment_line = QColor("#2e3843")
            fill_start = QColor("#4ba3c7")
            fill_end = QColor("#81c784")
            text_color = QColor("#ffffff")
        else:
            background = QColor("#f8f4ee")
            border = QColor("#e0d5c4")
            segment_line = QColor("#ddd1bf")
            fill_start = QColor("#1f7ae0")
            fill_end = QColor("#16a085")
            text_color = QColor("#17324d")

        if self.progress_color:
            fill_start = QColor(self.progress_color)
            fill_end = QColor(self.progress_color)

        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius, radius)

        filled_ratio = self.progress_units / PROGRESS_UNITS
        fill_width = rect.width() * filled_ratio
        if fill_width > 0:
            fill_rect = QRectF(rect.left(), rect.top(), fill_width, rect.height())
            gradient = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            gradient.setColorAt(0.0, fill_start)
            gradient.setColorAt(1.0, fill_end)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(fill_rect, radius, radius)

            # A soft moving highlight keeps the active filled segment visually alive.
            shimmer_width = max(fill_rect.width() * 0.18, 26.0)
            shimmer_x = fill_rect.left() + (max(fill_rect.width() - shimmer_width, 0.0) * self.animation_phase)
            shimmer_rect = QRectF(shimmer_x, fill_rect.top(), shimmer_width, fill_rect.height())
            shimmer = QLinearGradient(shimmer_rect.topLeft(), shimmer_rect.topRight())
            shimmer.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer.setColorAt(0.5, QColor(255, 255, 255, 70))
            shimmer.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(shimmer)
            painter.drawRoundedRect(shimmer_rect, radius, radius)

        painter.setPen(QPen(segment_line, 1))
        for index in range(1, self.segments):
            x = rect.left() + (rect.width() * self.boundaries[index])
            painter.drawLine(int(x), rect.top() + 2, int(x), rect.bottom() - 2)

        percent = int(round(filled_ratio * 100))
        painter.setPen(text_color)
        text_rect = rect.adjusted(0, -1, 0, -1)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{percent}%")
        painter.end()


class InstallerWindow(QMainWindow):
    def __init__(self, config: AppConfig, executor: StepExecutor) -> None:
        super().__init__()
        self.config = config
        self.executor = executor
        self.execution_started = False
        self.cancel_requested = False
        self.exit_code = 0
        self.thread: QThread | None = None
        self.worker: ExecutionWorker | None = None
        self.total_steps = max(len(config.steps), 1)
        self.displayed_progress = 0.0
        self.target_progress = 0.0
        self.current_step_index: int | None = None
        self.current_step_started_at: float | None = None
        self.current_step_estimated_duration: float | None = None
        self.current_step_live_ratio: float | None = None
        self.raw_detail_text = ""

        self.setWindowTitle(config.title)
        self.resize(720, 500)
        self.setMinimumSize(620, 420)
        if self.config.mode == UiMode.BASIC:
            self.resize(540, 210)
            self.setMinimumSize(500, 190)
            self.setMaximumHeight(240)
            self.setWindowFlag(Qt.WindowCloseButtonHint, False)
            self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(50)
        self.animation_timer.timeout.connect(self._tick_progress_animation)

        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)

        self.header_label = QLabel(f"{config.title}  {APP_VERSION}")
        self.header_label.setObjectName("header")
        self.header_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        card_layout.addWidget(self.header_label)

        self.stack = QStackedWidget()
        card_layout.addWidget(self.stack, 1)

        self.welcome_page = self._build_welcome_page()
        self.running_page = self._build_running_page()
        self.finish_page = self._build_finish_page()
        self.stack.addWidget(self.welcome_page)
        self.stack.addWidget(self.running_page)
        self.stack.addWidget(self.finish_page)

        self.button_bar = QHBoxLayout()
        self.button_bar.addStretch(1)
        card_layout.addLayout(self.button_bar)

        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self._request_cancel)
        self.next_button = QPushButton("Weiter")
        self.next_button.clicked.connect(self._on_next)
        self.start_button = QPushButton("Installation starten")
        self.start_button.clicked.connect(self._start_execution)
        self.close_button = QPushButton("Schliessen")
        self.close_button.clicked.connect(self.close)

        self.button_bar.addWidget(self.cancel_button)
        self.button_bar.addWidget(self.next_button)
        self.button_bar.addWidget(self.start_button)
        self.button_bar.addWidget(self.close_button)

        self._apply_stylesheet()

        if self.config.mode == UiMode.BASIC:
            self._configure_basic_mode()
        else:
            self._configure_full_mode()

    def run(self) -> int:
        self.show()
        return self.exit_code

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.config.mode == UiMode.BASIC and self.thread is not None and self.thread.isRunning():
            event.ignore()
            return
        if self.thread is not None and self.thread.isRunning():
            event.ignore()
            self._request_cancel()
            return
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_detail_label()

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Installationsassistent")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        text = QLabel(
            "Dieser Assistent fuehrt die konfigurierten Installationsschritte aus "
            "und zeigt waehrenddessen den Fortschritt weich und schrittweise an."
        )
        text.setWordWrap(True)
        text.setObjectName("body")
        layout.addWidget(text)

        details = QLabel(
            f"Version: {APP_VERSION}\n"
            f"Modus: {self.config.mode.value}\n"
            f"Theme: {self.config.theme.value}\n"
            f"Installer: {self.config.installer_path.name}\n"
            f"Schritte: {len(self.config.steps)}\n"
            f"Logdatei: {self.config.log_path}"
        )
        details.setObjectName("muted")
        details.setWordWrap(True)
        layout.addWidget(details)
        layout.addStretch(1)
        return page

    def _build_running_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.progress = SegmentedProgressBar(
            self.total_steps,
            self.config.theme,
            self.config.progress_color,
        )
        layout.addWidget(self.progress)

        self.message_label = QLabel("Die Installation wird vorbereitet.")
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("body")
        layout.addWidget(self.message_label)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(False)
        self.detail_label.setObjectName("muted")
        self.detail_label.setMinimumHeight(24)
        self.detail_label.setContentsMargins(0, 2, 0, 4)
        self.detail_label.hide()
        layout.addWidget(self.detail_label)

        self.step_label = QLabel(f"0 von {len(self.config.steps)} Schritten abgeschlossen")
        self.step_label.setObjectName("muted")
        layout.addWidget(self.step_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("logView")
        layout.addWidget(self.log_text, 1)
        return page

    def _build_finish_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.finish_title = QLabel("Installation abgeschlossen")
        self.finish_title.setObjectName("sectionTitle")
        layout.addWidget(self.finish_title)

        self.finish_message = QLabel("")
        self.finish_message.setWordWrap(True)
        self.finish_message.setObjectName("body")
        layout.addWidget(self.finish_message)

        layout.addStretch(1)
        return page

    def _configure_basic_mode(self) -> None:
        self.stack.setCurrentWidget(self.running_page)
        self.header_label.hide()
        self.next_button.hide()
        self.cancel_button.hide()
        self.start_button.hide()
        self.close_button.hide()
        self.log_text.hide()
        self.step_label.hide()
        self._append_log("Installation startet automatisch im BASIC-Modus.")
        QTimer.singleShot(100, self._start_execution)

    def _configure_full_mode(self) -> None:
        self.stack.setCurrentWidget(self.welcome_page)
        self.start_button.hide()
        self.close_button.hide()
        self._append_log("Bereit zum Starten.")

    def _on_next(self) -> None:
        if self.execution_started:
            return
        self._start_execution()

    def _start_execution(self) -> None:
        if self.execution_started:
            return

        self.execution_started = True
        self.stack.setCurrentWidget(self.running_page)
        self.next_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.animation_timer.start()
        self._append_log("Installation gestartet.")

        self.thread = QThread(self)
        self.worker = ExecutionWorker(self.executor)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._handle_progress)
        self.worker.live_status.connect(self._handle_live_status)
        self.worker.live_progress.connect(self._handle_live_progress)
        self.worker.finished.connect(self._finish_execution)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _request_cancel(self) -> None:
        if self.thread is None or not self.thread.isRunning():
            self.close()
            return
        if self.cancel_requested:
            return

        answer = QMessageBox.question(
            self,
            self.config.title,
            "Moechten Sie die laufende Installation wirklich abbrechen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.message_label.setText("Die Installation wird abgebrochen...")
        self._append_log("Abbruch wurde angefordert.")
        self.executor.request_cancel()

    def _handle_progress(self, event: ProgressEvent) -> None:
        self.step_label.setText(f"{event.completed} von {event.total} Schritten abgeschlossen")

        if event.state == "running":
            self.current_step_index = event.completed
            self.current_step_started_at = time.monotonic()
            self.current_step_estimated_duration = event.estimated_duration
            self.current_step_live_ratio = None
            self.target_progress = self._step_units(event.completed, event.total)
            self.message_label.setText(event.label)
            self.raw_detail_text = ""
            self.detail_label.clear()
            self.detail_label.setToolTip("")
            self.detail_label.hide()
            self._append_log(f"Starte: {event.label}")
        elif event.state == "success":
            self.current_step_index = None
            self.current_step_started_at = None
            self.current_step_estimated_duration = None
            self.current_step_live_ratio = None
            self.target_progress = self._step_units(event.completed, event.total)
            self.raw_detail_text = ""
            self.detail_label.clear()
            self.detail_label.setToolTip("")
            self.detail_label.hide()
            self._append_log(f"Fertig: {event.label}")
        elif event.state == "failed":
            self.current_step_index = None
            self.current_step_started_at = None
            self.current_step_estimated_duration = None
            self.current_step_live_ratio = None
            self.target_progress = self._step_units(event.completed, event.total)
            self.raw_detail_text = ""
            self.detail_label.clear()
            self.detail_label.setToolTip("")
            self.detail_label.hide()
            self._append_log(f"Fehler: {event.label}")
        elif event.state == "cancelled":
            self.current_step_index = None
            self.current_step_started_at = None
            self.current_step_estimated_duration = None
            self.current_step_live_ratio = None
            self.raw_detail_text = ""
            self.detail_label.clear()
            self.detail_label.setToolTip("")
            self.detail_label.hide()
            self._append_log(f"Abgebrochen: {event.label}")

    def _handle_live_status(self, message: str) -> None:
        text = message.strip()
        if not text:
            return
        self.raw_detail_text = text
        self._refresh_detail_label()
        self.detail_label.show()
        self._append_log(f"Aktiv: {text}")

    def _handle_live_progress(self, ratio: float) -> None:
        self.current_step_live_ratio = min(max(ratio, 0.0), 1.0)

    def _finish_execution(self, summary: ExecutionSummary) -> None:
        self.animation_timer.stop()
        self.execution_started = False
        self.thread = None
        self.worker = None
        self.exit_code = 0 if summary.succeeded else 1
        final_steps = summary.completed_steps if not summary.succeeded else summary.total_steps
        self.displayed_progress = self._step_units(final_steps, summary.total_steps)
        self.target_progress = self.displayed_progress
        self._apply_progress_display(self.displayed_progress)
        if self.config.mode == UiMode.BASIC:
            self.stack.setCurrentWidget(self.running_page)
        else:
            self.stack.setCurrentWidget(self.finish_page)

        self.next_button.hide()
        self.start_button.hide()
        self.cancel_button.hide()
        if self.config.mode == UiMode.BASIC:
            self.close_button.hide()
        else:
            self.close_button.show()
            self.close_button.setEnabled(True)

        if summary.status == ExecutionStatus.SUCCEEDED:
            self.finish_title.setText("Installation abgeschlossen")
            self.finish_message.setText(
                "Alle konfigurierten Schritte wurden erfolgreich ausgefuehrt."
            )
            self._append_log("Alle Schritte erfolgreich abgeschlossen.")
            if self.config.mode == UiMode.BASIC:
                self.message_label.setText("Installation abgeschlossen. Fenster schliesst sich automatisch...")
                self.raw_detail_text = ""
                self.detail_label.clear()
                self.detail_label.setToolTip("")
                self.detail_label.hide()
        elif summary.status == ExecutionStatus.CANCELLED:
            active_label = summary.active_step.label if summary.active_step else "Aktueller Schritt"
            self.finish_title.setText("Installation abgebrochen")
            self.finish_message.setText(
                "Die Installation wurde durch den Benutzer abgebrochen.\n\n"
                f"Letzter aktiver Schritt: {active_label}\n"
                f"Logdatei: {self.config.log_path}"
            )
            self._append_log(f"Installation durch Benutzer abgebrochen bei: {active_label}")
            if self.config.mode == UiMode.BASIC:
                self.message_label.setText("Installation abgebrochen.")
                self.raw_detail_text = ""
                self.detail_label.clear()
                self.detail_label.setToolTip("")
                self.detail_label.hide()
        else:
            failed_label = summary.failed_step.label if summary.failed_step else "Unbekannter Schritt"
            self.finish_title.setText("Installation fehlgeschlagen")
            self.finish_message.setText(
                "Die Installation konnte nicht abgeschlossen werden.\n\n"
                f"Fehlgeschlagener Schritt: {failed_label}\n"
                f"Logdatei: {self.config.log_path}"
            )
            self._append_log(f"Installation fehlgeschlagen bei: {failed_label}")
            if self.config.mode == UiMode.BASIC:
                self.message_label.setText(f"Installation fehlgeschlagen: {failed_label}")
                self.raw_detail_text = ""
                self.detail_label.clear()
                self.detail_label.setToolTip("")
                self.detail_label.hide()
            QMessageBox.critical(
                self,
                self.config.title,
                (
                    "Die Installation konnte nicht abgeschlossen werden.\n\n"
                    f"Fehlgeschlagener Schritt: {failed_label}\n"
                    f"Logdatei: {self.config.log_path}"
                ),
            )

        if self.config.mode == UiMode.BASIC:
            QTimer.singleShot(2000, self.close)

    def _tick_progress_animation(self) -> None:
        self.progress.advance_animation()
        if self.current_step_index is not None and self.current_step_started_at is not None:
            start = self._step_units(self.current_step_index, self.total_steps)
            end = self._step_units(self.current_step_index + 1, self.total_steps)
            hold_end = start + (end - start) * STEP_HOLD_RATIO
            if self.current_step_live_ratio is not None:
                ratio = self.current_step_live_ratio
            else:
                estimated = self.current_step_estimated_duration or 2.0
                elapsed = max(time.monotonic() - self.current_step_started_at, 0.0)
                ratio = min(elapsed / estimated, 1.0)
            self.target_progress = max(self.target_progress, start + (hold_end - start) * ratio)

        if self.displayed_progress < self.target_progress:
            gap = self.target_progress - self.displayed_progress
            self.displayed_progress = min(
                self.target_progress,
                self.displayed_progress + max(gap * 0.2, 3.0),
            )
        elif self.displayed_progress > self.target_progress:
            self.displayed_progress = self.target_progress

        self._apply_progress_display(self.displayed_progress)

    def _apply_progress_display(self, units: float) -> None:
        bounded = max(0.0, min(float(PROGRESS_UNITS), units))
        self.progress.set_progress(bounded)

    def _step_units(self, completed_steps: int, total_steps: int) -> float:
        boundaries = build_segment_boundaries(total_steps)
        safe_index = min(max(completed_steps, 0), len(boundaries) - 1)
        return boundaries[safe_index] * PROGRESS_UNITS

    def _append_log(self, message: str) -> None:
        self.log_text.append(message)

    def _refresh_detail_label(self) -> None:
        if not self.raw_detail_text:
            self.detail_label.clear()
            return

        available_width = max(self.detail_label.width() - 8, 120)
        metrics = QFontMetrics(self.detail_label.font())
        shortened = metrics.elidedText(
            self.raw_detail_text,
            Qt.TextElideMode.ElideMiddle,
            available_width,
        )
        self.detail_label.setText(shortened)
        self.detail_label.setToolTip(self.raw_detail_text)

    def _apply_stylesheet(self) -> None:
        if self.config.theme == ThemeMode.DARK:
            stylesheet = """
            QWidget {
                background: #171b20;
                color: #edf2f7;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QFrame#card {
                background: #20262d;
                border: 1px solid #303945;
                border-radius: 18px;
            }
            QLabel#header {
                color: #f4f7fb;
            }
            QLabel#sectionTitle {
                font-size: 16pt;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#body {
                color: #d4dde6;
                font-size: 10.5pt;
            }
            QLabel#muted {
                color: #98a8b8;
                padding-top: 2px;
                padding-bottom: 4px;
            }
            QTextEdit#logView {
                background: #13181d;
                color: #e7edf4;
                border: 1px solid #313b46;
                border-radius: 12px;
                padding: 8px;
            }
            QProgressBar {
                border: 1px solid #394653;
                border-radius: 8px;
                background: #13181d;
                color: #ffffff;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk {
                border-radius: 7px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4ba3c7,
                    stop: 1 #81c784
                );
            }
            QPushButton {
                min-width: 120px;
                padding: 10px 16px;
                border-radius: 10px;
                border: 1px solid #41505f;
                background: #26303a;
                color: #eef4fb;
            }
            QPushButton:hover {
                background: #32404d;
            }
            QPushButton:disabled {
                color: #7f8b97;
                background: #20262d;
            }
            """
        else:
            stylesheet = """
            QWidget {
                background: #f5f7fa;
                color: #243041;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QFrame#card {
                background: #ffffff;
                border: 1px solid #d7e0ea;
                border-radius: 18px;
            }
            QLabel#header {
                color: #1f2c3a;
            }
            QLabel#sectionTitle {
                font-size: 16pt;
                font-weight: 700;
                color: #203247;
            }
            QLabel#body {
                color: #35506f;
                font-size: 10.5pt;
            }
            QLabel#muted {
                color: #667f99;
                padding-top: 2px;
                padding-bottom: 4px;
                background: transparent;
                border: none;
            }
            QTextEdit#logView {
                background: #ffffff;
                color: #27415d;
                border: 1px solid #d7e0ea;
                border-radius: 12px;
                padding: 8px;
            }
            QPushButton {
                min-width: 120px;
                padding: 10px 16px;
                border-radius: 12px;
                border: 1px solid #d7e0ea;
                background: #ffffff;
                color: #27415d;
            }
            QPushButton:hover {
                background: #f3f7fb;
            }
            QPushButton:disabled {
                color: #9aacbf;
                background: #f8fafc;
                border: 1px solid #e3e9f0;
            }
            """
        self.setStyleSheet(stylesheet)


def run_app(config: AppConfig, executor: StepExecutor) -> int:
    if config.mode == UiMode.SILENT:
        summary = executor.run()
        return 0 if summary.succeeded else 1

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(config.title)
    window = InstallerWindow(config, executor)
    window.run()
    app.exec()
    return window.exit_code
