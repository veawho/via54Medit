#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy_medit.py — via54Medit 豆包伙伴 一键部署引擎（跨平台：Windows / macOS / Linux）

设计目标：上传部署伙伴后【一步完成】——由豆包工作伙伴在对话中自动调用本脚本，
检测并补全全部依赖，DeepSeek API Key 支持三种提供方式：
  1) --key sk-xxx        （伙伴对话内收集后传入，推荐）
  2) 环境变量 DEEPSEEK_API_KEY
  3) 交互式 input()      （终端手动运行时）

用法：
  python deploy_medit.py --check-only          # 只体检
  python deploy_medit.py                        # 全量部署（缺 key 时交互询问）
  python deploy_medit.py --key sk-xxx           # 伙伴自动部署（对话内已拿到 key）
  python deploy_medit.py --skip-paddle          # 跳过 PaddleOCR
幂等可重跑；输出状态报告；日志 ~/.via54medit/deploy_medit.log
"""
import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, ".via54medit", "bin")
CFG_DIR = os.path.join(HOME, ".medit")
CFG_FILE = os.path.join(CFG_DIR, "config.yaml")
KEY_FILE = os.path.join(HOME, ".deepseek.key")
LOG = os.path.join(BIN, "deploy_medit.log")
BASE_TOKEN = "Al8xbS4u9av85esUgjvcWYDankb"
BIT_URL = f"https://hackhealth.feishu.cn/base/{BASE_TOKEN}"
REPORT = []
TS = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{TS}] {msg}\n")
    except Exception:
        pass


def rep(name, status, detail=""):
    REPORT.append((name, status, detail))
    mark = {"OK": "✅", "FIXED": "🔧", "SKIP": "➖", "FAIL": "❌", "WARN": "⚠️"}.get(status, "·")
    print(f"{mark} {name:<34} {detail}", flush=True)
    log(f"{mark} {name}: {detail}")


def run(cmd, silent=False):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not silent and r.stdout.strip():
        print(r.stdout.strip(), flush=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def have(cmdname):
    return shutil.which(cmdname) is not None


def py_import_ok(mod):
    rc, _, _ = run([sys.executable, "-c", f"import {mod}"], silent=True)
    return rc == 0


def platform_tag():
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    if s == "darwin":
        return "darwin"
    return "linux"


def pick_medit_binary(bundle_dir):
    """按平台选择安装包内二进制：win → medit.exe；darwin → medit-arm64/amd64（按架构）。"""
    tag = platform_tag()
    cand = []
    if tag == "windows":
        cand = [os.path.join(bundle_dir, "bin", "medit.exe")]
    elif tag == "darwin":
        arm = platform.machine().lower()
        if arm in ("arm64", "aarch64"):
            cand = [os.path.join(bundle_dir, "bin", "medit-arm64"), os.path.join(bundle_dir, "bin", "medit")]
        else:
            cand = [os.path.join(bundle_dir, "bin", "medit-amd64"), os.path.join(bundle_dir, "bin", "medit")]
    else:
        cand = [os.path.join(bundle_dir, "bin", "medit-linux"), os.path.join(bundle_dir, "bin", "medit")]
    for c in cand:
        if os.path.exists(c):
            return c
    return None


def ensure_config():
    os.makedirs(CFG_DIR, exist_ok=True)
    if os.path.exists(CFG_FILE):
        rep("medit 配置", "OK", CFG_FILE)
        return
    cfg = """# via54Medit 本机配置（deploy_medit.py 自动生成）
version: 1
sources:
  pubmed: { enabled: true, api_key: "", rate_limit: 3, email: "" }
  openalex: { enabled: true, email: "", rate_limit: 10 }
  s2: { enabled: true, api_key: "", rate_limit: 1 }
llm:
  default: deepseek
  providers:
    openai: { api_key: "", model: "deepseek-flash", base_url: "https://api.deepseek.com/v1" }
router:
  concurrency: 4
  timeout_per_source: 30s
  max_retries: 3
  fallback_order: [pubmed, openalex, s2]
  fusion: { weights: { cited_by: 0.3, recency: 0.2, fwci: 0.3, multi_source: 0.2 }, simhash_hamming_threshold: 3 }
  classify: { use_llm: true, enable_pico: true }
storage: { qa_dir: "~/.medit/qa", index_db: "~/.medit/fts5.db", pdf_dir: "~/.medit/pdfs", knowledge_base: "medlit", audit_log: "~/.medit/audit" }
output: { default_format: "json", pretty: true, color: "auto", language: "auto" }
"""
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        f.write(cfg)
    rep("medit 配置", "FIXED", "已生成默认配置（DeepSeek 默认 / 3 源）")


def deploy_deepseek(args, bundle_dir):
    """deepseek.py 强制部署 + API Key 落位。"""
    ds = os.path.join(BIN, "deepseek.py")
    if not os.path.exists(ds):
        src = os.path.join(bundle_dir, "bin", "deepseek.py")
        if os.path.exists(src):
            shutil.copy(src, ds)
    if os.path.exists(ds):
        rep("DeepSeek CLI", "OK", "deepseek.py 就位（跨平台，强制部署）")
    else:
        rep("DeepSeek CLI", "FAIL", "deepseek.py 缺失（安装包 bin 也缺）")
        return
    # key 解析链：--key → env → ~/.deepseek.key → config → 交互
    key = (args.key or "").strip() or os.environ.get("DEEPSEEK_API_KEY", "").strip()
    key_file_has = os.path.exists(KEY_FILE) and open(KEY_FILE, encoding="utf-8").read().strip()
    cfg_key = ""
    if os.path.exists(CFG_FILE):
        try:
            for ln in open(CFG_FILE, encoding="utf-8"):
                if "api_key:" in ln and '"' in ln:
                    v = ln.split('"')[1] if ln.count('"') >= 2 else ""
                    if v:
                        cfg_key = v
        except Exception:
            pass
    if not key and not key_file_has and cfg_key:
        key = cfg_key
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
        rep("DeepSeek key", "FIXED", "已从 config 回填 ~/.deepseek.key")
    if key and not key_file_has:
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
        rep("DeepSeek key", "FIXED", "已写入 ~/.deepseek.key")
    elif key or key_file_has:
        if not key:
            key = key_file_has
        # 回填 config
        if os.path.exists(CFG_FILE):
            c = open(CFG_FILE, encoding="utf-8").read()
            import re
            c2 = re.sub(r'api_key:\s*""', f'api_key: "{key}"', c, count=1)
            if c2 != c:
                open(CFG_FILE, "w", encoding="utf-8").write(c2)
                rep("DeepSeek key", "FIXED", "已回填 config providers.openai.api_key")
        rep("DeepSeek key", "OK", "已配置（env / ~/.deepseek.key / config）")
    elif args.check_only:
        rep("DeepSeek key", "FAIL", "强制要求：需提供 DeepSeek API Key（部署时用 --key 或对话提供）")
    else:
        print("", flush=True)
        print("⚠ 强制要求：DeepSeek API Key 缺失。", flush=True)
        print("  PPT 分析 / 文献分析 / highlight / 视觉 默认均走 DeepSeek。", flush=True)
        if args.yes:
            rep("DeepSeek key", "FAIL", "未提供 key（--yes 非交互模式）")
        else:
            try:
                prompt = input("  请输入 DeepSeek API Key（sk-...，留空跳过）: ").strip()
            except EOFError:
                prompt = ""
            if prompt:
                with open(KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(prompt)
                rep("DeepSeek key", "FIXED", "已写入 ~/.deepseek.key（交互输入）")
            else:
                rep("DeepSeek key", "FAIL", "未提供 key，可稍后重跑或设置 DEEPSEEK_API_KEY")


def deploy_lark():
    """lark-cli 检测 + 账号绑定 + 多维表格可达。"""
    if have("lark-cli"):
        rc, out, _ = run(["lark-cli", "contact", "+get-user", "--jq", ".data.user.open_id"], silent=True)
        if "ou_" in out:
            rep("lark-cli 部署", "OK", f"已就绪，本地飞书账号已绑定（openid {out.strip()}）")
        else:
            rep("lark-cli 部署", "WARN", "命令存在但登录态异常（请重新登录 lark-cli）")
    else:
        rep("lark-cli 部署", "WARN", "未安装 lark-cli（豆包/飞书工作环境自带；缺失时按官方方式安装）")
    rc, out, _ = run(["lark-cli", "base", "+table-list", "--base-token", BASE_TOKEN], silent=True)
    if "监控数据周报" in out:
        rep("多维表格绑定", "OK", f"已绑定 {BIT_URL}")
    else:
        rep("多维表格绑定", "WARN", "表格不可访问（检查租户权限）")


def deploy_schedule():
    sched = os.path.join(BIN, "create_sched.py")
    if not os.path.exists(sched):
        rep("定时任务脚本", "WARN", "create_sched.py 缺失")
        return
    rc, _, _ = run([sys.executable, sched], silent=True)
    rep("定时任务注册", "OK" if rc == 0 else "FAIL", "采集(5分钟) + 周一校验(10:30)")


def main():
    ap = argparse.ArgumentParser(prog="deploy_medit.py", description="via54Medit 伙伴一键部署（跨平台）")
    ap.add_argument("--check-only", action="store_true", help="只体检不修复")
    ap.add_argument("--key", default="", help="DeepSeek API Key（伙伴对话内收集后传入）")
    ap.add_argument("--skip-paddle", action="store_true", help="跳过 PaddleOCR")
    ap.add_argument("--yes", action="store_true", help="非交互模式（缺 key 直接 FAIL 不询问）")
    args = ap.parse_args()

    print(f"\n=== via54Medit 伙伴一键部署  {TS}  [{platform_tag()}] ===", flush=True)
    os.makedirs(BIN, exist_ok=True)
    bundle_dir = os.path.dirname(os.path.abspath(__file__)) or "."

    # 1. medit 二进制（安装包自带 → 复制）
    medit_dst = os.path.join(BIN, "medit.exe" if platform_tag() == "windows" else "medit")
    if os.path.exists(medit_dst):
        rc, out, _ = run([medit_dst, "version"], silent=True)
        rep("medit 二进制", "OK", out.splitlines()[0] if out else "就位")
    else:
        src = pick_medit_binary(bundle_dir)
        if src and not args.check_only:
            shutil.copy(src, medit_dst)
            rep("medit 二进制", "FIXED", f"从安装包部署（{os.path.basename(src)}）")
        else:
            rep("medit 二进制", "FAIL", "安装包无本平台二进制，需 Go 编译")

    # 2. Python 与依赖
    if sys.executable:
        rep("Python", "OK", sys.version.split()[0])
    py_deps = [("PyMuPDF", "fitz", "pymupdf"), ("python-pptx", "pptx", "python-pptx"), ("Pillow", "PIL", "Pillow")]
    if platform_tag() == "windows":
        py_deps.append(("pywin32", "win32com", "pywin32"))
    missing = []
    for mod, imp, pkg in py_deps:
        if py_import_ok(imp):
            rep(f"py: {mod}", "OK", "已安装")
        else:
            rep(f"py: {mod}", "WARN", "缺失")
            missing.append(pkg)
    if missing and not args.check_only:
        run([sys.executable, "-m", "pip", "install", "--quiet"] + missing, silent=True)
        ok = all(py_import_ok(i) for _, i, _ in py_deps)
        rep("Python 依赖安装", "FIXED" if ok else "FAIL", "已安装" if ok else f"pip 失败: {','.join(missing)}")

    # 3. PaddleOCR（可选，大）
    if py_import_ok("paddleocr"):
        rep("PaddleOCR", "OK", "已安装")
    elif args.skip_paddle:
        rep("PaddleOCR", "SKIP", "已跳过（--skip-paddle）")
    elif args.check_only:
        rep("PaddleOCR", "WARN", "缺失（~1GB，可选）")
    else:
        run([sys.executable, "-m", "pip", "install", "--quiet", "paddlepaddle", "paddleocr"], silent=True)
        rep("PaddleOCR", "FIXED" if py_import_ok("paddleocr") else "FAIL", "安装完成" if py_import_ok("paddleocr") else "安装失败（--skip-paddle 可跳过）")

    # 4. FFmpeg
    if have("ffmpeg"):
        rep("FFmpeg", "OK", "可用")
    elif args.check_only:
        rep("FFmpeg", "WARN", "缺失")
    else:
        if platform_tag() == "windows" and have("winget"):
            run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-package-agreements",
                 "--accept-source-agreements", "--disable-interactivity"], silent=True)
        elif platform_tag() == "darwin" and have("brew"):
            run(["brew", "install", "ffmpeg"], silent=True)
        elif have("apt-get"):
            run(["sudo", "apt-get", "install", "-y", "ffmpeg"], silent=True)
        rep("FFmpeg", "FIXED" if have("ffmpeg") else "WARN", "已安装" if have("ffmpeg") else "安装未生效（PATH 需重启）")

    # 5. Office COM（仅 Windows；macOS 用 LibreOffice 渲染备选）
    if platform_tag() == "windows":
        try:
            import win32com.client  # noqa
            win32com.client.Dispatch("PowerPoint.Application")
            rep("Office COM (PPT)", "OK", "COM 可实例化")
        except Exception:
            rep("Office COM (PPT)", "WARN" if args.check_only else "FAIL", "需安装 Microsoft Office")
    else:
        rep("Office COM (PPT)", "SKIP", "仅 Windows；macOS 渲染走 LibreOffice/poppler")

    # 6. 配置初始化
    ensure_config()

    # 7. DeepSeek CLI + Key（强制）
    deploy_deepseek(args, bundle_dir)

    # 8. lark-cli + 飞书绑定
    deploy_lark()

    # 9. 定时任务
    deploy_schedule()

    # 10. 报告
    ok = sum(1 for _, s, _ in REPORT if s in ("OK", "FIXED"))
    warn = sum(1 for _, s, _ in REPORT if s == "WARN")
    fail = sum(1 for _, s, _ in REPORT if s == "FAIL")
    print(f"\n✅ 正常/已修复: {ok}   ⚠️ 警告: {warn}   ❌ 失败: {fail}", flush=True)
    print(f"日志: {LOG}", flush=True)
    if fail > 0:
        for n, s, d in REPORT:
            if s == "FAIL":
                print(f"  ❌ {n}: {d}", flush=True)
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    main()
