"""
OWNDAYS L&D Secretary Bot v6
LINE Bot + Claude API + Google Sheets + PostgreSQL Memory
"""

import os
import json
import hashlib
import hmac
import base64
from flask import Flask, request, abort, jsonify, send_file, Response
import anthropic
from models_config import get_model
import requests
from sheets_tools import get_survey_summary, get_oar_summary, get_sheet_names, SHEET_IDS
from memory import init_db, load_history, save_message, clear_history, get_message_count
from scheduler import start_scheduler
from manager_agent import run_manager, run_scheduled_task
from google_search import google_search
from trainer_manager_agent import run_trainer_manager
from reporter_agent import run_reporter
from reviewer_agent import run_reviewer
from financial_agent import run_financial_manager
from legal_agent import run_legal_manager
from hr_agent import run_hr_manager
from web_agent import run_web_admin
from data_agent import run_data_analyst
from creator_agent import run_creator
from models_config import print_model_summary

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")  # ถ้าเว้นว่าง = เปิด public (จะเตือนใน log)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Init DB on startup
init_db()
print_model_summary()

# =============================================================
# TOOLS
# =============================================================
TOOLS = [
    {
        "name": "get_survey_data",
        "description": "ดึงข้อมูล Training Survey จาก Google Sheets",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_oar_data",
        "description": "ดึงข้อมูล Training Registration (OAR) จาก Google Sheets",
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
                    "enum": ["survey", "dashboard", "oar"]
                }
            },
            "required": ["sheet_key"]
        }
    },
    {
        "name": "ask_manager",
        "description": "ส่งงานที่ซับซ้อนให้ Manager AI (Atlas) วิเคราะห์และประสานงาน เช่น สรุปภาพรวม, วิเคราะห์เชิงลึก, เสนอแผนงาน",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "งานที่ต้องการให้ Manager AI ทำ"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "web_search",
        "description": "ค้นหาข้อมูลจาก Google เช่น benchmark L&D, best practices, trend, สถิติ, ข่าวล่าสุด",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "คำค้นหา"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ask_trainer_manager",
        "description": "ให้ Trainer Manager AI (Pulse) วิเคราะห์หลักสูตร ติดตาม trainer performance และเสนอแนวทางพัฒนา",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "งานที่ต้องการเช่น วิเคราะห์ trainer, สรุปหลักสูตร, หา low score"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_reporter",
        "description": "ให้ Reporter AI (Sage) จัดทำรายงานภาพรวม L&D พร้อม highlight และ recommendation",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "description": "ประเภทรายงาน เช่น weekly, monthly, summary"
                }
            },
            "required": []
        }
    },
    {
        "name": "ask_reviewer",
        "description": "ให้ Reviewer/QA AI (Guard) ตรวจสอบคุณภาพงานก่อนส่งออก เช่น รายงาน, email, เนื้อหาการฝึกอบรม",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "เนื้อหาที่ต้องการตรวจสอบ"
                },
                "content_type": {
                    "type": "string",
                    "description": "ประเภทงาน เช่น report, email, training_material, analysis"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "ask_financial",
        "description": "ให้ Financial Manager AI (Coin) วิเคราะห์ค่าใช้จ่าย budget, forecast, ROI และรายงานการเงิน L&D",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "งานที่ต้องการ เช่น สรุปค่าใช้จ่าย, forecast, ROI, แจ้งเตือน budget"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_legal",
        "description": "ให้ Legal Manager AI (Lex) ให้คำปรึกษากฎหมายแรงงาน, PDPA, สัญญาฝึกอบรม, IP content, กฎหมาย KH/LA",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "คำถามหรืองานด้านกฎหมาย เช่น ตรวจสัญญา, ถาม PDPA, เช็คกฎแรงงาน"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_hr",
        "description": "ให้ HR Manager AI (People) ค้นหาข้อมูลพนักงาน, เช็ค probation, วิเคราะห์ headcount, turnover และ HR insights",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "งาน HR เช่น ค้นหาพนักงาน, เช็ค probation, สรุป headcount"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_web_admin",
        "description": "ให้ Web Admin AI (Pixel) ตรวจสอบสถานะ od-connect.com, วิเคราะห์ content และแนะนำการปรับปรุง",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "งาน web เช่น เช็คสถานะเว็บ, ดู content, แนะนำ UX"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_data_analyst",
        "description": "ให้ Data Analysis AI (Sigma) วิเคราะห์ข้อมูลเชิงลึก, trends, KPI comparison และ insights",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "งานวิเคราะห์ เช่น เปรียบเทียบ area, trainer ranking, trend analysis"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "ask_creator",
        "description": "ให้ Creator AI (Lens) สร้าง training content, quiz, สคริปต์, หรือสื่อการสอน",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "งาน content เช่น เขียน quiz BSC, สร้างสคริปต์ video, แต่ง LINE message"}
            },
            "required": ["task"]
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
    elif tool_name == "ask_manager":
        task = tool_input.get("task", "")
        return run_manager(task)
    elif tool_name == "web_search":
        query = tool_input.get("query", "")
        return google_search(query)
    elif tool_name == "ask_trainer_manager":
        task = tool_input.get("task", "")
        return run_trainer_manager(task)
    elif tool_name == "ask_reporter":
        report_type = tool_input.get("report_type", "weekly")
        return run_reporter(report_type)
    elif tool_name == "ask_reviewer":
        review_content = tool_input.get("content", "")
        content_type = tool_input.get("content_type", "report")
        return run_reviewer(review_content, content_type)
    elif tool_name == "ask_financial":
        task = tool_input.get("task", "")
        return run_financial_manager(task)
    elif tool_name == "ask_legal":
        task = tool_input.get("task", "")
        return run_legal_manager(task)
    elif tool_name == "ask_hr":
        task = tool_input.get("task", "")
        return run_hr_manager(task)
    elif tool_name == "ask_web_admin":
        task = tool_input.get("task", "")
        return run_web_admin(task)
    elif tool_name == "ask_data_analyst":
        task = tool_input.get("task", "")
        return run_data_analyst(task)
    elif tool_name == "ask_creator":
        task = tool_input.get("task", "")
        return run_creator(task)
    return "ไม่พบ tool นี้"


# =============================================================
# SYSTEM PROMPT
# =============================================================
SECRETARY_PROMPT = """คุณคือ "Rocket" — AI เลขาส่วนตัวของ Peanut ผู้ชาย ทำงานให้ตลอด 24 ชั่วโมง

== บุคลิกและการสื่อสาร ==
- คุณเป็นผู้ชาย ใช้คำลงท้าย "ครับ" เสมอ ห้ามใช้ "ค่ะ" หรือ "นะคะ" เด็ดขาด
- ตอบภาษาไทยเป็นหลัก กระชับ ตรงประเด็น เหมาะกับอ่านบน LINE
- ห้ามใช้ Markdown เช่น ** ## __ เด็ดขาด ใช้ plain text และ emoji แทน
- เรียงข้อมูลจากใหม่ไปเก่าเสมอ
-  ทำหน้าที่ รวบรวมงานจากแต่ละแผนกในแต่ละวัน นำเสนองานหรือโปรเจค ไอเดีย ของแต่ละแผนกให้หัวหน้างาน Peanut กด อนุมัติ 
- เมื่อถูกถามข้อมูล Survey, Training, OAR ให้ดึงจาก Google Sheets ทุกครั้ง
- ถ้าข้อมูลไม่เพียงพอ ให้บอกว่าขอข้อมูลเพิ่มเติมแทน อย่าพยายามเดาหรือสร้างข้อมูลขึ้นมาเอง
- ถ้าถูกถามคำถามที่อยู่นอกเหนือความสามารถของคุณ ให้ตอบว่า "ขอโทษครับ เรื่องนี้ผมไม่แน่ใจ ครับ" อย่าพยายามตอบหรือเดาคำตอบเองเด็ดขาด
- ถ้าถูกถามคำถามที่เกี่ยวกับกฎหมาย ให้ใช้ Legal Manager AI (Lex) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- ถ้าถูกถามคำถามที่เกี่ยวกับการเงิน ให้ใช้ Financial Manager AI (Coin) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด 
- ถ้าถูกถามคำถามที่เกี่ยวกับการวิเคราะห์ข้อมูลเชิงลึก หรือการวางแผนกลยุทธ์ ให้ใช้ Manager AI (Atlas) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- ถ้าถูกถามคำถามที่เกี่ยวกับการวิเคราะห์ trainer performance หรือการพัฒนาหลักสูตร ให้ใช้ Trainer Manager AI (Pulse) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- ถ้าถูกถามคำถามที่เกี่ยวกับการจัดทำรายงานภาพรวม หรือการสรุปข้อมูล ให้ใช้ Reporter AI (Sage) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- ถ้าถูกถามคำถามที่เกี่ยวกับการตรวจสอบคุณภาพงาน เช่น รายงาน, email, เนื้อหาการฝึกอบรม ให้ใช้ Reviewer/QA AI (Guard) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- มีไอเดียใหม่ๆมานำเสนอเสมอ เช่น การใช้เครื่องมือใหม่ๆ, การปรับปรุงการทำงาน, การแจ้งเตือนที่เป็นประโยชน์, การค้นหาโอกาสในการพัฒนา L&D


== เกี่ยวกับ Peanut ==
- ชื่อจริง: Peanut (รัชกฤช เดชาเนติรัตน์)
- ตำแหน่ง: Regional L&D Manager, OWNDAYS Thailand
- ดูแล: OWNDAYS Academy — Thailand, Cambodia, Laos
- รับผิดชอบ: 70 สาขา, พนักงานหน้าร้าน 400+ คน, trainer 18 คน
- อายุงาน: 10 ปี (เริ่ม มกราคม. 2016)
บทบาทระดับกลยุทธ์ (Strategic Level):
- วิเคราะห์ความต้องการภาพรวมขององค์กร (Organizational Needs) ในระดับภูมิภาค
- ค้นหาโอกาสใหม่ๆ ในการเติบโตและพัฒนาการฝึกอบรม (Keep searching opportunities for growth)
- วางกลยุทธ์เพื่อพัฒนาศักยภาพพนักงานทั้งบริษัท (Develop company employee)
- เชื่อมโยงข้อมูลการฝึกอบรมเข้ากับเป้าหมายทางธุรกิจของ 5 พื้นที่ (Align training with business goals)
- ประสานงานกับผู้บริหารระดับสูงและผู้มีส่วนได้ส่วนเสีย (Stakeholders) เพื่อให้แน่ใจว่าการฝึกอบรมสอดคล้องกับทิศทางของบริษัท
บทบาทระดับปฏิบัติการ (Operational Level):
- ติดตามและวิเคราะห์ข้อมูลการฝึกอบรม เช่น คะแนน Survey, OAR, ประสิทธิภาพของ trainer และหลักสูตรต่างๆ (Track and analyze training data)
- เสนอแนวทางพัฒนา Trainer แต่ละบุคคล หรือสิ่งที่อยากขอรับการสนับสนุนเพิ่มเติมให้ทีมตามบทบาท Manager (Suggest development for each trainer or support needed for manager role)
- จัดทำรายงานสรุปภาพรวมการฝึกอบรมในแต่ละเดือน พร้อม highlight และ recommendation (Create monthly report with highlights and recommendations)


== ทีม L&D ==
- Jame: Regional (เพื่อนร่วมงาน L&D)
- Judy: Training Manager (Sales)
- Jib: Training Manager (Optical)
- Dr.Fair: Training Manager (Optometry)
Trainer Sales: Pui(Asst.Manager), Jets, Trin, Nueng, Tonpalm
Trainer Optical: Jajah(Asst.Manager), Kio, Toy, Kwang, Mark
Trainer Optometry: Dr.Benz, Dr.Milk, Dr.Lookaew

== โครงสร้างพื้นที่ (ใหม่ เม.ย. 2026) ==
5 พื้นที่: Megastore / Metropolitan / North+Central / West+NE / South+Eastern

== หลักสูตรทั้งหมด 16 หลักสูตร ==
Hybrid: OTT (Orientation), PE (Personality Enhancement), BOBT (Basic On-Board), MOBT (Moderate On-Board), MTOBT (Mastery On-Board), SMOT (Store Manager Orientation), MOT (Management Orientation)
Sales: BSC (Basic Sales Essential), MSC (Moderate Sales Participatory), MTSC (Mastery Sales Delegation)
Optical: BOC (Basic Optical Comprehension), MOC (Moderate Optical Progression), MTOC (Mastery Optical Evolution)
Optometry: BVC (Basic Vision Fundamentals), MVC (Moderate Vision Care Advisor), MTVC (Mastery Professional Vision Management)
Outsource: Professional Consultative Selling

เส้นทางการเรียน: OTT → PE → Basic (BSC/BOC/BVC) → BOBT → Moderate → MOBT → Mastery → MTOBT
Management Track: SMOT → MOT

== Survey System ==
10 คำถาม แบ่งเป็น 2 กลุ่ม:
Trainer (1-5): ความรู้, การถ่ายทอด, เทคนิคนำเสนอ, บรรยากาศ, ตอบคำถาม
Program (6-10): สื่อการสอน, กิจกรรม, สถานที่, ระยะเวลา, ความพึงพอใจ
คะแนน: Very Good=4, Good=3, Quite Good=2, Moderate=1, Needs Improvement=0

== แพลตฟอร์มและระบบ ==
- OWNDAYS Connect: od-connect.com (WIX) — มีทั้ง Web และ App (Android/iOS)
- ลงทะเบียน: od-connect.com/oar-owndays-academy-registration
- Survey: od-connect.com/oar-survey
- Dashboard: HTML + Chart.js + Google Apps Script API
- ข้อมูลเก็บใน Google Drive และ Google Sheets

== สาขาทั้งหมด ==
MEGA Bangna, Zpell @ Future Park, Central Eastville, Seacon Bangkae, Seacon Square, Fashion Island, The Mall Korat, Central Udon, Central Chiangmai, Gaysorn Village Premium Store, Central Mahachai, Central Phuket, Central Westgate, CentralWorld, Terminal 21 Pattaya, ICONSIAM, Gateway Bangsue, Donki Mall Thonglor, Central Rama 3, Central Village (Outlet), Central Hatyai, Central Rayong, Siam Premium Outlets, Siam Center, Central Salaya, Central Pinklao, Central Rama 2, Central Si Racha, Central Ayutthaya, Central Khonkaen, Central Chanthaburi, Terminal 21 Rama 3, Central Ramindra, Central Chiangrai, Central Samui, Central Nakhon Si, Marche Thonglor, Park Silom, The Mall Bangkae, Central Westville, Central Nakhon Pathom, True Digital Park, V-Square Plaza Nakhon Sawan, Makro Sri Ayutthaya, Central Rama 9, One Bangkok, Robinson Ratchaburi, Market Village Huahin, Lotus's Mall Makro Sathon, Robinson Lifestyle Kanchanaburi, Esplanade Ratchada, Charn At The Avenue, Siam Square One, Robinson Latkrabang, The Mall Bang Kapi, Maya Chiangmai, Robinson Lifestyle Chachoengsao, Central Chiangmai Airport, Central Krabi, Outlet Square Muang Thong Thani, Robinson Lifestyle Saraburi, Robinson Lifestyle Trang, Robinson Lifestyle Chonburi, Robinson Lifestyle Suphanburi, Robinson Lifestyle Buriram, The Glass Market Bangna, Imperial Samrong, Central Phitsanulok, Robinson Suphanburi, Central Lampang, Central Khonkaen Campus, Central Surat Thani, Central Northville, Happitat Bangna, Central Chaengwattana, Robinson Prachinburi, Robinson Phetchaburi, Central Park, The Central Phaholyothin และอื่นๆในอนาคต

== สิ่งที่ยังทำไม่ได้ (แจ้งตรงๆ) ==
- เช็ค/ส่ง Email @owndays.com (ต้องรอ IT อนุมัติ)
- เช็ค Google Calendar (กำลังพัฒนา)

เมื่อต้องค้นหาข้อมูลจากอินเทอร์เน็ต ให้ใช้ web_search tool ได้เลย ไม่ต้องพึ่ง agent อื่น
"""


# =============================================================
# CLAUDE RESPONSE
# =============================================================
def get_claude_response(user_id: str, message: str) -> str:
    # โหลด history จาก DB
    history = load_history(user_id, limit=20)

    # เพิ่มข้อความใหม่
    history.append({"role": "user", "content": message})
    save_message(user_id, "user", message)

    try:
        while True:
            response = claude.messages.create(
                model=get_model("rocket"),
                max_tokens=1024,
                system=SECRETARY_PROMPT,
                tools=TOOLS,
                messages=history
            )

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})
                save_message(user_id, "assistant", response.content)

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
                save_message(user_id, "user", tool_results)
                continue

            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            save_message(user_id, "assistant", final_text)
            return final_text

    except Exception as e:
        print(f"Claude Error: {e}")
        return "ขอโทษครับ ระบบมีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้ง"


# =============================================================
# LINE
# =============================================================
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


# =============================================================
# ROUTES
# =============================================================
@app.route("/", methods=["GET"])
def health_check():
    return "LD Secretary Bot v6 - Rocket is running!", 200


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

            # Special commands
            if user_message.strip() == "/myid":
                reply_message(reply_token, f"Your LINE User ID:\n{user_id}")
            elif user_message.strip() == "/clearmemory":
                success = clear_history(user_id)
                reply_message(reply_token, "ลบความจำทั้งหมดแล้วครับ 🗑️" if success else "เกิดข้อผิดพลาดครับ")
            elif user_message.strip() == "/memstats":
                count = get_message_count(user_id)
                reply_message(reply_token, f"มีข้อความในความจำทั้งหมด {count} ข้อความครับ 🧠")
            else:
                response = get_claude_response(user_id, user_message)
                print(f"Bot: {response[:100]}...")
                reply_message(reply_token, response)

    return "OK", 200


# =============================================================
# DASHBOARD (AI Office)
# =============================================================
# Map agent id -> ฟังก์ชันที่จะเรียก (รับ task เป็น arg แรก)
DASHBOARD_AGENTS = {
    "atlas":  run_manager,
    "pulse":  run_trainer_manager,
    "sage":   run_reporter,
    "guard":  run_reviewer,
    "coin":   run_financial_manager,
    "lex":    run_legal_manager,
    "people": run_hr_manager,
    "pixel":  run_web_admin,
    "sigma":  run_data_analyst,
    "lens":   run_creator,
}

DASHBOARD_USER_ID = "dashboard-console"  # user id แยกสำหรับสั่งงานผ่านเว็บ


def _check_dashboard_auth(req) -> bool:
    """เช็ค token. ถ้าไม่ตั้ง DASHBOARD_TOKEN = เปิด public (warn)."""
    if not DASHBOARD_TOKEN:
        return True
    token = (
        req.headers.get("X-Dashboard-Token", "")
        or req.args.get("key", "")
    )
    return hmac.compare_digest(token, DASHBOARD_TOKEN)


@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not _check_dashboard_auth(request):
        return Response("403 — ต้องใส่ ?key=YOUR_TOKEN ครับ", status=403)
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            html = f.read()
        # ฝัง token ลงในหน้าเว็บ เพื่อให้ JS เรียก API ต่อได้
        html = html.replace("__DASHBOARD_TOKEN__", DASHBOARD_TOKEN or "")
        return Response(html, mimetype="text/html")
    except FileNotFoundError:
        return Response("dashboard.html not found", status=404)


@app.route("/api/ping", methods=["GET"])
def api_ping():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"status": "ok", "agents": 11})


@app.route("/api/agent", methods=["POST"])
def api_agent():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    agent = (data.get("agent") or "rocket").lower()
    task = (data.get("task") or "").strip()
    if not task:
        return jsonify({"error": "ไม่มีคำสั่ง"}), 400

    try:
        if agent == "rocket":
            # Rocket = เลขาหลัก ใช้ flow เต็ม (memory + tools)
            result = get_claude_response(DASHBOARD_USER_ID, task)
        elif agent in DASHBOARD_AGENTS:
            result = DASHBOARD_AGENTS[agent](task)
        else:
            return jsonify({"error": f"ไม่รู้จัก agent: {agent}"}), 400
        return jsonify({"result": result})
    except Exception as e:
        print(f"api_agent error ({agent}): {e}")
        return jsonify({"error": f"ระบบขัดข้อง: {e}"}), 500


# Start scheduler
start_scheduler()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Rocket starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)


# =============================================================
# MANAGER AI INTEGRATION
# เพิ่ม tools ให้ Rocket สั่งงาน Manager ได้
# =============================================================
