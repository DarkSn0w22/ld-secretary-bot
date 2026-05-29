"""
Scheduler — Consolidated Morning Report
ทุกวัน 09:00: Rocket สรุปรายงานจากทุก agent ส่งครั้งเดียว
(ยกเลิกการส่งแยกของ Coin/People/Sage/Daily Brief แยก)
"""

import os
import threading
import time
from datetime import datetime
import pytz
import requests
import anthropic
from models_config import get_model
from agent_log import log_agent

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ส่งรายงาน 09:00 วันจันทร์-ศุกร์ ครั้งเดียว
MORNING_HOUR   = 9
MORNING_MINUTE = 0
WORK_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri


def push_message(text: str) -> bool:
    """ส่ง LINE message ถึง Peanut"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    chunks = []
    remaining = text
    while remaining:
        chunks.append({"type": "text", "text": remaining[:5000]})
        remaining = remaining[5000:]
    payload = {"to": PEANUT_USER_ID, "messages": chunks[:5]}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Push error: {e}")
        return False


def collect_agent_reports(weekday: int) -> dict:
    """เก็บรายงานจากแต่ละ agent — return dict (ไม่ส่ง LINE)"""
    reports = {}

    # Coin: Budget status
    try:
        from financial_agent import get_budget_summary_text
        reports["coin"] = get_budget_summary_text()
        log_agent("scheduler", "coin", "ขอ budget summary เช้า", reports["coin"])
    except Exception as e:
        reports["coin"] = f"ข้อมูล budget ไม่พร้อม: {e}"

    # People: Probation alerts
    try:
        from hr_agent import get_probation_summary_text
        reports["people"] = get_probation_summary_text()
        log_agent("scheduler", "people", "ขอ probation summary เช้า", reports["people"])
    except Exception as e:
        reports["people"] = f"ข้อมูล HR ไม่พร้อม: {e}"

    # Sage: Training — จันทร์+พฤหัส full, วันอื่น highlight
    try:
        from reporter_agent import get_training_summary_text
        full = weekday in [0, 3]
        reports["sage"] = get_training_summary_text(full=full)
        log_agent("scheduler", "sage", f"ขอ training summary (full={full})", reports["sage"])
    except Exception as e:
        reports["sage"] = f"ข้อมูล training ไม่พร้อม: {e}"

    return reports


def consolidated_morning_report() -> str:
    """Rocket รวมรายงานทุก agent แล้วสรุปเป็นข้อความเดียว"""
    now = datetime.now(BANGKOK_TZ)
    weekday = now.weekday()
    day_th = ["จันทร์","อังคาร","พุธ","พฤหัส","ศุกร์","เสาร์","อาทิตย์"]
    date_str = now.strftime(f"วัน{day_th[weekday]}ที่ %d/%m/%Y")

    print(f"[Scheduler] Collecting agent reports for {date_str}...")
    reports = collect_agent_reports(weekday)

    prompt = f"""วันนี้: {date_str} 09:00 น.

รายงานจากทีม AI:

💰 Coin (Financial):
{reports.get('coin', '-')}

👥 People (HR):
{reports.get('people', '-')}

📚 Sage (Training):
{reports.get('sage', '-')}

คุณคือ Rocket เลขานุการ AI ของ Peanut (Regional L&D Manager)
สรุปรายงานเช้าออกเป็น 1 ข้อความกระชับ ดังนี้:
- บรรทัดแรก: 🌅 วันที่ + "รายงานเช้า"
- แต่ละแผนก: หัวข้อ + emoji + เฉพาะประเด็นสำคัญที่ต้องรู้/ต้องทำ
  (ถ้าไม่มีเรื่องสำคัญ → ข้ามแผนกนั้นไปเลย)
- ถ้ามี action → รวมไว้ท้าย "⚡ Action วันนี้:"
- ห้าม Markdown ใช้ plain text + emoji เท่านั้น
- ยาวไม่เกิน 1,200 ตัวอักษร
- ลงท้าย "ครับ" """

    try:
        response = claude.messages.create(
            model=get_model("scheduler"),
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.content[0].text.strip()
        log_agent("scheduler", "rocket", "รวม morning report", result)
        return result
    except Exception as e:
        print(f"Report generation error: {e}")
        # Fallback plain text
        return (f"🌅 {date_str} รายงานเช้าครับ\n\n"
                f"💰 Coin: {reports.get('coin','?')}\n\n"
                f"👥 People: {reports.get('people','?')}\n\n"
                f"📚 Sage: {reports.get('sage','?')}")


def scheduler_loop():
    print("Scheduler started — 1 consolidated message at 09:00 Mon-Fri (Bangkok)")
    sent_today = None

    while True:
        now = datetime.now(BANGKOK_TZ)
        today = now.date()
        weekday = now.weekday()

        if (now.hour == MORNING_HOUR and
                now.minute == MORNING_MINUTE and
                weekday in WORK_DAYS and
                sent_today != today):
            print("[Scheduler] Generating consolidated morning report...")
            try:
                report = consolidated_morning_report()
                if push_message(report):
                    sent_today = today
                    print("[Scheduler] Morning report sent ✓ (1 message)")
                else:
                    print("[Scheduler] Failed to send morning report")
            except Exception as e:
                print(f"[Scheduler] Error: {e}")

        time.sleep(30)


def start_scheduler():
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    print("Scheduler thread started")
