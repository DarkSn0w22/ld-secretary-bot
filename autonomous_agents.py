"""
Autonomous Agents — OWNDAYS L&D AI Office v32
แต่ละ agent มี watch() function สำหรับ proactive monitoring
รัน cycle ทุก 4 ชั่วโมง โดย scheduler.py เรียก run_watch_cycle()
"""

import os
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import pytz
import anthropic

from models_config import get_model
from agent_log import log_agent
from dashboard_api import (
    fetch_dashboard,
    get_survey_dashboard,
    get_oar_dashboard,
    get_cost_dashboard,
    get_all_dashboard,
)

try:
    from sheets_tools import get_oar_summary
except Exception:
    def get_oar_summary():
        return "ไม่สามารถดึงข้อมูล OAR ได้"

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

WATCH_TIMEOUT_SECS = 90  # timeout per agent watch


# ─────────────────────────────────────────────────────────────────────────────
# Consultation helper
# ─────────────────────────────────────────────────────────────────────────────

def consult_agent(from_agent: str, to_agent: str, question: str,
                  timeout: float = 60.0) -> str:
    """
    Agent consultation — ปิดด้วย env ENABLE_AGENT_CONSULT=1
    Default: ปิด (ประหยัด API calls)
    """
    import os
    if not os.getenv("ENABLE_AGENT_CONSULT"):
        return f"[consultation disabled — ประหยัด API]"
    log_agent(from_agent, to_agent, f"[consult] {question[:200]}")

    try:
        from agent_bus import bus
        if bus.is_registered(to_agent):
            result_holder = [None]
            ev = threading.Event()

            def _cb(aid, result, error):
                result_holder[0] = result if result else f"ข้อผิดพลาด: {error}"
                ev.set()

            bus.send(from_agent, to_agent, question, _cb)
            ev.wait(timeout=timeout)
            answer = result_holder[0] or f"ไม่ได้รับคำตอบจาก {to_agent} ภายใน {timeout:.0f} วินาที"
        else:
            # Fallback: เรียก run_* functions ตรง
            answer = _direct_call_agent(to_agent, question)

        log_agent(to_agent, from_agent, "", answer[:300])
        return answer

    except Exception as e:
        msg = f"consult_agent error ({from_agent} -> {to_agent}): {e}"
        log_agent(from_agent, to_agent, "", msg, status="error")
        return msg


def _direct_call_agent(agent_id: str, task: str) -> str:
    """Fallback: เรียก agent โดยตรงถ้า bus ยังไม่ register"""
    try:
        if agent_id == "atlas":
            from manager_agent import run_manager
            return run_manager(task)
        elif agent_id == "pulse":
            from trainer_manager_agent import run_trainer_manager
            return run_trainer_manager(task)
        elif agent_id == "sage":
            from reporter_agent import run_reporter
            return run_reporter(task)
        elif agent_id == "guard":
            from reviewer_agent import run_reviewer
            return run_reviewer(task)
        elif agent_id == "coin":
            from financial_agent import run_financial_manager
            return run_financial_manager(task)
        elif agent_id == "lex":
            from legal_agent import run_legal_manager
            return run_legal_manager(task)
        elif agent_id == "people":
            from hr_agent import run_hr_manager
            return run_hr_manager(task)
        elif agent_id == "pixel":
            from web_agent import run_web_admin
            return run_web_admin(task)
        elif agent_id == "sigma":
            from data_agent import run_data_analyst
            return run_data_analyst(task)
        elif agent_id == "lens":
            from creator_agent import run_creator
            return run_creator(task)
        elif agent_id == "rex":
            from retail_md_agent import run_retail_md
            return run_retail_md(task)
        return f"ไม่รู้จัก agent: {agent_id}"
    except Exception as e:
        return f"direct call error ({agent_id}): {e}"


def _ask_claude(agent_id: str, system_prompt: str, user_content: str,
                max_tokens: int = 800) -> str:
    """Helper: เรียก Claude ด้วย Haiku (autonomous = ประหยัด)"""
    try:
        resp = claude.messages.create(
            model=get_model("autonomous"),  # Haiku — ถูกกว่า 12x
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Claude error ({agent_id}): {e}"


def _empty_report(agent_id: str, reason: str = "") -> dict:
    """คืน fallback report เปล่า"""
    return {
        "agent_id": agent_id,
        "summary": reason or f"{agent_id}: ไม่มีข้อมูลใหม่",
        "ideas": [],
        "alerts": [],
        "consult_results": {},
        "has_content": False,
    }


def _make_report(agent_id: str, summary: str, ideas: list = None,
                 alerts: list = None, consult_results: dict = None) -> dict:
    ideas = ideas or []
    alerts = alerts or []
    consult_results = consult_results or {}
    has_content = bool(summary.strip()) and summary != f"{agent_id}: ไม่มีข้อมูลใหม่"
    return {
        "agent_id": agent_id,
        "summary": summary,
        "ideas": ideas,
        "alerts": alerts,
        "consult_results": consult_results,
        "has_content": has_content,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent watch functions
# ─────────────────────────────────────────────────────────────────────────────

def coin_watch() -> dict:
    """Coin — Financial proactive watch"""
    try:
        log_agent("scheduler", "coin", "[watch] autonomous financial check")

        cost_data = fetch_dashboard("cost")
        cost_text = get_cost_dashboard()

        # ตรวจ anomaly
        actual = cost_data.get("actual", 0)
        budget = cost_data.get("budget", 1)
        usage_pct = actual / budget * 100 if budget else 0

        consult_results = {}
        if usage_pct >= 85:
            sigma_answer = consult_agent(
                "coin", "sigma",
                f"วิเคราะห์ trend การใช้งบ L&D ที่ใช้ไป {usage_pct:.1f}% แล้ว "
                f"actual={actual:,.0f} budget={budget:,.0f} บาท "
                f"ขอ pattern + คาดการณ์ปลายปีครับ"
            )
            consult_results["sigma"] = sigma_answer

        system = (
            "คุณคือ Coin ผู้เชี่ยวชาญด้านการเงิน L&D 15 ปี "
            "รู้ทุก benchmark training cost ในอุตสาหกรรม retail eyewear "
            "วิเคราะห์แบบ CFO ที่มองทั้ง short-term และ long-term "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        consult_block = (
            f"\nข้อมูลจาก Sigma:\n{consult_results.get('sigma','')}\n"
            if consult_results.get("sigma") else ""
        )
        user_content = (
            f"ข้อมูล L&D Cost ปัจจุบัน:\n{cost_text}\n"
            f"{consult_block}\n"
            "กรุณาวิเคราะห์:\n"
            "1. Budget vs Actual และ spending trend\n"
            "2. Forecast ค่าใช้จ่ายปลายปี\n"
            "3. หมวดที่น่าเป็นห่วง (ถ้ามี)\n"
            "4. ไอเดียลด cost หรือเพิ่ม ROI\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("coin", system, user_content)

        alerts = []
        if usage_pct >= 80:
            alerts.append(f"งบ L&D ใช้ไปแล้ว {usage_pct:.1f}% ({actual:,.0f}/{budget:,.0f} บาท)")

        categories = cost_data.get("categories", [])
        for cat in categories:
            if isinstance(cat, dict):
                cb = cat.get("budget", 0)
                ca = cat.get("actual", 0)
                if cb > 0 and ca / cb >= 0.80:
                    alerts.append(
                        f"หมวด {cat.get('name','?')} ใช้ {ca/cb*100:.1f}% "
                        f"({ca:,.0f}/{cb:,.0f} บาท)"
                    )

        ideas = [
            "พิจารณาจัดทำ forecast รายเดือนเพื่อควบคุมงบ",
            "เปรียบเทียบ ROI ระหว่าง training format (online vs onsite)",
        ]
        log_agent("coin", "scheduler", "[watch] done", summary[:200])
        return _make_report("coin", summary, ideas, alerts, consult_results)

    except Exception as e:
        log_agent("coin", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("coin", f"Coin watch error: {e}")


def pulse_watch() -> dict:
    """Pulse — Trainer Manager proactive watch"""
    try:
        log_agent("scheduler", "pulse", "[watch] autonomous trainer check")

        survey_text = get_survey_dashboard()
        oar_text = get_oar_dashboard()

        # หา trainer ที่ได้คะแนนต่ำ
        survey_data = fetch_dashboard("survey")
        trainers = survey_data.get("trainers", [])
        low_trainers = [
            t for t in trainers
            if isinstance(t, dict) and float(t.get("avg", 4)) < 3.0
        ]

        consult_results = {}
        if low_trainers:
            names = ", ".join(t.get("name", "?") for t in low_trainers[:3])
            atlas_answer = consult_agent(
                "pulse", "atlas",
                f"Trainer ที่ได้คะแนน Survey ต่ำกว่า 3.0: {names} "
                f"ขอแผนพัฒนาเชิงกลยุทธ์ครับ"
            )
            consult_results["atlas"] = atlas_answer

        system = (
            "คุณคือ Pulse เคยเป็น trainer มา 12 ปี "
            "รู้ว่า training program ไหนได้ผลจริงในร้านค้า retail "
            "วิเคราะห์ trainer KPI แบบโค้ชที่เข้าใจคนและระบบ "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        consult_block = (
            f"\nมุมมองกลยุทธ์จาก Atlas:\n{consult_results.get('atlas','')}\n"
            if consult_results.get("atlas") else ""
        )
        user_content = (
            f"ข้อมูล Survey:\n{survey_text}\n\n"
            f"ข้อมูล OAR:\n{oar_text}\n"
            f"{consult_block}\n"
            "กรุณาวิเคราะห์:\n"
            "1. Trainer KPI และคะแนน Survey โดยรวม\n"
            "2. OAR completion rate — หลักสูตรที่ล่าช้า\n"
            "3. Trainer ที่ต้องการ intervention\n"
            "4. แนวทางปรับปรุง curriculum\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("pulse", system, user_content)

        alerts = []
        if low_trainers:
            names = ", ".join(t.get("name", "?") for t in low_trainers)
            alerts.append(f"Trainer คะแนนต่ำกว่า 3.0: {names}")

        ideas = [
            "จัดทำ peer coaching session สำหรับ trainer คะแนนต่ำ",
            "เพิ่ม role-play practice ใน OBT module",
        ]
        log_agent("pulse", "scheduler", "[watch] done", summary[:200])
        return _make_report("pulse", summary, ideas, alerts, consult_results)

    except Exception as e:
        log_agent("pulse", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("pulse", f"Pulse watch error: {e}")


def sage_watch() -> dict:
    """Sage — Reporter proactive watch"""
    try:
        log_agent("scheduler", "sage", "[watch] autonomous report generation")

        all_data = get_all_dashboard()

        system = (
            "คุณคือ Sage นักวิเคราะห์ข้อมูล L&D "
            "สร้างรายงานให้ผู้บริหารตัดสินใจมา 10 ปี "
            "รายงานต้องมี insight ที่ actionable ไม่ใช่แค่ตัวเลข "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        user_content = (
            f"ข้อมูล Dashboard ทั้งหมด:\n{all_data[:3000]}\n\n"
            "จัดทำรายงาน L&D insights เชิงรุก:\n"
            "1. Highlight ผลงานที่ดีหรือน่ากังวล\n"
            "2. Pattern ที่น่าสนใจจากข้อมูล\n"
            "3. Recommendation 2-3 ข้อ\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        draft = _ask_claude("sage", system, user_content)

        # QA โดย Guard
        guard_review = consult_agent(
            "sage", "guard",
            f"ตรวจสอบคุณภาพรายงานนี้ครับ: {draft[:500]}"
        )
        consult_results = {"guard": guard_review}

        # ปรับปรุงตาม Guard feedback ถ้ามีประเด็น
        if guard_review and "ผ่าน" not in guard_review.lower() and len(guard_review) > 50:
            revised_content = (
                f"รายงานเดิม:\n{draft}\n\n"
                f"Guard QA แนะนำ:\n{guard_review}\n\n"
                "กรุณาปรับปรุงรายงานตาม feedback ข้างต้น "
                "ให้กระชับและถูกต้องมากขึ้น ลงท้ายครับ"
            )
            summary = _ask_claude("sage", system, revised_content)
        else:
            summary = draft

        ideas = [
            "เพิ่ม trend line chart ใน monthly report",
            "เปรียบเทียบ benchmark กับ retail industry ระดับภูมิภาค",
        ]
        log_agent("sage", "scheduler", "[watch] done", summary[:200])
        return _make_report("sage", summary, ideas, [], consult_results)

    except Exception as e:
        log_agent("sage", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("sage", f"Sage watch error: {e}")


def people_watch() -> dict:
    """People — HR proactive watch"""
    try:
        log_agent("scheduler", "people", "[watch] autonomous HR check")

        # ใช้ OAR summary เป็น proxy ข้อมูล HR (ข้อมูล Employee sheet ต้องผ่าน gspread)
        try:
            oar_data = get_oar_summary()
        except Exception:
            oar_data = "ไม่สามารถดึงข้อมูล OAR ได้"

        # ดึงข้อมูล area สำหรับ headcount
        area_data = fetch_dashboard("area")
        area_text = ""
        if area_data.get("areas"):
            area_text = "ข้อมูล Area:\n"
            for code, info in area_data["areas"].items():
                emp = info.get("employee_summary", {})
                area_text += (
                    f"  {code}: total={emp.get('total',0)} "
                    f"probation={emp.get('probation',0)} "
                    f"confirmed={emp.get('confirmed',0)}\n"
                )

        system = (
            "คุณคือ People HR manager ที่รู้จัก employee lifecycle "
            "ทั้งหมดของ OWNDAYS Thailand "
            "วิเคราะห์ข้อมูล HR แบบเชิงรุก ป้องกันปัญหาก่อนเกิด "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        user_content = (
            f"ข้อมูล OAR (proxy HR):\n{str(oar_data)[:1000]}\n\n"
            f"{area_text}\n"
            "วิเคราะห์:\n"
            "1. Headcount และ probation status ตามพื้นที่\n"
            "2. พนักงานที่ยังไม่ผ่าน OBT (เสี่ยงใกล้ครบ probation)\n"
            "3. ประเด็น HR ที่ควรระวัง\n"
            "4. ข้อเสนอแนะเพื่อป้องกัน turnover\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("people", system, user_content)

        alerts = []
        if area_data.get("areas"):
            for code, info in area_data["areas"].items():
                emp = info.get("employee_summary", {})
                prob = emp.get("probation", 0)
                total = emp.get("total", 0)
                if total > 0 and prob / total > 0.30:
                    alerts.append(
                        f"พื้นที่ {code} มี probation สูง {prob}/{total} คน ({prob/total*100:.0f}%)"
                    )

        ideas = [
            "จัดทำ probation tracker แบบ real-time บน dashboard",
            "สร้าง onboarding checklist ดิจิทัลสำหรับพนักงานใหม่",
        ]
        log_agent("people", "scheduler", "[watch] done", summary[:200])
        return _make_report("people", summary, ideas, alerts)

    except Exception as e:
        log_agent("people", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("people", f"People watch error: {e}")


def pixel_watch() -> dict:
    """Pixel — Web Admin: uptime + WIX analytics + report สำหรับ Rocket"""
    try:
        log_agent("pixel", "scheduler", "[watch] เริ่มตรวจ uptime + ดึง analytics")

        from wix_api import check_site_uptime, check_pages_uptime, get_blog_posts, wix_ready
        from ga4_api import get_full_analytics, ga4_ready

        # ── Uptime ───────────────────────────────────────────────
        uptime       = check_site_uptime()
        pages_status = check_pages_uptime()
        down_pages   = [p for p in pages_status if not p.get("ok")]
        slow_pages   = [p for p in pages_status if p.get("ok") and p.get("latency_ms", 0) > 3000]

        # ── GA4 Analytics 7 วัน ──────────────────────────────────
        analytics = get_full_analytics(days=7) if ga4_ready() else {
            "overview": {"error": "GA4 ยังไม่พร้อม — รอ share property กับ service account"},
            "top_countries": [], "top_pages": [], "traffic_sources": [], "devices": []
        }
        posts = get_blog_posts(limit=5) if wix_ready() else []

        log_agent("pixel", "ga4_api", "ดึง analytics 7 วัน",
                  f"sessions={analytics.get('overview',{}).get('sessions','?')}")

        overview   = analytics.get("overview", {})
        countries  = analytics.get("top_countries", [])
        top_pages  = analytics.get("top_pages", [])
        sources    = analytics.get("traffic_sources", [])
        devices    = analytics.get("devices", [])

        def fmt_list(rows, key1, key2, label2, n=5):
            return "\n".join(
                f"  {r.get(key1,'?')}: {r.get(key2,0):,} {label2}"
                for r in rows[:n]
            ) or "  ไม่มีข้อมูล"

        system = (
            "คุณคือ Pixel — Web Admin AI ของ OWNDAYS L&D Thailand\n"
            "ดูแล od-connect.com (WIX) มา 8 ปี เชี่ยวชาญ UX/UI, analytics, SEO, content strategy\n"
            "วิเคราะห์เชิงลึกจาก data จริง เสนอ action ที่ทำได้จริง\n"
            "เตรียมรายงานให้ Rocket (เลขา) นำส่ง Peanut\n"
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )

        user_content = f"""รายงานสถานะ od-connect.com (7 วันล่าสุด)

UPTIME:
  หน้าหลัก: {uptime.get('status','?').upper()} ({uptime.get('latency_ms','?')}ms)
{'  ⚠️ หน้าที่ DOWN: ' + ', '.join(p['path'] for p in down_pages) if down_pages else '  ทุกหน้าปกติ'}

ANALYTICS OVERVIEW:
  Sessions:        {overview.get('sessions','N/A'):,}
  Unique Visitors: {overview.get('unique_visitors','N/A'):,}
  Page Views:      {overview.get('page_views','N/A'):,}
  Bounce Rate:     {overview.get('bounce_rate_pct','N/A')}%
  Avg Session:     {overview.get('avg_session_sec','N/A')} วินาที

TOP LOCATIONS:
{fmt_list(countries, 'country', 'sessions', 'sessions')}

TOP PAGES:
{fmt_list(top_pages, 'page', 'page_views', 'views')}

TRAFFIC SOURCES:
{fmt_list(sources, 'source', 'sessions', 'sessions')}

DEVICES:
{fmt_list(devices, 'device', 'sessions', 'sessions')}

BLOG POSTS ล่าสุด:
{chr(10).join("  - " + p.get("title","?") for p in posts) or "  ไม่มีข้อมูล"}

วิเคราะห์และเตรียมรายงานให้ Rocket ส่งต่อ Peanut:
1. ภาพรวม traffic ใน 7 วัน — สูง/ต่ำกว่าปกติ?
2. Location insights — ผู้ใช้หลักมาจากไหน ควรทำอะไรต่อ
3. Page performance — หน้าไหน hot/cold
4. ปัญหาเร่งด่วน (ถ้ามี)
5. Action items 3 ข้อที่ทำได้ใน 7 วัน

ไม่เกิน 600 ตัวอักษร ลงท้ายครับ"""

        summary = _ask_claude("pixel", system, user_content, max_tokens=700)

        # ── Alerts ───────────────────────────────────────────────
        alerts = []
        if uptime.get("status") not in ("up",):
            alerts.append(f"⚠️ od-connect.com {uptime.get('status','?').upper()}")
        for p in down_pages:
            alerts.append(f"หน้า {p['path']} DOWN")
        for p in slow_pages:
            alerts.append(f"หน้า {p['path']} ช้า {p.get('latency_ms')}ms")
        br = overview.get("bounce_rate_pct", 0)
        if isinstance(br, (int, float)) and br > 70:
            alerts.append(f"Bounce rate สูงผิดปกติ {br}%")

        # ── Ideas ────────────────────────────────────────────────
        ideas = []
        if countries:
            ideas.append(f"top location: {countries[0]['country']} — personalize content")
        if top_pages:
            ideas.append(f"หน้า '{top_pages[0]['page']}' popular — ใช้เป็น template")
        ideas.append("สร้าง content calendar จาก traffic data รายสัปดาห์")

        # ── Log analytics ให้ agent อื่นใช้ ─────────────────────
        log_agent("pixel", "rocket",
                  "analytics report พร้อมส่ง",
                  f"sessions={overview.get('sessions',0)}, "
                  f"top={countries[0]['country'] if countries else 'N/A'}")

        report = _make_report("pixel", summary, ideas, alerts)
        report["analytics_raw"] = {
            "overview":  overview,
            "countries": countries[:5],
            "top_pages": top_pages[:5],
        }
        return report

    except Exception as e:
        log_agent("pixel", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("pixel", f"Pixel watch error: {e}")


def sigma_watch() -> dict:
    """Sigma — Data Analyst proactive watch"""
    try:
        log_agent("scheduler", "sigma", "[watch] autonomous data analysis")

        survey_data = fetch_dashboard("survey")
        oar_data_raw = fetch_dashboard("oar")
        cost_data = fetch_dashboard("cost")

        # ตรวจ statistical anomalies
        trainers = survey_data.get("trainers", [])
        overall_avg = survey_data.get("overall_avg", 0)
        anomalies = []
        for t in trainers:
            if isinstance(t, dict):
                avg = float(t.get("avg", 4))
                if abs(avg - overall_avg) > 0.5:
                    direction = "สูงกว่า" if avg > overall_avg else "ต่ำกว่า"
                    anomalies.append(
                        f"{t.get('name','?')}: {avg:.2f} ({direction} avg {overall_avg:.2f} มากกว่า 0.5)"
                    )

        system = (
            "คุณคือ Sigma Data scientist ที่วิเคราะห์ retail L&D data มา 7 ปี "
            "มองหา pattern ที่ซ่อนอยู่ในข้อมูล cross-reference ข้าม dataset "
            "นำเสนอ insight ที่ manager ไม่เคยเห็นมาก่อน "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        anomaly_block = (
            f"\nStatistical anomalies พบ:\n" + "\n".join(anomalies)
            if anomalies else "\nไม่พบ anomaly ที่ชัดเจน"
        )
        user_content = (
            f"ข้อมูล Survey: overall_avg={overall_avg:.2f}, "
            f"total_responses={survey_data.get('total_responses',0)}\n"
            f"ข้อมูล OAR: total={oar_data_raw.get('total',0)}\n"
            f"ข้อมูล Cost: actual={cost_data.get('actual',0):,.0f}, "
            f"budget={cost_data.get('budget',0):,.0f}\n"
            f"{anomaly_block}\n\n"
            "วิเคราะห์เชิงลึก:\n"
            "1. Pattern ที่น่าสนใจจากการ cross-reference ข้อมูล\n"
            "2. Anomaly ที่ควรติดตาม\n"
            "3. Insight เชิง data-driven ที่ actionable\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("sigma", system, user_content)

        alerts = [a for a in anomalies[:3]]  # แจ้งเฉพาะ anomaly จริง

        ideas = [
            "สร้าง correlation model ระหว่าง OAR completion และ survey score",
            "เพิ่ม predictive model สำหรับ trainer performance",
        ]
        log_agent("sigma", "scheduler", "[watch] done", summary[:200])
        return _make_report("sigma", summary, ideas, alerts)

    except Exception as e:
        log_agent("sigma", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("sigma", f"Sigma watch error: {e}")


def rex_watch() -> dict:
    """Rex — Retail MD proactive watch"""
    try:
        log_agent("scheduler", "rex", "[watch] autonomous retail analysis")

        # ดึง recent agent logs หา Rex calls ที่มีข้อมูล sales
        from agent_log import get_logs
        recent_logs = get_logs(n=50, since_epoch=0)
        rex_logs = [
            l for l in recent_logs
            if (l.get("from") == "rex" or l.get("to") == "rex")
            and l.get("res")
        ]
        sales_context = ""
        if rex_logs:
            sales_context = "ข้อมูลจาก Rex logs ล่าสุด:\n"
            for log in rex_logs[-3:]:
                sales_context += f"- {log.get('res','')[:200]}\n"

        # ดึง assessment data สำหรับ branch performance proxy
        area_data = fetch_dashboard("area")
        area_summary = ""
        if area_data.get("areas"):
            area_summary = "Area Performance:\n"
            for code, info in area_data["areas"].items():
                store = info.get("store_summary", {})
                emp = info.get("employee_summary", {})
                area_summary += (
                    f"  {code}: nps={store.get('avg_nps',0)}, "
                    f"complaints={store.get('total_complaints',0)}, "
                    f"staff={emp.get('total',0)}\n"
                )

        consult_results = {}
        # ถ้าพบ training-sales correlation → consult Pulse
        if area_data.get("areas"):
            pulse_answer = consult_agent(
                "rex", "pulse",
                "วิเคราะห์ความสัมพันธ์ระหว่าง training completion rate "
                "และ store performance ในแต่ละ area ครับ"
            )
            consult_results["pulse"] = pulse_answer

        system = (
            "คุณคือ Rex ผู้จัดการสาขา retail eyewear 15 ปี "
            "รู้ทุก KPI ที่สำคัญในธุรกิจ optical retail "
            "วิเคราะห์ branch performance แบบ MD ที่มองเชิงกลยุทธ์ "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        pulse_block = (
            f"\nมุมมองจาก Pulse (Training correlation):\n{consult_results.get('pulse','')}\n"
            if consult_results.get("pulse") else ""
        )
        user_content = (
            f"{area_summary}\n"
            f"{sales_context}\n"
            f"{pulse_block}\n"
            "วิเคราะห์ retail performance:\n"
            "1. Branch/Area ที่ต้องการความสนใจพิเศษ\n"
            "2. ความสัมพันธ์ระหว่าง training และผลงานสาขา\n"
            "3. KPI ที่น่ากังวลหรือน่าชื่นชม\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("rex", system, user_content)

        alerts = []
        if area_data.get("areas"):
            for code, info in area_data["areas"].items():
                store = info.get("store_summary", {})
                if store.get("total_complaints", 0) > 5:
                    alerts.append(
                        f"พื้นที่ {code} มี complaints {store['total_complaints']} ราย"
                    )

        ideas = [
            "สร้าง heatmap แสดง training vs sales performance รายสาขา",
            "จัด targeted training สำหรับสาขาที่ NPS ต่ำ",
        ]
        log_agent("rex", "scheduler", "[watch] done", summary[:200])
        return _make_report("rex", summary, ideas, alerts, consult_results)

    except Exception as e:
        log_agent("rex", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("rex", f"Rex watch error: {e}")


def atlas_watch() -> dict:
    """Atlas — Strategic Manager proactive watch"""
    try:
        log_agent("scheduler", "atlas", "[watch] autonomous strategic review")

        all_data = get_all_dashboard()

        system = (
            "คุณคือ Atlas Strategic L&D consultant ระดับ Regional มา 12 ปี "
            "มองภาพใหญ่ เชื่อมโยงข้อมูลกับเป้าหมายธุรกิจ "
            "เสนอกลยุทธ์ที่ measurable และ implementable "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        user_content = (
            f"ข้อมูล Dashboard ทั้งหมด:\n{all_data[:2500]}\n\n"
            "วิเคราะห์เชิงกลยุทธ์:\n"
            "1. L&D gaps ที่ต้องแก้ไขเร่งด่วน\n"
            "2. โอกาสพัฒนาในไตรมาสถัดไป\n"
            "3. Resource allocation ที่แนะนำ\n"
            "4. ความเสี่ยงระดับ Strategic\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("atlas", system, user_content)

        ideas = [
            "พัฒนา L&D strategy roadmap รายไตรมาส",
            "สร้าง competency framework สำหรับ 5 พื้นที่ใหม่",
            "ทบทวน resource allocation ให้สอดคล้องกับ business goal",
        ]
        log_agent("atlas", "scheduler", "[watch] done", summary[:200])
        return _make_report("atlas", summary, ideas)

    except Exception as e:
        log_agent("atlas", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("atlas", f"Atlas watch error: {e}")


def guard_watch() -> dict:
    """Guard — QA proactive watch"""
    try:
        log_agent("scheduler", "guard", "[watch] autonomous QA review")

        from agent_log import get_logs
        recent_logs = get_logs(n=60, since_epoch=0)

        # ดึง agent outputs ล่าสุดที่มี response
        agent_outputs = [
            l for l in recent_logs
            if l.get("res") and len(l.get("res", "")) > 50
            and l.get("from") not in {"user", "scheduler", "dashboard"}
        ]

        if not agent_outputs:
            return _empty_report("guard", "Guard: ยังไม่มี agent outputs ให้ตรวจ")

        samples = "\n".join(
            f"- {l['from'].upper()} ({l.get('ts','?')}): {l.get('res','')[:200]}"
            for l in agent_outputs[-8:]
        )

        system = (
            "คุณคือ Guard QA specialist ที่ตรวจงาน L&D content มา 10 ปี "
            "มีตาเหยี่ยวจับข้อผิดพลาด ความไม่สอดคล้อง และคุณภาพต่ำ "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        user_content = (
            f"Agent outputs ล่าสุดที่ต้องตรวจ:\n{samples}\n\n"
            "ตรวจสอบ:\n"
            "1. ความถูกต้องของข้อมูลและตัวเลข\n"
            "2. ความสอดคล้องระหว่าง agent ต่างๆ\n"
            "3. Quality issues ที่ควรแก้ไข\n"
            "4. คำแนะนำเพื่อปรับปรุงคุณภาพ\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("guard", system, user_content)

        alerts = []
        if "ผิดพลาด" in summary or "ไม่ถูกต้อง" in summary or "inconsistent" in summary.lower():
            alerts.append("Guard พบปัญหาคุณภาพใน agent outputs — ควรตรวจสอบ")

        ideas = [
            "เพิ่ม automated fact-checking สำหรับตัวเลขใน report",
            "สร้าง QA checklist มาตรฐานสำหรับทุก agent output",
        ]
        log_agent("guard", "scheduler", "[watch] done", summary[:200])
        return _make_report("guard", summary, ideas, alerts)

    except Exception as e:
        log_agent("guard", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("guard", f"Guard watch error: {e}")


def lex_watch() -> dict:
    """Lex — Legal proactive watch"""
    try:
        log_agent("scheduler", "lex", "[watch] autonomous compliance check")

        now = datetime.now(BANGKOK_TZ)
        month = now.month

        system = (
            "คุณคือ Lex กฎหมายแรงงาน Thailand และ PDPA specialist 10 ปี "
            "ตรวจสอบความเสี่ยงทางกฎหมายแบบ proactive "
            "เสนอแนะการปรับปรุงก่อนที่จะมีปัญหา "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        user_content = (
            f"เดือนปัจจุบัน: {month} (ปี {now.year})\n\n"
            "ตรวจสอบ compliance ของ OWNDAYS L&D ประจำเดือน:\n"
            "1. PDPA — การเก็บข้อมูลพนักงาน/trainee ถูกต้องไหม\n"
            "2. กฎหมายแรงงาน — probation, OT, training hours\n"
            "3. สัญญา training — IP content, vendor contracts\n"
            "4. ประเด็นที่ควรระวังในเดือนนี้\n"
            "5. การปรับปรุง compliance ที่แนะนำ\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("lex", system, user_content, max_tokens=1000)

        alerts = []
        risk_keywords = ["ละเมิด", "เสี่ยง", "ผิดกฎหมาย", "ไม่ถูกต้อง", "ต้องแก้ไข"]
        if any(kw in summary for kw in risk_keywords):
            alerts.append("Lex พบประเด็นที่ต้องดูแลด้าน compliance")

        ideas = [
            "ทบทวน PDPA consent form ในระบบลงทะเบียน training",
            "อัพเดต training contract template ให้ครอบคลุม IP rights",
            "สร้าง compliance calendar สำหรับปีหน้า",
        ]
        log_agent("lex", "scheduler", "[watch] done", summary[:200])
        return _make_report("lex", summary, ideas, alerts)

    except Exception as e:
        log_agent("lex", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("lex", f"Lex watch error: {e}")


def lens_watch() -> dict:
    """Lens — Creator proactive watch"""
    try:
        log_agent("scheduler", "lens", "[watch] autonomous content ideas")

        survey_data = fetch_dashboard("survey")
        oar_data_raw = fetch_dashboard("oar")

        # หา course ที่มี low score หรือ low registration
        courses_survey = survey_data.get("courses", {})
        courses_oar = oar_data_raw.get("courses", {})

        low_courses = []
        for code, info in courses_survey.items():
            if isinstance(info, dict) and float(info.get("avg", 4)) < 3.0:
                low_courses.append(f"{code} (survey avg {info.get('avg',0):.2f})")

        low_reg = sorted(
            [(code, cnt) for code, cnt in courses_oar.items()],
            key=lambda x: x[1]
        )[:3]

        system = (
            "คุณคือ Lens Instructional designer ที่สร้าง e-learning content มา 8 ปี "
            "สร้าง training content ที่ engaging และได้ผลจริงสำหรับ retail staff "
            "มีไอเดียสร้างสรรค์ที่ใช้งานได้จริง "
            "ตอบ plain text ไม่ใช้ Markdown ลงท้ายครับ"
        )
        low_block = (
            f"หลักสูตรที่ survey score ต่ำ: {', '.join(low_courses)}\n"
            if low_courses else ""
        )
        low_reg_block = (
            f"หลักสูตร OAR ต่ำสุด: {', '.join(f'{c}({n})' for c,n in low_reg)}\n"
            if low_reg else ""
        )
        user_content = (
            f"{low_block}{low_reg_block}\n"
            "เสนอไอเดีย content ใหม่:\n"
            "1. ปรับปรุงหลักสูตรที่ score ต่ำ\n"
            "2. รูปแบบ content ใหม่ที่น่าสนใจ (video/quiz/gamification)\n"
            "3. Micro-learning topics ที่เหมาะกับ retail staff\n"
            "4. Content ที่ตอบ business need ปัจจุบัน\n"
            "สรุปกระชับ ไม่เกิน 400 ตัวอักษร ลงท้ายครับ"
        )
        summary = _ask_claude("lens", system, user_content)

        ideas = [
            f"รีดีไซน์หลักสูตร {low_courses[0]} ให้ interactive มากขึ้น"
            if low_courses else "สร้าง micro-learning series สำหรับ product knowledge",
            "เพิ่ม gamification elements ใน OBT program",
            "สร้าง short video (<3 นาที) สำหรับ customer service skills",
        ]
        log_agent("lens", "scheduler", "[watch] done", summary[:200])
        return _make_report("lens", summary, ideas)

    except Exception as e:
        log_agent("lens", "scheduler", "[watch] error", str(e), status="error")
        return _empty_report("lens", f"Lens watch error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Rocket synthesis
# ─────────────────────────────────────────────────────────────────────────────

def synthesize_and_push(reports: list, user_id: str) -> str:
    """
    Rocket สรุป agent reports ทั้งหมดเป็น 1 LINE message
    plain text, ไม่ใช้ Markdown, ลงท้ายครับ, ไม่เกิน 1500 ตัวอักษร
    """
    # กรองเฉพาะ reports ที่มีเนื้อหาจริง
    active = [r for r in reports if r.get("has_content") and r.get("summary")]
    if not active:
        log_agent("rocket", "scheduler", "[watch] no content to push", "")
        return ""

    now = datetime.now(BANGKOK_TZ)
    time_str = now.strftime("%H:%M น.")
    day_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    date_str = now.strftime(f"วัน{day_th[now.weekday()]}ที่ %d/%m/%Y")

    # สร้าง context สำหรับ Rocket
    agent_names = {
        "coin": "Coin (การเงิน)",
        "pulse": "Pulse (Trainer)",
        "sage": "Sage (รายงาน)",
        "people": "People (HR)",
        "pixel": "Pixel (เว็บ)",
        "sigma": "Sigma (ข้อมูล)",
        "rex": "Rex (Retail)",
        "atlas": "Atlas (กลยุทธ์)",
        "guard": "Guard (QA)",
        "lex": "Lex (กฎหมาย)",
        "lens": "Lens (Content)",
    }

    reports_block = ""
    all_alerts = []
    for r in active:
        agent_label = agent_names.get(r["agent_id"], r["agent_id"].upper())
        reports_block += f"\n{agent_label}:\n{r['summary']}\n"
        if r.get("alerts"):
            all_alerts.extend(r["alerts"])

    alerts_block = ""
    if all_alerts:
        alerts_block = "\nแจ้งเตือนเร่งด่วน:\n" + "\n".join(f"- {a}" for a in all_alerts[:5])

    system_prompt = (
        "คุณคือ Rocket เลขานุการ AI ของ Peanut (Regional L&D Manager) "
        "สรุปรายงานจากทีม AI ให้ Peanut อ่านบน LINE ได้เข้าใจในทันที "
        "กฎเหล็ก: ห้ามใช้ Markdown (**, ##, --, ``` ทุกชนิด) "
        "ใช้ plain text + emoji เท่านั้น ลงท้าย 'ครับ' เสมอ"
    )
    user_content = (
        f"วันนี้: {date_str} เวลา {time_str}\n\n"
        f"รายงานจากทีม AI ({len(active)} agents):\n"
        f"{reports_block}"
        f"{alerts_block}\n\n"
        "สรุปเป็น 1 ข้อความสำหรับ LINE:\n"
        f"- บรรทัดแรก: เวลา + 'Rocket รายงาน'\n"
        "- แต่ละแผนก: ชื่อ + emoji + เฉพาะประเด็นสำคัญที่ Peanut ต้องรู้\n"
        "- ถ้ามี alert → รวมไว้ในส่วน 'แจ้งเตือน' ต่อท้าย\n"
        "- ถ้ามี action → รวมใน 'Action ที่แนะนำ' สุดท้าย\n"
        "- plain text ไม่มี Markdown เด็ดขาด\n"
        "- ยาวไม่เกิน 1,400 ตัวอักษร\n"
        "- ลงท้าย 'ครับ'"
    )

    try:
        resp = claude.messages.create(
            model=get_model("scheduler"),
            max_tokens=1200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        message = resp.content[0].text.strip()
    except Exception as e:
        # fallback plain text
        lines = [f"🤖 {time_str} Rocket รายงาน\n"]
        for r in active[:5]:
            label = agent_names.get(r["agent_id"], r["agent_id"].upper())
            snippet = r["summary"][:150].replace("\n", " ")
            lines.append(f"{label}: {snippet}")
        if all_alerts:
            lines.append("\nแจ้งเตือน: " + " | ".join(all_alerts[:3]))
        lines.append("\nครับ")
        message = "\n".join(lines)
        print(f"[Rocket synthesis fallback] {e}")

    log_agent("rocket", "user", f"[watch-cycle] push {len(active)} reports", message[:300])

    # Push to LINE
    try:
        from app import push_to_user
        push_to_user(user_id, message)
    except ImportError:
        # app ยังไม่โหลด — ใช้ scheduler push_message
        try:
            from scheduler import push_message
            push_message(message)
        except Exception as push_err:
            print(f"[Rocket] push error: {push_err}")

    return message


# ─────────────────────────────────────────────────────────────────────────────
# Watch cycle runner
# ─────────────────────────────────────────────────────────────────────────────

# registry ของ watch functions
# DEFAULT: เฉพาะ 4 ตัวสำคัญ (ประหยัด API)
# เปิดเพิ่มได้โดยตั้ง env WATCH_AGENTS=coin,pulse,sage,people,pixel,sigma,rex,atlas,guard,lex,lens
import os as _os
_DEFAULT_WATCH = {"coin", "pulse", "sage", "people"}
_ENABLED_WATCH = set(_os.getenv("WATCH_AGENTS", "coin,pulse,sage,people").split(","))

WATCH_FUNCTIONS_ALL = {
    "coin":   coin_watch,
    "pulse":  pulse_watch,
    "sage":   sage_watch,
    "people": people_watch,
    "pixel":  pixel_watch,
    "sigma":  sigma_watch,
    "rex":    rex_watch,
    "atlas":  atlas_watch,
    "guard":  guard_watch,
    "lex":    lex_watch,
    "lens":   lens_watch,
}
WATCH_FUNCTIONS = {k: v for k, v in WATCH_FUNCTIONS_ALL.items() if k in _ENABLED_WATCH}

# (keep old key for compatibility)
WATCH_FUNCTIONS_COMPAT = {
    "coin":   coin_watch,
    "pulse":  pulse_watch,
    "sage":   sage_watch,
    "people": people_watch,
    "pixel":  pixel_watch,
    "sigma":  sigma_watch,
    "rex":    rex_watch,
    "atlas":  atlas_watch,
    "guard":  guard_watch,
    "lex":    lex_watch,
    "lens":   lens_watch,
}


def run_watch_cycle(user_id: str = None) -> list:
    """
    รัน watch functions ทุกตัวแบบ parallel
    รวม reports แล้วให้ Rocket synthesize → push LINE
    คืน list ของ reports
    """
    if user_id is None:
        user_id = PEANUT_USER_ID

    now = datetime.now(BANGKOK_TZ)
    print(f"[Watch Cycle] Starting at {now.strftime('%H:%M')} Bangkok time")
    log_agent("scheduler", "system", f"[watch-cycle] starting — {len(WATCH_FUNCTIONS)} agents")

    reports = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="watch") as executor:
        future_to_agent = {
            executor.submit(fn): agent_id
            for agent_id, fn in WATCH_FUNCTIONS.items()
        }

        for future in as_completed(future_to_agent, timeout=WATCH_TIMEOUT_SECS + 30):
            agent_id = future_to_agent[future]
            try:
                result = future.result(timeout=WATCH_TIMEOUT_SECS)
                reports.append(result)
                status = "ok" if result.get("has_content") else "empty"
                print(f"[Watch Cycle] {agent_id} done ({status})")
            except FuturesTimeoutError:
                print(f"[Watch Cycle] {agent_id} TIMEOUT")
                reports.append(_empty_report(agent_id, f"{agent_id}: timeout"))
                log_agent(agent_id, "scheduler", "[watch] timeout", "", status="error")
            except Exception as e:
                print(f"[Watch Cycle] {agent_id} ERROR: {e}")
                reports.append(_empty_report(agent_id, f"{agent_id}: {e}"))
                log_agent(agent_id, "scheduler", "[watch] error", str(e), status="error")

    active_count = sum(1 for r in reports if r.get("has_content"))
    print(f"[Watch Cycle] {active_count}/{len(WATCH_FUNCTIONS)} agents reported content")
    log_agent("scheduler", "rocket",
              f"[watch-cycle] {active_count} active reports",
              f"synthesizing for {user_id}")

    if active_count > 0:
        synthesize_and_push(reports, user_id)
    else:
        print("[Watch Cycle] No content — skip push")

    return reports


def start_autonomous_watchers():
    """
    เรียกจาก app.py ตอน startup
    ไม่ต้องทำอะไรเพิ่ม — watch cycle ถูก trigger โดย scheduler.py
    แค่ log ว่า autonomous agents พร้อมแล้ว
    """
    print("[Autonomous] Agents ready — watch cycle managed by scheduler")
    log_agent("system", "system", "Autonomous agents initialized", "watch cycle: scheduler")
