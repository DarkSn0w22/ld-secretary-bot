"""
WIX REST API wrapper for Pixel agent
od-connect.com (WIX platform) integration
"""

import os
import requests

# WIX API Key (IST.eyJ... format) — ใส่ใน Railway env: WIX_API_KEY
# WIX Site ID — ดูจาก manage.wix.com/dashboard/{SITE_ID}/... ใส่ใน Railway env: WIX_SITE_ID
WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
BASE_URL = "https://www.wixapis.com"
OD_CONNECT_URL = "https://www.od-connect.com"


def wix_headers() -> dict:
    """HTTP headers สำหรับ WIX API calls (API Key auth)"""
    h = {"Content-Type": "application/json"}
    if WIX_API_KEY:
        h["Authorization"] = WIX_API_KEY   # WIX API Key ใส่ตรงๆ ไม่ต้อง Bearer
    if WIX_SITE_ID:
        h["wix-site-id"] = WIX_SITE_ID
    return h


def wix_ready() -> bool:
    """คืน True ถ้า WIX credentials พร้อม"""
    return bool(WIX_CLIENT_ID and WIX_CLIENT_SECRET and WIX_SITE_ID)


def check_site_uptime() -> dict:
    """HTTP ping to od-connect.com — คืน dict พร้อม status/latency"""
    import time
    result = {
        "url": OD_CONNECT_URL,
        "status": "unknown",
        "status_code": None,
        "latency_ms": None,
        "error": None,
    }
    try:
        start = time.time()
        resp = requests.get(
            OD_CONNECT_URL,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (OwnDays-LD-Bot/1.0)"},
            allow_redirects=True,
        )
        elapsed = int((time.time() - start) * 1000)
        result["status_code"] = resp.status_code
        result["latency_ms"] = elapsed
        if resp.status_code < 400:
            result["status"] = "up"
        else:
            result["status"] = "degraded"
            result["error"] = f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "down"
        result["error"] = f"ConnectionError: {e}"
    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = "Request timed out after 15s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


def check_pages_uptime(pages: list = None) -> list:
    """ตรวจสอบหน้าสำคัญหลายหน้าพร้อมกัน"""
    import threading, time
    if pages is None:
        pages = [
            "/",
            "/oar-owndays-academy-registration",
            "/oar-survey",
            "/ldfinancial",
            "/ldmaindashboard",
            "/emp-info",
        ]
    results = [None] * len(pages)

    def _check(idx, path):
        url = OD_CONNECT_URL + path
        try:
            start = time.time()
            resp = requests.get(
                url,
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0 (OwnDays-LD-Bot/1.0)"},
                allow_redirects=True,
            )
            elapsed = int((time.time() - start) * 1000)
            results[idx] = {
                "path": path,
                "status_code": resp.status_code,
                "latency_ms": elapsed,
                "ok": resp.status_code < 400,
            }
        except Exception as e:
            results[idx] = {"path": path, "status_code": None, "latency_ms": None,
                            "ok": False, "error": str(e)}

    threads = [threading.Thread(target=_check, args=(i, p), daemon=True)
               for i, p in enumerate(pages)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    return [r for r in results if r is not None]


def get_site_pages() -> list:
    """GET site properties / pages via WIX Pages API"""
    if not WIX_API_KEY or not WIX_SITE_ID:
        return []
    try:
        resp = requests.get(
            f"{BASE_URL}/v2/pages/",
            headers=wix_headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            pages = data.get("pages", [])
            return [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "url": p.get("url"),
                    "hidden": p.get("hidden", False),
                }
                for p in pages
            ]
        return []
    except Exception as e:
        print(f"WIX get_site_pages error: {e}")
        return []


def get_cms_collection(collection_id: str, limit: int = 10) -> list:
    """Query WIX CMS collection"""
    if not WIX_API_KEY or not WIX_SITE_ID:
        return []
    try:
        url = f"{BASE_URL}/v2/collections/{collection_id}/items/query"
        payload = {
            "dataCollectionId": collection_id,
            "query": {
                "paging": {"limit": limit},
                "sort": [{"fieldName": "_updatedDate", "order": "DESC"}],
            },
        }
        resp = requests.post(url, headers=wix_headers(), json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("items", [])
        return []
    except Exception as e:
        print(f"WIX get_cms_collection error: {e}")
        return []


def update_cms_item(collection_id: str, item_id: str, data: dict) -> dict:
    """Update a CMS item by ID"""
    if not WIX_API_KEY or not WIX_SITE_ID:
        return {"error": "WIX API key not configured"}
    try:
        url = f"{BASE_URL}/v2/collections/{collection_id}/items/{item_id}"
        payload = {"dataCollectionId": collection_id, "item": data}
        resp = requests.put(url, headers=wix_headers(), json=payload, timeout=15)
        if resp.status_code in (200, 201):
            return resp.json()
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def get_analytics_overview(days: int = 7) -> dict:
    """ดึง site analytics overview — visitors, pageviews, sessions, locations"""
    if not WIX_API_KEY or not WIX_SITE_ID:
        return {"error": "WIX_API_KEY หรือ WIX_SITE_ID ไม่ได้ตั้งค่า"}
    from datetime import datetime, timedelta
    import pytz
    end   = datetime.now(pytz.utc)
    start = end - timedelta(days=days)

    def fmt(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = {}

    # ── 1) Traffic overview ──────────────────────────────────────
    try:
        resp = requests.post(
            f"{BASE_URL}/analytics/v2/reports/query",
            headers=wix_headers(),
            json={
                "dateRange": {"startDate": fmt(start), "endDate": fmt(end)},
                "metrics":   ["SESSIONS", "PAGE_VIEWS", "UNIQUE_VISITORS",
                               "BOUNCE_RATE", "AVG_SESSION_DURATION"],
                "dimensions": []
            },
            timeout=20
        )
        if resp.ok:
            rows = resp.json().get("rows", [{}])
            r = rows[0] if rows else {}
            result["overview"] = {
                "sessions":          r.get("SESSIONS", 0),
                "page_views":        r.get("PAGE_VIEWS", 0),
                "unique_visitors":   r.get("UNIQUE_VISITORS", 0),
                "bounce_rate_pct":   round(float(r.get("BOUNCE_RATE", 0)) * 100, 1),
                "avg_session_sec":   int(float(r.get("AVG_SESSION_DURATION", 0))),
            }
        else:
            result["overview"] = {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        result["overview"] = {"error": str(e)}

    # ── 2) Top locations (countries) ────────────────────────────
    try:
        resp = requests.post(
            f"{BASE_URL}/analytics/v2/reports/query",
            headers=wix_headers(),
            json={
                "dateRange": {"startDate": fmt(start), "endDate": fmt(end)},
                "metrics":   ["SESSIONS", "UNIQUE_VISITORS"],
                "dimensions": ["COUNTRY"],
                "order":     [{"metric": "SESSIONS", "direction": "DESC"}],
                "paging":    {"limit": 10}
            },
            timeout=20
        )
        if resp.ok:
            rows = resp.json().get("rows", [])
            result["top_countries"] = [
                {
                    "country":  r.get("COUNTRY", "Unknown"),
                    "sessions": r.get("SESSIONS", 0),
                    "visitors": r.get("UNIQUE_VISITORS", 0),
                }
                for r in rows
            ]
        else:
            result["top_countries"] = []
    except Exception as e:
        result["top_countries"] = []

    # ── 3) Top pages ─────────────────────────────────────────────
    try:
        resp = requests.post(
            f"{BASE_URL}/analytics/v2/reports/query",
            headers=wix_headers(),
            json={
                "dateRange": {"startDate": fmt(start), "endDate": fmt(end)},
                "metrics":   ["PAGE_VIEWS", "UNIQUE_VISITORS"],
                "dimensions": ["PAGE_URL"],
                "order":     [{"metric": "PAGE_VIEWS", "direction": "DESC"}],
                "paging":    {"limit": 10}
            },
            timeout=20
        )
        if resp.ok:
            rows = resp.json().get("rows", [])
            result["top_pages"] = [
                {
                    "page":       r.get("PAGE_URL", "/"),
                    "page_views": r.get("PAGE_VIEWS", 0),
                    "visitors":   r.get("UNIQUE_VISITORS", 0),
                }
                for r in rows
            ]
        else:
            result["top_pages"] = []
    except Exception as e:
        result["top_pages"] = []

    # ── 4) Traffic sources ───────────────────────────────────────
    try:
        resp = requests.post(
            f"{BASE_URL}/analytics/v2/reports/query",
            headers=wix_headers(),
            json={
                "dateRange": {"startDate": fmt(start), "endDate": fmt(end)},
                "metrics":   ["SESSIONS"],
                "dimensions": ["TRAFFIC_SOURCE"],
                "order":     [{"metric": "SESSIONS", "direction": "DESC"}],
                "paging":    {"limit": 8}
            },
            timeout=20
        )
        if resp.ok:
            rows = resp.json().get("rows", [])
            result["traffic_sources"] = [
                {"source": r.get("TRAFFIC_SOURCE", "?"), "sessions": r.get("SESSIONS", 0)}
                for r in rows
            ]
        else:
            result["traffic_sources"] = []
    except Exception as e:
        result["traffic_sources"] = []

    # ── 5) Device breakdown ──────────────────────────────────────
    try:
        resp = requests.post(
            f"{BASE_URL}/analytics/v2/reports/query",
            headers=wix_headers(),
            json={
                "dateRange": {"startDate": fmt(start), "endDate": fmt(end)},
                "metrics":   ["SESSIONS"],
                "dimensions": ["DEVICE_TYPE"],
            },
            timeout=20
        )
        if resp.ok:
            result["devices"] = [
                {"device": r.get("DEVICE_TYPE", "?"), "sessions": r.get("SESSIONS", 0)}
                for r in resp.json().get("rows", [])
            ]
        else:
            result["devices"] = []
    except Exception as e:
        result["devices"] = []

    result["period_days"] = days
    return result


def get_blog_posts(limit: int = 5) -> list:
    """Get recent blog posts from WIX Blog API"""
    if not WIX_API_KEY or not WIX_SITE_ID:
        return []
    try:
        url = f"{BASE_URL}/blog/v3/posts"
        params = {
            "fieldsets": "CONTENT_TEXT",
            "paging.limit": limit,
            "sort": "PUBLISHED_DATE_DESCENDING",
        }
        resp = requests.get(url, headers=wix_headers(), params=params, timeout=15)
        if resp.status_code == 200:
            posts = resp.json().get("posts", [])
            return [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "url": p.get("url"),
                    "publishedDate": p.get("firstPublishedDate"),
                    "excerpt": (p.get("contentText") or "")[:200],
                }
                for p in posts
            ]
        return []
    except Exception as e:
        print(f"WIX get_blog_posts error: {e}")
        return []
