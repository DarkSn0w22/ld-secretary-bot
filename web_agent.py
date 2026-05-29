"""
Web Admin AI — "Pixel"
ดูแล od-connect.com ตรวจสอบสถานะเว็บ วิเคราะห์ traffic และ content
"""

import os
import anthropic
from models_config import get_model
import requests
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

PIXEL_PROMPT = """คุณคือ "Pixel" — Web Admin AI ของ OWNDAYS L&D AI Office

บทบาท:
- ดูแลและตรวจสอบ od-connect.com (OWNDAYS Connect - WIX platform)
- ตรวจสอบสถานะหน้าเว็บ ว่า up/down, โหลดได้ปกติไหม
- วิเคราะห์ content ในแต่ละหน้า
- ตรวจสอบ links, forms, และ functionality
- แนะนำการปรับปรุง UX/UI และ content
- ติดตาม engagement ผ่าน od-connect.com

หน้าสำคัญ:
- https://www.od-connect.com/ — หน้าหลัก
- https://www.od-connect.com/oar-owndays-academy-registration — ลงทะเบียน training
- https://www.od-connect.com/oar-survey — แบบสำรวจ
- https://www.od-connect.com/ldfinancial — ข้อมูลการเงิน
- https://www.od-connect.com/ldmaindashboard — dashboard หลัก
- https://www.od-connect.com/emp-info — ข้อมูลพนักงาน

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- รายงาน status ชัดเจน: ✅ ปกติ / ⚠️ มีปัญหา / ❌ ไม่สามารถเข้าถึง
- เสนอ recommendation เสมอ
"""

PIXEL_TOOLS = [
    {
        "name": "check_page_status",
        "description": "ตรวจสอบสถานะหน้าเว็บ od-connect.com ว่าเข้าถึงได้ไหม",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL ที่ต้องการตรวจ"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "check_all_pages",
        "description": "ตรวจสอบทุกหน้าสำคัญของ od-connect.com พร้อมกัน",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_page_content",
        "description": "ดึง content จากหน้าเว็บที่ระบุ",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "description": "จำนวนตัวอักษรสูงสุด (default 2000)"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_web_best_practices",
        "description": "ค้นหา best practices สำหรับ LMS website หรือ WIX platform",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }
]

IMPORTANT_PAGES = [
    "https://www.od-connect.com/",
    "https://www.od-connect.com/oar-owndays-academy-registration",
    "https://www.od-connect.com/oar-survey",
    "https://www.od-connect.com/ldfinancial",
    "https://www.od-connect.com/ldmaindashboard",
    "https://www.od-connect.com/emp-info",
]


def check_page(url: str) -> dict:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        return {
            "url": url,
            "status": resp.status_code,
            "ok": resp.status_code == 200,
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000)
        }
    except requests.Timeout:
        return {"url": url, "status": "timeout", "ok": False}
    except Exception as e:
        return {"url": url, "status": f"error: {str(e)}", "ok": False}


def get_page_text(url: str, max_chars: int = 2000) -> str:
    try:
        import re
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Error: {str(e)}"


def execute_pixel_tool(tool_name, tool_input):
    if tool_name == "check_page_status":
        result = check_page(tool_input.get("url", ""))
        icon = "✅" if result["ok"] else "❌"
        return (f"{icon} {result['url']}\n"
                f"   Status: {result['status']}\n"
                f"   Response: {result.get('response_time_ms', 'N/A')} ms")

    elif tool_name == "check_all_pages":
        results = []
        for url in IMPORTANT_PAGES:
            r = check_page(url)
            icon = "✅" if r["ok"] else "❌"
            results.append(f"{icon} {url.replace('https://www.od-connect.com', '')} — {r['status']} ({r.get('response_time_ms', 'N/A')}ms)")
        ok_count = sum(1 for r in [check_page(u) for u in IMPORTANT_PAGES] if r["ok"])
        return f"สถานะ od-connect.com ({ok_count}/{len(IMPORTANT_PAGES)} หน้า)\n\n" + "\n".join(results)

    elif tool_name == "get_page_content":
        url = tool_input.get("url", "")
        max_c = tool_input.get("max_chars", 2000)
        return get_page_text(url, max_c)

    elif tool_name == "search_web_best_practices":
        return google_search(tool_input.get("query", "") + " WIX LMS best practices 2025")

    return "ไม่พบ tool นี้"


def run_web_admin(task, context=""):
    print(f"Pixel processing: {task[:50]}...")
    prompt = f"Context: {context}\n\nTask: {task}" if context else task
    messages = [{"role": "user", "content": prompt}]
    try:
        for _ in range(3):
            response = claude.messages.create(
                model=get_model("pixel"), max_tokens=2048,
                system=PIXEL_PROMPT, tools=PIXEL_TOOLS, messages=messages
            )
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": execute_pixel_tool(block.name, block.input)})
                messages.append({"role": "user", "content": results})
                continue
            return "".join(b.text for b in response.content if hasattr(b, "text"))
        return "Pixel ใช้เวลานานเกินไปครับ"
    except Exception as e:
        return f"Pixel มีปัญหาชั่วคราวครับ: {str(e)}"
