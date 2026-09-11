"""
Feishu Bitable (多维表格 / Base) integration module.
Manages automatic Base creation, table schema setup (见 TABLE_SCHEMA_FIELDS), multi-user weekly record syncing (with upsert idempotency),
and data retrieval for automated chart reports.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .config import CONFIG_FILE_PATH, load_config, save_config
from .csv_migrate import migrate_header
from .models import AggregateReport

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# Bitable field types
# 1: Text, 2: Number, 3: SingleSelect, 5: DateTime
TABLE_SCHEMA_FIELDS = [
    {"field_name": "汇报周期", "type": 1},  # 主字段文本
    {"field_name": "成员花名", "type": 1},
    {"field_name": "成员OpenID", "type": 1},
    {"field_name": "上报时间", "type": 5},
    {"field_name": "文献检索篇数", "type": 2},
    {"field_name": "检索节约工时(h)", "type": 2},
    {"field_name": "文献下载篇数", "type": 2},
    {"field_name": "下载节约工时(h)", "type": 2},
    {"field_name": "Highlight阅读页数", "type": 2},
    {"field_name": "Highlight标注篇数", "type": 2},
    {"field_name": "高亮节约工时(h)", "type": 2},
    {"field_name": "总节约工时(h)", "type": 2},
    # ↓ 其他类目: 与三类一样统计**实际工时**与 **Token 消耗**;
    #   不产出"节约工时" —— 该类目没有人工基准, 不编造。
    {"field_name": "其他任务数", "type": 2},
    {"field_name": "其他工作时长(h)", "type": 2},
    {"field_name": "其他Token消耗", "type": 2},
    # 其他Token消耗 的子集(没有 task_id 归属的那部分)。单列出来才能分辨
    # "确实是其他工作"与"调用方忘了标归属" —— 否则这个数字没法解读。
    {"field_name": "其他未归属Token", "type": 2},
    {"field_name": "真实Token消耗", "type": 2},
    {"field_name": "API调用次数", "type": 2},
    {"field_name": "上报状态", "type": 3, "property": {
        "options": [
            {"name": "🟢 自动同步"},
            {"name": "🟡 补登修正"},
            {"name": "⚪ 待核验"}
        ]
    }}
]


# ---------------------------------------------------------------------------
# 目标表 schema 适配层
#
# 本模块既能创建并使用「自建标准表」(15 字段, 见上方 TABLE_SCHEMA_FIELDS),
# 也能接入公司既有的「监控数据周报明细」表 (13 字段, 命名与标准表完全不同)。
# 因此在读写边界做一次双向映射, 使上层 (chart_reporter / daemon) 无需感知差异:
#   写入: 标准字段名 -> 目标表字段名
#   读取: 目标表字段名 -> 标准字段名
# ---------------------------------------------------------------------------

SCHEMA_STANDARD = "standard"   # 本模块自建表
SCHEMA_COMPANY = "company"     # 公司既有「监控数据周报明细」表

STANDARD_STATUS_VALUE = "🟢 自动同步"
COMPANY_STATUS_VALUE = "已自动同步"

# 公司既有表实际拥有的字段 = 原有 13 列 + v5.4.43 补齐的 8 个统计列。
# 补齐前只有前 13 个, 于是"其他"三列与三个细分工时在**写入时被静默丢弃**,
# 只能挤进「备注说明」当一段纯文本 —— 看得到, 但没法筛选、分组、画图。
COMPANY_TABLE_FIELDS = {
    "记录标识", "统计周次", "提交成员", "统计日期",
    "文献检索量", "成功下载量", "高亮标注量", "解析物理总页数",
    "节省工时(小时)", "Token消耗量", "项目任务类型", "数据状态", "备注说明",
    # ↓ v5.4.43 补齐的统计列 (与标准表同名, 映射即恒等)
    "检索节约工时(h)", "下载节约工时(h)", "高亮节约工时(h)",
    "其他任务数", "其他工作时长(h)", "其他Token消耗", "其他未归属Token",
    "API调用次数",
}

# 标准字段名 -> 公司表字段名。
#
# 对齐契约: **标准表里的每个字段, 要么在这里有同义列, 要么在
# ``INTENTIONALLY_NOT_A_COLUMN`` 里写明为什么不该有列**。没有第三种状态 ——
# "静默丢弃"正是"统计列没对齐最新的统计数据项"的成因, 也最难被发现。
COMPANY_FIELD_MAP: Dict[str, str] = {
    "记录标识": "记录标识",
    "汇报周期": "统计周次",
    "成员花名": "提交成员",
    "上报时间": "统计日期",
    "文献检索篇数": "文献检索量",
    "文献下载篇数": "成功下载量",
    "Highlight标注篇数": "高亮标注量",
    "Highlight阅读页数": "解析物理总页数",
    "总节约工时(h)": "节省工时(小时)",
    "真实Token消耗": "Token消耗量",
    "项目任务类型": "项目任务类型",
    "上报状态": "数据状态",
    "备注说明": "备注说明",
    # v5.4.43: 补齐的统计列 —— 在此之前这些值根本没有落点
    "检索节约工时(h)": "检索节约工时(h)",
    "下载节约工时(h)": "下载节约工时(h)",
    "高亮节约工时(h)": "高亮节约工时(h)",
    "其他任务数": "其他任务数",
    "其他工作时长(h)": "其他工作时长(h)",
    "其他Token消耗": "其他Token消耗",
    "其他未归属Token": "其他未归属Token",
    "API调用次数": "API调用次数",
}

#: 刻意**不建列**的标准字段 -> 理由。
#:
#: 对齐契约只有两种合法状态: 目标表里有同名列, 或者在这里写明理由。
#: 这张表是**显式的决策记录**, 不是"忘了处理"的收容所 —— 加条目必须带理由。
INTENTIONALLY_NOT_A_COLUMN: Dict[str, str] = {
    "成员OpenID": "身份标识而非统计项; 公司表多人可见, 不在共享表里扩散 open_id"
                  "(图表按花名聚合, 不需要它)",
}

# 反向映射: 公司表字段名 -> 标准字段名
STANDARD_FIELD_MAP: Dict[str, str] = {v: k for k, v in COMPANY_FIELD_MAP.items()}

# 本地备份 CSV 的固定列序。备份始终以「标准字段名」落盘, 与目标表是哪一种
# schema 无关 —— 否则同一份 CSV 会混入两种列语义, 表头错位后无法回读。
BACKUP_FIELDS: List[str] = [f["field_name"] for f in TABLE_SCHEMA_FIELDS]

# 公司表 payload 的写入列序, 即当前映射的取值顺序。
# 由 COMPANY_FIELD_MAP 的取值顺序推导, 与其构造方 build_company_payload 保持一致。
COMPANY_PAYLOAD_ORDER: List[str] = list(COMPANY_FIELD_MAP.values())

#: 历史遗留的 13 列写入顺序 —— **冻结, 不随映射扩展而变**。
#:
#: 本地备份里那些"13 列、按公司列序写入"的历史行, 是靠
#: ``len(row) == len(COMPANY_PAYLOAD_ORDER)`` 认出来的(见 ``_load_local_csv_records``)。
#: 如果把这里跟着 COMPANY_FIELD_MAP 一起变长, 那些行就再也认不出来, 会被当作
#: 无法对齐的脏行**静默丢掉** —— 回退路径上少的就是它们。
COMPANY_PAYLOAD_ORDER_LEGACY: List[str] = [
    "记录标识", "统计周次", "提交成员", "统计日期",
    "文献检索量", "成功下载量", "高亮标注量", "解析物理总页数",
    "节省工时(小时)", "Token消耗量", "项目任务类型", "数据状态", "备注说明",
]

#: 标准字段 -> 飞书字段类型 (用于给目标表补列)
STANDARD_FIELD_TYPES: Dict[str, int] = {
    f["field_name"]: f["type"] for f in TABLE_SCHEMA_FIELDS
}
#: 建列时需要带的 property(目前只有单选)
STANDARD_FIELD_PROPERTIES: Dict[str, Any] = {
    f["field_name"]: f["property"] for f in TABLE_SCHEMA_FIELDS if "property" in f
}


#: 公司表**独有**的标记字段。标准表里不会出现这些名字, 因此它们是识别的可靠依据。
COMPANY_MARKER_FIELDS = {"记录标识", "统计周次", "提交成员", "统计日期"}


def detect_schema_profile(field_names: Optional[Any]) -> str:
    """根据目标表实际字段名推断 schema 类型。

    判据优先看**独有标记字段**: 公司表有 ``记录标识 / 统计周次 / 提交成员 / 统计日期``
    这套命名, 标准表一个都没有。之所以不再单纯比"命中数多少", 是因为 v5.4.43 给公司表
    补上了 8 个与标准表**同名**的统计列 —— 两边名字开始交叠, 谁多谁少的比较会越来越
    脆弱(公司表 21 列里已经有 8 列与标准表同名)。标记字段不会交叠, 所以它是稳的。

    命中数比较作为兜底保留: 供既没有标记字段、又确实是标准表的历史表使用。
    识别不出时返回空串。
    """
    names = set(field_names or [])
    if not names:
        return ""
    if len(names & COMPANY_MARKER_FIELDS) >= 2:
        return SCHEMA_COMPANY
    standard_names = {f["field_name"] for f in TABLE_SCHEMA_FIELDS}
    standard_hits = len(names & standard_names)
    company_hits = len(names & COMPANY_TABLE_FIELDS)
    if max(standard_hits, company_hits) < 3:
        return ""
    return SCHEMA_COMPANY if company_hits > standard_hits else SCHEMA_STANDARD


def unmapped_standard_fields() -> List[str]:
    """既没有同义列、也没有写明理由的标准字段。

    **应该永远是空列表**。非空就意味着某个统计项正在被静默丢弃 —— 那正是
    "统计列没有对齐最新的统计数据项"的成因, 所以它由测试守着(见
    ``tests/test_telemetry.py::TestBitableColumnAlignment``)。
    """
    return [f["field_name"] for f in TABLE_SCHEMA_FIELDS
            if f["field_name"] not in COMPANY_FIELD_MAP
            and f["field_name"] not in INTENTIONALLY_NOT_A_COLUMN]


def intended_target_columns(schema: str = SCHEMA_STANDARD) -> List[str]:
    """某个 schema 下, 每个标准字段**应该**落在哪一列。

    标准表用同名; 公司表用 ``COMPANY_FIELD_MAP`` 的映射名。刻意不建列的字段不出现在这里。
    """
    if schema == SCHEMA_COMPANY:
        return list(COMPANY_FIELD_MAP.values())
    return [f["field_name"] for f in TABLE_SCHEMA_FIELDS]


def missing_target_columns(field_names: Optional[Any],
                           schema: str = SCHEMA_STANDARD) -> List[str]:
    """目标表里**缺哪些统计列**。返回目标表视角的列名。

    只报"应该有的统计列", 不含刻意不建列的字段(见 ``INTENTIONALLY_NOT_A_COLUMN``)。
    """
    names = set(field_names or [])
    if not names:
        return []
    return [c for c in intended_target_columns(schema) if c not in names]


def week_label(report: AggregateReport) -> str:
    """把报告周期规整成公司表「统计周次」的写法, 如 2026-W37 / 2026-09 / 历史累计。"""
    ptype = getattr(report, "period_type", "") or ""
    start = (getattr(report, "start_date", "") or "")[:10]
    if ptype == "all_time":
        return "历史累计"
    if ptype == "monthly" and len(start) >= 7:
        return start[:7]
    try:
        iso = datetime.strptime(start, "%Y-%m-%d").isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        return report.period_name


def _period_start_ms(report: AggregateReport) -> int:
    """周期起始日 (当周周一 / 当月 1 日) 00:00 +08:00 的毫秒时间戳。

    实测该表 datetime 字段只接受毫秒时间戳: ISO 字符串无论带不带毫秒、带不带时区,
    均返回 1254064 DatetimeFieldConvFail。
    """
    start = (getattr(report, "start_date", "") or "")[:10]
    try:
        dt = datetime.strptime(start, "%Y-%m-%d").replace(
            tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        # 兜底也必须带 +08:00: 裸 datetime.now() 会按机器本地时区解释,
        # 在东八区以外的机器上会偏移出一整天。
        dt = datetime.now(timezone(timedelta(hours=8))).replace(
            hour=0, minute=0, second=0, microsecond=0)
    return int(dt.timestamp() * 1000)



class FeishuBitableManager:
    def __init__(self, config: Optional[dict] = None, tenant_token: Optional[str] = None):
        self._cfg = config if isinstance(config, dict) else load_config()
        self.app_id = self._cfg.get("feishu", {}).get("app_id", "")
        self.app_secret = self._cfg.get("feishu", {}).get("app_secret", "")
        self._cached_token = tenant_token
        self.app_token = self._cfg.get("feishu", {}).get("company_bitable_token", "")
        self.table_id = self._cfg.get("feishu", {}).get("company_bitable_table_id", "")
        self.bitable_url = self._cfg.get("feishu", {}).get("company_bitable_url", "")

    def get_tenant_token(self) -> str:
        """获取飞书租户 tenant_access_token。"""
        if self._cached_token:
            return self._cached_token
        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        payload = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    self._cached_token = data.get("tenant_access_token", "")
                    return self._cached_token
                raise RuntimeError(f"获取租户 Token 失败: {data}")
        except Exception as e:
            raise RuntimeError(f"飞书鉴权接口连接异常: {e}")

    def _api_request(self, endpoint: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """封装标准飞书 OpenAPI 请求。"""
        try:
            tok = self.get_tenant_token()
        except Exception as e:
            return {"code": -1, "msg": str(e)}
        url = f"{FEISHU_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8"
        }
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw_err = e.read().decode("utf-8", errors="replace")
            try:
                err_data = json.loads(raw_err)
            except Exception:
                err_data = {"code": e.code, "msg": raw_err}
            return err_data
        except Exception as e:
            return {"code": -1, "msg": str(e)}

    def create_bitable_app(self, name: str = "TraeWork团队文献整理AI监控看板") -> Tuple[bool, Dict[str, Any]]:
        """在飞书云端新建多维表格 (Bitable Base)。"""
        payload = {"name": name}
        res = self._api_request("/bitable/v1/apps", method="POST", body=payload)
        code = res.get("code", -1)

        if code == 0:
            app_info = res.get("data", {}).get("app", {})
            self.app_token = app_info.get("app_token", "")
            self.table_id = app_info.get("default_table_id", "")
            self.bitable_url = app_info.get("url", f"https://feishu.cn/base/{self.app_token}")

            # 保存至本地配置
            self._cfg["feishu"]["company_bitable_token"] = self.app_token
            self._cfg["feishu"]["company_bitable_table_id"] = self.table_id
            self._cfg["feishu"]["company_bitable_url"] = self.bitable_url
            save_config(self._cfg)

            # 初始化数据表字段与视图
            self.init_table_fields(self.app_token, self.table_id)
            self.init_table_views(self.app_token, self.table_id)

            return True, {
                "app_token": self.app_token,
                "table_id": self.table_id,
                "url": self.bitable_url,
                "msg": f"成功在飞书云端新建多维表格《{name}》！"
            }
        elif code == 99991672:
            auth_url = f"https://open.feishu.cn/app/{self.app_id}/auth?q=bitable:app,base:app:create&op_from=openapi&token_type=tenant" if self.app_id else "https://open.feishu.cn/app"
            return False, {
                "code": code,
                "auth_url": auth_url,
                "msg": (
                    "当前应用尚未开通飞书【多维表格 (bitable:app)】权限。\n"
                    f"👉 请点击官方链接一键开通: {auth_url}\n"
                    "开通后重新运行即可直接创建，或手动在飞书新建多维表格后将链接绑定至本工具。"
                )
            }
        else:
            return False, {
                "code": code,
                "msg": f"创建多维表格失败: {res.get('msg', '未知错误')}"
            }

    def bind_existing_bitable(self, token_or_url: str) -> Tuple[bool, str]:
        """绑定已有飞书多维表格（通过 URL 或 Token），并自动初始化字段与配置。"""
        raw = token_or_url.strip()
        app_token = raw
        if "base/" in raw:
            parts = raw.split("base/")[-1].split("?")[0].split("/")
            app_token = parts[0]

        if not app_token.startswith("bascn") and len(app_token) < 10:
            return False, f"无法识别的多维表格 Token: '{token_or_url}'。正确格式为以 'bascn' 开头的标识符或飞书链接。"

        self.app_token = app_token
        self.bitable_url = f"https://feishu.cn/base/{self.app_token}"

        # 获取默认 table_id
        res = self._api_request(f"/bitable/v1/apps/{self.app_token}/tables")
        if res.get("code") == 0:
            tables = res.get("data", {}).get("items", [])
            if tables:
                self.table_id = tables[0].get("table_id", "")
        else:
            # 尝试直接查询 app 信息
            info_res = self._api_request(f"/bitable/v1/apps/{self.app_token}")
            if info_res.get("code") == 0:
                self.table_id = info_res.get("data", {}).get("app", {}).get("default_table_id", "")

        self._cfg["feishu"]["company_bitable_token"] = self.app_token
        if self.table_id:
            self._cfg["feishu"]["company_bitable_table_id"] = self.table_id
        self._cfg["feishu"]["company_bitable_url"] = self.bitable_url
        save_config(self._cfg)

        # 尝试初始化字段。
        # 注意: 这里必须按**探测出来的 schema** 补列, 不能假定是标准表 ——
        # 绑定的若是公司既有表, 按标准表补列会往公司表里塞一批"汇报周期/成员花名"
        # 之类用不上的同义列, 而真正缺的统计列反而没补上。
        if self.table_id:
            schema, reason = self.resolve_schema()
            created = self.ensure_table_columns(self.app_token, self.table_id, schema)
            align = self.column_alignment()
            tail = ""
            if created:
                tail = f"; 已补齐 {len(created)} 个统计列: {', '.join(created)}"
            if align.get("missing"):
                tail += (f"; ⚠️ 仍有 {len(align['missing'])} 列缺失: "
                         f"{', '.join(align['missing'])}")

        return True, (f"成功绑定多维表格: {self.bitable_url} "
                      f"(Table ID: {self.table_id or '自动识别'})"
                      + (f" | schema={schema} ({reason}){tail}" if self.table_id else ""))

    def init_table_fields(self, app_token: str, table_id: str) -> List[str]:
        """为**标准表**补齐缺失的统计列, 返回本次新建的列名。"""
        return self.ensure_table_columns(app_token, table_id, SCHEMA_STANDARD)

    def ensure_table_columns(self, app_token: str, table_id: str,
                            schema: str = "", dry_run: bool = False
                            ) -> List[str]:
        """把目标表的**统计列**补齐到与标准字段一致, 返回本次新建的列名。

        这是"统计列对齐"的执行者: 少哪列补哪列。为什么必须有它 —— 表是**先建后用**的,
        代码后来新增统计项(如 v5.4.37 的"其他"三列)不会让已存在的表自动长出列来,
        于是那些值在写入时被静默丢弃, 只能挤进备注当纯文本。实测公司表就这样少了 8 列。

        ``dry_run=True`` 只算不建(用于 ``--dry-run`` 与自检)。
        """
        created: List[str] = []
        if not app_token or not table_id:
            return created
        schema = schema or self.resolve_schema()[0]
        res = self._api_request(
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields?page_size=200")
        if res.get("code") != 0:
            return created
        existing = {i.get("field_name") for i in (res.get("data") or {}).get("items", [])}
        for target in intended_target_columns(schema):
            if target in existing:
                continue
            if dry_run:
                created.append(target)
                continue
            payload: Dict[str, Any] = {
                "field_name": target,
                # 目标表的列名可能是公司表的别名, 类型要按**标准字段名**取
                "type": STANDARD_FIELD_TYPES.get(STANDARD_FIELD_MAP.get(target, target), 2),
            }
            prop = STANDARD_FIELD_PROPERTIES.get(
                STANDARD_FIELD_MAP.get(target, target))
            if prop:
                payload["property"] = prop
            f_res = self._api_request(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                method="POST", body=payload)
            if f_res.get("code") == 0:
                created.append(target)
        return created

    def column_alignment(self) -> Dict[str, Any]:
        """自检: 目标表与"最新统计项"差哪些列。供 CLI 与同步前的告警使用。

        返回 ``{"schema","reason","existing","missing","intentionally_skipped"}``。
        ``missing`` 非空就是"统计列没对齐"的**确证**, 不再靠肉眼比对。
        """
        schema, reason = self.resolve_schema()
        names, err = self.list_table_field_names()
        if names is None:
            return {"schema": schema, "reason": reason, "existing": None,
                    "missing": [], "intentionally_skipped": INTENTIONALLY_NOT_A_COLUMN,
                    "error": err}
        return {
            "schema": schema,
            "reason": reason,
            "existing": sorted(names),
            "missing": missing_target_columns(names, schema),
            "intentionally_skipped": INTENTIONALLY_NOT_A_COLUMN,
            "error": "",
        }

    def init_table_views(self, app_token: str, table_id: str) -> List[str]:
        """初始化表格视图（成员分组视图、每周人效趋势视图）。"""
        views_created = []
        view_defs = [
            {"view_name": "👥 按成员汇总看板", "view_type": "grid"},
            {"view_name": "📅 按周次趋势看板", "view_type": "grid"},
        ]
        for v in view_defs:
            res = self._api_request(f"/bitable/v1/apps/{app_token}/tables/{table_id}/views", method="POST", body=v)
            if res.get("code") == 0:
                views_created.append(v["view_name"])
        return views_created

    # ------------------------------------------------------------------
    # schema 探测与 payload 构造
    # ------------------------------------------------------------------

    def list_table_field_names(self) -> Tuple[Optional[set], str]:
        """读取目标表实际字段名。返回 (字段名集合 | None, 错误信息)。"""
        if not self.app_token or not self.table_id:
            return None, "未绑定多维表格"
        res = self._api_request(
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields?page_size=200"
        )
        if res.get("code") == 0:
            items = (res.get("data") or {}).get("items") or []
            return {i.get("field_name") for i in items if i.get("field_name")}, ""
        return None, str(res.get("msg", ""))

    def resolve_schema(self) -> Tuple[str, str]:
        """确定本次读写的 schema。返回 (schema, 判定依据说明)。"""
        forced = (self._cfg.get("feishu", {}) or {}).get("company_bitable_schema", "") or ""
        if forced in (SCHEMA_STANDARD, SCHEMA_COMPANY):
            return forced, f"由配置指定 ({forced})"
        names, err = self.list_table_field_names()
        if names:
            detected = detect_schema_profile(names)
            if detected:
                return detected, f"自动识别 ({detected}; 表内 {len(names)} 个字段)"
            return SCHEMA_STANDARD, f"字段未匹配已知 schema, 回退标准表 ({len(names)} 个字段)"
        return SCHEMA_STANDARD, f"无法读取字段, 回退标准表 ({err[:80]})"

    def _custom_field_map(self) -> Dict[str, str]:
        raw = (self._cfg.get("feishu", {}) or {}).get("company_bitable_field_map") or {}
        return {k: v for k, v in raw.items() if isinstance(v, str) and v}

    def _field_map(self) -> Dict[str, str]:
        """标准字段名 -> 目标表字段名 的最终映射 (内置映射 + 配置覆盖)。

        写入与「备注保护」必须共用同一份映射: 若只在写入侧应用覆盖, 保护逻辑
        仍按内置名字去 payload 里删除, 改名后的备注列会被覆盖掉。
        """
        field_map = dict(COMPANY_FIELD_MAP)
        field_map.update(self._custom_field_map())
        return field_map

    def _note_field_name(self) -> str:
        """目标表「备注说明」列的实际字段名 (可能被配置改名)。"""
        return self._field_map().get("备注说明", "")

    def build_standard_payload(self, report: AggregateReport, nick: str, oid: str) -> Dict[str, Any]:
        """按本模块自建标准表构造 payload (字段见 TABLE_SCHEMA_FIELDS)。"""
        r = report.to_dict()
        now_ts = int(datetime.now().timestamp() * 1000)
        return {
            "汇报周期": report.period_name,
            "成员花名": nick,
            "成员OpenID": oid,
            "上报时间": now_ts,
            "文献检索篇数": r["retrieval"]["count"],
            "检索节约工时(h)": float(r["retrieval"]["saved_hours"]),
            "文献下载篇数": r["download"]["count"],
            "下载节约工时(h)": float(r["download"]["saved_hours"]),
            "Highlight阅读页数": r["highlight"]["pages"],
            "Highlight标注篇数": r["highlight"]["count"],
            "高亮节约工时(h)": float(r["highlight"]["saved_hours"]),
            "总节约工时(h)": float(r["overall"]["total_saved_hours"]),
            "其他任务数": int(r["other"]["count"]),
            "其他工作时长(h)": float(r["other"]["duration_hours"]),
            "其他Token消耗": int(r["other"]["total_tokens"]),
            "其他未归属Token": int(r["other"].get("unattributed_tokens", 0)),
            "真实Token消耗": int(r["tokens"]["total_tokens"]),
            "API调用次数": int(r["tokens"].get("llm_call_count", 0)),
            "上报状态": STANDARD_STATUS_VALUE,
        }

    def _resolve_member(self, nick: str) -> str:
        """目标表里实际写入的「提交成员」值。

        company_bitable_member 只作为本机用户的显示名映射: 当传入的昵称等于本机
        配置昵称(或为空)时启用, 显式传入的其他成员名不被覆盖, 避免多人场景串号。
        该值同时用于写入与幂等查找, 两处必须一致, 否则会重复新增。
        """
        configured = ((self._cfg.get("feishu", {}) or {}).get("company_bitable_member") or "").strip()
        local = ((self._cfg.get("user", {}) or {}).get("nickname") or "").strip()
        if configured and (not nick or nick == local):
            return configured
        return nick or configured

    def build_company_payload(self, report: AggregateReport, nick: str) -> Dict[str, Any]:
        """按公司既有「监控数据周报明细」表构造 payload。

        先按标准字段名组织, 再经 ``COMPANY_FIELD_MAP`` 转成目标表字段名。
        **统计项一个都不丢**: 每个数值统计项在公司表里都有同名列(v5.4.43 补齐);
        唯一没有列的是 ``成员OpenID``, 理由见 ``INTENTIONALLY_NOT_A_COLUMN``。
        """
        r = report.to_dict()
        feishu = self._cfg.get("feishu", {}) or {}
        project = (feishu.get("company_bitable_project") or "").strip() or "via54Medit"
        member = self._resolve_member(nick)
        week = week_label(report)
        tokens = member.split()
        short = tokens[0] if tokens else ""
        total_hours = float(r["overall"]["total_saved_hours"])
        std: Dict[str, Any] = {
            "记录标识": f"{week}_{short}_{project}" if short else week,
            "汇报周期": week,
            "成员花名": member,
            "上报时间": _period_start_ms(report),
            "文献检索篇数": int(r["retrieval"]["count"]),
            "检索节约工时(h)": float(r["retrieval"]["saved_hours"]),
            "文献下载篇数": int(r["download"]["count"]),
            "下载节约工时(h)": float(r["download"]["saved_hours"]),
            "Highlight标注篇数": int(r["highlight"]["count"]),
            "Highlight阅读页数": int(r["highlight"]["pages"]),
            "高亮节约工时(h)": float(r["highlight"]["saved_hours"]),
            "总节约工时(h)": total_hours,
            # 其他类目: 与三类一样逐项成列, 否则它在这张表里只能是一段备注文本 ——
            # 看得到, 但筛选不了、分组不了、画不了图。
            "其他任务数": int(r["other"]["count"]),
            "其他工作时长(h)": float(r["other"]["duration_hours"]),
            "其他Token消耗": int(r["other"]["total_tokens"]),
            "其他未归属Token": int(r["other"].get("unattributed_tokens", 0)),
            "真实Token消耗": int(r["tokens"]["total_tokens"]),
            "API调用次数": int(r["tokens"].get("llm_call_count", 0)),
            # 单选字段必须写字符串: 传数组会返回 1254062 SingleSelectFieldConvFail
            "项目任务类型": project,
            "上报状态": COMPANY_STATUS_VALUE,
            "备注说明": (
                f"自动同步：检索 {r['retrieval']['count']} 篇 / 下载 {r['download']['count']} 篇 / "
                f"高亮 {r['highlight']['count']} 篇（{r['highlight']['pages']} 页），"
                f"其他 {r['other']['count']} 项，合计节约 {total_hours}h"
            ),
        }
        field_map = self._field_map()
        payload: Dict[str, Any] = {}
        for std_key, value in std.items():
            target = field_map.get(std_key)
            if target:
                payload[target] = value
        return payload

    def _explain_error(self, res: Dict[str, Any]) -> str:
        """把飞书错误码翻译成可操作的提示。"""
        code = res.get("code")
        msg = str(res.get("msg", "未知错误"))
        if code == 99991672:
            auth = (f"https://open.feishu.cn/app/{self.app_id}/auth?q=bitable:app"
                    if self.app_id else "https://open.feishu.cn/app")
            return (
                f"{msg}\n  👉 应用缺少多维表格权限。需在开发者后台开通 bitable:app 并"
                f"【创建版本后发布】(仅勾选不生效), 同时把该应用加为目标 Base 的协作者。"
                f"\n  开通入口: {auth}"
            )
        low = msg.lower()
        if "fieldnamenotfound" in low or "field not found" in low or "fieldname" in low:
            return (
                f"{msg}\n  👉 目标表字段名与写入字段不匹配。可用 "
                f"`medit-telemetry bitable --sync --dry-run` 查看实际 payload, "
                f"再通过配置 company_bitable_schema / company_bitable_field_map 适配。"
            )
        return msg

    def sync_weekly_report(
        self,
        report: AggregateReport,
        nickname: str = "",
        open_id: str = "",
        dry_run: bool = False,
        preserve_note: bool = True,
    ) -> Tuple[bool, str]:
        """
        团队成员每周上传数据至公共多维表格。

        自动识别目标表 schema 并做字段映射, 因此既能写入自建标准表, 也能写入
        公司既有的「监控数据周报明细」表。具有幂等机制: 同一成员、同一周期重复
        上报时更新原记录而非新增, 杜绝脏数据。
        """
        nick = nickname or self._cfg.get("user", {}).get("nickname", "") or "wtg"
        oid = open_id or self._cfg.get("user", {}).get("open_id", "")
        r = report.to_dict()

        if not self.app_token or not self.table_id:
            # 未绑定 -> 新建自建标准表
            ok, res_dict = self.create_bitable_app()
            if not ok:
                return False, f"未绑定多维表格且自动创建受阻: {res_dict.get('msg')}"

        # 1. 确定 schema 并构造 payload
        schema, reason = self.resolve_schema()
        if schema == SCHEMA_COMPANY:
            payload = self.build_company_payload(report, nick)
        else:
            payload = self.build_standard_payload(report, nick, oid)

        # 1b. 列对齐自检: 目标表缺列时**必须说出来**。
        #     缺列 = 那些统计项写不进去, 而且不会有任何报错 —— 正是"统计列没对齐"
        #     最难被发现的地方。这里只报不改: 周期同步去改公司共享表的 schema 太越界,
        #     补列由显式的 `medit-telemetry bitable --align-fields` 执行。
        try:
            align = self.column_alignment()
            missing_cols = align.get("missing") or []
        except Exception:                                       # noqa: BLE001
            missing_cols = []

        if dry_run:
            return True, json.dumps({
                "dry_run": True,
                "schema": schema,
                "schema_reason": reason,
                "app_token": self.app_token,
                "table_id": self.table_id,
                "field_count": len(payload),
                "fields": payload,
                "missing_columns": missing_cols,
                "align_hint": ("目标表缺 %d 列, 这些统计项写不进去; "
                               "运行 `medit-telemetry bitable --align-fields` 补齐: %s"
                               % (len(missing_cols), ", ".join(missing_cols)))
                              if missing_cols else "",
            }, ensure_ascii=False, indent=2)

        # 仅在真正落库后才写本地备份: dry-run 不应产生任何副作用,
        # 否则备份里会留下与最终写入不一致的试探行。
        self._record_local_csv(payload, schema)

        # 2. 幂等检查 (按周期 + 成员)
        existing = self._find_existing_record(report, nick, schema)
        if existing:
            rec_id, rec_fields = existing
            # 保护人工填写的备注: 目标格已有内容时不覆盖
            if schema == SCHEMA_COMPANY and preserve_note:
                note_key = self._note_field_name()
                if note_key and str(rec_fields.get(note_key) or "").strip():
                    payload.pop(note_key, None)
            up_url = (f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}"
                      f"/records/{rec_id}")
            res = self._api_request(up_url, method="PUT", body={"fields": payload})
            if res.get("code") == 0:
                return True, (
                    f"已成功更新本周多维表格数据！(schema={schema} | 花名: {nick} | "
                    f"节约工时: {r['overall']['total_saved_hours']}h | 记录ID: {rec_id})"
                    + self._drift_note(missing_cols)
                )
            return False, f"更新多维表格记录失败: {self._explain_error(res)}"

        # 3. 新增记录
        add_url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        res = self._api_request(add_url, method="POST", body={"fields": payload})
        if res.get("code") == 0:
            rec_id = (res.get("data") or {}).get("record", {}).get("record_id", "")
            return True, (
                f"已成功向团队多维表格同步本周数据！(schema={schema} | 花名: {nick} | "
                f"节约工时: {r['overall']['total_saved_hours']}h | 记录ID: {rec_id})"
                + self._drift_note(missing_cols)
            )
        return False, f"写入多维表格记录失败: {self._explain_error(res)}"

    @staticmethod
    def _drift_note(missing_cols: List[str]) -> str:
        """缺列告警的措辞。**不能只是日志一行** —— 缺列意味着那些统计项在表里不存在,
        而写入不会报错, 所以必须跟着成功消息一起回到调用方(daemon 会把它写进日志/告警)。"""
        if not missing_cols:
            return ""
        return ("\n  ⚠️ 目标表缺 %d 个统计列, 这些项本次**写不进去**: %s\n"
                "     补齐: medit-telemetry bitable --align-fields"
                % (len(missing_cols), ", ".join(missing_cols)))

    def _find_existing_record(
        self, report: AggregateReport, nickname: str, schema: str = SCHEMA_STANDARD
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """按「周期 + 成员」查找已有记录, 返回 (record_id, 原始字段) 或 None。"""
        url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records?page_size=100"
        res = self._api_request(url)
        if res.get("code") != 0:
            return None
        if schema == SCHEMA_COMPANY:
            period_key = COMPANY_FIELD_MAP["汇报周期"]
            member_key = COMPANY_FIELD_MAP["成员花名"]
            period_val = week_label(report)
            # 必须与 build_company_payload 写入的值一致, 否则匹配不上而重复新增
            member_val = self._resolve_member(nickname)
        else:
            period_key, member_key = "汇报周期", "成员花名"
            period_val = report.period_name
            member_val = nickname
        for item in (res.get("data") or {}).get("items", []):
            f = item.get("fields", {}) or {}
            got_member = f.get(member_key)
            if isinstance(got_member, list):
                got_member = got_member[0] if got_member else ""
            if (str(f.get(period_key) or "").strip() == str(period_val).strip()
                    and str(got_member or "").strip() == str(member_val).strip()):
                return item.get("record_id"), f
        return None

    def fetch_team_records(self) -> List[Dict[str, Any]]:
        """从多维表格拉取团队所有成员历史记录, 用于图表与战报汇总。

        两条路径 (在线读取 / 本地备份回退) 都在读取边界统一归一化为标准字段名,
        因此接入公司既有表时 chart_reporter 无需改动, 也不会因表格不可达而拿到
        公司字段名而读空。
        """
        if not self.app_token or not self.table_id:
            return self._load_local_csv_records()

        url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records?page_size=500"
        res = self._api_request(url)
        if res.get("code") == 0:
            schema, _ = self.resolve_schema()
            records = []
            for item in (res.get("data") or {}).get("items", []):
                records.append(self.normalize_record_fields(item.get("fields", {}) or {}, schema))
            return records
        return self._load_local_csv_records()

    @staticmethod
    def normalize_record_fields(fields: Dict[str, Any], schema: str = SCHEMA_COMPANY) -> Dict[str, Any]:
        """读取边界映射: 目标表字段名 -> 标准字段名。"""
        if not fields:
            return {}
        if schema != SCHEMA_COMPANY:
            return dict(fields)
        return {STANDARD_FIELD_MAP.get(k, k): v for k, v in fields.items()}

    @staticmethod
    def _backup_csv_path() -> str:
        """本地备份 CSV 路径。读写两侧共用, 避免路径写死后两边不一致。"""
        return os.path.expanduser(r"~/.medit/team_bitable_backup.csv")

    def _record_local_csv(self, fields: Dict[str, Any], schema: str = SCHEMA_STANDARD):
        """本地零丢失企业双备份。

        无论目标表是哪种 schema, 备份一律以「标准字段名」落盘并以 ``BACKUP_FIELDS``
        为固定列序: 否则同一份 CSV 会混入两种列语义, 表头与实际列错位后无法回读。

        追加前会先把表头对齐到当前 ``BACKUP_FIELDS`` (见 ``csv_migrate``) —— 新增类目
        就是新增列; 新列一律**追加在末尾**, 表头没对齐就写入更宽的行, 回读时会因列数
        不符被当作脏行**静默丢弃** (备份看着还在长, 数据却在丢)。清理逻辑与公共统计表
        共用同一实现, 避免两处规则慢慢分叉。
        """
        std = self.normalize_record_fields(fields, schema)
        row = [std.get(name, "") for name in BACKUP_FIELDS]
        csv_path = self._backup_csv_path()
        try:
            import csv
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            may_append = True
            if os.path.exists(csv_path):
                may_append, _note = migrate_header(csv_path, BACKUP_FIELDS)
            if not may_append:
                # 表头没对齐就继续追加, 正是这个备份开始丢数据的时刻 —— 宁可不写。
                return
            file_exists = os.path.exists(csv_path)
            with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(BACKUP_FIELDS)
                writer.writerow(row)
        except Exception:
            pass

    def _load_local_csv_records(self) -> List[Dict[str, Any]]:
        """读取本地备份, 统一返回「标准字段名」的记录。

        历史版本曾把公司表 schema 的 13 列 payload 直接追加进标准表头的文件,
        造成列错位。这里按列宽识别这类遗留行并按其写入列序还原, 而不是整行丢弃;
        只有完全无法对齐的行才跳过。

        ``COMPANY_PAYLOAD_ORDER_LEGACY`` 是**冻结**的 13 列序 —— 不能跟着
        ``COMPANY_FIELD_MAP`` 一起变长, 否则这些历史行会认不出来被静默丢掉。
        """
        csv_path = self._backup_csv_path()
        if not os.path.exists(csv_path):
            return []
        try:
            import csv
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        except Exception:
            return []
        if not rows:
            return []

        header = [c.strip() for c in rows[0]]
        header_schema = detect_schema_profile(header)
        records: List[Dict[str, Any]] = []
        for raw in rows[1:]:
            if not any(str(c).strip() for c in raw):
                continue
            if len(raw) == len(header):
                row_dict = dict(zip(header, raw))
                records.append(self.normalize_record_fields(row_dict, header_schema))
            elif len(raw) == len(COMPANY_PAYLOAD_ORDER_LEGACY):
                row_dict = dict(zip(COMPANY_PAYLOAD_ORDER_LEGACY, raw))
                records.append(self.normalize_record_fields(row_dict, SCHEMA_COMPANY))
            else:
                # 列数与表头无法对齐, 视为脏行跳过而非猜测
                continue

        # 与在线路径的 upsert 语义对齐: 同一 (周期, 成员) 只保留最后一次写入。
        # 备份是追加写的, 重复运行会留下多份相同记录, 不折叠就会让回退路径
        # 返回重复行、把图表数据放大。
        deduped: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for rec in records:
            key = (str(rec.get("汇报周期") or "").strip(),
                   str(rec.get("成员花名") or "").strip())
            deduped[key] = rec
        return list(deduped.values())
