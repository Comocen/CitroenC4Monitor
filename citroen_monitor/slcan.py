"""Strict parser for classic Lawicel SLCAN frames.

CAN FD SLCAN variants are intentionally not accepted by this parser.
"""
import re


_HEX = re.compile(r"^[0-9A-Fa-f]+$")


def parse_line(line: str):
    line = str(line).strip()
    if not line or line[0] not in "tTrR":
        return None
    kind = line[0]
    extended = kind in "TR"
    remote = kind in "rR"
    id_len = 8 if extended else 3
    header_len = 1 + id_len + 1
    if len(line) < header_len:
        return None
    can_id_text = line[1:1 + id_len]
    dlc_text = line[1 + id_len]
    if not _HEX.fullmatch(can_id_text) or not _HEX.fullmatch(dlc_text):
        return None
    can_id = int(can_id_text, 16)
    if can_id > (0x1FFFFFFF if extended else 0x7FF):
        return None
    dlc = int(dlc_text, 16)
    if not 0 <= dlc <= 8:
        return None
    payload_text = line[header_len:]
    expected_payload_len = 0 if remote else dlc * 2
    if len(payload_text) != expected_payload_len:
        return None
    if payload_text and not _HEX.fullmatch(payload_text):
        return None
    payload_text = payload_text.upper()
    return {
        "can_id": can_id_text.upper(),
        "frame_type": "RTR" if remote else ("EXT" if extended else "STD"),
        "dlc": dlc,
        "data": " ".join(payload_text[i:i + 2] for i in range(0, len(payload_text), 2)),
        "raw": line,
    }
