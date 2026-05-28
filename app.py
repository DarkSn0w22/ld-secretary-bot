"""
OWNDAYS L&D Secretary Bot v2
AI Agent เลขา — LINE Bot + Claude API + Google Sheets
"""

import os
import json
import hashlib
import hmac
import base64
from flask import Flask, request, abort
import anthropic
import requests
from sheets_tools import get_survey_summary, get_oar_summary, get_sheet_names, SHEET_IDS

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "your-channel-secret")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "your-access-token")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-anthropic-key")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

TOOLS = [
    {
        "name": "get_survey_data",
        "description": "ดึงข้อมูล Training Survey จาก Google Sheets เพื่อดูคะแนนความพึงพอใจการอบรม",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_oar_data",
        "description": "ดึงข้อมูล Training Registration (OAR) จาก Google Sheets เพื่อดูการลงทะเบียนอบรม",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_sheet_list",
        "description": "ดูรายชื่อ sheets ทั้งหมดใน spreadsheet",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_key": {
                    "type": "string",
                    "description": "ชื่อ sheet: survey, dashboard, หรือ oar",
                    "enum": ["survey", "dashboard", "oar"]
                }
            },
            "required": ["sheet_key"]
        }
    }
]


def execute_tool(tool_name, tool_input):
    if tool_name == "get_survey_data":
        return get_survey_summary()
    elif tool_name == "get_oar_data":
        return get_oar_summary()
    elif tool_name == "get_sheet_list":
        sheet_key = tool_input.get("sheet_key", "survey")
        names = get_sheet_names(SHEET_IDS.get(sheet_key, SHEET_IDS["survey"]))
        return f"Sheets ใน {sheet_key}: {', '.join(names)}" if names else "ไม่พบข้อมูล"
    return "ไม่พบ tool นี้"


SECRETARY_PROMPT = """คุณคือ "Secretary" AI เลขาส่วนตัวของ Peanut (Regional L&D Manager, OWNDAYS Thailand)

บทบาท:
- ตอบเป็นภาษาไทย กระชับ เหมาะกับ LINE
- ห้ามใช้ Markdown เช่น ** หรือ ### เด็ดขาด ใช้ plain text เท่านั้น
- ใช้ emoji แทน bullet point ได้
- เมื่อถูกถามข้อมูล Survey หรือ Training ให้ดึงจาก Google Sheets เสมอ
- เรียงข้อมูลจากใหม่ไปเก่า

ข้อมูลพื้นฐาน:
- OWNDAYS Thailand 73 สาขา พนักงาน 400+ คน
- Trainer 18 คน: Sales (Judy,Pui,Jets,Trin,Nueng,Tonpalm), Optical (Jib,Jajah,Kio,Toy,Kwang,Mark), Optometry (Fair,Benz,Milk,Lookaew)
- 5 พื้นที่: Megastore, Metropolitan, North+Central, West+NE, South+Eastern
- แพลตฟอร์ม: OWNDAYS Connect (od-connect.com)
"""

conversations = {}
MAX_HISTORY = 20


def get_claude_response(user_id, message):
    if user_id not in conversations:
        conversations[user_id] = []

    history = conversations[user_id]
    history.append({"role": "user", "content": message})

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
        conversations[user_id] = history

    try:
        while True:
            response = claude.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                system=SECRETARY_PROMPT,
                tools=TOOLS,
                messages=history
            )

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"Tool: {block.name}")
                        result = execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                history.append({"role": "user", "content": tool_results})
                continue

            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            history.append({"role": "assistant", "content": final_text})
            return final_text

    except Exception as e:
        print(f"Claude Error: {e}")
        return "ขอโทษครับ ระบบมีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้ง"


def verify_signature(body, signature):
    hash = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return signature == base64.b64encode(hash).decode("utf-8")


def reply_message(reply_token, text):
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
    payload = {"replyToken": reply_token, "messages": messages[:5]}
    requests.post(url, headers=headers, json=payload)


@app.route("/", methods=["GET"])
def health_check():
    return "LD Secretary Bot v2 is running!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        abort(400)

    events = json.loads(body).get("events", [])

    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_id = event["source"]["userId"]
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            print(f"User {user_id[:8]}...: {user_message}")

            if user_message.strip() == "/myid":
                reply_message(reply_token, f"Your LINE User ID:\n{user_id}")
            else:
                response = get_claude_response(user_id, user_message)
                print(f"Bot: {response[:100]}...")
                reply_message(reply_token, response)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"LD Secretary Bot v2 starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
