"""
Agent Save Tools — Shared สำหรับทุก agent
==========================================
ให้ทุก agent สามารถ:
  1. write_to_sheets   — บันทึกข้อมูลลง Google Sheets (ของตัวเองหรือ sheet ใดก็ได้)
  2. read_any_sheet    — อ่านข้อมูลจาก Sheets ใดก็ได้ (generic reader)
  3. create_drive_file — สร้างไฟล์ใน Google Drive folder (real file)

วิธีใช้ใน agent file:
    from agent_save_tools import SAVE_TOOLS, execute_save_tool, auto_save

    AGENT_TOOLS = [...existing tools...] + SAVE_TOOLS

    def execute_agent_tool(name, inputs):
        result = execute_save_tool(name, inputs, agent_id="atlas")
        if result is not None:
            return result
        # ...existing handlers...
"""

import os
import io
import threading
from agent_log import log_agent

DEFAULT_SHEET_ID   = os.getenv("REPORTS_SHEET_ID", "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ")
DEFAULT_FOLDER_ID  = os.getenv("DRIVE_FOLDER_ID",  "1m4IHMoxU0Wj_tBP8W90ql2JJewkP7kEM")

# ── Tool definitions (เพิ่มใน TOOLS list ของแต่ละ agent) ──────────────────────

SAVE_TOOLS = [
    {
        "name": "write_to_sheets",
        "description": (
            "บันทึกรายงาน ผลการวิเคราะห์ หรือข้อมูลลง Google Sheets "
            "(default: OWNDAYS AI Reports tab ของ agent ตัวเอง) "
            "หรือระบุ sheet_id + tab_name เพื่อเขียนลง Sheets ใดก็ได้"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "หัวเรื่องรายงาน เช่น 'Sales Analysis Week 22'"
                },
                "content": {
                    "type": "string",
                    "description": "เนื้อหาทั้งหมดที่ต้องการบันทึก"
                },
                "sheet_id": {
                    "type": "string",
                    "description": "(optional) Google Sheets ID — ถ้าไม่ระบุใช้ OWNDAYS AI Reports"
                },
                "tab_name": {
                    "type": "string",
                    "description": "(optional) ชื่อ tab — ถ้าไม่ระบุใช้ชื่อ agent ตัวเอง"
                },
                "mode": {
                    "type": "string",
                    "enum": ["append", "overwrite"],
                    "description": "(optional) 'append' (default) หรือ 'overwrite'",
                    "default": "append"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "read_any_sheet",
        "description": (
            "อ่านข้อมูลจาก Google Sheets ใดก็ได้ (generic reader) "
            "ใช้เมื่อต้องเข้าถึงข้อมูลที่ไม่ใช่ survey/oar/dashboard ปกติ "
            "เช่น ตารางงาน trainers, schedules, planning sheets"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "Google Sheets ID (จาก URL) หรือ full URL"
                },
                "tab_name": {
                    "type": "string",
                    "description": "ชื่อ tab ที่จะอ่าน"
                },
                "range": {
                    "type": "string",
                    "description": "(optional) A1 notation เช่น 'A1:Z100' — ถ้าไม่ระบุอ่านทั้ง tab"
                },
                "max_rows": {
                    "type": "integer",
                    "description": "(optional) จำกัดจำนวนแถว default 200",
                    "default": 200
                }
            },
            "required": ["sheet_id", "tab_name"]
        }
    },
    {
        "name": "create_drive_file",
        "description": (
            "สร้างไฟล์งานใหม่ใน Google Drive folder ของ OWNDAYS L&D AI "
            "(real Drive file — ไม่ใช่แค่ Sheets row) "
            "ใช้เมื่อต้องการ action plan, proposal, training material ที่ต้องแชร์เป็นไฟล์"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "ชื่อไฟล์พร้อมนามสกุล เช่น 'Action_Plan_Q3_2026.txt'"
                },
                "content": {
                    "type": "string",
                    "description": "เนื้อหาทั้งหมดของไฟล์"
                },
                "folder_id": {
                    "type": "string",
                    "description": "(optional) Drive folder ID — ถ้าไม่ระบุใช้ default L&D folder"
                }
            },
            "required": ["filename", "content"]
        }
    }
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_sheet_id(s: str) -> str:
    """ดึง sheet_id จาก URL หรือใช้เป็น id ตรงๆ"""
    if not s:
        return DEFAULT_SHEET_ID
    if "/spreadsheets/d/" in s:
        try:
            return s.split("/spreadsheets/d/")[1].split("/")[0]
        except Exception:
            pass
    return s.strip()


# ── Handler dispatch ──────────────────────────────────────────────────────────

def execute_save_tool(tool_name: str, tool_input: dict,
                      agent_id: str = "agent"):
    """คืน string ถ้า tool match, คืน None ถ้าไม่ใช่ tool ของโมดูลนี้"""
    if tool_name == "write_to_sheets":
        return _write_to_sheets(tool_input, agent_id)
    elif tool_name == "read_any_sheet":
        return _read_any_sheet(tool_input, agent_id)
    elif tool_name == "create_drive_file":
        return _create_drive_file(tool_input, agent_id)
    return None


# ── 1) write_to_sheets ────────────────────────────────────────────────────────

def _write_to_sheets(inputs: dict, agent_id: str) -> str:
    title    = inputs.get("title", "รายงาน")
    content  = inputs.get("content", "")
    sheet_id = _extract_sheet_id(inputs.get("sheet_id", ""))
    tab      = inputs.get("tab_name") or agent_id.capitalize()
    mode     = inputs.get("mode", "append")

    try:
        from drive_api import _get_gspread
        from datetime import datetime
        import pytz
        BANGKOK = pytz.timezone("Asia/Bangkok")

        gc = _get_gspread()
        if not gc:
            return "❌ gspread client ไม่พร้อม"

        ss = gc.open_by_key(sheet_id)

        # find or create tab
        try:
            ws = ss.worksheet(tab)
        except Exception:
            try:
                ws = ss.add_worksheet(title=tab, rows=2000, cols=5)
                ws.update("A1", [["Timestamp", "Agent", "Title", "Content", "Status"]])
            except Exception as e:
                return f"❌ ไม่สามารถสร้าง tab '{tab}': {e}"

        now = datetime.now(BANGKOK).strftime("%Y-%m-%d %H:%M")
        trimmed = content[:49000]
        row = [now, agent_id.capitalize(), title[:200], trimmed, "✅"]

        if mode == "overwrite":
            ws.clear()
            ws.update("A1", [["Timestamp", "Agent", "Title", "Content", "Status"], row])
        else:
            ws.append_row(row, value_input_option="RAW")

        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={ws.id}"
        log_agent(agent_id, "sheets", f"saved: {title[:80]}", url)
        return (f"✅ บันทึกลง Google Sheets สำเร็จครับ\n"
                f"Tab: {tab} | {title}\n"
                f"Mode: {mode}\n"
                f"Link: {url}")

    except Exception as e:
        err = str(e)
        log_agent(agent_id, "sheets", "save FAILED", err, status="error")
        return f"❌ write_to_sheets error: {err}"


# ── 2) read_any_sheet ─────────────────────────────────────────────────────────

def _read_any_sheet(inputs: dict, agent_id: str) -> str:
    sheet_id  = _extract_sheet_id(inputs.get("sheet_id", ""))
    tab_name  = inputs.get("tab_name", "")
    rng       = inputs.get("range", "")
    max_rows  = int(inputs.get("max_rows", 200))

    if not sheet_id or not tab_name:
        return "❌ ต้องระบุ sheet_id และ tab_name"

    try:
        from drive_api import _get_gspread
        gc = _get_gspread()
        if not gc:
            return "❌ gspread client ไม่พร้อม"

        ss = gc.open_by_key(sheet_id)
        try:
            ws = ss.worksheet(tab_name)
        except Exception as e:
            tabs = [w.title for w in ss.worksheets()]
            return f"❌ ไม่พบ tab '{tab_name}'\nTabs ที่มี: {', '.join(tabs[:20])}"

        if rng:
            rows = ws.get(rng)
        else:
            rows = ws.get_all_values()

        if not rows:
            return f"⚠️ Tab '{tab_name}' ว่าง"

        # Limit rows + columns
        rows = rows[:max_rows]
        header = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        log_agent(agent_id, "sheets", f"read: {tab_name}", f"{len(rows)} rows")

        # Format as text table (compact)
        out = [f"Sheet: {sheet_id[:20]}... | Tab: {tab_name} | Rows: {len(rows)}"]
        if header:
            out.append(f"Header: {' | '.join(str(c)[:30] for c in header)}")
        out.append("---")
        for i, r in enumerate(data_rows[:50]):  # max 50 rows displayed
            cells = ' | '.join(str(c)[:40] for c in r if c != "")
            if cells:
                out.append(f"{i+1}. {cells}")
        if len(data_rows) > 50:
            out.append(f"... และอีก {len(data_rows)-50} แถว")
        return "\n".join(out)

    except Exception as e:
        err = str(e)
        log_agent(agent_id, "sheets", "read FAILED", err, status="error")
        return f"❌ read_any_sheet error: {err}"


# ── 3) create_drive_file ──────────────────────────────────────────────────────

def _create_drive_file(inputs: dict, agent_id: str) -> str:
    filename  = inputs.get("filename", "report.txt")
    content   = inputs.get("content", "")
    folder_id = inputs.get("folder_id") or DEFAULT_FOLDER_ID

    # ลองสร้างไฟล์จริงใน Drive ก่อน
    drive_result = _try_create_real_drive_file(filename, content, folder_id, agent_id)
    if drive_result:
        return drive_result

    # Fallback: บันทึกใน Sheets tab
    return _fallback_save_as_sheets_row(filename, content, agent_id)


def _try_create_real_drive_file(filename: str, content: str,
                                 folder_id: str, agent_id: str) -> str | None:
    """ลองสร้างไฟล์จริงใน Drive — return None ถ้าไม่ได้ให้ fallback"""
    try:
        from drive_api import _get_gspread
        gc = _get_gspread()
        if not gc:
            return None

        # ใช้ credentials เดียวกับ gspread เพื่อเรียก Drive API
        creds = gc.auth
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http   import MediaIoBaseUpload
        except ImportError:
            print("[Drive] googleapiclient ไม่ติดตั้ง — fallback to Sheets")
            return None

        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        # MIME type — สำหรับ .txt
        mime = "text/plain"
        if filename.lower().endswith((".md",)):
            mime = "text/markdown"
        elif filename.lower().endswith((".csv",)):
            mime = "text/csv"
        elif filename.lower().endswith((".json",)):
            mime = "application/json"

        body = content.encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(body), mimetype=mime, resumable=False)

        file_metadata = {
            "name":    filename,
            "parents": [folder_id],
        }

        result = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        url    = result.get("webViewLink", "")
        fileid = result.get("id", "")
        log_agent(agent_id, "drive", f"created: {filename}", url)
        return (f"✅ สร้างไฟล์ '{filename}' ใน Google Drive สำเร็จครับ\n"
                f"Folder: {folder_id}\n"
                f"Link: {url}\n"
                f"File ID: {fileid}")

    except Exception as e:
        err = str(e)
        print(f"[Drive] real file create failed: {err}")
        log_agent(agent_id, "drive", "real create failed", err, status="error")
        # ส่ง None เพื่อ fallback
        return None


def _fallback_save_as_sheets_row(filename: str, content: str, agent_id: str) -> str:
    """Fallback: เก็บใน Sheets tab "Drive_Files" """
    try:
        from drive_api import save_report
        full_content = f"=== {filename} ===\n\n{content}"
        res = save_report("Drive_Files", filename, full_content)
        if res.get("ok"):
            url = res.get("url", "")
            log_agent(agent_id, "drive", f"saved as sheet row: {filename}", url)
            return (f"⚠️ Drive API ไม่พร้อม — บันทึกเป็น Sheets row แทน\n"
                    f"ไฟล์: '{filename}'\n"
                    f"Tab: Drive_Files\n"
                    f"Link: {url}")
        else:
            return f"❌ สร้างไฟล์ไม่สำเร็จ: {res.get('error','unknown')}"
    except Exception as e:
        return f"❌ create_drive_file fallback error: {e}"


# ── Auto-save helper (เรียกหลัง agent เสร็จงาน) ─────────────────────────────

# ขนาดผลงานที่ถือว่า "ชิ้นใหญ่" → สร้างเป็น Drive file ด้วย
# ปรับได้ผ่าน env AUTO_DRIVE_THRESHOLD (default 500 chars)
AUTO_DRIVE_THRESHOLD = int(os.getenv("AUTO_DRIVE_THRESHOLD", "500"))
AUTO_DRIVE_ENABLED   = os.getenv("AUTO_DRIVE_ENABLED", "1") == "1"


def _slugify(text: str, max_len: int = 40) -> str:
    """แปลงข้อความเป็น filename-safe slug"""
    import re
    # เอาเฉพาะ alphanumeric + spaces, ตัดสั้น
    cleaned = re.sub(r'[^\w\s\-ก-๙]', '', text)[:max_len]
    return cleaned.strip().replace(' ', '_') or 'report'


def auto_save(agent_id: str, task: str, result: str) -> None:
    """
    บันทึก agent result อัตโนมัติ:
      1. ทุกครั้ง → Sheets tab ของ agent นั้น (background)
      2. ถ้าผลงาน > AUTO_DRIVE_THRESHOLD → Drive file ด้วย (background)
    """
    if not result or len(result) < 40:
        return

    def _save_sheets():
        try:
            from drive_api import save_report
            tab = agent_id.capitalize()
            res = save_report(tab, task[:150], result)
            if res.get("ok"):
                print(f"[AutoSave] {tab} Sheets ✅")
            else:
                print(f"[AutoSave] {tab} Sheets ❌ {res.get('error','')}")
        except Exception as e:
            print(f"[AutoSave] {agent_id} Sheets error: {e}")

    def _save_drive():
        """สร้าง Drive file สำหรับงานชิ้นใหญ่"""
        try:
            from datetime import datetime
            import pytz
            BANGKOK = pytz.timezone("Asia/Bangkok")
            now     = datetime.now(BANGKOK)
            ts      = now.strftime("%Y%m%d_%H%M")
            slug    = _slugify(task, 35)
            filename = f"{agent_id.capitalize()}_{ts}_{slug}.txt"

            # Header + content
            content = (
                f"=== {agent_id.upper()} Report ===\n"
                f"วันที่: {now.strftime('%Y-%m-%d %H:%M น.')}\n"
                f"งาน: {task}\n"
                f"{'='*50}\n\n"
                f"{result}"
            )

            res = _try_create_real_drive_file(
                filename=filename,
                content=content,
                folder_id=DEFAULT_FOLDER_ID,
                agent_id=agent_id
            )
            if res:
                print(f"[AutoDrive] {agent_id.capitalize()} Drive ✅ ({filename})")
            else:
                print(f"[AutoDrive] {agent_id.capitalize()} Drive ⚠️ (fallback to Sheets only)")
        except Exception as e:
            print(f"[AutoDrive] {agent_id} error: {e}")

    # ── เริ่ม Sheets save เสมอ ──────────────────────────────────
    threading.Thread(target=_save_sheets, daemon=True,
                     name=f"save-sheets-{agent_id}").start()

    # ── เริ่ม Drive save เฉพาะงานชิ้นใหญ่ ──────────────────────
    if AUTO_DRIVE_ENABLED and len(result) >= AUTO_DRIVE_THRESHOLD:
        threading.Thread(target=_save_drive, daemon=True,
                         name=f"save-drive-{agent_id}").start()
