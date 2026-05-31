"""
AI Reports Storage — บันทึกรายงานจาก agents ลง Google Sheets
ใช้ service account เดิม (GOOGLE_CREDENTIALS_JSON)
Sheet: OWNDAYS AI Reports (1 spreadsheet, แยก tab ต่อ agent)
"""
import os
import json
import base64
from datetime import datetime
import pytz

REPORTS_SHEET_ID = os.getenv("REPORTS_SHEET_ID", "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ")
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

_gc = None   # gspread client (cached)


def _get_gspread():
    """คืน gspread client — ใช้ service account เดิม"""
    global _gc
    if _gc:
        return _gc
    try:
        import gspread
        from google.oauth2 import service_account

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if creds_json:
            creds_dict = json.loads(base64.b64decode(creds_json).decode("utf-8"))
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            key_file = os.getenv("GOOGLE_KEY_FILE", "credentials.json")
            creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)

        _gc = gspread.authorize(creds)
        return _gc
    except Exception as e:
        print(f"[Reports] gspread init error: {e}")
        return None


def _get_or_create_tab(ss, tab_name: str):
    """หา worksheet ที่มีชื่อนั้น หรือสร้างใหม่"""
    try:
        return ss.worksheet(tab_name)
    except Exception:
        ws = ss.add_worksheet(title=tab_name, rows=1000, cols=8)
        # Header row
        ws.update("A1", [["Timestamp", "Agent", "Task", "Report", "Status"]])
        return ws


def save_report(agent_id: str, task: str, report_text: str) -> dict:
    """
    บันทึกรายงานลง Google Sheets
    - Tab ชื่อ agent (เช่น Rex, Sage, Coin)
    - แถวใหม่ต่อการ save ทุกครั้ง
    - คืน {ok, url, tab, row}
    """
    gc = _get_gspread()
    if not gc or not REPORTS_SHEET_ID:
        return {"ok": False, "error": "Sheets client ไม่พร้อม"}

    try:
        ss = gc.open_by_key(REPORTS_SHEET_ID)
        tab_name = agent_id.capitalize()   # Rex, Sage, Coin, etc.
        ws = _get_or_create_tab(ss, tab_name)

        now = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d %H:%M")
        # ตัดข้อความยาวเกิน 50000 chars (Sheets limit per cell ~50k)
        report_trimmed = report_text[:49000] if len(report_text) > 49000 else report_text

        ws.append_row(
            [now, tab_name, task[:200], report_trimmed, "✅"],
            value_input_option="RAW",
        )

        url = f"https://docs.google.com/spreadsheets/d/{REPORTS_SHEET_ID}/edit#gid={ws.id}"
        print(f"[Reports] {tab_name} report saved → {url}")
        return {"ok": True, "url": url, "tab": tab_name, "timestamp": now}

    except Exception as e:
        print(f"[Reports] save error: {e}")
        return {"ok": False, "error": str(e)}


def save_table_report(agent_id: str, task: str, rows: list) -> dict:
    """
    บันทึก structured data (list of lists) ลง Sheets
    rows[0] = header, rows[1:] = data
    """
    gc = _get_gspread()
    if not gc or not REPORTS_SHEET_ID:
        return {"ok": False, "error": "Sheets client ไม่พร้อม"}

    try:
        ss = gc.open_by_key(REPORTS_SHEET_ID)
        now = datetime.now(BANGKOK_TZ).strftime("%Y%m%d_%H%M")
        tab_name = f"{agent_id.capitalize()}_{now}"
        ws = ss.add_worksheet(title=tab_name, rows=max(len(rows)+5, 50), cols=max(len(rows[0])+2 if rows else 5, 5))

        # Write task description in A1
        ws.update("A1", [[f"Agent: {agent_id.upper()} | Task: {task[:100]} | Generated: {now}"]])
        if rows:
            ws.update("A2", rows)

        url = f"https://docs.google.com/spreadsheets/d/{REPORTS_SHEET_ID}/edit#gid={ws.id}"
        return {"ok": True, "url": url, "tab": tab_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def reports_ready() -> bool:
    """True ถ้าพร้อมบันทึก"""
    return bool(
        REPORTS_SHEET_ID and
        (os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("credentials.json"))
    )


# ── Backward-compatible aliases ──────────────────────────────────────────────
def drive_ready() -> bool:
    return reports_ready()

def save_text_report(agent_id: str, filename: str, content: str) -> dict:
    """Alias: บันทึก text report → Sheets"""
    task = filename.replace(".txt", "").replace("_", " ")
    return save_report(agent_id, task, content)

def save_excel_report(agent_id: str, filename: str, excel_bytes: bytes) -> dict:
    """Excel ไม่รองรับใน Sheets — คืน error แนะนำใช้ save_table_report แทน"""
    return {"ok": False, "error": "ใช้ save_table_report(agent_id, task, rows) สำหรับ structured data"}

def save_spreadsheet_data(agent_id: str, title: str, rows: list) -> dict:
    """Alias: บันทึก structured data → Sheets tab"""
    return save_table_report(agent_id, title, rows)
