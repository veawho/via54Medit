#!/usr/bin/env python3.11
"""
vision_verify.py — L3 视觉验证统一入口 (3 级 Cascade)

视觉调用顺序 (v4.0):
  1. sensenova-6.7-flash-lite (主)  — 视觉质量最高 + 免费 + 0 VRAM + 无敏感词
  2. MiniMax-M3 / MiniMax-VL-01 (备) — 速度最快，质量高 (配额可能用尽)
  3. 本地 PyMuPDF 兜底 (最简) — 无 API 调用，纯文字层匹配

用法:
    python3.11 vision_verify.py <image_path> "<prompt>"
    python3.11 vision_verify.py <image_path> "<prompt>" --provider sensenova
    python3.11 vision_verify.py <image_path> "<prompt>" --provider minimax
    python3.11 vision_verify.py <image_path> "<prompt>" --provider local

环境变量:
    SENSENOVA_API_KEY      sensenova API key
    SENSENOVA_BASE_URL     sensenova base URL (默认: https://token.sensenova.cn/v1)
    MINIMAX_CN_API_KEY     MiniMax API key (默认: $MINIMAX_CN_API_KEY_2)
    VISION_TIMEOUT         单调用超时 (默认: 30)
    SKIP_SENSENOVA         跳过 sensenova (设为 1)
    SKIP_MINIMAX           跳过 MiniMax (设为 1)
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

# ====================================================================
# 配置
# ====================================================================

SENSENOVA_DEFAULT_BASE = "https://token.sensenova.cn/v1"
MINIMAX_DEFAULT_BASE = "https://api.minimax.chat/v1"
SENSENOVA_MODEL = "sensenova-6.7-flash-lite"
MINIMAX_MODEL = "MiniMax-M3"
DEFAULT_TIMEOUT = int(os.environ.get("VISION_TIMEOUT", "30"))

SENSENOVA_API_KEY = os.environ.get("SENSENOVA_API_KEY", "")
MINIMAX_API_KEY = os.environ.get("MINIMAX_CN_API_KEY",
                                  os.environ.get("MINIMAX_CN_API_KEY_2", ""))


def encode_image(path: str) -> str:
    """将图片转 base64 (OpenAI-compatible)."""
    import base64
    ext = path.lower().rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def call_sensenova(image_path: str, prompt: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """调用 sensenova-6.7-flash-lite (主视觉模型)."""
    if not SENSENOVA_API_KEY:
        return {"success": False, "error": "SENSENOVA_API_KEY not set",
                "provider": "sensenova"}
    base_url = os.environ.get("SENSENOVA_BASE_URL", SENSENOVA_DEFAULT_BASE)
    import urllib.request
    img_b64 = encode_image(image_path)
    payload = json.dumps({
        "model": SENSENOVA_MODEL,
        "messages": [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img_b64}},
                {"type": "text", "text": prompt},
            ]},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SENSENOVA_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"success": True, "content": content, "provider": "sensenova",
                "model": SENSENOVA_MODEL}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "sensenova"}


def call_minimax(image_path: str, prompt: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """调用 MiniMax-M3 (备选视觉模型)."""
    if not MINIMAX_API_KEY:
        return {"success": False, "error": "MINIMAX_API_KEY not set",
                "provider": "minimax"}
    img_b64 = encode_image(image_path)
    payload = json.dumps({
        "model": MINIMAX_MODEL,
        "messages": [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": img_b64}},
                {"type": "text", "text": prompt},
            ]},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{MINIMAX_DEFAULT_BASE}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        if "error" in data:
            err_msg = data["error"].get("message", "unknown error")
            return {"success": False, "error": err_msg, "provider": "minimax",
                    "model": MINIMAX_MODEL}
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"success": True, "content": content, "provider": "minimax",
                "model": MINIMAX_MODEL}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "minimax"}


def call_local(image_path: str, prompt: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """本地 PyMuPDF 兜底 (无 API 调用, 只检查图片尺寸和 metadata)."""
    try:
        import fitz
        # 图片文件用 PIL 检查尺寸
        import io
        with open(image_path, "rb") as f:
            data = f.read()
        import struct
        # 简单检查 JPEG/PNG header
        if data[:3] == b"\xff\xd8\xff":
            fmt = "JPEG"
            size = len(data)
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            fmt = "PNG"
            size = len(data)
        else:
            fmt = "unknown"
            size = len(data)
        content = f"Image: {fmt}, size={size}B. "
        content += f"Prompt: {prompt}"
        content += " [local fallback: image metadata only, no visual understanding]"
        return {"success": True, "content": content, "provider": "local"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "local"}


def vision_analyze(image_path: str, prompt: str,
                   provider: str = "cascade",
                   timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    统一视觉验证入口.

    3 级 Cascade:
      1. sensenova-6.7-flash-lite (主)
      2. MiniMax-M3 (备)
      3. 本地 PyMuPDF 兜底

    返回: {success, content, provider, model, error}
    """
    if provider == "sensenova":
        return call_sensenova(image_path, prompt, timeout)
    if provider == "minimax":
        return call_minimax(image_path, prompt, timeout)
    if provider == "local":
        return call_local(image_path, prompt)

    # cascade: sensenova -> minimax -> local
    result = {"success": False, "content": "", "error": "", "provider": "",
              "cascade": []}
    cascade = [
        ("sensenova", call_sensenova, os.environ.get("SKIP_SENSENOVA") != "1"),
        ("minimax", call_minimax, os.environ.get("SKIP_MINIMAX") != "1"),
        ("local", call_local, True),
    ]

    for name, fn, enabled in cascade:
        if not enabled:
            result["cascade"].append({"provider": name, "skipped": True})
            continue
        t0 = time.time()
        res = fn(image_path, prompt, timeout)
        elapsed = round(time.time() - t0, 1)
        result["cascade"].append({"provider": name, "elapsed_s": elapsed,
                                  "success": res.get("success", False)})
        if res.get("success"):
            result.update({
                "success": True, "content": res.get("content", ""),
                "provider": res.get("provider", name),
                "model": res.get("model", ""),
                "error": "",
            })
            break
        else:
            result["error"] = res.get("error", "")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="L3 vision verification — 3-level cascade"
    )
    parser.add_argument("image_path", help="Path to image file")
    parser.add_argument("prompt", help="Vision prompt (default: count highlights)")
    parser.add_argument("--provider", choices=["sensenova", "minimax",
                                                "local", "cascade"],
                        default="cascade",
                        help="Visual provider (default: cascade)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Timeout in seconds")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON only")
    args = parser.parse_args()

    result = vision_analyze(args.image_path, args.prompt,
                            provider=args.provider, timeout=args.timeout)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Provider: {result.get('provider', '?')}")
        if result.get("cascade"):
            for c in result["cascade"]:
                print(f"  {c['provider']}: {'skipped' if c.get('skipped') else c.get('success', False)} ({c.get('elapsed_s', '?')}s)")
        if result.get("success"):
            print(f"Content:\n{result.get('content', '')}")
        else:
            print(f"Error: {result.get('error', 'unknown')}")


if __name__ == "__main__":
    main()
