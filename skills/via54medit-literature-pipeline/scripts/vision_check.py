#!/usr/bin/env python3
"""视觉检查统一入口: SenseNova(商汤, 用户指定) -> M3 -> GLM 依次降级.
用于检查 PPT slide 渲染图、PDF 页面渲染图、highlight 导出图. 支持单图或多图."""
import os, sys, json, base64, time, urllib.request
from pathlib import Path

SENSENOVA_KEY = os.environ.get("SENSENOVA_API_KEY", "")
SENSENOVA_URL = "https://token.sensenova.cn/v1/chat/completions"
SENSENOVA_MODEL = "sensenova-6.8-flash-lite"

M3_KEY = os.environ.get("M3_API_KEY", "")
M3_URL = "https://api.minimaxi.com/anthropic/v1/messages"

GLM_KEY = os.environ.get("GLM_API_KEY", "")
GLM_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def _b64(img):
    return base64.b64encode(Path(img).read_bytes()).decode()


def _oai_content(imgs, prompt):
    return ([{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(p)}"}}
             for p in imgs]
            + [{"type": "text", "text": prompt}])


def call_sensenova(imgs, prompt, max_tokens=2000):
    body = {"model": SENSENOVA_MODEL, "max_tokens": max_tokens, "temperature": 0.1,
            "messages": [{"role": "user", "content": _oai_content(imgs, prompt)}]}
    for attempt in range(3):
        try:
            req = urllib.request.Request(SENSENOVA_URL, data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {SENSENOVA_KEY}",
                         "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            msg = d["choices"][0]["message"]
            txt = (msg.get("content") or "").strip() or (msg.get("reasoning") or "").strip()
            if txt:
                return txt
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    return ""


def call_m3(imgs, prompt, max_tokens=2000):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": _b64(p)}} for p in imgs]
    content.append({"type": "text", "text": prompt})
    body = {"model": "MiniMax-M3", "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(M3_URL, data=json.dumps(body).encode(),
        headers={"x-api-key": M3_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    return d["content"][0]["text"].strip()


def call_glm(imgs, prompt, max_tokens=2000):
    oai = _oai_content(imgs, prompt)
    body = {"model": "glm-4.6v-flash", "messages": [{"role": "user", "content": oai}],
            "max_tokens": max_tokens, "temperature": 0.1}
    req = urllib.request.Request(GLM_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {GLM_KEY}", "Content-Type": "application/json",
                 "User-Agent": "glm-literature/1.0"}, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            return d["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(4)
                continue
            raise


def vision(imgs, prompt, max_tokens=2000):
    """imgs: str/Path 或 list. 优先 SenseNova, M3/GLM 兜底."""
    if isinstance(imgs, (str, Path)):
        imgs = [imgs]
    try:
        txt = call_sensenova(imgs, prompt, max_tokens)
        if txt:
            return "[sensenova] " + txt
        print("[sensenova empty, fallback M3]", file=sys.stderr)
    except Exception as e:
        print(f"[sensenova fail: {e}, fallback M3]", file=sys.stderr)
    try:
        return "[m3] " + call_m3(imgs, prompt, max_tokens)
    except Exception as e:
        print(f"[m3 fail: {e}, fallback GLM]", file=sys.stderr)
    try:
        return "[glm] " + call_glm(imgs, prompt, max_tokens)
    except Exception as e:
        return f"ERROR all backends failed: {e}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: vision_check.py <img1> [img2 ...] <prompt>", file=sys.stderr)
        sys.exit(1)
    imgs = sys.argv[1:-1]
    prompt = sys.argv[-1]
    print(vision(imgs, prompt))
