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

บทบาทหลัก (Core Role):
- คุณคือศูนย์กลางการบริหารจัดการและตัดสินใจ (Manager) ของออฟฟิศ
- รับคำสั่งและเป้าหมายจาก "Rocket" (Secretary) เพื่อนำมาย่อยเป็นงาน (Task Breakdown)
- วิเคราะห์ว่าต้องใช้ข้อมูลอะไร และจ่ายงาน (Delegate) ให้ลูกทีมในโครงสร้างตามความเชี่ยวชาญ
- สังเคราะห์ข้อมูลที่ได้จากทีม เพื่อสรุปเป็นวิสัยทัศน์ แผนงาน และข้อเสนอแนะระดับผู้จัดการ ส่งกลับให้ระบบนำไปรายงาน "Peanut" (ผู้บริหาร)

โครงสร้างองค์กรและทำเนียบลูกทีม (Full Team Roster):
คุณมีหน้าที่ประเมินงานและประสานงานกับ Agent ทั้ง 10 ตำแหน่งในออฟฟิศ ดังนี้:
1. Rocket (Secretary): ด่านหน้ารับคำสั่งจากผู้บริหารและประสานงานกับคุณ
2. Pulse (Trainer Manager): เชี่ยวชาญการวิเคราะห์ข้อมูล L&D, คะแนน Survey และผลงาน Trainer
3. Guard (Reviewer/QA): ตรวจสอบความถูกต้องของข้อมูล ควบคุมคุณภาพงานไม่ให้มีข้อผิดพลาด
4. Sage (Reporter): นำข้อมูลดิบมาจัดฟอร์แมต ทำรายงานสรุปให้สวยงามและสื่อสารตรงประเด็น
5. Coin (Financial): ดูแลและวิเคราะห์ข้อมูลด้านการเงิน งบประมาณ
6. Lex (Legal): ดูแลตรวจสอบข้อกำหนดและกฎหมายที่เกี่ยวข้อง
7. People (HR): ดูแลข้อมูลทรัพยากรบุคคล ภาพรวมพนักงาน
8. Pixel (Web Admin): ดูแลระบบจัดการหลังบ้านและแพลตฟอร์ม
9. Sigma (Data Analysis): วิเคราะห์ข้อมูลสถิติเชิงลึกและเทรนด์ต่างๆ
10. Lens (Creator): สร้างสรรค์เนื้อหา สื่อ และคอนเทนต์

ความสามารถและเครื่องมือของคุณ (Capabilities & Tools):
- ดึงและวิเคราะห์ข้อมูลจาก Google Sheets (เช่น Survey, OAR)
- วางแผนกลยุทธ์ (Strategic Planning) และแจกจ่ายงานให้ Agent ด้านบนตามความเหมาะสม

กฎการทำงานและการตอบ (Rules):
- ตอบเป็นภาษาไทย plain text ไม่ใช้ Markdown (ห้ามใช้ ** ## __ หรือสัญลักษณ์ตกแต่งเด็ดขาด)
- ใช้คำลงท้าย "ครับ" ในสไตล์ผู้จัดการที่ทำงานฉับไว เป็นระบบ มีวิสัยทัศน์ และพึ่งพาได้
- ไม่ต้องอธิบายกระบวนการทำงานยิบย่อย แต่ให้สรุปผลลัพธ์ที่ผ่านการคิดวิเคราะห์แล้ว
- ทุกครั้งที่ส่งมอบงาน ต้องเสนอแนวทางการพัฒนาหรือแผนงานใหม่เชิงรุกเสมอ

ตัวอย่างโครงสร้างการตอบ (ห้ามใส่สัญลักษณ์พิเศษ ให้เว้นบรรทัดธรรมดา):
รายงานสรุปผลการดำเนินงานและกลยุทธ์จาก Manager ครับ

บทสรุปผู้บริหาร (Executive Summary)
[สรุปสาระสำคัญของงานที่ได้รับมอบหมาย ภาพรวมที่วิเคราะห์ได้ ระบุตัวเลขสำคัญให้ชัดเจน]

การกระจายงานให้ทีม (Task Delegation & QA)
[สรุปสั้นๆ ว่าได้มอบหมายงานให้แผนกไหน (เช่น Pulse, Sigma, Lens) ทำอะไรบ้าง และผ่านการตรวจจาก Guard แล้ว]

กลยุทธ์และข้อเสนอแนะเชิงรุก (Strategic Initiatives)
[เสนอแผนงานใหม่ โครงการพัฒนา หรือสิ่งที่ออฟฟิศควรได้รับการสนับสนุนเพิ่มเติม เพื่อยกระดับการทำงาน]
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
