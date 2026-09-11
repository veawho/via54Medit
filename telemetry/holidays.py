"""中国大陆法定节假日日历 —— 用来判断某一天是不是「工作日」。

为什么需要它
------------
推送是**到点触发**的: 守护进程必须在目标时刻正在运行(机器开着、没休眠), 否则那一次
周报/月报就静默丢失, 而且不会有任何报错。所以要在推送日的**前一个工作日**提醒用户
别关机 —— 而"前一个工作日"不能只按周末推算:

* 春节/国庆连休会让"前一天"本身是假期(2026 年国庆从 10-01 放到 10-07);
* 调休补班又会让某个周六变成工作日(2026 年 09-20 周日、10-10 周六都要上班)。

不查法定节假日安排, 提醒就会提醒错日子。

数据来源与权威性
----------------
主源 `holiday-cn <https://github.com/NateScarlet/holiday-cn>`_: 机器可读, 且**逐条标注
对应的国务院办公厅公告链接**。例如 2026 年的 ``papers`` 指向
《国务院办公厅关于2026年部分节假日安排的通知》(国办发明电〔2025〕7 号)
https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm —— 已逐条核对一致
(含 09-20、10-10 两个补班日)。

备源 ``timor.tech`` 的年度接口(同样的放假/补班数据), 主源不可达时使用。

取不到数据时**如实降级**, 不装作有数据
--------------------------------------
退化为"仅按周末判断", 并把 ``authoritative=False`` 传给调用方。年份尚未公布(例如
2027 年的安排要到 2026 年 11 月左右才发布)也走这条路径。调用方据此提示用户,
而不是拿一个可能把补班日算成休息日的日历当真。
"""

import json
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

#: 节假日数据缓存目录 (与 ~/.medit 下其它状态文件一致)
HOLIDAY_DIR = os.path.expanduser(os.path.join("~", ".medit", "holidays"))

#: 取到有效数据后的缓存有效期(天)。放假安排在一年内不会变, 可以缓存久一点。
CACHE_DAYS_OK = 30

#: "该年暂无数据"的缓存有效期(天)。短一些: 安排通常在 11 月前后公布, 要能自动补上。
CACHE_DAYS_MISSING = 3

FETCH_TIMEOUT = 10

#: 主源: holiday-cn (标注了国务院公告原文)
_SRC_HOLIDAY_CN = "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
#: 备源: timor.tech
_SRC_TIMOR = "https://timor.tech/api/holiday/year/{year}"

_UA = "via54Medit-telemetry/1.0 (+holiday calendar)"


@dataclass
class HolidayCalendar:
    """某一年的放假与补班安排。"""

    year: int
    #: "2026-10-01" -> "国庆节"
    off_days: Dict[str, str] = field(default_factory=dict)
    #: "2026-09-20" -> "国庆节前补班" (调休上班的周末)
    work_days: Dict[str, str] = field(default_factory=dict)
    source: str = "weekend-only"
    #: 数据是否来自权威来源(holiday-cn / timor)。False 表示只能按周末推算。
    authoritative: bool = False
    papers: List[str] = field(default_factory=list)
    fetched_at: str = ""
    note: str = ""

    # ---- 查询 ----

    def is_off(self, d: date) -> bool:
        """法定放假(含调休放假)。"""
        return d.isoformat() in self.off_days

    def is_makeup_workday(self, d: date) -> bool:
        """调休补班(周末但要上班)。"""
        return d.isoformat() in self.work_days

    def is_workday(self, d: date) -> bool:
        """是否工作日。

        规则: 调休补班 > 法定放假 > 周末。数据不权威时退化为"仅按周末判断"。
        """
        if self.is_makeup_workday(d):
            return True
        if self.is_off(d):
            return False
        return d.weekday() < 5

    def describe(self, d: date) -> str:
        """这一天的性质, 用于日志与提醒正文。"""
        if self.is_makeup_workday(d):
            return "调休补班日(%s)" % self.work_days[d.isoformat()]
        if self.is_off(d):
            return "法定假期(%s)" % self.off_days[d.isoformat()]
        if d.weekday() >= 5:
            return "周末"
        return "工作日"

    def previous_workday(self, d: date, *, include_self: bool = False) -> date:
        """``d`` 之前最近的一个工作日。

        ``include_self=True`` 时 ``d`` 本身是工作日就返回 ``d``。
        最多回看 30 天(足够跨过春节/国庆连休), 再找不到就原样返回 ``d`` ——
        宁可给一个可能不准的日期, 也不要在这里无限循环。
        """
        cur = d if include_self else d - timedelta(days=1)
        for _ in range(30):
            cal = calendar_for(cur.year)
            if cal.is_workday(cur):
                return cur
            cur -= timedelta(days=1)
        return d

    def next_workday(self, d: date, *, include_self: bool = False) -> date:
        """``d`` 之后最近的一个工作日(对称实现, 供提醒文案与测试使用)。"""
        cur = d if include_self else d + timedelta(days=1)
        for _ in range(30):
            cal = calendar_for(cur.year)
            if cal.is_workday(cur):
                return cur
            cur += timedelta(days=1)
        return d


# --------------------------------------------------------------------------- #
# 缓存
# --------------------------------------------------------------------------- #
def _cache_path(year: int) -> str:
    return os.path.join(HOLIDAY_DIR, "%d.json" % year)


def _read_cache(year: int) -> Optional[Dict[str, Any]]:
    try:
        with open(_cache_path(year), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_cache(year: int, payload: Dict[str, Any]):
    """写缓存。失败静默 —— 缓存只是省一次网络请求, 不该影响主流程。"""
    try:
        os.makedirs(HOLIDAY_DIR, exist_ok=True)
        tmp = _cache_path(year) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _cache_path(year))
    except OSError:
        pass


def _cache_age_days(entry: Dict[str, Any]) -> float:
    try:
        stamp = datetime.fromisoformat(str(entry.get("fetched_at") or ""))
    except (TypeError, ValueError):
        return 1e9
    return (datetime.now() - stamp).total_seconds() / 86400.0


# --------------------------------------------------------------------------- #
# 取数
# --------------------------------------------------------------------------- #
def _http_json(url: str) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:                                       # noqa: BLE001
        return None


def _fetch_holiday_cn(year: int) -> Optional[Dict[str, Any]]:
    """主源。返回 ``{"off_days":..., "work_days":..., "papers":[...]}``。"""
    data = _http_json(_SRC_HOLIDAY_CN.format(year=year))
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        return None
    off, work = {}, {}
    for day in data["days"]:
        if not isinstance(day, dict):
            continue
        ds = str(day.get("date") or "")
        name = str(day.get("name") or "").strip()
        if len(ds) != 10:
            continue
        if day.get("isOffDay"):
            off[ds] = name or "法定假期"
        else:
            work[ds] = (name + "后补班") if name else "调休补班"
    if not off:
        return None
    papers = [str(p) for p in (data.get("papers") or []) if p]
    return {"off_days": off, "work_days": work, "papers": papers,
            "source": "holiday-cn", "note": "数据来自 holiday-cn, 逐条标注国务院公告原文"}


def _fetch_timor(year: int) -> Optional[Dict[str, Any]]:
    """备源。``holiday`` 是以 "MM-DD" 为键的字典。"""
    data = _http_json(_SRC_TIMOR.format(year=year))
    if not isinstance(data, dict) or data.get("code") != 0:
        return None
    table = data.get("holiday")
    if not isinstance(table, dict):
        return None
    off, work = {}, {}
    for key, item in table.items():
        if not isinstance(item, dict):
            continue
        ds = str(item.get("date") or key)
        if len(ds) == 5:                                    # "10-01" -> "2026-10-01"
            ds = "%d-%s" % (year, ds)
        if len(ds) != 10:
            continue
        name = str(item.get("name") or "").strip()
        if item.get("holiday"):
            off[ds] = name or "法定假期"
        else:
            work[ds] = name or "调休补班"
    if not off:
        return None
    return {"off_days": off, "work_days": work, "papers": [],
            "source": "timor.tech", "note": "数据来自 timor.tech 年度接口"}


def _weekend_only(year: int, note: str) -> HolidayCalendar:
    return HolidayCalendar(year=year, source="weekend-only", authoritative=False,
                           note=note, fetched_at=datetime.now().isoformat(timespec="seconds"))


def load_calendar(year: int, *, allow_fetch: bool = True, force: bool = False) -> HolidayCalendar:
    """取某一年的日历。**永不抛异常**, 取不到就如实降级为"仅按周末判断"。

    缓存策略: 有效数据缓存 30 天; "该年暂无数据" 只缓存 3 天 —— 安排通常 11 月前后
    公布, 短缓存能让它自动补上, 不必手工清缓存。
    """
    entry = None if force else _read_cache(year)
    if entry:
        age = _cache_age_days(entry)
        ttl = CACHE_DAYS_MISSING if entry.get("missing") else CACHE_DAYS_OK
        if age <= ttl:
            if entry.get("missing"):
                return _weekend_only(year, entry.get("note") or "该年度安排尚未公布")
            return HolidayCalendar(
                year=year,
                off_days=entry.get("off_days") or {},
                work_days=entry.get("work_days") or {},
                source=entry.get("source") or "cache",
                authoritative=True,
                papers=entry.get("papers") or [],
                fetched_at=entry.get("fetched_at") or "",
                note="%s (本地缓存)" % (entry.get("note") or ""),
            )

    if not allow_fetch:
        if entry and not entry.get("missing"):
            return HolidayCalendar(year=year, off_days=entry.get("off_days") or {},
                                   work_days=entry.get("work_days") or {},
                                   source=entry.get("source") or "cache", authoritative=True,
                                   papers=entry.get("papers") or [],
                                   fetched_at=entry.get("fetched_at") or "",
                                   note="离线: 使用本地缓存")
        return _weekend_only(year, "离线且无缓存, 仅按周末判断")

    for fetcher in (_fetch_holiday_cn, _fetch_timor):
        got = None
        try:
            got = fetcher(year)
        except Exception:                                   # noqa: BLE001
            got = None
        if got:
            payload = dict(got, year=year, missing=False,
                           fetched_at=datetime.now().isoformat(timespec="seconds"))
            _write_cache(year, payload)
            return HolidayCalendar(year=year, off_days=got["off_days"], work_days=got["work_days"],
                                   source=got["source"], authoritative=True, papers=got["papers"],
                                   fetched_at=payload["fetched_at"], note=got["note"])

    note = "%d 年放假安排尚未公布或数据源不可达, 仅按周末判断" % year
    _write_cache(year, {"year": year, "missing": True, "note": note,
                        "fetched_at": datetime.now().isoformat(timespec="seconds")})
    if entry and not entry.get("missing"):
        # 这次没取到, 但手里有旧数据 —— 旧的比"没有"强, 但要标明可能过期
        return HolidayCalendar(year=year, off_days=entry.get("off_days") or {},
                               work_days=entry.get("work_days") or {},
                               source=entry.get("source") or "cache", authoritative=True,
                               papers=entry.get("papers") or [],
                               fetched_at=entry.get("fetched_at") or "",
                               note="本次取数失败, 使用可能过期的本地缓存")
    return _weekend_only(year, note)


#: 进程内日历缓存: 判断一个日期要先知道它属于哪一年, 逐次读盘没有意义。
_CAL_CACHE: Dict[int, HolidayCalendar] = {}


def calendar_for(year: int, *, allow_fetch: bool = True, force: bool = False) -> HolidayCalendar:
    if force or year not in _CAL_CACHE or (allow_fetch and not _CAL_CACHE[year].authoritative):
        _CAL_CACHE[year] = load_calendar(year, allow_fetch=allow_fetch, force=force)
    return _CAL_CACHE[year]


def reset_cache():
    """清掉进程内日历缓存 (测试用, 免得用例之间互相污染)。"""
    _CAL_CACHE.clear()


def is_workday(d: date) -> bool:
    return calendar_for(d.year).is_workday(d)


def previous_workday(d: date, *, include_self: bool = False) -> date:
    return calendar_for(d.year).previous_workday(d, include_self=include_self)


def workday_status(d: date) -> Tuple[bool, str]:
    """``(是否工作日, 说明)`` —— 说明里会带上"数据是否权威"。"""
    cal = calendar_for(d.year)
    text = cal.describe(d)
    if not cal.authoritative:
        text += "（按周末推算, 未取到 %d 年放假安排）" % d.year
    return cal.is_workday(d), text


def clear_cache(year: Optional[int] = None) -> List[str]:
    """删除磁盘缓存, 返回被删掉的文件列表。"""
    reset_cache()
    removed: List[str] = []
    years = [year] if year else list(range(2020, date.today().year + 3))
    for y in years:
        path = _cache_path(y)
        if os.path.exists(path):
            try:
                os.remove(path)
                removed.append(path)
            except OSError:
                pass
    return removed


def cache_status(year: Optional[int] = None) -> Dict[str, Any]:
    """当前日历状态, 供 ``holiday --status`` 与文档展示。"""
    year = year or date.today().year
    cal = calendar_for(year, allow_fetch=False)
    entry = _read_cache(year) or {}
    return {
        "year": year,
        "source": cal.source,
        "authoritative": cal.authoritative,
        "off_days": len(cal.off_days),
        "work_days": len(cal.work_days),
        "papers": cal.papers,
        "note": cal.note,
        "cache_dir": HOLIDAY_DIR,
        "cached": bool(entry),
        "cache_age_days": round(_cache_age_days(entry), 1) if entry else None,
    }
