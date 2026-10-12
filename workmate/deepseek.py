#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deepseek.py — DeepSeek 统一 CLI（跨平台：Windows / macOS / Linux）
用途：以命令行方式调用 DeepSeek API（chat 对话 / vision 图像理解 / models 列表 / balance 连通探测），
      作为豆包与 via54Medit 之外的独立 LLM 能力补充；每次调用自动写入 ~/.medit/cli_usage.jsonl 埋点。
凭据：优先 $DEEPSEEK_API_KEY（或 DEEPSEEK_API_KEY env），其次 ~/.deepseek.key 文件。
用法：
  python deepseek.py chat "问题" [--system "..."] [--model deepseek-flash|deepseek-v4-pro] [--json]
  python deepseek.py vision <图片路径或URL> "问题" [--model ...] [--json]
  python deepseek.py models
  python deepseek.py balance
退出码：0 成功；1 API 失败；2 参数/凭据错误
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"


def resolve_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        kf = os.path.join(os.path.expanduser("~"), ".deepseek.key")
        if os.path.exists(kf):
            with open(kf, "r", encoding="utf-8") as f:
                key = f.read().strip()
    return key


def _usage_path():
    return os.path.join(os.path.expanduser("~"), ".medit", "cli_usage.jsonl")


def _append_usage(rec):
    try:
        d = os.path.dirname(_usage_path())
        os.makedirs(d, exist_ok=True)
        with open(_usage_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _post_json(path, payload, timeout=90):
    key = resolve_key()
    if not key:
        print("DeepSeek CLI: 未找到 API Key。请设置环境变量 DEEPSEEK_API_KEY 或创建 ~/.deepseek.key", file=sys.stderr)
        sys.exit(2)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        msg = ""
        try:
            msg = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        if code == 402:
            print("DeepSeek CLI: API balance insufficient (402). Please top up at platform.deepseek.com.", file=sys.stderr)
        elif code == 401:
            print("DeepSeek CLI: API Key 无效 (401)", file=sys.stderr)
        else:
            print(f"DeepSeek CLI: 调用失败 ({code}): {msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"DeepSeek CLI: 网络错误: {e}", file=sys.stderr)
        sys.exit(1)


def _get_json(path, timeout=30):
    key = resolve_key()
    req = urllib.request.Request(BASE + path, method="GET",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"DeepSeek CLI: 请求失败: {e}", file=sys.stderr)
        sys.exit(1)


def _image_data_url(path):
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not os.path.exists(path):
        print(f"DeepSeek CLI: 图片文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["content"])


def cmd_chat(args):
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})
    start = time.time()
    r = _post_json("/chat/completions", {"model": args.model, "messages": messages, "stream": False})
    dur = round(time.time() - start, 2)
    content = r["choices"][0]["message"]["content"]
    usage = r.get("usage", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    _append_usage({
        "source": "deepseek-cli",
        "session_id": "ds-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "task_type": "chat",
        "start_ms": int(time.time() * 1000) - int(dur * 1000),
        "end_ms": int(time.time() * 1000),
        "duration_s": dur,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "model": r.get("model", args.model),
        "user": "魏宇浩",
        "status": "实时",
        "ts": now,
    })
    _emit({"model": r.get("model"), "content": content, "usage": usage,
           "finish_reason": r["choices"][0].get("finish_reason")}, args.json)


def cmd_vision(args):
    img_path = args.image or args.prompt
    question = args.question or args.prompt
    if not img_path:
        print('用法: deepseek.py vision <图片路径或URL> "问题" [--model ...] [--json]', file=sys.stderr)
        sys.exit(2)
    prompt_text = args.question or (args.prompt if args.image else "Describe the image.")
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": _image_data_url(img_path)}},
        ],
    })
    start = time.time()
    r = _post_json("/chat/completions", {"model": args.model, "messages": messages, "stream": False})
    dur = round(time.time() - start, 2)
    content = r["choices"][0]["message"]["content"]
    usage = r.get("usage", {})
    _append_usage({
        "source": "deepseek-cli",
        "session_id": "ds-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "task_type": "vision",
        "start_ms": int(time.time() * 1000) - int(dur * 1000),
        "end_ms": int(time.time() * 1000),
        "duration_s": dur,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "model": r.get("model", args.model),
        "user": "魏宇浩",
        "status": "实时",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _emit({"model": r.get("model"), "content": content, "usage": usage,
           "finish_reason": r["choices"][0].get("finish_reason")}, args.json)


def cmd_models(args):
    r = _get_json("/models")
    for m in r.get("data", []):
        print(m.get("id", ""))


def cmd_balance(args):
    r = _post_json("/chat/completions",
                   {"model": args.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1})
    print(f"DeepSeek API 连通正常 (model={r.get('model')})")


def main():
    ap = argparse.ArgumentParser(prog="deepseek.py", description="DeepSeek 统一 CLI（跨平台）")
    ap.add_argument("action", choices=["chat", "vision", "models", "balance"], nargs="?", default="chat")
    ap.add_argument("prompt", nargs="?", default="", help="chat 的问题 / vision 的图片路径或 URL")
    ap.add_argument("question", nargs="?", default="", help="vision 的问题（位置参数第 3 位）")
    ap.add_argument("--system", default="", help="system 提示")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"模型（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--image", default="", help="vision 图片路径或 URL（命名参数）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if args.action == "chat":
        if not args.prompt:
            print('用法: deepseek.py chat "问题" [--system "..."] [--model ...] [--json]', file=sys.stderr)
            sys.exit(2)
        cmd_chat(args)
    elif args.action == "vision":
        cmd_vision(args)
    elif args.action == "models":
        cmd_models(args)
    elif args.action == "balance":
        cmd_balance(args)


if __name__ == "__main__":
    main()
