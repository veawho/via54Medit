"""Go 侧 LLM 用量 spool 的摄入器。

背景
----
仓库里其实有**两套** LLM 调用面:

* Python 侧 (``scripts/provider_llm.py`` / ``glm_vision.py`` / ``hl_v3_final/vision_check.py`` …)
  直接调 :func:`telemetry.token_tracker.record_llm_usage` 入库;
* Go 侧 (``internal/foundation/llm.go``、``llm_glm.go``) —— ``medit ask`` / ``medplan`` /
  docproc / medit-mcp 都走这里。Go 没有 SQLite 驱动, 所以它把每次调用的真实
  ``usage`` 追加到一行 JSONL, 由本模块**幂等**地摄入 ``llm_token_logs``。

幂等性
------
每行都带 ``req_id`` (服务商返回的 id, 没有就自造唯一值)。摄入时先查出库里已有的
req_id 再写, 所以"写了一半崩了、下一轮重跑"不会重复计费 —— 这正是不能靠
"读完就删 spool"来保证正确性的原因。
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import llm_providers
from .db import TelemetryDB
from .models import LLMTokenRecord

#: 与 Go 侧 ``foundation.LLMUsageSpoolEnv`` 保持同名同语义
SPOOL_ENV = llm_providers.SPOOL_ENV

#: 一批最多摄入多少行, 防止异常巨大的 spool 一次吃满内存
MAX_BATCH = 20000


def spool_path() -> str:
    """spool 路径。与 Go 端 ``spoolPath()`` 同一套解析规则。"""
    v = (os.environ.get(SPOOL_ENV) or "").strip()
    if v:
        return os.path.expanduser(v)
    home = os.path.expanduser("~")
    return os.path.join(home, ".medit", "llm_usage_spool.jsonl")


def normalize_provider(name: str) -> str:
    """把 Go 侧的名字归一成落库用的名字(glm → zhipu 等)。"""
    return llm_providers.PROVIDER_ALIASES.get(
        (name or "").strip().lower(), (name or "unknown").strip().lower() or "unknown")


def _as_int(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0


def _parse_created_at(rec: Dict[str, Any]) -> str:
    """优先用 Go 端写下的 ts; 解析不了才退回当前时间。

    用 ts 才能让"上周花了多少 token"这类按时间切分的统计对齐真实调用时刻,
    而不是对齐"摄入时刻"。
    """
    raw = str(rec.get("ts") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(
                tzinfo=None).isoformat()
        except ValueError:
            pass
    return datetime.now().isoformat()


def _to_record(rec: Dict[str, Any], raw_line: str) -> Optional[LLMTokenRecord]:
    """把一行 spool JSON 变成一条待入库记录; 不合格返回 None。"""
    if not isinstance(rec, dict):
        return None

    prompt_tokens = _as_int(rec.get("prompt_tokens"))
    completion_tokens = _as_int(rec.get("completion_tokens"))
    total_tokens = _as_int(rec.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0:
        # 没有 token 的行(服务商没返回 usage)不该入库 —— 记 0 只会污染统计口径
        return None

    req_id = str(rec.get("req_id") or "").strip()
    if not req_id:
        # 没给 id 也要能幂等: 用整行内容做指纹
        req_id = "spool-" + hashlib.sha1(raw_line.encode("utf-8")).hexdigest()[:24]

    return LLMTokenRecord(
        task_id=str(rec.get("task_id") or ""),
        project_name=str(rec.get("project_name") or ""),
        provider=normalize_provider(str(rec.get("provider") or "")),
        model=str(rec.get("model") or "unknown"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        req_id=req_id,
        source=str(rec.get("source") or "go"),
        created_at=_parse_created_at(rec),
    )


def read_records(path: Optional[str] = None):
    """读 spool, 返回 ``(可入库记录, 坏行说明, 已处理字节数, 是否被单批上限截断)``。

    按**字节**读而不是按文本读: 返回值里的"已处理字节数"要用来把 spool 切成
    "处理过的头"与"还没读的尾", 而文本流的 ``tell()`` 与字节数在非 ASCII 内容上
    并不一致 —— 拿它去切片会把某一行劈成两半。

    坏行只跳过不中断(如实记进 bad)。
    """
    target = path or spool_path()
    records: List[LLMTokenRecord] = []
    bad: List[str] = []
    consumed = 0
    truncated = False
    if not os.path.exists(target):
        return records, bad, consumed, truncated

    with open(target, "rb") as fh:
        offset = 0
        for lineno, raw in enumerate(fh, 1):
            offset += len(raw)
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                consumed = offset
                continue
            if len(records) >= MAX_BATCH:
                # 到上限就停; 这一行**不算处理过**, 留给下一轮
                truncated = True
                break
            consumed = offset
            try:
                rec = json.loads(line)
            except ValueError as exc:
                bad.append("第 %d 行不是合法 JSON: %s" % (lineno, exc))
                continue
            item = _to_record(rec, line)
            if item is None:
                bad.append("第 %d 行没有可用 token 计数, 已跳过" % lineno)
                continue
            records.append(item)
    return records, bad, consumed, truncated


def _commit_progress(path: str, consumed: int) -> str:
    """把**已经处理过**的前 ``consumed`` 字节挪走, 只留还没读的尾巴。

    为什么不是"整文件轮转": 单批上限一旦生效, 整文件轮转会**把没读到的行直接丢掉**,
    那是真的丢账。而"只截断不推进"同样不行 —— 已入库的重复行会一直占着批额,
    后面的行永远读不到。所以必须按"已处理到哪"来推进。

    安全性: 写入用 ``os.replace``(原子)。先落库再推进, 所以任何时刻崩溃都只是
    "重放一次已经被 req_id 去重挡掉的记录", 不会重复计费, 也不会丢。
    处理过的头会另存一份 ``.ingested`` 留作现场。
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(consumed)
            tail = fh.read()
    except OSError:
        return ""

    rotated = path + ".ingested"
    try:
        with open(rotated, "wb") as fh:
            fh.write(head)
    except OSError:
        rotated = ""

    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(tail)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ""
    return rotated


def ingest(path: Optional[str] = None, db: Optional[TelemetryDB] = None,
           rotate: bool = True) -> Dict[str, Any]:
    """把 spool 摄入 ``llm_token_logs``。

    返回 ``{"path","read","imported","duplicated","invalid","truncated",
    "rotated_to","problems"}``。``imported + duplicated + invalid`` 应当等于 ``read``
    (被单批上限截断时除外, ``truncated=True``)。

    ``rotate=False`` 只读不动文件, 供校验用(部署校验会真摄入, 但它不关心 spool 去留)。
    """
    target = path or spool_path()
    out: Dict[str, Any] = {
        "path": target, "read": 0, "imported": 0,
        "duplicated": 0, "invalid": 0, "rotated_to": "", "problems": [],
        "truncated": False,
    }
    records, bad, consumed, truncated = read_records(target)
    out["read"] = len(records) + len(bad)
    out["invalid"] = len(bad)
    out["problems"] = bad
    out["truncated"] = truncated
    if not records:
        # 一行可入库的都没有, 但坏行/空行也要清掉, 否则它们会一直卡在同一处
        if rotate and consumed:
            out["rotated_to"] = _commit_progress(target, consumed)
        return out

    target_db = db or TelemetryDB()
    seen = target_db.existing_llm_req_ids([r.req_id for r in records])
    for rec in records:
        if rec.req_id in seen:
            out["duplicated"] += 1
            continue
        target_db.record_llm_token_log(rec)
        seen.add(rec.req_id)
        out["imported"] += 1

    # 只推进到"已处理"的位置: 截断时尾巴原样留着, 下一轮接着读。
    if rotate and consumed:
        out["rotated_to"] = _commit_progress(target, consumed)
    return out


def write_spool_record(record: Dict[str, Any], path: Optional[str] = None) -> bool:
    """把一条 LLM 用量记录追加到 spool。

    供 TraeWork 伴侣进程 / 插件 / MCP 调用: 它们拿到 IDE 的真实 usage 后,
    以 ``provider="traework"`` 写入 spool, 由 :func:`ingest` 统一摄入本库。

    ``record`` 建议包含的字段(与 Go 侧 ``recordLLMUsage`` 一致):
      provider, model, prompt_tokens, completion_tokens, total_tokens,
      req_id, source, project_name, ts。
    缺失的字段会自动补齐: ts 为当前 UTC 时间, provider/model 默认 unknown,
    total_tokens 为 prompt + completion, 空 req_id 会生成一个指纹 id。

    返回 ``True`` 表示成功追加; 失败时静默返回 ``False``(记账是旁路)。
    """
    if not isinstance(record, dict):
        return False
    prompt = _as_int(record.get("prompt_tokens"))
    completion = _as_int(record.get("completion_tokens"))
    total = _as_int(record.get("total_tokens"))
    if total <= 0:
        total = prompt + completion
    if total <= 0:
        return False

    provider = str(record.get("provider") or "unknown").strip() or "unknown"
    model = str(record.get("model") or "unknown").strip() or "unknown"
    req_id = str(record.get("req_id") or "").strip()
    if not req_id:
        fingerprint = json.dumps(record, sort_keys=True, ensure_ascii=False)
        req_id = "traework-" + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:24]

    ts = str(record.get("ts") or "").strip()
    if not ts:
        ts = datetime.now().astimezone().isoformat()

    line = json.dumps({
        "ts": ts,
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "req_id": req_id,
        "source": str(record.get("source") or "traework").strip() or "traework",
        "project_name": str(record.get("project_name") or ""),
    }, ensure_ascii=False)

    target = path or spool_path()
    try:
        if dir_ := os.path.dirname(target):
            os.makedirs(dir_, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except OSError:
        return False


def spool_status(path: Optional[str] = None) -> Dict[str, Any]:
    """spool 当前状态, 用于报表与部署自检里的"有没有漏记"。"""
    target = path or spool_path()
    st: Dict[str, Any] = {"path": target, "exists": False, "pending": 0, "bytes": 0, "mtime": ""}
    try:
        info = os.stat(target)
    except OSError:
        return st
    st["exists"] = True
    st["bytes"] = info.st_size
    st["mtime"] = datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds")
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            st["pending"] = sum(1 for ln in fh if ln.strip())
    except OSError:
        pass
    return st
