"""
Historical Memory — OWNDAYS AI Office v36
=========================================================
Sigma และ agents อื่น track KPI trends ข้ามสัปดาห์/เดือน

PRIMARY storage: /tmp/owndays_memory.json  (fast, no quota)
  Structure: {"snapshots": [{ts, source, metric, value, notes}, ...]}
  Keep last 500 entries.

GOOGLE SHEETS SYNC: ONLY via sync_to_sheets() — called manually
  or once/day from the scheduler.  NOT on every read/write.

On startup: load from JSON. If missing, seed once from Sheets
  (silent fail if unavailable).

Schema per row (Sheets / JSON):
  [Timestamp | Source | Metric | Value | Notes]

ตัวอย่าง metrics ที่ track:
  survey.overall_avg        — คะแนน survey เฉลี่ย
  survey.total_responses    — จำนวนผู้ตอบ
  cost.usage_pct            — % งบที่ใช้ไป
  cost.actual               — ยอดจริง (บาท)
  oar.total                 — OAR registrations
  website.is_up             — 1/0
  website.latency_ms        — latency
  website.sessions_7d       — GA4 sessions
  hr.probation_count        — จำนวน probation
"""

import os
import json
import threading
from datetime import datetime, timedelta
from typing import Optional
import pytz

BANGKOK_TZ       = pytz.timezone("Asia/Bangkok")
REPORTS_SHEET_ID = os.getenv("REPORTS_SHEET_ID", "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ")
MEMORY_TAB       = "AI_Memory"
MAX_ENTRIES      = 500          # keep last N snapshots in JSON
JSON_PATH        = "/tmp/owndays_memory.json"

# ── Thread safety ──────────────────────────────────────────────────────────────
_lock: threading.Lock = threading.Lock()

# ── In-memory store (loaded from JSON on first use) ───────────────────────────
# list of {ts, source, metric, value, notes}
_snapshots: list = []
_loaded: bool    = False   # has the JSON file been loaded yet?
_dirty_since: int = 0      # index of first entry not yet synced to Sheets


# ── JSON helpers ───────────────────────────────────────────────────────────────

def _json_path() -> str:
    return JSON_PATH


def _load_json() -> None:
    """Load snapshots from JSON file into _snapshots. Call once."""
    global _snapshots, _loaded, _dirty_since
    path = _json_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("snapshots", [])
        # Validate / coerce entries
        clean = []
        for e in entries:
            try:
                clean.append({
                    "ts":     str(e.get("ts", "")),
                    "source": str(e.get("source", "")),
                    "metric": str(e.get("metric", "")),
                    "value":  float(e.get("value", 0.0)),
                    "notes":  str(e.get("notes", "")),
                })
            except (TypeError, ValueError):
                pass
        _snapshots = clean[-MAX_ENTRIES:]
        _dirty_since = len(_snapshots)   # all loaded entries are already "synced"
        print(f"[Memory] Loaded {len(_snapshots)} entries from {path}")
        _loaded = True
        return
    except FileNotFoundError:
        print(f"[Memory] {path} not found — attempting seed from Sheets")
    except Exception as e:
        print(f"[Memory] JSON load error: {e} — attempting seed from Sheets")

    # Seed once from Sheets (silent fail)
    _loaded = True   # mark loaded so we don't retry in a loop
    try:
        rows = _sheets_fetch_all()
        for row in rows:
            try:
                _snapshots.append({
                    "ts":     row[0],
                    "source": row[1],
                    "metric": row[2],
                    "value":  float(row[3]),
                    "notes":  row[4] if len(row) > 4 else "",
                })
            except (IndexError, ValueError):
                pass
        _snapshots = _snapshots[-MAX_ENTRIES:]
        _dirty_since = len(_snapshots)   # seeded = already in Sheets
        if _snapshots:
            _save_json()
            print(f"[Memory] Seeded {len(_snapshots)} entries from Sheets → {path}")
    except Exception as e:
        print(f"[Memory] Sheets seed failed (ok, continuing): {e}")


def _save_json() -> None:
    """Persist _snapshots to JSON file. Caller must hold _lock."""
    path = _json_path()
    try:
        payload = {"snapshots": _snapshots}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=None, separators=(",", ":"))
        os.replace(tmp, path)          # atomic on POSIX
    except Exception as e:
        print(f"[Memory] JSON save error: {e}")


def _ensure_loaded() -> None:
    """Lazy-load on first access (thread-safe)."""
    global _loaded
    if not _loaded:
        with _lock:
            if not _loaded:
                _load_json()


# ── Sheets helpers ─────────────────────────────────────────────────────────────

def _sheets_ready() -> bool:
    return bool(
        REPORTS_SHEET_ID and
        (os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("credentials.json"))
    )


def _get_sheet_ws():
    """Return worksheet AI_Memory — create if missing."""
    try:
        from drive_api import _get_gspread
        gc = _get_gspread()
        if not gc or not REPORTS_SHEET_ID:
            return None
        ss = gc.open_by_key(REPORTS_SHEET_ID)
        try:
            return ss.worksheet(MEMORY_TAB)
        except Exception:
            ws = ss.add_worksheet(title=MEMORY_TAB, rows=2000, cols=5)
            ws.update("A1", [["Timestamp", "Source", "Metric", "Value", "Notes"]])
            print(f"[Memory] Created tab '{MEMORY_TAB}'")
            return ws
    except Exception as e:
        print(f"[Memory] sheet error: {e}")
        return None


def _sheets_fetch_all() -> list:
    """Fetch all data rows from Sheets (header excluded). Returns list of rows."""
    ws = _get_sheet_ws()
    if not ws:
        return []
    all_rows = ws.get_all_values()
    return all_rows[1:] if len(all_rows) > 1 else []


# ── Public API ─────────────────────────────────────────────────────────────────

def record_snapshot(source: str, metrics: dict, notes: str = "") -> bool:
    """
    บันทึก KPI snapshot ลง JSON (primary). ไม่แตะ Sheets.

    Args:
        source   ชื่อ agent/system เช่น "coin", "pulse", "pixel"
        metrics  dict ของ metric_key → numeric_value
                 เช่น {"survey.overall_avg": 3.52, "survey.total_responses": 148}
        notes    หมายเหตุเพิ่มเติม (ไม่บังคับ)

    Returns:
        True เสมอ (Sheets errors ไม่กระทบ)
    """
    _ensure_loaded()
    now = datetime.now(BANGKOK_TZ)
    ts  = now.strftime("%Y-%m-%d %H:%M")

    new_entries = []
    for key, val in metrics.items():
        try:
            new_entries.append({
                "ts":     ts,
                "source": source,
                "metric": key,
                "value":  float(val),
                "notes":  notes,
            })
        except (TypeError, ValueError):
            pass   # skip non-numeric

    if not new_entries:
        return True

    with _lock:
        _snapshots.extend(new_entries)
        # Trim to MAX_ENTRIES
        excess = len(_snapshots) - MAX_ENTRIES
        if excess > 0:
            del _snapshots[:excess]
        _save_json()

    return True


def get_history(metric_key: str, n: int = 10, source: str = None) -> list:
    """
    คืน list ของ {ts, value, source} ล่าสุด n จุด จาก JSON (primary).

    ลำดับ: เก่าสุด → ใหม่สุด (เหมาะกับ chart)
    """
    _ensure_loaded()
    with _lock:
        data = [
            {"ts": r["ts"], "value": r["value"], "source": r["source"]}
            for r in _snapshots
            if r["metric"] == metric_key and (not source or r["source"] == source)
        ]
    return data[-n:]


def get_trend(metric_key: str, periods: int = 4) -> dict:
    """
    วิเคราะห์ trend ของ metric

    Returns:
        {
            metric, current, previous, change, change_pct,
            trend: 'up'|'down'|'stable',
            arrow: '↑'|'↓'|'→',
            color: 'green'|'red'|'gray',
            history: [values...],
            data_points: int
        }
    """
    history = get_history(metric_key, n=periods + 1)
    result = {
        "metric":      metric_key,
        "current":     None,
        "previous":    None,
        "change":      None,
        "change_pct":  None,
        "trend":       "unknown",
        "arrow":       "—",
        "color":       "gray",
        "history":     [h["value"] for h in history],
        "data_points": len(history),
    }

    if not history:
        return result

    result["current"] = history[-1]["value"]

    if len(history) >= 2:
        result["previous"]   = history[-2]["value"]
        result["change"]     = result["current"] - result["previous"]
        if result["previous"] != 0:
            result["change_pct"] = result["change"] / abs(result["previous"]) * 100

        threshold = 0.02  # 2% change = significant
        if result["change_pct"] is not None:
            if result["change_pct"] > threshold * 100:
                result["trend"], result["arrow"], result["color"] = "up",     "↑", "green"
            elif result["change_pct"] < -threshold * 100:
                result["trend"], result["arrow"], result["color"] = "down",   "↓", "red"
            else:
                result["trend"], result["arrow"], result["color"] = "stable", "→", "gray"
        else:
            result["trend"], result["arrow"], result["color"] = "stable", "→", "gray"

    return result


def get_dashboard_trends() -> dict:
    """
    คืน trend summary สำหรับ dashboard
    ทุก metric หลักพร้อม arrow + color
    """
    KEY_METRICS = [
        ("survey.overall_avg",     "Survey Avg",       "pulse",  True),
        ("survey.total_responses", "Survey Responses", "pulse",  True),
        ("cost.usage_pct",         "Budget Used %",    "coin",   False),  # False = ขึ้นไม่ดี
        ("cost.actual",            "Budget Actual",    "coin",   False),
        ("oar.total",              "OAR Total",        "pulse",  True),
        ("website.latency_ms",     "Web Latency",      "pixel",  False),  # False = ขึ้นไม่ดี
        ("website.sessions_7d",    "Web Sessions",     "pixel",  True),
        ("hr.probation_count",     "Probation",        "people", False),
    ]

    out = {}
    for metric_key, label, source, higher_is_better in KEY_METRICS:
        t = get_trend(metric_key)
        t["label"]            = label
        t["source"]           = source
        t["higher_is_better"] = higher_is_better

        # Flip color logic ถ้า higher_is_better = False
        if t["trend"] != "unknown" and not higher_is_better:
            if t["color"] == "green":
                t["color"] = "red"
            elif t["color"] == "red":
                t["color"] = "green"

        out[metric_key] = t

    return out


def get_sigma_context(lookback_days: int = 30) -> str:
    """
    คืน historical context สำหรับ Sigma ใช้ใน analysis
    สรุป trends ในรูปแบบข้อความ
    """
    trends = get_dashboard_trends()
    if not any(t["current"] is not None for t in trends.values()):
        return "ยังไม่มีข้อมูล historical (เพิ่งเริ่มเก็บ)"

    lines = [f"Historical KPI Trends (last {lookback_days} days):"]
    for key, t in trends.items():
        if t["current"] is None:
            continue
        curr  = t["current"]
        label = t["label"]
        if t["change_pct"] is not None:
            chg = f"{t['change_pct']:+.1f}%"
            lines.append(
                f"  {label}: {curr:.2f} {t['arrow']} ({chg} from prev) "
                f"[{t['data_points']} data pts]"
            )
        else:
            lines.append(f"  {label}: {curr:.2f} {t['arrow']} [1 data point]")
    return "\n".join(lines)


def get_summary_text() -> str:
    """สรุปสั้นๆ สำหรับ agent reports"""
    trends = get_dashboard_trends()
    significant = []
    for key, t in trends.items():
        if t["current"] is None or t["data_points"] < 2:
            continue
        if t["trend"] in ("up", "down") and t.get("change_pct") is not None:
            icon = "📈" if t["color"] == "green" else "📉"
            significant.append(
                f"{icon} {t['label']}: {t['current']:.1f} ({t['change_pct']:+.1f}%)"
            )
    if not significant:
        return "ยังไม่มีข้อมูล trend (รอ 2+ snapshots)"
    return "Trend สำคัญ:\n" + "\n".join(significant[:5])


# ── Sheets sync (manual / scheduled, NOT automatic) ───────────────────────────

def sync_to_sheets() -> dict:
    """
    Bulk-write entries that have NOT yet been synced to Google Sheets.

    Call this from the scheduler (e.g. once/day) or manually.
    Returns {"ok": bool, "synced": int, "error": str|None}

    Thread-safe: takes _lock only while reading the pending slice, then
    updates _dirty_since after a successful write.
    """
    global _dirty_since

    _ensure_loaded()

    if not _sheets_ready():
        return {"ok": False, "synced": 0, "error": "Sheets credentials not configured"}

    with _lock:
        pending = _snapshots[_dirty_since:]
        start_idx = _dirty_since

    if not pending:
        return {"ok": True, "synced": 0, "error": None}

    try:
        ws = _get_sheet_ws()
        if not ws:
            return {"ok": False, "synced": 0, "error": "Cannot open worksheet"}

        rows = [
            [e["ts"], e["source"], e["metric"], e["value"], e["notes"]]
            for e in pending
        ]
        ws.append_rows(rows, value_input_option="RAW")

        with _lock:
            # Advance dirty pointer.  If _snapshots was trimmed while we were
            # writing, clamp so we don't go past the current length.
            _dirty_since = min(start_idx + len(pending), len(_snapshots))

        print(f"[Memory] sync_to_sheets: wrote {len(rows)} rows")
        return {"ok": True, "synced": len(rows), "error": None}

    except Exception as e:
        print(f"[Memory] sync_to_sheets error: {e}")
        return {"ok": False, "synced": 0, "error": str(e)}
