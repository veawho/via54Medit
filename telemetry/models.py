"""Data models for via54Medit telemetry and analytics."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class TaskType(str, Enum):
    RETRIEVAL = "retrieval"
    DOWNLOAD = "download"
    HIGHLIGHT = "highlight"
    CORRECTION = "correction"


@dataclass
class RetrievalItem:
    paper_id: str
    doi: str = ""
    url: str = ""
    citation_text: str = ""
    duration_seconds: float = 0.0
    source: str = ""
    success: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DownloadItem:
    paper_id: str
    doi: str = ""
    pdf_path: str = ""
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error_msg: str = ""
    source: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class HighlightItem:
    paper_id: str
    pdf_path: str = ""
    page_count: int = 0
    num_annots: int = 0
    highlight_duration_seconds: float = 0.0
    correction_duration_seconds: float = 0.0
    status: str = "yellow_ok"  # yellow_ok, corrected, missing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LLMTokenRecord:
    """真实 LLM 服务商网关返回的精确账单 Token 日志。"""
    id: Optional[int] = None
    task_id: str = ""
    project_name: str = ""
    provider: str = "deepseek"   # deepseek, zhipu, openai, sensenova, etc.
    model: str = ""              # deepseek-chat, glm-4.6v-flash, etc.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    req_id: str = ""             # 服务商请求 ID (如 request_id)，用于核对账单
    source: str = ""             # 调用源脚本或模块
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TaskRecord:
    task_id: str
    task_type: TaskType
    project_name: str
    start_time: str
    end_time: str
    duration_seconds: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    status: str = "success"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregateReport:
    period_type: str  # "weekly", "monthly", "all_time"
    period_name: str  # e.g., "2026年第37周", "2026年09月", "历史累计"
    start_date: str
    end_date: str
    
    # 1. 文献检索统计
    retrieval_count: int = 0
    retrieval_duration_seconds: float = 0.0
    retrieval_avg_seconds: float = 0.0
    retrieval_saved_seconds: float = 0.0  # 人工 7min/篇 - AI耗时
    
    # 2. 文献下载统计
    download_count: int = 0
    download_duration_seconds: float = 0.0
    download_avg_seconds: float = 0.0
    download_saved_seconds: float = 0.0  # 人工 2min/篇 - AI耗时
    
    # 3. 文献 Highlight 统计
    highlight_pages: int = 0
    highlight_count: int = 0
    highlight_duration_seconds: float = 0.0
    highlight_avg_seconds: float = 0.0
    correction_duration_seconds: float = 0.0
    correction_avg_seconds: float = 0.0
    highlight_saved_seconds: float = 0.0  # 人工 4min/篇 - (AI高亮耗时 + 修正耗时)
    
    # 4. 人效节约总计
    total_saved_seconds: float = 0.0
    total_saved_hours: float = 0.0
    
    # 5. Token 消耗统计 (默认 exact 模式: 100% 对应服务商控制台账单)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    token_mode: str = "exact"     # "exact" (真实网关直连) 或 "estimated" (估算)
    llm_call_count: int = 0       # 真实 LLM API 请求次数
    
    # 历史对比 (用于月报)
    historical_cumulative: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_type": self.period_type,
            "period_name": self.period_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "retrieval": {
                "count": self.retrieval_count,
                "duration_seconds": round(self.retrieval_duration_seconds, 2),
                "avg_seconds": round(self.retrieval_avg_seconds, 2),
                "saved_minutes": round(self.retrieval_saved_seconds / 60.0, 1),
                "saved_hours": round(self.retrieval_saved_seconds / 3600.0, 2),
            },
            "download": {
                "count": self.download_count,
                "duration_seconds": round(self.download_duration_seconds, 2),
                "avg_seconds": round(self.download_avg_seconds, 2),
                "saved_minutes": round(self.download_saved_seconds / 60.0, 1),
                "saved_hours": round(self.download_saved_seconds / 3600.0, 2),
            },
            "highlight": {
                "pages": self.highlight_pages,
                "count": self.highlight_count,
                "duration_seconds": round(self.highlight_duration_seconds, 2),
                "avg_seconds": round(self.highlight_avg_seconds, 2),
                "correction_duration_seconds": round(self.correction_duration_seconds, 2),
                "correction_avg_seconds": round(self.correction_avg_seconds, 2),
                "saved_minutes": round(self.highlight_saved_seconds / 60.0, 1),
                "saved_hours": round(self.highlight_saved_seconds / 3600.0, 2),
            },
            "overall": {
                "total_saved_minutes": round(self.total_saved_seconds / 60.0, 1),
                "total_saved_hours": round(self.total_saved_hours, 2),
            },
            "tokens": {
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
                "token_mode": self.token_mode,
                "llm_call_count": self.llm_call_count,
            },
        }
