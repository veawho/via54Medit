#!/usr/bin/env python3.11
"""
L3 视觉复核集成 — 调用 sensenova-6.7-flash-lite 多模态验证 highlight 图.

用法:
    python3.11 l3_vision_verify.py <image_path> <allegation_text> [--json]

L4 流程:
    1. L0 验证 PDF 真实性 (medit anno2ppt l0verify)
    2. L1 PyMuPDF 文字提取
    3. L2 PaddleOCR (中文/图片)
    4. L3 sensenova vision 复核 (本脚本)
    5. L4 应证推理机 (medit anno2ppt confirm)

sensenova 优势: 免费, 262K context, 无需安装, 无需 Token.
"""
import sys
import os
import json

# 调用 sensenova_vision.py
script_dir = os.path.dirname(os.path.abspath(__file__))
vision_script = os.path.join(script_dir, "sensenova_vision.py")


def verify_highlight(image_path, allegation_text, json_mode=False):
    """验证 highlight 图是否应证 PPT 引用语义.

    参数:
        image_path: highlight 图路径
        allegation_text: PPT 引用语义 (C 列)
        json_mode: 是否输出 JSON

    返回:
        dict: {"success": bool, "content": str, "error": str}
    """
    if not os.path.exists(vision_script):
        return {"success": False, "content": "",
                "error": f"sensenova_vision.py not found at {vision_script}"}

    if not os.path.exists(image_path):
        return {"success": False, "content": "",
                "error": f"Image not found: {image_path}"}

    import subprocess
    cmd = [sys.executable, vision_script, image_path, allegation_text]
    if json_mode:
        cmd.append("--json")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"success": False, "content": "",
                    "error": f"vision script exited {result.returncode}: {result.stderr[:200]}"}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"success": False, "content": "", "error": "timeout after 60s"}
    except json.JSONDecodeError:
        return {"success": False, "content": result.stdout, "error": ""}
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}


def main():
    if len(sys.argv) < 3:
        print(f"用法: {sys.argv[0]} <image_path> <allegation_text> [--json]")
        print(f"示例: {sys.argv[0]} P3-1_page1_highlight.jpg '最佳客观缓解'")
        sys.exit(1)

    image_path = sys.argv[1]
    allegation_text = sys.argv[2]
    json_mode = "--json" in sys.argv

    result = verify_highlight(image_path, allegation_text, json_mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()