"""SQLite storage engine for via54Medit telemetry."""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from .models import DownloadItem, HighlightItem, LLMTokenRecord, RetrievalItem, TaskRecord, TaskType


DEFAULT_DB_PATH = os.path.expanduser(r"~/.medit/telemetry.db")


class TelemetryDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 任务总表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                project_name TEXT DEFAULT '',
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                extra TEXT DEFAULT '{}'
            )
            """)

            # 2. 文献检索明细表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                paper_id TEXT NOT NULL,
                doi TEXT DEFAULT '',
                url TEXT DEFAULT '',
                citation_text TEXT DEFAULT '',
                duration_seconds REAL DEFAULT 0.0,
                source TEXT DEFAULT '',
                success INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """)

            # 3. 文献下载明细表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                paper_id TEXT NOT NULL,
                doi TEXT DEFAULT '',
                pdf_path TEXT DEFAULT '',
                file_size_bytes INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                error_msg TEXT DEFAULT '',
                source TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """)

            # 4. 文献 Highlight 与质检修正表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS highlight_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                paper_id TEXT NOT NULL,
                pdf_path TEXT DEFAULT '',
                page_count INTEGER DEFAULT 0,
                num_annots INTEGER DEFAULT 0,
                highlight_duration_seconds REAL DEFAULT 0.0,
                correction_duration_seconds REAL DEFAULT 0.0,
                status TEXT DEFAULT 'yellow_ok',
                created_at TEXT NOT NULL
            )
            """)

            # 5. 同步与推送日志表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,  -- 'feishu_card', 'feishu_sheet'
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT '',
                payload TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """)

            # 6. 真实大模型网关 Token 消耗明细表 (100% 对应服务商控制台账单)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_token_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT DEFAULT '',
                project_name TEXT DEFAULT '',
                provider TEXT NOT NULL,       -- 如 'deepseek', 'zhipu', 'openai', 'sensenova'
                model TEXT NOT NULL,          -- 如 'deepseek-chat', 'glm-4.6v-flash'
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                req_id TEXT DEFAULT '',       -- 服务商 request_id
                source TEXT DEFAULT '',       -- 调用源
                created_at TEXT NOT NULL
            )
            """)

            # 索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_created ON retrieval_items (created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_created ON download_items (created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_highlight_created ON highlight_items (created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks (start_time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_tokens_created ON llm_token_logs (created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_tokens_provider ON llm_token_logs (provider)")
            conn.commit()

    def record_task(self, task: TaskRecord):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (task_id, task_type, project_name, start_time, end_time, duration_seconds, 
                 prompt_tokens, completion_tokens, total_tokens, status, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
                    task.project_name,
                    task.start_time,
                    task.end_time,
                    task.duration_seconds,
                    task.prompt_tokens,
                    task.completion_tokens,
                    task.total_tokens,
                    task.status,
                    json.dumps(task.extra, ensure_ascii=False),
                ),
            )
            conn.commit()

    def record_retrieval_item(self, task_id: str, item: RetrievalItem):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO retrieval_items 
                (task_id, paper_id, doi, url, citation_text, duration_seconds, source, success, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item.paper_id,
                    item.doi,
                    item.url,
                    item.citation_text,
                    item.duration_seconds,
                    item.source,
                    1 if item.success else 0,
                    item.created_at,
                ),
            )
            conn.commit()

    def record_download_item(self, task_id: str, item: DownloadItem):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO download_items 
                (task_id, paper_id, doi, pdf_path, file_size_bytes, duration_seconds, success, error_msg, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item.paper_id,
                    item.doi,
                    item.pdf_path,
                    item.file_size_bytes,
                    item.duration_seconds,
                    1 if item.success else 0,
                    item.error_msg,
                    item.source,
                    item.created_at,
                ),
            )
            conn.commit()

    def record_highlight_item(self, task_id: str, item: HighlightItem):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO highlight_items 
                (task_id, paper_id, pdf_path, page_count, num_annots, highlight_duration_seconds, 
                 correction_duration_seconds, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item.paper_id,
                    item.pdf_path,
                    item.page_count,
                    item.num_annots,
                    item.highlight_duration_seconds,
                    item.correction_duration_seconds,
                    item.status,
                    item.created_at,
                ),
            )
            conn.commit()

    def has_highlight_item(self, pdf_path: str = "", paper_id: str = "") -> bool:
        with self.get_connection() as conn:
            if pdf_path:
                row = conn.execute("SELECT 1 FROM highlight_items WHERE pdf_path = ? LIMIT 1", (pdf_path,)).fetchone()
                if row:
                    return True
            if paper_id:
                row = conn.execute("SELECT 1 FROM highlight_items WHERE paper_id = ? LIMIT 1", (paper_id,)).fetchone()
                if row:
                    return True
            return False

    def update_highlight_page_count(self, pdf_path: str, page_count: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE highlight_items SET page_count = ? WHERE pdf_path = ?", (page_count, pdf_path))
            conn.commit()

    def has_download_item(self, pdf_path: str = "", paper_id: str = "") -> bool:
        with self.get_connection() as conn:
            if pdf_path:
                row = conn.execute("SELECT 1 FROM download_items WHERE pdf_path = ? LIMIT 1", (pdf_path,)).fetchone()
                if row:
                    return True
            if paper_id:
                row = conn.execute("SELECT 1 FROM download_items WHERE paper_id = ? LIMIT 1", (paper_id,)).fetchone()
                if row:
                    return True
            return False

    def has_retrieval_item(self, paper_id: str = "", doi: str = "", url: str = "") -> bool:
        with self.get_connection() as conn:
            if doi:
                row = conn.execute("SELECT 1 FROM retrieval_items WHERE doi = ? LIMIT 1", (doi,)).fetchone()
                if row:
                    return True
            if url:
                row = conn.execute("SELECT 1 FROM retrieval_items WHERE url = ? LIMIT 1", (url,)).fetchone()
                if row:
                    return True
            if paper_id:
                row = conn.execute("SELECT 1 FROM retrieval_items WHERE paper_id = ? LIMIT 1", (paper_id,)).fetchone()
                if row:
                    return True
            return False

    def deduplicate_database(self):
        """清理历史重复记录，保留最新的一条，清除冗余。"""
        with self.get_connection() as conn:
            # 1. highlight_items 去重
            conn.execute("""
            DELETE FROM highlight_items 
            WHERE id NOT IN (
                SELECT MAX(id) FROM highlight_items 
                GROUP BY CASE WHEN pdf_path != '' THEN pdf_path ELSE paper_id END
            )
            """)
            # 2. download_items 去重
            conn.execute("""
            DELETE FROM download_items 
            WHERE id NOT IN (
                SELECT MAX(id) FROM download_items 
                GROUP BY CASE WHEN pdf_path != '' THEN pdf_path ELSE paper_id END
            )
            """)
            # 3. retrieval_items 去重
            conn.execute("""
            DELETE FROM retrieval_items 
            WHERE id NOT IN (
                SELECT MAX(id) FROM retrieval_items 
                GROUP BY CASE WHEN doi != '' THEN doi WHEN url != '' THEN url ELSE paper_id END
            )
            """)
            # 4. tasks 扫描任务去重 (同项目仅保留单次有效登记)
            conn.execute("""
            DELETE FROM tasks 
            WHERE task_id LIKE 'scan_%' 
            AND task_id NOT IN (
                SELECT MAX(task_id) FROM tasks 
                WHERE task_id LIKE 'scan_%' 
                GROUP BY project_name
            )
            """)
            conn.commit()

    def record_sync_log(self, sync_type: str, target: str, status: str, message: str, payload: str = ""):
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sync_logs (sync_type, target, status, message, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sync_type, target, status, message, payload, datetime.now().isoformat()),
            )
            conn.commit()

    def query_retrievals(self, start_iso: Optional[str] = None, end_iso: Optional[str] = None) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            query = "SELECT * FROM retrieval_items WHERE 1=1"
            params = []
            if start_iso:
                query += " AND created_at >= ?"
                params.append(start_iso)
            if end_iso:
                query += " AND created_at <= ?"
                params.append(end_iso)
            query += " ORDER BY created_at ASC"
            return conn.execute(query, params).fetchall()

    def query_downloads(self, start_iso: Optional[str] = None, end_iso: Optional[str] = None) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            query = "SELECT * FROM download_items WHERE 1=1"
            params = []
            if start_iso:
                query += " AND created_at >= ?"
                params.append(start_iso)
            if end_iso:
                query += " AND created_at <= ?"
                params.append(end_iso)
            query += " ORDER BY created_at ASC"
            return conn.execute(query, params).fetchall()

    def query_highlights(self, start_iso: Optional[str] = None, end_iso: Optional[str] = None) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            query = "SELECT * FROM highlight_items WHERE 1=1"
            params = []
            if start_iso:
                query += " AND created_at >= ?"
                params.append(start_iso)
            if end_iso:
                query += " AND created_at <= ?"
                params.append(end_iso)
            query += " ORDER BY created_at ASC"
            return conn.execute(query, params).fetchall()

    def query_tasks(self, start_iso: Optional[str] = None, end_iso: Optional[str] = None) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params = []
            if start_iso:
                query += " AND start_time >= ?"
                params.append(start_iso)
            if end_iso:
                query += " AND start_time <= ?"
                params.append(end_iso)
            query += " ORDER BY start_time ASC"
            return conn.execute(query, params).fetchall()

    def record_llm_token_log(self, record: LLMTokenRecord):
        """记录一条真实大模型 API 响应的计费 Token。"""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO llm_token_logs 
                (task_id, project_name, provider, model, prompt_tokens, completion_tokens, total_tokens, req_id, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.task_id,
                    record.project_name,
                    record.provider,
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.req_id,
                    record.source,
                    record.created_at,
                ),
            )
            conn.commit()

    def query_llm_tokens(self, start_iso: Optional[str] = None, end_iso: Optional[str] = None, 
                         provider: Optional[str] = None) -> List[sqlite3.Row]:
        """查询指定时间段或供应商的真实 Token 日志。"""
        with self.get_connection() as conn:
            query = "SELECT * FROM llm_token_logs WHERE 1=1"
            params = []
            if start_iso:
                query += " AND created_at >= ?"
                params.append(start_iso)
            if end_iso:
                query += " AND created_at <= ?"
                params.append(end_iso)
            if provider:
                query += " AND provider = ?"
                params.append(provider.lower())
            query += " ORDER BY created_at ASC"
            return conn.execute(query, params).fetchall()
