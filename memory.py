"""
Memory Module — PostgreSQL
เก็บ conversation history ข้ามวัน (text only)
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


def load_history(user_id: str, limit: int = 20) -> list:
    """โหลดเฉพาะ text message ธรรมดา ไม่เอา tool blocks"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT role, content FROM conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        history = []
        for row in reversed(rows):
            role = row[0]
            content = row[1]

            # ข้าม tool-related content
            if "tool_use" in content or "tool_result" in content:
                continue

            # ข้าม JSON arrays
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    continue
                content = parsed
            except Exception:
                pass

            if content and str(content).strip():
                history.append({"role": role, "content": str(content)})

        return history

    except Exception as e:
        print(f"Load history error: {e}")
        return []


def save_message(user_id: str, role: str, content):
    """บันทึกเฉพาะ plain text เท่านั้น"""
    try:
        if not isinstance(content, str):
            return
        if not content.strip():
            return
        if "tool_use" in content or "tool_result" in content:
            return

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, content)
        )
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
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0
