"""
Agent Chat Log — บันทึกการสื่อสารระหว่าง AI agents
thread-safe in-memory buffer, expose ผ่าน /api/agent-log
"""

import threading
from datetime import datetime
import pytz

_lock = threading.Lock()
_logs = []          # list of log entry dicts
MAX_LOGS = 300      # เก็บล่าสุด 300 รายการ

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

# สีของแต่ละ agent (ใช้ใน dashboard)
AGENT_COLORS = {
    "rocket":  "#4f9eff",
    "atlas":   "#a78bfa",
    "pulse":   "#3ddc84",
    "sage":    "#ffd166",
    "guard":   "#ff5c5c",
    "coin":    "#fb923c",
    "lex":     "#22d3ee",
    "people":  "#f472b6",
    "pixel":   "#86efac",
    "sigma":   "#e879f9",
    "lens":    "#fbbf24",
    "rex":     "#f87171",
    "scheduler": "#64748b",
    "user":    "#94a3b8",
    "system":  "#475569",
}


def log_agent(from_agent: str, to_agent: str, message: str, response: str = "", status: str = "ok"):
    """บันทึก 1 รายการ agent interaction"""
    now = datetime.now(BANGKOK_TZ)
    entry = {
        "ts":    now.strftime("%H:%M:%S"),
        "date":  now.strftime("%d/%m"),
        "epoch": now.timestamp(),
        "from":  from_agent.lower(),
        "to":    to_agent.lower(),
        "msg":   message[:250],
        "res":   response[:400] if response else "",
        "status": status,           # ok | error | info
        "color_from": AGENT_COLORS.get(from_agent.lower(), "#64748b"),
        "color_to":   AGENT_COLORS.get(to_agent.lower(), "#64748b"),
    }
    with _lock:
        _logs.append(entry)
        if len(_logs) > MAX_LOGS:
            _logs.pop(0)


def get_logs(n: int = 80, since_epoch: float = 0):
    """ดึง log ล่าสุด n รายการ (หรือตั้งแต่ since_epoch)"""
    with _lock:
        if since_epoch:
            entries = [e for e in _logs if e["epoch"] > since_epoch]
        else:
            entries = list(_logs[-n:])
    return entries


def clear_logs():
    """ลบ log ทั้งหมด"""
    with _lock:
        _logs.clear()
