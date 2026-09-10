"""
Natural language parser for medit-telemetry deployment.
Extracts deployment intent, user nickname (花名), Feishu OpenID, and reporting schedules.
"""

import re
from typing import Any, Dict, Optional


def parse_natural_language_instruction(text: str) -> Dict[str, Any]:
    """
    解析用户输入的自然语言部署指令。
    
    例如:
      "在新设备上单独部署监控，花名叫星云，每周五下午6点汇报"
      "帮我安装文献监控并绑定飞书，花名wtg，OpenID为ou_12345"
      "部署TraeWork监控，每月1日9点汇报"
      "卸载监控守护进程"
    """
    result: Dict[str, Any] = {
        "intent": "deploy",  # deploy | uninstall | status
        "silent": True,      # 自然语言触发默认全自动静默装配
        "nickname": "",
        "openid": "",
        "app_id": "",
        "app_secret": "",
        "weekly": "",
        "monthly": "",
        "bitable": "",
        "allow_break_system_packages": False,
        "raw_text": text,
    }

    if not text or not text.strip():
        return result

    raw = text.strip()
    low = raw.lower()

    # 1. 意图判定
    if any(k in raw for k in ["卸载", "清理", "移除"]) or "uninstall" in low:
        result["intent"] = "uninstall"
        return result
    if any(k in raw for k in ["状态", "运行情况", "查询", "存活"]) and not any(k in raw for k in ["部署", "安装", "配置"]):
        result["intent"] = "status"
        return result

    # 2. 提取花名 / 昵称
    # 匹配: 花名叫wtg, 花名是星云, 花名: 李四, 昵称: 张三, 我是wtg
    nick_match = re.search(r"(?:花名|昵称|用户名)[是叫为:：\s]*([a-zA-Z0-9_\u4e00-\u9fa5]+)", raw)
    if nick_match:
        result["nickname"] = nick_match.group(1).strip()
    else:
        # 次选匹配: "我是xxx" (且排除常用词)
        who_match = re.search(r"我是([a-zA-Z0-9_\u4e00-\u9fa5]{2,10})", raw)
        if who_match and who_match.group(1) not in ["在新", "在新设备", "一个", "正在"]:
            result["nickname"] = who_match.group(1).strip()

    # 3. 提取 OpenID (ou_xxx)
    oid_match = re.search(r"(ou_[a-zA-Z0-9]{16,40})", raw)
    if oid_match:
        result["openid"] = oid_match.group(1).strip()

    # 4. 提取飞书 App ID (cli_xxx)
    appid_match = re.search(r"(cli_[a-zA-Z0-9]{16,40})", raw)
    if appid_match:
        result["app_id"] = appid_match.group(1).strip()

    # 5. 提取每周汇报时间 (Weekly Schedule)
    # 支持: 每周五 18:00, 周一 09:00, 星期五下午6点, Friday 18:00
    weekly_day = None
    day_match = re.search(r"(?:每)?(?:周|星期|礼拜)([一二三四五六日天1-7])|(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)", raw, re.I)
    if day_match:
        d_cn = day_match.group(1)
        d_en = day_match.group(2)
        if d_cn:
            day_map = {"一": "周一", "1": "周一", "二": "周二", "2": "周二", "三": "周三", "3": "周三",
                       "四": "周四", "4": "周四", "五": "周五", "5": "周五", "六": "周六", "6": "周六",
                       "日": "周日", "天": "周日", "7": "周日"}
            weekly_day = day_map.get(d_cn, "周五")
        elif d_en:
            weekly_day = d_en.capitalize()

    # 提取时间 (HH:MM 或 下午/晚上/上午 X 点)
    w_time = _extract_time_of_day(raw)
    if weekly_day:
        result["weekly"] = f"{weekly_day} {w_time or '18:00'}"

    # 6. 提取每月汇报时间 (Monthly Schedule)
    # 支持: 每月1日 09:00, 月末 18:00, 每月最后一天
    if "月末" in raw or "最后一天" in raw or "last" in low:
        m_time = w_time or "18:00"
        result["monthly"] = f"last {m_time}"
    else:
        m_day_match = re.search(r"每?月\s*([012]?\d)\s*[日号号]?", raw)
        if m_day_match:
            d_val = m_day_match.group(1)
            m_time = w_time or "09:00"
            result["monthly"] = f"{d_val} {m_time}"

    # 7. 提取多维表格 Token 或完整 URL
    bitable_match = re.search(r"(https?://[^\s\"']*(?:feishu\.cn|larksuite\.com)/base/[a-zA-Z0-9]+)|(bascn[a-zA-Z0-9]{15,40})", raw)
    if bitable_match:
        result["bitable"] = bitable_match.group(1) or bitable_match.group(2)

    # 8. 逃生开关: 是否允许绕过 PEP 668 保护写入外部管理的解释器
    # 默认关闭 —— 只有用户明确表达「强制安装 / 允许写入系统解释器」时才开启
    if any(k in raw for k in ["强制安装", "强制写入", "允许写入", "绕过保护"]) \
            or "break-system-packages" in low or "break_system_packages" in low:
        result["allow_break_system_packages"] = True

    return result


def _extract_time_of_day(text: str) -> Optional[str]:
    """从文本中提取时间，如 18:00, 09:30, 下午6点, 晚上8点半, 上午9点。"""
    # 优先匹配标准 HH:MM
    std_match = re.search(r"([01]?\d|2[0-3])[:：]([0-5]\d)", text)
    if std_match:
        h = int(std_match.group(1))
        m = int(std_match.group(2))
        return f"{h:02d}:{m:02d}"

    # 匹配中文语境时间: 下午6点, 晚上8点, 上午9点, 9点半
    cn_match = re.search(r"(早上|上午|中午|下午|晚上)?\s*([01]?\d|2[0-3])\s*点(?:([0-5]\d)分|(半))?", text)
    if cn_match:
        period = cn_match.group(1) or ""
        hour = int(cn_match.group(2))
        minute_str = cn_match.group(3)
        is_half = bool(cn_match.group(4))

        if minute_str:
            minute = int(minute_str)
        elif is_half:
            minute = 30
        else:
            minute = 0

        if period in ["下午", "晚上"] and hour < 12:
            hour += 12
        elif period in ["早上", "上午"] and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    return None
