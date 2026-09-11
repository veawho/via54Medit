"""Configuration manager and cross-device setup wizard for via54Medit telemetry."""

import json
import os
import re
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .platform_paths import (
    desktop_dir,
    trae_work_config_candidates,
    trae_work_config_path,
    trae_work_dir,
)

CONFIG_FILE_PATH = os.path.expanduser(r"~/.medit/telemetry_config.json")
TRAE_WORKSPACE_CONFIG = trae_work_config_path()

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

# --------------------------------------------------------------------------- #
# 默认排程 —— **唯一事实来源**
#
# 周报: 每周一 10:30   月报: 每月 1 日 10:30
# 提醒: 推送日的前一个工作日 18:00 提醒用户别关机 (见 reminders.py)
#
# 这些常量同时被 config.DEFAULT_CONFIG、daemon 的兜底取值与 nlp_deploy 的默认值引用 ——
# 之前默认时间散落在三处字面量里("09:00" 抄了三遍), 改一次要改三处, 迟早漏一处。
# --------------------------------------------------------------------------- #
DEFAULT_WEEKLY_SCHEDULE: Dict[str, Any] = {
    "enabled": True,
    "day_of_week": 0,       # 0 = Monday
    "time": "10:30",
}
DEFAULT_MONTHLY_SCHEDULE: Dict[str, Any] = {
    "enabled": True,
    "day_of_month": 1,      # 1..28 或 -1 (月末)
    "time": "10:30",
}
#: 推送日前一个工作日的"别关机"提醒。
DEFAULT_REMINDER_SCHEDULE: Dict[str, Any] = {
    "enabled": True,
    "time": "18:00",        # 该工作日下班前后, 用户离开工位之前
}

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
        "company_bitable_url": "",
        # 目标表 schema 适配（留空则自动探测）
        "company_bitable_schema": "",       # "standard" | "company" | "" (自动识别)
        "company_bitable_project": "",      # 目标表「项目任务类型」单选值，如 via54Medit
        "company_bitable_member": "",       # 目标表「提交成员」显示名，留空则用 user.nickname
        "company_bitable_field_map": {}     # 可选：自定义 标准字段名 -> 目标表字段名 覆盖
    },
    "schedule": {
        "weekly": json.loads(json.dumps(DEFAULT_WEEKLY_SCHEDULE)),
        "monthly": json.loads(json.dumps(DEFAULT_MONTHLY_SCHEDULE)),
        "reminder": json.loads(json.dumps(DEFAULT_REMINDER_SCHEDULE)),
        # 目标日落在周末或法定节假日时, 顺延到下一个工作日(补班的周六算工作日)。
        # 判断依据是 holidays 模块的日历(来源为国务院公告)。设为 false 则按固定日期发。
        "defer_non_workday": True,
    },
    "watcher": {
        "poll_interval_seconds": 30,
        "watch_dirs": [
            trae_work_dir(),
            desktop_dir()
        ]
    },
    # 关键事件的外部告警 (飞书)。守护进程的"资源耗尽但不崩溃"型故障不会触发 KeepAlive,
    # 只有主动推送才能被及时发现 —— 5.4.5 那次文件描述符耗尽就静默了十余小时。
    "alerts": {
        "enabled": True,
        # 同一类告警的静默期 (分钟), 避免刷屏; 发送失败时会缩短为 10 分钟再试
        "min_interval_minutes": 60
    }
}


#: 排程默认值迁移
#
# 旧版本默认是 09:00。已部署过的设备把 09:00 **写进了** ~/.medit/telemetry_config.json,
# 因此只改 DEFAULT_CONFIG 对它们无效 —— 深合并时旧值会盖住新默认。
#
# 迁移规则: **只在该值仍等于旧默认值时才替换**, 也就是"用户没自定义过"的才动;
# 用户自己设过的(例如 Friday 18:00)一律不碰。并且打一次版本戳, 只做一次 ——
# 否则将来用户**故意**改回 09:00, 又会被悄悄顶成 10:30。
SCHEDULE_DEFAULTS_VERSION = 2
_FORMER_DEFAULTS = {
    ("weekly", "time"): "09:00",
    ("monthly", "time"): "09:00",
}


def _migrate_schedule_defaults(saved: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """把仍是旧默认值的排程升到当前默认。返回是否**需要落盘**。

    ``saved`` 是磁盘上那份配置(用来看用户到底写了什么), ``config`` 是合并后的结果。
    """
    try:
        version = int(saved.get("schedule_defaults_version", 1))
    except (TypeError, ValueError):
        version = 1
    if version >= SCHEDULE_DEFAULTS_VERSION:
        return False

    schedule = config.setdefault("schedule", {})
    changed = []
    for (section, field_name), former in _FORMER_DEFAULTS.items():
        new_default = (DEFAULT_CONFIG["schedule"][section] or {}).get(field_name)
        node = schedule.setdefault(section, {})
        # 只有"磁盘上明确写着旧默认值"才算没自定义过
        stored = (saved.get("schedule", {}) or {}).get(section, {}) or {}
        if str(stored.get(field_name, "")) != former:
            continue
        if str(node.get(field_name, "")) == former and new_default:
            node[field_name] = new_default
            changed.append("%s.%s: %s -> %s" % (section, field_name, former, new_default))

    config["schedule_defaults_version"] = SCHEDULE_DEFAULTS_VERSION
    if changed:
        print("[Config] 排程默认值已升级: %s" % "; ".join(changed))
    # 无论是否真的改了时间, 版本戳都要落盘一次 —— 否则"用户将来故意改回旧默认值"
    # 又会被当成未迁移而再次顶掉。
    return True


def _persist_migration(config: Dict[str, Any]):
    """静默回写迁移结果。只在配置文件**已存在**时写 —— 不能让只读命令顺手造出一个配置文件。"""
    if not os.path.exists(CONFIG_FILE_PATH):
        return
    try:
        directory = os.path.dirname(CONFIG_FILE_PATH)
        os.makedirs(directory, exist_ok=True)
        fd = os.open(CONFIG_FILE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(CONFIG_FILE_PATH, 0o600)
        except OSError:
            pass
    except OSError as e:
        print(f"[Config] 排程迁移回写失败 (本次运行仍已生效): {e}")


def load_config() -> Dict[str, Any]:
    """加载配置：优先 ~/.medit/telemetry_config.json，其次嗅探本机 TraeWork，最后使用默认值。"""
    config = json.loads(json.dumps(DEFAULT_CONFIG))

    # 1. 尝试嗅探本机 TraeWork 凭据作为基线
    #    跨平台候选路径 (Windows %APPDATA% / macOS Application Support /
    #    Linux XDG)，命中首个含 appId 的配置即停止。
    for workspace_config in trae_work_config_candidates():
        if not os.path.exists(workspace_config):
            continue
        try:
            with open(workspace_config, "r", encoding="utf-8") as tf:
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
            continue
        if config["feishu"]["app_id"]:
            break

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
            # 旧默认值(09:00)已被写进老设备的配置文件, 光改 DEFAULT_CONFIG 对它们无效。
            if _migrate_schedule_defaults(saved, config):
                _persist_migration(config)
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
    """保存配置至 ~/.medit/telemetry_config.json。

    配置里含飞书 app_secret, 因此落盘时就把权限收紧: 文件 0600、目录 0700。用 os.open
    带 mode 创建可避免"先以 0644 落盘、随后才 chmod"之间的可读窗口; 对已存在的旧文件
    mode 不生效, 所以再显式 chmod 一次 (这正是本次修复前 0644 的成因)。
    """
    directory = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(directory, exist_ok=True)
    fd = os.open(CONFIG_FILE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_FILE_PATH, 0o600)
        os.chmod(directory, 0o700)
    except OSError:
        pass
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

    # 4. 「别关机」提醒 (推送日的前一个工作日)
    print("4. 「别关机」提醒:")
    print("   推送是**到点触发**的: 目标时刻机器关机或休眠, 这一次就静默漏推、不补发。")
    print("   因此默认在推送日的**前一个工作日**(按法定节假日推算, 会避开连休与调休)提醒一次。")
    rem = current["schedule"].setdefault(
        "reminder", json.loads(json.dumps(DEFAULT_REMINDER_SCHEDULE)))
    cur_rtime = rem.get("time", DEFAULT_REMINDER_SCHEDULE["time"])
    cur_ren = rem.get("enabled", True)
    ans_r = input(f"   是否开启？(Y/n) [当前: {'已开启' if cur_ren else '已关闭'}]: ").strip().lower()
    if ans_r in ["n", "no"]:
        rem["enabled"] = False
        print("   ✓ 已关闭提醒 (可随时用 `config --set-reminder 18:00` 重新开启)。\n")
    else:
        rem["enabled"] = True
        r_input = input(f"   提醒时刻 (格式 HH:MM) [{cur_rtime}]: ").strip()
        if r_input:
            try:
                hh, mm = r_input.split(":")
                h, m = int(hh), int(mm)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
                rem["time"] = f"{h:02d}:{m:02d}"
            except Exception:
                print(f"   ⚠️ 时间格式有误，保持 {cur_rtime}。")
        print(f"   ✓ 将在推送日的前一个工作日 {rem['time']} 提醒。\n")

    # 保存配置
    save_config(current)
    print("\n================================================================")
    print("🎉 部署初始化完成！您现在可以随时执行以下命令：")
    print("  • 启动主动后台监控守护: python -m telemetry.cli daemon --start")
    print("  • 查看/修改当前配置:     python -m telemetry.cli config")
    print("  • 查看法定节假日日历:     python -m telemetry.cli holiday")
    print("  • 推送测试卡片:           python -m telemetry.cli push --period week")
    print("================================================================\n")
