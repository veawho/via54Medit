#!/usr/bin/env python3
"""
provider_vision.py — via54Medit 统一视觉 provider (2026-09-04)

默认 vision = mmx-cli (mmx vision describe)。可用环境变量 VISION_PROVIDER 切换:
    mmx        (默认)   MiniMax VLM via mmx-cli
    sensenova           sensenova-6.7-flash-lite API
    glm                 GLM-4V (若可用)

接口兼容 sensenova_vision.py:
    vision_analyze(image_path, prompt, json_mode=False, timeout=...) -> str
    get_api_key / encode_image / get_image_mime

CLI 子进程模式 (兼容 sensenova_vision.py 被 subprocess 调用方式):
    python3 provider_vision.py <image_path> <prompt> [--json] [--save]
"""
import os
import sys
import json
import argparse


def _provider():
    return os.environ.get("VISION_PROVIDER", "mmx").strip().lower()


def vision_analyze(image_path, prompt, json_mode=False, timeout=180):
    p = _provider()
    if p == "sensenova":
        from sensenova_vision import vision_analyze as _va
        return _va(image_path, prompt, json_mode=json_mode, timeout=timeout)
    if p == "glm":
        # GLM-4V 走 glm_vision 封装 (若函数存在)
        try:
            from glm_vision import vision_analyze as _va
        except Exception:
            raise RuntimeError("VISION_PROVIDER=glm 但 glm_vision.vision_analyze 不可用")
        return _va(image_path, prompt, json_mode=json_mode, timeout=timeout)
    # 默认 mmx-cli
    from mmx_vision import vision_analyze as _va
    return _va(image_path, prompt, json_mode=json_mode, timeout=timeout)


def get_api_key():
    p = _provider()
    if p == "sensenova":
        from sensenova_vision import get_api_key as _g
        return _g()
    if p == "glm":
        return os.environ.get("GLM_API_KEY")
    from mmx_vision import get_api_key as _g
    return _g()


def encode_image(image_path):
    p = _provider()
    if p == "sensenova":
        from sensenova_vision import encode_image as _e
        return _e(image_path)
    from mmx_vision import encode_image as _e
    return _e(image_path)


def get_image_mime(image_path):
    p = _provider()
    if p == "sensenova":
        from sensenova_vision import get_image_mime as _g
        return _g(image_path)
    from mmx_vision import get_image_mime as _g
    return _g(image_path)


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
