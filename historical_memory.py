"""
Historical Memory — OWNDAYS AI Office v35
=========================================================
Sigma และ agents อื่น track KPI trends ข้ามสัปดาห์/เดือน
จัดเก็บ snapshot ลง Google Sheets tab "AI_Memory"
Fallback: in-memory buffer (ไม่ persist ข้าม restart)

Schema per row:
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
from datetime import datetime, timedelta
from typing import Optional
import pytz

BANGKOK_TZ   = pytz.timezone("Asia/Bangkok")
REPORTS_SHEET_ID = os.getenv("REPORTS_SHEET_ID", "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ")
MEMORY_TAB   = "AI_Memory"
MAX_ROWS_PER_METRIC = 60    # เก็บสูงสุด 60 จุด ต่อ metric (~60 วัน ถ้า daily)

# ── In-memory fallback buffer ────────────────────────────────────────────────
# list of {ts, source, metric, value, notes}
_buffer: list = []
MAX_BUFFER = 500


# ── Sheets helpers ────────────────────────────────────────────────────────────

def _get_sheet_ws():
    """คืน worksheet AI_Memory — สร้างถ้ายังไม่มี"""
    try:
        from drive_api import _get_gspread
        gc = _get_gspread()
        if not gc or not REPORTS_SHEET_ID:
            return None
        ss = gc.open_by_key(REPORTS_SHEET_ID)
        try:
            ws = ss.worksheet(MEMORY_TAB)
        except Exception:
            ws = ss.add_worksheet(title=MEMORY_TAB, rows=2000, cols=5)
            ws.update("A1", [["Timestamp", "Source", "Metric", "Value", "Notes"]])
            print(f"[Memory] Created tab '{MEMORY_TAB}'")
        return ws
    except Exception as e:
        print(f"[Memory] sheet error: {e}")
        return None


def _sheets_ready() -> bool:
    return bool(
        REPORTS_SHEET_ID and
        (os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("credentials.json"))
    )


# ── Public API ────────────────────────────────────────────────────────────────

def record_snapshot(source: str, metrics: dict, notes: str = "") -> bool:
    """
    บันทึก KPI snapshot ลง Sheets + buffer

    Args:
        source   ชื่อ agent/system เช่น "coin", "pulse", "pixel"
        metrics  dict ของ metric_key → numeric_value
                 เช่น {"survey.overall_avg": 3.52, "survey.total_responses": 148}
        notes    หมายเหตุเพิ่มเติม (ไม่บังคับ)

    Returns:
        True ถ้าสำเร็จ (Sheets หรือ buffer)
    """
    now = datetime.now(BANGKOK_TZ)
    ts  = now.strftime("%Y-%m-%d %H:%M")

    # ─ Buffer (always) ────────────────────────────────────────────
    for key, val in metrics.items():
        try:
            _buffer.append({
                "ts": ts, "source": source,
                "metric": key, "value": float(val), "notes": notes
            })
        except (TypeError, ValueError):
            pass  # skip non-numeric
    if len(_buffer) > MAX_BUFFER:
        del _buffer[:len(_buffer) - MAX_BUFFER]

    # ─ Google Sheets ──────────────────────────────────────────────
    if not _sheets_ready():
        return True  # buffer only

    try:
        ws = _get_sheet_ws()
        if not ws:
            return False
        rows = [
            [ts, source, key, float(val) if isinstance(val, (int, float)) else 0, notes]
            for key, val in metrics.items()
            if isinstance(val, (int, float))
        ]
        if rows:
            ws.append_rows(rows, value_input_option="RAW")
        return True
    except Exception as e:
        print(f"[Memory] record error: {e}")
        return False


def get_history(metric_key: str, n: int = 10, source: str = None) -> list:
    """
    คืน list ของ {ts, value, source} ล่าสุด n จุด

    ลำดับ: เก่าสุด → ใหม่สุด (เหมาะกับ chart)
    """
    # ลอง Sheets ก่อน
    if _sheets_ready():
        try:
            ws = _get_sheet_ws()
            if ws:
                all_rows = ws.get_all_values()
                # all_rows[0] = header, [1:] = data
                data = []
                for row in all_rows[1:]:
                    if len(row) < 4:
                        continue
                    r_ts, r_src, r_metric, r_val = row[0], row[1], row[2], row[3]
                    if r_metric != metric_key:
                        continue
                    if source and r_src != source:
                        continue
                    try:
                        data.append({"ts": r_ts, "value": float(r_val), "source": r_src})
                    except ValueError:
                        pass
                return data[-n:]  # last n
        except Exception as e:
            print(f"[Memory] get_history sheets error: {e}")

    # Fallback buffer
    data = [
        {"ts": r["ts"], "value": r["value"], "source": r["source"]}
        for r in _buffer
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
                result["trend"], result["arrow"], result["color"] = "up",   "↑", "green"
            elif result["change_pct"] < -threshold * 100:
                result["trend"], result["arrow"], result["color"] = "down", "↓", "red"
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
        ("survey.overall_avg",      "Survey Avg",     "pulse",  True),
        ("survey.total_responses",  "Survey Responses","pulse", True),
        ("cost.usage_pct",          "Budget Used %",  "coin",   False),  # False = ขึ้นไม่ดี
        ("cost.actual",             "Budget Actual",  "coin",   False),
        ("oar.total",               "OAR Total",      "pulse",  True),
        ("website.latency_ms",      "Web Latency",    "pixel",  False),  # False = ขึ้นไม่ดี
        ("website.sessions_7d",     "Web Sessions",   "pixel",  True),
        ("hr.probation_count",      "Probation",      "people", False),
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
        curr = t["current"]
        label = t["label"]
        if t["change_pct"] is not None:
            chg  = f"{t['change_pct']:+.1f}%"
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
