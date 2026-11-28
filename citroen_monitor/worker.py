"""Serial SLCAN reader for WeAct USB2CANFD V1.

The adapter is configured explicitly for silent classic-CAN reception and
ASCII SLCAN output. The firmware-version probe is deliberately separate.
"""
import threading
import time

import serial
from PySide6.QtCore import QThread, Signal

from .slcan import parse_line


class CanWorker(QThread):
    frame_received = Signal(dict)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, port, serial_baud=115200, can_bitrate=500):
        super().__init__()
        self.port = port
        self.serial_baud = serial_baud
        self.can_bitrate = can_bitrate
        self._stop = threading.Event()
        self.ser = None

    def _command(self, command, timeout=1.0):
        """Send one SLCAN command and require CR ACK (reject 0x07 NAK)."""
        self.ser.write(command.encode("ascii") + b"\\r")
        self.ser.flush()
        deadline = time.monotonic() + timeout
        response = bytearray()
        while time.monotonic() < deadline:
            chunk = self.ser.read(1)
            if not chunk:
                continue
            response.extend(chunk)
            if b"\\x07" in response:
                raise RuntimeError(
                    f"Адаптер отклонил команду {command!r} (NAK 0x07)"
                )
            if b"\\r" in response:
                return
        raise RuntimeError(
            f"Нет ACK (CR) на команду {command!r}; ответ: {bytes(response)!r}"
        )

    def stop(self):
        self._stop.set()
        # The reader thread owns the serial port. It closes the channel in
        # finally, avoiding concurrent reads/writes from the GUI thread.

    def run(self):
        try:
            self.ser = serial.Serial(
                self.port,
                self.serial_baud,
                timeout=0.05,
                write_timeout=1,
                bytesize=8,
                parity="N",
                stopbits=1,
                rtscts=False,
                dsrdtr=False,
            )
            time.sleep(0.2)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            bitrate_commands = {
                500: "S6",
                250: "S5",
                125: "S4",
            }
            bitrate_command = bitrate_commands.get(self.can_bitrate)
            if bitrate_command is None:
                raise ValueError(
                    "Поддерживаются только 500/250/125 kbit/s в этом прототипе"
                )

            # Match the known-working car-launcher sequence:
            # close -> silent mode -> nominal bitrate -> ASCII -> open.
            # H0 is essential because this application's parser consumes
            # text SLCAN frames, not the binary H1 enhanced stream.
            self._command("C")
            self._command("M1")
            self._command(bitrate_command)
            self._command("H0")
            self._command("O")

            self.status.emit(
                f"{self.port}: CAN-канал открыт, silent/listen-only, "
                f"ASCII SLCAN (H0), {self.can_bitrate} kbit/s"
            )

            while not self._stop.is_set():
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="ignore").strip()
                parsed = parse_line(line)
                if parsed:
                    parsed["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    parsed["host_rx_monotonic_ns"] = time.monotonic_ns()
                    self.frame_received.emit(parsed)

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self.ser:
                try:
                    if self.ser.is_open:
                        # Close CAN channel before releasing the COM port.
                        self._command("C", timeout=0.5)
                except Exception:
                    pass
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.status.emit("Остановлено")


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
            ser = serial.Serial(
                self.port, self.serial_baud, timeout=0.1, write_timeout=1
            )
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.write(b"V\\r")
            ser.flush()
            response = bytearray()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    response.extend(chunk)
                    if b"\\x07" in response or b"\\r" in response:
                        break
            raw = bytes(response)
            if not raw:
                self.error.emit(
                    "Нет ответа на запрос версии V. Проверьте COM-порт, "
                    "serial baud и драйвер."
                )
            elif b"\\x07" in raw:
                self.error.emit(f"Адаптер вернул NAK (0x07): {raw!r}")
            else:
                version = (
                    raw.replace(b"\\r", b"")
                    .replace(b"\\n", b"")
                    .decode("ascii", errors="replace")
                    .strip()
                )
                if version:
                    self.result.emit(
                        f"Ответ адаптера: {version} (raw: {raw!r})"
                    )
                else:
                    self.result.emit(
                        "Адаптер ответил ACK (CR), но строка версии пуста. "
                        f"Raw: {raw!r}"
                    )
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
