"""
Multi-Agent Message Bus — OWNDAYS AI Office
แต่ละ agent มี queue + worker thread ของตัวเอง
ทำงานได้ตลอดเวลา รับ-ส่งงานระหว่างกันได้โดยตรง
"""

import queue
import threading
import time
from datetime import datetime
import pytz
from agent_log import log_agent

BANGKOK_TZ = pytz.timezone("Asia/Bangkok")


class AgentTask:
    def __init__(self, from_agent: str, task: str, callback=None):
        self.from_agent = from_agent
        self.task       = task
        self.callback   = callback  # fn(agent_id, result, error)
        self.created_at = datetime.now(BANGKOK_TZ)


class AgentWorker:
    """1 worker = 1 agent — มี thread ทำงานตลอดเวลา"""

    def __init__(self, agent_id: str, handler):
        self.agent_id     = agent_id
        self.handler      = handler
        self._queue       = queue.Queue()
        self.status       = "idle"   # idle | busy | error
        self.current_task = None
        self.tasks_done   = 0
        self.last_active  = None
        self._thread      = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def enqueue(self, task: AgentTask):
        self._queue.put(task)

    @property
    def queue_size(self):
        return self._queue.qsize()

    def _loop(self):
        while True:
            task = self._queue.get()
            self.status       = "busy"
            self.current_task = task.task[:80]
            self.last_active  = datetime.now(BANGKOK_TZ).strftime("%H:%M:%S")

            log_agent(task.from_agent, self.agent_id, task.task[:200])
            try:
                result = self.handler(task.task)
                self.tasks_done += 1
                log_agent(self.agent_id, task.from_agent, "", result[:300])
                if task.callback:
                    task.callback(self.agent_id, result, None)
            except Exception as e:
                errmsg = f"ERROR: {e}"
                log_agent(self.agent_id, task.from_agent, "", errmsg, status="error")
                if task.callback:
                    task.callback(self.agent_id, None, str(e))
            finally:
                self.status       = "idle"
                self.current_task = None
                self._queue.task_done()


class AgentBus:
    """Central message bus — จัดการทุก agent"""

    def __init__(self):
        self._workers: dict[str, AgentWorker] = {}
        self._lock = threading.Lock()

    # ─── Registration ────────────────────────────────────────────
    def register(self, agent_id: str, handler):
        with self._lock:
            self._workers[agent_id] = AgentWorker(agent_id, handler)
        print(f"[Bus] ✓ {agent_id} online")

    # ─── Send to one agent (async) ───────────────────────────────
    def send(self, from_agent: str, to_agent: str, task: str,
             callback=None) -> bool:
        worker = self._workers.get(to_agent)
        if not worker:
            if callback:
                callback(to_agent, None, f"Agent '{to_agent}' ไม่พบ")
            return False
        worker.enqueue(AgentTask(from_agent, task, callback))
        return True

    # ─── Broadcast to multiple agents (parallel, wait for all) ──
    def broadcast(self, from_agent: str, agents: list,
                  task: str, timeout: float = 120.0) -> dict:
        """
        ส่ง task ไปหลาย agent พร้อมกัน แล้วรอผลทุกตัว
        คืน dict: {agent_id: result_or_error}
        """
        results: dict = {}
        remaining = [0]
        lock  = threading.Lock()
        done  = threading.Event()

        def _cb(agent_id, result, error):
            with lock:
                results[agent_id] = result if result else f"⚠️ {error}"
                remaining[0] -= 1
                if remaining[0] <= 0:
                    done.set()

        valid_agents = [a for a in agents if a in self._workers]
        if not valid_agents:
            return {a: "ไม่พบ agent" for a in agents}

        with lock:
            remaining[0] = len(valid_agents)

        for agent_id in valid_agents:
            self.send(from_agent, agent_id, task, _cb)

        # Fill missing (not registered)
        for a in agents:
            if a not in valid_agents:
                results[a] = "ไม่พบ agent"

        done.wait(timeout=timeout)
        return results

    # ─── Status ─────────────────────────────────────────────────
    def get_status(self) -> dict:
        """คืน status ของทุก agent สำหรับ dashboard"""
        return {
            aid: {
                "status":       w.status,
                "current_task": w.current_task,
                "tasks_done":   w.tasks_done,
                "last_active":  w.last_active,
                "queue_size":   w.queue_size,
            }
            for aid, w in self._workers.items()
        }

    def online_count(self) -> int:
        return len(self._workers)

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._workers


# ─── Global singleton ────────────────────────────────────────────
bus = AgentBus()
