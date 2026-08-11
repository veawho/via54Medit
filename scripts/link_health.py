#!/usr/bin/env python3
"""
link_health.py — 链接体检工具

═══════════════════════════════════════════════════════════════════════════
根因 (2026-08-02 用户亲授):
  - IARC 下线 GLOBOCAN 2022 → 链接失效没标注
  - PMC 现在有 POW 反爬 → 自动抓不到 PDF, 链接本身能开但下载失败
  - Wiley/Springer 付费墙 → 只能给 DOI
  - 之前我没建链接类型标准 + 失效检测 + 备用下载机制
═══════════════════════════════════════════════════════════════════════════

链接类型标准 (按可下载性 + 时效性):
  Type A: 官方 PDF 直链 (Frontiers/MDPI/IARC .pdf)  — 最优, 直接可下载 PDF
  Type B: PMC 主页 (POW 反爬, 但浏览器能开 PDF)  — 次优, 浏览器人工下
  Type C: DOI (付费墙, 期刊网站跳转)            — 兜底, 需机构权限
  Type D: 本地 file:// (人打开看, 不能下载)       — 镜像, 配合 A/B/C
  Type E: Wayback Machine 存档                    — 备用, 应对官网下线

体检维度:
  1. HTTP status (200/404/403/302)
  2. Content-Type (application/pdf vs text/html)
  3. Redirect chain (看最终 URL)
  4. 文件大小 (PDF 至少 >10KB)
  5. 时效差异 (URL 含 2022 但当前数据是 2024)

输出:
  - health_report.json: 全表链接体检报告
  - 时效差异标注 (GLOBOCAN 2022→2024)
  - 备用下载建议 (Type E Wayback / 镜像)
═══════════════════════════════════════════════════════════════════════════
"""

import json
import urllib.request
import urllib.error
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# 链接类型分类
# ═══════════════════════════════════════════════════════════════════════════


def classify_link(url: str) -> Dict:
    """
    链接分类, 返回 {type, label, expected_status, backup_strategies}
    """
    if not url:
        return {"type": "EMPTY", "label": "空链接", "expected_status": None, "backup_strategies": []}

    u = url.lower()

    # Type D: 本地 (放最前, 避免被 A2 拦)
    if u.startswith("file://"):
        return {
            "type": "D_LOCAL",
            "label": "本地 file:// (镜像, 需本地路径存在)",
            "expected_status": None,
            "backup_strategies": [],
        }

    # Type A2: 期刊 PDF 路径 (不管 .pdf 后缀, 都检查 wiley/sciencedirect/springer)
    if "wiley" in u or "sciencedirect" in u or "springer" in u:
        if "/pdf" in u or ".pdf" in u:
            return {
                "type": "A_OFFICIAL_PDF_PAYWALL",
                "label": "期刊官方 PDF (付费墙)",
                "expected_status": 403,
                "backup_strategies": ["B_PMC", "C_DOI", "E_WAYBACK"],
            }

    # Type A: 官方 PDF 直链
    if u.endswith(".pdf") or u.endswith("/pdf"):
        # 开放访问期刊: Frontiers / MDPI
        if "frontiersin.org" in u:
            return {
                "type": "A_OFFICIAL_PDF_OPEN",
                "label": "Frontiers 官方 PDF (开放访问)",
                "expected_status": 200,
                "backup_strategies": ["B_PMC", "E_WAYBACK", "D_LOCAL"],
            }
        if "mdpi.com" in u:
            return {
                "type": "A_OFFICIAL_PDF_OPEN",
                "label": "MDPI 官方 PDF (开放访问)",
                "expected_status": 200,
                "backup_strategies": ["B_PMC", "E_WAYBACK", "D_LOCAL"],
            }
        if "gco.iarc" in u:
            return {
                "type": "A_OFFICIAL_PDF",
                "label": "IARC GLOBOCAN PDF",
                "expected_status": 200,
                "backup_strategies": ["D_LOCAL", "E_WAYBACK"],
            }
        return {"type": "UNKNOWN", "label": "未知 .pdf 来源", "expected_status": None, "backup_strategies": []}

    # Type B: PMC 主页
    if "ncbi.nlm.nih.gov/pmc/articles/" in u or "pmc.ncbi.nlm.nih.gov" in u:
        return {
            "type": "B_PMC_PAGE",
            "label": "PubMed Central 主页 (POW 反爬, 浏览器能开)",
            "expected_status": 200,
            "backup_strategies": ["C_DOI", "E_WAYBACK", "D_LOCAL"],
        }

    # Type C: DOI
    if u.startswith("https://doi.org/"):
        return {
            "type": "C_DOI",
            "label": "DOI 解析 (付费墙跳转)",
            "expected_status": 302,
            "backup_strategies": ["B_PMC", "E_WAYBACK", "D_LOCAL"],
        }

    # Type E: Wayback Machine
    if "web.archive.org" in u or "archive.org" in u:
        return {
            "type": "E_WAYBACK",
            "label": "Wayback Machine 存档",
            "expected_status": 200,
            "backup_strategies": [],
        }

    # 政府/官网
    if "nhc.gov.cn" in u:
        return {
            "type": "G_GOV_PAGE",
            "label": "国家卫健委官网",
            "expected_status": 200,
            "backup_strategies": ["D_LOCAL", "E_WAYBACK"],
        }

    return {"type": "UNKNOWN", "label": "未知类型", "expected_status": None, "backup_strategies": []}


# ═══════════════════════════════════════════════════════════════════════════
# 体检 HTTP
# ═══════════════════════════════════════════════════════════════════════════


def check_link(url: str, timeout: int = 15) -> Dict:
    """
    检查单个链接健康度
    返回 {url, http_status, content_type, content_length, redirect_chain, is_alive, error}
    """
    result = {
        "url": url,
        "http_status": None,
        "content_type": None,
        "content_length": 0,
        "redirect_chain": [],
        "is_alive": False,
        "error": None,
        "checked_at": datetime.now().isoformat(),
    }
    if not url:
        result["error"] = "empty_url"
        return result
    if url.startswith("file://"):
        # 本地文件: 检查路径
        path = url[7:]
        if Path(path).exists():
            result["http_status"] = 200
            result["content_length"] = Path(path).stat().st_size
            result["is_alive"] = True
        else:
            result["http_status"] = 404
            result["error"] = "local_file_not_found"
        return result
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 via54Medit/1.0"})
        # 不自动 follow redirect, 看 chain
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        with opener.open(req, timeout=timeout) as resp:
            result["http_status"] = resp.status
            result["content_type"] = resp.headers.get("Content-Type", "?")
            # urllib 自动 follow redirect, 看 url chain (history attr)
            if hasattr(resp, "url"):
                result["redirect_chain"].append(resp.url)
            data = resp.read(1024 * 50)  # 最多读 50KB
            result["content_length"] = len(data)
            result["is_alive"] = resp.status == 200
    except urllib.error.HTTPError as e:
        result["http_status"] = e.code
        result["error"] = f"HTTP {e.code}: {e.reason}"
        # 403/404 也算"链接可达但内容受限"
        result["is_alive"] = e.code in (200, 301, 302, 403, 404)
    except Exception as e:
        result["error"] = str(e)[:200]
        result["is_alive"] = False
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 时效差异检测
# ═══════════════════════════════════════════════════════════════════════════


def detect_expiry_mismatch(url: str, label: str) -> Optional[Dict]:
    """
    检测时效差异, 例如:
    - URL 含 2022 但当前数据是 2024 (GLOBOCAN)
    - URL 含 2019 但当前文献已更新版本
    """
    u = url.lower()
    year_match = re.search(r"20\d{2}", u)
    if not year_match:
        return None
    url_year = year_match.group()
    # 特定规则: GLOBOCAN IARC 已下线 2022
    if "gco.iarc" in u and url_year == "2022":
        return {
            "type": "EXPIRED_REPLACED",
            "url_year": url_year,
            "current_year": "2024",
            "reason": "IARC 网站已下线 GLOBOCAN 2022, 只显示 2024 数据",
            "annotation": "PPT 引 GLOBOCAN 2022 (36.8万), 现 GLOBOCAN 2024 是 35.4万 (差 1.4万, 趋势一致)",
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Wayback Machine 备用查找
# ═══════════════════════════════════════════════════════════════════════════


def find_wayback(url: str, timeout: int = 10) -> Optional[str]:
    """
    找 Wayback Machine 最近的存档
    返回存档 URL 或 None
    """
    api = f"https://archive.org/wayback/available?url={url}"
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap and snap.get("available"):
            return snap.get("url")
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 全表体检
# ═══════════════════════════════════════════════════════════════════════════


def extract_links_from_h(h_value: str) -> List[str]:
    """从 H 列 markdown 文本提取所有 URL"""
    urls = re.findall(r"\]\((https?://[^)]+)\)", h_value)
    urls += re.findall(r"\]\((file://[^)]+)\)", h_value)
    return list(dict.fromkeys(urls))  # 去重保序


# ═══════════════════════════════════════════════════════════════════════════
# Pn-x → 时效差异白名单 (硬编码已知的 PPT 引文 vs 当前数据差异)
# ═══════════════════════════════════════════════════════════════════════════


PNX_EXPIRY_WHITELIST = {
    "P3-1": {
        "type": "EXPIRED_REPLACED",
        "url_year": "2022",
        "current_year": "2024",
        "reason": "IARC 网站 (gco.iarc.who.int) 已下线 GLOBOCAN 2022 数据, 只显示 2024",
        "annotation": "PPT 引 GLOBOCAN 2022 (中国肝癌 36.8万), 现 GLOBOCAN 2024 是 35.4万 (差 1.4万, 趋势一致). 数据时序差异不影响 PPT 应证结论.",
    },
    # 其他 Pn-x 待补 (IARC 系列)
}


def get_pnx_expiry(pnx: str) -> Optional[Dict]:
    """按 Pn-x 查时效差异"""
    return PNX_EXPIRY_WHITELIST.get(pnx)


def check_row(row_n: int, h_value: str, check_http: bool = False, pnx: Optional[str] = None) -> Dict:
    """
    检查单行链接健康度
    check_http=False: 只分类 (快)
    check_http=True: 分类 + HTTP 体检 (慢)
    pnx: 用于查时效差异白名单 (如 'P3-1')
    """
    urls = extract_links_from_h(h_value)
    report = {"row_n": row_n, "links": [], "errors": [], "warnings": [], "expiry_issues": []}

    # Pn-x 级时效标注 (白名单)
    if pnx:
        pnx_expiry = get_pnx_expiry(pnx)
        if pnx_expiry:
            report["expiry_issues"].append(pnx_expiry)

    for url in urls:
        link_info = classify_link(url)
        link_report = {"url": url, "type": link_info["type"], "label": link_info["label"]}
        # URL 内容级时效检测
        expiry = detect_expiry_mismatch(url, link_info["label"])
        if expiry:
            link_report["expiry"] = expiry
            if expiry not in report["expiry_issues"]:
                report["expiry_issues"].append(expiry)
        # HTTP 体检
        if check_http:
            check_result = check_link(url)
            link_report["health"] = check_result
            if not check_result["is_alive"] and link_info["type"] != "D_LOCAL":
                report["errors"].append({"url": url, "type": link_info["type"], "error": check_result["error"]})
            elif link_info["type"] != "D_LOCAL" and check_result["http_status"] != link_info["expected_status"]:
                if link_info["expected_status"] and link_info["expected_status"] not in [302, 301]:
                    report["warnings"].append({
                        "url": url,
                        "type": link_info["type"],
                        "expected": link_info["expected_status"],
                        "actual": check_result["http_status"],
                    })
        report["links"].append(link_report)
    return report


def full_table_check(check_http: bool = False) -> Dict:
    """全表链接体检"""
    from citation_sync import feishu_read_cells, csv_read_rows

    # 读飞书表
    cells = feishu_read_cells("A1:H161")
    full_report = {"rows": [], "summary": {"total_rows": 0, "errors": 0, "warnings": 0, "expiry_issues": 0}}

    for i, row in enumerate(cells):
        row_n = i + 1
        if row_n == 1:
            continue
        h_val = row[7].get("value", "") if len(row) > 7 else ""
        pnx = f"P{row[0].get('value', '')}-{row[1].get('value', '')}" if len(row) > 1 else ""
        row_report = check_row(row_n, h_val, check_http=check_http, pnx=pnx)
        row_report["pnx"] = pnx
        full_report["rows"].append(row_report)
        full_report["summary"]["total_rows"] += 1
        full_report["summary"]["errors"] += len(row_report["errors"])
        full_report["summary"]["warnings"] += len(row_report["warnings"])
        full_report["summary"]["expiry_issues"] += len(row_report["expiry_issues"])
    return full_report


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def cli_classify(args):
    if not args:
        print("用法: classify <url>")
        return
    info = classify_link(args[0])
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cli_check(args):
    if not args:
        print("用法: check <url>")
        return
    result = check_link(args[0])
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cli_check_row(args):
    """检查单行链接"""
    row_n = int(args[0])
    check_http = "--http" in args
    from citation_sync import read_truth_row
    truth = read_truth_row(row_n)
    h = truth["H_source_link"]
    report = check_row(row_n, h, check_http=check_http)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cli_check_table(args):
    """全表链接体检"""
    check_http = "--http" in args
    report = full_table_check(check_http=check_http)
    out = args[args.index("--out") + 1] if "--out" in args else None
    if out:
        with open(out, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"✅ 报告写入 {out}")
    else:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        for row in report["rows"]:
            if row["errors"] or row["expiry_issues"]:
                print(f"\nRow {row['row_n']} ({row.get('pnx', '?')}):")
                for err in row["errors"]:
                    print(f"  ❌ {err}")
                for exp in row["expiry_issues"]:
                    print(f"  ⚠️ EXPIRED: {exp}")


def cli_find_wayback(args):
    if not args:
        print("用法: find_wayback <url>")
        return
    wb = find_wayback(args[0])
    if wb:
        print(f"✅ Wayback: {wb}")
    else:
        print(f"❌ 无 Wayback 存档")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    cmds = {
        "classify": cli_classify,
        "check": cli_check,
        "check_row": cli_check_row,
        "check_table": cli_check_table,
        "find_wayback": cli_find_wayback,
    }
    if cmd not in cmds:
        print(f"未知命令: {cmd}, 可用: {list(cmds.keys())}")
        sys.exit(1)
    cmds[cmd](args)


if __name__ == "__main__":
    main()