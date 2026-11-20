"""Small parser for classic Lawicel SLCAN frames."""
from dataclasses import dataclass

@dataclass
class CanFrame:
    timestamp: str
    can_id: str
    frame_type: str
    dlc: int
    data: str
    raw: str

def parse_line(line: str):
    line = line.strip()
    if not line or line[0] not in "tTrR":
        return None
    try:
        kind = line[0]
        extended = kind in "TR"
        remote = kind in "rR"
        id_len = 8 if extended else 3
        can_id = line[1:1 + id_len]
        dlc = int(line[1 + id_len], 16)
        if not 0 <= dlc <= 8:
            return None
        payload = "" if remote else line[2 + id_len:2 + id_len + dlc * 2].upper()
        if not remote and len(payload) != dlc * 2:
            return None
        return {"can_id": can_id.upper(), "frame_type": "RTR" if remote else ("EXT" if extended else "STD"), "dlc": dlc, "data": " ".join(payload[i:i+2] for i in range(0, len(payload), 2)), "raw": line}
    except (ValueError, IndexError):
        return None
