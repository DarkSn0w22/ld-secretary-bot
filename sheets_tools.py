"""
Google Sheets Tools สำหรับ LD Secretary Bot
ดึงข้อมูลจาก Google Sheets ผ่าน Service Account
"""

import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

# =============================================================
# SHEET IDs (จาก Knowledge Base)
# =============================================================
SHEET_IDS = {
    "survey":    "1RlnQEXOJ3EPwqnuDLMk3rjBvinJbW1wKFcRyMfdlEVs",
    "dashboard": "1QKjyFlmJrgmiYHagn7olhpr41ucQJQc8ck3zae8obJI",
    "oar":       "1Ux83yvg3sdANd8_OB104Np9jartOfEF9_xhoX5JslSU",
    "trainers":  "1vXfDYIE-Otd5frS0RxsGP6D-IVfDlTQcO6YC0P0ZowY",  # ตารางงาน AI + Trainers
    "reports":   "1wXZI3aXj21ZkhcJgUA4lD5BewjzridVtbHaNeNgnxJQ",  # OWNDAYS AI Reports
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",   # read+write (เพิ่ม write)
    "https://www.googleapis.com/auth/drive"           # read+write
]


def get_sheets_service():
    """สร้าง Google Sheets service จาก credentials"""

    # วิธีที่ 1: อ่านจาก Environment Variable (แนะนำสำหรับ Railway)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_dict = json.loads(base64.b64decode(creds_json).decode("utf-8"))
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds)

    # วิธีที่ 2: อ่านจากไฟล์ (สำหรับ local testing)
    key_file = os.getenv("GOOGLE_KEY_FILE", "credentials.json")
    if os.path.exists(key_file):
        creds = service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds)

    return None


def read_sheet(sheet_id: str, range_name: str, limit_rows: int = 100) -> list:
    """
    อ่านข้อมูลจาก Google Sheet
    คืนค่าเป็น list of lists
    """
    service = get_sheets_service()
    if not service:
        return []

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()

        values = result.get("values", [])
        return values[:limit_rows]  # จำกัดจำนวน row

    except Exception as e:
        print(f"Sheets Error: {e}")
        return []


def get_sheet_names(sheet_id: str) -> list:
    """ดึงชื่อ sheet ทั้งหมดใน spreadsheet"""
    service = get_sheets_service()
    if not service:
        return []

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=sheet_id
        ).execute()

        sheets = spreadsheet.get("sheets", [])
        return [s["properties"]["title"] for s in sheets]

    except Exception as e:
        print(f"Sheets Error: {e}")
        return []


# =============================================================
# ฟังก์ชันดึงข้อมูลเฉพาะทาง
# =============================================================

def get_survey_summary() -> str:
    """ดึงข้อมูล survey สรุป (sheet แรก)"""
    sheet_names = get_sheet_names(SHEET_IDS["survey"])
    if not sheet_names:
        return "ไม่สามารถเชื่อมต่อ Google Sheets ได้"

    # อ่าน sheet แรก (summary หรือ sheet ล่าสุด)
    data = read_sheet(SHEET_IDS["survey"], f"{sheet_names[0]}!A1:Z50")
    if not data:
        return "ไม่มีข้อมูล survey"

    # แปลงเป็น text สำหรับส่งให้ Claude
    result = f"📊 ข้อมูล Survey (Sheet: {sheet_names[0]})\n"
    result += f"พบ {len(sheet_names)} sheets ทั้งหมด: {', '.join(sheet_names[:5])}\n\n"

    # แสดง 20 แถวแรก
    for i, row in enumerate(data[:20]):
        result += " | ".join(str(cell) for cell in row) + "\n"

    return result


def get_oar_summary() -> str:
    """ดึงข้อมูล Training Registration"""
    sheet_names = get_sheet_names(SHEET_IDS["oar"])
    if not sheet_names:
        return "ไม่สามารถเชื่อมต่อ Google Sheets ได้"

    data = read_sheet(SHEET_IDS["oar"], f"{sheet_names[0]}!A1:Z50")
    if not data:
        return "ไม่มีข้อมูล OAR"

    result = f"📋 ข้อมูล Training Registration\n"
    result += f"Sheets: {', '.join(sheet_names[:5])}\n\n"

    for row in data[:20]:
        result += " | ".join(str(cell) for cell in row) + "\n"

    return result


def get_trainer_schedule(tab_name: str = "", max_rows: int = 60) -> str:
    """
    ดึงข้อมูลตารางงาน Trainers + AI tasks
    Sheet: 1vXfDYIE-Otd5frS0RxsGP6D-IVfDlTQcO6YC0P0ZowY

    Args:
        tab_name  ชื่อ tab (ถ้าไม่ระบุใช้ tab แรกที่มีหรือ tab ปัจจุบัน)
        max_rows  จำนวนแถวสูงสุด (default 60)
    """
    sheet_id   = SHEET_IDS["trainers"]
    sheet_names = get_sheet_names(sheet_id)
    if not sheet_names:
        return "ไม่สามารถเชื่อมต่อ Trainers schedule sheet ได้ (ตรวจ Service Account permissions)"

    # ใช้ tab ที่ระบุ หรือ default tab แรก
    if tab_name and tab_name in sheet_names:
        target_tab = tab_name
    elif tab_name:
        return (f"ไม่พบ tab '{tab_name}' ใน Trainers sheet\n"
                f"Tabs ที่มี: {', '.join(sheet_names)}")
    else:
        target_tab = sheet_names[0]

    data = read_sheet(sheet_id, f"{target_tab}!A1:Z{max_rows}", limit_rows=max_rows)
    if not data:
        return f"ไม่พบข้อมูลใน tab '{target_tab}'"

    result = f"📅 ตารางงาน Trainers (Tab: {target_tab})\n"
    result += f"Tabs ทั้งหมด: {', '.join(sheet_names)}\n"
    result += f"แสดง {len(data)} แถว:\n\n"

    for row in data:
        cells = " | ".join(str(c)[:50] for c in row if c)
        if cells.strip():
            result += cells + "\n"

    return result


def get_custom_range(sheet_key: str, sheet_name: str, cell_range: str) -> str:
    """
    ดึงข้อมูล range ที่ระบุเอง
    sheet_key: 'survey', 'dashboard', 'oar'
    """
    sheet_id = SHEET_IDS.get(sheet_key)
    if not sheet_id:
        return f"ไม่พบ sheet key: {sheet_key}"

    full_range = f"{sheet_name}!{cell_range}" if sheet_name else cell_range
    data = read_sheet(sheet_id, full_range)

    if not data:
        return "ไม่พบข้อมูลใน range นี้"

    result = ""
    for row in data:
        result += " | ".join(str(cell) for cell in row) + "\n"

    return result
