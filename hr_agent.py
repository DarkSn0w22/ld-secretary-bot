"""
HR Manager AI — "People"
ดูแลข้อมูลพนักงานทุกคน จาก Employee Master Sheet
แจ้งเตือน: พนักงานใหม่/ลาออก + หมด probation
"""

import os
import anthropic
from models_config import get_model
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import base64
import requests
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

EMPLOYEE_SHEET_ID = "1FLIugt_XASi_vsP7FHdL2UVthQQDsdZpH6St3zVofMU"
EMP_INFO_URL = "https://www.od-connect.com/emp-info"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

PEOPLE_PROMPT = """คุณคือ "People" — HR Manager AI ของ OWNDAYS L&D AI Office

บทบาท:
- ดูแลข้อมูลพนักงานทุกคนใน OWNDAYS Thailand (73 สาขา, 400+ คน)
- ติดตาม lifecycle พนักงาน: เข้าใหม่, probation, confirm, ลาออก
- วิเคราะห์ข้อมูล headcount, turnover, การกระจายตัวตามสาขา/พื้นที่
- เชื่อมโยงข้อมูล HR กับ L&D เช่น ใครยังไม่ผ่าน OBT, ใครควรได้รับ training
- รายงาน HR insights ให้ Peanut ตัดสินใจได้เร็วขึ้น

ข้อมูลใน Employee Master Sheet:
- Sheet "Employee": พนักงานปัจจุบันทั้งหมด
- Sheet "HQ": ทีม HQ และ L&D
- Sheet "Resigned employee": พนักงานที่ลาออกแล้ว
- Sheet "Training": ประวัติการฝึกอบรม
- Sheet "Assessment": ผลการประเมิน
- Sheet "OAR log": บันทึกการลงทะเบียน On-the-job

5 พื้นที่: Megastore, Metropolitan, North+Central, West+NE, South+Eastern
Trainer teams: Judy/Pui/Jets/Trin/Nueng/Tonpalm (Sales), Jib/Jajah/Kio/Toy/Kwang/Mark (Optical), Dr.Fair/Dr.Benz/Dr.Milk/Dr.Lookaew (Optometry)

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- ใส่ตัวเลขจริงทุกครั้ง
- แจ้ง action ที่ควรทำเสมอ
- Probation ปกติ 119 วัน (ประมาณ 4 เดือน) ตามกฎหมายแรงงานไทย
"""

PEOPLE_TOOLS = [
    {
        "name": "get_all_employees",
        "description": "ดึงข้อมูลพนักงานทั้งหมดจาก Employee sheet",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_resigned_employees",
        "description": "ดึงรายชื่อพนักงานที่ลาออกแล้ว",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_training_records",
        "description": "ดึงประวัติการฝึกอบรมและ assessment ของพนักงาน",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_name": {"type": "string", "description": "ชื่อพนักงาน (ถ้าต้องการเฉพาะคน)"}
            },
            "required": []
        }
    },
    {
        "name": "check_probation_expiry",
        "description": "ตรวจสอบพนักงานที่กำลังจะหมดอายุ probation ใน 7-30 วันข้างหน้า",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "จำนวนวันล่วงหน้าที่ต้องการตรวจ (default 30)"}
            },
            "required": []
        }
    },
    {
        "name": "search_employee",
        "description": "ค้นหาพนักงานด้วยชื่อ, สาขา, หรือตำแหน่ง",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "คำค้นหา"}
            },
            "required": ["keyword"]
        }
    }
]


def get_gspread_client():
    """สร้าง gspread client จาก env var"""
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_b64:
        raise ValueError("GOOGLE_CREDENTIALS_JSON not set")
    creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet_data(sheet_name: str) -> list:
    """ดึงข้อมูลจาก sheet ที่ระบุ"""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(EMPLOYEE_SHEET_ID)
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records()
        return records
    except Exception as e:
        print(f"Sheet error ({sheet_name}): {e}")
        return []


def format_employees_summary(employees: list) -> str:
    """สรุปข้อมูลพนักงานเป็น text"""
    if not employees:
        return "ไม่พบข้อมูลพนักงาน"

    total = len(employees)
    # นับตาม area ถ้ามี column นั้น
    areas = {}
    probation = []
    today = datetime.now()

    for emp in employees:
        # Area
        area = emp.get("Area", emp.get("area", emp.get("พื้นที่", "Unknown")))
        areas[area] = areas.get(area, 0) + 1

        # Probation check - หา start date
        start_date_str = emp.get("Start Date", emp.get("start_date", emp.get("วันเริ่มงาน", "")))
        if start_date_str:
            try:
                # รองรับหลายรูปแบบ
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
                    try:
                        start_date = datetime.strptime(str(start_date_str), fmt)
                        probation_end = start_date + timedelta(days=119)
                        days_left = (probation_end - today).days
                        confirmed = emp.get("Confirmed", emp.get("confirmed", emp.get("ผ่าน Probation", "")))
                        if 0 <= days_left <= 30 and not confirmed:
                            name = emp.get("Name", emp.get("name", emp.get("ชื่อ", "Unknown")))
                            branch = emp.get("Branch", emp.get("branch", emp.get("สาขา", "")))
                            probation.append({
                                "name": name, "branch": branch,
                                "days_left": days_left,
                                "end_date": probation_end.strftime("%d/%m/%Y")
                            })
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

    summary = f"พนักงานทั้งหมด: {total} คน\n\n"
    if areas:
        summary += "แยกตามพื้นที่:\n"
        for area, count in sorted(areas.items()):
            summary += f"  {area}: {count} คน\n"

    if probation:
        summary += f"\n⚠️ หมด probation ใน 30 วัน: {len(probation)} คน\n"
        for p in probation[:10]:
            summary += f"  - {p['name']} ({p['branch']}) วันที่ {p['end_date']} เหลือ {p['days_left']} วัน\n"

    return summary


def push_line_message(text: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"to": PEANUT_USER_ID, "messages": [{"type": "text", "text": text[:5000]}]}
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"People push error: {e}")


def execute_people_tool(tool_name, tool_input):
    if tool_name == "get_all_employees":
        employees = get_sheet_data("Employee")
        return format_employees_summary(employees)

    elif tool_name == "get_resigned_employees":
        resigned = get_sheet_data("Resigned employee")
        if not resigned:
            return "ไม่พบข้อมูลพนักงานที่ลาออก"
        return f"พนักงานที่ลาออกแล้ว: {len(resigned)} คน\n" + \
               "\n".join([f"- {r.get('Name', r.get('ชื่อ', 'Unknown'))} "
                          f"({r.get('Branch', r.get('สาขา', ''))}) "
                          f"ลาออก: {r.get('Resign Date', r.get('วันลาออก', ''))}"
                          for r in resigned[:20]])

    elif tool_name == "get_training_records":
        name = tool_input.get("employee_name", "")
        training = get_sheet_data("Training")
        assess = get_sheet_data("Assessment")
        if name:
            training = [r for r in training if name.lower() in str(r.get("Name", "")).lower()]
            assess = [r for r in assess if name.lower() in str(r.get("Name", "")).lower()]
        return (f"Training records: {len(training)} รายการ\n"
                f"Assessment records: {len(assess)} รายการ\n"
                + json.dumps(training[:10], ensure_ascii=False))

    elif tool_name == "check_probation_expiry":
        days = tool_input.get("days_ahead", 30)
        employees = get_sheet_data("Employee")
        today = datetime.now()
        expiring = []
        for emp in employees:
            start_str = emp.get("Start Date", emp.get("start_date", emp.get("วันเริ่มงาน", "")))
            if not start_str:
                continue
            try:
                for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
                    try:
                        start = datetime.strptime(str(start_str), fmt)
                        end = start + timedelta(days=119)
                        left = (end - today).days
                        confirmed = emp.get("Confirmed", emp.get("confirmed", ""))
                        if 0 <= left <= days and not confirmed:
                            expiring.append({
                                "name": emp.get("Name", emp.get("ชื่อ", "?")),
                                "branch": emp.get("Branch", emp.get("สาขา", "")),
                                "position": emp.get("Position", emp.get("ตำแหน่ง", "")),
                                "days_left": left,
                                "end_date": end.strftime("%d/%m/%Y")
                            })
                        break
                    except ValueError:
                        continue
            except Exception:
                continue
        if not expiring:
            return f"ไม่มีพนักงานหมด probation ใน {days} วันข้างหน้า"
        result = f"พนักงานหมด probation ใน {days} วัน: {len(expiring)} คน\n\n"
        for e in expiring:
            result += (f"👤 {e['name']} | {e['position']}\n"
                       f"   สาขา: {e['branch']}\n"
                       f"   หมด probation: {e['end_date']} (อีก {e['days_left']} วัน)\n\n")
        return result

    elif tool_name == "search_employee":
        kw = tool_input.get("keyword", "").lower()
        employees = get_sheet_data("Employee")
        found = [e for e in employees if any(
            kw in str(v).lower() for v in e.values()
        )]
        if not found:
            return f"ไม่พบพนักงานที่ตรงกับ '{kw}'"
        return f"พบ {len(found)} คน:\n" + "\n".join([
            f"- {e.get('Name', e.get('ชื่อ', '?'))} | {e.get('Position', '')} | {e.get('Branch', '')}"
            for e in found[:15]
        ])

    return "ไม่พบ tool นี้"


def run_hr_manager(task, context=""):
    """รัน People วิเคราะห์ข้อมูล HR"""
    print(f"People processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        for _ in range(4):
            response = claude.messages.create(
                model=get_model("people"),
                max_tokens=2048,
                system=PEOPLE_PROMPT,
                tools=PEOPLE_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"People using tool: {block.name}")
                        result = execute_people_tool(block.name, block.input)
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
            print("People completed")
            return final_text

        return "People ใช้เวลานานเกินไปครับ ลองถามใหม่แบบเจาะจงกว่านี้"

    except Exception as e:
        print(f"People Error: {e}")
        return f"People มีปัญหาชั่วคราวครับ: {str(e)}"


def get_probation_summary_text() -> str:
    """คืน probation status เป็น text — สำหรับ consolidated morning report"""
    try:
        from datetime import date, timedelta
        from sheets_tools import get_oar_summary
        # reuse logic จาก check_probation_alerts แต่คืน text แทน push LINE
        result = check_probation_alerts(return_text=True)
        return result if result else "ไม่มีพนักงานหมด probation ใน 7 วันครับ"
    except Exception as e:
        return f"ดึงข้อมูลไม่ได้: {e}"


def check_probation_alerts(return_text: bool = False):
    """เช็ค probation ที่จะหมดใน 7 วัน — รันทุกวัน"""
    print("People checking probation expiry...")
    employees = get_sheet_data("Employee")
    today = datetime.now()
    expiring_soon = []

    for emp in employees:
        start_str = emp.get("Start Date", emp.get("start_date", emp.get("วันเริ่มงาน", "")))
        if not start_str:
            continue
        try:
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
                try:
                    start = datetime.strptime(str(start_str), fmt)
                    end = start + timedelta(days=119)
                    left = (end - today).days
                    confirmed = emp.get("Confirmed", emp.get("confirmed", ""))
                    if 0 <= left <= 7 and not confirmed:
                        expiring_soon.append({
                            "name": emp.get("Name", emp.get("ชื่อ", "?")),
                            "branch": emp.get("Branch", emp.get("สาขา", "")),
                            "position": emp.get("Position", emp.get("ตำแหน่ง", "")),
                            "days_left": left,
                            "end_date": end.strftime("%d/%m/%Y")
                        })
                    break
                except ValueError:
                    continue
        except Exception:
            continue

    if expiring_soon:
        msg = f"⚠️ พนักงานหมด probation ใน 7 วัน: {len(expiring_soon)} คน\n"
        for e in expiring_soon:
            msg += (f"👤 {e['name']} | {e['position']}\n"
                    f"   สาขา: {e['branch']}\n"
                    f"   หมด: {e['end_date']} (อีก {e['days_left']} วัน)\n")
        msg += "กรุณา confirm หรือ terminate ครับ"
        if return_text:
            return msg
        push_line_message("⚠️ แจ้งเตือน Probation จาก People\n\n" + msg)
        print(f"People: {len(expiring_soon)} probation alerts sent")
    else:
        print("People: No probation expiring in 7 days")
        if return_text:
            return "ไม่มีพนักงานหมด probation ใน 7 วันครับ"
