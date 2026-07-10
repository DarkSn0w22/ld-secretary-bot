"""
Dashboard Guardian AI — "Guardian"
เฝ้าดู L&D Dashboard (Google Apps Script Web App) ทุกสัปดาห์ (จันทร์ 13:00)
ตรวจทุก action (survey/cost/asset/oar/area/assessment) ว่า error ไหม หรือโครงสร้างข้อมูลเปลี่ยนไปจากรอบก่อนไหม
แจ้ง Peanut ทาง LINE เสมอ + Microsoft Teams ถ้าตั้งค่า TEAMS_WEBHOOK_URL ไว้ และเซฟรายงานลง Sheets
(pattern เดียวกับ weekly_meeting.py / friday_review.py — LINE push + drive_api.save_report + agent_log)
"""

import os
import json
import hashlib
import requests
import anthropic
from models_config import get_model
from dashboard_api import fetch_dashboard
from agent_log import log_agent

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

WATCHED_ACTIONS = ["ping", "survey", "cost", "asset", "oar", "area", "assessment"]
SNAPSHOT_PATH = "/tmp/.guardian_dashboard_snapshot.json"  # เหมือน pattern ของ historical_memory.py

GUARDIAN_PROMPT = """คุณคือ "Guardian" — ผู้เฝ้าระวัง L&D Dashboard ของ OWNDAYS L&D AI Office

บทบาท:
- เฝ้าดู Dashboard API (Google Apps Script Web App) ที่เลี้ยงทั้งหน้าเว็บ Dashboard และบอทตัวนี้
- ตรวจทุก action: survey, cost, asset, oar, area, assessment
- ถ้าเจอ error หรือโครงสร้างข้อมูลเปลี่ยนแปลงกะทันหัน จะสรุปแจ้ง Peanut (Regional L&D Manager) ทันที
  ทั้งทาง LINE และ Microsoft Teams (ถ้าตั้งค่าไว้)
- เวลามีคนถามสถานะสด ให้เรียก tool check_health แล้วรายงานตามจริง ห้ามเดา

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- รายงานตัวเลข/action ที่มีปัญหาแบบเจาะจง ห้ามพูดกว้างๆ
"""

GUARDIAN_TOOLS = [
    {
        "name": "check_health",
        "description": "ตรวจสุขภาพ Dashboard API ทุก action ตอนนี้ทันที (สด ไม่ใช้แคช)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "send_test_notification",
        "description": "ส่งข้อความทดสอบไปยัง LINE และ Microsoft Teams (ถ้าตั้งค่า TEAMS_WEBHOOK_URL ไว้) เพื่อเช็คว่าต่อถูกจริงไหม",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    }
]


def _load_snapshots() -> dict:
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_snapshots(snap: dict):
    """atomic write เหมือน pattern ของ historical_memory.py"""
    try:
        tmp_path = SNAPSHOT_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp_path, SNAPSHOT_PATH)
    except Exception as e:
        print(f"[Guardian] save snapshot error: {e}")


def _signature(payload: dict):
    """คืน (payload_hash, keys_json) — keys_json คือรายชื่อ field ระดับบนสุด ใช้เทียบว่าโครงสร้างเปลี่ยนไหม"""
    keys = sorted([k for k in payload.keys() if k not in ("status", "timestamp", "year")])
    keys_json = json.dumps(keys, ensure_ascii=False)
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload_hash, keys_json


def check_dashboard_health(force_report: bool = False) -> str:
    """
    ตรวจทุก action ของ Dashboard API
    - force_report=False: คืน "" ถ้าไม่มีอะไรเปลี่ยน, คืนสรุปปัญหาเป็น text ถ้ามี
    - force_report=True (weekly digest / tool แบบโต้ตอบ): คืนสถานะปัจจุบันของทุก action เสมอ
    """
    snapshots = _load_snapshots()
    issues = []
    status_lines = []

    for action in WATCHED_ACTIONS:
        try:
            payload = fetch_dashboard(action)
        except Exception as e:
            issues.append(f"❌ {action}: เรียก API ไม่สำเร็จ ({e})")
            status_lines.append(f"❌ {action}: เรียกไม่สำเร็จ")
            continue

        status = payload.get("status", "unknown")
        payload_hash, keys_json = _signature(payload)
        last = snapshots.get(action)

        if status == "error":
            issues.append(f"❌ {action}: {payload.get('message', 'unknown error')}")
        elif last is not None:
            if last.get("status") == "error":
                issues.append(f"✅ {action}: กลับมาใช้งานได้แล้ว (รอบก่อนเจอ error)")
            elif last.get("keys_json") != keys_json:
                issues.append(
                    f"⚠️ {action}: โครงสร้างข้อมูลเปลี่ยนไปจากเดิม\n"
                    f"   เดิม: {last.get('keys_json')}\n   ใหม่: {keys_json}"
                )

        status_lines.append(f"{'✅' if status == 'success' else '❌'} {action}: {status}")

        # อัปเดต baseline เฉพาะตอนสำเร็จ (หรือยังไม่มี baseline) — ไม่ให้ error ชั่วคราวไปทับ baseline ที่ดี
        if status == "success" or last is None:
            snapshots[action] = {"hash": payload_hash, "keys_json": keys_json, "status": status}
        else:
            snapshots[action]["status"] = status

    _save_snapshots(snapshots)

    if force_report:
        header = "📋 Guardian — Dashboard Health Check (รายสัปดาห์)\n\n"
        body = "\n".join(status_lines)
        tail = ("\n\n" + "\n".join(issues)) if issues else "\n\nไม่พบปัญหาครับ ✅"
        return header + body + tail

    if not issues:
        return ""
    return "🚨 Guardian แจ้งเตือนจาก L&D Dashboard\n\n" + "\n".join(issues)


def _notify_teams(text: str):
    if not TEAMS_WEBHOOK_URL:
        print("[Guardian] TEAMS_WEBHOOK_URL not set, skip Teams notify")
        return
    try:
        requests.post(TEAMS_WEBHOOK_URL, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"[Guardian] Teams push error: {e}")


def notify_all(text: str):
    """LINE เสมอ (ผ่าน scheduler.push_message ตัวเดิมที่ agent อื่นใช้) + Teams ถ้าตั้งค่าไว้"""
    from scheduler import push_message  # lazy import กัน circular import กับ scheduler.py
    push_message(text)
    _notify_teams(text)


def run_weekly_check(user_id=None):
    """เรียกจาก scheduler.py ทุกวันจันทร์ 13:00 — ตรวจ + แจ้งเสมอ + เซฟ Sheets (เหมือน weekly_meeting/friday_review)"""
    print("[Guardian] Running weekly dashboard health check...")
    summary = check_dashboard_health(force_report=True)
    notify_all(summary)
    log_agent("scheduler", "guardian", "[weekly-check]", summary[:400], status="ok")

    try:
        from drive_api import save_report
        save_report("guardian", "Weekly Dashboard Health Check", summary)
    except Exception as e:
        print(f"[Guardian] save_report error: {e}")

    print("[Guardian] Weekly check completed ✓")


def execute_guardian_tool(tool_name, tool_input):
    if tool_name == "check_health":
        return check_dashboard_health(force_report=True)
    elif tool_name == "send_test_notification":
        test_msg = ("🔔 Guardian test notification\n"
                     "ถ้าเห็นข้อความนี้ทั้งใน LINE และ Teams แสดงว่าต่อ webhook ถูกทั้งคู่ครับ")
        notify_all(test_msg)
        teams_state = "ตั้งค่า TEAMS_WEBHOOK_URL ไว้แล้ว ส่งไปด้วย" if TEAMS_WEBHOOK_URL else "ยังไม่ได้ตั้งค่า TEAMS_WEBHOOK_URL เลยส่งแค่ LINE"
        return f"ส่ง test notification แล้วครับ — LINE: ส่งแล้ว, Teams: {teams_state}"
    return "ไม่พบ tool นี้"


def run_guardian(task, context=""):
    """รัน Guardian แบบโต้ตอบ — handler สำหรับ agent_bus.register('guardian', run_guardian)"""
    print(f"Guardian processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        for _ in range(4):
            response = claude.messages.create(
                model=get_model("guardian"),
                max_tokens=1024,
                system=GUARDIAN_PROMPT,
                tools=GUARDIAN_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Guardian using tool: {block.name}")
                        result = execute_guardian_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            print("Guardian completed")
            return final_text

        return "Guardian ใช้เวลานานเกินไปครับ ลองถามใหม่แบบเจาะจงกว่านี้"

    except Exception as e:
        print(f"Guardian Error: {e}")
        return f"Guardian มีปัญหาชั่วคราวครับ: {str(e)}"
