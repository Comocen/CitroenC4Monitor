"""Read-only OBD-II Mode 01 response parsing and PID decoding.

This module does not open serial ports or transmit diagnostic requests.
It decodes complete positive-response payloads supplied by a caller.
"""
import re


PID_DEFINITIONS = {
    0x04: ("Расчётная нагрузка двигателя", "%", 1),
    0x05: ("Температура охлаждающей жидкости", "°C", 1),
    0x06: ("Краткосрочная коррекция топлива, Bank 1", "%", 1),
    0x07: ("Долгосрочная коррекция топлива, Bank 1", "%", 1),
    0x0A: ("Давление топлива", "kPa", 1),
    0x0B: ("Абсолютное давление во впускном коллекторе", "kPa", 1),
    0x0C: ("Обороты двигателя", "rpm", 2),
    0x0D: ("Скорость автомобиля", "km/h", 1),
    0x0F: ("Температура воздуха на впуске", "°C", 1),
    0x10: ("Массовый расход воздуха (MAF)", "g/s", 2),
    0x11: ("Положение дроссельной заслонки", "%", 1),
    0x42: ("Напряжение блока управления", "V", 2),
    0x46: ("Температура окружающего воздуха", "°C", 1),
}


def _bytes(data):
    """Accept bytes, an iterable of byte values, or a hex string."""
    if isinstance(data, str):
        compact = re.sub(r"[^0-9A-Fa-f]", "", data)
        if len(compact) % 2:
            raise ValueError("Нечётное число шестнадцатеричных символов")
        return bytes.fromhex(compact)
    try:
        return bytes(data)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректные байты ответа OBD-II") from exc


def decode_pid(pid, data):
    """Decode Mode 01 PID data bytes into a display-ready record."""
    pid = int(pid)
    raw = _bytes(data)
    if pid not in PID_DEFINITIONS:
        raise ValueError(f"PID 01{pid:02X} пока не поддерживается декодером")
    name, unit, length = PID_DEFINITIONS[pid]
    if len(raw) != length:
        raise ValueError(f"Для PID 01{pid:02X} нужны {length} байт, получено {len(raw)}")
    a = raw[0]
    word = (a << 8) | raw[1] if length == 2 else a

    if pid == 0x04:
        value = a * 100.0 / 255.0
    elif pid in (0x05, 0x0F, 0x46):
        value = a - 40
    elif pid == 0x0A:
        value = 3 * a
    elif pid == 0x0B:
        value = a
    elif pid == 0x0C:
        value = word / 4.0
    elif pid == 0x0D:
        value = a
    elif pid == 0x10:
        value = word / 100.0
    elif pid == 0x11:
        value = a * 100.0 / 255.0
    elif pid == 0x42:
        value = word / 1000.0
    elif pid in (0x06, 0x07):
        value = (a - 128) * 100.0 / 128.0
    else:
        raise ValueError(f"Формула для PID 01{pid:02X} не реализована")

    return {"pid": f"01{pid:02X}", "name": name, "value": value,
            "unit": unit, "raw": raw.hex(" ").upper()}


def parse_mode01_response(response, requested_pid=None):
    """Decode a positive Mode 01 response (41 <PID> <data...>).

    Accepts spaced ELM327 text and optional CAN headers. Multi-frame
    ISO-TP responses are intentionally outside this first version.
    """
    if isinstance(response, bytes):
        response = response.decode("ascii", errors="ignore")
    tokens = re.findall(r"(?i)(?<![0-9a-f])[0-9a-f]{2}(?![0-9a-f])", str(response))
    values = [int(token, 16) for token in tokens]
    for index in range(len(values) - 2):
        if values[index] != 0x41:
            continue
        pid = values[index + 1]
        if requested_pid is not None and pid != int(requested_pid):
            continue
        if pid not in PID_DEFINITIONS:
            continue
        needed = PID_DEFINITIONS[pid][2]
        data = values[index + 2:index + 2 + needed]
        if len(data) == needed:
            return decode_pid(pid, data)
    return None


def supported_pids(data, base_pid=0x00):
    """Decode a four-byte support bitmap; base_pid is 00, 20, or 40."""
    raw = _bytes(data)
    if len(raw) != 4:
        raise ValueError("Карта поддерживаемых PID должна содержать 4 байта")
    base_pid = int(base_pid)
    if base_pid not in (0x00, 0x20, 0x40):
        raise ValueError("base_pid должен быть 00, 20 или 40")
    bitmap = int.from_bytes(raw, "big")
    return [base_pid + bit for bit in range(1, 33)
            if bitmap & (1 << (32 - bit))]
