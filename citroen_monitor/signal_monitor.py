"""Decode user-configured signals from passively received classic CAN frames."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SignalDefinition:
    name: str
    can_id: str
    start_bit: int
    bit_length: int
    factor: float = 1.0
    offset: float = 0.0
    unit: str = ""
    signed: bool = False

    def normalized_id(self):
        return f"{int(self.can_id, 16):X}"


def decode_signal_value(data, start_bit, bit_length, factor=1.0, offset=0.0,
                        signed=False):
    """Decode Intel/little-endian bit numbering (bit 0 is LSB of byte 0)."""
    if not isinstance(data, str):
        raise ValueError("CAN payload must be a hexadecimal string")
    try:
        payload = bytes.fromhex(data)
    except ValueError as exc:
        raise ValueError("Invalid hexadecimal CAN payload") from exc
    if not payload:
        raise ValueError("CAN payload is empty")
    if not isinstance(start_bit, int) or not isinstance(bit_length, int):
        raise ValueError("Bit positions must be integers")
    if start_bit < 0 or bit_length < 1 or bit_length > 64:
        raise ValueError("Bit range must be within 0..63 and length 1..64")
    if start_bit + bit_length > len(payload) * 8:
        raise ValueError("Configured bit range exceeds received payload")
    if not isinstance(factor, (int, float)) or not isinstance(offset, (int, float)):
        raise ValueError("Factor and offset must be numbers")
    if not math.isfinite(factor) or not math.isfinite(offset):
        raise ValueError("Factor and offset must be finite numbers")

    raw = int.from_bytes(payload, byteorder="little", signed=False)
    raw = (raw >> start_bit) & ((1 << bit_length) - 1)
    if signed and raw & (1 << (bit_length - 1)):
        raw -= 1 << bit_length
    return raw * float(factor) + float(offset)


def validate_definition(definition):
    """Validate a signal definition before it is added to the live monitor."""
    name = str(definition.name).strip()
    if not name:
        raise ValueError("Укажите название сигнала")
    can_id = str(definition.can_id).strip()
    if can_id.lower().startswith("0x"):
        can_id = can_id[2:]
    if not can_id or any(ch not in "0123456789abcdefABCDEF" for ch in can_id):
        raise ValueError("CAN ID должен быть шестнадцатеричным числом")
    if int(can_id, 16) > 0x1FFFFFFF:
        raise ValueError("CAN ID превышает 29-битный диапазон")
    if definition.start_bit < 0 or definition.bit_length < 1 or definition.bit_length > 64:
        raise ValueError("Проверьте начальный бит и длину сигнала (1..64)")
    if definition.start_bit + definition.bit_length > 64:
        raise ValueError("Сигнал не должен выходить за пределы 8 байт")
    if not math.isfinite(definition.factor) or not math.isfinite(definition.offset):
        raise ValueError("Множитель и смещение должны быть конечными числами")
    if definition.factor == 0:
        raise ValueError("Множитель не должен быть равен нулю")
    return SignalDefinition(
        name=name, can_id=f"{int(can_id, 16):X}",
        start_bit=int(definition.start_bit), bit_length=int(definition.bit_length),
        factor=float(definition.factor), offset=float(definition.offset),
        unit=str(definition.unit).strip(), signed=bool(definition.signed),
    )
