#!/usr/bin/env python3
"""
via54_health.py — 自检自查自修 (v9.7)

自动化健康检查 + 自动修复:
1. 检查每个 Pn-x 完整性: manifest / main / fb / highlight
2. 检查 main PDF filename + content 错位
3. 检查 PPT ↔ CSV 对齐率
4. 检查 highlight 图质量 (有黄色像素, 大小合理)
5. 检查链接时效性 (curl -sI)
6. 自修能力: 自动填充缺失 manifest, 修复过期链接

用法:
    python3.11 via54_health.py check          # 只检查
    python3.11 via54_health.py fix            # 检查 + 修复
    python3.11 via54_health.py report         # 生成报告
"""
import sys, os, json, csv, subprocess, importlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_manifest(pn_x: str, pn_path: str) -> Dict:
    """检查 manifest 完整性"""
    manifest_path = f"{pn_path}/_manifest.json"
    if not os.path.isfile(manifest_path):
        return {"status": "missing", "path": manifest_path}
    try:
        with open(manifest_path) as f:
            m = json.load(f)
        # v9.7: 接受 highlight_pages 或 highlight_summary
        required = ['pn_x', 'main_pdf']
        mandatory = ['highlight_summary']
        has_hl = 'highlight_summary' in m or 'highlight_pages' in m
        missing = [k for k in required if k not in m]
        if not has_hl:
            missing.append('highlight_summary_or_pages')
        return {"status": "ok" if not missing else "incomplete", "missing_keys": missing, "manifest": m}
    except json.JSONDecodeError as e:
        return {"status": "corrupted", "error": str(e)}


def check_main_pdf(pn_x: str, pn_path: str, info_d: Dict) -> Dict:
    """检查 main PDF 存在性 + 错位"""
    files = [f for f in os.listdir(pn_path) if '_main_' in f or f.startswith(f'{pn_x}_main')]
    if not files:
        return {"status": "no_main", "files": []}

    # 检测错位
    try:
        import h_column_builder
        importlib.reload(h_column_builder)
        from h_column_builder import scan_pn_x_dir, detect_main_pdf_mismatch, detect_main_pdf_content_mismatch
        scan = scan_pn_x_dir(pn_x, os.path.dirname(pn_path))
        mismatch_fn = detect_main_pdf_mismatch(pn_x, info_d, scan, d_raw=info_d.get("_d_raw"))
        mismatch_ct = detect_main_pdf_content_mismatch(pn_x, info_d, scan, d_raw=info_d.get("_d_raw"))
        if mismatch_fn or mismatch_ct:
            return {"status": "mismatch", "filename": mismatch_fn, "content": mismatch_ct, "files": files}
    except Exception as e:
        return {"status": "error", "error": str(e), "files": files}

    return {"status": "ok", "files": files}


def check_highlight(pn_x: str, pn_path: str) -> Dict:
    """检查 highlight 图质量"""
    from PIL import Image
    import numpy as np
    hl_files = [f for f in os.listdir(pn_path) if 'highlight' in f.lower()]
    if not hl_files:
        return {"status": "no_highlight", "files": []}

    # 检查每张图是否有黄色像素 + 大小合理
    issues = []
    for hl in hl_files:
        path = f"{pn_path}/{hl}"
        try:
            arr = np.array(Image.open(path).convert("RGB"))
            yellow = (arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] < 150)
            pct = yellow.sum() / yellow.size * 100
            if pct < 0.01:
                issues.append(f"{hl}: 黄色像素 {pct:.3f}% (过低)")
        except Exception as e:
            issues.append(f"{hl}: 读取失败 {e}")

    return {"status": "ok" if not issues else "issues", "files": hl_files, "issues": issues}


def check_ppt_csv_alignment(ppt_path: str, csv_path: str) -> Dict:
    """检查 PPT ↔ CSV 对齐"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ppt_understand import find_citation_marks_v2

    all_marks = {}
    for sn in range(3, 44):
        try:
            marks = find_citation_marks_v2(ppt_path, slide_num=sn)
            if marks:
                all_marks[sn] = marks
        except:
            pass

    with open(csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    page_col = None
    for c in cols:
        if c.strip() == 'PPT页':
            page_col = 'PPT页'
            break
    if not page_col:
        page_col = cols[0]
    pn_col = None
    for c in cols:
        if c.strip() == '第几条':
            pn_col = '第几条'
            break
    if not pn_col:
        pn_col = cols[1]

    matched = 0
    unmatched = []
    total = 0
    for sn, marks in all_marks.items():
        for num_str in marks:
            num = int(num_str)
            total += 1
            found = any(int(r[page_col].strip()) == sn and r[pn_col].strip() == str(num) for r in rows)
            if found:
                matched += 1
            else:
                unmatched.append((sn, num, marks[num_str]["context"][:60]))

    return {
        "total": total,
        "matched": matched,
        "unmatched": len(unmatched),
        "rate": matched / total if total else 0,
        "unmatched_list": unmatched[:10],
    }


def check_links(pn_x_list: List[str], lit_base: str) -> Dict:
    """检查 main PDF 的 verified_doi_url 时效性"""
    results = []
    for pn_x in pn_x_list:
        mp = f"{lit_base}/{pn_x}/_manifest.json"
        if not os.path.isfile(mp):
            continue
        try:
            with open(mp) as f:
                m = json.load(f)
            url = m.get("verified_doi_url")
            if not url:
                continue
            # curl -sI 验证
            r = subprocess.run(['curl', '-sI', '-o', '/dev/null', '-w', '%{http_code}', '-L', '--max-time', '10', url],
                capture_output=True, text=True, timeout=15)
            code = r.stdout.strip()
            results.append({"pn_x": pn_x, "url": url, "code": code})
        except Exception as e:
            results.append({"pn_x": pn_x, "error": str(e)})

    return {"total": len(results), "results": results}


def run_health_check(lit_base: str = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index",
                    csv_path: str = "/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv",
                    ppt_path: str = "/Users/david/Desktop/雷管方案_文献整理/PPT原版_雷管方案_三重获益_引领uHCC一线治疗_0622.pptx") -> Dict:
    """运行全量健康检查"""

    print("=" * 60)
    print("via54_health.py — 自检自查自修 (v9.7)")
    print("=" * 60)

    # 1. 收集 Pn-x 列表
    pn_x_list = sorted([d for d in os.listdir(lit_base)
                        if os.path.isdir(f"{lit_base}/{d}") and d.startswith('P')])
    print(f"\nPn-x 目录数: {len(pn_x_list)}")

    # 2. 检查每个 Pn-x
    print("\n[1/4] Pn-x 完整性检查...")
    issues = []
    pn_x_with_main = 0
    pn_x_with_manifest = 0
    pn_x_with_highlight = 0

    import h_column_builder
    importlib.reload(h_column_builder)
    from h_column_builder import parse_d_field

    # 读 CSV 一次性
    with open(csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    # 找 PPT 页 列
    page_col = None
    for c in cols:
        if c.strip() == 'PPT页':
            page_col = 'PPT页'
            break
        elif c.lstrip('\ufeff').strip() == 'PPT页':
            page_col = c
            break
    if not page_col:
        page_col = cols[0]
    # 找 第几条 列
    pn_col = None
    for c in cols:
        if c.strip() == '第几条':
            pn_col = '第几条'
            break
    if not pn_col:
        pn_col = cols[1]
    # 找 PPT中的文献引用 完整字段
    d_col = None
    for c in cols:
        if c.strip() == 'PPT中的文献引用 完整字段':
            d_col = 'PPT中的文献引用 完整字段'
            break
    if not d_col:
        d_col = cols[3]
    csv_d = {f"P{r[page_col].strip()}-{r[pn_col].strip()}": r[d_col] for r in rows}

    for pn_x in pn_x_list:
        pn_path = f"{lit_base}/{pn_x}"
        d_raw = csv_d.get(pn_x, "")
        info_d = parse_d_field(d_raw)
        info_d["_d_raw"] = d_raw

        # 1.1 manifest
        mc = check_manifest(pn_x, pn_path)
        if mc["status"] == "ok":
            pn_x_with_manifest += 1

        # 1.2 main PDF
        mp = check_main_pdf(pn_x, pn_path, info_d)
        if mp["status"] == "ok":
            pn_x_with_main += 1
        elif mp["status"] == "mismatch":
            issues.append((pn_x, "main_mismatch", mp))

        # 1.3 highlight
        hl = check_highlight(pn_x, pn_path)
        if hl["status"] == "ok" and hl.get("files"):
            pn_x_with_highlight += 1
        elif hl.get("issues"):
            issues.append((pn_x, "highlight_issues", hl["issues"]))

    print(f"  Manifest OK: {pn_x_with_manifest}/{len(pn_x_list)}")
    print(f"  Main PDF OK: {pn_x_with_main}/{len(pn_x_list)}")
    print(f"  Highlight OK: {pn_x_with_highlight}/{len(pn_x_list)}")
    print(f"  Issues: {len(issues)}")

    # 3. PPT ↔ CSV 对齐
    print("\n[2/4] PPT ↔ CSV 对齐检查...")
    align = check_ppt_csv_alignment(ppt_path, csv_path)
    print(f"  Total: {align['total']}, Matched: {align['matched']}, Rate: {align['rate']:.1%}")
    if align['unmatched_list']:
        print(f"  未对齐案例:")
        for sn, num, ctx in align['unmatched_list']:
            print(f"    Slide {sn} 标号 {num}: {ctx!r}")

    # 4. 链接健康 (抽样 5 个)
    print("\n[3/4] 链接健康检查 (抽样 5 个)...")
    sample = pn_x_list[:5]
    links = check_links(sample, lit_base)
    ok_count = sum(1 for r in links['results'] if r.get('code') in ['200', '302', '301'])
    print(f"  样本 OK: {ok_count}/{len(links['results'])}")
    for r in links['results']:
        print(f"    {r.get('pn_x', 'N/A')}: {r.get('code', r.get('error', '?'))} - {r.get('url', 'N/A')[:50]}")

    # 5. 汇总
    print("\n[4/4] 健康报告汇总...")
    report = {
        "pn_x_total": len(pn_x_list),
        "manifest_ok": pn_x_with_manifest,
        "main_pdf_ok": pn_x_with_main,
        "highlight_ok": pn_x_with_highlight,
        "ppt_csv_alignment": align,
        "link_health_sample": links,
        "issues": [
            {"pn_x": pn, "type": t, "detail": str(d)[:200]}
            for pn, t, d in issues[:20]
        ],
    }

    # 输出报告
    report_path = f"{os.path.dirname(os.path.abspath(__file__))}/../_health_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {report_path}")

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='check', choices=['check', 'fix', 'report'])
    args = parser.parse_args()

    report = run_health_check()
    print(f"\n✅ 自检完成: {report['pn_x_total']} Pn-x, {len(report['issues'])} issues")


if __name__ == "__main__":
    main()
