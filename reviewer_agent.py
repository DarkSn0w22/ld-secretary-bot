"""
Reviewer/QA AI — "Guard"
ตรวจสอบคุณภาพงานก่อนส่งให้ Manager หรือ Peanut
"""

import os
import anthropic
from models_config import get_model

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

GUARD_PROMPT = """คุณคือ "Guard" — Reviewer/QA AI ของ OWNDAYS L&D AI Office

บทบาท:
- ตรวจสอบคุณภาพงานที่ agent อื่นสร้างก่อนส่งออก
- หาข้อผิดพลาด ความไม่สอดคล้อง หรือจุดที่ควรปรับปรุง
- ให้คะแนน QA Score 1-10 พร้อม feedback ชัดเจน
- รับรองว่างานมีมาตรฐานก่อนถึงมือ Peanut หรือ MD

สิ่งที่ตรวจสอบ:
1. ความถูกต้องของข้อมูลและตัวเลข
2. ความครบถ้วนของเนื้อหาตามที่ขอ
3. ความชัดเจนและอ่านง่าย
4. ความเหมาะสมของภาษาและรูปแบบ
5. Legal risk หรือ sensitive content
6. ความสอดคล้องกับ OWNDAYS brand และ L&D context

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ให้ QA Score ชัดเจน (เช่น QA Score: 8/10)
- ระบุจุดที่ดี และจุดที่ต้องแก้ไข
- ถ้าคะแนน < 7 ให้ระบุว่าต้อง revise ก่อน
- ใช้คำลงท้าย "ครับ"

เกี่ยวกับ OWNDAYS L&D:
- 73 สาขา, trainer 18 คน, พนักงาน 400+ คน
- ผู้รับรายงาน: Peanut (Regional L&D Manager), MD, CFO, SEA Regional
- ต้องมีมาตรฐานระดับ professional เสมอ
"""


def run_reviewer(content: str, content_type: str = "report", context: str = "") -> str:
    """
    ตรวจสอบคุณภาพงาน
    content: เนื้อหาที่ต้องการตรวจ
    content_type: ประเภทงาน เช่น report, email, training_material, analysis
    """
    print(f"Guard reviewing {content_type}...")

    prompt = f"""กรุณาตรวจสอบงานต่อไปนี้:

ประเภทงาน: {content_type}
{f'Context: {context}' if context else ''}

เนื้อหาที่ต้องตรวจ:
{content}

กรุณาให้:
1. QA Score: X/10
2. จุดที่ดี (อย่างน้อย 2 ข้อ)
3. จุดที่ต้องแก้ไข (ถ้ามี)
4. สรุป: ผ่าน หรือ ต้อง revise ก่อน
5. Version ที่แก้แล้ว (ถ้าคะแนน < 7)"""

    try:
        response = claude.messages.create(
            model=get_model("guard"),
            max_tokens=2000,
            system=GUARD_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.content[0].text
        print("Guard review completed")
        return result
    except Exception as e:
        print(f"Guard Error: {e}")
        return f"Guard มีปัญหาชั่วคราวครับ: {str(e)}"


def review_and_improve(content: str, content_type: str = "report") -> dict:
    """
    ตรวจสอบและคืนผลพร้อม flag ว่าผ่านหรือไม่
    คืนค่า: {passed: bool, score: int, feedback: str, improved: str}
    """
    review = run_reviewer(content, content_type)

    # ดึง score จาก response
    score = 0
    try:
        for line in review.split("\n"):
            if "QA Score" in line or "score" in line.lower():
                nums = [int(s) for s in line.split() if s.replace("/","").isdigit() and int(s.replace("/","")) <= 10]
                if nums:
                    score = nums[0]
                    break
    except Exception:
        score = 7  # default

    passed = score >= 7

    return {
        "passed": passed,
        "score": score,
        "feedback": review,
        "needs_revision": not passed
    }
