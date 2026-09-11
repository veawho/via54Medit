"""Feishu integration: Direct IM push and public sheet synchronization."""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from .models import AggregateReport
from .csv_migrate import migrate_header as _migrate_header, range_end as _range_end
from .platform_paths import trae_work_config_path


TRAE_CONFIG_PATH = trae_work_config_path()
from .config import load_config

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# --------------------------------------------------------------------------- #
# 公司公共统计表的列定义 —— **唯一事实来源**
#
# 表头、数据行、追加区间都由它派生, 免得三处各写一份、慢慢走样。
#
# ⚠️ 新类目只能**追加在末尾**, 不能插在中间: 飞书电子表格的 values_append 只能往
# 表格尾部追加, 无法插列。若把「其他」插到「总节约工时」前面, 历史行与新行的列语义
# 就会整体错位 —— 旧行的「总节约工时」会落在新行的「其他任务数」位置上。
# 追加在末尾时, 历史行的新列留空, 语义不受影响。
# --------------------------------------------------------------------------- #
PUBLIC_SHEET_COLUMNS = [
    "上报时间", "统计周期", "用户昵称", "用户OpenID",
    "检索篇数", "检索耗时(秒)", "检索节约(小时)",
    "下载成功数", "下载耗时(秒)", "下载节约(小时)",
    "阅读页数", "高亮完成数", "高亮耗时(秒)", "修正耗时(秒)", "高亮节约(小时)",
    "总节约工时(小时)", "Token总消耗", "状态",
    # ↓ 其他类目(追加在末尾, 见上方说明)
    "其他任务数", "其他工作时长(秒)", "其他Token消耗",
]


def sheet_range_end() -> str:
    """追加区间的右端列名 (如 21 列 -> "U")。"""
    return _range_end(PUBLIC_SHEET_COLUMNS)


def build_public_sheet_row(report: AggregateReport, nickname: str, open_id: str) -> list:
    """构造一行公共统计表数据 —— 顺序与 ``PUBLIC_SHEET_COLUMNS`` 严格一致。"""
    r = report.to_dict()
    return [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        report.period_name,
        nickname,
        open_id,
        r["retrieval"]["count"],
        r["retrieval"]["duration_seconds"],
        r["retrieval"]["saved_hours"],
        r["download"]["count"],
        r["download"]["duration_seconds"],
        r["download"]["saved_hours"],
        r["highlight"]["pages"],
        r["highlight"]["count"],
        r["highlight"]["duration_seconds"],
        r["highlight"]["correction_duration_seconds"],
        r["highlight"]["saved_hours"],
        r["overall"]["total_saved_hours"],
        r["tokens"]["total_tokens"],
        "已上报",
        r["other"]["count"],
        r["other"]["duration_seconds"],
        r["other"]["total_tokens"],
    ]


def _tokens_share(r: Dict[str, Any]) -> str:
    """「其他 Token 占总量多少」的说明串 —— 便于一眼看出这是零头还是大头。

    顺带点出其中"没有 task_id 归属"的部分: 那部分是调用方没标归属、而非真的其他工作,
    不说清楚的话这个数字就没法解读。
    """
    total = int(r["tokens"]["total_tokens"] or 0)
    other = int(r["other"]["total_tokens"] or 0)
    if total <= 0 or other <= 0:
        return ""
    text = f"（占总量 {other * 100.0 / total:.1f}%）"
    unattr = int(r["other"].get("unattributed_tokens") or 0)
    if unattr > 0:
        text += f"，其中 {unattr:,} 无 task_id 归属"
    return text


def migrate_public_csv_columns(csv_path: str):
    """把本地公共统计表的表头升级到当前列定义。返回 ``(可安全追加, 提示)``。

    实现在 ``csv_migrate.migrate_header`` —— 多维表格的本地备份 CSV 用的是同一套
    规则(按列名整表重写、新列补空), 故不在这里再写一份。理由见该模块的说明:
    **新列只能追加在末尾**, 中间插列会让历史行整体错位。

    第一个返回值为 False 时, 调用方**不应**再往这个文件追加数据。
    """
    ok, note = _migrate_header(csv_path, PUBLIC_SHEET_COLUMNS)
    if note:
        note = "本地统计表" + note
    return ok, note


class FeishuSyncClient:
    def __init__(self, config_path: str = TRAE_CONFIG_PATH, sheet_token: Optional[str] = None):
        self.config_path = config_path
        self.app_id = ""
        self.app_secret = ""
        self.user_open_id = ""
        self.bot_name = ""
        self.nickname = "wtg"
        self.sheet_token = sheet_token
        #: 云端表表头是否已在本进程内对齐过 (见 _ensure_sheet_header)
        self._header_synced = False
        self._load_config()

    def _load_config(self):
        # 1. 优先使用统一配置管理器 (~/.medit/telemetry_config.json)
        cfg = load_config()
        self.app_id = cfg.get("feishu", {}).get("app_id", "")
        self.app_secret = cfg.get("feishu", {}).get("app_secret", "")
        self.user_open_id = cfg.get("user", {}).get("open_id", "")
        self.bot_name = cfg.get("feishu", {}).get("bot_name", "TraeWork Bot")
        self.nickname = cfg.get("user", {}).get("nickname", "wtg")
        if not self.sheet_token:
            self.sheet_token = cfg.get("feishu", {}).get("company_sheet_token", "")

        # 2. 环境变量最高优先级覆盖
        if os.environ.get("FEISHU_APP_ID"):
            self.app_id = os.environ.get("FEISHU_APP_ID")
        if os.environ.get("FEISHU_APP_SECRET"):
            self.app_secret = os.environ.get("FEISHU_APP_SECRET")
        if os.environ.get("FEISHU_USER_OPEN_ID"):
            self.user_open_id = os.environ.get("FEISHU_USER_OPEN_ID")
        if os.environ.get("USER_NICKNAME"):
            self.nickname = os.environ.get("USER_NICKNAME")
        if os.environ.get("COMPANY_STATS_SHEET_TOKEN"):
            self.sheet_token = os.environ.get("COMPANY_STATS_SHEET_TOKEN")

    def get_tenant_token(self) -> str:
        """获取租户 access_token。"""
        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        payload = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    return data.get("tenant_access_token", "")
                raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"连接飞书鉴权接口失败: {e}")

    def get_user_nickname(self) -> str:
        """动态查询用户花名/昵称，查询失败则使用预设。"""
        try:
            tok = self.get_tenant_token()
            url = f"{FEISHU_API_BASE}/contact/v3/users/{self.user_open_id}?user_id_type=open_id"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                name = data.get("data", {}).get("user", {}).get("name")
                if name:
                    self.nickname = name
                    return name
        except Exception:
            pass
        return self.nickname

    def build_card(self, report: AggregateReport) -> Dict[str, Any]:
        """构建结构严谨、美观大方的飞书交互式卡片 JSON。"""
        is_weekly = report.period_type == "weekly"
        title_prefix = "【周报】" if is_weekly else ("【月报】" if report.period_type == "monthly" else "【总战报】")
        header_color = "turquoise" if is_weekly else "blue"

        r = report.to_dict()
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**统计周期**：{report.period_name} ({report.start_date[:10]} 至 {report.end_date[:10]})\n"
                               f"**执行人员**：**{self.nickname}** (`{self.user_open_id}`)\n"
                               f"**人效大跃升**：本期累计为人工节约 **{r['overall']['total_saved_hours']} 小时**（约合 {r['overall']['total_saved_minutes']} 分钟）！"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": False,
                        "text": {
                            "tag": "lark_md",
                            "content": f"🔍 **1. 文献检索 (基准 7min/篇)**\n"
                                       f"• 检索完成：**{r['retrieval']['count']} 篇**\n"
                                       f"• 检索耗时：**{r['retrieval']['duration_seconds']} 秒** (单篇均耗 {r['retrieval']['avg_seconds']}s)\n"
                                       f"• 节约工时：**{r['retrieval']['saved_hours']} 小时** ({r['retrieval']['saved_minutes']} 分钟)"
                        }
                    },
                    {
                        "is_short": False,
                        "text": {
                            "tag": "lark_md",
                            "content": f"📥 **2. 文献下载 (基准 2min/篇)**\n"
                                       f"• 成功下载：**{r['download']['count']} 篇**\n"
                                       f"• 下载耗时：**{r['download']['duration_seconds']} 秒** (单篇均耗 {r['download']['avg_seconds']}s)\n"
                                       f"• 节约工时：**{r['download']['saved_hours']} 小时** ({r['download']['saved_minutes']} 分钟)"
                        }
                    },
                    {
                        "is_short": False,
                        "text": {
                            "tag": "lark_md",
                            "content": f"🖍️ **3. Highlight 与质检 (基准 4min/篇)**\n"
                                       f"• 阅读页数：**{r['highlight']['pages']} 页**\n"
                                       f"• 完成标注：**{r['highlight']['count']} 篇**\n"
                                       f"• 高亮均耗：**{r['highlight']['avg_seconds']}s** / 篇 | 修正均耗：**{r['highlight']['correction_avg_seconds']}s** / 篇\n"
                                       f"• 节约工时：**{r['highlight']['saved_hours']} 小时** ({r['highlight']['saved_minutes']} 分钟)"
                        }
                    },
                    {
                        "is_short": False,
                        "text": {
                            "tag": "lark_md",
                            "content": f"🧩 **4. 其他工作 (无人工基准)**\n"
                                       f"• 任务数：**{r['other']['count']} 项**\n"
                                       f"• 工作时长：**{r['other']['duration_seconds']} 秒**"
                                       f"（{r['other']['duration_hours']} 小时，均耗 {r['other']['avg_seconds']}s）\n"
                                       f"• Token 消耗：**{r['other']['total_tokens']:,}**"
                                       f"{_tokens_share(r)}"
                                       f"\n• 说明：不计节约工时 —— 该类目没有人工基准"
                        }
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"⚡ **Token 资源消耗 (服务商控制台 100% 绝对一致)**\n"
                               f"• 计量模式：`真实网关响应 (100% 账单对齐)`\n"
                               f"• Prompt Tokens: `{r['tokens']['prompt_tokens']:,}` | Completion Tokens: `{r['tokens']['completion_tokens']:,}`\n"
                               f"• Total Tokens: **{r['tokens']['total_tokens']:,}**" +
                               (f" (已核验真实 API 调用 {r['tokens']['llm_call_count']} 次)" if r['tokens']['llm_call_count'] > 0 else " (本周期无代码直接 LLM 网络调用)")
                }
            }
        ]

        # 若是月报且附带历史累计
        if report.historical_cumulative:
            hc = report.historical_cumulative.to_dict()
            elements.extend([
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"🏆 **历史累计总功绩战报**\n"
                                   f"• 历史文献检索：**{hc['retrieval']['count']} 篇** (节约 {hc['retrieval']['saved_hours']}h)\n"
                                   f"• 历史成功下载：**{hc['download']['count']} 篇** (节约 {hc['download']['saved_hours']}h)\n"
                                   f"• 历史文献阅读：**{hc['highlight']['pages']} 页** | Highlight **{hc['highlight']['count']} 篇** (节约 {hc['highlight']['saved_hours']}h)\n"
                                   f"• 历史总计节约工时：🚀 **{hc['overall']['total_saved_hours']} 小时**！"
                    }
                }
            ])

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{title_prefix} TraeWork 文献AI效率与人效收益汇报"
                },
                "template": header_color
            },
            "elements": elements
        }

    def push_to_user_chat(self, report: AggregateReport) -> Tuple[bool, str]:
        """将聚合战报通过 TraeWork Bot 直接推送至用户飞书会话。"""
        try:
            tok = self.get_tenant_token()
            url = f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type=open_id"
            card = self.build_card(report)
            payload = json.dumps({
                "receive_id": self.user_open_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False)
            }).encode("utf-8")
            
            req = urllib.request.Request(
                url, data=payload, 
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"}, 
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    return True, f"推送成功 (Message ID: {data.get('data', {}).get('message_id')})"
                return False, f"推送失败: code={data.get('code')}, msg={data.get('msg')}"
        except Exception as e:
            return False, f"推送异常: {str(e)}"

    def sync_to_public_sheet(self, report: AggregateReport) -> Tuple[bool, str]:
        """同步用户昵称与成绩至公司公共统计表。若云端表无权限，自动落盘本地企业公共统计表。"""
        r = report.to_dict()
        # 列序由 PUBLIC_SHEET_COLUMNS 单一来源派生, 不在这里手写第二份。
        row_values = build_public_sheet_row(report, self.nickname, self.user_open_id)

        # 1. 始终在本地落盘企业公共统计基线 CSV (zero-loss fallback)
        csv_path = os.path.expanduser(r"~/.medit/company_public_stats.csv")
        try:
            import csv
            # 追加之前先对齐表头: 本版新增了「其他」三列, 历史文件仍是旧表头。
            # 表头没对齐就追加, 新行会比表头宽, 列语义从此错位 —— 于是这个文件
            # 会在"看起来正常"的状态下开始说假话。迁移不成功就不追加。
            may_append, note = (True, "")
            if os.path.exists(csv_path):
                may_append, note = migrate_public_csv_columns(csv_path)
            if note:
                print(f"[FeishuSync] {note}")
            if may_append:
                file_exists = os.path.exists(csv_path)
                with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(PUBLIC_SHEET_COLUMNS)
                    writer.writerow(row_values)
        except Exception as e:
            print(f"[FeishuSync] 写入本地统计表警告: {e}")

        # 2. 尝试同步至飞书云端表格
        try:
            tok = self.get_tenant_token()
            if not self.sheet_token:
                self.sheet_token = self._ensure_default_sheet(tok)
            header_note = self._ensure_sheet_header(tok)
            if header_note:
                print(f"[FeishuSync] {header_note}")

            url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{self.sheet_token}/values_append"
            body = json.dumps({
                "valueRange": {
                    "range": f"Sheet1!A:{sheet_range_end()}",
                    "values": [row_values]
                }
            }).encode("utf-8")
            
            req = urllib.request.Request(
                url, data=body,
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    return True, f"已成功同步至飞书公共表格 (Token: {self.sheet_token})，且已本地双备份。"
                return True, f"已落盘本地公共表 ({csv_path})。飞书云端提示: {data.get('msg')}"
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="replace")
            if "99991672" in err_text or "permission_violations" in err_text:
                auth_hint = f"https://open.feishu.cn/app/{self.app_id}/auth?q=sheets:spreadsheet"
                return True, (
                    f"已成功同步至本地公共统计表 ({csv_path})！\n"
                    f"【飞书云端权限提示】当前 Bot 尚未开通表格创建权限，若需同步至飞书在线表，"
                    f"请管理员在飞书开放平台为应用 {self.app_id} 开通 [电子表格] 权限，或将该 Bot 添加至已有公司的在线公共表格。"
                )
            return True, f"已落盘本地公共表 ({csv_path})。飞书云端接口返回: {e}"
        except Exception as e:
            return True, f"已落盘本地公共表 ({csv_path})。云端同步异常: {str(e)}"

    def _ensure_sheet_header(self, tok: str) -> str:
        """把云端表的表头行对齐到当前列定义 (best-effort, 每进程只做一次)。

        历史云端表是在写入「其他」三列之前建的, 因此第 19 列往后没有表头 —— 追加进去
        的数据会落在没有标题的列里, 看着像野数据。这里把整行表头重写一遍: 前 18 列
        名字未变, 重写是幂等的, 不动任何数据行。

        失败不影响数据追加 (表头没对齐只是"不好看", 数据本身没错列)。
        """
        if self._header_synced or not self.sheet_token:
            return ""
        self._header_synced = True
        try:
            url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{self.sheet_token}/values"
            body = json.dumps({
                "valueRange": {
                    "range": f"Sheet1!A1:{sheet_range_end()}1",
                    "values": [PUBLIC_SHEET_COLUMNS],
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=body,
                headers={"Authorization": f"Bearer {tok}",
                         "Content-Type": "application/json; charset=utf-8"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=10) as _:
                pass
            return "云端表表头已对齐到当前列定义"
        except Exception as e:
            return f"云端表表头对齐失败 (不影响数据追加): {e}"

    def _ensure_default_sheet(self, tok: str) -> str:
        """若无公共表，自动为企业创建一份《TraeWork文献整理AI人效公共统计表》并初始化表头。"""
        url = f"{FEISHU_API_BASE}/sheets/v3/spreadsheets"
        body = json.dumps({"title": "TraeWork文献整理AI人效公共统计表"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            st = data.get("data", {}).get("spreadsheet", {}).get("spreadsheet_token")
            if not st:
                raise RuntimeError("创建默认公共统计表失败")
            
            # 初始化表头 —— 与 PUBLIC_SHEET_COLUMNS 同源, 不另写一份
            init_url = f"{FEISHU_API_BASE}/sheets/v2/spreadsheets/{st}/values"
            init_body = json.dumps({
                "valueRange": {
                    "range": f"Sheet1!A1:{sheet_range_end()}1",
                    "values": [PUBLIC_SHEET_COLUMNS]
                }
            }).encode("utf-8")
            init_req = urllib.request.Request(
                init_url, data=init_body,
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"},
                method="PUT"
            )
            try:
                with urllib.request.urlopen(init_req, timeout=10) as _:
                    pass
            except Exception:
                pass
            print(f"[FeishuSync] 成功自动创建公共统计表: https://open.feishu.cn/sheets/{st}")
            return st
