"""
Trainer Manager AI — "Pulse"
ดูแลหลักสูตรทั้งหมด วิเคราะห์ผลการเรียน ติดตาม trainer performance
"""

import os
import anthropic
from sheets_tools import get_survey_summary, get_oar_summary, get_sheet_names, SHEET_IDS, read_sheet

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
        "name": "get_survey_data",
        "description": "ดึงข้อมูล Survey ทั้งหมด วิเคราะห์คะแนน trainer และ program",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_oar_data",
        "description": "ดึงข้อมูล Training Registration วิเคราะห์จำนวนผู้เข้าอบรมต่อหลักสูตร",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_survey_sheets",
        "description": "ดูรายชื่อ sheet ทั้งหมดใน Survey Spreadsheet (แต่ละ sheet = แต่ละหลักสูตร)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "analyze_trainer_performance",
        "description": "วิเคราะห์ performance ของ trainer แต่ละคน จาก survey score",
        "input_schema": {
            "type": "object",
            "properties": {
                "trainer_name": {
                    "type": "string",
                    "description": "ชื่อ trainer ที่ต้องการวิเคราะห์ ถ้าไม่ระบุจะวิเคราะห์ทุกคน"
                }
            },
            "required": []
        }
    },
    {
        "name": "analyze_course_performance",
        "description": "วิเคราะห์ผลการอบรมของหลักสูตรที่ระบุ",
        "input_schema": {
            "type": "object",
            "properties": {
                "course_code": {
                    "type": "string",
                    "description": "รหัสหลักสูตร เช่น BOC, MSC, SMOT"
                }
            },
            "required": ["course_code"]
        }
    }
]


def execute_pulse_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_survey_data":
        return get_survey_summary()

    elif tool_name == "get_oar_data":
        return get_oar_summary()

    elif tool_name == "get_survey_sheets":
        names = get_sheet_names(SHEET_IDS["survey"])
        if names:
            return f"หลักสูตรที่มีข้อมูล Survey ({len(names)} หลักสูตร):\n" + "\n".join(names)
        return "ไม่พบข้อมูล"

    elif tool_name == "analyze_trainer_performance":
        trainer = tool_input.get("trainer_name", "ทุกคน")
        survey_data = get_survey_summary()
        return f"ข้อมูล Survey สำหรับวิเคราะห์ trainer {trainer}:\n{survey_data}"

    elif tool_name == "analyze_course_performance":
        course = tool_input.get("course_code", "")
        # ลองดึง sheet ที่ชื่อตรงกับ course code
        sheet_names = get_sheet_names(SHEET_IDS["survey"])
        target = next((s for s in sheet_names if course.upper() in s.upper()), None)
        if target:
            data = read_sheet(SHEET_IDS["survey"], f"{target}!A1:Z50")
            if data:
                result = f"ข้อมูลหลักสูตร {course} (Sheet: {target}):\n"
                for row in data[:30]:
                    result += " | ".join(str(c) for c in row) + "\n"
                return result
        return f"ไม่พบข้อมูลหลักสูตร {course} ใน Survey Sheets"

    return "ไม่พบ tool นี้"


def run_trainer_manager(task: str, context: str = "") -> str:
    """รัน Pulse วิเคราะห์ข้อมูลหลักสูตรและ trainer"""
    print(f"Pulse processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        while True:
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
