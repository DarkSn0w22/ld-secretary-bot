"""
Google Search Skill — shared utility
ทุก agent เรียกใช้ได้ ไม่ใช่ agent แยก
"""

import os
import requests

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
