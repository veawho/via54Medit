"""via54Medit Telemetry Package.

导入策略: 本文件只暴露版本号; 其余对外符号按需加载 (PEP 562 模块级 ``__getattr__``)。

为什么不再 eager 导入
--------------------
任何 ``import telemetry.*`` 都会先执行本文件, 于是调用方即便只想用一个轻量子模块, 也会
被迫拉起整张依赖图 —— 实测 ``import telemetry.alerter`` 连带导入 131 个模块, 其中还包含
PyMuPDF (``watcher`` -> ``pdf_utils`` -> ``fitz``)。两个真实代价:

1. **多余开销**: 纯文本 / 纯网络的调用方 (``envcheck``、``alerter``) 也要为 PDF 依赖买单;
   连 ``import telemetry.db`` 这种只用到标准库的用法也不例外。
2. **输出污染**: ``fitz`` 在被导入时会往 stderr 打一行弃用警告, 于是连
   ``medit-telemetry --env-check`` 这类诊断命令, 输出前面都会莫名多出一行 PDF 库的警告。

惰性之后, 每个子模块只为自己真正用到的依赖买单; 既有的 ``from telemetry import
TelemetryDB`` 之类写法完全不受影响 (由 ``__getattr__`` 兜住)。
"""

import importlib
from typing import Any

__version__ = "1.5.46"

#: 对外符号 -> (子模块, 模块内名称)
_LAZY_EXPORTS = {
    "TaskType": (".models", "TaskType"),
    "RetrievalItem": (".models", "RetrievalItem"),
    "DownloadItem": (".models", "DownloadItem"),
    "HighlightItem": (".models", "HighlightItem"),
    "TaskRecord": (".models", "TaskRecord"),
    "AggregateReport": (".models", "AggregateReport"),
    "LLMTokenRecord": (".models", "LLMTokenRecord"),
    "TelemetryDB": (".db", "TelemetryDB"),
    "TelemetryTracker": (".tracker", "TelemetryTracker"),
    "TelemetryAggregator": (".aggregator", "TelemetryAggregator"),
    "FeishuSyncClient": (".feishu_sync", "FeishuSyncClient"),
    "WorkspaceScanner": (".watcher", "WorkspaceScanner"),
    "record_llm_usage": (".token_tracker", "record_llm_usage"),
}

__all__ = ["__version__", *sorted(_LAZY_EXPORTS)]


def __getattr__(name: str) -> Any:
    """按需加载对外符号 (PEP 562)。

    解析结果写回 ``globals()``, 后续同名访问就不再走这里。
    """
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(importlib.import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
