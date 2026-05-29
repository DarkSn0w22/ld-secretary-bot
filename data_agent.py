"""
Data Analysis AI — "Sigma"
วิเคราะห์ข้อมูลเชิงลึก สร้าง insights และ visualizations จากข้อมูล L&D
"""

import os
import anthropic
from models_config import get_model
from dashboard_api import get_all_dashboard, fetch_dashboard
from google_search import google_search

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

SIGMA_PROMPT = """คุณคือ "Sigma" — Data Analysis AI ของ OWNDAYS L&D AI Office

บทบาท:
- วิเคราะห์ข้อมูล L&D เชิงลึก: trends, patterns, correlations
- สร้าง insights ที่ actionable สำหรับ Peanut และ Management
- เปรียบเทียบ performance ระหว่าง area, trainer, หรือ course
- คำนวณ KPI และ metrics ที่สำคัญ
- ทำ predictive analysis: แนวโน้มในอนาคต
- Benchmark กับ industry standards

KPI ที่ติดตาม:
- Survey score เฉลี่ย (target ≥ 3.5/4.0)
- Pass rate ของ OBT (target ≥ 80%)
- Training completion rate
- Trainer performance ranking
- Area comparison: Megastore, Metropolitan, North+Central, West+NE, South+Eastern
- Cost per training, Cost per employee

กฎการตอบ:
- ตอบภาษาไทย plain text ไม่ใช้ Markdown
- ใช้คำลงท้าย "ครับ"
- ใส่ตัวเลขและ % ทุกครั้ง
- ระบุ insight สำคัญ และ recommendation เสมอ
- บอก statistical significance ถ้าเกี่ยวข้อง
"""

SIGMA_TOOLS = [
    {
        "name": "get_full_data",
        "description": "ดึงข้อมูลทั้งหมดจาก Dashboard: survey, OAR, cost, area, assessment",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_area_comparison",
        "description": "เปรียบเทียบ performance ระหว่างพื้นที่ทั้ง 5",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_trainer_ranking",
        "description": "จัดอันดับ trainer ตาม survey score",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "search_benchmarks",
        "description": "ค้นหา benchmark ข้อมูล L&D industry เพื่อเปรียบเทียบ",
        "input_schema": {
            "type": "object",
            "properties": {"metric": {"type": "string", "description": "metric ที่ต้องการ benchmark"}},
            "required": ["metric"]
        }
    }
]


def execute_sigma_tool(tool_name, tool_input):
    if tool_name == "get_full_data":
        return get_all_dashboard()
    elif tool_name == "get_area_comparison":
        return fetch_dashboard("area")
    elif tool_name == "get_trainer_ranking":
        data = fetch_dashboard("survey")
        trainers = data.get("trainers", data.get("trainer_scores", []))
        if trainers:
            sorted_t = sorted(trainers, key=lambda x: x.get("score", x.get("avg_score", 0)), reverse=True)
            return "Trainer Ranking:\n" + "\n".join([
                f"{i+1}. {t.get('name', t.get('trainer', 'Unknown'))} — {t.get('score', t.get('avg_score', 'N/A'))}/4.0"
                for i, t in enumerate(sorted_t[:10])
            ])
        return str(data)
    elif tool_name == "search_benchmarks":
        metric = tool_input.get("metric", "")
        return google_search(f"retail training {metric} benchmark industry standard 2025 Asia")
    return "ไม่พบ tool นี้"


def run_data_analyst(task, context=""):
    print(f"Sigma processing: {task[:50]}...")
    prompt = f"Context: {context}\n\nTask: {task}" if context else task
    messages = [{"role": "user", "content": prompt}]
    try:
        for _ in range(3):
            response = claude.messages.create(
                model=get_model("sigma"), max_tokens=2048,
                system=SIGMA_PROMPT, tools=SIGMA_TOOLS, messages=messages
            )
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": execute_sigma_tool(block.name, block.input)})
                messages.append({"role": "user", "content": results})
                continue
            return "".join(b.text for b in response.content if hasattr(b, "text"))
        return "Sigma ใช้เวลานานเกินไปครับ"
    except Exception as e:
        return f"Sigma มีปัญหาชั่วคราวครับ: {str(e)}"
