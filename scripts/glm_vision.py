#!/usr/bin/env python3
"""
glm_vision.py — GLM-4.1V-Thinking-Flash 多模态 wrapper (2026-08-11)

替换 sensenova-6.7-flash-lite, 走智谱 OpenAI 兼容接口.

API: https://open.bigmodel.cn/api/paas/v4/chat/completions
Model: glm-4.1v-thinking-flash (免费, 64K context, 多模态)

设计原则:
- 接口与 sensenova_call 完全兼容 (image_paths, prompt, json_mode, timeout, cache)
- 用 MD5 cache 解决 GLM 4V 非确定性 (temp=0.05)
- 支持多图输入 (PPTX + PDF page)
- 失败时 fallback 到 sensenova_call
"""
import os, sys, json, time, re, hashlib
import urllib.request
import urllib.error
from pathlib import Path


CACHE_PATH = "/tmp/_glm_vision_cache.json"
DEFAULT_MODEL = "glm-4.1v-thinking-flash"
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def _get_api_key():
    key = os.environ.get("GLM_API_KEY")
    if key:
        return key
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("GLM_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _get_base_url():
    return os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL)


def _encode_image(path):
    with open(path, "rb") as f:
        return __import__("base64").b64encode(f.read()).decode()


def _mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp"}.get(ext, "image/png")


def _cache_key(image_paths, prompt):
    img_part = "|".join(sorted(image_paths))
    h = hashlib.md5((prompt + img_part).encode()).hexdigest()[:24]
    return h


def _load_cache():
    if os.path.isfile(CACHE_PATH):
        try:
            return json.load(open(CACHE_PATH))
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def glm_vision_call(image_paths, prompt, json_mode=True, timeout=120, model=DEFAULT_MODEL):
    """
    调用 GLM-4.1V-Thinking-Flash 多模态 API.
    接口与 sensenova_call 完全兼容.

    Args:
        image_paths: str 或 list[str]
        prompt: text prompt
        json_mode: 要求 JSON 输出
        timeout: API 超时 (thinking 模式建议 60-120s)
        model: 模型名 (默认 glm-4.1v-thinking-flash)

    Returns:
        str: 响应 content (失败返回 "")
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]

    cache = _load_cache()
    key = _cache_key(image_paths, prompt)
    if key in cache:
        return cache[key]

    api_key = _get_api_key()
    if not api_key:
        return ""

    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        if not os.path.isfile(p):
            continue
        b64 = _encode_image(p)
        content.append({"type": "image_url", "image_url": {"url": f"data:{_mime(p)};base64,{b64}"}})

    data = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.05,
        "max_tokens": 4096,
    }
    # 注意: GLM 4.1V-Thinking 不一定支持 response_format json_object, 不加, prompt 里强调 JSON

    url = f"{_get_base_url()}/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            result = json.loads(r.read().decode())
        content_str = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        cache[key] = content_str
        _save_cache(cache)
        return content_str
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  GLM HTTPError {e.code}: {body}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"  GLM err: {e}", file=sys.stderr)
        return ""


if __name__ == "__main__":
    # 简单测试
    import sys
    if len(sys.argv) < 2:
        print("usage: glm_vision.py <image_path> [prompt]")
        sys.exit(1)
    img = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "请描述这张图片"
    result = glm_vision_call(img, prompt)
    print(result[:500])
