#!/usr/bin/env python3
"""install_mmx.py — 部署/升级 mmx-cli 作为默认 Vision 引擎

**重要更正 (v5.4.34)**: mmx-cli 是 **npm 包**, 不是 PyPI 包。
旧版本这里跑的是 ``pip install --upgrade mmx-cli``, 而 PyPI 上根本没有这个发行版 ——
命令必然失败, 然后被错误处理吞掉, 于是部署"看起来成功了"。
本机实况: ``~/.local/bin/mmx -> ../lib/node_modules/mmx-cli/dist/mmx.mjs`` (shebang 是 node)。

因此安装动作改为: 探测 node/npm → ``npm install -g mmx-cli`` → 校验 ``mmx --version``。
缺 node/npm 时按平台给出安装途径 (brew / apt / winget / choco), 而不是假装装上了。

**v5.4.36**: 探测与安装都交给 ``deploy_scan`` —— 包括"全局装不动就退回私有前缀
``$VIA54_HOME/tools/node``"(openclaw ``install-cli.sh`` 的 rootless 思路) 与"装完必须
复验可执行文件"。本文件不再自己拼路径, 否则从私有前缀装的会被自己的探测判成"没装"，
于是每次都重装一遍。

想一次把整套环境(含 OCR 等)都过一遍, 用 ``python3 scripts/deploy_scan.py``。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_scan as ds                                        # noqa: E402


def check_mmx_installed():
    return bool(ds._which("mmx") or ds._which("mmx-cli"))


def install_mmx_cli():
    """经 npm 安装。返回 (ok, detail)。"""
    if not (ds._which("node") and ds._which("npm")):
        ok, msg = ds.system_install({"brew": "node", "apt-get": "nodejs",
                                     "dnf": "nodejs", "pacman": "nodejs",
                                     "winget": "OpenJS.NodeJS.LTS", "choco": "nodejs"})
        if not ok:
            return False, ("本机没有 node/npm, 且自动安装未成功: %s "
                           "(装好 Node.js 后再跑 `npm install -g mmx-cli`)" % msg)
        if not (ds._which("node") and ds._which("npm")):
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

    print("==========================================")
    print(" via54Medit Vision 引擎部署状态")
    print(" 私有前缀(装不动全局时的兜底): %s" % ds.NODE_PREFIX)
    print("==========================================")
    print(" 默认 Vision Provider: mmx (VISION_PROVIDER=mmx)")
    if installed:
        path = ds._which("mmx") or ds._which("mmx-cli")
        ok, out = ds._run([path, "--version"], timeout=60)
        print(" mmx-cli: 已就绪 %s  (%s)" % (out.splitlines()[0].strip() if ok and out else "", path))
        up = ds._run([ds._which("npm") or "npm", "view", "mmx-cli", "version"], timeout=120)
        if up[0] and up[1] and up[1].strip().splitlines()[0] not in (out or ""):
            print(" 提示: npm 上最新版为 %s, 升级: npm install -g mmx-cli" % up[1].strip().splitlines()[0])
    else:
        print(" mmx-cli: ✗ 仍需处理 —— npm install -g mmx-cli")

    # 凭据**只认 mmx 自己的状态**。以前这里读 MINIMAX_API_KEY, 是接错了对象:
    # mmx 用 `mmx auth login` 把凭据写进 ~/.mmx/config.json, 与那个环境变量是两套;
    # 照环境变量下结论会同时产生假警报(已认证却报"调用会失败")与假就绪(配了环境变量
    # 但没登录, 报"已配置"而实际 401)。
    auth_ok, auth_detail = ds._probe_mmx_auth()
    print(" 凭据    : %s %s" % ("✓" if auth_ok else "✗", auth_detail))
    if not auth_ok:
        print(" 补法    : export MINIMAX_API_KEY=... 后重跑本脚本(部署流程会代登),")
        print("           或交互式执行 `mmx auth login`(OAuth)")
    print(" 复检    : python3 scripts/deploy_scan.py --verify-mmx")
    print("==========================================")
    return installed and auth_ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                           # noqa: BLE001
        pass
    sys.exit(0 if verify_and_configure() else 1)
