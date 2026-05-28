"""
Memory Module — PostgreSQL
เก็บ conversation history ข้ามวัน
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_user_id ON conversations(user_id);
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("DB initialized")
    except Exception as e:
        print(f"DB init error: {e}")


def _sanitize_history(history: list) -> list:
    """
    ทำความสะอาด history ก่อนส่งให้ Claude
    - กรอง tool_result ที่ไม่มี tool_use คู่กันออก
    - กรอง assistant message ที่มีแค่ tool_use block (ไม่มี text) ออก
    """
    clean = []
    i = 0
    while i < len(history):
        msg = history[i]

        if msg["role"] == "assistant":
            content = msg["content"]
            # ถ้า content เป็น list ให้เช็คว่ามี text block ไหม
            if isinstance(content, list):
                has_text = any(
                    (isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip())
                    for b in content
                )
                has_tool_use = any(
                    (isinstance(b, dict) and b.get("type") == "tool_use")
                    for b in content
                )
                if has_tool_use and not has_text:
                    # assistant message ที่มีแค่ tool_use — ข้ามทั้ง assistant + user(tool_result) ถัดไป
                    i += 1
                    if i < len(history) and history[i]["role"] == "user":
                        user_content = history[i]["content"]
                        if isinstance(user_content, list) and any(
                            isinstance(b, dict) and b.get("type") == "tool_result"
                            for b in user_content
                        ):
                            i += 1  # ข้าม tool_result ด้วย
                    continue
            clean.append(msg)

        elif msg["role"] == "user":
            content = msg["content"]
            # ถ้าเป็น tool_result แต่ไม่มี assistant tool_use ก่อนหน้า — ข้าม
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            ):
                # เช็ค message ก่อนหน้าว่ามี tool_use ไหม
                if clean and clean[-1]["role"] == "assistant":
                    prev = clean[-1]["content"]
                    if isinstance(prev, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_use"
                        for b in prev
                    ):
                        clean.append(msg)
                        i += 1
                        continue
                # ไม่มี tool_use คู่ — ข้าม
                i += 1
                continue
            clean.append(msg)

        i += 1

    return clean


def load_history(user_id: str, limit: int = 20) -> list:
    """โหลด conversation history ของ user (เฉพาะ text messages)"""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # โหลดเฉพาะ text messages ธรรมดา ไม่เอา tool_use/tool_result
        cur.execute("""
            SELECT role, content FROM conversations
            WHERE user_id = %s
            AND content NOT LIKE '%tool_use%'
            AND content NOT LIKE '%tool_result%'
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        history = []
        for row in reversed(rows):
            content = row["content"]
            try:
                parsed = json.loads(content)
                # ถ้า parse แล้วได้ list ที่มี tool block — ข้าม
                if isinstance(parsed, list):
                    continue
                content = parsed
            except Exception:
                pass
            history.append({"role": row["role"], "content": content})

        return history

    except Exception as e:
        print(f"Load history error: {e}")
        return []


def save_message(user_id: str, role: str, content):
    """บันทึกเฉพาะ text message ธรรมดาลง database"""
    try:
        # บันทึกแค่ string content (ไม่บันทึก tool use/result)
        if not isinstance(content, str):
            return  # ข้าม tool blocks ทั้งหมด

        if not content.strip():
            return  # ข้าม empty string

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO conversations (user_id, role, content)
            VALUES (%s, %s, %s)
        """, (user_id, role, content))
        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Save message error: {e}")


def clear_history(user_id: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Clear history error: {e}")
        return False


def get_message_count(user_id: str) -> int:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM conversations WHERE user_id = %s", (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception:
        return 0
