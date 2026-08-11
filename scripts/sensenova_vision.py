#!/usr/bin/env python3.11
"""
sensenova_vision.py — L4 视觉复核工具

替代 mmx vision 做 highlight 图的视觉验证。
sensenova-6.7-flash-lite 支持多模态 (text + image)，免费，262K context。

用法:
    python3.11 sensenova_vision.py <image_path> <prompt>
    python3.11 sensenova_vision.py <image_path> <prompt> --json  (结构化输出)
    python3.11 sensenova_vision.py <image_path> <prompt> --save  (保存结果到文件)
    python3.11 sensenova_vision.py <image_path> <prompt> --json --save

API:
    base_url: https://token.sensenova.cn/v1
    model: sensenova-6.7-flash-lite
    input: text + image (base64)
    output: text
    pricing: 全部免费 (prompt=0, completion=0, image=0, request=0)

依赖: 无 (仅 Python stdlib)
"""
import sys
import os
import json
import base64
import urllib.request
import urllib.error
import argparse


def get_api_key():
    """从环境变量或 .env 文件获取 API key."""
    key = os.environ.get("SENSENOVA_API_KEY")
    if key:
        return key

    # 从 .env 文件读取
    env_paths = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.env"),
        ".env",
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SENSENOVA_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
    return None


def encode_image(image_path):
    """将图片文件编码为 base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_image_mime(image_path):
    """根据文件扩展名获取 MIME 类型."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "image/png")


def vision_analyze(image_path, prompt, json_mode=False, timeout=30):
    """
    调用 sensenova-6.7-flash-lite 多模态 API 分析图片。

    参数:
        image_path: 图片文件路径
        prompt: 分析提示词
        json_mode: 是否要求 JSON 输出
        timeout: API 超时秒数

    返回:
        dict: {"success": bool, "content": str, "error": str}
    """
    api_key = get_api_key()
    if not api_key:
        return {"success": False, "content": "", "error": "SENSENOVA_API_KEY not found"}

    if not os.path.exists(image_path):
        return {"success": False, "content": "", "error": f"Image not found: {image_path}"}

    try:
        b64 = encode_image(image_path)
        mime = get_image_mime(image_path)
    except Exception as e:
        return {"success": False, "content": "", "error": f"Image encode failed: {e}"}

    # 构建消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }
    ]

    # 请求体
    data = {
        "model": "sensenova-6.7-flash-lite",
        "messages": messages,
        "temperature": 0.1,  # 低温度提高确定性
    }

    if json_mode:
        data["response_format"] = {"type": "json_object"}

    # 发送请求
    try:
        req = urllib.request.Request(
            "https://token.sensenova.cn/v1/chat/completions",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            content = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {"success": True, "content": content, "error": ""}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"success": False, "content": "", "error": f"HTTP {e.code}: {body[:200]}"}
    except urllib.error.URLError as e:
        return {"success": False, "content": "", "error": f"Network: {e.reason}"}
    except Exception as e:
        return {"success": False, "content": "", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="sensenova-6.7-flash-lite 多模态视觉复核工具"
    )
    parser.add_argument("image", help="图片文件路径")
    parser.add_argument("prompt", nargs="?", default="请描述这张图片的内容",
                        help="分析提示词")
    parser.add_argument("--json", action="store_true",
                        help="要求结构化 JSON 输出")
    parser.add_argument("--save", action="store_true",
                        help="保存结果到 JSON 文件")
    parser.add_argument("--timeout", type=int, default=30,
                        help="API 超时秒数 (默认 30)")
    args = parser.parse_args()

    result = vision_analyze(args.image, args.prompt, args.json, args.timeout)

    # 输出
    if args.json and result["success"]:
        # 解析 LLM 返回的 JSON 内容
        try:
            parsed = json.loads(result["content"])
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            # 如果 LLM 返回的不是 JSON，包装成 JSON
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # 保存结果
    if args.save and result["success"]:
        save_path = f"{os.path.splitext(args.image)[0]}_vision_result.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {save_path}", file=sys.stderr)

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()