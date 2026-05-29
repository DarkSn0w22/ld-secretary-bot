"""
WIX REST API wrapper for Pixel agent
od-connect.com (WIX platform) integration
"""

import os
import requests

WIX_CLIENT_ID     = os.getenv("WIX_CLIENT_ID", "")
WIX_CLIENT_SECRET = os.getenv("WIX_CLIENT_SECRET", "")
WIX_SITE_ID       = os.getenv("WIX_SITE_ID", "")
BASE_URL = "https://www.wixapis.com"
OD_CONNECT_URL = "https://www.od-connect.com"

# ── OAuth token cache ──────────────────────────────────────────
_token_cache = {"access_token": "", "expires_at": 0}


def get_access_token() -> str:
    """Exchange Client Credentials → Access Token (cached)"""
    import time
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]
    if not WIX_CLIENT_ID or not WIX_CLIENT_SECRET:
        return ""
    try:
        resp = requests.post(
            "https://www.wixapis.com/oauth2/token",
            json={
                "clientId":     WIX_CLIENT_ID,
                "clientSecret": WIX_CLIENT_SECRET,
                "grantType":    "client_credentials",
            },
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            _token_cache["access_token"] = data.get("access_token", "")
            _token_cache["expires_at"]   = time.time() + data.get("expires_in", 3600)
            return _token_cache["access_token"]
    except Exception as e:
        print(f"[WIX] token error: {e}")
    return ""


def wix_headers() -> dict:
    """HTTP headers สำหรับ WIX API calls"""
    token = get_access_token()
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
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
