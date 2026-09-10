import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any

from .db import TelemetryDB, DEFAULT_DB_PATH
from .models import DownloadItem, HighlightItem, RetrievalItem, TaskRecord, TaskType
from .pdf_utils import get_pdf_page_count


class TelemetryTracker:
    def __init__(self, db: Optional[TelemetryDB] = None):
        self.db = db or TelemetryDB()

    @contextmanager
    def track_retrieval(self, project_name: str = "default", extra: Optional[Dict[str, Any]] = None):
        """Context manager to track literature URL retrieval."""
        task_id = f"retrieval_{uuid.uuid4().hex[:12]}"
        start_ts = time.time()
        start_iso = datetime.now().isoformat()
        items: List[RetrievalItem] = []
        token_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        class RetrievalCollector:
            def add_item(self, paper_id: str, url: str = "", doi: str = "", 
                         citation_text: str = "", duration_seconds: float = 0.0, 
                         source: str = "", success: bool = True):
                item = RetrievalItem(
                    paper_id=paper_id,
                    doi=doi,
                    url=url,
                    citation_text=citation_text,
                    duration_seconds=duration_seconds,
                    source=source,
                    success=success,
                )
                items.append(item)
                return item

            def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0):
                token_info["prompt_tokens"] += prompt_tokens
                token_info["completion_tokens"] += completion_tokens
                token_info["total_tokens"] += (prompt_tokens + completion_tokens)

        collector = RetrievalCollector()
        status = "success"
        try:
            yield collector
        except Exception as e:
            status = "failed"
            raise e
        finally:
            end_ts = time.time()
            end_iso = datetime.now().isoformat()
            duration = max(0.001, end_ts - start_ts)
            
            # 自动均摊单篇耗时（若单项未提供单项耗时）
            if items:
                unassigned = [it for it in items if it.duration_seconds <= 0]
                if unassigned:
                    avg_t = duration / len(items)
                    for it in unassigned:
                        it.duration_seconds = avg_t

            task_rec = TaskRecord(
                task_id=task_id,
                task_type=TaskType.RETRIEVAL,
                project_name=project_name,
                start_time=start_iso,
                end_time=end_iso,
                duration_seconds=duration,
                prompt_tokens=token_info["prompt_tokens"],
                completion_tokens=token_info["completion_tokens"],
                total_tokens=token_info["total_tokens"],
                status=status,
                extra={"items_count": len(items), **(extra or {})},
            )
            self.db.record_task(task_rec)
            for it in items:
                self.db.record_retrieval_item(task_id, it)

    @contextmanager
    def track_download(self, project_name: str = "default", extra: Optional[Dict[str, Any]] = None):
        """Context manager to track literature PDF downloading."""
        task_id = f"download_{uuid.uuid4().hex[:12]}"
        start_ts = time.time()
        start_iso = datetime.now().isoformat()
        items: List[DownloadItem] = []
        token_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        class DownloadCollector:
            def add_item(self, paper_id: str, doi: str = "", pdf_path: str = "",
                         file_size_bytes: int = 0, duration_seconds: float = 0.0,
                         success: bool = True, error_msg: str = "", source: str = ""):
                item = DownloadItem(
                    paper_id=paper_id,
                    doi=doi,
                    pdf_path=pdf_path,
                    file_size_bytes=file_size_bytes,
                    duration_seconds=duration_seconds,
                    success=success,
                    error_msg=error_msg,
                    source=source,
                )
                items.append(item)
                return item

            def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0):
                token_info["prompt_tokens"] += prompt_tokens
                token_info["completion_tokens"] += completion_tokens
                token_info["total_tokens"] += (prompt_tokens + completion_tokens)

        collector = DownloadCollector()
        status = "success"
        try:
            yield collector
        except Exception as e:
            status = "failed"
            raise e
        finally:
            end_ts = time.time()
            end_iso = datetime.now().isoformat()
            duration = max(0.001, end_ts - start_ts)

            if items:
                unassigned = [it for it in items if it.duration_seconds <= 0]
                if unassigned:
                    avg_t = duration / len(items)
                    for it in unassigned:
                        it.duration_seconds = avg_t

            success_count = sum(1 for it in items if it.success)
            task_rec = TaskRecord(
                task_id=task_id,
                task_type=TaskType.DOWNLOAD,
                project_name=project_name,
                start_time=start_iso,
                end_time=end_iso,
                duration_seconds=duration,
                prompt_tokens=token_info["prompt_tokens"],
                completion_tokens=token_info["completion_tokens"],
                total_tokens=token_info["total_tokens"],
                status=status if success_count == len(items) else ("partial" if success_count > 0 else "failed"),
                extra={"total_items": len(items), "success_count": success_count, **(extra or {})},
            )
            self.db.record_task(task_rec)
            for it in items:
                self.db.record_download_item(task_id, it)

    @contextmanager
    def track_highlight(self, project_name: str = "default", extra: Optional[Dict[str, Any]] = None):
        """Context manager to track literature highlighting & inspection/correction."""
        task_id = f"highlight_{uuid.uuid4().hex[:12]}"
        start_ts = time.time()
        start_iso = datetime.now().isoformat()
        items: List[HighlightItem] = []
        token_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        class HighlightCollector:
            def add_item(self, paper_id: str, pdf_path: str = "", page_count: int = 0,
                         num_annots: int = 0, highlight_duration_seconds: float = 0.0,
                         correction_duration_seconds: float = 0.0, status: str = "yellow_ok"):
                if page_count <= 0 and pdf_path and os.path.exists(pdf_path):
                    page_count = get_pdf_page_count(pdf_path)

                item = HighlightItem(
                    paper_id=paper_id,
                    pdf_path=pdf_path,
                    page_count=page_count,
                    num_annots=num_annots,
                    highlight_duration_seconds=highlight_duration_seconds,
                    correction_duration_seconds=correction_duration_seconds,
                    status=status,
                )
                items.append(item)
                return item

            def add_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0):
                token_info["prompt_tokens"] += prompt_tokens
                token_info["completion_tokens"] += completion_tokens
                token_info["total_tokens"] += (prompt_tokens + completion_tokens)

        collector = HighlightCollector()
        task_status = "success"
        try:
            yield collector
        except Exception as e:
            task_status = "failed"
            raise e
        finally:
            end_ts = time.time()
            end_iso = datetime.now().isoformat()
            duration = max(0.001, end_ts - start_ts)

            if items:
                unassigned_hl = [it for it in items if it.highlight_duration_seconds <= 0]
                if unassigned_hl:
                    avg_t = duration / len(items)
                    for it in unassigned_hl:
                        it.highlight_duration_seconds = avg_t

            task_rec = TaskRecord(
                task_id=task_id,
                task_type=TaskType.HIGHLIGHT,
                project_name=project_name,
                start_time=start_iso,
                end_time=end_iso,
                duration_seconds=duration,
                prompt_tokens=token_info["prompt_tokens"],
                completion_tokens=token_info["completion_tokens"],
                total_tokens=token_info["total_tokens"],
                status=task_status,
                extra={"highlight_items_count": len(items), **(extra or {})},
            )
            self.db.record_task(task_rec)
            for it in items:
                self.db.record_highlight_item(task_id, it)
