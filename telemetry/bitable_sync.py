"""
Feishu Bitable (多维表格 / Base) integration module.
Manages automatic Base creation, table schema setup (15 fields), multi-user weekly record syncing (with upsert idempotency),
and data retrieval for automated chart reports.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .config import CONFIG_FILE_PATH, load_config, save_config
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

        # 尝试初始化字段
        if self.table_id:
            self.init_table_fields(self.app_token, self.table_id)

        return True, f"成功绑定多维表格: {self.bitable_url} (Table ID: {self.table_id or '自动识别'})"

    def init_table_fields(self, app_token: str, table_id: str) -> List[str]:
        """为多维表格自动创建 15 个标准化统计字段。"""
        created = []
        # 1. 查询现有字段，避免重复创建
        res = self._api_request(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields")
        existing_names = set()
        if res.get("code") == 0:
            for item in res.get("data", {}).get("items", []):
                existing_names.add(item.get("field_name"))

        for fld in TABLE_SCHEMA_FIELDS:
            name = fld["field_name"]
            if name in existing_names:
                continue
            payload = {
                "field_name": name,
                "type": fld["type"]
            }
            if "property" in fld:
                payload["property"] = fld["property"]

            f_res = self._api_request(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", method="POST", body=payload)
            if f_res.get("code") == 0:
                created.append(name)

        return created

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

    def sync_weekly_report(self, report: AggregateReport, nickname: str = "", open_id: str = "") -> Tuple[bool, str]:
        """
        团队成员每周上传数据至公共多维表格。
        具有自动幂等机制：同一成员、同一周期如果重复上报，自动更新该记录，杜绝脏数据。
        """
        nick = nickname or self._cfg.get("user", {}).get("nickname", "wtg")
        oid = open_id or self._cfg.get("user", {}).get("open_id", "")
        r = report.to_dict()

        now_ts = int(datetime.now().timestamp() * 1000)
        fields_payload = {
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
            "真实Token消耗": int(r["tokens"]["total_tokens"]),
            "API调用次数": int(r["tokens"].get("llm_call_count", 0)),
            "上报状态": "🟢 自动同步"
        }

        # 始终写入本地备份 CSV
        self._record_local_csv(fields_payload)

        if not self.app_token or not self.table_id:
            # 尝试通过配置或创建
            ok, res_dict = self.create_bitable_app()
            if not ok:
                return False, f"未绑定多维表格且自动创建受阻: {res_dict.get('msg')}"

        # 1. 查询是否有同一周期、同一花名的历史记录 (幂等检查)
        existing_record_id = self._find_existing_record(report.period_name, nick)

        if existing_record_id:
            # 更新已有记录
            up_url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{existing_record_id}"
            res = self._api_request(up_url, method="PUT", body={"fields": fields_payload})
            if res.get("code") == 0:
                return True, f"已成功更新本周多维表格数据！(花名: {nick} | 节约工时: {r['overall']['total_saved_hours']}h | 记录ID: {existing_record_id})"
            return False, f"更新多维表格记录失败: {res.get('msg')}"
        else:
            # 新增记录
            add_url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
            res = self._api_request(add_url, method="POST", body={"fields": fields_payload})
            if res.get("code") == 0:
                rec_id = res.get("data", {}).get("record", {}).get("record_id", "")
                return True, f"已成功向团队多维表格同步本周数据！(花名: {nick} | 节约工时: {r['overall']['total_saved_hours']}h | 记录ID: {rec_id})"
            return False, f"写入多维表格记录失败: {res.get('msg')}"

    def _find_existing_record(self, period_name: str, nickname: str) -> Optional[str]:
        """查询指定周期与花名是否已有记录。"""
        url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records?page_size=100"
        res = self._api_request(url)
        if res.get("code") == 0:
            for item in res.get("data", {}).get("items", []):
                f = item.get("fields", {})
                if f.get("汇报周期") == period_name and f.get("成员花名") == nickname:
                    return item.get("record_id")
        return None

    def fetch_team_records(self) -> List[Dict[str, Any]]:
        """从多维表格拉取团队所有成员历史记录，用于图表与战报汇总。"""
        if not self.app_token or not self.table_id:
            return self._load_local_csv_records()

        url = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records?page_size=500"
        res = self._api_request(url)
        if res.get("code") == 0:
            records = []
            for item in res.get("data", {}).get("items", []):
                records.append(item.get("fields", {}))
            return records
        return self._load_local_csv_records()

    def _record_local_csv(self, fields: Dict[str, Any]):
        """本地零丢失企业双备份。"""
        csv_path = os.path.expanduser(r"~/.medit/team_bitable_backup.csv")
        file_exists = os.path.exists(csv_path)
        try:
            import csv
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(list(fields.keys()))
                writer.writerow(list(fields.values()))
        except Exception:
            pass

    def _load_local_csv_records(self) -> List[Dict[str, Any]]:
        csv_path = os.path.expanduser(r"~/.medit/team_bitable_backup.csv")
        if not os.path.exists(csv_path):
            return []
        try:
            import csv
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            return []
