"""
Manager AI — Background Orchestrator
รวบรวม ประสานงาน และสั่งการ agent อื่นๆ ทั้งหมด
"""

import os
import json
import anthropic
from models_config import get_model
from dashboard_api import get_survey_dashboard, get_oar_dashboard, get_area_dashboard, get_cost_dashboard, get_all_dashboard
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

MANAGER_PROMPT = """คุณคือ "Atlas" — Manager AI ของ OWNDAYS L&D AI Office

บทบาท:
- รับ task จาก Rocket (Secretary) แล้วประสานงานกับ agent อื่น
- วิเคราะห์ว่า task ต้องใช้ข้อมูลอะไร และต้องทำขั้นตอนไหนบ้าง
- รวบรวมผลลัพธ์และสรุปให้ Rocket นำไปรายงาน Peanut
- ตอบเป็นภาษาไทย กระชับ ใช้ plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"

ความสามารถปัจจุบัน:
- ดึงข้อมูล Survey จาก Google Sheets
- ดึงข้อมูล Training Registration (OAR)
- วิเคราะห์และสรุปข้อมูล L&D
- เสนอแผนงานและ initiative ใหม่

สิ่งที่กำลังพัฒนา (agent อื่นๆ ในทีม):
- Researcher AI (ค้นหาข้อมูลอินเทอร์เน็ต)
- Trainer Manager AI (วิเคราะห์หลักสูตร)
- Creator AI (สร้างคอนเทนต์)
- Reporter AI (ส่งรายงาน)
- Financial AI, HR AI, Legal AI, Data Analysis AI, Web Admin AI

ข้อมูล OWNDAYS L&D:
- 73 สาขา, trainer 18 คน, พนักงาน 400+ คน
- 5 พื้นที่: Megastore, Metropolitan, North+Central, West+NE, South+Eastern
- 16 หลักสูตร แบ่ง Sales/Optical/Optometry/Hybrid
"""

MANAGER_TOOLS = [
    {
        "name": "web_search",
        "description": "ค้นหาข้อมูลจาก Google เช่น benchmark, best practices, trend, สถิติ",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "คำค้นหา"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_survey_data",
        "description": "ดึงข้อมูล Training Survey จาก Google Sheets",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_oar_data",
        "description": "ดึงข้อมูล Training Registration (OAR) จาก Google Sheets",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "analyze_and_recommend",
        "description": "วิเคราะห์ข้อมูลที่มีและเสนอแผนงาน/แนวทางพัฒนา",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_area": {
                    "type": "string",
                    "description": "ด้านที่ต้องการวิเคราะห์ เช่น survey, trainer, branch, course"
                }
            },
            "required": ["focus_area"]
        }
    }
]


def execute_manager_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "web_search":
        return google_search(tool_input.get("query", ""))
    elif tool_name == "get_survey_data":
        return get_survey_dashboard()
    elif tool_name == "get_oar_data":
        return get_oar_dashboard()
    elif tool_name == "analyze_and_recommend":
        focus = tool_input.get("focus_area", "general")
        return get_all_dashboard()
    return "ไม่พบ tool นี้"


def run_manager(task: str, context: str = "") -> str:
    """
    รัน Manager AI กับ task ที่ได้รับ
    คืนค่าเป็น string ผลลัพธ์
    """
    print(f"Manager AI processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        while True:
            response = claude.messages.create(
                model=get_model("atlas"),
                max_tokens=2048,
                system=MANAGER_PROMPT,
                tools=MANAGER_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Manager using tool: {block.name}")
                        result = execute_manager_tool(block.name, block.input)
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

            print(f"Manager completed task")
            return final_text

    except Exception as e:
        print(f"Manager AI Error: {e}")
        return f"Manager AI มีปัญหาชั่วคราวครับ: {str(e)}"


# =============================================================
# Task Templates — งานที่ Manager ทำได้เลย
# =============================================================

MANAGER_TASKS = {
    "monthly_report": "สรุปภาพรวม L&D ประจำเดือน ดึงข้อมูล survey และ OAR วิเคราะห์แนวโน้ม เสนอจุดที่ควรพัฒนา",
    "survey_analysis": "วิเคราะห์ผล survey ทั้งหมด หา trainer ที่ทำได้ดี/ต้องพัฒนา หาหลักสูตรที่ได้คะแนนต่ำ",
    "training_status": "สรุปสถานะการอบรมทั้งหมด ว่าหลักสูตรไหนมีคนลงทะเบียนเท่าไหร่ พื้นที่ไหนยังขาด",
    "weekly_initiative": "เสนอ 3 initiative ที่ควรทำสัปดาห์นี้ อ้างอิงจากข้อมูล survey และ OAR ล่าสุด",
}


def run_scheduled_task(task_key: str) -> str:
    """รัน task ที่กำหนดไว้ล่วงหน้า"""
    task = MANAGER_TASKS.get(task_key, task_key)
    return run_manager(task)
