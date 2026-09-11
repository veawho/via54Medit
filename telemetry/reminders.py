"""推送日前一个工作日的「别关机」提醒。

为什么需要它
------------
推送是**到点触发**的: 守护进程必须在目标时刻正在运行(机器开着、没休眠), 那一次周报/月报
才会发出去。机器关机或睡过去了, 这一次就静默丢失 —— 没有报错, 也没有补发。提前一个
工作日提醒是唯一能在事前降低这种概率的手段。

(提醒本身也要靠机器在那一刻运行才能发出。所以它是降低概率, 不是消除 —— 
不做过度承诺。守护进程下次启动时若仍在提醒日的提醒时刻之后, 会补发一次, 见下。)

设计要点
--------
1. **按"前一个工作日"算, 不按"前一天"**: 春节/国庆连休会让前一天本身是假期, 调休补班
   又会让周六变成工作日。日期一律问 ``holidays`` 模块。
2. **同一天合并成一张卡**: 2026-09-30 既是"10-01 月报"的前一个工作日, 也是"10-05 周报"
   的前一个工作日 —— 分两条发就是同一个晚上骚扰两次。这里合并。
3. **幂等靠落盘的 key**: key 取 ``reminder:<提醒日>``, 成功后的静默期设为 24h。这样
   守护进程被反复拉起也不会重发; 而**发送失败会 10 分钟后就重试**, 不会因为一次网络
   抖动就把当晚的提醒丢掉。
4. **事后补发**: 提醒条件是"到了提醒日的提醒时刻之后", 而不是"正好那一分钟"。所以
   18:00 该提醒、机器 22:00 才开机, 一样会补上 —— 当晚提醒仍有意义。
5. **永不抛异常**: 复用 ``alerter.send_alert``, 它对外只返回 ``(bool, 说明)``。
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import holidays, schedule

#: 提醒时刻默认值 —— 取工作日结束前后, 用户离开工位之前。
DEFAULT_REMINDER_TIME = "18:00"

#: 成功发送后的静默期(分钟)。取 24h: key 已按"提醒日"分桶, 当天不再重发即可。
_SENT_SILENCE_MINUTES = 24 * 60

KIND_LABELS = schedule.KIND_LABELS


def _parse_hhmm(text: str, fallback: str) -> Tuple[int, int]:
    return schedule.parse_hhmm(text, fallback)


def reminder_settings(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """读取提醒设置, 任何异常都退回默认值(默认**开启**)。"""
    section = ((cfg or {}).get("schedule") or {}).get("reminder") or {}
    h, m = _parse_hhmm(section.get("time"), DEFAULT_REMINDER_TIME)
    return {
        "enabled": bool(section.get("enabled", True)),
        "time": "%02d:%02d" % (h, m),
        "hour": h,
        "minute": m,
    }


# --------------------------------------------------------------------------- #
# 下一次推送目标时刻 —— **一律走 schedule 模块**
#
# 顺延规则(遇周末/法定节假日顺延到下一个工作日)必须与守护进程用同一份实现, 否则会出现
# "提醒说明天推、实际却推到假期之后"。schedule 模块就是那份唯一实现。
# --------------------------------------------------------------------------- #
def next_occurrence(cfg: Dict[str, Any], now: datetime, kind: str) -> Optional[datetime]:
    """下一次该类型的**生效**推送时刻(已顺延); 未启用时返回 ``None``。"""
    return schedule.next_occurrence(cfg, now, kind)


def upcoming_pushes(cfg: Dict[str, Any], now: datetime) -> List[Tuple[str, datetime]]:
    """所有已启用推送的下一次**生效**时刻, 按时间升序。"""
    by_kind = schedule.next_effective_by_kind(cfg, now)
    return sorted(by_kind.items(), key=lambda x: x[1])


def push_details(cfg: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """下一次各类型推送的完整信息(含是否顺延、原定日期、顺延原因)。"""
    out = []
    for kind, eff in upcoming_pushes(cfg, now):
        for occ in schedule.occurrences(cfg, now):
            if occ["kind"] == kind and occ["effective"] == eff:
                out.append(occ)
                break
    return out


# --------------------------------------------------------------------------- #
# 该不该提醒
# --------------------------------------------------------------------------- #
def due_reminders(cfg: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """今天该提醒的推送项(可能不止一个, 例如国庆前那个工作日)。

    条件: ``now`` 的日期 == **顺延后**目标日的**前一个工作日**, 且 ``now`` 已过提醒时刻。
    不要求"正好那一分钟" —— 机器晚开机也应当补上当晚的提醒。

    注意顺延的连带影响: 目标日顺延后, 它的"前一个工作日"也会跟着变(2026-10-01 顺延到
    10-08 后, 提醒日仍是 09-30 —— 因为 10-01~10-07 全是假期, 09-30 就是假期前最后一个工作日)。
    这也是为什么提醒日必须按**顺延后**的日期来算。
    """
    conf = reminder_settings(cfg)
    if not conf["enabled"]:
        return []

    due: List[Dict[str, Any]] = []
    for occ in push_details(cfg, now):
        target = occ["effective"]
        cal = holidays.calendar_for(target.year)
        remind_date = cal.previous_workday(target.date())
        if now.date() != remind_date:
            continue
        if (now.hour, now.minute) < (conf["hour"], conf["minute"]):
            continue
        due.append({
            "kind": occ["kind"],
            "label": occ["label"],
            "target": target,
            "raw": occ["raw"],
            "deferred": bool(occ["deferred"]),
            "reason": occ.get("reason") or "",
            "remind_date": remind_date,
            # 提醒日与推送日相隔的天数: 假期前最后一个工作日提醒时, 中间会隔着整段假期,
            # 文案据此换说法(不能说"今晚别关机", 那既不现实也没必要)。
            "gap_days": (target.date() - remind_date).days,
            "authoritative": cal.authoritative,
            "calendar_note": cal.note,
            "remind_status": cal.describe(remind_date),
        })
    due.sort(key=lambda x: x["target"])
    return due


def reminder_key(remind_date: date) -> str:
    """按"提醒日"分桶的幂等 key —— 同一天的所有目标共用一次发送。"""
    return "reminder:%s" % remind_date.isoformat()


def build_reminder_lines(due: List[Dict[str, Any]]) -> List[str]:
    """构造提醒卡片的正文。

    措辞按"提醒日到推送日隔了几天"变化 —— 这是顺延功能带来的必要修正: 提醒日取的是
    推送日的**前一个工作日**, 当中间隔着周末或整段假期时, "今晚请不要关机"既不准确
    也没必要(用户完全可以周末关机、周一再开)。
    """
    if not due:
        return []
    remind_date = due[0]["remind_date"]
    lines = [
        "**有战报要自动推送, 请保持设备开机联网。**",
        "",
        "推送是到点触发的: 机器关机或休眠, 这一次就会**静默丢失**(不报错、不补发)。",
        "",
    ]
    for item in due:
        target = item["target"]
        weekday = "周" + "一二三四五六日"[target.weekday()]
        lines.append(
            "• **%s** → `%s（%s）%s` 自动推送 + 多维表格同步"
            % (item["label"], target.strftime("%Y-%m-%d"), weekday, target.strftime("%H:%M"))
        )
        if item.get("deferred"):
            lines.append(
                "    - 原定 `%s`, 因%s顺延到该日" % (item["raw"].strftime("%Y-%m-%d"),
                                              item.get("reason") or "非工作日")
            )

    latest = max(item["target"] for item in due)
    lines += [
        "",
        "**请在 `%s` 之前确保设备开机联网, 并确认不会进入休眠。**" % latest.strftime("%Y-%m-%d"),
    ]
    if all(item.get("gap_days", 0) <= 1 for item in due):
        lines.append("也就是**明天**, 今晚请不要关机。")
    else:
        lines += [
            "",
            "_(今天是推送日前的最后一个工作日; 推送日与今天之间隔着休息日, "
            "期间不必守着设备, 只要在推送日之前开机联网即可。)_",
        ]

    lines += [
        "",
        "_(本条提醒按法定节假日安排在 `%s（%s）` 发出)"
        % (remind_date.isoformat(), due[0].get("remind_status") or ""),
    ]
    if not all(item.get("authoritative") for item in due):
        lines.append(
            "⚠️ 未取到 %d 年放假安排, 上述日期仅按周末推算, 未考虑调休补班; "
            "联网后可执行 `python -m telemetry.cli holiday --refresh` 补上。"
            % remind_date.year
        )
    return lines


def send_due(
    cfg: Dict[str, Any],
    now: Optional[datetime] = None,
    logger=None,
) -> Optional[Tuple[bool, str, str]]:
    """检查并发送提醒。返回 ``(是否发出, 说明, 幂等key)``; 今天不该提醒时返回 ``None``。

    调用方(守护进程)可把返回的 key 记在内存里, 避免在同一天里反复走这套判断;
    跨重启的幂等由 ``alerter`` 落盘的状态保证。
    """
    now = now or datetime.now()
    try:
        due = due_reminders(cfg, now)
    except Exception as e:                                  # noqa: BLE001
        if logger:
            logger("提醒检查异常(已忽略): %s" % e)
        return None
    if not due:
        return None

    key = reminder_key(due[0]["remind_date"])
    title = "别关机提醒：%s" % "、".join(item["label"] for item in due)
    try:
        from .alerter import send_alert

        ok, msg = send_alert(
            title,
            build_reminder_lines(due),
            key=key,
            level="info",
            # 提醒有自己的开关(schedule.reminder.enabled)。这里显式给出设置, 是为了让
            # 它**不受 alerts.enabled 影响** —— 关掉资源告警不该顺带关掉别关机提醒。
            # 静默期取 24h: key 已按提醒日分桶, 当天不再重发; 失败则 10 分钟后重试。
            settings={"enabled": True, "min_interval_minutes": _SENT_SILENCE_MINUTES},
        )
    except Exception as e:                                  # noqa: BLE001
        ok, msg = False, "提醒发送异常: %s" % e
    if logger:
        logger("⏰ 别关机提醒: %s" % msg)
    return ok, msg, key


def reminder_status(cfg: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """提醒的当前状态, 供 ``config`` / ``holiday --status`` 展示。

    ``raw`` / ``deferred`` / ``reason`` 一并给出 —— 排程顺延后, 只看"下次什么时候推"
    无法判断它是不是被顺延过, 而这正是排查"为什么不是周一发"的关键信息。
    """
    now = now or datetime.now()
    conf = reminder_settings(cfg)
    items = []
    for occ in push_details(cfg, now):
        target = occ["effective"]
        cal = holidays.calendar_for(target.year)
        remind = cal.previous_workday(target.date())
        items.append({
            "kind": occ["kind"],
            "label": occ["label"],
            "target": target.strftime("%Y-%m-%d %H:%M"),
            "raw": occ["raw"].strftime("%Y-%m-%d %H:%M"),
            "deferred": bool(occ["deferred"]),
            "reason": occ.get("reason") or "",
            "remind_date": remind.isoformat(),
            "remind_status": cal.describe(remind),
            "gap_days": (target.date() - remind).days,
            "authoritative": cal.authoritative,
            "already_due_today": bool(due_reminders(cfg, now)),
        })
    return {
        "enabled": conf["enabled"],
        "time": conf["time"],
        "defer_non_workday": schedule.deferral_enabled(cfg),
        "upcoming": items,
    }
