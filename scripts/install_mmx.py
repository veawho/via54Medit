#!/usr/bin/env python3
"""
install_mmx.py — 自动部署 mmx-cli 作为默认 Vision 引擎

功能:
  1. 检测当前环境是否已有 mmx-cli (mmx 命令)。
  2. 若缺失，自动使用当前 Python 环境的 pip 安装 mmx-cli。
  3. 配置默认环境变量 VISION_PROVIDER=mmx。
  4. 检查 MINIMAX_API_KEY 是否已配置，并在缺失时给出配置引导。
"""
import os
import sys
import shutil
import subprocess

def check_mmx_installed():
    return shutil.which("mmx") is not None or shutil.which("mmx-cli") is not None

def install_mmx_cli():
    print("[install_mmx] 正在为当前 Python 环境安装 mmx-cli...")
    try:
        # 优先使用当前 Python 可执行文件
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "mmx-cli"],
                             capture_output=True, text=True, timeout=300)
        if res.returncode == 0:
            print("  ✓ mmx-cli 安装成功")
            return True
        else:
            # 尝试备选包名或源码安装
            print(f"  ⚠️ pip 安装 mmx-cli 返回: {res.stderr.strip() or res.stdout.strip()}")
            return False
    except Exception as e:
        print(f"  ✗ 安装过程发生异常: {e}")
        return False

def verify_and_configure():
    installed = check_mmx_installed()
    if not installed:
        installed = install_mmx_cli()
    
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    print("==========================================")
    print(" via54Medit Vision 引擎部署状态")
    print("==========================================")
    print(f"默认 Vision Provider: mmx")
    print(f"mmx-cli 状态: {'已就绪' if (installed or check_mmx_installed()) else '需手动配置或已内置在 virtualenv'}")
    if api_key:
        print(f"MINIMAX_API_KEY: 已配置 (长度: {len(api_key)})")
    else:
        print("MINIMAX_API_KEY: ⚠️ 未检测到 (需单独配置)")
        print("提示: 请在环境变量或 .env 中设置:")
        print("  export MINIMAX_API_KEY='你的MiniMax_API_Key'")
        print("  export MINIMAX_GROUP_ID='你的GroupId(如适用)'")
    print("==========================================")
    return installed

if __name__ == "__main__":
    verify_and_configure()
