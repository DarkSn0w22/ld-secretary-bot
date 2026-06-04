"""
AI Reports Storage — บันทึกรายงานจาก agents ลง Google Sheets
ใช้ service account เดิม (GOOGLE_CREDENTIALS_JSON)
Sheet: OWNDAYS AI Reports (1 spreadsheet, แยก tab ต่อ agent)
"""
import os
import json
import base64
import time
from datetime import datetime
import pytz

REPORTS_SHEET_ID = os.getenv("REPORTS_SHEET_ID", "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ")
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

_gc = None   # gspread client (cached)


def _get_gspread(force_refresh: bool = False):
    """คืน gspread client — refresh ถ้า stale หรือ force"""
    global _gc
    if _gc and not force_refresh:
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
        print("[Reports] gspread client ready ✓")
        return _gc
    except Exception as e:
        _gc = None
        print(f"[Reports] gspread init error: {e}")
        return None


def _get_or_create_tab(ss, tab_name: str):
    """หา worksheet ที่มีชื่อนั้น หรือสร้างใหม่ — fallback to first sheet"""
    # 1. หา tab ที่มีชื่อตรง
    try:
        return ss.worksheet(tab_name)
    except Exception:
        pass

    # 2. ลองสร้าง tab ใหม่
    try:
        ws = ss.add_worksheet(title=tab_name, rows=2000, cols=5)
        ws.update("A1", [["Timestamp", "Agent", "Task", "Report", "Status"]])
        print(f"[Reports] Created new tab '{tab_name}'")
        return ws
    except Exception as e:
        print(f"[Reports] Cannot create tab '{tab_name}': {e} — using first sheet")

    # 3. Fallback: ใช้ sheet แรกที่มีอยู่
    try:
        ws = ss.get_worksheet(0)
        print(f"[Reports] Fallback to first sheet: '{ws.title}'")
        return ws
    except Exception as e2:
        raise Exception(f"Cannot access any worksheet: {e2}")


def save_report(agent_id: str, task: str, report_text: str) -> dict:
    """
    บันทึกรายงานลง Google Sheets
    - Tab ชื่อ agent (Meeting, Rex, Sage, Coin ฯลฯ)
    - แถวใหม่ต่อการ save ทุกครั้ง
    - คืน {ok, url, tab}
    - ถ้า client stale จะ refresh อัตโนมัติ 1 ครั้ง
    """
    if not REPORTS_SHEET_ID:
        return {"ok": False, "error": "REPORTS_SHEET_ID ไม่ได้ตั้งค่า"}

    def _try_save(gc_client):
        ss       = gc_client.open_by_key(REPORTS_SHEET_ID)
        tab_name = agent_id.capitalize()
        ws       = _get_or_create_tab(ss, tab_name)
        now      = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d %H:%M")
        trimmed  = report_text[:49000]
        ws.append_row([now, tab_name, task[:200], trimmed, "✅"],
                      value_input_option="RAW")
        url = f"https://docs.google.com/spreadsheets/d/{REPORTS_SHEET_ID}/edit#gid={ws.id}"
        print(f"[Reports] ✅ {tab_name} saved → {url}")
        return {"ok": True, "url": url, "tab": tab_name, "timestamp": now}

    # ── First attempt ─────────────────────────────────────────────
    gc = _get_gspread()
    if not gc:
        return {"ok": False, "error": "gspread client ไม่พร้อม (credentials?)"}
    try:
        return _try_save(gc)
    except Exception as e:
        err_str = str(e)
        print(f"[Reports] save error (attempt 1): {err_str}")

        # ── Retry on 429 (quota exceeded) — sleep 2 s then retry once ─
        if "429" in err_str:
            print("[Reports] 429 quota exceeded — sleeping 2 s then retrying...")
            time.sleep(2)
            try:
                return _try_save(gc)
            except Exception as e2:
                print(f"[Reports] save error (attempt 2, 429 retry): {e2}")
                return {"ok": False, "error": str(e2)}

        # ── Retry with fresh client (token อาจ expire) ────────────
        if any(k in err_str.lower() for k in ("invalid", "expired", "401", "403", "token")):
            print("[Reports] Refreshing gspread client and retrying...")
            gc2 = _get_gspread(force_refresh=True)
            if gc2:
                try:
                    return _try_save(gc2)
                except Exception as e2:
                    print(f"[Reports] save error (attempt 2): {e2}")
                    return {"ok": False, "error": str(e2)}

        return {"ok": False, "error": err_str}


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
