"""
Legal Manager AI — "Lex"
ที่ปรึกษากฎหมายประจำทีม L&D
ครอบคลุม: แรงงานไทย, PDPA, สัญญาฝึกอบรม, IP, กฎหมาย KH/LA
"""

import os
import anthropic
from models_config import get_model
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

LEX_PROMPT = """คุณคือ "Lex" — Legal Manager AI ของ OWNDAYS L&D AI Office

บทบาท:
- ที่ปรึกษากฎหมายเบื้องต้นสำหรับแผนก L&D
- ตรวจสอบความถูกต้องทางกฎหมายของเอกสาร นโยบาย และ content ก่อนใช้งาน
- แจ้งเตือน legal risk ที่อาจเกิดขึ้น
- ให้ความรู้ด้านกฎหมายที่เกี่ยวข้องกับ L&D และ HR

ขอบเขตความรู้:
1. กฎหมายแรงงานไทย — สัญญาจ้าง, ชั่วโมงทำงาน, OT, วันหยุด, เลิกจ้าง
2. PDPA (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล) — การเก็บข้อมูลพนักงาน, consent, data retention
3. สัญญาการฝึกอบรม — training bond, ข้อตกลงการรักษาความลับ
4. IP ของ Training Content — ลิขสิทธิ์, การใช้เนื้อหาจากภายนอก, fair use
5. กฎหมายแรงงานกัมพูชา/ลาว — ความแตกต่างจากไทยที่ต้องระวัง
6. การใช้ AI ในองค์กร — ข้อกฎหมายและนโยบายที่เกี่ยวข้อง
7. เอกสาร HR — NDA, non-compete, consent forms

ข้อจำกัดสำคัญ:
- Lex ให้ข้อมูลเบื้องต้นเท่านั้น ไม่ใช่คำปรึกษากฎหมายจริง
- งานที่มี legal risk สูงต้องให้ทนายมนุษย์ตรวจสอบเสมอ
- แจ้งข้อจำกัดนี้ทุกครั้งที่ให้คำแนะนำสำคัญ

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- ระบุกฎหมาย/มาตราที่อ้างอิงเสมอ
- แจ้ง risk level: ต่ำ / กลาง / สูง / ต้องปรึกษาทนาย
- เสนอ recommendation เสมอ
"""

LEX_TOOLS = [
    {
        "name": "search_thai_law",
        "description": "ค้นหาข้อมูลกฎหมายแรงงานไทย, PDPA, หรือกฎหมายที่เกี่ยวข้อง",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "คำค้นหา เช่น กฎหมายแรงงาน ชั่วโมงทำงาน"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_international_law",
        "description": "ค้นหากฎหมายแรงงานกัมพูชา ลาว หรือกฎหมายระหว่างประเทศ",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "review_document",
        "description": "ตรวจสอบเอกสารทางกฎหมาย เช่น สัญญา, นโยบาย, consent form",
        "input_schema": {
            "type": "object",
            "properties": {
                "document": {"type": "string", "description": "เนื้อหาเอกสารที่ต้องตรวจ"},
                "doc_type": {"type": "string", "description": "ประเภทเอกสาร เช่น contract, policy, consent"}
            },
            "required": ["document"]
        }
    }
]


def execute_lex_tool(tool_name, tool_input):
    if tool_name == "search_thai_law":
        query = tool_input.get("query", "") + " กฎหมายไทย labor law Thailand"
        return google_search(query)
    elif tool_name == "search_international_law":
        query = tool_input.get("query", "") + " Cambodia Laos labor law"
        return google_search(query)
    elif tool_name == "review_document":
        doc = tool_input.get("document", "")
        doc_type = tool_input.get("doc_type", "document")
        return f"เอกสารประเภท {doc_type} ที่ต้องตรวจ:\n{doc[:2000]}"
    return "ไม่พบ tool นี้"


def run_legal_manager(task, context=""):
    """รัน Lex ให้คำปรึกษากฎหมาย"""
    print(f"Lex processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        for _ in range(3):
            response = claude.messages.create(
                model=get_model("lex"),
                max_tokens=2048,
                system=LEX_PROMPT,
                tools=LEX_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Lex using tool: {block.name}")
                        result = execute_lex_tool(block.name, block.input)
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
            print("Lex completed")
            return final_text

        return "Lex ใช้เวลานานเกินไปครับ ลองถามใหม่แบบเจาะจงกว่านี้"

    except Exception as e:
        print(f"Lex Error: {e}")
        return f"Lex มีปัญหาชั่วคราวครับ: {str(e)}"
