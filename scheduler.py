"""
Scheduler — Morning Report + Autonomous 4-hour Watch Cycle
09:00: Rocket consolidated morning report
08:00/12:00/16:00/20:00 จ-ศ: Autonomous agent watch cycle (ทุก 4 ชั่วโมง)
"""

import os
import json
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

SCHEDULE_CONFIG_FILE = "schedule_config.json"
WORK_DAYS = [0, 1, 2, 3, 4]  # Mon-Fri fallback

# ── Runtime config (reloaded every 5 min from schedule_config.json) ──────────
_schedule_config = None
_config_loaded_at = 0.0

def load_schedule_config() -> dict:
    """อ่าน schedule_config.json — ถ้าไม่มีใช้ default 09:00"""
    global _schedule_config, _config_loaded_at
    try:
        with open(SCHEDULE_CONFIG_FILE, "r", encoding="utf-8") as f:
            _schedule_config = json.load(f)
            _config_loaded_at = time.time()
            return _schedule_config
    except Exception:
        pass
    # Default
    _schedule_config = {
        "jobs": [{
            "time": "09:00",
            "days": ["Mon","Tue","Wed","Thu","Fri"],
            "agent": "Rocket",
            "task": "Consolidated Morning Report (Coin + People + Sage)",
            "enabled": True
        }]
    }
    return _schedule_config

def get_schedule_config() -> dict:
    """คืน config ปัจจุบัน — reload ถ้าไฟล์เปลี่ยน (ทุก 5 นาที)"""
    if _schedule_config is None or time.time() - _config_loaded_at > 300:
        load_schedule_config()
    return _schedule_config or {}

def get_morning_job():
    """ดึง job แรกที่ enabled จาก config"""
    cfg = get_schedule_config()
    for job in cfg.get("jobs", []):
        if job.get("enabled", True):
            return job
    return None

def get_morning_hour_minute():
    """แยก HH:MM จาก job แรก"""
    job = get_morning_job()
    if job:
        try:
            hh, mm = job["time"].split(":")
            return int(hh), int(mm)
        except Exception:
            pass
    return 9, 0  # default

DAY_MAP = {"Mon":0,"Tue":1,"Wed":2,"Thu":3,"Fri":4,"Sat":5,"Sun":6}

def get_morning_days():
    """คืน list ของ weekday integers จาก config"""
    job = get_morning_job()
    if job:
        days = job.get("days", ["Mon","Tue","Wed","Thu","Fri"])
        return [DAY_MAP[d] for d in days if d in DAY_MAP]
    return WORK_DAYS


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


# ── Activity digest config ────────────────────────────────────────
# ส่งสรุปกิจกรรม agent ทุก X ชั่วโมง ถ้ามีการทำงานจริง
ACTIVITY_DIGEST_HOURS = []  # ปิด — ประหยัด API (เปิดได้โดย env ACTIVITY_DIGEST=1)
_last_activity_epoch = 0.0             # epoch ของ log ล่าสุดที่ส่งไปแล้ว

# ── Autonomous watch cycle config ────────────────────────────────
# รัน agent watch ทุก 4 ชั่วโมง (08:00 / 12:00 / 16:00 / 20:00) จ-ศ
WATCH_HOURS = [12]   # รัน 1 ครั้ง/วัน (เดิม 4 ครั้ง) — ประหยัด 75%


def build_activity_digest() -> str | None:
    """สร้างสรุปกิจกรรม agents ตั้งแต่ครั้งสุดท้าย — คืน None ถ้าไม่มีอะไรใหม่"""
    global _last_activity_epoch
    from agent_log import get_logs
    import time

    # ดึง log ใหม่ตั้งแต่ครั้งล่าสุด
    new_logs = get_logs(n=100, since_epoch=_last_activity_epoch)

    # กรองเฉพาะ agent calls จริง (ไม่ใช่ user/dashboard/scheduler)
    skip = {"user", "dashboard", "scheduler", "rocket"}
    activity = [
        l for l in new_logs
        if l.get("from", "").lower() not in skip
        or l.get("to", "").lower() not in skip
    ]
    # เฉพาะที่เป็น agent → agent หรือ rocket → agent
    real_calls = [
        l for l in new_logs
        if (l.get("from", "") == "rocket" and l.get("to", "") not in {"user", "dashboard"})
        or (l.get("from", "") not in {"user", "dashboard", "scheduler"}
            and l.get("to", "") not in {"user", "dashboard"})
    ]

    if not real_calls:
        return None  # ไม่มีกิจกรรมใหม่

    # อัพเดต epoch
    _last_activity_epoch = max(l["epoch"] for l in real_calls)

    # สรุปด้วย Claude (Rocket voice)
    now = datetime.now(BANGKOK_TZ)
    time_str = now.strftime("%H:%M น.")
    log_text = "\n".join(
        f"- {l['from'].upper()} → {l['to'].upper()}: {l['msg'][:80]}"
        + (f"\n  ✅ {l['res'][:120]}" if l.get('res') else "")
        for l in real_calls[-12:]  # 12 รายการล่าสุด
    )

    prompt = f"""เวลา {time_str}

กิจกรรม agent ล่าสุด:
{log_text}

คุณคือ Rocket เลขานุการ AI
สรุปสิ่งที่ทีมทำในช่วงที่ผ่านมาให้ Peanut ทราบ:
- ขึ้นต้น: 🤖 + เวลา + "ทีมรายงาน"
- บอกว่า agent ไหนทำอะไร ผลลัพธ์สำคัญคืออะไร
- ถ้ามีสิ่งที่ต้อง action → แจ้งด้วย
- plain text ไม่มี Markdown
- กระชับ ไม่เกิน 500 ตัวอักษร
- ลงท้าย "ครับ" """

    try:
        resp = claude.messages.create(
            model=get_model("scheduler"),
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        # Fallback สั้นๆ
        agents_done = list({l["from"].upper() for l in real_calls
                            if l["from"] not in {"user", "dashboard", "scheduler"}})
        return (f"🤖 {time_str} ทีมรายงาน\n\n"
                f"Agent ที่ทำงาน: {', '.join(agents_done)}\n"
                f"รวม {len(real_calls)} tasks ในช่วงที่ผ่านมาครับ")


def run_watch_cycle_background():
    """รัน autonomous watch cycle ใน background thread"""
    try:
        from autonomous_agents import run_watch_cycle
        print("[Scheduler] Launching watch cycle...")
        run_watch_cycle(user_id=PEANUT_USER_ID)
        print("[Scheduler] Watch cycle completed ✓")
    except Exception as e:
        print(f"[Scheduler] Watch cycle error: {e}")
        log_agent("scheduler", "system", "[watch-cycle] error", str(e), status="error")


def scheduler_loop():
    print("Scheduler started — morning report 09:00 + activity digests 11:00/15:00/19:00 "
          "+ autonomous watch 08:00/12:00/16:00/20:00")
    sent_today = None
    sent_digest_hours = set()   # เซ็ต hours ที่ส่ง digest ไปแล้วในวันนี้
    sent_watch_hours = set()    # เซ็ต hours ที่ trigger watch cycle ไปแล้วในวันนี้

    while True:
        now = datetime.now(BANGKOK_TZ)
        today = now.date()
        weekday = now.weekday()

        # รีเซ็ต trackers เมื่อขึ้นวันใหม่
        if sent_today != today:
            sent_digest_hours = set()
            sent_watch_hours = set()

        # ── Morning Report — เวลาจาก schedule_config.json ──────────
        mh, mm = get_morning_hour_minute()
        mdays   = get_morning_days()
        if (now.hour == mh and
                now.minute == mm and
                weekday in mdays and
                sent_today != today):
            print("[Scheduler] Generating consolidated morning report...")
            try:
                report = consolidated_morning_report()
                if push_message(report):
                    sent_today = today
                    print("[Scheduler] Morning report sent ✓")
            except Exception as e:
                print(f"[Scheduler] Morning report error: {e}")

        # ── Activity Digest 11:00 / 15:00 / 19:00 ───────────────
        if (now.hour in ACTIVITY_DIGEST_HOURS and
                now.minute == 0 and
                weekday in WORK_DAYS and
                now.hour not in sent_digest_hours):
            print(f"[Scheduler] Checking activity digest at {now.hour}:00...")
            try:
                digest = build_activity_digest()
                if digest:
                    if push_message(digest):
                        sent_digest_hours.add(now.hour)
                        print(f"[Scheduler] Activity digest sent ✓ ({now.hour}:00)")
                else:
                    sent_digest_hours.add(now.hour)
                    print(f"[Scheduler] No new activity at {now.hour}:00 — skip")
            except Exception as e:
                print(f"[Scheduler] Activity digest error: {e}")

        # ── Autonomous Watch Cycle 08:00 / 12:00 / 16:00 / 20:00 จ-ศ ──
        if (now.hour in WATCH_HOURS and
                now.minute == 0 and
                weekday in WORK_DAYS and
                now.hour not in sent_watch_hours):
            print(f"[Scheduler] Triggering autonomous watch cycle at {now.hour}:00...")
            sent_watch_hours.add(now.hour)  # mark ก่อนเพื่อป้องกัน double-trigger
            watch_thread = threading.Thread(
                target=run_watch_cycle_background,
                daemon=True,
                name=f"watch-cycle-{now.hour:02d}"
            )
            watch_thread.start()

        time.sleep(30)


def start_scheduler():
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    print("Scheduler thread started")
