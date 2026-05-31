"""
Weekly Monday All-Hands Meeting — OWNDAYS AI Office
=====================================================
ทุกวันจันทร์เวลา 09:30 น. ทุกแผนก (11 agents) ประชุมรวม
รายงานผลสัปดาห์ที่ผ่านมา + แผนสัปดาห์นี้
Rocket สรุปเป็น "รายงานการประชุม" ส่ง LINE ทันที

Cost: ~11 Haiku calls ≈ ฿0.20/สัปดาห์
"""

import os
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
import pytz
import anthropic
from models_config import get_model
from agent_log import log_agent

BANGKOK_TZ    = pytz.timezone("Asia/Bangkok")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")
claude         = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

AGENT_TIMEOUT  = 60   # timeout per agent (seconds)
MEETING_TIME   = "09:30"  # เวลาประชุม (ใช้แสดงใน header)


# ── Agent personas & weekly prompt ───────────────────────────────────────────

AGENT_MEETING_CONFIG = {
    "rex": {
        "name": "Rex",
        "icon": "📊",
        "role": "Retail MD",
        "prompt": (
            "คุณคือ Rex Retail MD วิเคราะห์ผลงาน sales สาขาสัปดาห์นี้:\n"
            "1. สาขาที่ทำได้ดีที่สุด/แย่ที่สุด (ถ้ามีข้อมูล)\n"
            "2. KPI หลักที่น่ากังวล (CVR/ATV/Achiev%)\n"
            "3. สาขาที่ต้องการ training intervention ด่วน\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "rex",
    },
    "pulse": {
        "name": "Pulse",
        "icon": "📚",
        "role": "Trainer Manager",
        "prompt": (
            "คุณคือ Pulse Trainer Manager รายงานสถานะ training สัปดาห์นี้:\n"
            "1. Survey score ภาพรวม / trainer ที่น่ากังวล\n"
            "2. OAR completion / หลักสูตรที่ล่าช้า\n"
            "3. แผน intervention สัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "pulse",
    },
    "coin": {
        "name": "Coin",
        "icon": "💰",
        "role": "Financial Manager",
        "prompt": (
            "คุณคือ Coin Financial Manager รายงานสถานะงบประมาณสัปดาห์นี้:\n"
            "1. งบที่ใช้ไป / % คงเหลือ\n"
            "2. หมวดรายจ่ายที่ต้องระวัง\n"
            "3. ข้อแนะนำด้านการเงินสัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "coin",
    },
    "people": {
        "name": "People",
        "icon": "👥",
        "role": "HR Manager",
        "prompt": (
            "คุณคือ People HR Manager รายงานสถานะ HR สัปดาห์นี้:\n"
            "1. พนักงาน probation ที่ต้องดำเนินการ\n"
            "2. headcount เปลี่ยนแปลง (ถ้ามี)\n"
            "3. ประเด็น HR ที่ต้องติดตามสัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "people",
    },
    "pixel": {
        "name": "Pixel",
        "icon": "🌐",
        "role": "Web Admin",
        "prompt": (
            "คุณคือ Pixel Web Admin รายงานสถานะ od-connect.com สัปดาห์นี้:\n"
            "1. Uptime / performance\n"
            "2. Traffic & user engagement (GA4 ถ้ามี)\n"
            "3. งาน content หรือ tech ที่ต้องทำสัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "pixel",
    },
    "sigma": {
        "name": "Sigma",
        "icon": "📈",
        "role": "Data Analyst",
        "prompt": (
            "คุณคือ Sigma Data Analyst รายงาน insights สัปดาห์นี้:\n"
            "1. Trend ที่น่าสนใจจากข้อมูล (survey / cost / OAR)\n"
            "2. Anomaly หรือ pattern ที่ควรติดตาม\n"
            "3. Data ที่ขาดหรือควรเก็บเพิ่ม\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "sigma",
    },
    "sage": {
        "name": "Sage",
        "icon": "📋",
        "role": "Reporter",
        "prompt": (
            "คุณคือ Sage Reporter รายงานภาพรวม L&D สัปดาห์นี้:\n"
            "1. Highlight สำคัญที่ควรรู้\n"
            "2. เรื่องที่ต้องนำเสนอ management\n"
            "3. ข้อเสนอแนะเชิง strategic\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "sage",
    },
    "atlas": {
        "name": "Atlas",
        "icon": "🎯",
        "role": "Strategy Manager",
        "prompt": (
            "คุณคือ Atlas Strategic Manager รายงานมุมมองกลยุทธ์สัปดาห์นี้:\n"
            "1. L&D alignment กับ business goal\n"
            "2. โอกาสหรือความเสี่ยงที่มองเห็น\n"
            "3. Priority สำหรับสัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "atlas",
    },
    "lens": {
        "name": "Lens",
        "icon": "✏️",
        "role": "Content Creator",
        "prompt": (
            "คุณคือ Lens Instructional Designer รายงาน content สัปดาห์นี้:\n"
            "1. Content ที่กำลังพัฒนา / เสร็จแล้ว\n"
            "2. หลักสูตรที่ต้องปรับปรุงเร่งด่วน\n"
            "3. ไอเดีย content ใหม่สำหรับสัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "lens",
    },
    "guard": {
        "name": "Guard",
        "icon": "🛡️",
        "role": "QA Reviewer",
        "prompt": (
            "คุณคือ Guard QA Specialist รายงานคุณภาพงานสัปดาห์นี้:\n"
            "1. ประเด็นคุณภาพที่พบจาก agent outputs\n"
            "2. งานที่ผ่าน QA / ที่ต้องแก้ไข\n"
            "3. ข้อเสนอแนะเพื่อยกระดับคุณภาพ\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "guard",
    },
    "lex": {
        "name": "Lex",
        "icon": "⚖️",
        "role": "Legal Manager",
        "prompt": (
            "คุณคือ Lex Legal Manager รายงาน compliance สัปดาห์นี้:\n"
            "1. ประเด็นกฎหมาย/PDPA ที่ต้องระวัง\n"
            "2. เอกสาร/สัญญาที่ต้องดำเนินการ\n"
            "3. แนะนำด้าน compliance สัปดาห์หน้า\n"
            "กระชับ ไม่เกิน 180 ตัวอักษร plain text ลงท้ายครับ"
        ),
        "fn": "lex",
    },
}


# ── Helper: ดึงข้อมูล context สำหรับแต่ละ agent ─────────────────────────────

def _get_agent_context(agent_id: str) -> str:
    """ดึงข้อมูลจริงมาใส่ใน context ให้ agent รายงานได้แม่นขึ้น"""
    try:
        from dashboard_api import fetch_dashboard
        if agent_id in ("rex", "sigma", "atlas", "sage"):
            d = fetch_dashboard("survey")
            cost = fetch_dashboard("cost")
            return (
                f"Survey overall_avg={d.get('overall_avg',0):.2f}, "
                f"responses={d.get('total_responses',0)}, "
                f"cost_usage={cost.get('actual',0):,.0f}/{cost.get('budget',1):,.0f} บาท"
            )
        elif agent_id in ("pulse", "lens", "guard"):
            d = fetch_dashboard("survey")
            oar = fetch_dashboard("oar")
            return (
                f"Survey avg={d.get('overall_avg',0):.2f}, "
                f"OAR total={oar.get('total',0)}"
            )
        elif agent_id == "coin":
            d = fetch_dashboard("cost")
            actual = d.get("actual", 0)
            budget = d.get("budget", 1) or 1
            return f"actual={actual:,.0f} budget={budget:,.0f} ({actual/budget*100:.1f}%)"
        elif agent_id == "people":
            d = fetch_dashboard("area")
            areas = d.get("areas", {})
            total_prob = sum(
                v.get("employee_summary", {}).get("probation", 0)
                for v in areas.values()
            ) if areas else 0
            return f"probation count ~{total_prob} คน"
        elif agent_id in ("pixel", "lex"):
            return "ข้อมูลทั่วไป — วิเคราะห์จาก context ที่มี"
    except Exception:
        pass
    return ""


# ── Step 1: แต่ละ agent ให้ weekly summary ───────────────────────────────────

def _run_agent_weekly(agent_id: str) -> dict:
    """รัน 1 agent — คืน {agent_id, name, icon, role, report}"""
    cfg     = AGENT_MEETING_CONFIG[agent_id]
    context = _get_agent_context(agent_id)

    system = (
        f"คุณคือ {cfg['name']} ({cfg['role']}) ของ OWNDAYS L&D Thailand "
        f"กำลังรายงานในการประชุมประจำสัปดาห์ (Monday All-Hands) "
        f"ตอบ plain text สั้นกระชับ ไม่ใช้ Markdown ลงท้ายครับ"
    )
    user_content = (
        f"ข้อมูลปัจจุบัน: {context}\n\n" if context else ""
    ) + cfg["prompt"]

    try:
        resp = claude.messages.create(
            model=get_model("autonomous"),   # Haiku — ประหยัด
            max_tokens=350,
            system=system,
            messages=[{"role": "user", "content": user_content}]
        )
        report = resp.content[0].text.strip()
    except Exception as e:
        report = f"รายงานไม่ได้: {e}"

    log_agent("meeting", agent_id, "[weekly] report", report[:200])
    return {
        "agent_id": agent_id,
        "name":     cfg["name"],
        "icon":     cfg["icon"],
        "role":     cfg["role"],
        "report":   report,
    }


# ── Step 2: Rocket synthesize → "รายงานการประชุม" ────────────────────────────

def _synthesize_meeting(reports: list, meeting_date: str) -> list[str]:
    """
    Rocket รวบรวมทุก agent → รายงานการประชุม
    คืน list[str] เพราะอาจยาวเกิน 5000 ตัวอักษร (ส่ง LINE หลายข้อความ)
    """
    # สร้าง block ต่อ agent
    agent_block = "\n".join(
        f"{r['icon']} {r['name']} ({r['role']}):\n{r['report']}"
        for r in reports
    )

    system = (
        "คุณคือ Rocket เลขานุการ AI ของ Peanut (Regional L&D Manager) "
        "สรุป 'รายงานการประชุมประจำสัปดาห์' ให้อ่านทาง LINE ได้ในทันที "
        "กฎเหล็ก: ห้ามใช้ Markdown (**##--) ใช้ plain text + emoji ลงท้าย 'ครับ'"
    )
    prompt = (
        f"การประชุม Monday All-Hands — {meeting_date}\n\n"
        f"รายงานจากทีม AI ทั้ง 11 แผนก:\n\n{agent_block}\n\n"
        "สรุปเป็นรายงานการประชุม LINE:\n"
        "บรรทัดแรก: 📋 รายงานการประชุม L&D AI ประจำสัปดาห์ [วันที่]\n"
        "แต่ละแผนก: icon + ชื่อ + ประเด็นสำคัญ 1-2 บรรทัด (ข้ามแผนกที่ไม่มีเรื่อง)\n"
        "ส่วนท้าย: ⚡ Action Items สัปดาห์นี้ (รวม action จากทุกแผนก ไม่เกิน 5 ข้อ)\n"
        "และ: 💡 Rocket แนะนำ (insight สำคัญที่สุด 1 ข้อ)\n"
        "ยาวไม่เกิน 1,500 ตัวอักษร ลงท้ายครับ"
    )

    try:
        resp = claude.messages.create(
            model=get_model("scheduler"),   # Haiku
            max_tokens=1400,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        full_text = resp.content[0].text.strip()
    except Exception as e:
        # Fallback: plain concat
        lines = [f"📋 รายงานการประชุม L&D AI\n{meeting_date}\n"]
        for r in reports:
            lines.append(f"{r['icon']} {r['name']}: {r['report'][:120]}")
        lines.append("\nครับ")
        full_text = "\n".join(lines)
        print(f"[Meeting] synthesis fallback: {e}")

    # แบ่งเป็น chunks ถ้าเกิน 4800 ตัวอักษร (LINE limit 5000)
    chunks = []
    while full_text:
        chunks.append(full_text[:4800])
        full_text = full_text[4800:]
    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────

def run_monday_meeting(user_id: str = None) -> list[str]:
    """
    รัน Monday All-Hands Meeting แบบ parallel
    คืน list[str] ของข้อความที่ส่ง LINE ไปแล้ว
    """
    if user_id is None:
        user_id = PEANUT_USER_ID

    now          = datetime.now(BANGKOK_TZ)
    day_th       = ["จันทร์","อังคาร","พุธ","พฤหัส","ศุกร์","เสาร์","อาทิตย์"]
    meeting_date = now.strftime(f"วัน{day_th[now.weekday()]}ที่ %d/%m/%Y")
    time_str     = now.strftime("%H:%M น.")

    print(f"[Meeting] Monday All-Hands starting — {meeting_date} {time_str}")
    log_agent("scheduler", "meeting", f"[meeting] start — {meeting_date}", "")

    # ── ส่ง header ก่อน (แจ้ง Peanut ว่าประชุมกำลังเริ่ม) ──────
    try:
        from scheduler import push_message
        push_message(
            f"📋 การประชุมทีม L&D AI เริ่มแล้วครับ\n"
            f"⏱ {meeting_date} {time_str}\n\n"
            f"⚙️ กำลังรวบรวมรายงานจาก 11 แผนก...\n"
            f"(คาดว่าได้รายงานภายใน 1-2 นาทีครับ)"
        )
    except Exception:
        pass

    # ── รัน agents แบบ parallel ──────────────────────────────────
    reports = []
    agent_ids = list(AGENT_MEETING_CONFIG.keys())

    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="meeting") as executor:
        futures = {executor.submit(_run_agent_weekly, aid): aid for aid in agent_ids}
        for future in as_completed(futures, timeout=AGENT_TIMEOUT + 10):
            aid = futures[future]
            try:
                result = future.result(timeout=AGENT_TIMEOUT)
                reports.append(result)
                print(f"[Meeting] {aid} ✓")
            except FutTimeout:
                print(f"[Meeting] {aid} TIMEOUT")
                cfg = AGENT_MEETING_CONFIG[aid]
                reports.append({
                    "agent_id": aid, "name": cfg["name"],
                    "icon": cfg["icon"], "role": cfg["role"],
                    "report": "ไม่ได้รับรายงาน (timeout)"
                })
            except Exception as e:
                print(f"[Meeting] {aid} ERROR: {e}")
                cfg = AGENT_MEETING_CONFIG[aid]
                reports.append({
                    "agent_id": aid, "name": cfg["name"],
                    "icon": cfg["icon"], "role": cfg["role"],
                    "report": f"เกิดข้อผิดพลาด: {e}"
                })

    # เรียงตาม order ที่กำหนด
    order = list(AGENT_MEETING_CONFIG.keys())
    reports.sort(key=lambda r: order.index(r["agent_id"]) if r["agent_id"] in order else 99)

    print(f"[Meeting] All {len(reports)} agents reported — synthesizing...")
    log_agent("meeting", "rocket", f"[meeting] synthesizing {len(reports)} reports")

    # ── Rocket synthesize → push LINE ────────────────────────────
    chunks = _synthesize_meeting(reports, meeting_date)
    sent   = []

    try:
        from scheduler import push_message
        for i, chunk in enumerate(chunks):
            if push_message(chunk):
                sent.append(chunk)
                if len(chunks) > 1:
                    print(f"[Meeting] Pushed part {i+1}/{len(chunks)}")
    except Exception as e:
        print(f"[Meeting] push error: {e}")

    # บันทึกลง Google Sheets
    try:
        from drive_api import save_report
        full_report = "\n\n---\n\n".join(chunks)
        save_report("meeting", f"Monday All-Hands {meeting_date}", full_report)
    except Exception:
        pass

    log_agent("rocket", "user", f"[meeting] done — {len(sent)} messages sent", "")
    print(f"[Meeting] Complete — {len(sent)} LINE messages sent")
    return sent
