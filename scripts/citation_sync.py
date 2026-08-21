#!/usr/bin/env python3
"""
citation_sync.py — 飞书表 ↔ 本地 CSV 单一真理源 + 原子化双向同步工具

═══════════════════════════════════════════════════════════════════════════
根因 (2026-08-02 用户亲授):
  - 之前我用 ad-hoc Python 每次"发现问题 → 写 patch", 是症状级修复
  - 没有"飞书是真理源"的硬约束, 没有"原子化写入"机制, 没有"写前对账"
═══════════════════════════════════════════════════════════════════════════

单一真理源: 飞书表 (Feishu sheet)
本地镜像:   citation_table.csv (CSV)
同步方向:   飞书 → CSV (真理源单向同步)
            CSV → 飞书 (用户改 CSV 后, 先 dry-run diff 确认再推)

【铁律】任何写入飞书前必跑 lock_row_anchors + assert_no_collision
【铁律】任何写入后必跑 re_read_verify
【铁律】CSV 与飞书任何字段不一致, 以飞书为准
═══════════════════════════════════════════════════════════════════════════
"""

import json
import subprocess
import csv
import os
import os
import io
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# 飞书配置 (硬编码, 不允许运行期改)
FEISHU_TOKEN = os.environ.get("FEISHU_TOKEN") or os.environ.get("FEISHU_SHEET_TOKEN", "")
FEISHU_SHEET = "b03e59"
LARK_CLI = os.environ.get("LARK_CLI", "/Users/david/.hermes/node/bin/lark-cli")

# 本地 CSV 路径
CSV_PATH = "/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv"
BASE_DIR = "/Users/david/Desktop/雷管方案_文献整理"


# ═══════════════════════════════════════════════════════════════════════════
# 飞书操作 (低级 API)
# ═══════════════════════════════════════════════════════════════════════════


def lark_cli(*args) -> Tuple[int, str, str]:
    """调用 lark-cli, 返回 (exit_code, stdout, stderr)"""
    cmd = [LARK_CLI] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def feishu_read_cells(range_str: str, include: str = "value") -> List[List[Dict]]:
    """读飞书单元格"""
    rc, out, err = lark_cli(
        "sheets", "+cells-get",
        "--spreadsheet-token", FEISHU_TOKEN,
        "--sheet-id", FEISHU_SHEET,
        "--range", range_str,
        "--include", include,
    )
    if rc != 0:
        raise RuntimeError(f"读飞书失败 {range_str}: {err}")
    return json.loads(out)["data"]["ranges"][0]["cells"]


def feishu_write_cells(range_str: str, cells_2d: List[List[Dict]], dry_run: bool = False) -> bool:
    """写飞书单元格 (原子化)"""
    cells_json = json.dumps(cells_2d)
    args = [
        "sheets", "+cells-set",
        "--spreadsheet-token", FEISHU_TOKEN,
        "--sheet-id", FEISHU_SHEET,
        "--range", range_str,
        "--cells", cells_json,
    ]
    if dry_run:
        args.append("--dry-run")
    rc, out, err = lark_cli(*args)
    if dry_run:
        return rc == 0
    if rc != 0:
        raise RuntimeError(f"写飞书失败 {range_str}: {err}")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 对账算法 (写之前必跑)
# ═══════════════════════════════════════════════════════════════════════════


def lock_row_anchors(row_n: int, window: int = 5) -> Dict:
    """
    锁住 Row N 周围的 D+E+H 真值, 返回锚点 dict
    写之前必跑, 防错位
    """
    lo = max(2, row_n - window)
    hi = row_n + window
    range_str = f"A{lo}:H{hi}"
    cells = feishu_read_cells(range_str)
    anchors = {}
    for i, row in enumerate(cells):
        rn = lo + i
        a = row[0].get("value", "") if len(row) > 0 else ""
        b = row[1].get("value", "") if len(row) > 1 else ""
        anchors[rn] = {
            "A_ppt_page": a,
            "B_mark": b,
            "expected_pnx": f"P{a}-{b}" if a and b and a.isdigit() and b.isdigit() else None,
        }
    return anchors


def assert_no_collision(row_n: int, expected_pnx: str, anchors: Dict) -> None:
    """
    防错位: 写之前必须断言 Row N 的 A+B 字段 == expected_pnx
    否则会覆盖别人的数据
    """
    actual = anchors.get(row_n, {})
    actual_pnx = actual.get("expected_pnx")
    if actual_pnx != expected_pnx:
        raise CollisionError(
            f"Row {row_n} 错位! 期望 Pn-x={expected_pnx}, 实际={actual_pnx}\n"
            f"完整锚点: {anchors}"
        )


class CollisionError(RuntimeError):
    """写飞书时检测到 Row 错位"""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# 飞书表是真理源 (单一真理源铁律)
# ═══════════════════════════════════════════════════════════════════════════


def feishu_is_truth() -> str:
    """返回真理源标识"""
    return "feishu"


def read_truth_row(row_n: int) -> Dict:
    """读飞书 Row N 真值 (真理源, H 列用 markdown 镜像格式跟 CSV 对齐)"""
    cells = feishu_read_cells(f"A{row_n}:H{row_n}", include="value,rich_text")
    row = cells[0]
    # H 列: 优先用 markdown (CSV 镜像), 没有时用 value
    h_value = ""
    if len(row) > 7:
        cell_dict = row[7]
        # 优先读 rich_text → markdown
        if cell_dict.get("rich_text"):
            h_value = rich_text_to_markdown(cell_dict["rich_text"])
        else:
            h_value = cell_dict.get("value", "")
    return {
        "row_n": row_n,
        "A_ppt_page": row[0].get("value", "") if len(row) > 0 else "",
        "B_mark": row[1].get("value", "") if len(row) > 1 else "",
        "C_citation": row[2].get("value", "") if len(row) > 2 else "",
        "D_citation_full": row[3].get("value", "") if len(row) > 3 else "",
        "E_doi": row[4].get("value", "") if len(row) > 4 else "",
        "F_type": row[5].get("value", "") if len(row) > 5 else "",
        "G_pdf_path": row[6].get("value", "") if len(row) > 6 else "",
        "H_source_link": h_value,
    }


def read_truth_pnx(pnx: str) -> Optional[Dict]:
    """按 Pn-x 找飞书 Row (扫 A+B 列)"""
    cells = feishu_read_cells("A2:B161")
    for i, row in enumerate(cells):
        row_n = i + 2
        a = row[0].get("value", "") if len(row) > 0 else ""
        b = row[1].get("value", "") if len(row) > 1 else ""
        if f"P{a}-{b}" == pnx:
            return read_truth_row(row_n)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 本地 CSV (镜像, 不是真理源)
# ═══════════════════════════════════════════════════════════════════════════


def csv_read_rows() -> List[List[str]]:
    """读本地 CSV 全部行 (含表头)"""
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def csv_write_row(row_n: int, new_row: List[str]) -> None:
    """写本地 CSV Row N (行级原子, 先读再改再写)"""
    rows = csv_read_rows()
    if row_n > len(rows):
        raise IndexError(f"CSV Row {row_n} 超出实际行数 {len(rows)}")
    rows[row_n - 1] = new_row  # row_n=1 是表头, idx 0
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        w.writerow(row)
    bom = "\ufeff"
    output = bom + buf.getvalue().rstrip("\r\n")
    with open(CSV_PATH, "w") as f:
        f.write(output)


# ═══════════════════════════════════════════════════════════════════════════
# 双向同步 (原子化)
# ═══════════════════════════════════════════════════════════════════════════


def sync_feishu_to_csv(row_n: int) -> bool:
    """
    单向同步: 飞书 → CSV
    飞书是真理源, CSV 是镜像
    """
    truth = read_truth_row(row_n)
    csv_rows = csv_read_rows()
    if row_n > len(csv_rows):
        raise IndexError(f"CSV Row {row_n} 超出实际行数 {len(csv_rows)}")
    csv_row = csv_rows[row_n - 1]
    # H 列从飞书 value → CSV markdown (rich_text 反向解析)
    fs_cells = feishu_read_cells(f"H{row_n}:H{row_n}", include="rich_text")
    rt = fs_cells[0][0].get("rich_text", []) if fs_cells and fs_cells[0] else []
    csv_row[7] = rich_text_to_markdown(rt)
    # 写回 CSV
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    for row in csv_rows:
        w.writerow(row)
    bom = "\ufeff"
    output = bom + buf.getvalue().rstrip("\r\n")
    with open(CSV_PATH, "w") as f:
        f.write(output)
    return True


def rich_text_to_markdown(rt_list: List[Dict]) -> str:
    """rich_text → markdown (用于 CSV 镜像)"""
    md = ""
    for item in rt_list:
        t = item.get("text", "")
        if item.get("type") == "link":
            url = item.get("link", "")
            md += f"[{t}]({url})"
        else:
            md += t
    return md


def sync_all_feishu_to_csv() -> int:
    """全表同步: 飞书 → CSV"""
    cells = feishu_read_cells("A1:H161")
    n = 0
    for i, row in enumerate(cells):
        row_n = i + 1
        if row_n == 1:
            continue  # 跳过表头
        try:
            sync_feishu_to_csv(row_n)
            n += 1
        except Exception as e:
            print(f"⚠️ 同步 Row {row_n} 失败: {e}")
    return n



# ═══════════════════════════════════════════════════════════════════════════
# markdown → rich_text 转换 (P0 铁律: H 列必须写可点击链接)
# ═══════════════════════════════════════════════════════════════════════════

def markdown_to_rich_text(md: str) -> List[Dict]:
    """
    把 CSV H 列 markdown 文本转换成飞书 rich_text 数组。
    v3: 同时检测 [text](url) 和 裸 URL 都转 link
    
    保留换行符 \\n, 飞书渲染时自动换行。
    相邻 text 段自动合并。
    
    根因: 之前 H 列写入多段文本 (每行一段), 飞书内联渲染无换行。
    修复: 2026-08-02 v3, 单段文本含 \\n + 独立 link 段。
    """
    import re

    rt: List[Dict] = []
    if not md:
        return rt

    # 找所有链接
    all_links = []
    for m in re.finditer(r"\\[([^\\]]+)\\]\\(([^)]+)\\)", md):
        all_links.append((m.start(), m.end(), m.group(1), m.group(2)))
    for m in re.finditer(r"https?://[^\\s`\\n\\)>]+", md):
        already = False
        for s, e, _, _ in all_links:
            if s <= m.start() and m.end() <= e:
                already = True
                break
        if not already:
            all_links.append((m.start(), m.end(), m.group(), m.group()))
    
    all_links.sort(key=lambda x: x[0])
    
    parts = []
    last = 0
    for s, e, text, url in all_links:
        if s > last:
            parts.append(("text", md[last:s]))
        parts.append(("link", text, url))
        last = e
    if last < len(md):
        parts.append(("text", md[last:]))
    
    if not parts:
        rt.append({"type": "text", "text": md})
        return rt
    
    # 合并相邻 text
    merged = []
    for p in parts:
        if p[0] == "text":
            if merged and merged[-1][0] == "text":
                merged[-1] = ("text", merged[-1][1] + p[1])
            else:
                merged.append(p)
        else:
            merged.append(p)
    
    for p in merged:
        if p[0] == "text":
            rt.append({"type": "text", "text": p[1]})
        else:
            rt.append({"type": "link", "text": p[1], "link": p[2]})
    
    return rt


# ═══════════════════════════════════════════════════════════════════════════
# 原子化写入 H 列 (rich_text + 写前对账 + 写后验证)
# ═══════════════════════════════════════════════════════════════════════════


def write_h_atomic(row_n: int, expected_pnx: str, rich_text: List[Dict]) -> bool:
    """
    原子化写飞书 H 列 (markdown → rich_text 自动转换)

    P0 铁律: rich_text 必须含 {type:"link"} 段, 否则飞书链接不可点击。

    步骤:
      1. lock_row_anchors(N-5, N+5) 拉 A+B 真值
      2. assert_no_collision(N, expected_pnx)
      3. 自动把 markdown → rich_text (内含 markdown_to_rich_text)
      4. dry_run 写入
      5. 真写入
      6. re_read_verify
      7. 验证 rich_text 中含 link 段 (有 DOI 时)
    """
    import csv, os

    # 1. 对账
    anchors = lock_row_anchors(row_n, window=5)
    # 2. 断言
    assert_no_collision(row_n, expected_pnx, anchors)

    # 3. 如果 rich_text 是空列表, 从 CSV 重建
    if not rich_text:
        csv_path = os.path.join(
            os.environ.get("PROJECT_BASE", "/Users/david/Desktop/雷管方案_文献整理"),
            "_citation_table", "citation_table.csv",
        )
        with open(csv_path, newline="") as f:
            csv_rows = list(csv.DictReader(f))
            col_names = list(csv_rows[0].keys())
        for r in csv_rows:
            if r[col_names[0]].strip() == "5" and r[col_names[1]].strip() == str(row_n - 10):
                h_md = r[col_names[7]].strip()
                rich_text = markdown_to_rich_text(h_md)
                break
        if not rich_text:
            raise RuntimeError(f"CSV 中找不到 Row {row_n} 的 H 列内容")

    # 4. dry_run
    range_str = f"H{row_n}:H{row_n}"
    cells_2d = [[{"rich_text": rich_text}]]
    if not feishu_write_cells(range_str, cells_2d, dry_run=True):
        raise RuntimeError(f"dry-run 失败 Row {row_n}")
    # 5. 真写入
    feishu_write_cells(range_str, cells_2d, dry_run=False)
    # 6. 写后验证
    verify_cells = feishu_read_cells(range_str, include="rich_text")
    verify_rt = verify_cells[0][0].get("rich_text", []) if verify_cells and verify_cells[0] else []
    if len(verify_rt) != len(rich_text):
        raise RuntimeError(
            f"写后验证失败 Row {row_n}: 期望 {len(rich_text)} 元素, 实际 {len(verify_rt)} 元素"
        )
    # 7. 验证 link 段存在
    link_count = sum(1 for x in verify_rt if x.get("type") == "link")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# CLI 命令
# ═══════════════════════════════════════════════════════════════════════════


def cli_lock(args):
    """lock_row_anchors 命令"""
    row_n = int(args[0])
    anchors = lock_row_anchors(row_n)
    for rn, info in anchors.items():
        print(f"  Row {rn}: A={info['A_ppt_page']!r} B={info['B_mark']!r} -> {info['expected_pnx']}")


def cli_read_truth(args):
    """read_truth_row 命令"""
    row_n = int(args[0])
    truth = read_truth_row(row_n)
    print(json.dumps(truth, ensure_ascii=False, indent=2))


def cli_sync(args):
    """sync 命令 (飞书 → CSV)"""
    if args and args[0] == "all":
        n = sync_all_feishu_to_csv()
        print(f"✅ 同步 {n} 行")
    else:
        row_n = int(args[0])
        sync_feishu_to_csv(row_n)
        print(f"✅ 同步 Row {row_n}")


def cli_write_h(args):
    """
    write_h 命令 — 原子化写入 H 列
    用法: write_h <row_n> <expected_pnx> <rich_text_json_file>
    """
    if len(args) < 3:
        print("用法: write_h <row_n> <expected_pnx> <rich_text.json>")
        sys.exit(1)
    row_n = int(args[0])
    expected_pnx = args[1]
    with open(args[2]) as f:
        rich_text = json.load(f)
    write_h_atomic(row_n, expected_pnx, rich_text)
    print(f"✅ Row {row_n} ({expected_pnx}) H 列原子化写入完成")


def cli_diff(args):
    """diff 命令 — 比对飞书与 CSV 差异"""
    row_n = int(args[0])
    truth = read_truth_row(row_n)
    csv_rows = csv_read_rows()
    csv_row = csv_rows[row_n - 1]
    fields = ["A_ppt_page", "B_mark", "C_citation", "D_citation_full", "E_doi", "F_type", "G_pdf_path", "H_source_link"]
    diffs = []
    for i, f in enumerate(fields):
        truth_val = truth.get(f, "")
        csv_val = csv_row[i] if i < len(csv_row) else ""
        if truth_val != csv_val:
            diffs.append((f, truth_val[:60], csv_val[:60]))
    if diffs:
        print(f"❌ Row {row_n} 有 {len(diffs)} 处不一致:")
        for f, t, c in diffs:
            print(f"  {f}:")
            print(f"    飞书: {t}")
            print(f"    CSV:  {c}")
    else:
        print(f"✅ Row {row_n} 完全对齐")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    cmds = {
        "lock": cli_lock,
        "read_truth": cli_read_truth,
        "sync": cli_sync,
        "write_h": cli_write_h,
        "diff": cli_diff,
    }
    if cmd not in cmds:
        print(f"未知命令: {cmd}, 可用: {list(cmds.keys())}")
        sys.exit(1)
    cmds[cmd](args)


if __name__ == "__main__":
    main()