"""
Google Analytics 4 Data API — สำหรับ Pixel agent
ดึง analytics data จาก od-connect.com
"""
import os
import json
import base64

# od-connect.com GA4 properties (ค้นพบจาก accountSummaries)
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "376227651")   # od-connect.com หลัก
GA4_PROPERTY_IDS = ["376227651", "539554359"]                  # ทั้ง 2 properties

# OAuth2 credentials ของ nakit@owndays.com (มีสิทธิ์ GA4 อยู่แล้ว)
GA4_CLIENT_ID     = os.getenv("GA4_OAUTH_CLIENT_ID", "")
GA4_CLIENT_SECRET = os.getenv("GA4_OAUTH_CLIENT_SECRET", "")
GA4_REFRESH_TOKEN = os.getenv("GA4_REFRESH_TOKEN", "")


def _get_ga4_client():
    """สร้าง GA4 client — ลำดับ: OAuth refresh token → service account"""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        # วิธีที่ 1: ใช้ OAuth Refresh Token ของ nakit@owndays.com
        if GA4_REFRESH_TOKEN:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            # ถ้ามี client_id/secret ใช้ refresh ผ่าน OAuth2
            if GA4_CLIENT_ID and GA4_CLIENT_SECRET:
                creds = Credentials(
                    token=None,
                    refresh_token=GA4_REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=GA4_CLIENT_ID,
                    client_secret=GA4_CLIENT_SECRET,
                    scopes=["https://www.googleapis.com/auth/analytics.readonly"]
                )
            else:
                # ใช้ Google's default OAuth app (OAuth Playground)
                creds = Credentials(
                    token=None,
                    refresh_token=GA4_REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id="764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com",
                    client_secret="d-FL95Q19q7MQmFpd7hHD0Ty",
                    scopes=["https://www.googleapis.com/auth/analytics.readonly"]
                )
            creds.refresh(Request())
            return BetaAnalyticsDataClient(credentials=creds)

        # วิธีที่ 2: ใช้ Service Account (fallback)
        from google.oauth2 import service_account
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            creds_dict = json.loads(base64.b64decode(creds_json).decode("utf-8"))
            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            return BetaAnalyticsDataClient(credentials=creds)

        key_file = os.getenv("GOOGLE_KEY_FILE", "credentials.json")
        if os.path.exists(key_file):
            creds = service_account.Credentials.from_service_account_file(
                key_file,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            return BetaAnalyticsDataClient(credentials=creds)
    except Exception as e:
        print(f"[GA4] client error: {e}")
    return None


def get_overview(days: int = 7) -> dict:
    """ดึง traffic overview: sessions, users, pageviews, bounce rate"""
    client = _get_ga4_client()
    if not client:
        return {"error": "GA4 client ไม่พร้อม — ตรวจสอบ GOOGLE_CREDENTIALS_JSON"}
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension
        )
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="screenPageViews"),
                Metric(name="bounceRate"),
                Metric(name="averageSessionDuration"),
                Metric(name="newUsers"),
            ]
        )
        resp = client.run_report(req)
        row = resp.rows[0] if resp.rows else None
        if not row:
            return {"sessions": 0, "users": 0, "pageviews": 0}

        vals = [v.value for v in row.metric_values]
        return {
            "sessions":          int(float(vals[0])),
            "unique_users":      int(float(vals[1])),
            "page_views":        int(float(vals[2])),
            "bounce_rate_pct":   round(float(vals[3]) * 100, 1),
            "avg_session_sec":   int(float(vals[4])),
            "new_users":         int(float(vals[5])),
            "period_days":       days,
        }
    except Exception as e:
        return {"error": str(e)}


def get_top_countries(days: int = 7, limit: int = 10) -> list:
    """Top countries by sessions"""
    client = _get_ga4_client()
    if not client:
        return []
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension, OrderBy
        )
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="country")],
            metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                                desc=True)],
            limit=limit,
        )
        resp = client.run_report(req)
        return [
            {
                "country":  row.dimension_values[0].value,
                "sessions": int(float(row.metric_values[0].value)),
                "users":    int(float(row.metric_values[1].value)),
            }
            for row in resp.rows
        ]
    except Exception as e:
        print(f"[GA4] top_countries error: {e}")
        return []


def get_top_pages(days: int = 7, limit: int = 10) -> list:
    """Top pages by pageviews"""
    client = _get_ga4_client()
    if not client:
        return []
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension, OrderBy
        )
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="pagePath"), Dimension(name="pageTitle")],
            metrics=[Metric(name="screenPageViews"), Metric(name="totalUsers")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                                desc=True)],
            limit=limit,
        )
        resp = client.run_report(req)
        return [
            {
                "path":       row.dimension_values[0].value,
                "title":      row.dimension_values[1].value,
                "page_views": int(float(row.metric_values[0].value)),
                "users":      int(float(row.metric_values[1].value)),
            }
            for row in resp.rows
        ]
    except Exception as e:
        print(f"[GA4] top_pages error: {e}")
        return []


def get_traffic_sources(days: int = 7) -> list:
    """Traffic sources breakdown"""
    client = _get_ga4_client()
    if not client:
        return []
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension, OrderBy
        )
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                                desc=True)],
        )
        resp = client.run_report(req)
        return [
            {
                "source":   row.dimension_values[0].value,
                "sessions": int(float(row.metric_values[0].value)),
            }
            for row in resp.rows
        ]
    except Exception as e:
        print(f"[GA4] traffic_sources error: {e}")
        return []


def get_devices(days: int = 7) -> list:
    """Device category breakdown"""
    client = _get_ga4_client()
    if not client:
        return []
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension
        )
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="deviceCategory")],
            metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        )
        resp = client.run_report(req)
        return [
            {
                "device":   row.dimension_values[0].value,
                "sessions": int(float(row.metric_values[0].value)),
                "users":    int(float(row.metric_values[1].value)),
            }
            for row in resp.rows
        ]
    except Exception as e:
        print(f"[GA4] devices error: {e}")
        return []


def get_full_analytics(days: int = 7) -> dict:
    """ดึง analytics ครบทุกมิติ — สำหรับ Pixel watch cycle"""
    return {
        "overview":        get_overview(days),
        "top_countries":   get_top_countries(days),
        "top_pages":       get_top_pages(days),
        "traffic_sources": get_traffic_sources(days),
        "devices":         get_devices(days),
        "period_days":     days,
    }


def ga4_ready() -> bool:
    """True ถ้า GA4 credentials พร้อม"""
    return bool(
        GA4_PROPERTY_ID and (
            GA4_REFRESH_TOKEN or
            os.getenv("GOOGLE_CREDENTIALS_JSON") or
            os.path.exists("credentials.json")
        )
    )
