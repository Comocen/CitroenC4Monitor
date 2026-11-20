"""Serial SLCAN reader. Starts the adapter in listen-only mode."""
import threading, time
import serial
from PySide6.QtCore import QThread, Signal
from .slcan import parse_line

class CanWorker(QThread):
    frame_received = Signal(dict)
    status = Signal(str)
    error = Signal(str)
    def __init__(self, port, serial_baud=115200, can_bitrate=500):
        super().__init__(); self.port=port; self.serial_baud=serial_baud; self.can_bitrate=can_bitrate; self._stop=threading.Event(); self.ser=None
    def stop(self):
        self._stop.set()
        if self.ser:
            try: self.ser.write(b'C\r')
            except Exception: pass
    def run(self):
        try:
            self.ser=serial.Serial(self.port,self.serial_baud,timeout=0.2,write_timeout=1)
            time.sleep(0.2)
            self.ser.reset_input_buffer()
            cmd={500:b'S6\r',250:b'S5\r',125:b'S4\r'}.get(self.can_bitrate)
            if not cmd: raise ValueError('Поддерживаются только 500/250/125 kbit/s в этом прототипе')
            self.ser.write(b'C\r'); time.sleep(0.05); self.ser.write(cmd); time.sleep(0.05)
            self.ser.write(b'L\r')
            self.status.emit(f'{self.port}: listen-only, {self.can_bitrate} kbit/s')
            while not self._stop.is_set():
                raw=self.ser.readline()
                if not raw: continue
                line=raw.decode('ascii',errors='ignore').strip()
                parsed=parse_line(line)
                if parsed:
                    parsed['timestamp']=time.strftime('%Y-%m-%d %H:%M:%S')
                    self.frame_received.emit(parsed)
        except Exception as e: self.error.emit(str(e))
        finally:
            if self.ser:
                try: self.ser.write(b'C\r'); self.ser.close()
                except Exception: pass
            self.status.emit('Остановлено')
