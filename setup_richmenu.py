"""
LINE Rich Menu Setup — รัน 1 ครั้งเพื่อ activate Rich Menu ใน LINE Bot
ใช้ token จาก env LINE_CHANNEL_ACCESS_TOKEN
"""
import os
import json
import requests

LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "richmenu.png")

HEADERS = {
    "Authorization": f"Bearer {LINE_TOKEN}",
    "Content-Type": "application/json",
}

# ── 6 buttons, 3 cols × 2 rows ────────────────────────────────
W, H = 2500, 1686
bw, bh = W // 3, H // 2
AREAS = [
    # Row 1
    {"bounds": {"x": 0,    "y": 0,   "width": bw, "height": bh},
     "action": {"type": "message", "text": "ให้ Rex สรุป sales report ครับ"}},
    {"bounds": {"x": bw,   "y": 0,   "width": bw, "height": bh},
     "action": {"type": "message", "text": "ให้ Pulse สรุปสถานะ training ครับ"}},
    {"bounds": {"x": bw*2, "y": 0,   "width": bw, "height": bh},
     "action": {"type": "message", "text": "ให้ Coin สรุป budget ครับ"}},
    # Row 2
    {"bounds": {"x": 0,    "y": bh,  "width": bw, "height": bh},
     "action": {"type": "message", "text": "ให้ People สรุป HR update ครับ"}},
    {"bounds": {"x": bw,   "y": bh,  "width": bw, "height": bh},
     "action": {"type": "message", "text": "ให้ Pixel เช็ค website ครับ"}},
    {"bounds": {"x": bw*2, "y": bh,  "width": bw, "height": bh},
     "action": {"type": "message", "text": "สรุปรายงานวันนี้ให้หน่อยครับ"}},
]

MENU_DEF = {
    "size":     {"width": W, "height": H},
    "selected": True,
    "name":     "OWNDAYS L&D AI Menu",
    "chatBarText": "เมนู L&D AI 🚀",
    "areas":    AREAS,
}


def delete_existing_menus():
    """ลบ Rich Menu เก่าออกก่อน"""
    r = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=HEADERS)
    if r.status_code == 200:
        for menu in r.json().get("richmenus", []):
            mid = menu["richMenuId"]
            requests.delete(f"https://api.line.me/v2/bot/richmenu/{mid}", headers=HEADERS)
            print(f"  Deleted old menu: {mid}")


def create_menu() -> str:
    """สร้าง Rich Menu และคืน richMenuId"""
    r = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        json=MENU_DEF,
    )
    if r.status_code != 200:
        raise Exception(f"Create failed: {r.status_code} {r.text}")
    mid = r.json()["richMenuId"]
    print(f"✅ Created menu: {mid}")
    return mid


def upload_image(menu_id: str):
    """อัพโหลด PNG ไปยัง Rich Menu"""
    with open(IMAGE_PATH, "rb") as f:
        r = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={
                "Authorization": f"Bearer {LINE_TOKEN}",
                "Content-Type": "image/png",
            },
            data=f.read(),
        )
    if r.status_code != 200:
        raise Exception(f"Upload failed: {r.status_code} {r.text}")
    print(f"✅ Image uploaded")


def set_default(menu_id: str):
    """ตั้ง Rich Menu เป็น default สำหรับทุกคน"""
    r = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
        headers=HEADERS,
    )
    if r.status_code != 200:
        # fallback: set as default menu
        r2 = requests.post(
            f"https://api.line.me/v2/bot/richmenu/default/{menu_id}",
            headers=HEADERS,
        )
        if r2.status_code not in (200, 201):
            print(f"⚠️  Set default warning: {r2.status_code} {r2.text}")
            return
    print(f"✅ Set as default menu")


def setup_richmenu() -> dict:
    """Main function — delete old → create → upload image → set default"""
    if not LINE_TOKEN:
        return {"ok": False, "error": "ไม่มี LINE_CHANNEL_ACCESS_TOKEN"}
    if not os.path.exists(IMAGE_PATH):
        return {"ok": False, "error": f"ไม่พบรูป: {IMAGE_PATH}"}

    try:
        print("Deleting old menus...")
        delete_existing_menus()
        print("Creating new menu...")
        menu_id = create_menu()
        print("Uploading image...")
        upload_image(menu_id)
        print("Setting as default...")
        set_default(menu_id)
        print(f"\n🎉 Rich Menu พร้อมใช้งานแล้วครับ! menu_id={menu_id}")
        return {"ok": True, "menu_id": menu_id}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = setup_richmenu()
    print(json.dumps(result, ensure_ascii=False, indent=2))
