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
