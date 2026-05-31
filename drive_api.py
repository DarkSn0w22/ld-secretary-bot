"""
Google Drive API — บันทึกไฟล์จาก agents
DRIVE_ROOT_FOLDER_ID = root folder สำหรับ AI reports
ใช้ service account เดิม (GOOGLE_CREDENTIALS_JSON)
"""
import os
import io
import json
import base64

DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", "")

# Sub-folder names per agent
AGENT_FOLDERS = {
    "rex":    "Rex — Sales Reports",
    "sage":   "Sage — Training Reports",
    "coin":   "Coin — Budget Reports",
    "pulse":  "Pulse — Trainer Analysis",
    "pixel":  "Pixel — Web Analytics",
    "sigma":  "Sigma — Data Analysis",
    "atlas":  "Atlas — Strategy Reports",
    "guard":  "Guard — QA Reports",
    "lex":    "Lex — Legal Documents",
    "people": "People — HR Reports",
    "lens":   "Lens — Content",
    "rocket": "Rocket — General",
}

_drive_service = None
_folder_id_cache: dict = {}


def _get_drive_service():
    """สร้าง Drive service — ลำดับ: OAuth user token → service account"""
    global _drive_service
    if _drive_service:
        return _drive_service
    try:
        from googleapiclient.discovery import build

        # ── วิธีที่ 1: OAuth refresh token ของ user (ไม่มีปัญหา quota) ──
        refresh_token = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN", "")
        client_id     = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "") or os.getenv("GA4_OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "") or os.getenv("GA4_OAUTH_CLIENT_SECRET", "")

        if refresh_token and client_id and client_secret:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            creds.refresh(Request())
            _drive_service = build("drive", "v3", credentials=creds)
            print("[Drive] using OAuth user credentials ✓")
            return _drive_service

        # ── วิธีที่ 2: Service Account (อาจติด quota issue) ──
        from google.oauth2 import service_account
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        SCOPES = ["https://www.googleapis.com/auth/drive"]
        if creds_json:
            creds_dict = json.loads(base64.b64decode(creds_json).decode())
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            creds = service_account.Credentials.from_service_account_file(
                os.getenv("GOOGLE_KEY_FILE", "credentials.json"), scopes=SCOPES)
        _drive_service = build("drive", "v3", credentials=creds)
        print("[Drive] using service account credentials")
        return _drive_service

    except Exception as e:
        print(f"[Drive] service init error: {e}")
        return None


def _get_or_create_folder(parent_id: str, name: str) -> str:
    """หาหรือสร้าง sub-folder ใน parent"""
    cache_key = f"{parent_id}/{name}"
    if cache_key in _folder_id_cache:
        return _folder_id_cache[cache_key]

    svc = _get_drive_service()
    if not svc:
        return parent_id

    # ค้นหา folder ที่มีชื่อนี้อยู่แล้ว
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         f"and '{parent_id}' in parents and trashed=false")
    results = svc.files().list(q=q, fields="files(id,name)").execute()
    files = results.get("files", [])
    if files:
        fid = files[0]["id"]
    else:
        # สร้างใหม่
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        f = svc.files().create(body=meta, fields="id").execute()
        fid = f["id"]

    _folder_id_cache[cache_key] = fid
    return fid


def _get_agent_folder(agent_id: str) -> str:
    """คืน folder ID ของ agent — สร้างถ้ายังไม่มี"""
    if not DRIVE_ROOT_FOLDER_ID:
        return ""
    folder_name = AGENT_FOLDERS.get(agent_id, f"{agent_id.title()} Reports")
    return _get_or_create_folder(DRIVE_ROOT_FOLDER_ID, folder_name)


def save_text_report(agent_id: str, filename: str, content: str) -> dict:
    """บันทึก text report เป็น Google Doc (plain text)
    คืน {ok, url, file_id, error}
    """
    svc = _get_drive_service()
    if not svc:
        return {"ok": False, "error": "Drive service ไม่พร้อม"}

    folder_id = _get_agent_folder(agent_id)
    if not folder_id:
        return {"ok": False, "error": "ไม่มี DRIVE_ROOT_FOLDER_ID"}

    try:
        from googleapiclient.http import MediaInMemoryUpload
        file_bytes = content.encode("utf-8")
        media = MediaInMemoryUpload(file_bytes, mimetype="text/plain", resumable=False)
        meta = {"name": filename, "parents": [folder_id]}
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        # ทำให้ผู้มีลิงก์ดูได้
        svc.permissions().create(
            fileId=f["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()
        return {"ok": True, "url": f.get("webViewLink", ""), "file_id": f["id"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_excel_report(agent_id: str, filename: str, excel_bytes: bytes) -> dict:
    """บันทึก Excel (.xlsx) ไฟล์"""
    svc = _get_drive_service()
    if not svc:
        return {"ok": False, "error": "Drive service ไม่พร้อม"}

    folder_id = _get_agent_folder(agent_id)
    if not folder_id:
        return {"ok": False, "error": "ไม่มี DRIVE_ROOT_FOLDER_ID"}

    try:
        from googleapiclient.http import MediaInMemoryUpload
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        media = MediaInMemoryUpload(excel_bytes, mimetype=mime, resumable=False)
        meta = {"name": filename, "parents": [folder_id]}
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        svc.permissions().create(
            fileId=f["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()
        return {"ok": True, "url": f.get("webViewLink", ""), "file_id": f["id"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_pdf_report(agent_id: str, filename: str, pdf_bytes: bytes) -> dict:
    """บันทึก PDF ไฟล์"""
    svc = _get_drive_service()
    if not svc:
        return {"ok": False, "error": "Drive service ไม่พร้อม"}

    folder_id = _get_agent_folder(agent_id)
    if not folder_id:
        return {"ok": False, "error": "ไม่มี DRIVE_ROOT_FOLDER_ID"}

    try:
        from googleapiclient.http import MediaInMemoryUpload
        media = MediaInMemoryUpload(pdf_bytes, mimetype="application/pdf", resumable=False)
        meta = {"name": filename, "parents": [folder_id]}
        f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        svc.permissions().create(
            fileId=f["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()
        return {"ok": True, "url": f.get("webViewLink", ""), "file_id": f["id"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_spreadsheet_data(agent_id: str, title: str, rows: list) -> dict:
    """สร้าง Google Sheets จาก list of lists และคืนลิงก์"""
    svc = _get_drive_service()
    if not svc:
        return {"ok": False, "error": "Drive service ไม่พร้อม"}

    folder_id = _get_agent_folder(agent_id)
    if not folder_id:
        return {"ok": False, "error": "ไม่มี DRIVE_ROOT_FOLDER_ID"}

    try:
        from googleapiclient.discovery import build as gbuild
        from google.oauth2 import service_account

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if creds_json:
            creds_dict = json.loads(base64.b64decode(creds_json).decode())
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
        else:
            creds = service_account.Credentials.from_service_account_file(
                os.getenv("GOOGLE_KEY_FILE", "credentials.json"), scopes=SCOPES
            )

        sheets_svc = gbuild("sheets", "v4", credentials=creds)

        # สร้าง Spreadsheet ใหม่
        spreadsheet = sheets_svc.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Data"}}],
        }).execute()
        sid = spreadsheet["spreadsheetId"]

        # เขียนข้อมูล
        if rows:
            sheets_svc.spreadsheets().values().update(
                spreadsheetId=sid,
                range="Data!A1",
                valueInputOption="RAW",
                body={"values": rows},
            ).execute()

        # ย้ายไป folder
        drive_svc = _get_drive_service()
        drive_svc.files().update(
            fileId=sid,
            addParents=folder_id,
            removeParents="root",
            fields="id",
        ).execute()
        # Share
        drive_svc.permissions().create(
            fileId=sid,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
        return {"ok": True, "url": url, "file_id": sid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def drive_ready() -> bool:
    return bool(
        DRIVE_ROOT_FOLDER_ID and
        (os.getenv("GOOGLE_CREDENTIALS_JSON") or os.path.exists("credentials.json"))
    )
