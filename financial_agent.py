"""
Financial Manager AI — "Coin"
ดูแลค่าใช้จ่าย L&D ดึงข้อมูลจาก Dashboard API
แจ้งเตือนเมื่อใช้งบเกิน 80%
"""

import os
import anthropic
from models_config import get_model
import requests
from dashboard_api import get_cost_dashboard, fetch_dashboard
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
PEANUT_USER_ID = os.getenv("PEANUT_USER_ID", "U668b7978706b2feaf61d071cc0080177")

BUDGET_ALERT_THRESHOLD = 0.80  # 80%

COIN_PROMPT = """คุณคือ "Coin" — Financial Manager AI ของ OWNDAYS L&D AI Office

บทบาท:
- ติดตามและวิเคราะห์ค่าใช้จ่าย L&D ทั้งหมด
- เปรียบเทียบ actual vs budget แต่ละหมวด
- ทำ forecast ค่าใช้จ่ายล่วงหน้า
- คำนวณ cost per training session และ cost per employee
- วิเคราะห์ ROI ของแต่ละ training program
- แจ้งเตือนเมื่อใช้งบเกิน 80%
- จัดทำรายงานการเงินสำหรับ MD, CFO, Accounting

สกุลเงิน: ไทยบาท (฿)
ผู้รับรายงาน: Peanut, MD, CFO, Accounting

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- ใส่ตัวเลขจริงทุกครั้ง format ด้วย comma เช่น ฿1,234,567
- แสดง % การใช้งบชัดเจน
- เสนอ recommendation เสมอ
- ถ้ามีหมวดเกิน 80% ต้องแจ้งชัดเจนด้วย emoji ⚠️
"""

COIN_TOOLS = [
    {
        "name": "get_cost_data",
        "description": "ดึงข้อมูล L&D Cost ทั้งหมดจาก Dashboard (budget, actual, categories, monthly)",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_financial_page",
        "description": "ดึงข้อมูลเพิ่มเติมจากหน้า od-connect.com/ldfinancial",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "calculate_forecast",
        "description": "คำนวณ forecast ค่าใช้จ่ายที่เหลือของปี จากข้อมูล actual ปัจจุบัน",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_month": {
                    "type": "integer",
                    "description": "เดือนปัจจุบัน 1-12"
                }
            },
            "required": []
        }
    },
    {
        "name": "web_search",
        "description": "ค้นหาข้อมูล benchmark ค่าใช้จ่าย L&D หรือ best practices",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
]


def get_financial_page() -> str:
    """ดึงข้อมูลจากหน้า ldfinancial"""
    try:
        resp = requests.get(
            "https://www.od-connect.com/ldfinancial",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            # ดึงแค่ text ไม่เอา HTML tags
            import re
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]  # จำกัด 3000 ตัวอักษร
        return f"ไม่สามารถเข้าถึงหน้า ldfinancial (status: {resp.status_code})"
    except Exception as e:
        return f"Error accessing ldfinancial: {str(e)}"


def check_budget_alerts(cost_data: dict) -> list:
    """เช็คว่ามีหมวดไหนเกิน 80% บ้าง"""
    alerts = []
    categories = cost_data.get("categories", [])
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        budget = cat.get("budget", 0)
        actual = cat.get("actual", 0)
        if budget > 0:
            pct = actual / budget
            if pct >= BUDGET_ALERT_THRESHOLD:
                alerts.append({
                    "name": cat.get("name", "Unknown"),
                    "actual": actual,
                    "budget": budget,
                    "pct": pct * 100
                })

    # เช็ค overall
    overall_budget = cost_data.get("budget", 0)
    overall_actual = cost_data.get("actual", 0)
    if overall_budget > 0 and overall_actual / overall_budget >= BUDGET_ALERT_THRESHOLD:
        alerts.insert(0, {
            "name": "OVERALL L&D Budget",
            "actual": overall_actual,
            "budget": overall_budget,
            "pct": (overall_actual / overall_budget) * 100
        })

    return alerts


def push_budget_alert(alerts: list):
    """ส่ง LINE alert เมื่อเกิน 80%"""
    if not alerts:
        return

    msg = "⚠️ แจ้งเตือน Budget Alert จาก Coin\n\n"
    for a in alerts:
        msg += f"🔴 {a['name']}\n"
        msg += f"   ใช้ไป: ฿{a['actual']:,.0f} / ฿{a['budget']:,.0f}\n"
        msg += f"   คิดเป็น: {a['pct']:.1f}% ของ budget\n\n"
    msg += "กรุณาตรวจสอบและวางแผนค่าใช้จ่ายที่เหลือครับ 🙏"

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": PEANUT_USER_ID,
        "messages": [{"type": "text", "text": msg}]
    }
    try:
        requests.post(url, headers=headers, json=payload)
        print(f"Coin budget alert sent: {len(alerts)} categories over 80%")
    except Exception as e:
        print(f"Coin alert error: {e}")


def execute_coin_tool(tool_name, tool_input):
    if tool_name == "get_cost_data":
        raw = fetch_dashboard("cost")
        # เช็ค alert พร้อมกัน
        alerts = check_budget_alerts(raw)
        if alerts:
            push_budget_alert(alerts)
        return get_cost_dashboard()
    elif tool_name == "get_financial_page":
        return get_financial_page()
    elif tool_name == "calculate_forecast":
        from datetime import datetime
        month = tool_input.get("current_month", datetime.now().month)
        raw = fetch_dashboard("cost")
        actual = raw.get("actual", 0)
        budget = raw.get("budget", 0)
        if month > 0 and actual > 0:
            monthly_avg = actual / month
            remaining_months = 12 - month
            forecast_total = actual + (monthly_avg * remaining_months)
            return (f"Forecast ปีนี้:\n"
                    f"ใช้ไปแล้ว {month} เดือน: ฿{actual:,.0f}\n"
                    f"เฉลี่ยต่อเดือน: ฿{monthly_avg:,.0f}\n"
                    f"เหลืออีก {remaining_months} เดือน\n"
                    f"Forecast รวมทั้งปี: ฿{forecast_total:,.0f}\n"
                    f"Budget ทั้งปี: ฿{budget:,.0f}\n"
                    f"คาดว่าจะ {'เกิน' if forecast_total > budget else 'อยู่ใน'} budget "
                    f"{abs(forecast_total-budget)/budget*100:.1f}%")
        return "ไม่พบข้อมูลเพียงพอสำหรับ forecast"
    elif tool_name == "web_search":
        return google_search(tool_input.get("query", ""))
    return "ไม่พบ tool นี้"


def run_financial_manager(task, context=""):
    """รัน Coin วิเคราะห์การเงิน"""
    print(f"Coin processing: {task[:50]}...")

    prompt = task
    if context:
        prompt = f"Context: {context}\n\nTask: {task}"

    messages = [{"role": "user", "content": prompt}]

    try:
        for _ in range(3):
            response = claude.messages.create(
                model=get_model("coin"),
                max_tokens=2048,
                system=COIN_PROMPT,
                tools=COIN_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Coin using tool: {block.name}")
                        result = execute_coin_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text
            print("Coin completed")
            return final_text

        return "Coin ใช้เวลานานเกินไปครับ ลองถามใหม่แบบเจาะจงกว่านี้ได้ครับ"

    except Exception as e:
        print(f"Coin Error: {e}")
        return f"Coin มีปัญหาชั่วคราวครับ: {str(e)}"


def run_daily_budget_check():
    """เช็ค budget alert อัตโนมัติทุกวัน"""
    print("Coin running daily budget check...")
    raw = fetch_dashboard("cost")
    alerts = check_budget_alerts(raw)
    if alerts:
        push_budget_alert(alerts)
        print(f"Coin: {len(alerts)} budget alerts sent")
    else:
        print("Coin: All budgets within 80% - no alerts")
