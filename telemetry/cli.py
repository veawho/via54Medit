"""Command-line interface for via54Medit telemetry, reporting, and Feishu sync."""

import argparse
import json
import os
import sys
from pprint import pprint

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .aggregator import TelemetryAggregator
from . import envcheck
from .config import (
    load_config,
    save_config,
    interactive_setup,
    parse_weekly_time,
    parse_monthly_time,
    WEEKDAY_NAMES,
    CONFIG_FILE_PATH,
)
from .db import TelemetryDB
from .feishu_sync import FeishuSyncClient
from .platform_paths import desktop_dir, trae_work_dir

# 刻意**不**在此处导入 ``.daemon`` / ``.watcher``:
# 两者会经 watcher -> pdf_utils -> fitz 拉起 PyMuPDF, 于是连 ``--help``、``--env-check``、
# ``alert`` 这些与 PDF 毫无关系的子命令也要付这份开销, 输出还会被 fitz 的弃用警告污染。
# 改用它们的函数各自在函数体内导入 (见 _install_autostart / cmd_daemon / cmd_scan 等)。


def cmd_status(args):
    db = TelemetryDB()
    agg = TelemetryAggregator(db)
    rep = agg.get_all_time_report()
    d = rep.to_dict()
    print("\n=======================================================")
    print(f"📊 TraeWork 文献整理 AI 效率总览 ({rep.period_name})")
    print("=======================================================")
    print(f"• 文献检索完成数: {d['retrieval']['count']} 篇 | 耗时: {d['retrieval']['duration_seconds']}s | 节约: {d['retrieval']['saved_hours']}h")
    print(f"• 文献成功下载数: {d['download']['count']} 篇 | 耗时: {d['download']['duration_seconds']}s | 节约: {d['download']['saved_hours']}h")
    print(f"• Highlight完成数: {d['highlight']['count']} 篇 | 阅读页数: {d['highlight']['pages']} 页 | 节约: {d['highlight']['saved_hours']}h")
    print(f"• 其他工作时长: {d['other']['duration_seconds']}s ({d['other']['duration_hours']}h) | 任务数: {d['other']['count']} | Token: {d['other']['total_tokens']:,} (无人工基准, 不计节约)")
    print(f"• 累计节约总工时: 🚀 {d['overall']['total_saved_hours']} 小时 ({d['overall']['total_saved_minutes']} 分钟)")
    mode_tag = "🟢 100% 控制台对齐" if d["tokens"].get("token_mode") == "exact" else "🟡 估算模式"
    call_cnt = d["tokens"].get("llm_call_count", 0)
    print(f"• 累计 Token 消耗: {d['tokens']['total_tokens']:,} tokens [{mode_tag}] | 真实调用: {call_cnt} 次")
    print("=======================================================\n")


def cmd_report(args):
    db = TelemetryDB()
    agg = TelemetryAggregator(db)
    if args.period == "week":
        rep = agg.get_weekly_report()
    elif args.period == "month":
        rep = agg.get_monthly_report()
    else:
        rep = agg.get_all_time_report()

    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        d = rep.to_dict()
        print(f"\n[{rep.period_name} 汇报单] (区间: {rep.start_date[:10]} ~ {rep.end_date[:10]})")
        print(f"1. 检索: {d['retrieval']['count']} 篇, 均耗 {d['retrieval']['avg_seconds']}s, 节约工时 {d['retrieval']['saved_hours']}h (人工 7min/篇)")
        print(f"2. 下载: {d['download']['count']} 篇, 均耗 {d['download']['avg_seconds']}s, 节约工时 {d['download']['saved_hours']}h (人工 2min/篇)")
        print(f"3. 高亮: {d['highlight']['count']} 篇, 阅读 {d['highlight']['pages']} 页, 均耗 {d['highlight']['avg_seconds']}s, 修正均耗 {d['highlight']['correction_avg_seconds']}s, 节约工时 {d['highlight']['saved_hours']}h (人工 4min/篇)")
        print(f"4. 其他: {d['other']['count']} 项, 工时 {d['other']['duration_seconds']}s, Token {d['other']['total_tokens']:,} (无人工基准, 不计节约工时)")
        print(f"5. 总体人效提升: 节约 {d['overall']['total_saved_hours']} 小时")
        print(f"6. Token 消耗: {d['tokens']['total_tokens']:,}\n")


def cmd_push(args):
    db = TelemetryDB()
    agg = TelemetryAggregator(db)
    rep = agg.get_weekly_report() if args.period == "week" else (agg.get_monthly_report() if args.period == "month" else agg.get_all_time_report())
    
    client = FeishuSyncClient()
    print(f"[FeishuPush] 准备推送 {rep.period_name} 至用户 OpenID: {client.user_open_id} ({client.nickname})...")
    if args.dry_run:
        card = client.build_card(rep)
        print("[DRY-RUN] 生成的卡片数据预览:")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    ok, msg = client.push_to_user_chat(rep)
    db.record_sync_log("feishu_card", client.user_open_id, "success" if ok else "failed", msg)
    print(f"[FeishuPush] 结果: {msg}")


def cmd_sync(args):
    db = TelemetryDB()
    agg = TelemetryAggregator(db)
    rep = agg.get_weekly_report() if args.period == "week" else (agg.get_monthly_report() if args.period == "month" else agg.get_all_time_report())
    
    # 1. 传统电子表格同步
    client = FeishuSyncClient(sheet_token=args.sheet)
    print(f"[FeishuSync] 准备同步 {rep.period_name} 成绩至公司公共统计表...")
    ok, msg = client.sync_to_public_sheet(rep)
    db.record_sync_log("feishu_sheet", client.sheet_token or "default", "success" if ok else "failed", msg)
    print(f"[FeishuSync] 结果: {msg}")

    # 2. 多维表格同步 (如果指定了 --bitable 或已绑定多维表格)
    if getattr(args, "bitable", False) or client.sheet_token.startswith("bascn") or load_config().get("feishu", {}).get("company_bitable_token"):
        from .bitable_sync import FeishuBitableManager
        bmgr = FeishuBitableManager()
        ok_b, msg_b = bmgr.sync_weekly_report(rep)
        db.record_sync_log("feishu_bitable", bmgr.app_token or "local_csv", "success" if ok_b else "failed", msg_b)
        print(f"[FeishuSync] 多维表格同步: {msg_b}")


def cmd_bitable(args):
    """飞书多维表格 (Bitable Base) 管理与团队图表看板。"""
    from .bitable_sync import FeishuBitableManager
    from .chart_reporter import render_html_dashboard, build_team_weekly_card
    mgr = FeishuBitableManager()

    if getattr(args, "create", False):
        name = getattr(args, "name", "") or "TraeWork团队文献整理AI监控看板"
        print(f"[*] 正在飞书云端创建全新多维表格《{name}》...")
        ok, res = mgr.create_bitable_app(name)
        if ok:
            print("✓ 创建成功！")
            print(f"  • 多维表格链接: {res['url']}")
            print(f"  • App Token:    {res['app_token']}")
            print(f"  • Table ID:     {res['table_id']}")
            print("  • 状态: 15 个标准化统计字段与分组视图已自动初始化。")
        else:
            print(f"[!] 创建提示:\n{res.get('msg')}")
        return

    if getattr(args, "bind", False):
        ok, msg = mgr.bind_existing_bitable(args.bind)
        print(f"[*] {msg}")
        return

    if getattr(args, "sync", False):
        db = TelemetryDB()
        agg = TelemetryAggregator(db)
        rep = agg.get_weekly_report() if args.period == "week" else (agg.get_monthly_report() if args.period == "month" else agg.get_all_time_report())
        dry = getattr(args, "dry_run", False)
        if dry:
            print("[*] DRY-RUN: 仅展示将要写入的字段, 不实际提交。")
        ok, msg = mgr.sync_weekly_report(rep, dry_run=dry)
        print(f"[*] {msg}")
        return

    if getattr(args, "report", False):
        print("[*] 正在汇总团队多维表格数据生成图表报告...")
        records = mgr.fetch_team_records()
        out_html = render_html_dashboard(records)
        print(f"✓ 团队人效图表报告已成功生成: {out_html}")
        if getattr(args, "open_browser", False):
            import webbrowser
            webbrowser.open(f"file:///{out_html}")
        return

    # 默认状态查询
    cfg = load_config()
    b_url = cfg.get("feishu", {}).get("company_bitable_url", "")
    b_tok = cfg.get("feishu", {}).get("company_bitable_token", "")
    print("\n=======================================================")
    print("📊 飞书多维表格 (Bitable Base) 团队协作看板状态")
    print("=======================================================")
    print(f"• 绑定状态: {'🟢 已绑定' if b_tok else '⚪ 未绑定'}")
    print(f"• 多维表格: {b_url or '未配置 (运行 medit-telemetry bitable --create 创建)'}")
    print(f"• 团队数据: 已自动启用本地零丢失双备份 (~/.medit/team_bitable_backup.csv)")
    print("• 常用命令:")
    print("    - 飞书创建多维表格: medit-telemetry bitable --create")
    print("    - 绑定已有多维表格: medit-telemetry bitable --bind <URL_OR_TOKEN>")
    print("    - 手动上传本周数据: medit-telemetry bitable --sync")
    print("    - 生成团队图表报告: medit-telemetry bitable --report")
    print("=======================================================\n")


def cmd_scan(args):
    from .watcher import WorkspaceScanner

    db = TelemetryDB()
    scanner = WorkspaceScanner(db)
    res = scanner.scan_project(args.path, args.name)
    print(f"[Scan] 扫描完成: {args.path}")
    print(f"  • 录入检索项: {res['retrieval']} 项")
    print(f"  • 录入下载项: {res['download']} 项")
    print(f"  • 录入高亮项: {res['highlight']} 项")


def cmd_backfill(args):
    from .watcher import WorkspaceScanner

    db = TelemetryDB()
    scanner = WorkspaceScanner(db)
    targets = [
        (os.path.join(desktop_dir(), "RSV"), "RSV"),
        (os.path.join(desktop_dir(), "TMA_test"), "TMA_test"),
        (os.path.join(trae_work_dir(), "6a9e448884fcf10fc666920a"), "Trae_RSV_Live"),
    ]
    print("[Backfill] 开始自动扫描历史成果并录入基准库...")
    total_stats = {"retrieval": 0, "download": 0, "highlight": 0}
    for p, name in targets:
        if os.path.exists(p):
            r = scanner.scan_project(p, name)
            print(f"  [OK] {name}: 检索 {r['retrieval']} | 下载 {r['download']} | 高亮 {r['highlight']}")
            for k in total_stats: total_stats[k] += r[k]
        else:
            print(f"  - 跳过不存在目录: {p}")
    print(f"[Backfill] 全部录入完成！历史累计录入: 检索 {total_stats['retrieval']} 项, 下载 {total_stats['download']} 篇, 高亮 {total_stats['highlight']} 篇。")


def cmd_holiday(args):
    """法定节假日日历的查看与刷新。

    用途: 确认"前一个工作日"是怎么算出来的。提醒要在推送日的前一个工作日发出, 而
    那一天可能是调休补班的周六、也可能因为连休而往前推好几天 —— 这张日历就是依据。
    """
    from datetime import date as _date

    from . import holidays

    if args.refresh:
        for path in holidays.clear_cache(args.year or None):
            print(f"[Holiday] 已清除缓存: {path}")
        holidays.reset_cache()
        print("[Holiday] 缓存已清, 下次判断将重新取数。")

    if args.check:
        try:
            d = _date.fromisoformat(args.check.strip())
        except ValueError:
            print(f"[Holiday] 日期格式错误: {args.check!r} (应为 YYYY-MM-DD)")
            return
        ok, text = holidays.workday_status(d)
        print(f"[Holiday] {d.isoformat()} {text} → {'工作日' if ok else '非工作日'}")
        print(f"          前一个工作日: {holidays.previous_workday(d).isoformat()}")
        return

    st = holidays.cache_status(args.year or None)
    print("=======================================================")
    print(f"📅 法定节假日日历 ({st['year']} 年)")
    print("=======================================================")
    print(f"• 数据来源:   {st['source']}{'' if st['authoritative'] else '  (非权威: 仅按周末推算)'}")
    print(f"• 放假天数:   {st['off_days']} 天    调休补班: {st['work_days']} 天")
    print(f"• 缓存目录:   {st['cache_dir']}"
          f"{'  (距今 %.1f 天)' % st['cache_age_days'] if st['cache_age_days'] is not None else '  (无缓存)'}")
    if st["papers"]:
        print("• 依据公告:")
        for paper in st["papers"]:
            print(f"    - {paper}")
    if st["note"]:
        print(f"• 说明:       {st['note']}")
    # 展示提醒实际会踩到的日期, 让"哪天该提醒"一目了然
    try:
        from .reminders import reminder_status

        upcoming = reminder_status(load_config()).get("upcoming") or []
        if upcoming:
            print("• 排程与提醒日:")
            for item in upcoming:
                print(f"    - 下次{item['label']}: {item['target']}  →  提醒日 "
                      f"{item['remind_date']}（{item['remind_status']}）")
    except Exception:                                       # noqa: BLE001
        pass
    print("=======================================================")


def cmd_init(args):
    """跨设备初始化向导。"""
    interactive_setup()


def cmd_config(args):
    """查看或修改配置。"""
    cfg = load_config()
    modified = False

    if args.nickname:
        cfg["user"]["nickname"] = args.nickname.strip()
        print(f"[Config] 已更新用户花名: {cfg['user']['nickname']}")
        modified = True

    if args.openid:
        cfg["user"]["open_id"] = args.openid.strip()
        print(f"[Config] 已更新用户 OpenID: {cfg['user']['open_id']}")
        modified = True

    if args.app_id:
        cfg["feishu"]["app_id"] = args.app_id.strip()
        print(f"[Config] 已更新飞书 App ID: {cfg['feishu']['app_id']}")
        modified = True

    if args.app_secret:
        cfg["feishu"]["app_secret"] = args.app_secret.strip()
        print(f"[Config] 已更新飞书 App Secret")
        modified = True

    if args.sheet:
        cfg["feishu"]["company_sheet_token"] = args.sheet.strip()
        print(f"[Config] 已更新企业公共统计表 Token: {cfg['feishu']['company_sheet_token']}")
        modified = True

    if args.set_weekly:
        parts = args.set_weekly.strip().split()
        if len(parts) >= 2:
            try:
                w_day, w_time = parse_weekly_time(parts[0], parts[1])
                cfg["schedule"]["weekly"]["day_of_week"] = w_day
                cfg["schedule"]["weekly"]["time"] = w_time
                print(f"[Config] 已更新周报推送时间: 每{WEEKDAY_NAMES[w_day]} {w_time}")
                modified = True
            except Exception as e:
                print(f"[Config] 错误: {e}")
        else:
            print("[Config] 格式错误，请使用: --set-weekly '<Day> <HH:MM>'，如 'Monday 10:30' 或 '周一 10:30'")

    if args.set_monthly:
        parts = args.set_monthly.strip().split()
        if len(parts) >= 2:
            try:
                m_day, m_time = parse_monthly_time(parts[0], parts[1])
                cfg["schedule"]["monthly"]["day_of_month"] = m_day
                cfg["schedule"]["monthly"]["time"] = m_time
                m_show = "月末最后一天" if m_day == -1 else f"{m_day}日"
                print(f"[Config] 已更新月报推送时间: 每月{m_show} {m_time}")
                modified = True
            except Exception as e:
                print(f"[Config] 错误: {e}")
        else:
            print("[Config] 格式错误，请使用: --set-monthly '<Day> <HH:MM>'，如 '1 10:30' 或 'last 18:00'")

    if args.set_reminder:
        parts = args.set_reminder.strip().split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except Exception:
            print("[Config] 格式错误，请使用: --set-reminder '18:00' (24 小时制 HH:MM)")
        else:
            node = cfg["schedule"].setdefault("reminder", {})
            node["time"] = "%02d:%02d" % (h, m)
            node["enabled"] = True
            print("[Config] 已开启「别关机」提醒: 推送日的前一个工作日 %02d:%02d" % (h, m))
            modified = True

    if args.no_reminder:
        cfg["schedule"].setdefault("reminder", {})["enabled"] = False
        print("[Config] 已关闭「别关机」提醒 (可随时用 --set-reminder '18:00' 重新开启)")
        modified = True

    if args.add_watch_dir:
        abs_p = os.path.abspath(args.add_watch_dir)
        if abs_p not in cfg["watcher"]["watch_dirs"]:
            cfg["watcher"]["watch_dirs"].append(abs_p)
            print(f"[Config] 已增加主动监控目录: {abs_p}")
            modified = True

    if modified:
        save_config(cfg)

    # 打印当前配置概览
    w_day_idx = cfg["schedule"]["weekly"]["day_of_week"]
    m_day_val = cfg["schedule"]["monthly"]["day_of_month"]
    m_day_name = "月末最后一天" if m_day_val == -1 else f"{m_day_val}日"

    print("\n=======================================================")
    print("⚙️  当前设备配置概览 (~/.medit/telemetry_config.json)")
    print("=======================================================")
    print(f"• 用户花名 (昵称): {cfg['user']['nickname']}")
    print(f"• 飞书账号 OpenID: {cfg['user']['open_id']}")
    print(f"• 飞书应用 App ID: {cfg['feishu']['app_id']}")
    print(f"• 公共表格 Token: {cfg['feishu']['company_sheet_token'] or '默认自动双备份至本地 CSV'}")
    print(f"• 每周汇报时间:    每{WEEKDAY_NAMES[w_day_idx]} {cfg['schedule']['weekly']['time']}")
    print(f"• 每月汇报时间:    每月{m_day_name} {cfg['schedule']['monthly']['time']}")
    # 提醒与"下次什么时候推"一并展示: 推送是到点触发的, 这两个信息是理解
    # "为什么这次没推 / 下次什么时候推"的关键, 不该只能靠读配置文件去拼。
    try:
        from .reminders import reminder_status

        st = reminder_status(cfg)
        print(f"• 别关机提醒:      {'已开启' if st['enabled'] else '已关闭'}"
              f"  (推送日的前一个工作日 {st['time']} 提醒)")
        for item in st["upcoming"]:
            flag = "" if item["authoritative"] else "  ⚠️ 仅按周末推算"
            print(f"    - 下次{item['label']}: {item['target']}  →  提醒日 {item['remind_date']}"
                  f"（{item['remind_status']}）{flag}")
    except Exception as e:                                  # noqa: BLE001
        print(f"• 别关机提醒:      状态读取失败 ({e})")
    print(f"• 主动监控目录:    {len(cfg['watcher']['watch_dirs'])} 个:")
    for d in cfg["watcher"]["watch_dirs"]:
        print(f"    - {d}")
    print("=======================================================\n")


def _install_autostart():
    """跨平台注册开机自启: macOS -> LaunchAgent; 其余 -> Windows Startup VBS。"""
    from .daemon import install_launchd_agent, install_startup_vbs

    if sys.platform == "darwin":
        install_launchd_agent()
    else:
        install_startup_vbs()


def _uninstall_autostart():
    """跨平台移除开机自启。"""
    from .daemon import uninstall_launchd_agent, uninstall_startup_vbs

    if sys.platform == "darwin":
        uninstall_launchd_agent()
    else:
        uninstall_startup_vbs()


def cmd_daemon(args):
    """后台主动监控与调度守护进程管理。"""
    from .daemon import (
        get_daemon_status,
        install_traework_companion_launcher,
        install_windows_startup_task,
        start_daemon_process,
        stop_daemon_process,
    )

    if args.start:
        start_daemon_process(foreground=False)
    elif args.foreground:
        start_daemon_process(foreground=True)
    elif args.stop:
        stop_daemon_process()
    elif args.install_startup:
        _install_autostart()
    elif args.uninstall_startup:
        _uninstall_autostart()
    elif args.create_launcher:
        install_traework_companion_launcher()
    elif args.install_task:
        install_windows_startup_task()
    else:
        # 查询状态
        st = get_daemon_status()
        print("\n=======================================================")
        print("🤖 Telemetry 主动监控守护服务状态")
        print("=======================================================")
        if st["running"]:
            print(f"• 状态: 🟢 正在运行中 (PID: {st['pid']})")
            details = st.get("details", {})
            if details:
                print(f"• 最近心跳: {details.get('last_tick')}")
                print(f"• 用户:     {details.get('user')} ({details.get('open_id')})")
                print(f"• 周报调度: {details.get('weekly_schedule')}")
                print(f"• 月报调度: {details.get('monthly_schedule')}")
                fd = details.get("fd") or {}
                if fd.get("used"):
                    limit = fd.get("limit")
                    ratio = f" ({fd['used'] * 100 // limit}%)" if limit else ""
                    print(f"• 文件描述符: {fd['used']}/{limit or '上限未知'}{ratio}")
        else:
            print("• 状态: 🔴 未运行")
            print("  提示: 使用 'python -m telemetry.cli daemon --start' 启动后台主动监控。")
        print("=======================================================\n")


def cmd_alert(args):
    """关键事件外部告警通道 (飞书) 的自检与管理。"""
    from . import alerter

    if args.enable or args.disable:
        cfg = load_config()
        cfg.setdefault("alerts", {})
        cfg["alerts"]["enabled"] = bool(args.enable)
        if args.min_interval is not None:
            cfg["alerts"]["min_interval_minutes"] = max(1, int(args.min_interval))
        save_config(cfg)
        print(f"[Alert] 已{'开启' if args.enable else '关闭'}关键事件外部告警。")
        return

    if args.test:
        print("[Alert] 正在发送测试告警 (绕过开关与限流)...")
        ok, msg = alerter.send_test_alert()
        print(f"  {'✓' if ok else '✗'} {msg}")
        return

    st = alerter.alert_status()
    print("\n=======================================================")
    print("🔔 关键事件外部告警通道 (飞书)")
    print("=======================================================")
    print(f"• 开关:     {'🟢 已开启' if st['enabled'] else '🔴 已关闭'}")
    print(f"• 静默期:   {st['min_interval_minutes']} 分钟 (同类告警; 发送失败则 10 分钟重试)")
    print(f"• 凭据:     {'✓ app_id / app_secret / open_id 齐备' if st['has_credentials'] else '✗ 缺少凭据, 无法推送'}")
    print(f"• 接收人:   {st['nickname'] or '(未设置)'}")
    print(f"• 状态文件: {st['state_file']}")
    limits = st["rate_limits"]
    if limits:
        print("• 最近发送记录:")
        for key, entry in sorted(limits.items()):
            print(f"    - {key}: {entry.get('last_attempt')} "
                  f"({'成功' if entry.get('last_ok') else '失败'})")
    else:
        print("• 最近发送记录: (无)")
    print("=======================================================")
    print("  验证通道: medit-telemetry alert --test")
    print("  开 / 关:  medit-telemetry alert --enable | --disable")
    print("  静默期:   medit-telemetry alert --min-interval 30")
    print("=======================================================\n")


def cmd_token(args):
    """LLM Token 真实账单管理与服务商控制台 100% 对齐。"""
    cfg = load_config()

    if args.mode:
        cfg.setdefault("telemetry", {})["token_mode"] = args.mode
        save_config(cfg)
        print(f"[Token] 已将默认统计模式设置为: {args.mode}")

    if args.log:
        p_tok = int(args.log[0])
        c_tok = int(args.log[1])
        from .token_tracker import record_llm_usage
        rec = record_llm_usage(
            response={"prompt_tokens": p_tok, "completion_tokens": c_tok},
            provider=args.provider or "deepseek",
            model=args.model or "console_manual",
            project_name=args.project or "default",
            source="cli:token",
        )
        print(f"[Token] 成功录入真实控制台调用: {p_tok} prompt + {c_tok} completion = {rec.total_tokens} total ({rec.provider}/{rec.model})")

    db = TelemetryDB()
    logs = db.query_llm_tokens()
    curr_mode = cfg.get("telemetry", {}).get("token_mode", "exact")

    print("\n=======================================================")
    print("💎 LLM Token 服务商控制台 100% 对齐总览")
    print("=======================================================")
    print(f"• 默认统计模式:  {'🟢 exact (100% 真实控制台网关响应对齐)' if curr_mode == 'exact' else '🟡 estimated (经验模型估算)'}")
    print(f"• 已核验真实调用: {len(logs)} 次")
    if logs:
        tot_p = sum(int(l["prompt_tokens"]) for l in logs)
        tot_c = sum(int(l["completion_tokens"]) for l in logs)
        tot_all = sum(int(l["total_tokens"]) for l in logs)
        print(f"• 真实消耗总计:   Prompt: {tot_p:,} | Completion: {tot_c:,} | Total: {tot_all:,} tokens")
        print("• 调用分布 (按供应商/模型):")
        by_model = {}
        for l in logs:
            k = f"{l['provider']}:{l['model']}"
            by_model[k] = by_model.get(k, 0) + int(l["total_tokens"])
        for k, v in by_model.items():
            print(f"    - {k}: {v:,} tokens")
    else:
        print("• 真实消耗总计:   0 tokens (目前无虚构估算，全部严格按真实调用计入)")
    print("=======================================================\n")


def cmd_deploy(args):
    from .deploy import (
        print_banner,
        check_python_environment,
        install_package_locally,
        setup_configuration,
        setup_autostart_and_launcher,
        launch_daemon_service,
        display_deployment_summary,
        uninstall_deployment,
    )
    if getattr(args, "uninstall", False):
        uninstall_deployment()
        return
    print_banner()
    if not check_python_environment():
        return
    install_package_locally()
    cfg = setup_configuration(args)
    setup_autostart_and_launcher(args)
    launch_daemon_service(args)
    display_deployment_summary(cfg)


def main():
    parser = argparse.ArgumentParser(description="TraeWork 文献整理与 Highlight 监控统计及飞书同步工具")
    parser.add_argument("--env-check", action="store_true",
                        help="自检运行环境 (PYTHONHOME / PYTHONPATH 冲突) 后退出")
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # init (向导)
    p_init = subparsers.add_parser("init", help="多设备部署交互式配置向导 (花名与飞书授权)")
    p_init.set_defaults(func=cmd_init)

    # config (配置管理)
    p_cfg = subparsers.add_parser("config", help="查看或修改当前设备配置与汇报时间")
    p_cfg.add_argument("--nickname", default="", help="修改用户花名/昵称")
    p_cfg.add_argument("--openid", default="", help="修改绑定的飞书 OpenID")
    p_cfg.add_argument("--app-id", default="", help="修改飞书应用 App ID")
    p_cfg.add_argument("--app-secret", default="", help="修改飞书应用 App Secret")
    p_cfg.add_argument("--sheet", default="", help="修改企业公共统计表 Token")
    p_cfg.add_argument("--bitable", default="", help="绑定团队飞书多维表格 (Base) URL 或 Token")
    p_cfg.add_argument("--set-weekly", default="", help="修改每周报告时间，例: 'Monday 10:30' 或 '周一 10:30'")
    p_cfg.add_argument("--set-monthly", default="", help="修改每月报告时间，例: '1 10:30' 或 'last 18:00'")
    p_cfg.add_argument("--set-reminder", default="",
                       help="开启/修改「别关机」提醒时刻 (推送日的前一个工作日)，例: '18:00'")
    p_cfg.add_argument("--no-reminder", action="store_true", help="关闭「别关机」提醒")
    p_cfg.add_argument("--add-watch-dir", default="", help="添加主动监控目录路径")
    p_cfg.set_defaults(func=cmd_config)

    # daemon (主动监控守护)
    p_daemon = subparsers.add_parser("daemon", help="主动监控守护服务管理 (启动/停止/状态/开机自启)")
    p_daemon.add_argument("--start", action="store_true", help="在后台启动主动监控守护进程")
    p_daemon.add_argument("--stop", action="store_true", help="停止后台守护进程")
    p_daemon.add_argument("--status", action="store_true", help="查询守护进程运行状态")
    p_daemon.add_argument("--foreground", action="store_true", help="在前台控制台直接运行")
    p_daemon.add_argument("--install-startup", action="store_true", help="注册开机自启 (macOS LaunchAgent / Windows Startup VBS)")
    p_daemon.add_argument("--uninstall-startup", action="store_true", help="移除开机自启")
    p_daemon.add_argument("--create-launcher", action="store_true", help="在桌面创建 TraeWork 伴随启动器 (点击同启监控)")
    p_daemon.add_argument("--install-task", action="store_true", help="一键注册为 Windows 开机计划任务")
    p_daemon.set_defaults(func=cmd_daemon)

    # status
    p_status = subparsers.add_parser("status", help="查看当前累计指标概览")
    p_status.set_defaults(func=cmd_status)

    # report
    p_report = subparsers.add_parser("report", help="生成周报/月报/总战报")
    p_report.add_argument("--period", choices=["week", "month", "all"], default="week", help="统计周期")
    p_report.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    p_report.set_defaults(func=cmd_report)

    # push
    p_push = subparsers.add_parser("push", help="推送周报/月报卡片至用户飞书会话")
    p_push.add_argument("--period", choices=["week", "month", "all"], default="week", help="统计周期")
    p_push.add_argument("--dry-run", action="store_true", help="演练模式，仅打印卡片数据不实际发送")
    p_push.set_defaults(func=cmd_push)

    # sync
    p_sync = subparsers.add_parser("sync", help="同步成绩至公司公共统计表或多维表格")
    p_sync.add_argument("--period", choices=["week", "month", "all"], default="week", help="统计周期")
    p_sync.add_argument("--sheet", default="", help="飞书电子表格 Token")
    p_sync.add_argument("--bitable", action="store_true", help="同步至团队飞书多维表格 (Base)")
    p_sync.set_defaults(func=cmd_sync)

    # bitable (飞书多维表格与团队看板)
    p_bitable = subparsers.add_parser("bitable", help="飞书多维表格 (Bitable Base) 团队自动上传与图表看板")
    p_bitable.add_argument("--create", action="store_true", help="在飞书自动创建多维表格看板与字段")
    p_bitable.add_argument("--name", default="", help="自定义多维表格名称")
    p_bitable.add_argument("--bind", default="", help="绑定已有飞书多维表格 URL 或 Token")
    p_bitable.add_argument("--sync", action="store_true", help="上传本周监控数据至多维表格")
    p_bitable.add_argument("--dry-run", action="store_true", help="仅展示 schema 判定与将写入的字段, 不实际提交")
    p_bitable.add_argument("--period", choices=["week", "month", "all"], default="week", help="统计周期")
    p_bitable.add_argument("--report", action="store_true", help="汇总团队所有成员数据生成图表看板")
    p_bitable.add_argument("--open-browser", action="store_true", help="生成报告后在浏览器打开")
    p_bitable.set_defaults(func=cmd_bitable)

    # holiday (法定节假日日历: 提醒日按它推算)
    p_holiday = subparsers.add_parser("holiday", help="查看/刷新法定节假日日历 (提醒日的推算依据)")
    p_holiday.add_argument("--year", type=int, default=0, help="查看指定年份 (默认今年)")
    p_holiday.add_argument("--refresh", action="store_true", help="清除本地缓存后重新取数")
    p_holiday.add_argument("--check", default="", help="判断某一天是否为工作日，例: '2026-10-01'")
    p_holiday.set_defaults(func=cmd_holiday)

    # scan
    p_scan = subparsers.add_parser("scan", help="扫描特定项目目录并录入成果")
    p_scan.add_argument("path", help="项目路径")
    p_scan.add_argument("--name", default="", help="项目名称")
    p_scan.set_defaults(func=cmd_scan)

    # backfill
    p_backfill = subparsers.add_parser("backfill", help="一键扫描并补录历史已有项目 (RSV, TMA)")
    p_backfill.set_defaults(func=cmd_backfill)

    # token (真实账单与控制台 100% 对齐)
    p_token = subparsers.add_parser("token", help="大模型 Token 真实账单管理与服务商控制台 100%% 对齐")
    p_token.add_argument("--mode", choices=["exact", "estimated"], help="设置默认统计模式 (exact=真实控制台对齐, estimated=经验估算)")
    p_token.add_argument("--log", nargs=2, type=int, metavar=("PROMPT", "COMPLETION"), help="手动补登一笔实际控制台消耗")
    p_token.add_argument("--provider", default="deepseek", help="大模型服务商 (如 deepseek, zhipu, openai)")
    p_token.add_argument("--model", default="", help="调用的模型名称")
    p_token.add_argument("--project", default="", help="所属项目名称")
    p_token.add_argument("--status", action="store_true", help="查询当前真实调用日志")
    p_token.set_defaults(func=cmd_token)

    # deploy (一键独立部署)
    p_deploy = subparsers.add_parser("deploy", help="一键独立部署引擎 (环境自检/注册/开机自启/启动守护)")
    p_deploy.add_argument("--silent", "-s", action="store_true", help="静默无交互模式")
    p_deploy.add_argument("--nickname", "-n", default="", help="用户花名/昵称")
    p_deploy.add_argument("--openid", default="", help="飞书 OpenID (ou_...)")
    p_deploy.add_argument("--app-id", default="", help="飞书 App ID")
    p_deploy.add_argument("--app-secret", default="", help="飞书 App Secret")
    p_deploy.add_argument("--sheet", default="", help="飞书公共表格 Token")
    p_deploy.add_argument("--weekly", default="", help="每周汇报时间，如: 'Friday 18:00'")
    p_deploy.add_argument("--monthly", default="", help="每月汇报时间，如: '1 09:00'")
    p_deploy.add_argument("--add-watch-dir", default="", help="追加主动监控目录")
    p_deploy.add_argument("--no-startup", action="store_true", help="不注册 Windows Startup 开机自启")
    p_deploy.add_argument("--no-launcher", action="store_true", help="不创建桌面伴随启动器")
    p_deploy.add_argument("--no-start", action="store_true", help="安装后不立即启动守护进程")
    p_deploy.add_argument("--uninstall", action="store_true", help="停止守护服务并移除自启")
    p_deploy.set_defaults(func=cmd_deploy)

    # alert (关键事件外部告警通道)
    p_alert = subparsers.add_parser("alert", help="关键事件外部告警通道 (飞书): 状态 / 测试 / 开关")
    p_alert.add_argument("--status", action="store_true", help="展示告警通道状态与最近发送记录 (默认)")
    p_alert.add_argument("--test", action="store_true", help="发送一条测试告警, 验证通道是否打通")
    p_alert.add_argument("--enable", action="store_true", help="开启关键事件外部告警")
    p_alert.add_argument("--disable", action="store_true", help="关闭关键事件外部告警")
    p_alert.add_argument("--min-interval", type=int, default=None, dest="min_interval",
                         help="同类告警的静默期 (分钟), 默认 60")
    p_alert.set_defaults(func=cmd_alert)

    args = parser.parse_args()

    if getattr(args, "env_check", False):
        print(envcheck.render_self_check())
        return

    # 环境自检: 只在检测到冲突时提示, 且不影响任何子命令的正常执行
    envcheck.warn_if_needed()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
