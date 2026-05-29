"""
Reporter AI — "Sage"
จัดหน้ารายงาน ส่งผลลัพธ์ทาง LINE อัตโนมัติ
ส่งทุกวันจันทร์ + พฤหัส เวลา 09:00 Bangkok Time
"""

import os
import anthropic
from models_config import get_model
import requests
from dashboard_api import get_all_dashboard

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

SAGE_PROMPT = """คุณคือ "Sage" — Reporter AI ของ OWNDAYS L&D AI Office

บทบาท:
- จัดทำรายงานภาพรวม L&D จากข้อมูล Dashboard
- นำเสนอสั้น กระชับ อ่านง่ายบน LINE
- เน้น highlight สำคัญ จุดที่ต้องระวัง และ recommendation

กฎการเขียนรายงาน:
- ใช้ plain text และ emoji เท่านั้น ห้าม Markdown (**/##)
- แบ่งหัวข้อด้วย emoji ชัดเจน
- ใส่ตัวเลขจริงทุกครั้ง
- จบด้วย recommendation 2-3 ข้อเสมอ
- ใช้คำลงท้าย "ครับ"
- ความยาวรวมไม่เกิน 1500 ตัวอักษร (เหมาะกับ LINE)
"""


def generate_report(data: str, report_type: str = "weekly") -> str:
    """ให้ Sage สรุปข้อมูลเป็นรายงาน"""
    prompt = f"""นี่คือข้อมูล L&D Dashboard ล่าสุด:

{data}

กรุณาจัดทำรายงาน {report_type} ภาพรวม L&D ครอบคลุม:
1. Survey & Trainer performance
2. Training registration (OAR)
3. Area performance
4. Assessment/Grading status
5. L&D Cost summary
6. Highlight จุดที่ดี และจุดที่ต้องระวัง
7. Recommendation 2-3 ข้อ

เขียนให้กระชับ อ่านง่ายบน LINE ไม่เกิน 1500 ตัวอักษร"""

    try:
        response = claude.messages.create(
            model=get_model("sage"),
            max_tokens=1500,
            system=SAGE_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Sage มีปัญหาในการสรุปรายงานครับ: {str(e)}"


def push_line_message(text: str):
    """ส่งข้อความไปหา Peanut ทาง LINE"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    messages = []
    while text:
        chunk = text[:5000]
        messages.append({"type": "text", "text": chunk})
        text = text[5000:]

    payload = {"to": PEANUT_USER_ID, "messages": messages[:5]}
    try:
        resp = requests.post(url, headers=headers, json=payload)
        return resp.status_code == 200
    except Exception as e:
        print(f"Sage push error: {e}")
        return False


def run_reporter(task: str = "weekly") -> str:
    """รัน Sage สร้างและส่งรายงาน"""
    print(f"Sage generating {task} report...")

    data = get_all_dashboard()
    report = generate_report(data, task)

    print(f"Sage report generated ({len(report)} chars)")
    return report


def get_training_summary_text(full: bool = False) -> str:
    """คืน training summary เป็น text — สำหรับ consolidated morning report"""
    try:
        data = get_all_dashboard()
        task = "weekly" if full else "highlight"
        return generate_report(data, task)[:600]
    except Exception as e:
        return f"ดึงข้อมูลไม่ได้: {e}"


def send_scheduled_report(report_type: str = "weekly"):
    """(legacy) ส่งรายงานอัตโนมัติ push ไปที่ LINE แยก"""
    print(f"Sage sending scheduled {report_type} report...")

    data = get_all_dashboard()

    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("Asia/Bangkok"))
    day_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    date_str = now.strftime(f"วัน{day_th[now.weekday()]}ที่ %d/%m/%Y")

    header = f"📋 รายงาน L&D รายสัปดาห์\n{date_str}\nโดย Sage (Reporter AI)\n{'─'*30}\n\n"

    report = generate_report(data, report_type)
    full_message = header + report

    success = push_line_message(full_message)
    if success:
        print("Sage report sent successfully")
    else:
        print("Sage failed to send report")

    return success
