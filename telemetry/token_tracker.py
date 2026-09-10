"""Universal LLM Token Usage Tracker & Console Consistency Engine.

Captures exact billed tokens from any LLM provider response (DeepSeek, Zhipu GLM, OpenAI, SenseNova, etc.)
and persists them into the telemetry database for 100% console-aligned accounting.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Union

from .db import TelemetryDB
from .models import LLMTokenRecord


def record_llm_usage(
    response: Any,
    provider: str = "deepseek",
    model: str = "",
    project_name: str = "",
    task_id: str = "",
    source: str = "",
    db: Optional[TelemetryDB] = None,
) -> Optional[LLMTokenRecord]:
    """记录一次真实的大模型调用 Token 消耗，保证与服务商控制台 100% 绝对一致。

    支持格式:
    1. OpenAI / DeepSeek / GLM SDK Response 对象 (带 .usage)
    2. Dict 格式的 HTTP 响应体 (包含 "usage": {"prompt_tokens": ..., "completion_tokens": ...})
    3. 直接传入 {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    """
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    req_id = ""
    extracted_model = model

    # 1. 尝试从常见对象或字典中提取
    usage = None
    if hasattr(response, "usage") and response.usage is not None:
        usage = response.usage
        if hasattr(response, "id") and response.id:
            req_id = str(response.id)
        if hasattr(response, "model") and response.model:
            extracted_model = str(response.model)
    elif isinstance(response, dict):
        usage = response.get("usage", response)
        req_id = str(response.get("id") or response.get("request_id") or response.get("req_id", ""))
        if not extracted_model:
            extracted_model = str(response.get("model", ""))

    if usage is not None:
        if hasattr(usage, "prompt_tokens"):
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        elif isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0) or 0
            completion_tokens = usage.get("completion_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    elif isinstance(response, (int, float)):
        total_tokens = int(response)

    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return None

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    record = LLMTokenRecord(
        task_id=task_id,
        project_name=project_name,
        provider=provider.lower(),
        model=extracted_model or "unknown",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        req_id=req_id,
        source=source or "api_call",
        created_at=datetime.now().isoformat(),
    )

    target_db = db or TelemetryDB()
    target_db.record_llm_token_log(record)
    return record
