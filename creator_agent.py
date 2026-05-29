"""
Creator AI — "Lens"
สร้าง training content, สคริปต์, quiz, สื่อการสอน และเนื้อหาสำหรับ od-connect.com
"""

import os
import anthropic
from models_config import get_model
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

LENS_PROMPT = """คุณคือ "Lens" — Creator AI ของ OWNDAYS L&D AI Office

บทบาท:
- สร้าง training content สำหรับ 16 หลักสูตรของ OWNDAYS Academy
- เขียนสคริปต์สำหรับ video training
- สร้าง quiz และ assessment questions
- เขียน e-learning content สำหรับ od-connect.com
- สร้าง infographic brief และ presentation outline
- แปล/ปรับเนื้อหาเป็นภาษาไทย-อังกฤษ-เขมร-ลาว
- สร้าง LINE message templates สำหรับ training announcements

หลักสูตรที่รับผิดชอบ:
OTT, PE, BSC/MSC/MTSC (Sales), BOC/MOC/MTOC (Optical), BVC/MVC/MTVC (Optometry),
BOBT/MOBT/MTOBT (On-board), SMOT, MOT

สไตล์การเขียน:
- ภาษาเข้าใจง่าย เหมาะกับ retail staff
- มีตัวอย่างจาก context ร้านแว่น OWNDAYS จริง
- Interactive และ engaging
- เน้น practical application

กฎการตอบ:
- ตอบภาษาไทย เว้นแต่จะระบุภาษาอื่น
- ใช้คำลงท้าย "ครับ"
- สร้าง content ที่พร้อม copy-paste ใช้ได้เลย
- ถามรายละเอียดก่อนถ้า task ไม่ชัดเจน
"""

LENS_TOOLS = [
    {
        "name": "research_topic",
        "description": "ค้นหาข้อมูลเพื่อสร้าง content เช่น optical knowledge, sales techniques",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"]
        }
    },
    {
        "name": "search_examples",
        "description": "ค้นหาตัวอย่าง training content หรือ quiz จากภายนอก",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
]

COURSE_CONTEXT = {
    "OTT": "Orientation Training — แนะนำบริษัท, วัฒนธรรม OWNDAYS, กฎระเบียบ",
    "PE": "Personality Enhancement — บุคลิกภาพในการบริการลูกค้า",
    "BSC": "Basic Sales Essential — ทักษะการขายพื้นฐาน, การต้อนรับ, customer journey",
    "BOC": "Basic Optical Comprehension — ความรู้เรื่องสายตา, เลนส์พื้นฐาน",
    "BVC": "Basic Vision Fundamentals — การดูแลสายตา, optometry เบื้องต้น",
    "MSC": "Moderate Sales Participatory — การขายเชิงลึก, cross-selling",
    "MOC": "Moderate Optical Progression — เลนส์ระดับกลาง, progressive lenses",
    "MVC": "Moderate Vision Care Advisor — การให้คำปรึกษาด้านสายตาระดับกลาง",
    "SMOT": "Store Manager Orientation — ภาวะผู้นำ, การบริหารสาขา",
}


def execute_lens_tool(tool_name, tool_input):
    if tool_name == "research_topic":
        topic = tool_input.get("topic", "")
        course_hint = ""
        for code, desc in COURSE_CONTEXT.items():
            if code.lower() in topic.lower() or any(w in topic.lower() for w in desc.lower().split(",")):
                course_hint = f" {code}: {desc}"
        return google_search(f"OWNDAYS optical retail training {topic}{course_hint} Thailand")
    elif tool_name == "search_examples":
        return google_search(tool_input.get("query", "") + " training content example retail")
    return "ไม่พบ tool นี้"


def run_creator(task, context=""):
    print(f"Lens processing: {task[:50]}...")
    prompt = f"Context: {context}\n\nTask: {task}" if context else task
    messages = [{"role": "user", "content": prompt}]
    try:
        for _ in range(3):
            response = claude.messages.create(
                model=get_model("lens"), max_tokens=3000,
                system=LENS_PROMPT, tools=LENS_TOOLS, messages=messages
            )
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": execute_lens_tool(block.name, block.input)})
                messages.append({"role": "user", "content": results})
                continue
            return "".join(b.text for b in response.content if hasattr(b, "text"))
        return "Lens ใช้เวลานานเกินไปครับ"
    except Exception as e:
        return f"Lens มีปัญหาชั่วคราวครับ: {str(e)}"
