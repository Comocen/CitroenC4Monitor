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
            self.status.emit(f'{self.port}: команда listen-only отправлена (ответ адаптера не проверен), {self.can_bitrate} kbit/s')
            while not self._stop.is_set():
                raw=self.ser.readline()
                if not raw: continue
                line=raw.decode('ascii',errors='ignore').strip()
                parsed=parse_line(line)
                if parsed:
                    parsed['timestamp']=time.strftime('%Y-%m-%d %H:%M:%S')
                    parsed['host_rx_monotonic_ns']=time.monotonic_ns()
                    self.frame_received.emit(parsed)
        except Exception as e: self.error.emit(str(e))
        finally:
            if self.ser:
                try: self.ser.write(b'C\r'); self.ser.close()
                except Exception: pass
            self.status.emit('Остановлено')


class AdapterCheckWorker(QThread):
    """Query firmware version without opening the CAN channel."""
    result = Signal(str)
    error = Signal(str)

    def __init__(self, port, serial_baud=115200):
        super().__init__()
        self.port = port
        self.serial_baud = serial_baud

    def run(self):
        ser = None
        try:
            ser = serial.Serial(self.port, self.serial_baud, timeout=0.1, write_timeout=1)
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.write(b"V\r")
            ser.flush()
            response = bytearray()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    response.extend(chunk)
                    if b"\x07" in response or b"\r" in response:
                        break
            raw = bytes(response)
            if not raw:
                self.error.emit("Нет ответа на запрос версии V. Проверьте COM-порт, serial baud и драйвер.")
            elif b"\x07" in raw:
                self.error.emit(f"Адаптер вернул NAK (0x07): {raw!r}")
            else:
                version = raw.replace(b"\r", b"").replace(b"\n", b"").decode("ascii", errors="replace").strip()
                if version:
                    self.result.emit(f"Ответ адаптера: {version} (raw: {raw!r})")
                else:
                    self.result.emit(f"Адаптер ответил ACK (CR), но строка версии пуста. Raw: {raw!r}")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
