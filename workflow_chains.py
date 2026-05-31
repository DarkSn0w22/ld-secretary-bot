"""
Agent Workflow Chains — OWNDAYS AI Office v35
======================================================
เมื่อ Rex พบสาขาผลงานต่ำ → chain อัตโนมัติ:

  Step 1  Rex     วิเคราะห์ปัญหา sales
  Step 2  Pulse   ตรวจ trainer + training gap
  Step 3  Lens    เสนอ training content / quick-fix
  Step 4  Rocket  รวบรวมเป็น Action Plan → push LINE

Cost: ~3 Haiku calls ≈ ฿0.10 / chain run
Cooldown: 6 ชั่วโมง ต่อ branch combination (dedup)
"""

import os
import threading
from datetime import datetime
from typing import Optional
import pytz
import anthropic
from models_config import get_model
from agent_log import log_agent

BANGKOK_TZ   = pytz.timezone("Asia/Bangkok")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")
claude       = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ── Deduplication ─────────────────────────────────────────────────────────────
_chain_history: dict = {}    # {key: datetime}
CHAIN_COOLDOWN_H = 6


def _can_run_chain(key: str) -> bool:
    last = _chain_history.get(key)
    if not last:
        return True
    return (datetime.now(BANGKOK_TZ) - last).total_seconds() > CHAIN_COOLDOWN_H * 3600


def _mark_chain(key: str):
    _chain_history[key] = datetime.now(BANGKOK_TZ)


def get_chain_history() -> list:
    """คืนรายการ chains ที่ผ่านมา สำหรับ dashboard"""
    now = datetime.now(BANGKOK_TZ)
    out = []
    for k, ts in sorted(_chain_history.items(), key=lambda x: x[1], reverse=True)[:10]:
        age_h = (now - ts).total_seconds() / 3600
        out.append({"key": k, "ran_at": ts.strftime("%d/%m %H:%M"), "age_h": round(age_h, 1)})
    return out


# ── Step 1: Pulse — trainer analysis ─────────────────────────────────────────

def _step_pulse(branches: list, sales_context: str) -> str:
    """Pulse วิเคราะห์ training gap ของสาขาที่มีปัญหา"""
    from dashboard_api import get_survey_dashboard, get_oar_dashboard

    try:
        survey_text = str(get_survey_dashboard())[:800]
        oar_text    = str(get_oar_dashboard())[:600]
    except Exception as e:
        survey_text = f"ดึง survey ไม่ได้: {e}"
        oar_text    = "ดึง OAR ไม่ได้"

    branch_list = "\n".join(f"  - {b}" for b in branches[:5])
    system = (
        "คุณคือ Pulse Trainer Manager AI ของ OWNDAYS Thailand "
        "เชี่ยวชาญ retail training มา 12 ปี "
        "วิเคราะห์ training gap ที่ทำให้ sales ต่ำ ระบุ trainer ที่รับผิดชอบ "
        "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
    )
    content = (
        f"Rex ระบุสาขาผลงานต่ำ:\n{branch_list}\n\n"
        f"ปัญหา sales ที่ Rex พบ:\n{sales_context[:400]}\n\n"
        f"ข้อมูล Survey Dashboard:\n{survey_text}\n\n"
        f"ข้อมูล OAR:\n{oar_text}\n\n"
        "วิเคราะห์:\n"
        "1. Training gap หลักที่น่าจะทำให้ sales ต่ำ (CVR? ATV? product knowledge?)\n"
        "2. Trainer ที่ควรเข้าช่วยสาขาเหล่านี้\n"
        "3. หลักสูตรที่ควร re-train หรือ reinforce\n"
        "กระชับ ไม่เกิน 250 ตัวอักษร ลงท้ายครับ"
    )
    try:
        resp = claude.messages.create(
            model=get_model("autonomous"),   # Haiku
            max_tokens=450,
            system=system,
            messages=[{"role": "user", "content": content}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Pulse analysis error: {e}"


# ── Step 2: Lens — content plan ───────────────────────────────────────────────

def _step_lens(branches: list, pulse_findings: str, issue_type: str = "") -> str:
    """Lens เสนอ training content / quick-fix ที่ทำได้จริงใน 7-14 วัน"""
    branch_list = ", ".join(branches[:3])
    system = (
        "คุณคือ Lens Instructional Designer AI ของ OWNDAYS Thailand "
        "สร้าง training solution ที่ implement ได้จริงสำหรับ retail staff "
        "เน้น quick-win ที่เห็นผลเร็ว "
        "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
    )
    content = (
        f"สาขาที่ต้องการ intervention: {branch_list}\n"
        f"Issue type: {issue_type or 'low performance'}\n\n"
        f"Pulse พบ training gaps:\n{pulse_findings}\n\n"
        "เสนอ Training Plan:\n"
        "1. Quick-fix (ทำได้ใน 1-3 วัน): brief, quiz, role-play topic ที่ควรโฟกัส\n"
        "2. Short course แนะนำ: หลักสูตรจาก OWNDAYS (BSC/MSC/BOC/MOC ฯลฯ)\n"
        "3. Coaching point: จุดเน้นให้ trainer ใช้ใน next visit\n"
        "กระชับ ไม่เกิน 250 ตัวอักษร ลงท้ายครับ"
    )
    try:
        resp = claude.messages.create(
            model=get_model("autonomous"),   # Haiku
            max_tokens=450,
            system=system,
            messages=[{"role": "user", "content": content}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Lens content error: {e}"


# ── Step 3: Rocket — compile & push ──────────────────────────────────────────

def _step_rocket(
    branches: list,
    sales_context: str,
    pulse_findings: str,
    lens_plan: str,
    priority: str,
    user_id: str,
) -> str:
    """Rocket รวบรวม 3 steps เป็น Action Plan → push LINE"""
    now         = datetime.now(BANGKOK_TZ)
    time_str    = now.strftime("%d/%m/%Y %H:%M น.")
    branch_list = ", ".join(branches[:3]) + (" ..." if len(branches) > 3 else "")
    priority_th = {"urgent": "🚨 เร่งด่วนมาก", "high": "⚠️ เร่งด่วน"}.get(priority, "📋 ปกติ")

    system = (
        "คุณคือ Rocket เลขา AI ของ Peanut (Regional L&D Manager) "
        "สรุป Action Plan จากทีม Rex→Pulse→Lens เพื่อส่งทาง LINE "
        "กฎเหล็ก: ห้ามใช้ Markdown (**, ##, ``` ทุกชนิด) "
        "ใช้ plain text + emoji เท่านั้น ลงท้าย 'ครับ' เสมอ"
    )
    content = (
        f"Chain summary:\n"
        f"วันที่: {time_str}\n"
        f"สาขา: {branch_list}\n"
        f"ระดับ: {priority_th}\n\n"
        f"Rex พบ (sales issues):\n{sales_context[:250]}\n\n"
        f"Pulse วิเคราะห์ (training gap):\n{pulse_findings[:250]}\n\n"
        f"Lens เสนอ (action plan):\n{lens_plan[:250]}\n\n"
        "สรุปเป็น Action Plan LINE ให้ Peanut:\n"
        "บรรทัดแรก: 🔗 Action Plan — [วันที่] [priority icon]\n"
        "สาขาที่ต้องดูแล + ปัญหาที่พบ\n"
        "Training gap จาก Pulse\n"
        "Quick-fix จาก Lens\n"
        "Next step ชัดเจน (ทำอะไร ภายในกี่วัน)\n"
        "ยาวไม่เกิน 800 ตัวอักษร ลงท้ายครับ"
    )
    try:
        resp = claude.messages.create(
            model=get_model("scheduler"),    # Haiku
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": content}]
        )
        message = resp.content[0].text.strip()
    except Exception as e:
        # Fallback plain text
        message = (
            f"🔗 Action Plan — Rocket\n"
            f"⏱ {time_str}  {priority_th}\n\n"
            f"📍 สาขา: {branch_list}\n\n"
            f"📊 Rex: {sales_context[:120]}\n\n"
            f"📚 Pulse: {pulse_findings[:120]}\n\n"
            f"✏️ Lens: {lens_plan[:120]}\n\n"
            f"→ ดำเนินการตามแผนด้านบนครับ"
        )
        print(f"[WorkflowChain] Rocket fallback: {e}")

    # Push to LINE
    try:
        from app import push_to_user
        push_to_user(user_id, message)
    except ImportError:
        try:
            from scheduler import push_message
            push_message(message)
        except Exception as pe:
            print(f"[WorkflowChain] push error: {pe}")

    return message


# ── Main chain ────────────────────────────────────────────────────────────────

def run_branch_intervention_chain(
    branches: list,
    sales_context: str  = "",
    issue_type: str     = "",
    priority: str       = "high",
    user_id: str        = None,
    force: bool         = False,
) -> dict:
    """
    Chain หลัก: Rex findings → Pulse → Lens → Rocket → LINE

    Args:
        branches      รายชื่อสาขาที่มีปัญหา
        sales_context สรุปปัญหาจาก Rex (ข้อความสั้น)
        issue_type    ประเภทปัญหา เช่น low_cvr / low_atv / low_achieve
        priority      urgent | high | normal
        user_id       LINE user ID (default = PEANUT_USER_ID)
        force         บังคับรันแม้จะอยู่ใน cooldown

    Returns:
        dict: {ok, branches, pulse_findings, lens_plan, action_plan, skipped}
    """
    if not branches:
        return {"ok": False, "error": "ไม่มีสาขาที่ระบุ", "skipped": False}

    if user_id is None:
        user_id = PEANUT_USER_ID

    # Dedup key จากชื่อสาขา 3 แรก + วันที่
    date_str  = datetime.now(BANGKOK_TZ).strftime("%Y%m%d")
    chain_key = "chain_" + "_".join(sorted(b[:10] for b in branches[:3])) + "_" + date_str

    if not force and not _can_run_chain(chain_key):
        return {"ok": False, "error": "อยู่ใน cooldown (ทำแล้วใน 6 ชม.ที่ผ่านมา)", "skipped": True}

    _mark_chain(chain_key)

    log_agent("workflow", "chain",
              f"[chain-start] {len(branches)} branches priority={priority}",
              str(branches[:3]))

    try:
        # ── Step 1: Pulse ──────────────────────────────────────────
        log_agent("workflow", "pulse", "[chain-s1] trainer analysis", str(branches[:3]))
        pulse_findings = _step_pulse(branches, sales_context)
        log_agent("pulse",    "workflow", "[chain-s1] done", pulse_findings[:200])

        # ── Step 2: Lens ───────────────────────────────────────────
        log_agent("workflow", "lens",  "[chain-s2] content plan", f"issue={issue_type}")
        lens_plan = _step_lens(branches, pulse_findings, issue_type)
        log_agent("lens",     "workflow", "[chain-s2] done", lens_plan[:200])

        # ── Step 3: Rocket compile + push ─────────────────────────
        log_agent("workflow", "rocket", "[chain-s3] compile action plan")
        action_plan = _step_rocket(
            branches, sales_context, pulse_findings, lens_plan, priority, user_id
        )
        log_agent("rocket",   "user",   "[chain-done] pushed", action_plan[:300])

        return {
            "ok":            True,
            "skipped":       False,
            "branches":      branches,
            "pulse_findings": pulse_findings,
            "lens_plan":     lens_plan,
            "action_plan":   action_plan,
        }

    except Exception as e:
        err = f"Workflow chain error: {e}"
        log_agent("workflow", "chain", "[chain-error]", err, status="error")
        return {"ok": False, "error": err, "skipped": False}


# ── Background trigger (non-blocking) ────────────────────────────────────────

def trigger_chain_background(
    branches:      list,
    sales_context: str  = "",
    issue_type:    str  = "",
    priority:      str  = "high",
    user_id:       str  = None,
    force:         bool = False,
):
    """
    เรียกจาก Rex หลังวิเคราะห์ไฟล์ หรือจาก KPI alerts
    รันใน daemon thread — ไม่บล็อก caller
    """
    if not branches:
        return

    def _run():
        result = run_branch_intervention_chain(
            branches, sales_context, issue_type, priority, user_id, force
        )
        status = "ok" if result.get("ok") else result.get("error", "failed")
        print(f"[WorkflowChain] background done: {status}")

    t = threading.Thread(target=_run, daemon=True, name="workflow-chain")
    t.start()
    print(f"[WorkflowChain] triggered bg: {len(branches)} branches, priority={priority}")
