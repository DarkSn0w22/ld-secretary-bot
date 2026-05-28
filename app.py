"""
OWNDAYS L&D Secretary Bot
AI Agent เลขา — LINE Bot + Claude API
"""

import os
import json
import hashlib
import hmac
import base64
from flask import Flask, request, abort
import anthropic
import requests

app = Flask(__name__)

# =============================================================
# CONFIG — ใส่ค่าจริงใน Environment Variables ตอน deploy
# =============================================================
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "your-channel-secret")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "your-access-token")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-anthropic-key")

# =============================================================
# CLAUDE CLIENT
# =============================================================
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =============================================================
# SYSTEM PROMPT — บุคลิกของ Agent เลขา
# =============================================================
SECRETARY_PROMPT = """คุณคือ "Secretary" — AI เลขาส่วนตัวของ Peanut (Regional L&D Manager, OWNDAYS Thailand)

บทบาทของคุณ:
- เลขาส่วนตัวที่ช่วยจัดการงาน, สรุปข้อมูล, เตือนความจำ, และ draft ข้อความ
- ตอบเป็นภาษาไทยเป็นหลัก ยกเว้นศัพท์เฉพาะทาง
- กระชับ ตรงประเด็น เหมาะกับอ่านบน LINE (ข้อความสั้น)
- ใช้ emoji พอเหมาะ ไม่มากเกินไป

ข้อมูลพื้นฐานที่ต้องรู้:
- OWNDAYS Thailand มี 73 สาขา, พนักงานหน้าร้าน 400+ คน
- ทีม L&D มี trainer 18 คน แบ่ง 3 division: Sales, Optical, Optometry
- Training Manager: Judy (Sales), Jib (Optical), Fair (Optometry)
- เพื่อนร่วมงาน L&D: Jame
- โครงสร้างใหม่แบ่งเป็น 5 พื้นที่: Megastore, Metropolitan, North+Central, West+NE, South+Eastern
- แพลตฟอร์มเรียนรู้: OWNDAYS Connect (od-connect.com)

สิ่งที่ยังทำไม่ได้ตอนนี้ (แต่จะเพิ่มในอนาคต):
- ดึงข้อมูลจาก Google Sheets โดยตรง
- เช็ค Google Calendar
- ส่ง Daily Brief อัตโนมัติ

ถ้าถูกถามเรื่องที่ยังทำไม่ได้ ให้บอกตรงๆ ว่า "ฟีเจอร์นี้กำลังพัฒนาอยู่ครับ"
"""

# =============================================================
# CONVERSATION MEMORY (in-memory, per user)
# จะอัพเกรดเป็น database ใน phase ถัดไป
# =============================================================
conversations = {}  # {user_id: [{"role": ..., "content": ...}]}
MAX_HISTORY = 20    # เก็บแค่ 20 ข้อความล่าสุดต่อ user


def get_claude_response(user_id: str, message: str) -> str:
    """ส่งข้อความไป Claude API แล้วรับคำตอบกลับมา"""

    # ดึง history ของ user
    if user_id not in conversations:
        conversations[user_id] = []

    history = conversations[user_id]

    # เพิ่มข้อความใหม่
    history.append({"role": "user", "content": message})

    # ตัดให้เหลือแค่ MAX_HISTORY
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        conversations[user_id] = history

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SECRETARY_PROMPT,
            messages=history
        )

        assistant_message = response.content[0].text

        # เก็บคำตอบลง history
        history.append({"role": "assistant", "content": assistant_message})

        return assistant_message

    except Exception as e:
        print(f"Claude API Error: {e}")
        return "ขอโทษครับ ระบบมีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้ง 🙏"


# =============================================================
# LINE WEBHOOK VERIFICATION
# =============================================================
def verify_signature(body: str, signature: str) -> bool:
    """ตรวจสอบว่า request มาจาก LINE จริง"""
    hash = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return signature == base64.b64encode(hash).decode("utf-8")


def reply_message(reply_token: str, text: str):
    """ส่งข้อความตอบกลับผ่าน LINE Reply API"""

    # LINE จำกัด 5000 ตัวอักษรต่อ message
    # ถ้ายาวเกินให้แบ่งส่ง
    messages = []
    while text:
        chunk = text[:5000]
        messages.append({"type": "text", "text": chunk})
        text = text[5000:]

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages[:5]  # LINE จำกัด 5 messages ต่อ reply
    }

    requests.post(url, headers=headers, json=payload)


# =============================================================
# ROUTES
# =============================================================
@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return "LD Secretary Bot is running! 🤖", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """LINE Webhook — รับข้อความจาก LINE"""

    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")

    # Verify signature
    if not verify_signature(body, signature):
        abort(400)

    # Parse events
    events = json.loads(body).get("events", [])

    for event in events:
        # รับแค่ข้อความ text
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_id = event["source"]["userId"]
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            print(f"📩 User {user_id[:8]}...: {user_message}")

            # ส่งไป Claude
            response = get_claude_response(user_id, user_message)

            print(f"🤖 Bot: {response[:100]}...")

            # ตอบกลับ LINE
            reply_message(reply_token, response)

    return "OK", 200


# =============================================================
# RUN
# =============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 LD Secretary Bot starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
