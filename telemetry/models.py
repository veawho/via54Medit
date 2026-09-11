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
    #: 其他工作 —— 不属于上面三类文献工作的一切（PPT/Word 渲染、PDF 解析、
    #: 数据同步、巡检、外部脚本等）。没有人工基准, 故只统计实际工时与 Token。
    OTHER = "other"


# --------------------------------------------------------------------------- #
# 类目归类 —— **唯一事实来源**
#
# 报告与推送里有四个类目: 文献检索 / 文献下载 / 文献高亮 / 其他。
# 归类规则集中在这里, 由 aggregator 与各推送端共用 —— 否则四处各写一份判断,
# 迟早出现"卡片上是 A、表格里是 B"的错位。
# --------------------------------------------------------------------------- #
CATEGORY_RETRIEVAL = "retrieval"
CATEGORY_DOWNLOAD = "download"
CATEGORY_HIGHLIGHT = "highlight"
CATEGORY_OTHER = "other"

#: 三个业务类目(有人工节约基准的类目)。
BUSINESS_CATEGORIES = (CATEGORY_RETRIEVAL, CATEGORY_DOWNLOAD, CATEGORY_HIGHLIGHT)
#: 全部类目。
ALL_CATEGORIES = BUSINESS_CATEGORIES + (CATEGORY_OTHER,)

#: task_type -> 类目。
#: * ``correction`` 并入 ``highlight``(修正属于高亮质检环节);
#: * **未列出的 task_type 一律归入 ``other``** —— "其他"是兜底类目,
#:   宁可多记也不丢: 一个没预料到的新 task_type 不该从战报里消失。
TASK_TYPE_TO_CATEGORY: Dict[str, str] = {
    TaskType.RETRIEVAL.value: CATEGORY_RETRIEVAL,
    TaskType.DOWNLOAD.value: CATEGORY_DOWNLOAD,
    TaskType.HIGHLIGHT.value: CATEGORY_HIGHLIGHT,
    TaskType.CORRECTION.value: CATEGORY_HIGHLIGHT,
    TaskType.OTHER.value: CATEGORY_OTHER,
}


def classify_task_type(task_type: Any) -> str:
    """把任意 ``task_type`` 归到四个类目之一。

    未知/空值 -> ``other``。接受 ``TaskType`` 枚举或裸字符串(库里存的是字符串)。
    """
    value = getattr(task_type, "value", None)
    if value is None:
        value = "" if task_type is None else str(task_type)
    return TASK_TYPE_TO_CATEGORY.get(str(value).strip().lower(), CATEGORY_OTHER)


def category_of_llm_log(task_id: str, task_category_index: Dict[str, str]) -> str:
    """把一条 LLM 调用归口到类目。

    规则**不猜**: 只按 ``task_id`` 去 ``tasks`` 表里查该任务的类目;
    查不到(含 ``task_id`` 为空 —— 调用方没标归属)时归入 ``other``。

    这样"其他 Token"的含义是确定的: *未能归属到三类业务工作的消耗*。
    它恒为总量 ``tokens.total_tokens`` 的子集, 不会与三类重复计算。
    """
    key = (task_id or "").strip()
    if not key:
        return CATEGORY_OTHER
    return task_category_index.get(key, CATEGORY_OTHER)


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

    # 4. 其他工作统计 (不属于上面三类文献工作的一切)
    #    口径: 只统计**实际工时**与 **Token 消耗** —— 其他类目没有人工基准,
    #    因此**不产出"节约工时"**(宁可不给, 也不编一个基准出来)。
    other_count: int = 0
    other_duration_seconds: float = 0.0
    other_avg_seconds: float = 0.0
    other_prompt_tokens: int = 0
    other_completion_tokens: int = 0
    other_total_tokens: int = 0
    other_llm_call_count: int = 0
    #: 其中"没有 task_id 归属、因而落到其他"的 Token —— 用于分辨
    #: "确实是其他工作"与"调用方忘了标归属", 避免这个数字说不清。
    other_unattributed_tokens: int = 0

    # 5. 人效节约总计
    total_saved_seconds: float = 0.0
    total_saved_hours: float = 0.0
    
    # 6. Token 消耗统计 (默认 exact 模式: 100% 对应服务商控制台账单)
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
            "other": {
                "count": self.other_count,
                "duration_seconds": round(self.other_duration_seconds, 2),
                "avg_seconds": round(self.other_avg_seconds, 2),
                "duration_hours": round(self.other_duration_seconds / 3600.0, 2),
                "prompt_tokens": self.other_prompt_tokens,
                "completion_tokens": self.other_completion_tokens,
                "total_tokens": self.other_total_tokens,
                "llm_call_count": self.other_llm_call_count,
                "unattributed_tokens": self.other_unattributed_tokens,
                # 其他类目没有人工基准, 故没有 saved_* —— 显式写出, 免得调用方
                # 以为"漏了"而自己去补一个凭空的基准。
                "has_saved_baseline": False,
            },
            "tokens": {
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
                "token_mode": self.token_mode,
                "llm_call_count": self.llm_call_count,
            },
        }
