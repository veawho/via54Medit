"""关键事件的外部告警通道: 把「需要人来看一眼」的事件推到飞书。

为什么需要它
------------
守护进程的资源耗尽型故障属于"不崩溃的故障": 文件描述符吃紧时进程还在跑, KeepAlive 也
不触发, 只靠本地日志与 ``daemon --status`` 得有人主动去看才会发现 —— 5.4.5 那次就因此
静默了十余小时。本模块把这类信号推送到飞书, 让它在无人值守时也能被看见。

设计要点
--------
1. **绝不反噬调用方**: 对外函数一律吞掉异常并返回 ``(False, 说明)``。告警通道坏掉不能
   把守护进程带崩, 也不能让"因为发不出告警"变成新的故障。
2. **按 key 限流, 且跨重启生效**: 状态落盘到 ``~/.medit/alerts_state.json``。否则守护
   进程被 KeepAlive 反复拉起时, 每次启动都会重发一遍同样的告警。
3. **失败快速重试、成功长期静默**: 成功后的静默期取 ``min_interval_minutes``; 失败则
   只等 ``RETRY_BACKOFF_MINUTES`` 就再试, 免得一次网络抖动把告警静音整整一小时。
4. **可开关**: 配置 ``alerts.enabled``, 默认开; 也可用 ``medit-telemetry alert --disable``
   就地关掉。
"""

import json
import os
import socket
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 限流状态文件 (含上次发送时间, 不含任何凭据)
STATE_FILE = os.path.expanduser(r"~/.medit/alerts_state.json")

# 发送失败后的重试间隔 (分钟)
RETRY_BACKOFF_MINUTES = 10

# 未配置时使用的默认值
DEFAULT_MIN_INTERVAL_MINUTES = 60

_LEVEL_COLORS = {"critical": "red", "warning": "orange", "info": "blue"}


def alert_settings(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """读取告警设置。

    ``cfg`` 可传入已加载的完整配置以免重复读盘; 任何异常都退回默认值 ——
    读配置失败不该有能力让告警逻辑本身崩掉。
    """
    if cfg is None:
        try:
            from .config import load_config

            cfg = load_config() or {}
        except Exception:
            cfg = {}

    section = cfg.get("alerts") or {}
    enabled = bool(section.get("enabled", True))
    try:
        min_interval = int(section.get("min_interval_minutes", DEFAULT_MIN_INTERVAL_MINUTES))
    except (TypeError, ValueError):
        min_interval = DEFAULT_MIN_INTERVAL_MINUTES
    if min_interval < 1:
        min_interval = 1
    return {"enabled": enabled, "min_interval_minutes": min_interval}


def _read_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: Dict[str, Any]):
    try:
        directory = os.path.dirname(STATE_FILE)
        os.makedirs(directory, exist_ok=True)
        fd = os.open(STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def rate_limited_for(
    key: str, min_interval_minutes: int, now: Optional[datetime] = None
) -> Optional[int]:
    """返回该 key 还需等待的分钟数; 未被限流时返回 ``None``。"""
    entry = _read_state().get(key) or {}
    stamp = entry.get("last_attempt")
    if not stamp:
        return None
    try:
        last = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    gap = min_interval_minutes if entry.get("last_ok") else min(RETRY_BACKOFF_MINUTES, min_interval_minutes)
    elapsed_min = ((now or datetime.now()) - last).total_seconds() / 60.0
    if elapsed_min < gap:
        return int(gap - elapsed_min) + 1
    return None


def build_alert_card(
    title: str, lines: List[str], level: str = "warning", nickname: str = "", host: str = ""
) -> Dict[str, Any]:
    """构建告警交互式卡片 (沿用与战报卡片一致的卡片结构)。"""
    elements: List[Dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": ln}} for ln in lines if ln
    ]
    elements.append({"tag": "hr"})
    who = " · ".join(x for x in (nickname, host) if x)
    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": f"via54Medit 守护进程告警 · {who} · {datetime.now():%Y-%m-%d %H:%M:%S}",
        }],
    })
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🚨 {title}"},
            "template": _LEVEL_COLORS.get(level, "orange"),
        },
        "elements": elements,
    }


def _post_card(card: Dict[str, Any]) -> Tuple[bool, str]:
    """把卡片推给配置里的用户; 任何异常都转成 (False, 说明)。"""
    try:
        from .feishu_sync import FEISHU_API_BASE, FeishuSyncClient

        client = FeishuSyncClient()
        if not (client.app_id and client.app_secret and client.user_open_id):
            return False, "配置缺少 app_id / app_secret / open_id, 无法推送"

        token = client.get_tenant_token()
        if not token:
            return False, "获取 tenant_access_token 失败"

        url = f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type=open_id"
        payload = json.dumps({
            "receive_id": client.user_open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") == 0:
            return True, f"推送成功 (Message ID: {data.get('data', {}).get('message_id')})"
        return False, f"推送失败: code={data.get('code')}, msg={data.get('msg')}"
    except Exception as e:
        return False, f"推送异常: {e}"


def _record_attempt(key: str, ok: bool):
    state = _read_state()
    state[key] = {
        "last_attempt": datetime.now().isoformat(timespec="seconds"),
        "last_ok": bool(ok),
    }
    _write_state(state)


def send_alert(
    title: str,
    lines: List[str],
    key: Optional[str] = None,
    level: str = "warning",
    force: bool = False,
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """发送一条告警卡片, 返回 ``(是否真的发出, 说明)``。

    ``force=True`` 跳过开关与限流, 供 ``--test`` 与人工触发使用。
    本函数永不抛异常 —— 调用方 (守护进程) 不需要为它做任何保护。
    """
    try:
        cfg: Dict[str, Any] = {}
        try:
            from .config import load_config

            cfg = load_config() or {}
        except Exception:
            pass

        conf = settings if settings is not None else alert_settings(cfg)
        if not conf["enabled"] and not force:
            return False, "告警已关闭 (alerts.enabled = false)"

        bucket_key = key or title
        if not force:
            wait = rate_limited_for(bucket_key, conf["min_interval_minutes"])
            if wait is not None:
                return False, f"限流中: 同类告警约 {wait} 分钟后再试"

        nickname = (cfg.get("user") or {}).get("nickname", "")
        try:
            host = socket.gethostname()
        except Exception:
            host = ""

        try:
            ok, msg = _post_card(build_alert_card(title, lines, level, nickname, host))
        except Exception as e:
            ok, msg = False, f"推送异常: {e}"

        # 无论成败都记一次尝试 —— 否则"每次都抛异常"会让限流形同虚设, 守护进程每 5 秒
        # 滴答就重试一次, 反而变成另一种刷屏。
        _record_attempt(bucket_key, ok)
        return ok, msg
    except Exception as e:
        return False, f"告警通道异常 (已忽略, 不影响调用方): {e}"


def alert_status(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """汇总告警通道的当前状态, 供 ``alert --status`` 展示。"""
    if cfg is None:
        try:
            from .config import load_config

            cfg = load_config() or {}
        except Exception:
            cfg = {}

    conf = alert_settings(cfg)
    feishu = cfg.get("feishu") or {}
    user = cfg.get("user") or {}
    return {
        "enabled": conf["enabled"],
        "min_interval_minutes": conf["min_interval_minutes"],
        "state_file": STATE_FILE,
        "rate_limits": _read_state(),
        "has_credentials": bool(
            feishu.get("app_id") and feishu.get("app_secret") and user.get("open_id")
        ),
        "nickname": user.get("nickname", ""),
    }


def send_test_alert() -> Tuple[bool, str]:
    """发送一条测试告警 (绕过开关与限流), 用于验证通道是否打通。"""
    return send_alert(
        "告警通道测试",
        [
            "**来源**：`medit-telemetry alert --test`",
            "**含义**：这条消息能收到, 说明守护进程的关键告警也送达得出去。",
            "**说明**：测试告警不受开关与限流影响, 也不会占用正式告警的限流额度。",
        ],
        key="__test__",
        level="info",
        force=True,
    )
