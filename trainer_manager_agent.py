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
from agent_save_tools import SAVE_TOOLS, execute_save_tool, auto_save

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

Trainer ทั้งหมด (Division — ทำงาน Hybrid ตอนลง Area):
Sales:     Judy(TM Area8), Pui(Asst.TM Area4), Jets(Area5), Trin(Area1), Nueng(Area3), Tonpalm(Area2)
Optical:   Jib(TM Area6), Jajah(Asst.TM Area5), Kio(Area3), Toy(Area1), Kwang(Area2), Mark(Area4)
Optometry: Fair/Dr.Fair(Specialist Area7), Benz/Dr.Benz(Specialist Area2), Milk/Dr.Milk(Specialist Area1), Looklew/Dr.Lookaew(Specialist Area3)

โครงสร้าง 8 Areas (2026):
Area 1 (SV Mink)   L&D: Trin, Toy, Milk        10 สาขา (เหนือ+เชียงใหม่+อยุธยา)
Area 2 (SV Meelap) L&D: Kwang, Tonpalm, Benz   10 สาขา (ตะวันตก+ใต้บน)
Area 3 (SV Bow)    L&D: Kio, Nueng, Looklew     9 สาขา (ตะวันออก+ชลบุรี)
Area 4 (SV Ko)     L&D: Pui, Mark              10 สาขา (กทม.ใน+พระราม)
Area 5 (SV Juji)   L&D: Jajah, Jets            10 สาขา (กทม.กลาง+ริมน้ำ)
Area 6 (AM Chock)  L&D: Jib                     7 สาขา (กทม.ใหญ่+เมกา)
Area 7 (SV Champ)  L&D: Fair                   10 สาขา (อีสาน+ภาคกลาง)
Area 8 (AM Aom)    L&D: Judy                    8 สาขา (กทม.สยาม+ฟิวเจอร์)

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
] + SAVE_TOOLS


def execute_pulse_tool(tool_name, tool_input):
    # ── Save tools (shared) ──────────────────────────────────────
    result = execute_save_tool(tool_name, tool_input, agent_id="pulse")
    if result is not None:
        return result
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
            auto_save("pulse", task, final_text)
            return final_text

        return "Pulse ใช้เวลาวิเคราะห์นานเกินไปครับ ลองถามเจาะจงกว่านี้ได้ไหมครับ"

    except Exception as e:
        print(f"Pulse Error: {e}")
        return f"Pulse มีปัญหาชั่วคราวครับ: {str(e)}"
