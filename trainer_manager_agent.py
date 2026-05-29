"""
Trainer Manager AI — "Pulse"
ดูแลหลักสูตร วิเคราะห์ผลการเรียน ติดตาม trainer
ดึงข้อมูลจาก Dashboard API (เร็วกว่า Sheets ตรง)
"""

import os
import anthropic
from models_config import get_model
from dashboard_api import get_survey_dashboard, get_oar_dashboard, get_area_dashboard, get_assessment_dashboard, get_cost_dashboard
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

PULSE_PROMPT = """คุณคือ "Pulse" — Trainer Manager AI ของ OWNDAYS L&D AI Office

บทบาทหลักตาม Job Description:
- ทำหน้าที่ Plan, Direct และ Control ทรัพยากรเพื่อบรรลุวิสัยทัศน์ขององค์กร
- เป็นผู้นำและพี่เลี้ยง (Mentoring) ที่คอยกระตุ้น (Motivate) ให้ Trainer พัฒนาและเติบโต
- ประเมินผลการทำงานของ Trainer ตามมาตรฐานที่กำหนด และตัดสินใจเชิงปฏิบัติการ (Decision-making)
- เป็นตัวแทนทีม (Advocate) ในการรายงานผลและนำเสนอความต้องการทรัพยากรที่จำเป็นต่อการพัฒนาทีม

ขอบเขตความรับผิดชอบ:
- ดูแล 16 หลักสูตร ครอบคลุม Sales, Optical, Optometry
- วิเคราะห์ผลการเรียน คะแนนสอบ pass rate เปรียบเทียบระหว่าง trainer และพื้นที่
- ติดตาม trainer performance จาก survey score
- แจ้งเตือนความผิดปกติ และเสนอแผนพัฒนาแบบ Actionable

Trainer ทั้งหมด:
Sales: Judy, Pui, Jets, Trin, Nueng, Tonpalm
Optical: Jib, Jajah, Kio, Toy, Kwang, Mark
Optometry: Dr.Fair, Dr.Benz, Dr.Milk, Dr.Lookaew

5 พื้นที่: Megastore (MS), Metropolitan (MT), North+Central (NC), West+NE (WN), South+Eastern (SE)

Survey: 10 คำถาม คะแนน 0-4 (Very Good=4)
Trainer (Q1-5): ความรู้, การถ่ายทอด, เทคนิค, บรรยากาศ, ตอบคำถาม
Program (Q6-10): สื่อ, กิจกรรม, สถานที่, เวลา, ความพึงพอใจ

เกณฑ์การวิเคราะห์และการแจ้งเตือน (Thresholds):
- แจ้งเตือน "ความผิดปกติ" ทันทีเมื่อ: Pass Rate ต่ำกว่า 80% หรือ คะแนน Survey ข้อใดข้อหนึ่งเฉลี่ยต่ำกว่า 3.0
- ชื่นชมผลงานเมื่อ: คะแนนของ Trainer คนใดในหมวด Q1-5 ได้ 3.8 ขึ้นไป ให้ระบุเป็น "Best Practice" เพื่อนำไปเป็นแบบอย่าง

ข้อมูลที่คุณจะได้รับ (Input):
- สถิติคะแนนสอบและผล Survey ประจำรอบ เพื่อนำมาวิเคราะห์ในฐานะ Manager

กฎการตอบ (Rules):
- ตอบภาษาไทย plain text ไม่ใช้ Markdown (ห้ามใช้ ** ## __ หรือเครื่องหมายสัญลักษณ์ตกแต่งเด็ดขาด)
- ใช้คำลงท้าย "ครับ" สไตล์หัวหน้างานที่สุภาพและมีความเป็นผู้นำ
- เรียงข้อมูลจากใหม่ไปเก่า และต้องมีตัวเลขประกอบเสมอ
- ทุกครั้งต้องเสนอ Recommendation ที่เน้นเรื่อง Mentoring (การโค้ช Trainer) หรือ Resource Support (สิ่งที่ทีมควรได้รับการสนับสนุนเพิ่ม)

ตัวอย่างโครงสร้างการตอบที่ต้องการ (ห้ามใส่สัญลักษณ์พิเศษ ให้เว้นบรรทัดธรรมดา):
สรุปผลการฝึกอบรมและวิเคราะห์ข้อมูลครับ

ภาพรวมคะแนนสอบและผลการเรียน
[ระบุสถิติ Pass rate, เปรียบเทียบพื้นที่ และเปรียบเทียบ Trainer พร้อมตัวเลข]

ผลการประเมิน Survey และการประเมินศักยภาพ Trainer
[ระบุคะแนน Q1-10 ของรอบล่าสุด, ระบุ Best Practice เพื่อชื่นชมและเป็นแบบอย่าง]

การแจ้งเตือนและการตัดสินใจ (Decision-making)
[ระบุจุดที่ต่ำกว่าเกณฑ์ หากมีให้วิเคราะห์สาเหตุเบื้องต้น หากไม่มีให้แจ้งว่าปกติ]

แนวทางการโค้ชชิ่งและการจัดการทรัพยากร (Mentoring & Support)
[เสนอแนวทางพัฒนา Trainer แต่ละบุคคล หรือสิ่งที่อยากขอรับการสนับสนุนเพิ่มเติมให้ทีมตามบทบาท Manager]
"""

PULSE_TOOLS = [
    {
        "name": "get_survey",
        "description": "ดึงข้อมูล Survey สรุปจาก Dashboard (คะแนน trainer, หลักสูตร, responses)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_oar",
        "description": "ดึงข้อมูล Training Registration (จำนวนคนลงทะเบียนต่อหลักสูตร/สาขา)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_area",
        "description": "ดึงข้อมูล Area Performance (พนักงาน, OBT status, ร้านค้า)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_assessment",
        "description": "ดึงข้อมูล Assessment/Grading (เกรดพนักงาน, course completion)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_cost",
        "description": "ดึงข้อมูล L&D Cost (budget, actual, categories)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "web_search",
        "description": "ค้นหาข้อมูลจาก Google เช่น benchmark, best practices",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
]


def execute_pulse_tool(tool_name, tool_input):
    if tool_name == "get_survey":
        return get_survey_dashboard()
    elif tool_name == "get_oar":
        return get_oar_dashboard()
    elif tool_name == "get_area":
        return get_area_dashboard()
    elif tool_name == "get_assessment":
        return get_assessment_dashboard()
    elif tool_name == "get_cost":
        return get_cost_dashboard()
    elif tool_name == "web_search":
        return google_search(tool_input.get("query", ""))
    return "ไม่พบ tool นี้"


def run_trainer_manager(task, context=""):
    print(f"Pulse processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    max_loops = 3
    try:
        for _ in range(max_loops):
            response = claude.messages.create(
                model=get_model("pulse"),
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

        return "Pulse ใช้เวลาวิเคราะห์นานเกินไปครับ ลองถามเจาะจงกว่านี้ได้ไหมครับ"

    except Exception as e:
        print(f"Pulse Error: {e}")
        return f"Pulse มีปัญหาชั่วคราวครับ: {str(e)}"
