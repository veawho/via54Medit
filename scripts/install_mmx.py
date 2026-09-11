#!/usr/bin/env python3
"""install_mmx.py — 部署/升级 mmx-cli 作为默认 Vision 引擎

**重要更正 (v5.4.34)**: mmx-cli 是 **npm 包**, 不是 PyPI 包。
旧版本这里跑的是 ``pip install --upgrade mmx-cli``, 而 PyPI 上根本没有这个发行版 ——
命令必然失败, 然后被错误处理吞掉, 于是部署"看起来成功了"。
本机实况: ``~/.local/bin/mmx -> ../lib/node_modules/mmx-cli/dist/mmx.mjs`` (shebang 是 node)。

因此安装动作改为: 探测 node/npm → ``npm install -g mmx-cli`` → 校验 ``mmx --version``。
缺 node/npm 时按平台给出安装途径 (brew / apt / winget / choco), 而不是假装装上了。

想一次把整套环境(含 OCR 等)都过一遍, 用 ``python3 scripts/deploy_scan.py``。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_scan as ds                                        # noqa: E402


def check_mmx_installed():
    return bool(shutil.which("mmx") or shutil.which("mmx-cli"))


def install_mmx_cli():
    """经 npm 安装。返回 (ok, detail)。"""
    if not (shutil.which("node") and shutil.which("npm")):
        ok, msg = ds.system_install({"brew": "node", "apt-get": "nodejs",
                                     "dnf": "nodejs", "pacman": "nodejs",
                                     "winget": "OpenJS.NodeJS.LTS", "choco": "nodejs"})
        if not ok:
            return False, ("本机没有 node/npm, 且自动安装未成功: %s "
                           "(装好 Node.js 后再跑 `npm install -g mmx-cli`)" % msg)
        if not (shutil.which("node") and shutil.which("npm")):
            # 刚装完可能还没进当前进程的 PATH
            return False, "Node.js 已安装, 但当前会话看不到 npm —— 请重开终端后重跑本脚本"
    return ds.npm_install("mmx-cli")


def verify_and_configure():
    installed = check_mmx_installed()
    if not installed:
        print("[install_mmx] 未检测到 mmx, 正在通过 npm 安装 (mmx-cli 不是 PyPI 包)...")
        installed, detail = install_mmx_cli()
        if installed:
            print("  ✓ %s" % detail)
        else:
            print("  ✗ 安装失败: %s" % detail)

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    print("==========================================")
    print(" via54Medit Vision 引擎部署状态")
    print("==========================================")
    print(" 默认 Vision Provider: mmx (VISION_PROVIDER=mmx)")
    if installed:
        path = shutil.which("mmx") or shutil.which("mmx-cli")
        ok, out = ds._run([path, "--version"], timeout=60)
        print(" mmx-cli: 已就绪 %s  (%s)" % (out.splitlines()[0].strip() if ok and out else "", path))
        up = ds._run([shutil.which("npm"), "view", "mmx-cli", "version"], timeout=120)
        if up[0] and up[1] and up[1].strip().splitlines()[0] not in (out or ""):
            print(" 提示: npm 上最新版为 %s, 升级: npm install -g mmx-cli" % up[1].strip().splitlines()[0])
    else:
        print(" mmx-cli: ✗ 仍需处理 —— npm install -g mmx-cli")
    if api_key:
        print(" MINIMAX_API_KEY: 已配置 (长度 %d)" % len(api_key))
    else:
        print(" MINIMAX_API_KEY: ✗ 未检测到 —— 部署脚本无法代填, 请自行配置:")
        print("   export MINIMAX_API_KEY='...'")
        print("   export MINIMAX_GROUP_ID='...(如适用)'")
    print("==========================================")
    return installed


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                           # noqa: BLE001
        pass
    sys.exit(0 if verify_and_configure() else 1)
