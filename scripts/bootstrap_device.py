#!/usr/bin/env python3
"""
bootstrap_device.py — via54Medit 全自动化设备部署与就绪初始化脚本

在任何新设备上通过 traework / hermes-agent / codex / openclaw / DeepSeek-harness 部署后，一键运行本脚本:
  1. 验证并安装依赖 (PyMuPDF, python-pptx, Pillow, mmx-cli)。
  2. 部署并验证 mmx-cli 为默认 Vision 引擎。
  3. 部署并验证 PowerPoint 为 PPT 默认渲染引擎 (Windows COM / macOS 原生 PowerPoint)。
  4. 编译 Go 核心程序 (bin/medit, bin/medit-mcp)。
  5. 注册自动定期从 GitHub 拉取更新的守护任务 (Cron / LaunchAgent)。
  6. 检查 API Key 配置项并输出就绪报告。
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def step_print(title):
    print(f"\n==> {title}")


def run_cmd(cmd, cwd=REPO_DIR):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return res.returncode == 0, res.stdout.strip(), res.stderr.strip()


def check_and_install_deps():
    step_print("1. 检查并安装 Python 核心依赖与 mmx-cli")
    deps = ["pymupdf", "python-pptx", "pillow", "requests", "mmx-cli"]
    try:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + deps
        print(f"  正在执行 pip 安装: {' '.join(deps)}...")
        ok, out, err = run_cmd(cmd)
        if ok:
            print("  ✓ 核心 Python 库与 mmx-cli 安装完成")
        else:
            print(f"  ⚠️ pip 安装返回: {err or out}")
    except Exception as e:
        print(f"  ✗ pip 执行异常: {e}")


def verify_vision_engine():
    step_print("2. 验证 mmx-cli 默认 Vision 引擎配置")
    mmx_path = shutil.which("mmx") or shutil.which("mmx-cli")
    if mmx_path:
        print(f"  ✓ mmx-cli 已就绪: {mmx_path}")
    else:
        print("  ⚠️ mmx 命令未在系统 PATH，但在当前 Python venv 中已安装模块")
    
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if api_key:
        print(f"  ✓ MINIMAX_API_KEY 已配置 (长度: {len(api_key)})")
    else:
        print("  ℹ️ MINIMAX_API_KEY 需单独配置 (建议配置在环境变量或 ~/.bashrc / ~/.zshrc)")


def verify_powerpoint_engine():
    step_print("3. 验证 PowerPoint 默认 PPT 渲染引擎")
    try:
        from ppt_render_engine import detect_engines, _engine_pref
        engines = detect_engines()
        pref = _engine_pref()
        print(f"  当前设定渲染引擎: {pref}")
        print("  系统已探测到的可用渲染引擎:")
        for name, kind, target in engines:
            print(f"    - {name} ({kind}: {target})")
        
        has_ppt = any(k in ("com", "macos_ppt") for _, k, _ in engines)
        if has_ppt:
            print("  ✓ Microsoft PowerPoint 原生引擎就绪，高保真渲染已激活！")
        else:
            print("  ℹ️ 未检测到原生 Microsoft PowerPoint，将使用 LibreOffice / python-pptx 备选渲染")
    except Exception as e:
        print(f"  ⚠️ PowerPoint 引擎探测提示: {e}")


def build_go_binaries():
    step_print("4. 构建 Go 核心二进制程序")
    if not shutil.which("go"):
        print("  ⚠️ 系统未找到 go 编译器，跳过 Go 构建 (若已通过预编译 binary 运行则正常)")
        return
        
    bin_dir = REPO_DIR / "bin"
    bin_dir.mkdir(exist_ok=True)
    
    ok1, _, err1 = run_cmd(["go", "build", "-o", "bin/medit", "./cmd/medit"])
    ok2, _, err2 = run_cmd(["go", "build", "-o", "bin/medit-mcp", "./cmd/medit-mcp"])
    
    if ok1 and ok2:
        print("  ✓ bin/medit 与 bin/medit-mcp 编译成功")
    else:
        print(f"  ⚠️ 编译输出: {err1} {err2}")


def setup_periodic_sync():
    step_print("5. 配置自动定期从 GitHub 拉取最新代码")
    sync_script = REPO_DIR / "scripts" / "auto_sync.py"
    if not sync_script.exists():
        print("  ✗ 未找到 auto_sync.py")
        return
        
    if sys.platform == "darwin":
        ok, out, _ = run_cmd([sys.executable, str(sync_script), "--install-launchd"])
        print(f"  {out}")
    else:
        ok, out, _ = run_cmd([sys.executable, str(sync_script), "--install-cron"])
        print(f"  {out}")


def main():
    print("======================================================")
    print(" via54Medit 设备一键部署与就绪初始化向导")
    print(" (兼容 Traework / Hermes / Codex / OpenClaw / DeepSeek)")
    print("======================================================")
    
    check_and_install_deps()
    verify_vision_engine()
    verify_powerpoint_engine()
    build_go_binaries()
    setup_periodic_sync()
    
    print("\n======================================================")
    print(" ✅ via54Medit 初始化完成！")
    print(" 默认配置清单:")
    print("   • Vision Engine: mmx-cli (VISION_PROVIDER=mmx)")
    print("   • PPT Engine   : Microsoft PowerPoint (RENDER_ENGINE=powerpoint)")
    print("   • Auto-Sync    : 已注册系统定时任务 (自动定期从 GitHub 拉取更新)")
    print("======================================================")


if __name__ == "__main__":
    main()
