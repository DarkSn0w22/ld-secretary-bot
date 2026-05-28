"""
Trainer Manager AI — "Pulse"
ดูแลหลักสูตรทั้งหมด วิเคราะห์ผลการเรียน ติดตาม trainer performance
"""

import os
import anthropic
from sheets_tools import get_survey_summary, get_oar_summary, get_sheet_names, SHEET_IDS
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

PULSE_PROMPT = """คุณคือ "Pulse" — Trainer Manager AI ของ OWNDAYS L&D AI Office

บทบาท:
- ดูแลและวิเคราะห์หลักสูตรทั้งหมด 16 หลักสูตร ครอบคลุม Sales, Optical, Optometry
- วิเคราะห์ผลการเรียน คะแนนสอบ pass rate เปรียบเทียบระหว่าง trainer และพื้นที่
- ติดตาม trainer performance จาก survey score และจำนวน session
- แจ้งเตือนความผิดปกติ เช่น fail rate สูง, สาขาไม่มี training นาน, trainer score ต่ำ
- เสนอแนวทางพัฒนาหลักสูตรและ trainer อยู่เสมอ
- ทำงานร่วมกับ digital transformation ผลักดันเนื้อหาขึ้น OWNDAYS Connect

ข้อมูลหลักสูตรทั้งหมด:
Hybrid: OTT, PE, BOBT, MOBT, MTOBT, SMOT, MOT
Sales: BSC, MSC, MTSC
Optical: BOC, MOC, MTOC
Optometry: BVC, MVC, MTVC
Outsource: Professional Consultative Selling

Trainer ทั้งหมด:
Sales: Judy, Pui, Jets, Trin, Nueng, Tonpalm
Optical: Jib, Jajah, Kio, Toy, Kwang, Mark
Optometry: Dr.Fair, Dr.Benz, Dr.Milk, Dr.Lookaew

5 พื้นที่: Megastore, Metropolitan, North+Central, West+NE, South+Eastern

Survey: 10 คำถาม คะแนน 0-4 (Very Good=4, Good=3, Quite Good=2, Moderate=1, Needs Improvement=0)
Trainer (Q1-5): ความรู้, การถ่ายทอด, เทคนิค, บรรยากาศ, ตอบคำถาม
Program (Q6-10): สื่อ, กิจกรรม, สถานที่, เวลา, ความพึงพอใจ

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- เรียงข้อมูลจากใหม่ไปเก่า
- ระบุตัวเลขและแหล่งข้อมูลเสมอ
- เสนอ recommendation ทุกครั้งที่วิเคราะห์เสร็จ
"""

PULSE_TOOLS = [
    {
        "name": "get_all_ld_data",
        "description": "ดึงข้อมูล Survey + OAR ทั้งหมดมาพร้อมกันในครั้งเดียว",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "web_search",
        "description": "ค้นหาข้อมูลจาก Google เช่น benchmark, best practices, trend",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "คำค้นหา"}
            },
            "required": ["query"]
        }
    }
]


def execute_pulse_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_all_ld_data":
        survey = get_survey_summary()
        oar = get_oar_summary()
        sheets = get_sheet_names(SHEET_IDS["survey"])
        sheet_list = ", ".join(sheets) if sheets else "ไม่พบ"
        return f"Survey Data:\n{survey}\n\nOAR Data:\n{oar}\n\nAvailable courses: {sheet_list}"
    elif tool_name == "web_search":
        query = tool_input.get("query", "")
        return google_search(query)
    return "ไม่พบ tool นี้"


def run_trainer_manager(task: str, context: str = "") -> str:
    """รัน Pulse วิเคราะห์ข้อมูลหลักสูตรและ trainer"""
    print(f"Pulse processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    max_loops = 3
    try:
        for loop_count in range(max_loops):
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=PULSE_PROMPT,
                tools=PULSE_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Pulse using tool: {block.name}")
                        result = execute_pulse_tool(block.name, block.input)
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

            print("Pulse completed task")
            return final_text

    except Exception as e:
        print(f"Pulse Error: {e}")
        return f"Pulse มีปัญหาชั่วคราวครับ: {str(e)}"


# Task templates
PULSE_TASKS = {
    "trainer_ranking": "จัดอันดับ trainer ทั้งหมดจากคะแนน survey สูงสุดไปต่ำสุด พร้อมระบุจุดเด่นและจุดที่ควรพัฒนา",
    "low_score_alert": "หา trainer หรือหลักสูตรที่ได้คะแนน survey ต่ำกว่า 3.0 พร้อมเสนอแนวทางแก้ไข",
    "course_summary": "สรุปภาพรวมทุกหลักสูตร ว่าหลักสูตรไหนมีคนเข้าอบรมมากสุด น้อยสุด และ survey score เป็นอย่างไร",
    "monthly_training_report": "สรุปรายงานการอบรมประจำเดือน จำนวน session, ผู้เข้าร่วม, คะแนน survey เฉลี่ย",
    "development_recommendations": "วิเคราะห์ข้อมูลทั้งหมดและเสนอ 5 แนวทางพัฒนาที่ควรทำใน quarter นี้",
}
