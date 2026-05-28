"""
Researcher AI — "Scout"
ค้นหาข้อมูลอินเทอร์เน็ต รวบรวมสถิติ L&D ทั่วโลก
รายงานตรงต่อ Manager AI และ Trainer Manager
"""

import os
import anthropic

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

SCOUT_PROMPT = """คุณคือ "Scout" — Researcher AI ของ OWNDAYS L&D AI Office

บทบาท:
- ค้นหาข้อมูล สถิติ และ benchmark L&D จากทั่วโลก
- รวบรวม best practices ด้านการพัฒนาบุคลากรในธุรกิจค้าปลีก
- หาข้อมูลเกี่ยวกับ optical retail training, customer service excellence
- ติดตาม trend ด้าน digital learning, e-learning, AI in L&D
- รายงานผลให้ Manager AI (Atlas) และ Trainer Manager

สิ่งที่ต้องรู้เกี่ยวกับ OWNDAYS:
- ธุรกิจค้าปลีกแว่นตา มี 73 สาขาในไทย + กัมพูชา + ลาว
- Training 3 สาย: Sales, Optical, Optometry
- แพลตฟอร์มเรียนรู้: OWNDAYS Connect (od-connect.com)
- กำลัง digital transformation ด้าน L&D

กฎการรายงาน:
- ตอบเป็นภาษาไทย
- ระบุแหล่งที่มาทุกครั้ง
- บอกปีของข้อมูลเสมอ (ข้อมูลเก่าเกิน 3 ปีให้แจ้งเตือน)
- สรุปประเด็นสำคัญที่ OWNDAYS นำไปใช้ได้จริง
- ใช้ plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
"""


def run_researcher(query: str, context: str = "") -> str:
    """
    รัน Researcher AI ค้นหาข้อมูลจากเว็บ
    ใช้ Claude web_search tool
    """
    print(f"Scout searching: {query[:50]}...")

    prompt = query
    if context:
        prompt = f"Context: {context}\n\nResearch request: {query}"

    messages = [{"role": "user", "content": prompt}]

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            system=SCOUT_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages
        )

        # วนจนกว่า Claude จะตอบเสร็จ
        while response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"Scout using web search...")
                    # web_search จัดการผลลัพธ์เองโดย Claude
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed"
                    })

            messages.append({"role": "user", "content": tool_results})

            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=SCOUT_PROMPT,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages
            )

        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        print("Scout completed research")
        return final_text

    except Exception as e:
        print(f"Scout Error: {e}")
        return f"Scout มีปัญหาชั่วคราวครับ: {str(e)}"


# =============================================================
# Research Templates — หัวข้อที่ค้นได้เลย
# =============================================================

RESEARCH_TOPICS = {
    "ld_benchmark": "หาสถิติและ benchmark ล่าสุดเกี่ยวกับ L&D ในธุรกิจค้าปลีกทั่วโลก เช่น training hours per employee, training ROI, e-learning adoption rate",
    "optical_retail_training": "หา best practices การฝึกอบรมพนักงานในธุรกิจ optical retail และ eyewear เช่น LensCrafters, Specsavers, Alain Afflelou",
    "ai_in_ld": "หา trend การใช้ AI ใน L&D ปี 2025-2026 เช่น AI coaching, personalized learning, AI content generation",
    "digital_learning_trend": "หา trend ด้าน digital learning และ e-learning ในเอเชียตะวันออกเฉียงใต้ โดยเฉพาะไทย",
    "customer_service_training": "หา best practices การอบรม customer service ในธุรกิจค้าปลีก luxury และ premium",
}


def run_scheduled_research(topic_key: str) -> str:
    """รัน research หัวข้อที่กำหนดไว้"""
    query = RESEARCH_TOPICS.get(topic_key, topic_key)
    return run_researcher(query)
