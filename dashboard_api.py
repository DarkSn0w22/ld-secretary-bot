"""
Dashboard API Skill — shared utility
ดึงข้อมูลจาก L&D Dashboard GAS API โดยตรง
เร็วกว่าอ่าน Google Sheets เพราะสรุปข้อมูลมาให้แล้ว
"""

import os
import json
import requests

DASHBOARD_API = "https://script.google.com/macros/s/AKfycbxAh8klUHUPQR7FP6DGLyaqCi4g4SeUY0WxAn38Iou9ezn2QkBBLfF7YW27KFHvhVv5/exec"


def fetch_dashboard(action: str, year: str = None) -> dict:
    """ดึงข้อมูลจาก Dashboard API"""
    try:
        params = {"action": action}
        if year:
            params["year"] = year

        response = requests.get(DASHBOARD_API, params=params, timeout=20)
        return response.json()

    except Exception as e:
        print(f"Dashboard API error ({action}): {e}")
        return {"status": "error", "message": str(e)}


def get_survey_dashboard(year: str = None) -> str:
    """ดึง Survey data สรุปจาก Dashboard"""
    data = fetch_dashboard("survey", year)
    if data.get("status") == "error":
        return f"ไม่สามารถดึงข้อมูล Survey: {data.get('message', 'unknown error')}"

    result = "=== Survey Dashboard ===\n"

    # Overall
    result += f"Total responses: {data.get('total_responses', 0)}\n"
    result += f"Overall avg: {data.get('overall_avg', 0)}\n\n"

    # Courses
    courses = data.get("courses", {})
    if courses:
        result += "Courses:\n"
        for code, info in courses.items():
            if isinstance(info, dict):
                result += f"  {code}: avg={info.get('avg', 0)}, responses={info.get('responses', 0)}\n"

    # Trainers
    trainers = data.get("trainers", [])
    if trainers:
        result += f"\nTrainers ({len(trainers)} คน):\n"
        for t in trainers[:18]:
            if isinstance(t, dict):
                result += f"  {t.get('name', '?')}: avg={t.get('avg', 0)}, count={t.get('count', 0)}\n"

    return result


def get_oar_dashboard(year: str = None) -> str:
    """ดึง OAR Registration data"""
    data = fetch_dashboard("oar", year)
    if data.get("status") == "error":
        return f"ไม่สามารถดึงข้อมูล OAR: {data.get('message', 'unknown error')}"

    result = "=== OAR Registration ===\n"
    result += f"Total registrations: {data.get('total', 0)}\n\n"

    courses = data.get("courses", {})
    if courses:
        result += "Courses:\n"
        for code, count in sorted(courses.items(), key=lambda x: x[1], reverse=True):
            result += f"  {code}: {count}\n"

    branches = data.get("branches", {})
    if branches:
        top_branches = sorted(branches.items(), key=lambda x: x[1], reverse=True)[:15]
        result += f"\nTop 15 Branches:\n"
        for name, count in top_branches:
            result += f"  {name}: {count}\n"

    return result


def get_cost_dashboard(year: str = None) -> str:
    """ดึง Cost data"""
    data = fetch_dashboard("cost", year)
    if data.get("status") == "error":
        return f"ไม่สามารถดึงข้อมูล Cost: {data.get('message', 'unknown error')}"

    result = "=== L&D Cost ===\n"
    result += f"Budget: {data.get('budget', 0):,.0f}\n"
    result += f"Actual: {data.get('actual', 0):,.0f}\n"
    result += f"Balance: {data.get('balance', 0):,.0f}\n"
    result += f"Avg per employee: {data.get('avg_per_employee', 0):,.0f}\n\n"

    categories = data.get("categories", [])
    if categories:
        result += "Categories:\n"
        for cat in categories:
            if isinstance(cat, dict):
                result += f"  {cat.get('name', '?')}: actual={cat.get('actual', 0):,.0f}, budget={cat.get('budget', 0):,.0f}\n"

    return result


def get_area_dashboard() -> str:
    """ดึง Area Performance data"""
    data = fetch_dashboard("area")
    if data.get("status") == "error":
        return f"ไม่สามารถดึงข้อมูล Area: {data.get('message', 'unknown error')}"

    result = "=== Area Performance ===\n"
    areas = data.get("areas", {})
    for area_code, area_data in areas.items():
        result += f"\n{area_code}:\n"
        emp = area_data.get("employee_summary", {})
        if emp:
            result += f"  Staff: total={emp.get('total', 0)}, probation={emp.get('probation', 0)}, confirmed={emp.get('confirmed', 0)}\n"
            result += f"  OBT: pass={emp.get('obt_pass', 0)}, in_progress={emp.get('obt_in_progress', 0)}, not_started={emp.get('obt_not_started', 0)}\n"
        store = area_data.get("store_summary", {})
        if store:
            result += f"  Store: complaints={store.get('total_complaints', 0)}, nps={store.get('avg_nps', 0)}\n"

    return result


def get_assessment_dashboard() -> str:
    """ดึง Assessment/Grading data"""
    data = fetch_dashboard("assessment")
    if data.get("status") == "error":
        return f"ไม่สามารถดึงข้อมูล Assessment: {data.get('message', 'unknown error')}"

    result = "=== Assessment ===\n"
    emps = data.get("employees", [])
    active = [e for e in emps if isinstance(e, dict) and e.get("status") == "Pass"]
    total = len(active)
    g1 = len([e for e in active if e.get("grade") == "1st"])
    g2 = len([e for e in active if e.get("grade") == "2nd"])
    g3 = len([e for e in active if e.get("grade") == "3rd"])

    result += f"Active staff: {total}\n"
    result += f"1st Grade: {g1} ({(g1/total*100):.1f}%)\n" if total else ""
    result += f"2nd Grade: {g2} ({(g2/total*100):.1f}%)\n" if total else ""
    result += f"3rd Grade: {g3} ({(g3/total*100):.1f}%)\n" if total else ""
    result += f"No Grade: {total-g1-g2-g3}\n" if total else ""

    return result


def get_all_dashboard(year: str = None) -> str:
    """ดึงทุกข้อมูลจาก Dashboard ในครั้งเดียว"""
    parts = []
    parts.append(get_survey_dashboard(year))
    parts.append(get_oar_dashboard(year))
    parts.append(get_cost_dashboard(year))
    parts.append(get_area_dashboard())
    parts.append(get_assessment_dashboard())
    return "\n\n".join(parts)
