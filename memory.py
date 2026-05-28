"""
Memory Module — PostgreSQL
เก็บ conversation history ข้ามวัน
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """สร้าง table ถ้ายังไม่มี"""
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
    """โหลด conversation history ของ user"""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT role, content FROM conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        # reverse ให้เรียงจากเก่าไปใหม่
        history = []
        for row in reversed(rows):
            content = row["content"]
            # content อาจเป็น JSON (tool use) หรือ plain text
            try:
                content = json.loads(content)
            except Exception:
                pass
            history.append({"role": row["role"], "content": content})

        return history

    except Exception as e:
        print(f"Load history error: {e}")
        return []


def save_message(user_id: str, role: str, content):
    """บันทึกข้อความลง database"""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # ถ้า content ไม่ใช่ string ให้แปลงเป็น JSON
        if not isinstance(content, str):
            if isinstance(content, list):
                serializable = []
                for item in content:
                    if hasattr(item, 'model_dump'):
                        serializable.append(item.model_dump())
                    elif hasattr(item, '__dict__'):
                        serializable.append(item.__dict__)
                    else:
                        serializable.append(item)
                content = json.dumps(serializable, ensure_ascii=False)
            else:
                content = json.dumps(content, ensure_ascii=False)

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
    """ลบ history ของ user ทั้งหมด"""
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
    """นับจำนวนข้อความทั้งหมดของ user"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM conversations WHERE user_id = %s",
            (user_id,)
        )
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception:
        return 0
