#!/usr/bin/env python3
"""
provider_llm.py — via54Medit 统一文本与推理 LLM provider (2026-09-04)

支持后端 (通过 LLM_PROVIDER 环境变量切换):
    deepseek    (默认) DeepSeek V3 / R1 (api.deepseek.com)
    hermes             Hermes Agent Gateway / local MiniMax
    openai / codex     OpenAI API / Codex compatible
    minimax            MiniMax Text API
    sensenova          SenseNova Text API

CLI 用法:
    python3 provider_llm.py "prompt" [--system "..."] [--model "..."] [--json]
"""
import os
import sys
import json
import urllib.request
import urllib.error
import argparse


def _provider():
    return os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()


def get_api_key(p=None):
    p = p or _provider()
    if p in ("deepseek", "deepseek-r1", "deepseek-v3"):
        return os.environ.get("DEEPSEEK_API_KEY", "")
    if p in ("openai", "codex"):
        return os.environ.get("OPENAI_API_KEY", "")
    if p == "minimax":
        return os.environ.get("MINIMAX_API_KEY", "")
    if p == "sensenova":
        return os.environ.get("SENSENOVA_API_KEY", "")
    if p == "hermes":
        return os.environ.get("HERMES_API_KEY", "")
    return os.environ.get("LLM_API_KEY", "")


def complete(prompt, system="", model=None, json_mode=False, temperature=0.1, timeout=120):
    p = _provider()
    api_key = get_api_key(p)
    
    # 1. DeepSeek Provider
    if p in ("deepseek", "deepseek-r1", "deepseek-v3"):
        endpoint = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
        m = model or ("deepseek-reasoner" if "r1" in p else "deepseek-chat")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode and "reasoner" not in m:
            payload["response_format"] = {"type": "json_object"}
            
        return _call_openai_compatible(endpoint, api_key, payload, timeout=timeout)
        
    # 2. OpenAI / Codex Provider
    if p in ("openai", "codex"):
        endpoint = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        m = model or "gpt-4o-mini"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            
        return _call_openai_compatible(endpoint, api_key, payload, timeout=timeout)

    # 3. Hermes Local Gateway
    if p == "hermes":
        endpoint = os.environ.get("HERMES_GATEWAY_URL", "http://localhost:8765/v1/chat/completions")
        m = model or "MiniMax-M3"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
        }
        return _call_openai_compatible(endpoint, api_key, payload, timeout=timeout)
        
    # Fallback to OpenAI compatible
    endpoint = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
    m = model or "deepseek-chat"
    return _call_openai_compatible(endpoint, api_key, {
        "model": m,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }, timeout=timeout)


def _call_openai_compatible(endpoint, api_key, payload, timeout=120):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            choice = res_data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            return {
                "success": True,
                "content": content,
                "reasoning_content": reasoning,
                "model": res_data.get("model", ""),
                "usage": res_data.get("usage", {})
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "content": ""
        }


def main():
    parser = argparse.ArgumentParser(description="via54Medit unified LLM provider")
    parser.add_argument("prompt", help="Prompt text")
    parser.add_argument("--system", default="", help="System prompt")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--json", dest="json_mode", action="store_true", help="JSON mode")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    res = complete(
        args.prompt,
        system=args.system,
        model=args.model,
        json_mode=args.json_mode,
        temperature=args.temperature,
        timeout=args.timeout
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


if __name__ == "__main__":
    main()
