"""Configuration manager and cross-device setup wizard for via54Medit telemetry."""

import json
import os
import re
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILE_PATH = os.path.expanduser(r"~/.medit/telemetry_config.json")
TRAE_WORKSPACE_CONFIG = os.path.expanduser(
    r"~\AppData\Roaming\TRAE SOLO CN\User\globalStorage\cloudide.icube-im-bridge\feishu-bridge\3401238267317833\channel_config.json"
)

# 星期映射字典
WEEKDAY_MAP = {
    "mon": 0, "monday": 0, "周一": 0, "星期一": 0, "1": 0,
    "tue": 1, "tuesday": 1, "周二": 1, "星期二": 1, "2": 1,
    "wed": 2, "wednesday": 2, "周三": 2, "星期三": 2, "3": 2,
    "thu": 3, "thursday": 3, "周四": 3, "星期四": 3, "4": 3,
    "fri": 4, "friday": 4, "周五": 4, "星期五": 4, "5": 4,
    "sat": 5, "saturday": 5, "周六": 5, "星期六": 5, "6": 5,
    "sun": 6, "sunday": 6, "周日": 6, "星期日": 6, "0": 6, "7": 6,
}
WEEKDAY_NAMES = ["周一 (Monday)", "周二 (Tuesday)", "周三 (Wednesday)", "周四 (Thursday)", "周五 (Friday)", "周六 (Saturday)", "周日 (Sunday)"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "user": {
        "nickname": "",
        "open_id": "",
        "email": "",
        "mobile": ""
    },
    "feishu": {
        "app_id": "",
        "app_secret": "",
        "domain": "feishu",
        "bot_name": "TraeWork Telemetry",
        "company_sheet_token": "",
        "company_bitable_token": "",
        "company_bitable_table_id": "",
        "company_bitable_url": ""
    },
    "schedule": {
        "weekly": {
            "enabled": True,
            "day_of_week": 0,  # 0 = Monday, 4 = Friday
            "time": "09:00"    # HH:MM
        },
        "monthly": {
            "enabled": True,
            "day_of_month": 1, # 1..28 或 -1 (月末)
            "time": "09:00"
        }
    },
    "watcher": {
        "poll_interval_seconds": 30,
        "watch_dirs": [
            os.path.expanduser(r"~\.trae-cn\work"),
            os.path.expanduser(r"~\Desktop")
        ]
    }
}


def load_config() -> Dict[str, Any]:
    """加载配置：优先 ~/.medit/telemetry_config.json，其次嗅探本机 TraeWork，最后使用默认值。"""
    config = json.loads(json.dumps(DEFAULT_CONFIG))

    # 1. 尝试嗅探本机 TraeWork 凭据作为基线
    if os.path.exists(TRAE_WORKSPACE_CONFIG):
        try:
            with open(TRAE_WORKSPACE_CONFIG, "r", encoding="utf-8") as tf:
                tdata = json.load(tf)
                ws = tdata.get("channels", {}).get("feishu", {}).get("workspace", {})
                if ws.get("appId"):
                    config["feishu"]["app_id"] = ws.get("appId")
                if ws.get("appSecret"):
                    config["feishu"]["app_secret"] = ws.get("appSecret")
                if ws.get("userOpenId"):
                    config["user"]["open_id"] = ws.get("userOpenId")
                if ws.get("botName"):
                    config["feishu"]["bot_name"] = ws.get("botName")
                    if "for " in ws.get("botName"):
                        config["user"]["nickname"] = ws.get("botName").split("for ")[-1].strip()
        except Exception:
            pass

    # 2. 读取用户自定义的持久化配置文件
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                # 深度合并
                for k, v in saved.items():
                    if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                        config[k].update(v)
                    else:
                        config[k] = v
        except Exception as e:
            print(f"[Config] 读取配置文件异常: {e}")

    # 3. 环境变量覆盖
    if os.environ.get("FEISHU_APP_ID"):
        config["feishu"]["app_id"] = os.environ.get("FEISHU_APP_ID")
    if os.environ.get("FEISHU_APP_SECRET"):
        config["feishu"]["app_secret"] = os.environ.get("FEISHU_APP_SECRET")
    if os.environ.get("FEISHU_USER_OPEN_ID"):
        config["user"]["open_id"] = os.environ.get("FEISHU_USER_OPEN_ID")
    if os.environ.get("USER_NICKNAME"):
        config["user"]["nickname"] = os.environ.get("USER_NICKNAME")
    if os.environ.get("COMPANY_STATS_SHEET_TOKEN"):
        config["feishu"]["company_sheet_token"] = os.environ.get("COMPANY_STATS_SHEET_TOKEN")
    if os.environ.get("COMPANY_BITABLE_TOKEN"):
        config["feishu"]["company_bitable_token"] = os.environ.get("COMPANY_BITABLE_TOKEN")

    return config


def save_config(config: Dict[str, Any]):
    """保存配置至 ~/.medit/telemetry_config.json。"""
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[Config] 配置已持久化至: {CONFIG_FILE_PATH}")


def parse_weekly_time(day_str: str, time_str: str) -> Tuple[int, str]:
    """解析用户输入的星期与时间 (如 'Friday', '18:00')。"""
    clean_day = day_str.strip().lower()
    if clean_day not in WEEKDAY_MAP:
        raise ValueError(f"无法识别的星期参数: '{day_str}'。支持格式: 周一/周二/.../周日, Mon/Tue/.../Sun, 1..7")
    weekday_idx = WEEKDAY_MAP[clean_day]

    # 校验时间格式 HH:MM
    match = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", time_str.strip())
    if not match:
        raise ValueError(f"无法识别的时间格式: '{time_str}'。正确格式为 24小时制 HH:MM (例如 09:00 或 18:30)")
    h, m = int(match.group(1)), int(match.group(2))
    norm_time = f"{h:02d}:{m:02d}"
    return weekday_idx, norm_time


def parse_monthly_time(day_str: str, time_str: str) -> Tuple[int, str]:
    """解析用户输入的月份日期与时间 (如 '1', '09:00' 或 'last', '18:00')。"""
    clean_day = day_str.strip().lower()
    if clean_day in ["last", "月末", "最后一天", "-1"]:
        day_val = -1
    else:
        try:
            day_val = int(clean_day)
            if not (1 <= day_val <= 28):
                raise ValueError
        except Exception:
            raise ValueError(f"无法识别的每月日期: '{day_str}'。支持 1~28 日或 'last' (月末最后一天)")

    match = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", time_str.strip())
    if not match:
        raise ValueError(f"无法识别的时间格式: '{time_str}'。正确格式为 24小时制 HH:MM (例如 09:00 或 18:30)")
    h, m = int(match.group(1)), int(match.group(2))
    norm_time = f"{h:02d}:{m:02d}"
    return day_val, norm_time


def interactive_setup():
    """多设备部署时的交互式授权与配置向导。"""
    print("================================================================")
    print("🚀 via54Medit 跨设备部署向导 (用户花名、飞书授权与定时报告)")
    print("================================================================")

    current = load_config()

    # 1. 填写花名 (用户昵称)
    default_nick = current["user"].get("nickname", "")
    nick_prompt = f"1. 请设置您的花名/用户昵称 [{default_nick}]: " if default_nick else "1. 请设置您的花名/用户昵称 (必填，如: wtg, 星云): "
    nickname = input(nick_prompt).strip() or default_nick
    while not nickname:
        nickname = input("   花名不能为空，请输入您的花名: ").strip()
    current["user"]["nickname"] = nickname
    print(f"   ✓ 用户花名已确认为: {nickname}\n")

    # 2. 飞书授权检测与绑定
    print("2. 飞书账号授权与凭据配置:")
    has_trae = os.path.exists(TRAE_WORKSPACE_CONFIG)
    use_trae = False
    if has_trae:
        ans = input("   检测到本机已安装 TraeWork，是否直接沿用 TraeWork 的飞书绑定凭据？(Y/n): ").strip().lower()
        if ans not in ["n", "no"]:
            use_trae = True
            print("   ✓ 已自动复用本机 TraeWork 飞书凭据。")

    if not use_trae:
        cur_app_id = current["feishu"].get("app_id", "")
        cur_app_secret = current["feishu"].get("app_secret", "")
        cur_open_id = current["user"].get("open_id", "")

        app_id = input(f"   请输入飞书应用 App ID [{cur_app_id}]: ").strip() or cur_app_id
        app_secret = input(f"   请输入飞书应用 App Secret [{cur_app_secret}]: ").strip() or cur_app_secret
        open_id = input(f"   请输入您的飞书账号 OpenID (ou_...) [{cur_open_id}]: ").strip() or cur_open_id

        current["feishu"]["app_id"] = app_id
        current["feishu"]["app_secret"] = app_secret
        current["user"]["open_id"] = open_id

    # 校验飞书鉴权
    print("   正在校验飞书连通性...")
    try:
        from .feishu_sync import FeishuSyncClient
        client = FeishuSyncClient()
        # 强制用当前输入覆盖
        client.app_id = current["feishu"]["app_id"]
        client.app_secret = current["feishu"]["app_secret"]
        client.user_open_id = current["user"]["open_id"]
        client.nickname = current["user"]["nickname"]
        tok = client.get_tenant_token()
        print(f"   ✓ 飞书鉴权校验成功！Token 有效。")
    except Exception as e:
        print(f"   ⚠️ 鉴权校验异常: {e} (您依然可以继续保存，稍后通过 config 命令修改)")

    print()
    # 3. 定时报告时间设置
    print("3. 定时报告时间配置 (可随时通过命令修改):")
    # 周报
    cur_w_day = current["schedule"]["weekly"]["day_of_week"]
    cur_w_time = current["schedule"]["weekly"]["time"]
    w_input = input(f"   每周报告时间 (格式: 星期 时间, 例: Friday 18:00) [{WEEKDAY_NAMES[cur_w_day]} {cur_w_time}]: ").strip()
    if w_input:
        parts = w_input.split()
        if len(parts) >= 2:
            try:
                w_day, w_time = parse_weekly_time(parts[0], parts[1])
                current["schedule"]["weekly"]["day_of_week"] = w_day
                current["schedule"]["weekly"]["time"] = w_time
                print(f"   ✓ 周报时间已设为: 每{WEEKDAY_NAMES[w_day]} {w_time}")
            except Exception as e:
                print(f"   ⚠️ 输入格式有误 ({e})，保持默认。")

    # 月报
    cur_m_day = current["schedule"]["monthly"]["day_of_month"]
    cur_m_time = current["schedule"]["monthly"]["time"]
    m_day_display = "月末最后一天" if cur_m_day == -1 else f"{cur_m_day}日"
    m_input = input(f"   每月报告时间 (格式: 日期 时间, 例: 1 09:00 或 last 18:00) [每月{m_day_display} {cur_m_time}]: ").strip()
    if m_input:
        parts = m_input.split()
        if len(parts) >= 2:
            try:
                m_day, m_time = parse_monthly_time(parts[0], parts[1])
                current["schedule"]["monthly"]["day_of_month"] = m_day
                current["schedule"]["monthly"]["time"] = m_time
                m_show = "月末最后一天" if m_day == -1 else f"{m_day}日"
                print(f"   ✓ 月报时间已设为: 每月{m_show} {m_time}")
            except Exception as e:
                print(f"   ⚠️ 输入格式有误 ({e})，保持默认。")

    # 保存配置
    save_config(current)
    print("\n================================================================")
    print("🎉 部署初始化完成！您现在可以随时执行以下命令：")
    print("  • 启动主动后台监控守护: python -m telemetry.cli daemon --start")
    print("  • 查看/修改当前配置:     python -m telemetry.cli config")
    print("  • 推送测试卡片:           python -m telemetry.cli push --period week")
    print("================================================================\n")
