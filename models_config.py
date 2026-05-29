"""
Model Config — จัดการรุ่น Claude ของทุก agent จากที่เดียว
================================================================
แก้รุ่นที่นี่ หรือ override ผ่าน Environment Variable บน Railway
โดยไม่ต้องแก้โค้ดและ deploy ใหม่

วิธีใช้บน Railway (Variables):
  MODEL_SONNET = claude-sonnet-4-5         <- รุ่นประหยัด (default ทุก agent)
  MODEL_OPUS   = claude-opus-4-1           <- รุ่นเก่งกว่า (ตรวจชื่อจริงที่ docs ก่อน!)
  MODEL_GUARD  = claude-opus-4-1           <- override เฉพาะ Guard
  MODEL_LEX    = claude-opus-4-1           <- override เฉพาะ Lex

หมายเหตุสำคัญ:
- ถ้า "ยังไม่ตั้ง" MODEL_OPUS → OPUS จะ fallback เป็น Sonnet อัตโนมัติ
  แปลว่า deploy ได้เลยไม่พัง และทุกตัวจะวิ่งบน Sonnet จนกว่าจะตั้งชื่อรุ่น Opus จริง
- ตรวจชื่อรุ่น Opus ล่าสุดที่ docs.claude.com/en/docs/about-claude/models ก่อนตั้ง env
"""

import os

# ── ชื่อรุ่นพื้นฐาน (แก้ที่นี่ หรือ override ด้วย env) ──────────────
SONNET = os.getenv("MODEL_SONNET", "claude-sonnet-4-5")

# OPUS: ถ้ายังไม่ตั้ง env MODEL_OPUS จะใช้ Sonnet ไปก่อน (ปลอดภัย ไม่พัง)
OPUS = os.getenv("MODEL_OPUS", SONNET)

# ── รุ่น default ต่อ agent (ตามคำแนะนำจาก review) ─────────────────
# ตัวที่ตั้งเป็น OPUS = งานเน้นคิด/มีผลทางกฎหมาย-การเงิน/เป็นด่านคุณภาพ
AGENT_MODELS = {
    "rocket": SONNET,   # เลขาหลัก — routing/ตอบ LINE ปริมาณสูง
    "atlas":  SONNET,   # Manager — สรุป/ประสานงาน (อัปเป็น OPUS ได้ถ้างานหนัก)
    "pulse":  SONNET,   # Trainer Manager — สรุป KPI
    "sage":   SONNET,   # Reporter — รายงานมีโครงสร้าง
    "guard":  OPUS,     # QA Reviewer — ด่านคุณภาพ ควรเก่ง >= ตัวที่ตรวจ
    "coin":   SONNET,   # Financial — อัปเป็น OPUS ได้ถ้า forecast/ROI ซับซ้อน
    "lex":    OPUS,     # Legal — กฎหมาย/PDPA ผิดมีผลจริง ปริมาณน้อย คุ้มสุด
    "people": SONNET,   # HR — ดึงข้อมูล/probation งานพื้นฐาน
    "pixel":  SONNET,   # Web Admin — monitoring งานพื้นฐาน
    "sigma":  SONNET,   # Data Analyst — อัปเป็น OPUS ได้ถ้าวิเคราะห์เชิงลึก
    "lens":   SONNET,   # Creator — content/quiz
    "rex":    SONNET,   # Retail MD — sales analysis, branch performance
    "scheduler": SONNET # งานอัตโนมัติ (Daily Brief ฯลฯ)
}


def get_model(agent_id: str) -> str:
    """
    คืนชื่อรุ่นของ agent
    ลำดับความสำคัญ:
      1. env เฉพาะตัว เช่น MODEL_LEX
      2. ค่า default ใน AGENT_MODELS
      3. SONNET (เผื่อ agent id ไม่รู้จัก)
    """
    env_key = f"MODEL_{agent_id.upper()}"
    return os.getenv(env_key, AGENT_MODELS.get(agent_id, SONNET))


# พิมพ์สรุปตอน start เพื่อให้เห็นว่าตัวไหนใช้รุ่นอะไร
def print_model_summary():
    opus_on = OPUS != SONNET
    print("─" * 48)
    print(f"MODEL CONFIG | Sonnet={SONNET}")
    print(f"             | Opus  ={OPUS}" + ("" if opus_on else "  (ยังไม่ตั้ง → ใช้ Sonnet)"))
    for aid in AGENT_MODELS:
        m = get_model(aid)
        tag = " [OPUS]" if (m == OPUS and opus_on) else ""
        print(f"   {aid:10}-> {m}{tag}")
    print("─" * 48)
