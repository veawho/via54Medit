"""SQLite storage engine for via54Medit telemetry."""

import json
import os
import sqlite3
from contextlib import contextmanager
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

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

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

    # ------------------------------------------------------------------ #
    # 字段刷新 —— 让"已登记条目"跟着最新观测值走
    #
    # 背景: watcher 遇到已收录的条目原先直接 `continue`, 于是**标注数(num_annots)与文件
    # 大小从此冻结在首次登记时的值**。用户在已高亮的 PDF 上继续加标注、或重新下载了更大的
    # PDF, 报表却纹丝不动 —— 这是"统计数据不实时"最具体的形态。
    #
    # 约定: ``None`` 表示"这次没观测到", 保持原值; 不用默认值去覆盖已有数据
    # (否则一次扫描失败就会把好数据抹成 0, 比不刷新更糟)。
    # ------------------------------------------------------------------ #
    def refresh_highlight_item(self, pdf_path: str, *, page_count: Optional[int] = None,
                               num_annots: Optional[int] = None) -> int:
        """把已登记高亮条目的页数/标注数刷新为最新观测值。返回改动行数。"""
        return self._refresh_rows(
            "highlight_items", "pdf_path", pdf_path,
            {"page_count": page_count, "num_annots": num_annots})

    def refresh_download_item(self, pdf_path: str, *, file_size_bytes: Optional[int] = None,
                              success: Optional[int] = None) -> int:
        """把已登记下载条目的文件大小/成功标记刷新为最新观测值。返回改动行数。"""
        return self._refresh_rows(
            "download_items", "pdf_path", pdf_path,
            {"file_size_bytes": file_size_bytes, "success": success})

    def _refresh_rows(self, table: str, where_col: str, where_val: str,
                      fields: Dict[str, Any]) -> int:
        updates = {k: v for k, v in (fields or {}).items() if v is not None}
        if not updates or not where_val:
            return 0
        sets = ", ".join("%s = ?" % k for k in updates)
        params = list(updates.values()) + [where_val]
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE %s SET %s WHERE %s = ?" % (table, sets, where_col), params)
            conn.commit()
            return cur.rowcount or 0

    def latest_ingest_at(self) -> Optional[str]:
        """最近一次明细入库时间 —— 用来回答"数据到底是不是最新的"。

        取各明细表 ``created_at`` 的最大值(而不是扫描任务的时间): 扫描可能什么都没发现,
        而"入库时间"才是数据新鲜度的真实证据。
        """
        with self.get_connection() as conn:
            stamps = []
            for table in ("retrieval_items", "download_items", "highlight_items"):
                row = conn.execute("SELECT MAX(created_at) AS m FROM %s" % table).fetchone()
                if row and row["m"]:
                    stamps.append(row["m"])
            return max(stamps) if stamps else None

    def table_counts(self) -> Dict[str, int]:
        """各明细表当前行数 —— 心跳与状态页的"实时数字"。"""
        out = {}
        with self.get_connection() as conn:
            for table in ("retrieval_items", "download_items", "highlight_items", "tasks"):
                out[table] = conn.execute("SELECT COUNT(*) AS n FROM %s" % table).fetchone()["n"]
        return out

    def purge_ignored_path_items(self, is_ignored=None) -> Dict[str, int]:
        """删除指向备份/临时目录的明细行, 返回各表删除的行数。

        为什么需要: 路径卫生规则挡住的是**将来**的扫描, 但库里已经被记过的重复行不会自己
        消失 —— 不清理的话报表仍然虚高, 直到人工去删。实测 RSV 的高亮因此虚高到 3 倍。

        **只在同一篇文献于非备份路径下也有行时才删。** 这样即便判定规则有偏差, 也绝不会把
        某一个文献整个删掉 —— 最坏情况只是少删几行, 统计口径不会被削。

        ``is_ignored`` 由调用方注入(默认用 watcher 的规则), 免得 db 反向依赖 watcher。
        """
        if is_ignored is None:
            from .watcher import is_ignored_path as is_ignored
        removed = {"highlight_items": 0, "download_items": 0}
        with self.get_connection() as conn:
            for table in removed:
                rows = conn.execute(
                    "SELECT id, paper_id, pdf_path FROM %s" % table).fetchall()
                kept_papers = set()
                drop = []
                for r in rows:
                    path = (r["pdf_path"] or "").strip()
                    pid = (r["paper_id"] or "").strip().lower()
                    if path and is_ignored(path):
                        drop.append((r["id"], pid))
                    else:
                        kept_papers.add(pid)
                # 只在"同一篇文献在非备份路径下也有行"时才删 —— 绝不会把某个文献整删掉
                safe = [rid for rid, pid in drop if pid and pid in kept_papers]
                if safe:
                    conn.executemany("DELETE FROM %s WHERE id = ?" % table,
                                     [(rid,) for rid in safe])
                    removed[table] = len(safe)
            conn.commit()
        return removed

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
