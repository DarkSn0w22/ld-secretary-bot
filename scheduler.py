"""
Scheduler — Background Jobs
Daily Brief: ทุกวัน 10:30
Weekly Report (Sage): ทุกวันจันทร์ + พฤหัส 09:00
"""

import os
import threading
import time
from datetime import datetime
import pytz
import requests
import anthropic
from dashboard_api import get_survey_dashboard

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Daily Brief: 10:30 ทุกวัน
BRIEF_HOUR = 10
BRIEF_MINUTE = 30

# Sage Report: 09:00 วันจันทร์ (0) และพฤหัส (3)
REPORT_HOUR = 9
REPORT_MINUTE = 0
REPORT_DAYS = [0, 3]  # Monday, Thursday


def push_message(text: str):
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
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Push error: {e}")
        return False


def generate_daily_brief() -> str:
    now = datetime.now(BANGKOK_TZ)
    day_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    date_str = now.strftime(f"วัน{day_th[now.weekday()]}ที่ %d/%m/%Y")

    print("Fetching survey data for daily brief...")
    survey_data = get_survey_dashboard()

    prompt = f"""วันนี้คือ {date_str} เวลา 10:30 น.

ข้อมูล Survey ล่าสุด:
{survey_data}

สรุป Daily Brief สั้นๆ สำหรับ Peanut (Regional L&D Manager)
รูปแบบ:
- ขึ้นต้นด้วย emoji เช้าและวันที่
- สรุป Survey highlight
- แจ้งสิ่งที่ควรติดตามวันนี้

ห้ามใช้ Markdown ใช้ plain text และ emoji เท่านั้น
ใช้คำลงท้าย "ครับ" ยาวไม่เกิน 500 ตัวอักษร"""

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Daily brief error: {e}")
        return f"🌅 Good Morning Peanut!\n{date_str}\n\nขอโทษครับ ระบบสรุปข้อมูลมีปัญหาชั่วคราว"


def scheduler_loop():
    print("Scheduler started — waiting for scheduled times (Bangkok)...")
    sent_brief_today = None
    sent_report_today = None

    while True:
        now = datetime.now(BANGKOK_TZ)
        today = now.date()
        weekday = now.weekday()

        # Daily Brief: 10:30
        if (now.hour == BRIEF_HOUR and
                now.minute == BRIEF_MINUTE and
                sent_brief_today != today):
            print(f"Sending daily brief...")
            brief = generate_daily_brief()
            if push_message(brief):
                sent_brief_today = today
                print("Daily brief sent")

        # Sage Weekly Report: 09:00 วันจันทร์ + พฤหัส
        if (now.hour == REPORT_HOUR and
                now.minute == REPORT_MINUTE and
                weekday in REPORT_DAYS and
                sent_report_today != today):
            print(f"Sending Sage weekly report (weekday={weekday})...")
            try:
                from reporter_agent import send_scheduled_report
                send_scheduled_report("weekly")
                sent_report_today = today
                print("Sage report sent")
            except Exception as e:
                print(f"Sage report error: {e}")

        time.sleep(30)


def start_scheduler():
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    print("Scheduler thread started")
