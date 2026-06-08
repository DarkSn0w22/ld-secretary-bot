"""
Agent Save Tools — Shared สำหรับทุก agent
==========================================
ให้ทุก agent สามารถ:
  1. write_to_sheets  — บันทึกรายงานลง Google Sheets
  2. create_drive_file — สร้างไฟล์งานใน Google Drive (stored in Sheets)

วิธีใช้ใน agent file:
    from agent_save_tools import SAVE_TOOLS, execute_save_tool, auto_save

    AGENT_TOOLS = [...existing tools...] + SAVE_TOOLS

    def execute_agent_tool(name, inputs):
        result = execute_save_tool(name, inputs, agent_id="atlas")
        if result is not None:
            return result
        # ...existing handlers...
"""

import threading
from agent_log import log_agent

# ── Tool definitions (เพิ่มใน TOOLS list ของแต่ละ agent) ──────────────────────

SAVE_TOOLS = [
    {
        "name": "write_to_sheets",
        "description": (
            "บันทึกรายงาน ผลการวิเคราะห์ หรือข้อมูลสำคัญลง Google Sheets (OWNDAYS AI Reports) "
            "ใช้เมื่อต้องการเก็บผลงานให้ Peanut อ่านภายหลัง หรือเมื่อทำงานชิ้นสำคัญเสร็จ"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "หัวเรื่องรายงาน เช่น 'Sales Analysis Week 22', 'Training Gap Report Jun 2026'"
                },
                "content": {
                    "type": "string",
                    "description": "เนื้อหาทั้งหมดที่ต้องการบันทึก"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "create_drive_file",
        "description": (
            "สร้างไฟล์งานใหม่ใน Google Drive ของ OWNDAYS L&D AI "
            "ใช้เมื่อต้องการสร้าง action plan, proposal, training plan, หรือเอกสารที่ต้องแชร์"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "ชื่อไฟล์ เช่น 'Action_Plan_Branch_WN_Jun2026.txt', 'Q3_Training_Plan.txt'"
                },
                "content": {
                    "type": "string",
                    "description": "เนื้อหาทั้งหมดของไฟล์"
                },
                "category": {
                    "type": "string",
                    "description": "หมวดหมู่ เช่น 'action_plans', 'training', 'reports', 'proposals' (ใช้เป็นชื่อ Sheets tab)",
                    "default": "reports"
                }
            },
            "required": ["filename", "content"]
        }
    }
]


# ── Handler ───────────────────────────────────────────────────────────────────

def execute_save_tool(tool_name: str, tool_input: dict,
                      agent_id: str = "agent") -> str | None:
    """
    จัดการ write_to_sheets และ create_drive_file
    คืน string ถ้า tool match, คืน None ถ้าไม่ใช่ tool ของโมดูลนี้

    Args:
        tool_name  ชื่อ tool จาก Claude
        tool_input inputs ที่ Claude ส่งมา
        agent_id   ชื่อ agent ที่เรียก (ใช้เป็น tab name fallback)
    """
    if tool_name == "write_to_sheets":
        return _write_to_sheets(tool_input, agent_id)
    elif tool_name == "create_drive_file":
        return _create_drive_file(tool_input, agent_id)
    return None   # ไม่ใช่ tool ของโมดูลนี้


def _write_to_sheets(inputs: dict, agent_id: str) -> str:
    title   = inputs.get("title", "รายงาน")
    content = inputs.get("content", "")
    tab     = agent_id.capitalize()   # e.g. Atlas, Pulse, Rex

    try:
        from drive_api import save_report
        res = save_report(tab, title, content)
        if res.get("ok"):
            url = res.get("url", "")
            log_agent(agent_id, "sheets", f"saved: {title[:80]}", url)
            return (f"✅ บันทึกลง Google Sheets สำเร็จครับ\n"
                    f"Tab: {res.get('tab','?')} | {title}\n"
                    f"Link: {url}")
        else:
            err = res.get("error", "unknown")
            log_agent(agent_id, "sheets", "save FAILED", err, status="error")
            return f"❌ บันทึก Sheets ไม่สำเร็จ: {err}"
    except Exception as e:
        return f"❌ write_to_sheets error: {e}"


def _create_drive_file(inputs: dict, agent_id: str) -> str:
    filename = inputs.get("filename", "report.txt")
    content  = inputs.get("content", "")
    category = inputs.get("category", "reports")
    tab      = category.replace(" ", "_").capitalize()   # e.g. Action_plans, Training

    # เก็บใน Sheets ก่อน (Drive API quota issue)
    # header เพิ่มข้อมูล filename ไว้
    full_content = f"=== {filename} ===\n\n{content}"

    try:
        from drive_api import save_report
        res = save_report(tab, filename, full_content)
        if res.get("ok"):
            url = res.get("url", "")
            log_agent(agent_id, "drive", f"file: {filename}", url)
            return (f"✅ สร้างไฟล์ '{filename}' สำเร็จครับ\n"
                    f"บันทึกใน Sheets tab: {res.get('tab','?')}\n"
                    f"Link: {url}")
        else:
            err = res.get("error", "unknown")
            return f"❌ สร้างไฟล์ไม่สำเร็จ: {err}"
    except Exception as e:
        return f"❌ create_drive_file error: {e}"


# ── Auto-save helper (เรียกหลัง agent เสร็จงาน) ─────────────────────────────

def auto_save(agent_id: str, task: str, result: str) -> None:
    """
    บันทึก agent result ลง Sheets แบบ background (ไม่บล็อก)
    เรียกจากท้าย run_* function ของแต่ละ agent
    """
    if not result or len(result) < 40:
        return   # ผลสั้นเกินไป ไม่คุ้มบันทึก

    def _save():
        try:
            from drive_api import save_report
            tab = agent_id.capitalize()
            res = save_report(tab, task[:150], result)
            if res.get("ok"):
                print(f"[AutoSave] {tab} ✅")
            else:
                print(f"[AutoSave] {tab} ❌ {res.get('error','')}")
        except Exception as e:
            print(f"[AutoSave] {agent_id} error: {e}")

    threading.Thread(target=_save, daemon=True, name=f"save-{agent_id}").start()
