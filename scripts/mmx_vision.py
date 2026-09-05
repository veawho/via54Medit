#!/usr/bin/env python3
"""
mmx_vision.py — MiniMax VLM (mmx-cli) 视觉封装 (2026-09-04 用户指定默认 vision)

默认 vision = mmx-cli (mmx vision describe)。接口兼容 sensenova_vision.py:
    vision_analyze(image_path, prompt, json_mode=False, timeout=...) -> str
    encode_image / get_image_mime / get_api_key (兼容占位)

用法:
    python3 mmx_vision.py <image_path> <prompt> [--json] [--save]
"""
import os
import sys
import json
import shutil
import base64
import argparse
import subprocess


def find_mmx_bin():
    """定位 mmx-cli 可执行文件 (env MMX_BIN > PATH mmx > 常见安装位置)"""
    cand = os.environ.get("MMX_BIN")
    if cand and os.path.exists(cand):
        return cand
    p = shutil.which("mmx")
    if p:
        return p
    for c in (os.path.expanduser("~/.local/bin/mmx"),
              os.path.expanduser("~/.hermes/node/bin/mmx"),
              os.path.expanduser("~/.npm-global/bin/mmx")):
        if os.path.exists(c):
            return c
    return "mmx"


def get_api_key():
    """mmx-cli 使用本地凭据 (~/.mmx/config.json), 无独立 key 概念; 返回 None 兼容"""
    return None


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_image_mime(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "image/png")


def vision_analyze(image_path, prompt, json_mode=False, timeout=180):
    """调用 mmx-cli (mmx vision describe) 分析图片。

    返回 (与 sensenova_vision.vision_analyze 契约一致):
        dict: {"success": bool, "content": str, "error": str}
    """
    if not os.path.exists(image_path):
        return {"success": False, "content": "", "error": "Image not found: %s" % image_path}
    mmx = find_mmx_bin()
    cmd = [mmx, "--output", "json", "vision", "describe",
           "--image", image_path, "--prompt", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"success": False, "content": "", "error": "mmx vision describe 超时 (%ds)" % timeout}
    except Exception as e:
        return {"success": False, "content": "", "error": "mmx vision describe 执行失败: %s" % str(e)[:200]}
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-300:]
        return {"success": False, "content": "", "error": "mmx vision describe 退出码 %d: %s" % (r.returncode, err)}
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        # 非 JSON 输出兜底: 直接返回原始文本
        return {"success": True, "content": (r.stdout or "").strip(), "error": ""}
    content = data.get("content")
    if content is None:
        return {"success": False, "content": "", "error": "mmx 响应缺少 content: %s" % (r.stdout or "")[:200]}
    return {"success": True, "content": str(content).strip(), "error": ""}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    parser.add_argument("prompt", nargs="?", default="Describe the image.")
    parser.add_argument("--json", dest="json_mode", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    ns = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    out = vision_analyze(ns.image_path, ns.prompt, json_mode=ns.json_mode, timeout=ns.timeout)
    # 输出契约与 sensenova_vision.py 一致: stdout JSON 对象 {success, content, error}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if ns.save and out.get("success"):
        save_path = os.path.splitext(ns.image_path)[0] + "_vision_result.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("\n结果已保存到: %s" % save_path, file=sys.stderr)
    sys.exit(0 if out.get("success") else 1)


if __name__ == "__main__":
    main()
