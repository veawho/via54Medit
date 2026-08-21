#!/usr/bin/env python3
"""
deps_auto.py — 环境自检 + 自动接入系统软件/依赖/包 (部署新系统即用)

检测并自动安装:
  - Python 版本 (要求 >= 3.10)
  - PyMuPDF (fitz)   — PDF 解析/highlight
  - python-pptx      — PPT 结构提取
  - Pillow           — 图片处理
  - pywin32          — Windows PowerPoint/WPS COM (仅 Windows)
  - (可选) 系统 PPT 引擎: PowerPoint/WPS/soffice 自动探测见 ppt_render_engine.py
  - (可选) 系统二进制: soffice / pdftotext / lark-cli 探测并给出各平台安装提示
  - requirements.txt: 存在时优先整表安装 (可复现)

自动安装失败时不中断 (打印提示, 由上层降级路径接管)。

用法:
  python deps_auto.py [--check] [--no-install]
  from deps_auto import ensure_env
"""
import os, sys, subprocess

MIN_PY = (3, 10)

DEPS = [
    ("pymupdf", "fitz", "PDF 解析/highlight"),
    ("python-pptx", "pptx", "PPT 结构提取"),
    ("Pillow", "PIL", "图片处理"),
]

WINDOWS_DEPS = [
    ("pywin32", "win32com", "PowerPoint/WPS COM 渲染"),
]


def _py_version_ok():
    return sys.version_info >= MIN_PY


def _importable(module):
    try:
        __import__(module)
        return True
    except Exception:
        return False


def _pip_install(pkg, label):
    print("  [install] %s (%s)..." % (pkg, label), flush=True)
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                           capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            print("    ✓ %s 已安装" % pkg, flush=True)
            return True
        print("    ✗ %s 安装失败: %s" % (pkg, (r.stderr or r.stdout)[-200:]), flush=True)
    except Exception as e:
        print("    ✗ %s 安装异常: %s" % (pkg, str(e)[:120]), flush=True)
    return False


def _tool_available(name):
    """系统二进制探测 (PATH 查找)"""
    import shutil
    return shutil.which(name)


def _check_system_tools():
    """探测系统二进制 (可选工具, 不装只提示)"""
    found = []
    missing = []
    for name, hint in [
        ("soffice", "LibreOffice (PPT 真实渲染): macOS `brew install --cask libreoffice`, Linux `apt install libreoffice`"),
        ("pdftotext", "poppler-utils (PDF 文本提取): macOS `brew install poppler`, Linux `apt install poppler-utils`"),
        ("lark-cli", "飞书 CLI 集成: 设置 $LARK_CLI 指向可执行文件"),
    ]:
        p = _tool_available(name)
        if p:
            found.append("%s=%s" % (name, p))
        else:
            missing.append("%s (%s)" % (name, hint))
    if found:
        print("  系统工具: %s" % " | ".join(found), flush=True)
    for m in missing:
        print("  ~ 可选缺失: %s" % m, flush=True)
    return missing


def ensure_env(install=True):
    """自检 + 自动安装缺失依赖; 返回 (ok, problems)"""
    problems = []
    print("== 环境自检 (Python %s) ==" % sys.version.split()[0], flush=True)
    # 优先按 requirements.txt 对齐 (可复现安装)
    req_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "requirements.txt")
    if install and os.path.exists(req_path):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print("  ~ requirements.txt 安装未完全成功, 逐项回退探测: %s" % (r.stderr or r.stdout)[-150:], flush=True)
    if not _py_version_ok():
        problems.append("Python %d.%d+ 必需, 当前 %d.%d" % (MIN_PY[0], MIN_PY[1], sys.version_info[0], sys.version_info[1]))
        print("  ✗ Python 版本过低: %s" % problems[-1], flush=True)
    for pkg, mod, label in DEPS:
        if _importable(mod):
            print("  ✓ %s (%s)" % (pkg, label), flush=True)
        elif install and _pip_install(pkg, label):
            pass
        else:
            problems.append("%s 缺失 (%s)" % (pkg, label))
            print("  ✗ %s 缺失" % pkg, flush=True)
    if os.name == "nt":
        for pkg, mod, label in WINDOWS_DEPS:
            if _importable(mod):
                print("  ✓ %s (%s)" % (pkg, label), flush=True)
            elif install and _pip_install(pkg, label):
                pass
            else:
                problems.append("%s 缺失 (%s)" % (pkg, label))
                print("  ✗ %s 缺失" % pkg, flush=True)
    # PPT 引擎提示 (ppt_render_engine 负责实际接入)
    try:
        from ppt_render_engine import detect_engines
        engines = detect_engines()
        names = [n for n, _k, _p in engines]
        print("  PPT 渲染引擎: %s" % (" → ".join(names)), flush=True)
    except Exception as e:
        print("  PPT 渲染引擎探测失败: %s" % str(e)[:100], flush=True)
    _check_system_tools()
    print("== 自检完成: %s ==" % ("OK" if not problems else "%d 项问题" % len(problems)), flush=True)
    return (not problems), problems


def main():
    install = "--no-install" not in sys.argv
    if "--check" in sys.argv:
        ok, problems = ensure_env(install=False)
    else:
        ok, problems = ensure_env(install=install)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
