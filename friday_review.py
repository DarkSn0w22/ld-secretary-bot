"""
Friday Weekly Review — OWNDAYS AI Office
==========================================
ทุกวันศุกร์ 16:00 น.

Step 1  Guard  รีวิวผลงานของทุก agent ในสัปดาห์นั้น
        — ดึง agent logs + dashboard data ตลอดสัปดาห์
        — ประเมิน quality / completeness / issues

Step 2  Atlas  รับ Guard report → วางแผนงานและทิศทาง 1-2 เดือนข้างหน้า
        — strategic direction
        — resource plan
        — OKR / focus areas

Step 3  Rocket รวมทั้งสองส่วนเป็น "สรุปสัปดาห์ + แผนล่วงหน้า" → push LINE
        — บันทึกลง Google Sheets ด้วย

Cost: ~3-4 Sonnet/Haiku calls ≈ ฿0.30/สัปดาห์
"""

import os
from datetime import datetime, timedelta
import pytz
import anthropic
from models_config import get_model
from agent_log import log_agent, get_logs

BANGKOK_TZ    = pytz.timezone("Asia/Bangkok")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")
claude         = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_week_logs() -> str:
    """รวบรวม agent activity log ตลอด 7 วันที่ผ่านมา"""
    now         = datetime.now(BANGKOK_TZ)
    week_ago_ep = (now - timedelta(days=7)).timestamp()

    raw = get_logs(n=300, since_epoch=week_ago_ep)

    # กรองเฉพาะ agent → agent calls (ไม่ใช่ poll/ping)
    calls = [
        l for l in raw
        if l.get("from") not in {"dashboard", "scheduler", "system"}
        and l.get("to")   not in {"dashboard", "system"}
        and (l.get("msg") or l.get("res"))
    ]

    if not calls:
        return "ไม่มี agent activity log ในสัปดาห์นี้ (อาจเพิ่งรีสตาร์ท)"

    # สรุปเป็นข้อความ
    lines = [f"Agent Activity Log — 7 วันที่ผ่านมา ({len(calls)} interactions):\n"]
    for c in calls[-60:]:    # max 60 รายการล่าสุด
        ts  = f"{c.get('date','')} {c.get('ts','')}"
        frm = c.get("from","?").upper()
        to  = c.get("to","?").upper()
        msg = c.get("msg","")[:100]
        res = c.get("res","")[:120]
        st  = "✅" if c.get("status") == "ok" else "❌"
        line = f"{st} [{ts}] {frm}→{to}: {msg}"
        if res:
            line += f"\n   └─ {res}"
        lines.append(line)
    return "\n".join(lines)


def _get_dashboard_week_summary() -> str:
    """ดึง KPI snapshot ปัจจุบัน + historical trend"""
    parts = []
    try:
        from dashboard_api import fetch_dashboard
        s = fetch_dashboard("survey")
        c = fetch_dashboard("cost")
        o = fetch_dashboard("oar")
        parts.append(
            f"Survey: avg={s.get('overall_avg',0):.2f}, responses={s.get('total_responses',0)}\n"
            f"Cost: actual={c.get('actual',0):,.0f} / budget={c.get('budget',1):,.0f} "
            f"({c.get('actual',0)/(c.get('budget',1) or 1)*100:.1f}%)\n"
            f"OAR: total={o.get('total',0)}"
        )
    except Exception as e:
        parts.append(f"Dashboard data error: {e}")

    try:
        from historical_memory import get_sigma_context
        parts.append("\n" + get_sigma_context(lookback_days=7))
    except Exception:
        pass

    return "\n".join(parts)


# ── Step 1: Guard review ──────────────────────────────────────────────────────

def _run_guard_review(week_logs: str, kpi_summary: str) -> str:
    """Guard ประเมินผลงานทีมตลอดสัปดาห์"""

    now      = datetime.now(BANGKOK_TZ)
    day_th   = ["จันทร์","อังคาร","พุธ","พฤหัส","ศุกร์","เสาร์","อาทิตย์"]
    week_str = f"สัปดาห์ {now.strftime('%d/%m')} — {(now - timedelta(days=4)).strftime('%d/%m/%Y')}"

    system = (
        "คุณคือ Guard QA Specialist & Performance Reviewer ของ OWNDAYS L&D Thailand\n"
        "มีประสบการณ์ตรวจสอบคุณภาพงานมา 10 ปี\n"
        "รีวิวผลงานทีม AI ทั้งสัปดาห์อย่างเป็นกลาง มองทั้งจุดดีและจุดที่ต้องพัฒนา\n"
        "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
    )
    prompt = (
        f"รีวิวผลงานทีม L&D AI — {week_str}\n\n"
        f"=== KPI Dashboard สัปดาห์นี้ ===\n{kpi_summary}\n\n"
        f"=== Agent Activity Log ===\n{week_logs[:3000]}\n\n"
        "กรุณาจัดทำ Weekly Performance Review:\n\n"
        "1. ภาพรวมสัปดาห์ — ทีมทำงานได้ดีแค่ไหน (1-2 ประโยค)\n\n"
        "2. Agent ที่ทำงานโดดเด่น — ระบุชื่อ + สิ่งที่ทำได้ดี\n\n"
        "3. จุดที่ต้องปรับปรุง — agent ไหน / เรื่องอะไร / ผลกระทบคืออะไร\n\n"
        "4. KPI Alert — metric ใดที่น่าเป็นห่วงมากที่สุด (ถ้ามี)\n\n"
        "5. คะแนนทีมประจำสัปดาห์ — X/10 พร้อมเหตุผลสั้น\n\n"
        "ยาวไม่เกิน 600 ตัวอักษร ลงท้ายครับ"
    )

    try:
        resp = claude.messages.create(
            model=get_model("guard"),
            max_tokens=700,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        result = resp.content[0].text.strip()
        log_agent("friday_review", "guard", "[review] weekly performance", result[:300])
        return result
    except Exception as e:
        log_agent("friday_review", "guard", "[review] error", str(e), status="error")
        return f"Guard review error: {e}"


# ── Step 2: Atlas strategic plan ─────────────────────────────────────────────

def _run_atlas_plan(guard_review: str, kpi_summary: str) -> str:
    """Atlas รับ Guard review → วางแผนกลยุทธ์ 1-2 เดือนข้างหน้า"""

    now       = datetime.now(BANGKOK_TZ)
    month_1   = (now + timedelta(days=30)).strftime("%B %Y")
    month_2   = (now + timedelta(days=60)).strftime("%B %Y")

    system = (
        "คุณคือ Atlas Strategic L&D Consultant ของ OWNDAYS Thailand\n"
        "มองภาพใหญ่ 30-90 วัน เชื่อมโยงข้อมูลกับเป้าหมายธุรกิจ\n"
        "วางแผนที่ measurable และ implementable จริงๆ\n"
        "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
    )
    prompt = (
        f"วางแผนกลยุทธ์ L&D — {month_1} ถึง {month_2}\n\n"
        f"=== Guard Weekly Review (ผลงานสัปดาห์นี้) ===\n{guard_review}\n\n"
        f"=== KPI ปัจจุบัน ===\n{kpi_summary}\n\n"
        "กรุณาวางแผน Strategic Direction 1-2 เดือนข้างหน้า:\n\n"
        f"1. Focus Areas หลัก (เดือน {month_1})\n"
        "   — 2-3 เรื่องที่ต้องโฟกัสมากที่สุด พร้อมเหตุผลจากข้อมูล\n\n"
        f"2. แผนงาน (เดือน {month_2})\n"
        "   — ต่อยอดจากเดือนแรก ทิศทางระยะกลาง\n\n"
        "3. Resource ที่ต้องการ\n"
        "   — Trainer, budget, content, หรือ tool ที่ต้องเตรียม\n\n"
        "4. KPI เป้าหมาย 2 เดือน\n"
        "   — ตัวเลขที่อยากเห็น (survey, OAR, budget, sales-training correlation)\n\n"
        "5. Risk & Mitigation\n"
        "   — ความเสี่ยงที่มองเห็น + วิธีป้องกัน\n\n"
        "ยาวไม่เกิน 700 ตัวอักษร ลงท้ายครับ"
    )

    try:
        resp = claude.messages.create(
            model=get_model("atlas"),
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        result = resp.content[0].text.strip()
        log_agent("friday_review", "atlas", "[plan] 1-2 month strategy", result[:300])
        return result
    except Exception as e:
        log_agent("friday_review", "atlas", "[plan] error", str(e), status="error")
        return f"Atlas plan error: {e}"


# ── Step 3: Rocket compile + push LINE ───────────────────────────────────────

def _compile_and_push(guard_review: str, atlas_plan: str, user_id: str) -> list:
    """Rocket รวม 2 ส่วน → รายงาน LINE หลายข้อความ (ถ้ายาว)"""

    now        = datetime.now(BANGKOK_TZ)
    day_th     = ["จันทร์","อังคาร","พุธ","พฤหัส","ศุกร์","เสาร์","อาทิตย์"]
    date_str   = now.strftime(f"วัน{day_th[now.weekday()]}ที่ %d/%m/%Y")
    time_str   = now.strftime("%H:%M น.")
    month_1    = (now + timedelta(days=30)).strftime("%B %Y")
    month_2    = (now + timedelta(days=60)).strftime("%B %Y")

    system = (
        "คุณคือ Rocket เลขานุการ AI ของ Peanut (Regional L&D Manager)\n"
        "สรุปรายงานสัปดาห์ + แผนล่วงหน้าเพื่อส่ง LINE\n"
        "กฎเหล็ก: ห้ามใช้ Markdown (**##--) ใช้ plain text + emoji ลงท้าย 'ครับ'"
    )
    prompt = (
        f"วันนี้: {date_str} {time_str}\n\n"
        f"=== Guard Review (ผลงานสัปดาห์) ===\n{guard_review}\n\n"
        f"=== Atlas Plan ({month_1}–{month_2}) ===\n{atlas_plan}\n\n"
        "สรุปเป็นรายงาน LINE 2 ส่วน:\n\n"
        "ส่วนที่ 1 — สรุปสัปดาห์ (Guard):\n"
        "  บรรทัดแรก: 🛡️ Weekly Review — [วันที่]\n"
        "  ภาพรวมทีม, จุดดี, จุดปรับปรุง, คะแนน\n"
        "  ยาวไม่เกิน 600 ตัวอักษร\n\n"
        "ส่วนที่ 2 — แผนล่วงหน้า (Atlas):\n"
        f"  บรรทัดแรก: 🎯 Strategic Plan — {month_1}–{month_2}\n"
        "  Focus areas, KPI targets, risks\n"
        "  ยาวไม่เกิน 700 ตัวอักษร\n\n"
        "แยกส่วน 1 และ 2 ด้วยบรรทัดว่าง\n"
        "แต่ละส่วนลงท้ายด้วย 'ครับ'"
    )

    try:
        resp = claude.messages.create(
            model=get_model("scheduler"),
            max_tokens=1400,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        full_text = resp.content[0].text.strip()
    except Exception as e:
        full_text = (
            f"🛡️ Weekly Review — {date_str}\n\n{guard_review[:500]}\nครับ\n\n"
            f"🎯 Strategic Plan — {month_1}–{month_2}\n\n{atlas_plan[:600]}\nครับ"
        )
        print(f"[FridayReview] Rocket fallback: {e}")

    # แบ่ง 2 ส่วน (ก่อน / หลัง "🎯")
    parts = []
    if "🎯" in full_text:
        idx = full_text.index("🎯")
        p1  = full_text[:idx].strip()
        p2  = full_text[idx:].strip()
        if p1: parts.append(p1)
        if p2: parts.append(p2)
    else:
        # ถ้าแยกไม่ได้ แบ่ง chunk
        while full_text:
            parts.append(full_text[:4800])
            full_text = full_text[4800:]

    # Push to LINE
    sent = []
    try:
        from scheduler import push_message
        for part in parts:
            if push_message(part):
                sent.append(part)
    except Exception as pe:
        print(f"[FridayReview] push error: {pe}")

    log_agent("rocket", "user", "[friday_review] pushed", f"{len(sent)} messages")
    return sent


# ── Main ──────────────────────────────────────────────────────────────────────

def run_friday_review(user_id: str = None) -> dict:
    """
    Friday Weekly Review + Atlas Strategic Plan

    Returns:
        {ok, guard_review, atlas_plan, messages_sent}
    """
    if user_id is None:
        user_id = PEANUT_USER_ID

    now      = datetime.now(BANGKOK_TZ)
    date_str = now.strftime("%d/%m/%Y %H:%M น.")

    print(f"[FridayReview] Starting — {date_str}")
    log_agent("scheduler", "friday_review", f"[review] start {date_str}")

    # ── แจ้ง Peanut ก่อนว่ากำลังประมวลผล ──────────────────────
    try:
        from scheduler import push_message
        push_message(
            f"🛡️ Friday Review เริ่มแล้วครับ\n"
            f"⏱ {date_str}\n\n"
            f"⚙️ Guard กำลังรีวิวผลงานสัปดาห์นี้...\n"
            f"จากนั้น Atlas จะวางแผนล่วงหน้า 1-2 เดือน\n"
            f"(คาดว่าได้รายงานภายใน 1-2 นาทีครับ)"
        )
    except Exception:
        pass

    # ── ดึงข้อมูล ────────────────────────────────────────────────
    print("[FridayReview] Collecting week logs...")
    week_logs   = _get_week_logs()
    kpi_summary = _get_dashboard_week_summary()

    # ── Step 1: Guard ────────────────────────────────────────────
    print("[FridayReview] Guard reviewing...")
    guard_review = _run_guard_review(week_logs, kpi_summary)

    # ── Step 2: Atlas ────────────────────────────────────────────
    print("[FridayReview] Atlas planning...")
    atlas_plan = _run_atlas_plan(guard_review, kpi_summary)

    # ── Step 3: Rocket compile + push ────────────────────────────
    print("[FridayReview] Rocket compiling + pushing LINE...")
    sent = _compile_and_push(guard_review, atlas_plan, user_id)

    # ── บันทึกลง Sheets ─────────────────────────────────────────
    try:
        from drive_api import save_report
        combined = (
            f"=== GUARD WEEKLY REVIEW ===\n{guard_review}\n\n"
            f"=== ATLAS STRATEGIC PLAN ===\n{atlas_plan}"
        )
        save_report("friday_review", f"Friday Review {date_str}", combined)
    except Exception:
        pass

    log_agent("friday_review", "rocket",
              f"[review] complete — {len(sent)} messages", "")
    print(f"[FridayReview] Complete — {len(sent)} messages sent")

    return {
        "ok":            True,
        "guard_review":  guard_review,
        "atlas_plan":    atlas_plan,
        "messages_sent": len(sent),
    }
