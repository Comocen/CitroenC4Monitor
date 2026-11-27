"""GUI for passive CAN capture, event annotation and traffic statistics."""
import csv
import json
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QLineEdit,
    QMessageBox, QTabWidget, QHeaderView, QCheckBox, QFileDialog
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtCore import Qt
from PySide6.QtSerialPort import QSerialPortInfo

from .analyzer import CanAnalyzer
from .button_research import (
    analyze_button_bits, analyze_button_trials, analyze_button_transitions,
    ButtonTrialRecorder, build_button_research_report_rows,
)
from .worker import AdapterCheckWorker, CanWorker
from .signal_monitor import SignalDefinition, decode_signal_value, validate_definition



class CanActivityChart(QWidget):
    """Compact bar chart of the most active CAN identifiers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setMinimumHeight(190)

    def set_items(self, items):
        self.items = list(items[:12])
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QColor, QPainter
        from PySide6.QtCore import Qt

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        if not self.items:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Пока нет принятых CAN-кадров")
            return
        left, right = 76, 58
        top, row_h = 12, 14
        max_count = max(item["count"] for item in self.items) or 1
        available = max(20, self.width() - left - right)
        painter.setFont(self.font())
        for index, item in enumerate(self.items):
            y = top + index * row_h
            if y + row_h > self.height():
                break
            painter.setPen(self.palette().text().color())
            painter.drawText(4, y + 11, str(item["can_id"]))
            width = int(available * item["count"] / max_count)
            painter.fillRect(left, y + 1, available, 9, QColor("#e7eaf0"))
            painter.fillRect(left, y + 1, width, 9, QColor("#3979bd"))
            painter.drawText(left + available + 6, y + 11, str(item["count"]))
        painter.end()


class ButtonCandidateChart(QWidget):
    """Visual comparison of released/pressed bit candidates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setMinimumHeight(150)

    def set_items(self, items):
        self.items = list(items[:10])
        self.setMinimumHeight(max(150, 28 * len(self.items) + 36))
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QColor, QPainter
        from PySide6.QtCore import Qt

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        if not self.items:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "После сравнения здесь появятся кандидаты сигналов")
            return
        painter.drawText(4, 16, "CAN ID / бит")
        painter.drawText(190, 16, "Отпущено → нажато")
        painter.drawText(max(330, self.width() - 150), 16, "Повторы")
        for i, item in enumerate(self.items):
            y = 28 + i * 28
            if y + 22 > self.height():
                break
            label = f'{item["can_id"]} / bit {item["bit_index"]}'
            painter.drawText(4, y + 15, label)
            color = QColor("#d9ead3") if item["candidate"] else QColor("#fce5cd")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(190, y, 112, 20, 4, 4)
            painter.setPen(QColor("#202124"))
            painter.drawText(197, y + 15,
                             f'{item["released_value"]} → {item["pressed_value"]}')
            painter.drawText(max(330, self.width() - 150), y + 15,
                             f'{item["changed_trials"]}/{item["eligible_trials"]}')
        painter.end()


class SignalHistoryChart(QWidget):
    """Dependency-free plot of recent decoded signal values."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = []
        self.setMinimumHeight(190)

    def set_values(self, values):
        self.values = list(values[-120:])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        if len(self.values) < 2:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "График появится после получения нескольких значений")
            painter.end()
            return
        left, right, top, bottom = 48, 12, 12, 24
        plot_w = max(1, self.width() - left - right)
        plot_h = max(1, self.height() - top - bottom)
        low, high = min(self.values), max(self.values)
        if high == low:
            padding = max(abs(high) * 0.05, 1.0)
            low, high = low - padding, high + padding
        painter.setPen(self.palette().text().color())
        painter.drawText(4, top + 8, f"{high:.3g}")
        painter.drawText(4, top + plot_h, f"{low:.3g}")
        painter.setPen(QColor("#3979bd"))
        points = []
        for index, value in enumerate(self.values):
            x = left + int(plot_w * index / max(1, len(self.values) - 1))
            y = top + int(plot_h * (high - value) / (high - low))
            points.append((x, y))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first[0], first[1], second[0], second[1])
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CitroenC4Monitor — passive CAN monitor")
        self.resize(1180, 760)
        self.worker = None
        self.adapter_check_worker = None
        self.rows = []
        self.events = []
        self.analyzer = CanAnalyzer()
        self.research_phase = None
        self.baseline_rows = []
        self.experiment_rows = []
        self.experiment_trials = []
        self.active_trial_rows = None
        self.active_trial_state = None
        self.trial_recorder = ButtonTrialRecorder(min_frames_per_window=3)
        self.transition_trials = []
        self.transition_results = []
        self.research_results = []
        self.bit_results = []

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

        self.check_adapter = QPushButton("Проверить адаптер")
        self.check_adapter.clicked.connect(self.check_adapter_version)
        bar.addWidget(self.check_adapter)
        self.start = QPushButton("Start (запрос listen-only)")
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
        self.stats_table = QTableWidget(0, 9)
        self.stats_table.setHorizontalHeaderLabels(
            ["CAN ID", "Кадров", "Доля", "Переходов данных", "Изменявшиеся байты",
             "Последние данные", "Средний интервал, мс", "Мин., мс", "Макс., мс"]
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )
        stats_layout.addWidget(QLabel(
            "Активность: 12 наиболее частых CAN ID. Интервалы рассчитаны по времени приёма на компьютере."
        ))
        self.can_activity_chart = CanActivityChart()
        stats_layout.addWidget(self.can_activity_chart)
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
        before_button = QPushButton("Окно: отпущено до")
        before_button.clicked.connect(lambda: self.set_trial_state("released_before"))
        research_controls.addWidget(before_button)
        pressed_button = QPushButton("Окно: нажато")
        pressed_button.clicked.connect(lambda: self.set_trial_state("pressed"))
        research_controls.addWidget(pressed_button)
        after_button = QPushButton("Окно: отпущено после")
        after_button.clicked.connect(lambda: self.set_trial_state("released_after"))
        research_controls.addWidget(after_button)
        finish_trial_button = QPushButton("Завершить попытку")
        finish_trial_button.clicked.connect(self.finish_experiment_trial)
        research_controls.addWidget(finish_trial_button)
        cancel_trial_button = QPushButton("Отменить попытку")
        cancel_trial_button.clicked.connect(self.cancel_experiment_trial)
        research_controls.addWidget(cancel_trial_button)
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
        research_layout.addWidget(QLabel(
            "Визуальная карта переходных битов: зелёный — повторяемый кандидат, "
            "оранжевый — наблюдаемое изменение без достаточной повторяемости."
        ))
        self.button_candidate_chart = ButtonCandidateChart()
        research_layout.addWidget(self.button_candidate_chart)
        self.button_candidate_summary = QLabel("Кандидаты не рассчитаны.")
        research_layout.addWidget(self.button_candidate_summary)
        self.research_table = QTableWidget(0, 7)
        self.research_table.setHorizontalHeaderLabels([
            "CAN ID", "Кадров фон", "Попыток", "Вариантов фона",
            "Повторяющиеся payload (n/N)", "Все новые payload", "Кандидат"
        ])
        self.research_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        research_layout.addWidget(self.research_table)
        research_layout.addWidget(QLabel(
            "Битовый анализ: значение каждого бита в большинстве кадров каждой попытки "
            "сравнивается с фоновым большинством. Нумерация: бит 0 — младший бит байта 0."
        ))
        self.bit_table = QTableWidget(0, 8)
        self.bit_table.setHorizontalHeaderLabels([
            "CAN ID", "Бит", "Байт", "Бит в байте",
            "Фон", "Кандидат", "Попыток со сменой", "Кандидат"
        ])
        research_layout.addWidget(self.bit_table)
        research_layout.addWidget(QLabel("Переходный анализ: оба окна отпускания должны совпадать, а окно нажатия — отличаться."))
        self.transition_table = QTableWidget(0, 7)
        self.transition_table.setHorizontalHeaderLabels(["CAN ID", "Бит", "Отпущено", "Нажато", "Повторов", "Подходящих попыток", "Кандидат"])
        research_layout.addWidget(self.transition_table)
        self.tabs.addTab(research_page, "Исследование кнопок")

        self.signal_definitions = []
        self.signal_page = self.build_signal_page()
        self.tabs.addTab(self.signal_page, "Сигналы и приборы")
        self.configure_tooltips()


    def configure_tooltips(self):
        """Explain the purpose and safe use of the main controls."""
        button_help = {
            "Обновить": "Повторно обнаружить последовательные порты. Если адаптер подключили после запуска, нажмите эту кнопку.",
            "Проверить адаптер": "Безопасная проверка: отправляет только V\\r для чтения версии прошивки. CAN-канал не открывается, кадры не передаются.",
            "Start (запрос listen-only)": "Начать чтение CAN через SLCAN. Отправляются команды управления каналом; приложение пока не подтверждает фактический listen-only. Не нажимайте для проверки USB-подключения.",
            "Stop": "Остановить захват и закрыть CAN-канал.",
            "Отметить событие": "Добавить временную метку к текущему захвату, например момент нажатия кнопки. Метка попадёт в отдельный CSV.",
            "Сохранить CSV": "Сохранить принятые CAN-кадры и метки событий в два CSV-файла.",
            "Начать запись фона": "Записать базовый CAN-трафик без нажатий. Перед этим должен идти захват CAN.",
            "Режим опытов": "Начать серию одинаковых действий. Введите название кнопки и выполните несколько отдельных попыток.",
            "Начать попытку": "Создать попытку для последовательности «отпущено до → нажато → отпущено после».",
            "Окно: отпущено до": "Записать CAN-состояние до нажатия. Кнопку не трогайте.",
            "Окно: нажато": "Записать CAN-состояние во время нажатия или удержания кнопки.",
            "Окно: отпущено после": "Записать CAN-состояние после отпускания кнопки.",
            "Завершить попытку": "Сохранить попытку. В каждом из трёх окон нужно не менее трёх кадров.",
            "Отменить попытку": "Отбросить только текущую незавершённую попытку. Предыдущие сохраняются.",
            "Завершить этап": "Завершить запись фона или серию опытов. После этого доступно сравнение.",
            "Сравнить": "Сравнить фон с отдельными попытками и найти повторяющиеся кандидаты. Это не расшифровка CAN.",
            "Сохранить отчёт CSV": "Экспортировать результаты анализа кнопок в CSV."
        }
        for button in self.findChildren(QPushButton):
            help_text = button_help.get(button.text())
            if help_text:
                button.setToolTip(help_text)

        self.port.setToolTip("COM-порт адаптера USB2CANFD, который появился в Windows после подключения.")
        self.serial.setToolTip("Скорость USB/Serial-соединения с адаптером. Это НЕ скорость CAN-шины. Сверьте значение с документацией прошивки.")
        self.rate.setToolTip("Скорость физической CAN-шины в kbit/s. Её нужно подтвердить для выбранной шины; не подбирайте наугад.")
        self.event.setToolTip("Короткое имя действия или состояния для временной отметки в журнале.")
        self.research_action.setToolTip("Название одного действия для серии опытов. Не смешивайте разные кнопки в одной серии.")
        self.status.setToolTip("Текущий статус COM-порта, проверки адаптера или захвата. Сообщение об отправке listen-only-команды не доказывает фактический режим.")
        self.research_status.setToolTip("Текущий этап исследования и состояние попыток.")

        self.table.setToolTip("Принятые кадры: CAN ID — идентификатор сообщения; DLC — длина данных; Data — байты; Raw — исходная строка SLCAN.")
        self.stats_table.setToolTip("Сводка по CAN ID текущего сеанса. Интервалы измеряются по времени получения на компьютере, не аппаратными часами CAN.")
        self.can_activity_chart.setToolTip("Количество кадров для наиболее активных CAN ID.")
        self.research_table.setToolTip("Payload-кандидаты — данные, повторившиеся в нескольких опытах относительно фона. Кандидат ещё не означает расшифрованный сигнал.")
        self.bit_table.setToolTip("Битовые кандидаты — позиции битов, у которых значение отличается от фонового в нескольких опытах.")
        self.transition_table.setToolTip("Переходные кандидаты: значение бита одинаково в обоих окнах отпускания и отличается в окне нажатия.")
        self.button_candidate_chart.setToolTip("Повторяемость переходов битов между состояниями «отпущено» и «нажато».")

        self.tabs.setTabToolTip(0, "Живой список кадров, которые адаптер передаёт программе.")
        self.tabs.setTabToolTip(1, "Частота CAN ID, изменения данных и интервалы между кадрами.")
        self.tabs.setTabToolTip(2, "Сравнение трафика до, во время и после нажатия кнопок.")
        self.tabs.setTabToolTip(3, "Настройка декодирования найденных CAN-сигналов и живые индикаторы/графики. Значения требуют проверенной карты сигналов.")
        self.signal_table.setToolTip("Список пользовательских декодеров. Значение обновляется только по кадрам с совпадающим CAN ID.")
        self.signal_chart.setToolTip("История последних 120 декодированных значений выбранного сигнала.")
        self.signal_live_value.setToolTip("Текущая интерпретация выбранного сигнала; отсутствие данных не означает нулевое значение.")

        header_help = {
            self.table: ["Время получения кадра на ПК", "Идентификатор CAN-сообщения", "Тип классического CAN-кадра", "Длина данных в байтах", "Байты полезных данных", "Исходная строка от адаптера"],
            self.stats_table: ["Идентификатор CAN", "Количество кадров", "Доля от общего числа", "Изменения payload между соседними кадрами этого ID", "Байты, которые менялись", "Последний payload", "Средний интервал между кадрами, мс", "Минимальный интервал, мс", "Максимальный интервал, мс"],
            self.research_table: ["CAN ID", "Кадры фоновой записи", "Число опытов", "Варианты фоновых данных", "Payload, повторившиеся в опытах", "Все новые payload-кандидаты", "Итоговый признак кандидата"],
            self.bit_table: ["CAN ID", "Номер бита от начала payload", "Индекс байта с нуля", "Номер бита внутри байта (0 — младший)", "Фоновое значение", "Значение-кандидат", "Попытки со сменой / подходящие попытки", "Итоговый признак кандидата"],
            self.transition_table: ["CAN ID", "Номер бита от начала payload", "Значение при отпускании", "Значение при нажатии", "Число повторившихся попыток", "Число подходящих попыток", "Итоговый признак кандидата"]
        }
        for table, descriptions in header_help.items():
            for column, description in enumerate(descriptions):
                item = table.horizontalHeaderItem(column)
                if item is not None:
                    item.setToolTip(description)

    def build_signal_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "Настройте декодирование найденного CAN-сигнала. Данные только читаются; "
            "программа не отправляет CAN-команды. Intel: bit 0 — младший бит byte 0."
        ))
        form = QHBoxLayout()
        layout.addLayout(form)
        self.signal_name = QLineEdit()
        self.signal_name.setPlaceholderText("Ближний свет / RPM")
        self.signal_can_id = QLineEdit()
        self.signal_can_id.setPlaceholderText("CAN ID hex")
        self.signal_start_bit = QLineEdit("0")
        self.signal_bit_length = QLineEdit("1")
        self.signal_factor = QLineEdit("1")
        self.signal_offset = QLineEdit("0")
        self.signal_unit = QLineEdit()
        self.signal_unit.setPlaceholderText("rpm, km/h, °C")
        for widget, label in [
            (self.signal_name, "Название"), (self.signal_can_id, "CAN ID"),
            (self.signal_start_bit, "Начальный бит"), (self.signal_bit_length, "Длина, бит"),
            (self.signal_factor, "Множитель"), (self.signal_offset, "Смещение"),
            (self.signal_unit, "Единица")
        ]:
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            col.addWidget(widget)
            form.addLayout(col)
        self.signal_signed = QCheckBox("Знаковый")
        form.addWidget(self.signal_signed)
        add_button = QPushButton("Добавить сигнал")
        add_button.clicked.connect(self.add_signal_definition)
        form.addWidget(add_button)

        actions = QHBoxLayout()
        layout.addLayout(actions)
        remove_button = QPushButton("Удалить выбранный")
        remove_button.clicked.connect(self.remove_signal_definition)
        actions.addWidget(remove_button)
        save_button = QPushButton("Сохранить профиль…")
        save_button.clicked.connect(self.save_signal_profile)
        actions.addWidget(save_button)
        load_button = QPushButton("Загрузить профиль…")
        load_button.clicked.connect(self.load_signal_profile)
        actions.addWidget(load_button)
        actions.addStretch(1)

        self.signal_table = QTableWidget(0, 7)
        self.signal_table.setHorizontalHeaderLabels([
            "Сигнал", "CAN ID", "Биты", "Формула", "Текущее значение", "Ед.", "Кадров"
        ])
        self.signal_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.signal_table.itemSelectionChanged.connect(self.refresh_selected_signal)
        layout.addWidget(self.signal_table)
        self.signal_live_value = QLabel("Выберите сигнал. Для обновления нужен активный захват CAN.")
        self.signal_live_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_live_value.setMinimumHeight(54)
        layout.addWidget(self.signal_live_value)
        self.signal_chart = SignalHistoryChart()
        layout.addWidget(self.signal_chart)
        self.signal_status = QLabel(
            "Нет сигналов. Для света обычно проверяют отдельный бит; для оборотов, скорости "
            "и температуры нужны подтверждённые диапазон битов, множитель и смещение."
        )
        self.signal_status.setWordWrap(True)
        layout.addWidget(self.signal_status)
        return page

    def add_signal_definition(self):
        try:
            definition = validate_definition(SignalDefinition(
                name=self.signal_name.text(), can_id=self.signal_can_id.text(),
                start_bit=int(self.signal_start_bit.text()),
                bit_length=int(self.signal_bit_length.text()),
                factor=float(self.signal_factor.text().replace(",", ".")),
                offset=float(self.signal_offset.text().replace(",", ".")),
                unit=self.signal_unit.text(), signed=self.signal_signed.isChecked(),
            ))
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Настройка сигнала", str(exc))
            return
        if any(x["definition"].name.casefold() == definition.name.casefold()
               for x in self.signal_definitions):
            QMessageBox.warning(self, "Настройка сигнала", "Название уже используется.")
            return
        self.signal_definitions.append({
            "definition": definition, "latest": None, "count": 0, "history": []
        })
        self.refresh_signal_table()
        self.signal_table.selectRow(len(self.signal_definitions) - 1)
        self.signal_status.setText("Сигнал добавлен. Ожидание подходящих кадров с указанным CAN ID.")

    def remove_signal_definition(self):
        row = self.signal_table.currentRow()
        if 0 <= row < len(self.signal_definitions):
            del self.signal_definitions[row]
            self.refresh_signal_table()
            self.signal_live_value.setText("Сигнал удалён.")
            self.signal_chart.set_values([])

    def refresh_signal_table(self):
        self.signal_table.setRowCount(len(self.signal_definitions))
        for row, item in enumerate(self.signal_definitions):
            d = item["definition"]
            value = item["latest"]
            if value is None:
                shown = "нет данных"
            elif d.bit_length == 1:
                shown = "ВКЛ" if value != 0 else "ВЫКЛ"
            else:
                shown = f"{value:.5g}"
            values = [d.name, "0x" + d.normalized_id(),
                      f"{d.start_bit}+{d.bit_length}",
                      f"x{d.factor:g} {d.offset:+g}", shown, d.unit, str(item["count"])]
            for column, text in enumerate(values):
                self.signal_table.setItem(row, column, QTableWidgetItem(text))

    def update_signal_monitor(self, frame):
        frame_id = str(frame.get("can_id", "")).upper().lstrip("0") or "0"
        updated = False
        for item in self.signal_definitions:
            d = item["definition"]
            if frame_id != d.normalized_id():
                continue
            try:
                value = decode_signal_value(
                    frame.get("data", ""), d.start_bit, d.bit_length,
                    d.factor, d.offset, d.signed
                )
            except ValueError:
                continue
            item["latest"] = value
            item["count"] += 1
            updated = True
            item["history"].append(value)
            if len(item["history"]) > 120:
                del item["history"][:-120]
        if updated:
            self.refresh_signal_table()
            self.refresh_selected_signal()

    def refresh_selected_signal(self):
        row = self.signal_table.currentRow()
        if not 0 <= row < len(self.signal_definitions):
            return
        item = self.signal_definitions[row]
        d, value = item["definition"], item["latest"]
        if value is None:
            display = "НЕТ ДАННЫХ"
            detail = "Нет подходящего кадра. Проверьте CAN ID, захват и длину payload."
        elif d.bit_length == 1:
            display = "ВКЛЮЧЕНО" if value != 0 else "ВЫКЛЮЧЕНО"
            detail = f"Декодированное значение: {value:g} {d.unit}".strip()
        else:
            display = f"{value:.5g} {d.unit}".strip()
            detail = f"Подходящих кадров: {item['count']}"
        self.signal_live_value.setText(f"{d.name}: {display}\n{detail}")
        self.signal_chart.set_values(item["history"])

    def save_signal_profile(self):
        if not self.signal_definitions:
            QMessageBox.information(self, "Профиль", "Нет сигналов для сохранения.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить профиль", "can_signals.json", "JSON (*.json)"
        )
        if not path:
            return
        payload = []
        for item in self.signal_definitions:
            d = item["definition"]
            payload.append({
                "name": d.name, "can_id": d.can_id, "start_bit": d.start_bit,
                "bit_length": d.bit_length, "factor": d.factor, "offset": d.offset,
                "unit": d.unit, "signed": d.signed,
            })
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Профиль", f"Ошибка сохранения: {exc}")
            return
        self.signal_status.setText(f"Профиль сохранён: {path}")

    def load_signal_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить профиль", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            if not isinstance(payload, list):
                raise ValueError("Ожидался список сигналов.")
            definitions = []
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError("Некорректная запись сигнала.")
                definitions.append(validate_definition(SignalDefinition(
                    name=item["name"], can_id=item["can_id"],
                    start_bit=int(item["start_bit"]), bit_length=int(item["bit_length"]),
                    factor=float(item.get("factor", 1)), offset=float(item.get("offset", 0)),
                    unit=item.get("unit", ""), signed=bool(item.get("signed", False)),
                )))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "Профиль", f"Ошибка загрузки: {exc}")
            return
        self.signal_definitions = [
            {"definition": d, "latest": None, "count": 0, "history": []}
            for d in definitions
        ]
        self.refresh_signal_table()
        if self.signal_definitions:
            self.signal_table.selectRow(0)
        self.signal_status.setText(
            f"Загружено сигналов: {len(self.signal_definitions)}. Проверьте корректность формул."
        )

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
            self.experiment_trials = []
            self.active_trial_rows = None
            self.active_trial_state = None
            self.trial_recorder.cancel()
            self.transition_trials = []
            self.transition_results = []
            self.research_results = []
            self.bit_results = []
            self.research_table.setRowCount(0)
            self.bit_table.setRowCount(0)
            self.transition_trials = []
            self.transition_results = []
            self.transition_table.setRowCount(0)
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
            self.active_trial_state = None
            self.trial_recorder.cancel()
            self.transition_trials = []
            self.transition_results = []
            self.research_results = []
            self.bit_results = []
            self.research_table.setRowCount(0)
            self.bit_table.setRowCount(0)
            self.transition_table.setRowCount(0)
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
        try:
            self.trial_recorder.begin()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Исследование кнопок", str(exc))
            return
        self.active_trial_rows = self.trial_recorder.active
        self.active_trial_state = None
        self.research_status.setText(
            f"Попытка {len(self.transition_trials) + 1}: последовательно запишите окна отпускания, нажатия и отпускания."
        )

    def set_trial_state(self, state):
        if self.active_trial_rows is None:
            QMessageBox.warning(self, "Исследование кнопок", "Сначала начните попытку.")
            return
        try:
            self.trial_recorder.start_window(state)
        except (RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "Исследование кнопок", str(exc))
            return
        self.active_trial_state = state
        messages = {
            "released_before": "Запись окна ДО нажатия: кнопку не трогайте.",
            "pressed": "Запись окна НАЖАТИЯ: нажмите и удерживайте кнопку.",
            "released_after": "Запись окна ПОСЛЕ отпускания: отпустите кнопку."
        }
        self.research_status.setText(messages[state])

    def finish_experiment_trial(self):
        if self.active_trial_rows is None:
            QMessageBox.information(
                self, "Исследование кнопок",
                "Сейчас нет активной попытки."
            )
            return
        try:
            trial = self.trial_recorder.finish()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Исследование кнопок", str(exc))
            return
        self.transition_trials.append(trial)
        if trial["pressed"]:
            self.experiment_trials.append(trial["pressed"])
        self.experiment_rows.extend(trial["released_before"] + trial["pressed"] + trial["released_after"])
        count = len(self.transition_trials)
        self.active_trial_rows = None
        self.active_trial_state = None
        self.research_status.setText(
            f"Сохранено попыток: {count}. Запишите следующую попытку "
            "того же действия или завершите режим опытов."
        )


    def cancel_experiment_trial(self):
        if not self.trial_recorder.cancel():
            QMessageBox.information(self, "Исследование кнопок", "Нет активной попытки.")
            return
        self.active_trial_rows = None
        self.active_trial_state = None
        self.research_status.setText("Текущая попытка отменена; сохранённые попытки не изменены.")

    def compare_research(self):
        if self.research_phase is not None:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Сначала нажмите «Завершить этап»."
            )
            return
        if not self.baseline_rows or len(self.transition_trials) < 2:
            QMessageBox.warning(
                self, "Исследование кнопок",
                "Нужна фоновая запись и минимум две отдельные попытки."
            )
            return
        self.research_results = analyze_button_trials(
            self.baseline_rows, self.experiment_trials, min_repeats=2
        )
        self.bit_results = analyze_button_bits(
            self.baseline_rows, self.experiment_trials, min_repeats=2
        )
        self.transition_results = analyze_button_transitions(self.transition_trials, min_repeats=2)
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
        self.bit_table.setRowCount(len(self.bit_results))
        for row_index, item in enumerate(self.bit_results):
            values = [
                item["can_id"], str(item["bit_index"]), str(item["byte_index"]),
                str(item["bit_in_byte"]), str(item["baseline_value"]),
                str(item["candidate_value"]),
                f'{item["changed_trials"]}/{item["eligible_trials"]}',
                "Да" if item["candidate"] else "Нет",
            ]
            for column, value in enumerate(values):
                self.bit_table.setItem(row_index, column, QTableWidgetItem(value))
        self.transition_table.setRowCount(len(self.transition_results))
        for row_index, item in enumerate(self.transition_results):
            values = [item["can_id"], str(item["bit_index"]), str(item["released_value"]), str(item["pressed_value"]), str(item["changed_trials"]), str(item["eligible_trials"]), "Да" if item["candidate"] else "Нет"]
            for column, value in enumerate(values):
                self.transition_table.setItem(row_index, column, QTableWidgetItem(value))
        candidates = sum(1 for item in self.research_results if item["candidate"])
        bit_candidates = sum(1 for item in self.bit_results if item["candidate"])
        transition_candidates = sum(1 for item in self.transition_results if item["candidate"])
        self.button_candidate_chart.set_items(self.transition_results)
        self.button_candidate_summary.setText(
            f"Payload-кандидатов: {candidates} | битовых: {bit_candidates} | "
            f"переходных: {transition_candidates}. Показано до 10 переходных позиций."
        )
        self.research_status.setText(
            f'Сравнение "{self.research_action.text().strip()}": '
            f'{len(self.experiment_trials)} попыток, {candidates} ID с payload, '
            "повторившимися минимум в двух попытках; "
            f"{bit_candidates} обычных битовых и {transition_candidates} переходных кандидатов. Это не расшифровка."
        )

    def save_research_report(self):
        if not (self.research_results or self.bit_results or self.transition_results):
            QMessageBox.information(
                self, "Отчёт", "Сначала выполните сравнение."
            )
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = f"button_research_{stamp}.csv"
        fields = [
            "action", "can_id", "baseline_frames", "trial_count",
            "experiment_frames", "baseline_variants", "candidate_payloads",
            "candidate", "candidate_bits", "press_release_bits"
        ]
        report_rows = build_button_research_report_rows(
            self.research_action.text().strip(),
            self.research_results,
            self.bit_results,
            self.transition_results,
            len(self.transition_trials),
        )
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(report_rows)
        QMessageBox.information(self, "Отчёт", f"Сохранено: {path}")

    def refresh_ports(self):
        current = self.port.currentText() if hasattr(self, "port") else ""
        if hasattr(self, "port"):
            self.port.clear()
            self.port.addItems([p.portName() for p in QSerialPortInfo.availablePorts()])
            index = self.port.findText(current)
            self.port.setCurrentIndex(index if index >= 0 else 0)

    def check_adapter_version(self):
        if self.worker is not None or self.adapter_check_worker is not None:
            return
        if not self.port.currentText():
            QMessageBox.warning(self, "COM", "COM-порт не найден")
            return
        self.adapter_check_worker = AdapterCheckWorker(self.port.currentText(), int(self.serial.currentText()))
        self.adapter_check_worker.result.connect(self.adapter_check_succeeded)
        self.adapter_check_worker.error.connect(self.adapter_check_failed)
        self.adapter_check_worker.finished.connect(self.adapter_check_finished)
        self.check_adapter.setEnabled(False)
        self.start.setEnabled(False)
        self.status.setText(f"Проверка {self.port.currentText()}: отправляется только запрос версии V...")
        self.adapter_check_worker.start()

    def adapter_check_succeeded(self, message):
        self.status.setText("Проверка завершена. " + message)

    def adapter_check_failed(self, message):
        self.status.setText("Проверка не пройдена: " + message)
        QMessageBox.warning(self, "Проверка адаптера", message)

    def adapter_check_finished(self):
        self.adapter_check_worker = None
        self.check_adapter.setEnabled(True)
        self.start.setEnabled(self.worker is None)

    def start_capture(self):
        if self.adapter_check_worker is not None:
            return
        if not self.port.currentText():
            QMessageBox.warning(self, "COM", "COM-порт не найден")
            return
        if self.worker is not None:
            return
        self.rows.clear()
        self.events.clear()
        self.research_phase = None
        self.baseline_rows = []
        self.experiment_rows = []
        self.experiment_trials = []
        self.active_trial_rows = None
        self.active_trial_state = None
        self.trial_recorder.cancel()
        self.transition_trials = []
        self.transition_results = []
        self.research_results = []
        self.bit_results = []
        self.research_status.setText(
            "Новый сеанс захвата: исследование кнопок сброшено."
        )
        self.research_table.setRowCount(0)
        self.bit_table.setRowCount(0)
        self.transition_table.setRowCount(0)
        self.button_candidate_chart.set_items([])
        self.button_candidate_summary.setText("Кандидаты не рассчитаны.")
        self.can_activity_chart.set_items([])
        self.analyzer.reset()
        for signal in self.signal_definitions:
            signal["latest"] = None
            signal["count"] = 0
            signal["history"] = []
        self.refresh_signal_table()
        self.refresh_selected_signal()
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
        self.update_signal_monitor(frame)
        if self.research_phase == "baseline":
            self.baseline_rows.append(dict(frame))
        elif self.research_phase == "experiment" and self.active_trial_rows is not None:
            self.trial_recorder.add_frame(frame)

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
        self.can_activity_chart.set_items(rows)
        self.stats_table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["can_id"],
                str(item["count"]),
                f"{item['share']:.1f}%",
                str(item["transitions"]),
                item["changed_bytes"],
                item["last_data"],
                f'{item["mean_interval_ms"]:.3f}' if item["mean_interval_ms"] is not None else "—",
                f'{item["min_interval_ms"]:.3f}' if item["min_interval_ms"] is not None else "—",
                f'{item["max_interval_ms"]:.3f}' if item["max_interval_ms"] is not None else "—",
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
                fieldnames=["timestamp", "host_rx_monotonic_ns", "can_id", "frame_type", "dlc", "data", "raw"],
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
