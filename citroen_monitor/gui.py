"""GUI for passive CAN capture, event annotation and traffic statistics."""
import csv
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QLineEdit,
    QMessageBox, QTabWidget, QHeaderView
)
from PySide6.QtSerialPort import QSerialPortInfo

from .analyzer import CanAnalyzer
from .button_research import analyze_button_trials
from .worker import CanWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CitroenC4Monitor — passive CAN monitor")
        self.resize(1180, 760)
        self.worker = None
        self.rows = []
        self.events = []
        self.analyzer = CanAnalyzer()
        self.research_phase = None
        self.baseline_rows = []
        self.experiment_rows = []
        self.experiment_trials = []
        self.active_trial_rows = None
        self.research_results = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        bar = QHBoxLayout()
        layout.addLayout(bar)
        self.port = QComboBox()
        self.refresh_ports()
        bar.addWidget(QLabel("COM:"))
        bar.addWidget(self.port)
        refresh = QPushButton("Обновить")
        refresh.clicked.connect(self.refresh_ports)
        bar.addWidget(refresh)

        self.serial = QComboBox()
        self.serial.addItems(["115200", "230400", "1000000"])
        bar.addWidget(QLabel("Serial baud:"))
        bar.addWidget(self.serial)
        self.rate = QComboBox()
        self.rate.addItems(["500", "250", "125"])
        bar.addWidget(QLabel("CAN kbit/s:"))
        bar.addWidget(self.rate)

        self.start = QPushButton("Start listen-only")
        self.start.clicked.connect(self.start_capture)
        bar.addWidget(self.start)
        self.stop = QPushButton("Stop")
        self.stop.clicked.connect(self.stop_capture)
        self.stop.setEnabled(False)
        bar.addWidget(self.stop)

        eventbar = QHBoxLayout()
        layout.addLayout(eventbar)
        self.event = QLineEdit()
        self.event.setPlaceholderText("Метка события, например STEERING_VOLUME_PLUS")
        eventbar.addWidget(self.event)
        mark = QPushButton("Отметить событие")
        mark.clicked.connect(self.mark_event)
        eventbar.addWidget(mark)
        save = QPushButton("Сохранить CSV")
        save.clicked.connect(self.save_csv)
        eventbar.addWidget(save)

        self.status = QLabel(
            "Готово. Перед подключением подтвердите физическую линию и режим "
            "listen-only по документации прошивки адаптера."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        live_page = QWidget()
        live_layout = QVBoxLayout(live_page)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Время", "CAN ID", "Тип", "DLC", "Data", "Raw"]
        )
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        live_layout.addWidget(self.table)
        self.tabs.addTab(live_page, "CAN кадры")

        stats_page = QWidget()
        stats_layout = QVBoxLayout(stats_page)
        self.stats_summary = QLabel("Кадров: 0 | Уникальных ID: 0")
        stats_layout.addWidget(self.stats_summary)
        self.stats_table = QTableWidget(0, 6)
        self.stats_table.setHorizontalHeaderLabels(
            ["CAN ID", "Кадров", "Доля", "Переходов данных", "Изменявшиеся байты", "Последние данные"]
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )
        stats_layout.addWidget(self.stats_table)
        self.tabs.addTab(stats_page, "Статистика CAN")

        research_page = QWidget()
        research_layout = QVBoxLayout(research_page)
        research_layout.addWidget(QLabel(
            "Снимите фоновый трафик без нажатий, затем отдельный захват с одним "
            "типом нажатия. Сравнение выделяет кандидатов, но не декодирует сигналы."
        ))
        research_controls = QHBoxLayout()
        research_layout.addLayout(research_controls)
        self.research_action = QLineEdit()
        self.research_action.setPlaceholderText("Действие, например STEERING_VOLUME_PLUS")
        research_controls.addWidget(self.research_action)
        baseline_button = QPushButton("Начать запись фона")
        baseline_button.clicked.connect(lambda: self.set_research_phase("baseline"))
        research_controls.addWidget(baseline_button)
        experiment_button = QPushButton("Режим опытов")
        experiment_button.clicked.connect(lambda: self.set_research_phase("experiment"))
        research_controls.addWidget(experiment_button)
        start_trial_button = QPushButton("Начать попытку")
        start_trial_button.clicked.connect(self.start_experiment_trial)
        research_controls.addWidget(start_trial_button)
        finish_trial_button = QPushButton("Завершить попытку")
        finish_trial_button.clicked.connect(self.finish_experiment_trial)
        research_controls.addWidget(finish_trial_button)
        finish_button = QPushButton("Завершить этап")
        finish_button.clicked.connect(lambda: self.set_research_phase(None))
        research_controls.addWidget(finish_button)
        compare_button = QPushButton("Сравнить")
        compare_button.clicked.connect(self.compare_research)
        research_controls.addWidget(compare_button)
        save_report_button = QPushButton("Сохранить отчёт CSV")
        save_report_button.clicked.connect(self.save_research_report)
        research_controls.addWidget(save_report_button)
        self.research_status = QLabel("Этап не выбран. Сначала запишите фоновый трафик.")
        self.research_status.setWordWrap(True)
        research_layout.addWidget(self.research_status)
        self.research_table = QTableWidget(0, 7)
        self.research_table.setHorizontalHeaderLabels([
            "CAN ID", "Кадров фон", "Попыток", "Вариантов фона",
            "Повторяющиеся payload (n/N)", "Все новые payload", "Кандидат"
        ])
        self.research_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        research_layout.addWidget(self.research_table)
        self.tabs.addTab(research_page, "Исследование кнопок")

    def set_research_phase(self, phase):
        if phase not in (None, "baseline", "experiment"):
            return
        if self.research_phase is not None and phase is not None:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Сначала завершите текущий этап."
            )
            return
        if phase == "baseline":
            self.baseline_rows = []
            self.experiment_rows = []
            self.research_results = []
            self.research_table.setRowCount(0)
        elif phase == "experiment":
            if not self.baseline_rows:
                QMessageBox.warning(
                    self, "Исследование кнопок",
                    "Сначала запишите фоновый трафик без нажатий."
                )
                return
            if not self.research_action.text().strip():
                QMessageBox.warning(
                    self, "Исследование кнопок",
                    "Введите название проверяемого действия."
                )
                return
            self.experiment_rows = []
            self.experiment_trials = []
            self.active_trial_rows = None
            self.research_results = []
            self.research_table.setRowCount(0)
        if phase is None and self.active_trial_rows is not None:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Сначала завершите текущую попытку."
            )
            return
        self.research_phase = phase
        names = {
            "baseline": "Запись фонового трафика",
            "experiment": "Режим опытов: " + self.research_action.text().strip()
                + ". Запишите не менее двух отдельных попыток.",
            None: "Этап завершён. Можно сравнить повторяемость."
        }
        self.research_status.setText(names[phase])

    def start_experiment_trial(self):
        if self.research_phase != "experiment":
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Сначала включите «Режим опытов»."
            )
            return
        if self.active_trial_rows is not None:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Текущая попытка уже записывается."
            )
            return
        self.active_trial_rows = []
        self.research_status.setText(
            f"Записывается попытка {len(self.experiment_trials) + 1}. "
            "Выполните одно и то же действие, затем завершите попытку."
        )

    def finish_experiment_trial(self):
        if self.active_trial_rows is None:
            QMessageBox.information(
                self, "Исследование кнопок",
                "Сейчас нет активной попытки."
            )
            return
        if not self.active_trial_rows:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "В этой попытке не получено CAN-кадров; она не сохранена."
            )
            self.active_trial_rows = None
            return
        self.experiment_trials.append(self.active_trial_rows)
        self.experiment_rows.extend(self.active_trial_rows)
        count = len(self.experiment_trials)
        self.active_trial_rows = None
        self.research_status.setText(
            f"Сохранено попыток: {count}. Запишите следующую попытку "
            "того же действия или завершите режим опытов."
        )

    def compare_research(self):
        if self.research_phase is not None:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Сначала нажмите «Завершить этап»."
            )
            return
        if not self.baseline_rows or len(self.experiment_trials) < 2:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Нужна фоновая запись и минимум две отдельные попытки."
            )
            return
        self.research_results = analyze_button_trials(
            self.baseline_rows, self.experiment_trials, min_repeats=2
        )
        self.research_table.setRowCount(len(self.research_results))
        for row_index, item in enumerate(self.research_results):
            values = [
                item["can_id"],
                str(item["baseline_frames"]),
                str(item["trial_count"]),
                str(item["baseline_variants"]),
                " | ".join(
                    f'{p["payload"]} ({p["repeat_count"]}/{item["trial_count"]})'
                    for p in item["candidate_payloads"] if p["candidate"]
                ) or "—",
                " | ".join(
                    p["payload"] for p in item["candidate_payloads"]
                ) or "—",
                "Да" if item["candidate"] else "Нет",
            ]
            for column, value in enumerate(values):
                self.research_table.setItem(
                    row_index, column, QTableWidgetItem(value)
                )
        candidates = sum(1 for item in self.research_results if item["candidate"])
        self.research_status.setText(
            f'Сравнение "{self.research_action.text().strip()}": '
            f'{len(self.experiment_trials)} попыток, {candidates} ID с payload, '
            "повторившимися минимум в двух попытках. Это кандидаты, не расшифровка."
        )

    def save_research_report(self):
        if not self.research_results:
            QMessageBox.information(
                self, "Отчёт", "Сначала выполните сравнение."
            )
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = f"button_research_{stamp}.csv"
        fields = [
            "action", "can_id", "baseline_frames", "trial_count",
            "experiment_frames", "baseline_variants", "candidate_payloads",
            "candidate"
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for item in self.research_results:
                row = {
                    "action": self.research_action.text().strip(),
                    "can_id": item["can_id"],
                    "baseline_frames": item["baseline_frames"],
                    "trial_count": item["trial_count"],
                    "experiment_frames": item["experiment_frames"],
                    "baseline_variants": item["baseline_variants"],
                    "candidate_payloads": " | ".join(
                        f'{p["payload"]}:{p["repeat_count"]}/{item["trial_count"]}'
                        for p in item["candidate_payloads"]
                    ),
                    "candidate": item["candidate"],
                }
                writer.writerow(row)
        QMessageBox.information(self, "Отчёт", f"Сохранено: {path}")

    def refresh_ports(self):
        current = self.port.currentText() if hasattr(self, "port") else ""
        if hasattr(self, "port"):
            self.port.clear()
            self.port.addItems([p.portName() for p in QSerialPortInfo.availablePorts()])
            index = self.port.findText(current)
            self.port.setCurrentIndex(index if index >= 0 else 0)

    def start_capture(self):
        if not self.port.currentText():
            QMessageBox.warning(self, "COM", "COM-порт не найден")
            return
        if self.worker is not None:
            return
        self.rows.clear()
        self.events.clear()
        self.analyzer.reset()
        self.table.setRowCount(0)
        self.stats_table.setRowCount(0)
        self.stats_summary.setText("Кадров: 0 | Уникальных ID: 0")

        self.worker = CanWorker(
            self.port.currentText(), int(self.serial.currentText()), int(self.rate.currentText())
        )
        self.worker.frame_received.connect(self.add_frame)
        self.worker.status.connect(self.status.setText)
        self.worker.error.connect(self.show_worker_error)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()
        self.start.setEnabled(False)
        self.stop.setEnabled(True)

    def show_worker_error(self, message):
        self.status.setText("Ошибка адаптера: " + message)
        QMessageBox.critical(self, "Ошибка адаптера", message)

    def worker_finished(self):
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        self.worker = None

    def stop_capture(self):
        worker = self.worker
        if worker is not None:
            worker.stop()
            worker.wait(2000)
            if worker.isRunning():
                self.status.setText(
                    "Поток ещё завершает работу. Подождите перед повторным запуском."
                )
                return
            self.worker = None
        self.start.setEnabled(True)
        self.stop.setEnabled(False)

    def add_frame(self, frame):
        self.rows.append(frame)
        self.analyzer.add(frame)
        if self.research_phase == "baseline":
            self.baseline_rows.append(dict(frame))
        elif self.research_phase == "experiment" and self.active_trial_rows is not None:
            self.active_trial_rows.append(dict(frame))

        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, key in enumerate(
            ["timestamp", "can_id", "frame_type", "dlc", "data", "raw"]
        ):
            self.table.setItem(row, column, QTableWidgetItem(str(frame.get(key, ""))))
        self.table.scrollToBottom()
        self.refresh_statistics()

    def refresh_statistics(self):
        summary = self.analyzer.summary()
        self.stats_summary.setText(
            f"Кадров: {summary['total_frames']} | "
            f"Уникальных CAN ID: {summary['unique_ids']} | "
            f"Типы: {summary['frame_types']}"
        )
        rows = self.analyzer.snapshot()
        self.stats_table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["can_id"],
                str(item["count"]),
                f"{item['share']:.1f}%",
                str(item["transitions"]),
                item["changed_bytes"],
                item["last_data"],
            ]
            for column, value in enumerate(values):
                self.stats_table.setItem(
                    row_index, column, QTableWidgetItem(value)
                )

    def mark_event(self):
        name = self.event.text().strip()
        if not name:
            return
        self.events.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": name,
            "frame_count": len(self.rows),
        })
        self.status.setText(f"Метка записана: {name}")
        self.event.clear()

    def save_csv(self):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        capture_path = f"capture_{stamp}.csv"
        events_path = f"events_{stamp}.csv"
        with open(capture_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["timestamp", "can_id", "frame_type", "dlc", "data", "raw"],
            )
            writer.writeheader()
            writer.writerows(self.rows)
        with open(events_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file, fieldnames=["timestamp", "event", "frame_count"]
            )
            writer.writeheader()
            writer.writerows(self.events)
        QMessageBox.information(
            self, "CSV", f"Сохранено: {capture_path} и {events_path}"
        )

    def closeEvent(self, event):
        self.stop_capture()
        event.accept()


def run():
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
