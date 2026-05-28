"""
Researcher AI — "Scout"
ค้นหาข้อมูลผ่าน Google Custom Search API
ไม่มี timeout ปัญหา ผลลัพธ์ชัดเจน
"""

import os
import requests
import anthropic

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

GOOGLE_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "f182b156f177d4a6a")


def google_search(query: str, num_results: int = 5) -> str:
    """ค้นหาผ่าน Google Custom Search API"""
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": num_results,
            "lr": "lang_th|lang_en",
        }
        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        if "items" not in data:
            return "ไม่พบผลการค้นหา"

        results = []
        for item in data["items"]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            results.append(f"หัวข้อ: {title}\nสรุป: {snippet}\nลิงก์: {link}")

        return "\n\n".join(results)

    except Exception as e:
        return f"Google Search error: {str(e)}"


SCOUT_PROMPT = """คุณคือ "Scout" — Researcher AI ของ OWNDAYS L&D AI Office

บทบาท:
- วิเคราะห์ผลการค้นหาจาก Google และสรุปเป็นภาษาไทย
- เน้นข้อมูลที่ OWNDAYS นำไปใช้ได้จริง
- ระบุแหล่งที่มาและปีของข้อมูลเสมอ
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"

เกี่ยวกับ OWNDAYS:
- ธุรกิจค้าปลีกแว่นตา 73 สาขา ไทย/กัมพูชา/ลาว
- Training 3 สาย: Sales, Optical, Optometry
- แพลตฟอร์ม: OWNDAYS Connect (od-connect.com)
- กำลัง digital transformation ด้าน L&D
"""


def run_researcher(query: str, context: str = "") -> str:
    """
    ค้นหาด้วย Google แล้วให้ Claude สรุป
    ไม่ใช้ web_search tool — ไม่มี timeout ปัญหา
    """
    print(f"Scout searching: {query[:50]}...")

    # Step 1: ค้นหาด้วย Google
    search_results = google_search(query)

    if "error" in search_results.lower() or "ไม่พบ" in search_results:
        # ลอง query ภาษาอังกฤษแทน
        en_query = query + " retail training benchmark 2024 2025"
        search_results = google_search(en_query)

    # Step 2: ให้ Claude สรุปผล
    prompt = f"""นี่คือผลการค้นหาจาก Google สำหรับคำถาม: "{query}"

ผลการค้นหา:
{search_results}

{'Context เพิ่มเติม: ' + context if context else ''}

กรุณาสรุปข้อมูลที่ได้เป็นภาษาไทย โดย:
1. สรุปประเด็นสำคัญ 3-5 ข้อ
2. ระบุตัวเลข/สถิติที่น่าสนใจ
3. เสนอว่า OWNDAYS นำไปใช้ได้อย่างไร
4. ระบุแหล่งที่มา"""

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=SCOUT_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.content[0].text
        print("Scout completed research")
        return result

    except Exception as e:
        print(f"Scout Error: {e}")
        return f"Scout มีปัญหาครับ: {str(e)}"


RESEARCH_TOPICS = {
    "ld_benchmark": "L&D training benchmark retail industry 2025 statistics",
    "optical_retail_training": "optical retail employee training best practices eyewear",
    "ai_in_ld": "AI in learning development corporate training 2025 trends",
    "digital_learning_trend": "digital learning e-learning Southeast Asia Thailand 2025",
    "customer_service_training": "customer service training retail premium luxury best practices",
}


def run_scheduled_research(topic_key: str) -> str:
    query = RESEARCH_TOPICS.get(topic_key, topic_key)
    return run_researcher(query)
