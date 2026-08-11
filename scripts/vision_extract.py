#!/usr/bin/env python3.11
"""
vision_extract.py - v9.6 新增: Vision API 提取 PDF highlight 图中的数据点

当 PyMuPDF 文字提取不到 PPT 数据点时 (数据在图片/截图中), 
调用 sensenova_vision API 从 highlight 图中提取.

用法:
    python3 vision_extract.py <pn_x> [--all]
    python3 vision_extract.py P3-1
"""
import sys, os, json, re, subprocess

lit_base = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index"


def extract_data_points_from_image(image_path, prompt=None):
    """调用 sensenova_vision API 提取图片中的数据点."""
    if prompt is None:
        prompt = (
            "请精确提取这张图片中的所有数字、百分比、年份, "
            "特别关注: 表格中的数字、柱状图标签、坐标轴刻度、"
            "标题中的数字、研究名称+数字、文献标识. "
            "输出格式: 数字 (描述), 每行一个."
        )
    
    result = subprocess.run([
        sys.executable,
        os.path.join(os.path.dirname(__file__), "sensenova_vision.py"),
        image_path, prompt, "--json"
    ], capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        return []
    
    try:
        data = json.loads(result.stdout)
        if not data.get("success"):
            return []
        content = data.get("content", "")
    except:
        return []
    
    # 解析数据点
    data_points = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 匹配 "数字 (描述)"
        m = re.match(r"^([\d\.]+%?)\s*\((.+?)\)\s*$", line)
        if m:
            num, desc = m.group(1), m.group(2)
            data_points.append({"value": num, "description": desc[:50]})
    
    return data_points


def vision_extract_pn_x(pn_x, lit_base_path=lit_base):
    """对 Pn-x 的所有 highlight 图做 vision OCR, 提取数据点."""
    pn_path = f"{lit_base_path}/{pn_x}"
    if not os.path.isdir(pn_path):
        return {}
    
    hl_files = sorted([f for f in os.listdir(pn_path) if 'highlight' in f.lower()])
    all_data_points = []
    
    for hl_file in hl_files:
        hl_path = f"{pn_path}/{hl_file}"
        print(f"  OCR: {hl_file}...")
        data_points = extract_data_points_from_image(hl_path)
        for dp in data_points:
            dp["source_image"] = hl_file
        all_data_points.extend(data_points)
    
    return all_data_points


def update_manifest_with_vision(pn_x, data_points, lit_base_path=lit_base):
    """把 vision OCR 结果写到 manifest."""
    manifest_path = f"{lit_base_path}/{pn_x}/_manifest.json"
    if not os.path.isfile(manifest_path):
        return
    
    with open(manifest_path) as f:
        m = json.load(f)
    
    # v9.6: 记录 vision OCR 结果
    m["vision_ocr_data_points"] = data_points
    m["vision_ocr_count"] = len(data_points)
    m["algorithm_version"] = "v9.6"
    
    with open(manifest_path, "w") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    
    print(f"  Manifest updated: {len(data_points)} vision OCR data points")


def main():
    if len(sys.argv) < 2:
        print("Usage: vision_extract.py <pn_x>")
        sys.exit(1)
    
    pn_x = sys.argv[1]
    print(f"=== {pn_x} Vision OCR ===")
    
    data_points = vision_extract_pn_x(pn_x)
    print(f"提取数据点: {len(data_points)}")
    
    if data_points:
        for dp in data_points[:10]:
            print(f"  {dp['value']} ({dp['description'][:40]})")
        update_manifest_with_vision(pn_x, data_points)


if __name__ == "__main__":
    main()
