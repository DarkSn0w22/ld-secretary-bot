"""
Daily Brief Scheduler
ส่ง LINE อัตโนมัติทุกวัน 10:30 (Bangkok Time)
"""

import os
import threading
import time
from datetime import datetime
import pytz
import requests
import anthropic
from sheets_tools import get_survey_summary

# =============================================================
# CONFIG
# =============================================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
BRIEF_HOUR = 10
BRIEF_MINUTE = 30

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# =============================================================
# ส่งข้อความหา Peanut โดยตรง (Push Message)
# =============================================================
def push_message(text: str):
    """ส่งข้อความไปหา Peanut โดยไม่ต้องรอให้ทักก่อน"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }

    # แบ่งถ้ายาวเกิน 5000 ตัว
    messages = []
    while text:
        chunk = text[:5000]
        messages.append({"type": "text", "text": chunk})
        text = text[5000:]

    payload = {
        "to": PEANUT_USER_ID,
        "messages": messages[:5]
    }

    response = requests.post(url, headers=headers, json=payload)
    print(f"Push message status: {response.status_code}")
    return response.status_code == 200


# =============================================================
# สร้าง Daily Brief
# =============================================================
def generate_daily_brief() -> str:
    """ให้ Claude สรุป Daily Brief จากข้อมูล Sheets"""

    now = datetime.now(BANGKOK_TZ)
    day_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    day_name = day_th[now.weekday()]
    date_str = now.strftime(f"วัน{day_name}ที่ %d/%m/%Y")

    # ดึงข้อมูล Survey
    print("Fetching survey data for daily brief...")
    survey_data = get_survey_summary()

    prompt = f"""วันนี้คือ {date_str} เวลา 10:30 น.

ข้อมูล Survey ล่าสุด:
{survey_data}

สรุป Daily Brief สั้นๆ สำหรับ Peanut ในฐานะ Regional L&D Manager
รูปแบบ:
- ขึ้นต้นด้วย emoji เช้าและชื่อ
- วันที่
- สรุป Survey สัปดาห์นี้ (highlight ที่น่าสนใจ)
- ถ้าไม่มีข้อมูลใหม่ให้บอกตรงๆ

ห้ามใช้ Markdown ใช้ plain text และ emoji เท่านั้น
ใช้คำลงท้าย "ครับ"
กระชับ อ่านง่ายบน LINE"""

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude error: {e}")
        return f"🌅 Good Morning Peanut!\n{date_str}\n\nขอโทษครับ ระบบสรุปข้อมูลมีปัญหาชั่วคราว"


# =============================================================
# Scheduler Loop
# =============================================================
def scheduler_loop():
    """วนลูปเช็คเวลาทุก 30 วินาที"""
    print("Scheduler started — waiting for 10:30 Bangkok time...")
    sent_today = None  # เก็บวันที่ส่งไปแล้ว

    while True:
        now = datetime.now(BANGKOK_TZ)
        today = now.date()

        # ถ้าถึงเวลา 10:30 และยังไม่ได้ส่งวันนี้
        if (now.hour == BRIEF_HOUR and
                now.minute == BRIEF_MINUTE and
                sent_today != today):

            print(f"Sending daily brief at {now.strftime('%H:%M')} Bangkok time...")
            brief = generate_daily_brief()
            success = push_message(brief)

            if success:
                sent_today = today
                print(f"Daily brief sent successfully on {today}")
            else:
                print("Failed to send daily brief")

        time.sleep(30)  # เช็คทุก 30 วินาที


def start_scheduler():
    """เริ่ม scheduler ใน background thread"""
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    print("Scheduler thread started")
