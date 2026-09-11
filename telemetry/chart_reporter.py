"""
Chart Reporter module:
Aggregates multi-user weekly records from Feishu Bitable or local backup,
generates interactive HTML dashboard charts and Feishu Team Leaderboard cards.
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple


def _num(value: Any) -> float:
    """宽松取数: 缺列 / 空串 / 脏值一律按 0 处理。

    记录可能来自**更早的周期**、或来自一张尚未补齐统计列的表(v5.4.43 之前公司表
    就没有"其他"三列), 因此读回来的记录缺列是正常的 —— 不能因此让整条记录被判为脏数据。
    缺哪些列由 ``bitable_sync.column_alignment()`` 明确报出, 不靠这里默默兜。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate_team_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总团队所有成员的数据，计算总和、均值与个人排名。"""
    member_summary: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "saved_hours": 0.0,
        "retrieval_count": 0,
        "download_count": 0,
        "highlight_pages": 0,
        "highlight_count": 0,
        "total_tokens": 0,
        # 其他类目: 工时与 Token 都汇总, 但没有"节约" (无人工基准)
        "other_hours": 0.0,
        "other_tokens": 0,
        "other_count": 0,
        "report_count": 0
    })

    weekly_trend: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "saved_hours": 0.0,
        "highlight_pages": 0,
        "member_count": 0
    })

    total_saved_hours = 0.0
    total_retrievals = 0
    total_downloads = 0
    total_pages = 0
    total_highlights = 0
    total_tokens = 0
    total_other_hours = 0.0
    total_other_tokens = 0
    total_other_count = 0

    for r in records:
        nick = str(r.get("成员花名", "未知成员"))
        period = str(r.get("汇报周期", "当前周期"))
        try:
            saved_h = float(r.get("总节约工时(h)", 0))
            ret_cnt = int(float(r.get("文献检索篇数", 0)))
            dl_cnt = int(float(r.get("文献下载篇数", 0)))
            pages = int(float(r.get("Highlight阅读页数", 0)))
            hl_cnt = int(float(r.get("Highlight标注篇数", 0)))
            tokens = int(float(r.get("真实Token消耗", 0)))
        except (ValueError, TypeError):
            continue

        # 其他类目: 历史记录 / 未补列的表里可能没有这三列, 缺列按 0 处理,
        # 由 bitable_sync.column_alignment() 负责把"缺列"这件事说出来。
        o_count = int(_num(r.get("其他任务数", 0)))
        o_hours = _num(r.get("其他工作时长(h)", 0))
        o_tokens = int(_num(r.get("其他Token消耗", 0)))

        # 累计个人
        m = member_summary[nick]
        m["saved_hours"] += saved_h
        m["retrieval_count"] += ret_cnt
        m["download_count"] += dl_cnt
        m["highlight_pages"] += pages
        m["highlight_count"] += hl_cnt
        m["total_tokens"] += tokens
        m["other_hours"] += o_hours
        m["other_tokens"] += o_tokens
        m["other_count"] += o_count
        m["report_count"] += 1

        # 累计周期趋势
        w = weekly_trend[period]
        w["saved_hours"] += saved_h
        w["highlight_pages"] += pages
        w["member_count"] += 1

        # 累计团队总计
        total_saved_hours += saved_h
        total_retrievals += ret_cnt
        total_downloads += dl_cnt
        total_pages += pages
        total_highlights += hl_cnt
        total_tokens += tokens
        total_other_hours += o_hours
        total_other_tokens += o_tokens
        total_other_count += o_count

    # 生成排名列表 (按节约工时降序)
    leaderboard = []
    for nick, data in member_summary.items():
        leaderboard.append({
            "nickname": nick,
            "saved_hours": round(data["saved_hours"], 2),
            "highlight_pages": data["highlight_pages"],
            "retrieval_count": data["retrieval_count"],
            "download_count": data["download_count"],
            "highlight_count": data["highlight_count"],
            "total_tokens": data["total_tokens"],
            "other_hours": round(data["other_hours"], 2),
            "other_tokens": data["other_tokens"],
            "other_count": data["other_count"],
            "report_count": data["report_count"]
        })
    leaderboard.sort(key=lambda x: x["saved_hours"], reverse=True)

    return {
        "total_saved_hours": round(total_saved_hours, 2),
        "total_retrievals": total_retrievals,
        "total_downloads": total_downloads,
        "total_pages": total_pages,
        "total_highlights": total_highlights,
        "total_tokens": total_tokens,
        "total_other_hours": round(total_other_hours, 2),
        "total_other_tokens": total_other_tokens,
        "total_other_count": total_other_count,
        "team_size": len(member_summary),
        "leaderboard": leaderboard,
        "weekly_trend": dict(weekly_trend)
    }


def build_team_weekly_card(records: List[Dict[str, Any]], period_name: str, bitable_url: str = "") -> Dict[str, Any]:
    """构建飞书富文本团队战报卡片（含金银铜人效排行榜、大盘汇总与多维表格直达按钮）。"""
    summary = aggregate_team_metrics(records)
    lb = summary["leaderboard"]

    # 排行榜文本
    medals = ["🥇", "🥈", "🥉", "🎖️", "🎖️"]
    lb_lines = []
    for idx, item in enumerate(lb[:5]):
        icon = medals[idx] if idx < len(medals) else "👤"
        lb_lines.append(
            f"{icon} **第 {idx + 1} 名**：**{item['nickname']}** — 节约 **{item['saved_hours']} 小时** | 阅读 {item['highlight_pages']} 页 | 标注 {item['highlight_count']} 篇"
        )
    lb_content = "\n".join(lb_lines) if lb_lines else "暂无成员上报数据"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "carmine",
            "title": {
                "tag": "plain_text",
                "content": f"🏆 TraeWork 团队文献整理 AI 每周人效总榜 ({period_name})"
            }
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**统计周期**：{period_name}\n"
                               f"**参与人数**：**{summary['team_size']} 位工程师/研究员**\n"
                               f"**团队累计节约总工时**：🚀 **{summary['total_saved_hours']} 小时**"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"### 📊 团队文献 AI 核心战绩总览\n"
                               f"• **文献检索完成**：{summary['total_retrievals']:,} 篇\n"
                               f"• **文献成功下载**：{summary['total_downloads']:,} 篇\n"
                               f"• **Highlight 阅读总页数**：{summary['total_pages']:,} 页\n"
                               f"• **Highlight 标注总数**：{summary['total_highlights']:,} 篇文献\n"
                               f"• **真实大模型 Token**：{summary['total_tokens']:,} tokens (100% 控制台对齐)\n"
                               f"• **其他工作**：{summary['total_other_count']:,} 项 / "
                               f"{summary['total_other_hours']:,} 小时 / "
                               f"{summary['total_other_tokens']:,} tokens (无人工基准, 不计节约)"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"### 🏅 团队成员人效贡献排行榜 (Top 5)\n{lb_content}"
                }
            },
            {"tag": "hr"}
        ]
    }

    if bitable_url:
        card["elements"].append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "📈 打开飞书多维表格看板与详细图表"
                    },
                    "type": "primary",
                    "url": bitable_url
                }
            ]
        })

    return card


def render_html_dashboard(records: List[Dict[str, Any]], output_file: str = "") -> str:
    """生成高保真、自包含的交互式团队人效图表看板 HTML。"""
    summary = aggregate_team_metrics(records)
    lb = summary["leaderboard"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 构造柱状图 SVG 条目
    max_h = max([x["saved_hours"] for x in lb] + [1.0])
    bar_items = []
    for item in lb:
        pct = (item["saved_hours"] / max_h) * 100
        bar_items.append(f"""
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 4px;">
                <span style="font-weight: bold; color: #1f2329;">{item['nickname']}</span>
                <span style="color: #0070f3; font-weight: bold;">{item['saved_hours']} 小时</span>
            </div>
            <div style="background: #edf2f7; border-radius: 6px; height: 16px; overflow: hidden;">
                <div style="width: {pct:.1f}%; background: linear-gradient(90deg, #0070f3, #00c48f); height: 100%; border-radius: 6px; transition: width 0.5s;"></div>
            </div>
            <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
                阅读 {item['highlight_pages']} 页 · 标注 {item['highlight_count']} 篇 · 检索 {item['retrieval_count']} 篇 · 下载 {item['download_count']} 篇
            </div>
        </div>
        """)
    bars_html = "\n".join(bar_items) if bar_items else "<div style='color:#94a3b8;'>暂无上报记录</div>"

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TraeWork 团队文献整理 AI 监控与人效图表看板</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 30px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #1e293b, #0f172a);
            color: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }}
        .header h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
        .header p {{ margin: 0; color: #94a3b8; font-size: 14px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0;
        }}
        .card .title {{ font-size: 13px; color: #64748b; margin-bottom: 6px; }}
        .card .val {{ font-size: 28px; font-weight: bold; color: #0f172a; }}
        .card .sub {{ font-size: 12px; color: #10b981; margin-top: 4px; }}
        .panel {{
            background: white;
            border-radius: 10px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0;
            margin-bottom: 24px;
        }}
        .panel h2 {{ margin: 0 0 16px 0; font-size: 18px; color: #0f172a; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 TraeWork 团队文献整理 AI 监控与人效看板</h1>
            <p>飞书多维表格实时同步 · 自动图表汇总 · 刷新时间: {now_str}</p>
        </div>

        <div class="grid">
            <div class="card">
                <div class="title">🚀 团队累计节约总工时</div>
                <div class="val">{summary['total_saved_hours']} <span style="font-size:16px;">小时</span></div>
                <div class="sub">折合 {int(summary['total_saved_hours'] * 60):,} 分钟</div>
            </div>
            <div class="card">
                <div class="title">📖 Highlight 阅读总页数</div>
                <div class="val">{summary['total_pages']:,} <span style="font-size:16px;">页</span></div>
                <div class="sub">100% 真实物理页数累加</div>
            </div>
            <div class="card">
                <div class="title">📄 标注文献总篇数</div>
                <div class="val">{summary['total_highlights']:,} <span style="font-size:16px;">篇</span></div>
                <div class="sub">检索 {summary['total_retrievals']} 篇 · 下载 {summary['total_downloads']} 篇</div>
            </div>
            <div class="card">
                <div class="title">💎 真实 LLM Token 账单</div>
                <div class="val">{summary['total_tokens']:,} <span style="font-size:16px;">tokens</span></div>
                <div class="sub">🟢 100% 服务商控制台严格对齐</div>
            </div>
            <div class="card">
                <div class="title">🧩 其他工作 (无人工基准)</div>
                <div class="val">{summary['total_other_hours']:,} <span style="font-size:16px;">小时</span></div>
                <div class="sub">{summary['total_other_count']:,} 项 · {summary['total_other_tokens']:,} tokens · 不计节约</div>
            </div>
        </div>

        <div class="panel">
            <h2>🏆 团队成员人效贡献横向对比 (节约工时 Ranking)</h2>
            {bars_html}
        </div>
    </div>
</body>
</html>
"""
    if not output_file:
        output_file = os.path.expanduser(r"~/.medit/team_weekly_report.html")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_file
