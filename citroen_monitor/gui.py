"""Minimal GUI for passive capture and event annotation."""
import csv, time
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QTableWidget,QTableWidgetItem,QLineEdit,QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtSerialPort import QSerialPortInfo
from .worker import CanWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('CitroenC4Monitor — passive CAN monitor'); self.resize(1050,650); self.worker=None; self.rows=[]; self.events=[]
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root)
        bar=QHBoxLayout(); layout.addLayout(bar)
        self.port=QComboBox(); self.refresh_ports(); bar.addWidget(QLabel('COM:')); bar.addWidget(self.port)
        refresh=QPushButton('Обновить'); refresh.clicked.connect(self.refresh_ports); bar.addWidget(refresh)
        self.serial=QComboBox(); self.serial.addItems(['115200','230400','1000000']); bar.addWidget(QLabel('Serial baud:')); bar.addWidget(self.serial)
        self.rate=QComboBox(); self.rate.addItems(['500','250','125']); bar.addWidget(QLabel('CAN kbit/s:')); bar.addWidget(self.rate)
        self.start=QPushButton('Start listen-only'); self.start.clicked.connect(self.start_capture); bar.addWidget(self.start)
        self.stop=QPushButton('Stop'); self.stop.clicked.connect(self.stop_capture); self.stop.setEnabled(False); bar.addWidget(self.stop)
        eventbar=QHBoxLayout(); layout.addLayout(eventbar)
        self.event=QLineEdit(); self.event.setPlaceholderText('Метка события, например STEERING_VOLUME_PLUS'); eventbar.addWidget(self.event)
        mark=QPushButton('Отметить событие'); mark.clicked.connect(self.mark_event); eventbar.addWidget(mark)
        save=QPushButton('Сохранить CSV'); save.clicked.connect(self.save_csv); eventbar.addWidget(save)
        self.status=QLabel('Готово. Работа только в режиме пассивного прослушивания.'); layout.addWidget(self.status)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(['Время','CAN ID','Тип','DLC','Data','Raw']); self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table)
    def refresh_ports(self):
        current=self.port.currentText() if hasattr(self,'port') else ''
        if hasattr(self,'port'): self.port.clear(); self.port.addItems([p.portName() for p in QSerialPortInfo.availablePorts()]); i=self.port.findText(current); self.port.setCurrentIndex(i if i>=0 else 0)
    def start_capture(self):
        if not self.port.currentText(): QMessageBox.warning(self,'COM','COM-порт не найден'); return
        self.worker=CanWorker(self.port.currentText(),int(self.serial.currentText()),int(self.rate.currentText())); self.worker.frame_received.connect(self.add_frame); self.worker.status.connect(self.status.setText); self.worker.error.connect(lambda e: QMessageBox.critical(self,'Ошибка адаптера',e)); self.worker.start(); self.start.setEnabled(False); self.stop.setEnabled(True)
    def stop_capture(self):
        if self.worker: self.worker.stop(); self.worker.wait(1500); self.worker=None
        self.start.setEnabled(True); self.stop.setEnabled(False)
    def add_frame(self,f):
        self.rows.append(f); r=self.table.rowCount(); self.table.insertRow(r)
        for c,k in enumerate(['timestamp','can_id','frame_type','dlc','data','raw']): self.table.setItem(r,c,QTableWidgetItem(str(f[k])))
        self.table.scrollToBottom()
    def mark_event(self):
        name=self.event.text().strip()
        if not name: return
        self.events.append({'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),'event':name,'frame_count':len(self.rows)}); self.status.setText(f'Метка записана: {name}'); self.event.clear()
    def save_csv(self):
        stamp=time.strftime('%Y%m%d_%H%M%S')
        with open(f'capture_{stamp}.csv','w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=['timestamp','can_id','frame_type','dlc','data','raw']); w.writeheader(); w.writerows(self.rows)
        with open(f'events_{stamp}.csv','w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=['timestamp','event','frame_count']); w.writeheader(); w.writerows(self.events)
        QMessageBox.information(self,'CSV',f'Сохранено: capture_{stamp}.csv и events_{stamp}.csv')
    def closeEvent(self,event): self.stop_capture(); event.accept()

def run():
    app=QApplication([]); win=MainWindow(); win.show(); return app.exec()
