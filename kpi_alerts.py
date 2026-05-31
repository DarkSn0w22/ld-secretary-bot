"""
KPI Alert System — แจ้งเตือนทันทีเมื่อ KPI ต่ำกว่าเกณฑ์
ไม่รอ watch cycle — push LINE ได้ทันที
"""
import os
from datetime import datetime, timedelta
import pytz

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

# ── เกณฑ์ KPI (ปรับได้ผ่าน env vars) ────────────────────────────────────────
THRESHOLDS = {
    # Training / Survey (Pulse)
    "survey_score_min":     float(os.getenv("KPI_SURVEY_MIN",     "3.5")),   # < 3.5/4.0
    "oar_completion_min":   float(os.getenv("KPI_OAR_MIN",         "70")),   # < 70%
    "trainer_score_min":    float(os.getenv("KPI_TRAINER_MIN",    "3.2")),   # trainer ส่วนตัว

    # Sales / Rex
    "branch_achieve_min":   float(os.getenv("KPI_ACHIEVE_MIN",    "85")),   # Achiev% < 85%
    "branch_cvr_min":       float(os.getenv("KPI_CVR_MIN",         "20")),   # CVR% < 20%
    "branch_atv_min":       float(os.getenv("KPI_ATV_MIN",       "3500")),   # ATV < 3,500
    "branch_engager_min":   float(os.getenv("KPI_ENGAGER_MIN",    "75")),   # Engager% < 75%

    # Budget / Coin
    "budget_warn_pct":      float(os.getenv("KPI_BUDGET_WARN",    "80")),   # ใช้เกิน 80%
    "budget_crit_pct":      float(os.getenv("KPI_BUDGET_CRIT",    "90")),   # ใช้เกิน 90%

    # HR / People
    "probation_warn_days":  int(os.getenv("KPI_PROBATION_WARN",    "7")),   # ≤ 7 วัน
    "probation_crit_days":  int(os.getenv("KPI_PROBATION_CRIT",    "3")),   # ≤ 3 วัน

    # Website / Pixel
    "web_latency_warn_ms":  int(os.getenv("KPI_WEB_WARN",       "3000")),   # > 3s
    "web_latency_crit_ms":  int(os.getenv("KPI_WEB_CRIT",       "8000")),   # > 8s
}

# ── Alert deduplication (ไม่ส่ง alert ซ้ำภายใน cooldown) ────────────────────
_sent: dict = {}   # {alert_key: datetime}
DEFAULT_COOLDOWN_H = 12   # ส่งซ้ำได้ทุก 12 ชั่วโมง


def _can_alert(key: str, cooldown_h: int = DEFAULT_COOLDOWN_H) -> bool:
    last = _sent.get(key)
    if not last:
        return True
    return (datetime.now(BANGKOK_TZ) - last).total_seconds() > cooldown_h * 3600


def _mark(key: str):
    _sent[key] = datetime.now(BANGKOK_TZ)


def _push(text: str):
    """ส่ง LINE ทันที"""
    try:
        from scheduler import push_message
        push_message(text)
    except Exception as e:
        print(f"[KPIAlert] push error: {e}")


# ── Public alert functions ───────────────────────────────────────────────────

def alert_survey_low(trainer_name: str, score: float, course: str = ""):
    """Pulse: survey score ต่ำกว่าเกณฑ์"""
    key = f"survey_{trainer_name}"
    min_s = THRESHOLDS["survey_score_min"]
    if score >= min_s or not _can_alert(key):
        return False
    _mark(key)
    _push(
        f"⚠️ Survey Alert — Pulse\n\n"
        f"📉 {trainer_name}: {score:.1f}/4.0 (เกณฑ์ {min_s})\n"
        f"{'หลักสูตร: ' + course if course else ''}\n"
        f"→ ควรวางแผน coaching หรือ re-training ครับ\n\n"
        f"⏱ {_now()}"
    )
    return True


def alert_branch_performance(branch_name: str, achieve_pct: float,
                              cvr_pct: float = None, atv: float = None):
    """Rex: สาขาผลงานต่ำกว่าเกณฑ์"""
    issues = []
    if achieve_pct < THRESHOLDS["branch_achieve_min"]:
        issues.append(f"Achiev% {achieve_pct:.1f}% (เกณฑ์ {THRESHOLDS['branch_achieve_min']}%)")
    if cvr_pct and cvr_pct < THRESHOLDS["branch_cvr_min"]:
        issues.append(f"CVR% {cvr_pct:.1f}% (เกณฑ์ {THRESHOLDS['branch_cvr_min']}%)")
    if atv and atv < THRESHOLDS["branch_atv_min"]:
        issues.append(f"ATV ฿{atv:,.0f} (เกณฑ์ ฿{THRESHOLDS['branch_atv_min']:,.0f})")

    if not issues:
        return False
    key = f"branch_{branch_name}"
    if not _can_alert(key):
        return False
    _mark(key)
    _push(
        f"🚨 Branch Alert — Rex\n\n"
        f"📍 สาขา {branch_name}\n"
        + "\n".join(f"  • {i}" for i in issues) +
        f"\n\n→ ตรวจสอบด่วน อาจต้องส่ง Trainer เข้าช่วยครับ\n\n"
        f"⏱ {_now()}"
    )
    return True


def alert_budget_usage(category: str, used_pct: float, actual: float, budget: float):
    """Coin: งบประมาณใกล้เต็มหรือเกิน"""
    is_crit = used_pct >= THRESHOLDS["budget_crit_pct"]
    is_warn = used_pct >= THRESHOLDS["budget_warn_pct"]
    if not (is_crit or is_warn):
        return False
    key = f"budget_{category}_{'crit' if is_crit else 'warn'}"
    if not _can_alert(key, cooldown_h=6 if is_crit else 24):
        return False
    _mark(key)
    icon = "🚨" if is_crit else "⚠️"
    _push(
        f"{icon} Budget Alert — Coin\n\n"
        f"💰 {category}: {used_pct:.1f}% ของ budget\n"
        f"   ใช้แล้ว: ฿{actual:,.0f} / ฿{budget:,.0f}\n"
        f"{'🔴 เกินเกณฑ์วิกฤต!' if is_crit else '🟡 ใกล้เต็ม budget'}\n\n"
        f"⏱ {_now()}"
    )
    return True


def alert_probation_expiring(employees: list):
    """People: พนักงาน probation ใกล้หมด
    employees = [{name, branch, position, days_left, end_date}]
    """
    critical = [e for e in employees if e.get("days_left", 99) <= THRESHOLDS["probation_crit_days"]]
    warning  = [e for e in employees if THRESHOLDS["probation_crit_days"] < e.get("days_left", 99) <= THRESHOLDS["probation_warn_days"]]

    sent = False
    if critical:
        key = f"probation_crit_{','.join(e['name'] for e in critical[:3])}"
        if _can_alert(key, cooldown_h=6):
            _mark(key)
            lines = "\n".join(f"  🔴 {e['name']} | {e.get('branch','')} | หมด {e.get('end_date','')} (อีก {e.get('days_left',0)} วัน)" for e in critical)
            _push(f"🚨 Probation Critical — People\n\n{lines}\n\n→ ดำเนินการ confirm/terminate ด่วนครับ\n\n⏱ {_now()}")
            sent = True

    if warning:
        key = f"probation_warn_{len(warning)}"
        if _can_alert(key, cooldown_h=24):
            _mark(key)
            lines = "\n".join(f"  🟡 {e['name']} | {e.get('branch','')} | อีก {e.get('days_left',0)} วัน" for e in warning)
            _push(f"⚠️ Probation Warning — People\n\n{lines}\n\n→ เตรียม review ภายในสัปดาห์นี้ครับ\n\n⏱ {_now()}")
            sent = True

    return sent


def alert_website_slow(page: str, latency_ms: int):
    """Pixel: เว็บช้าหรือ down"""
    is_crit = latency_ms >= THRESHOLDS["web_latency_crit_ms"]
    is_warn = latency_ms >= THRESHOLDS["web_latency_warn_ms"]
    if not (is_crit or is_warn):
        return False
    key = f"web_{page}_{'crit' if is_crit else 'warn'}"
    if not _can_alert(key, cooldown_h=1 if is_crit else 4):
        return False
    _mark(key)
    icon = "🚨" if is_crit else "⚠️"
    _push(
        f"{icon} Website Alert — Pixel\n\n"
        f"🌐 {page}: {latency_ms:,}ms\n"
        f"{'🔴 ช้ามากหรืออาจ down' if is_crit else '🟡 ช้ากว่าปกติ'}\n\n"
        f"→ ตรวจสอบ od-connect.com ด่วนครับ\n\n"
        f"⏱ {_now()}"
    )
    return True


def alert_website_down(url: str, error: str):
    """Pixel: เว็บ down"""
    key = f"web_down_{url[:30]}"
    if not _can_alert(key, cooldown_h=1):
        return False
    _mark(key)
    _push(
        f"🚨 Website DOWN — Pixel\n\n"
        f"🌐 {url}\n"
        f"❌ Error: {error[:100]}\n\n"
        f"→ ตรวจสอบและแก้ไขด่วนครับ\n\n"
        f"⏱ {_now()}"
    )
    return True


def get_threshold(key: str):
    """ดึงค่าเกณฑ์"""
    return THRESHOLDS.get(key)


def get_alert_summary() -> str:
    """สรุป alerts ที่ส่งไปล่าสุด"""
    if not _sent:
        return "ยังไม่มี alert ส่งออกครับ"
    now = datetime.now(BANGKOK_TZ)
    lines = []
    for key, ts in sorted(_sent.items(), key=lambda x: x[1], reverse=True)[:10]:
        age = (now - ts).total_seconds() / 3600
        lines.append(f"  {key}: {age:.1f} ชม.ที่แล้ว")
    return "Alert ล่าสุด:\n" + "\n".join(lines)


def _now() -> str:
    return datetime.now(BANGKOK_TZ).strftime("%d/%m/%Y %H:%M น.")
