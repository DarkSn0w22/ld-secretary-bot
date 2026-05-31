"""
OWNDAYS L&D Secretary Bot v30
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
from retail_md_agent import run_retail_md, download_line_file, parse_excel_to_text, parse_pdf_sales_report
from models_config import print_model_summary
from agent_log import log_agent, get_logs, clear_logs
from agent_bus import bus
from autonomous_agents import start_autonomous_watchers

app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.after_request
def add_cors_for_static(response):
    """เพิ่ม CORS header สำหรับ static files (ให้ canvas getImageData ทำงานได้)"""
    if '/static/' in request.path:
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

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
    """Route tool call → agent bus (หรือ direct call สำหรับ data tools)"""
    # ── Data tools: เรียกตรงเพราะไม่ใช่ AI agent ──
    if tool_name == "get_survey_data":
        return get_survey_summary()
    elif tool_name == "get_oar_data":
        return get_oar_summary()
    elif tool_name == "get_sheet_list":
        sheet_key = tool_input.get("sheet_key", "survey")
        names = get_sheet_names(SHEET_IDS.get(sheet_key, SHEET_IDS["survey"]))
        return f"Sheets ใน {sheet_key}: {', '.join(names)}" if names else "ไม่พบข้อมูล"
    elif tool_name == "web_search":
        return google_search(tool_input.get("query", ""))

    # ── AI Agent tools: ส่งผ่าน bus (มี queue + worker thread) ──
    AGENT_TOOL_MAP = {
        "ask_manager":       ("atlas",  lambda i: i.get("task", "")),
        "ask_trainer_manager": ("pulse", lambda i: i.get("task", "")),
        "ask_reporter":      ("sage",   lambda i: i.get("report_type", "weekly")),
        "ask_reviewer":      ("guard",  lambda i: i.get("content", "")),
        "ask_financial":     ("coin",   lambda i: i.get("task", "")),
        "ask_legal":         ("lex",    lambda i: i.get("task", "")),
        "ask_hr":            ("people", lambda i: i.get("task", "")),
        "ask_web_admin":     ("pixel",  lambda i: i.get("task", "")),
        "ask_data_analyst":  ("sigma",  lambda i: i.get("task", "")),
        "ask_creator":       ("lens",   lambda i: i.get("task", "")),
        "ask_retail_md":     ("rex",    lambda i: i.get("task", "")),
    }
    if tool_name in AGENT_TOOL_MAP:
        agent_id, get_task = AGENT_TOOL_MAP[tool_name]
        task = get_task(tool_input)
        if bus.is_registered(agent_id):
            # ส่งผ่าน bus แบบ sync-wait (Claude tool loop ต้องการผล)
            result_holder = [None]
            ev = __import__("threading").Event()
            def _cb(aid, result, error):
                result_holder[0] = result if result else f"⚠️ {error}"
                ev.set()
            bus.send("rocket", agent_id, task, _cb)
            ev.wait(timeout=90)
            return result_holder[0] or "ไม่ได้รับผลลัพธ์ภายใน 90 วินาที"
        # fallback ถ้า bus ยังไม่พร้อม
        direct = {
            "atlas": run_manager, "pulse": run_trainer_manager,
            "sage": run_reporter, "guard": run_reviewer,
            "coin": run_financial_manager, "lex": run_legal_manager,
            "people": run_hr_manager, "pixel": run_web_admin,
            "sigma": run_data_analyst, "lens": run_creator,
            "rex": run_retail_md,
        }
        return direct[agent_id](task) if agent_id in direct else "Agent ไม่พร้อม"

    return "ไม่พบ tool นี้"


def execute_tools_parallel(tool_blocks: list) -> list:
    """Execute หลาย tool call พร้อมกัน (parallel) แล้วคืน results ตามลำดับ"""
    import threading
    results = [None] * len(tool_blocks)

    def _run(idx, block):
        results[idx] = execute_tool(block.name, block.input)

    threads = []
    for i, block in enumerate(tool_blocks):
        if block.type == "tool_use":
            t = threading.Thread(target=_run, args=(i, block), daemon=True)
            threads.append((i, t))
            t.start()

    for _, t in threads:
        t.join(timeout=120)

    return results


# =============================================================
# SYSTEM PROMPT
# =============================================================
SECRETARY_PROMPT = """คุณคือ "Rocket" — AI เลขาส่วนตัวของ Peanut ผู้ชาย ทำงานให้ตลอด 24 ชั่วโมง

⚠️ กฎเหล็กที่ต้องทำตามเสมอ:
1. ห้ามใช้ Markdown เด็ดขาด — ห้ามใช้ ** ## __ ``` > - (bullet) เด็ดขาด ใช้ plain text + emoji เท่านั้น
2. ใช้คำลงท้าย "ครับ" เสมอ ห้ามใช้ "ค่ะ" หรือ "นะคะ" เด็ดขาด
3. คุณมี tools เรียก agent ได้จริง — ถ้า Peanut สั่งงานใด ให้เรียก tool ทันที อย่าบอกว่า "ทำไม่ได้"

== การกระจายงานและประสานงาน Agent ==
คุณเป็น Orchestrator — คุณสามารถเรียก Agent อื่นๆ ผ่าน tools ได้เลยทันที:

ask_manager → Atlas (วิเคราะห์เชิงลึก วางแผนกลยุทธ์ ประสานงาน)
ask_trainer_manager → Pulse (ติดตาม trainer KPI วิเคราะห์หลักสูตร)
ask_reporter → Sage (จัดทำรายงาน สรุปภาพรวม)
ask_reviewer → Guard (ตรวจสอบคุณภาพงาน QA)
ask_financial → Coin (วิเคราะห์งบประมาณ ค่าใช้จ่าย)
ask_legal → Lex (กฎหมายแรงงาน PDPA สัญญา)
ask_hr → People (ข้อมูลพนักงาน probation HR)
ask_web_admin → Pixel (เว็บไซต์ od-connect.com)
ask_data_analyst → Sigma (วิเคราะห์ข้อมูล trends KPI)
ask_creator → Lens (สร้าง content quiz script)
ask_retail_md → Rex (sales สาขา branch performance)

เมื่อ Peanut บอก "ให้ [agent] ทำ..." หรือ "กระจายงาน" หรือ "ให้แต่ละแผนก..." ให้:
- เรียก tool ที่เกี่ยวข้องทันที (เรียกหลาย tool ต่อเนื่องได้)
- รวบรวมผลจากทุก agent แล้วสรุปให้ Peanut เป็น plain text ที่กระชับ
- ห้ามบอกว่า "ผมทำไม่ได้" หรือ "ไม่มีระบบ broadcast" เด็ดขาด

== บุคลิกและการสื่อสาร ==
- ตอบภาษาไทยเป็นหลัก กระชับ ตรงประเด็น เหมาะกับอ่านบน LINE
- เรียงข้อมูลจากใหม่ไปเก่าเสมอ
- ทำหน้าที่รวบรวมงานจากแต่ละแผนกในแต่ละวัน นำเสนองานหรือโปรเจค ไอเดีย ของแต่ละแผนกให้ Peanut กดอนุมัติ
- เมื่อถูกถามข้อมูล Survey, Training, OAR ให้ดึงจาก Google Sheets ทุกครั้ง
- ถ้าข้อมูลไม่เพียงพอ ให้บอกว่าขอข้อมูลเพิ่มเติมแทน อย่าเดาหรือสร้างข้อมูลเองเด็ดขาด
- ถ้าถามนอกขอบเขต ให้ตอบว่า "ขอโทษครับ เรื่องนี้ผมไม่แน่ใจครับ"
- ถ้าถามเรื่องกฎหมาย → เรียก Lex ทันที
- ถ้าถามเรื่องการเงิน → เรียก Coin ทันที
- ถ้าถามเรื่องวิเคราะห์ข้อมูลเชิงลึก/กลยุทธ์ → เรียก Atlas ทันที
- ถ้าถามเรื่อง trainer performance/หลักสูตร → เรียก Pulse ทันที
- ถ้าถามเรื่องรายงานภาพรวม → เรียก Sage ทันที
- ถ้าถามเรื่อง sales/สาขา/branch → เรียก Rex ทันที
- มีไอเดียใหม่ๆมานำเสนอเสมอ เช่น การใช้เครื่องมือใหม่ๆ การปรับปรุงการทำงาน
- ถ้าถูกถามคำถามที่เกี่ยวกับการตรวจสอบคุณภาพงาน เช่น รายงาน, email, เนื้อหาการฝึกอบรม ให้ใช้ Reviewer/QA AI (Guard) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
- ถ้าถูกถามเรื่อง sales, ยอดขาย, ผลประกอบการสาขา, branch performance, ไฟล์ sales รายสัปดาห์ หรือการวิเคราะห์สาขา ให้ใช้ Retail MD AI (Rex) ในการตอบเสมอ อย่าพยายามตอบเองเด็ดขาด
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

== Trainer-Division Mapping (สำหรับ Dashboard Analytics) ==
Sales: Judy, Pui, Jets, Trin, Nueng, Tonpalm
Optical: Jib, Jajah, Kio, Toy, Kwang, Mark
Optometry: Dr.Fair, Dr.Benz, Dr.Milk, Dr.Lookaew
Regional/Other: Peanut, Jame

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
- Dashboard: HTML + Chart.js v4.4.1 + Google Apps Script API v6
- ข้อมูลเก็บใน Google Drive และ Google Sheets
- New Raw Data Folder: https://drive.google.com/drive/folders/1M_omBsJNJb-kJKp1nRAo88TD6fYCeTnL

== L&D Dashboard (GAS API v6) ==
Dashboard Tabs ทั้งหมด 11 tabs:
Active (4): Trainers (Trainer KPI/ranking), Training (Survey+OAR), L&D Cost (Budget vs Actual), L&D Asset (Laptop/iPad)
Placeholder รอพัฒนา (7): Academy, Assessment, Content Management, Employee Management, Store Service Performance, Lens Management, Contact Lens Management
API Actions: action=survey, cost, asset, oar, ping, all (ใส่ year filter ได้)

== เอกสารอ้างอิง ==
- LD_Manual_Ver_24.pdf — คู่มือ L&D ฉบับเต็ม
- Official_LD_LMS_by_Academy.pdf — LMS Academy Framework ทุกหลักสูตร
- Official_LD_Organization_Chart.pdf — Org Chart แผนก L&D
- OWNDAYS Employee Framework — เส้นทางการเรียนรู้ Basic → Moderate → Mastery

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
    # Log incoming message
    log_agent("user", "rocket", message[:200])

    # โหลด history จาก DB
    history = load_history(user_id, limit=20)

    # เพิ่มข้อความใหม่
    history.append({"role": "user", "content": message})
    save_message(user_id, "user", message)

    try:
        while True:
            response = claude.messages.create(
                model=get_model("rocket"),
                max_tokens=2048,   # เพิ่มจาก 1024 — รองรับกรณี Rocket เรียกหลาย agent แล้วสรุป
                system=SECRETARY_PROMPT,
                tools=TOOLS,
                messages=history
            )

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})
                save_message(user_id, "assistant", response.content)

                # ── Parallel execution: รัน tool calls พร้อมกันทั้งหมด ──
                use_blocks = [b for b in response.content if b.type == "tool_use"]
                parallel_results = execute_tools_parallel(use_blocks)

                tool_results = []
                for i, block in enumerate(use_blocks):
                    print(f"Tool: {block.name}")
                    result = parallel_results[i] or "ไม่ได้รับผลลัพธ์"
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
            log_agent("rocket", "user", "", final_text[:200])
            return final_text

    except Exception as e:
        print(f"Claude Error: {e}")
        log_agent("rocket", "user", "", f"ERROR: {e}", status="error")
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
    remaining = text
    while remaining:
        messages.append({"type": "text", "text": remaining[:5000]})
        remaining = remaining[5000:]
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": messages[:5]}
    requests.post(url, headers=headers, json=payload, timeout=10)


def push_to_user(user_id: str, text: str):
    """Push message ถึง user โดยตรง (ไม่ต้องใช้ reply token)"""
    messages = []
    remaining = text
    while remaining:
        messages.append({"type": "text", "text": remaining[:5000]})
        remaining = remaining[5000:]
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": user_id, "messages": messages[:5]}
    try:
        requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        print(f"push_to_user error: {e}")


def estimate_ack(message: str) -> str:
    """ตอบรับทันที พร้อมประมาณเวลา ตามความซับซ้อนของ task"""
    msg = message.lower()

    # Multi-agent / heavy tasks
    heavy = ["กระจาย", "ทุก agent", "ทุกแผนก", "ทุกตัว", "ภาพรวม",
             "รายงาน", "สรุปทั้งหมด", "วิเคราะห์ทั้ง", "ช่วยกัน"]
    # Single agent calls
    medium = ["atlas", "pulse", "sage", "guard", "coin", "lex",
              "people", "pixel", "sigma", "lens", "rex",
              "วิเคราะห์", "ตรวจสอบ", "เช็ค", "หา", "ค้นหา",
              "survey", "oar", "budget", "sales", "trainer"]

    if any(k in msg for k in heavy):
        eta = "ประมาณ 1-2 นาที"
        note = "กำลังประสานงานกับหลาย agent"
    elif any(k in msg for k in medium):
        eta = "ประมาณ 30-60 วินาที"
        note = "กำลังส่งงานไปยัง agent ที่รับผิดชอบ"
    else:
        eta = "ประมาณ 10-20 วินาที"
        note = "กำลังดำเนินการ"

    return f"⚙️ รับทราบครับ {note} คาดว่าได้คำตอบภายใน {eta} ครับ"


# =============================================================
# ROUTES
# =============================================================
@app.route("/", methods=["GET"])
def health_check():
    return "LD Secretary Bot v30 - Rocket is running!", 200


def _process_text_async(user_id: str, user_message: str):
    """รันใน background thread — ประมวลผลแล้ว push ผลกลับ"""
    try:
        result = get_claude_response(user_id, user_message)
        print(f"Bot: {result[:100]}...")
        push_to_user(user_id, result)
    except Exception as e:
        print(f"Async processing error: {e}")
        push_to_user(user_id, f"ขอโทษครับ เกิดข้อผิดพลาด: {e}")


def _process_file_async(user_id: str, msg_id: str, file_name: str):
    """รันใน background thread — parse ไฟล์แล้ว push ผลให้ Rex"""
    try:
        file_bytes = download_line_file(msg_id)
        fn_lower = file_name.lower()
        if fn_lower.endswith((".xlsx", ".xls")):
            sales_text = parse_excel_to_text(file_bytes)
        elif fn_lower.endswith(".pdf"):
            sales_text = parse_pdf_sales_report(file_bytes)
        else:
            sales_text = file_bytes.decode("utf-8", errors="replace")

        task = f"วิเคราะห์ไฟล์ Sales รายสัปดาห์ที่ส่งมา ชื่อไฟล์: {file_name}"
        result = run_retail_md(task, sales_file_content=sales_text)
        push_to_user(user_id, result)
    except Exception as e:
        push_to_user(user_id, f"ขอโทษครับ วิเคราะห์ไฟล์ไม่ได้: {e}")


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        abort(400)

    events = json.loads(body).get("events", [])

    for event in events:

        # ── ข้อความ text ──
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_id     = event["source"]["userId"]
            user_message = event["message"]["text"]
            reply_token  = event["replyToken"]
            cmd          = user_message.strip()

            print(f"User {user_id[:8]}...: {user_message[:60]}")

            # Special commands — reply ทันที ไม่ต้อง async
            if cmd == "/myid":
                reply_message(reply_token, f"Your LINE User ID:\n{user_id}")
            elif cmd == "/clearmemory":
                success = clear_history(user_id)
                reply_message(reply_token, "ลบความจำทั้งหมดแล้วครับ 🗑️" if success else "เกิดข้อผิดพลาดครับ")
            elif cmd == "/memstats":
                count = get_message_count(user_id)
                reply_message(reply_token, f"มีข้อความในความจำทั้งหมด {count} ข้อความครับ 🧠")
            else:
                # 1️⃣ ตอบรับทันที + บอก ETA
                reply_message(reply_token, estimate_ack(user_message))
                # 2️⃣ ประมวลผลใน background → push ผลเมื่อเสร็จ
                import threading
                threading.Thread(
                    target=_process_text_async,
                    args=(user_id, user_message),
                    daemon=True
                ).start()

        # ── ไฟล์ (Excel/PDF) → Rex ──
        elif event["type"] == "message" and event["message"]["type"] == "file":
            user_id     = event["source"]["userId"]
            reply_token  = event["replyToken"]
            msg          = event["message"]
            file_name    = msg.get("fileName", "sales_file")
            msg_id       = msg["id"]

            # 1️⃣ ตอบรับทันที
            reply_message(reply_token,
                f"📂 ได้รับไฟล์ '{file_name}' แล้วครับ\n"
                f"⚙️ กำลังให้ Rex วิเคราะห์ คาดว่าได้ผลภายใน 1-2 นาที ครับ")
            # 2️⃣ parse + วิเคราะห์ใน background → push ผล
            import threading
            threading.Thread(
                target=_process_file_async,
                args=(user_id, msg_id, file_name),
                daemon=True
            ).start()

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
    "rex":    run_retail_md,
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
        log_agent("dashboard", agent, task)
        if agent == "rocket":
            result = get_claude_response(DASHBOARD_USER_ID, task)
        elif agent in DASHBOARD_AGENTS:
            result = DASHBOARD_AGENTS[agent](task)
        else:
            return jsonify({"error": f"ไม่รู้จัก agent: {agent}"}), 400
        log_agent(agent, "dashboard", "", result[:300])
        return jsonify({"result": result})
    except Exception as e:
        print(f"api_agent error ({agent}): {e}")
        log_agent(agent, "dashboard", "", f"ERROR: {e}", status="error")
        return jsonify({"error": f"ระบบขัดข้อง: {e}"}), 500


@app.route("/api/agent-log", methods=["GET"])
def api_agent_log():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    since = request.args.get("since", 0, type=float)
    logs = get_logs(n=100, since_epoch=since)
    return jsonify({"logs": logs})


@app.route("/api/agent-log/clear", methods=["POST"])
def api_agent_log_clear():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    clear_logs()
    return jsonify({"ok": True})


SCHEDULE_CONFIG_FILE = "schedule_config.json"
DEFAULT_SCHEDULE = {
    "jobs": [
        {
            "time": "09:00",
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "agent": "Rocket",
            "task": "Consolidated Morning Report (Coin + People + Sage)",
            "enabled": True
        }
    ]
}


@app.route("/api/schedule-config", methods=["GET"])
def api_schedule_config_get():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    try:
        import json as _json
        with open(SCHEDULE_CONFIG_FILE, "r") as f:
            cfg = _json.load(f)
    except Exception:
        cfg = DEFAULT_SCHEDULE
    # Inject actual running time from scheduler
    try:
        from scheduler import get_morning_hour_minute, get_morning_days
        mh, mm = get_morning_hour_minute()
        mdays = get_morning_days()
        day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        cfg["_running"] = {
            "time": f"{mh:02d}:{mm:02d}",
            "days": [day_names[d] for d in mdays if d < 7],
        }
    except Exception:
        pass
    return jsonify(cfg)


@app.route("/api/schedule-config", methods=["POST"])
def api_schedule_config_post():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        import json as _json
        with open(SCHEDULE_CONFIG_FILE, "w") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        log_agent("dashboard", "scheduler", "อัพเดต schedule config", str(data)[:200])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agent-status", methods=["GET"])
def api_agent_status():
    if not _check_dashboard_auth(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"agents": bus.get_status(), "online": bus.online_count()})


# ─── Start background services ────────────────────────────────────────────────
def _start_agent_bus():
    """Register agents into bus — แต่ละตัวมี worker thread ของตัวเอง"""
    bus.register("atlas",  run_manager)
    bus.register("pulse",  run_trainer_manager)
    bus.register("sage",   run_reporter)
    bus.register("guard",  run_reviewer)
    bus.register("coin",   run_financial_manager)
    bus.register("lex",    run_legal_manager)
    bus.register("people", run_hr_manager)
    bus.register("pixel",  run_web_admin)
    bus.register("sigma",  run_data_analyst)
    bus.register("lens",   run_creator)
    bus.register("rex",    run_retail_md)
    print(f"[Bus] {bus.online_count()} agents online ✓")

_start_agent_bus()
start_scheduler()
start_autonomous_watchers()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Rocket starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)


# =============================================================
# MANAGER AI INTEGRATION
# เพิ่ม tools ให้ Rocket สั่งงาน Manager ได้
# =============================================================
