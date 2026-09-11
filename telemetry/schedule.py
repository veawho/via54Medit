"""推送排程的发生时刻 —— 含「遇到周末/法定节假日顺延到下一个工作日」。

为什么单独一个模块
------------------
"下一次推送到底是什么时候"有两个消费者:

* **守护进程** —— 据此决定此刻要不要真的推;
* **提醒模块** —— 据此决定哪一天提醒"别关机"。

两处各算一遍必然走样(本仓库在别处已经吃过"口径各算一遍、慢慢分叉"的亏), 所以只留一份实现。
提醒尤其依赖它: 如果提醒按**原始**目标日算、而守护进程按**顺延后**的日子推, 就会出现
"提醒说说明天推、实际却推到假期之后"这种自相矛盾。

顺延规则
--------
目标日落在**周末或法定节假日**时, 顺延到**下一个工作日**。判据是 ``holidays`` 模块的日历,
因此春节/国庆连休与调休补班都自动处理 —— 注意**补班的周六算工作日**, 不会被误顺延。

只改"哪一天发", 不改"报哪一期"
-------------------------------
报表周期仍按**实际发送日**计算(``get_weekly_report`` / ``get_monthly_report`` 的内部逻辑),
于是卡片上的 ``period_name``、表格行与多维表格记录三者自洽。常见顺延(1~6 天、仍在同一周/月内)
周期完全不变; 只有整周或整月都是假期的极端情形, 才会报到实际发送日所在的那一期 ——
那种情况下原定那一期本来也没有产出。
"""

from calendar import monthrange
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import holidays
from .config import DEFAULT_MONTHLY_SCHEDULE, DEFAULT_WEEKLY_SCHEDULE

#: 向后找候选目标日的窗口(天)。月报最多顺延到下一次目标日, 45 天足够覆盖月末配置。
_FWD_DAYS = 45
#: 向前回看的窗口(天)。最长顺延(春节连休)不超过 10 天, 回看同等长度足以找到
#: "今天是不是某次顺延后的生效日"。
_BACK_DAYS = 10

KIND_LABELS = {"weekly": "周报", "monthly": "月报"}

_TRUE = ("1", "true", "yes", "on")


def parse_hhmm(text: Any, fallback: str) -> Tuple[int, int]:
    """解析 ``HH:MM``; 任何畸形输入都退回 ``fallback``(不抛异常)。"""
    for candidate in (text, fallback):
        try:
            hh, mm = str(candidate or "").strip().split(":")
            h, m = int(hh), int(mm)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        except (TypeError, ValueError):
            continue
    return 10, 30


def schedule_enabled(cfg: Dict[str, Any], kind: str) -> bool:
    return bool(((cfg or {}).get("schedule") or {}).get(kind, {}).get("enabled", True))


def deferral_enabled(cfg: Dict[str, Any]) -> bool:
    """是否启用"遇周末/节假日顺延到下一个工作日"。默认开启。

    保留开关是为了可覆盖: 顺延的前提是"这套日历是权威的", 若取不到节假日数据(降级为
    仅按周末), 或用户就是想按固定日期发, 都可以关掉。
    """
    section = (cfg or {}).get("schedule") or {}
    if "defer_non_workday" not in section:
        return True
    return str(section.get("defer_non_workday")).strip().lower() in _TRUE


def _month_day(year: int, month: int, raw_day: int) -> int:
    """把配置里的"日"解析成该月实际可用的日 (-1 表示月末)。"""
    last = monthrange(year, month)[1]
    return last if raw_day == -1 else min(max(raw_day, 1), last)


def raw_occurrences(cfg: Dict[str, Any], now: datetime, kind: str,
                    *, back_days: int = _BACK_DAYS, fwd_days: int = _FWD_DAYS) -> List[datetime]:
    """窗口内所有**原始**目标时刻(尚未顺延)。

    用逐日扫描而不是"加法推算": 月末(-1)与闰年/大小月都能自然处理, 也不会因为某次
    顺延而错位。
    """
    if kind not in KIND_LABELS or not schedule_enabled(cfg, kind):
        return []
    sched = (cfg.get("schedule") or {}).get(kind) or {}
    fallback = (DEFAULT_WEEKLY_SCHEDULE if kind == "weekly" else DEFAULT_MONTHLY_SCHEDULE)["time"]
    h, m = parse_hhmm(sched.get("time"), fallback)

    if kind == "weekly":
        try:
            dow = int(sched.get("day_of_week", DEFAULT_WEEKLY_SCHEDULE["day_of_week"]))
        except (TypeError, ValueError):
            dow = DEFAULT_WEEKLY_SCHEDULE["day_of_week"]
    else:
        try:
            raw_day = int(sched.get("day_of_month", DEFAULT_MONTHLY_SCHEDULE["day_of_month"]))
        except (TypeError, ValueError):
            raw_day = DEFAULT_MONTHLY_SCHEDULE["day_of_month"]

    start = (now - timedelta(days=back_days)).date()
    out: List[datetime] = []
    for i in range(0, back_days + fwd_days + 1):
        d = start + timedelta(days=i)
        if kind == "weekly":
            if d.weekday() != dow:
                continue
        else:
            if d.day != _month_day(d.year, d.month, raw_day):
                continue
        out.append(datetime.combine(d, dtime(h, m)))
    return out


def defer(dt: datetime, *, enabled: bool = True) -> Tuple[datetime, str]:
    """把目标时刻顺延到下一个工作日。返回 ``(生效时刻, 顺延原因)``。

    当天就是工作日时原样返回、原因为空字符串。
    """
    if not enabled:
        return dt, ""
    d = dt.date()
    cal = holidays.calendar_for(d.year)
    if cal.is_workday(d):
        return dt, ""
    nxt = cal.next_workday(d, include_self=False)
    reason = "%s 是%s" % (d.isoformat(), cal.describe(d))
    if not cal.authoritative:
        reason += "(未取到放假安排, 仅按周末判断)"
    return datetime.combine(nxt, dt.time()), reason


def occurrences(cfg: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    """窗口内所有目标: 原始时刻 + 顺延后的生效时刻 + 原因。

    **按 (类型, 生效时刻) 去重**: 春节那种整周连休会让相邻的两次目标(如 02-16 与 02-23
    两个周一)顺延到**同一天**(02-24), 不去重就会在提醒里把"周报"列两遍。同一格里保留
    **最早的**原始目标 —— 它是第一个被顺延的安排, 用来解释原因最自然。
    """
    enabled = deferral_enabled(cfg)
    merged: Dict[Tuple[str, datetime], Dict[str, Any]] = {}
    for kind in KIND_LABELS:
        for raw in raw_occurrences(cfg, now, kind):
            eff, reason = defer(raw, enabled=enabled)
            key = (kind, eff)
            entry = merged.get(key)
            if entry is None:
                merged[key] = {
                    "kind": kind,
                    "label": KIND_LABELS[kind],
                    "raw": raw,
                    "effective": eff,
                    "deferred": eff != raw,
                    "reason": reason,
                    "also_from": [],
                }
            else:
                entry["also_from"].append(raw)
    return sorted(merged.values(), key=lambda x: x["effective"])


def next_occurrence(cfg: Dict[str, Any], now: datetime, kind: str) -> Optional[datetime]:
    """下一次该类型的**生效**推送时刻(已顺延); 未启用或无候选时返回 ``None``。

    与 ``reminders`` / 守护进程共用, 保证"提醒哪一天"与"实际哪一天推"永远一致。
    """
    for occ in occurrences(cfg, now):
        if occ["kind"] == kind and occ["effective"] >= now:
            return occ["effective"]
    return None


def next_effective_by_kind(cfg: Dict[str, Any], now: datetime) -> Dict[str, datetime]:
    """``{类型: 下一次生效时刻}``, 同样已顺延。"""
    out: Dict[str, datetime] = {}
    for occ in occurrences(cfg, now):
        if occ["effective"] >= now and occ["kind"] not in out:
            out[occ["kind"]] = occ["effective"]
    return out


def effective_on(cfg: Dict[str, Any], day: date) -> List[Dict[str, Any]]:
    """``day`` 这一天实际要推送的全部目标(已顺延)。"""
    probe = datetime.combine(day, dtime(0, 0))
    return [o for o in occurrences(cfg, probe) if o["effective"].date() == day]


def push_due_now(cfg: Dict[str, Any], now: datetime, kind: str) -> Tuple[bool, str]:
    """此刻是否该发这一类推送。返回 ``(是否该发, 顺延说明)``。

    命中条件: **顺延后**的生效日就是今天, 且当前分钟等于配置时间。不要求"正好那一秒",
    守护进程每 5 秒滴答一次, 会在那一分钟内命中。
    """
    for occ in effective_on(cfg, now.date()):
        if occ["kind"] != kind:
            continue
        eff: datetime = occ["effective"]
        if (now.hour, now.minute) != (eff.hour, eff.minute):
            continue
        why = ""
        if occ["deferred"]:
            why = "%s 原定 %s 推送, 因%s顺延到 %s" % (
                KIND_LABELS[kind], occ["raw"].strftime("%Y-%m-%d"),
                occ["reason"], eff.strftime("%Y-%m-%d"))
            if occ.get("also_from"):
                why += "(同期另 %d 次安排一并顺延到此日)" % len(occ["also_from"])
        return True, why
    return False, ""


def describe_deferral(cfg: Dict[str, Any], now: datetime, kind: str) -> str:
    """给日志/展示用的一句话: 下一次推送的时间与是否顺延。"""
    for occ in occurrences(cfg, now):
        if occ["kind"] != kind or occ["effective"] < now:
            continue
        text = "%s %s" % (KIND_LABELS[kind], occ["effective"].strftime("%Y-%m-%d %H:%M"))
        if occ["deferred"]:
            text += "(原定 %s, 因%s顺延)" % (occ["raw"].strftime("%Y-%m-%d"), occ["reason"])
        return text
    return "%s 未启用" % KIND_LABELS.get(kind, kind)
