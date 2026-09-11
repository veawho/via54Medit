#!/usr/bin/env python3
"""bootstrap_device.py — via54Medit 设备部署 / 版本更新后的一键就绪初始化

在**任何**新设备上部署完、或**更新到任何版本之后**, 都跑这一条:

    python3 scripts/bootstrap_device.py

它做四件事:
  1. **深度扫描本机环境 + 按平台补齐缺口** —— 交给 scripts/deploy_scan.py:
     只装"与本平台相关且确实缺失"的能力, 并按正确通道装
     (Python 包走 pip、mmx-cli 走 npm、系统工具走 brew/apt/winget/choco/scoop)。
     与平台无关的能力会被明确标成"不适用", **不安装也不校验**。
     分阶段跑(``--stage env|deps|compat``), 这样进度是可见的, 而不是等一大坨输出。
  2. **渲染通道真出图自检** —— 交给 scripts/render_doctor.py: "探测到"不等于"能出图"。
  3. **构建 Go 二进制**(有 go 工具链时)。
  4. **注册自动更新守护任务**(按平台选 launchd / cron / schtasks)。

本脚本**幂等**: 重复运行、或在版本更新后运行, 都只会补上当时缺的东西。

先看要装什么, 再决定装不装
--------------------------
    python3 scripts/bootstrap_device.py --dry-run

``--dry-run`` 会把第 1 步换成"只报计划" —— 打印出**真会执行的那条命令**, 不落地任何修改。
这是参考 openclaw 的 ``--dry-run`` 加的; 与之配套的还有 deploy_scan.py 的 ``--only``
(只补单个能力) 与安装后的**复验**(安装器说成功不算, 复验通过才算)。

为什么不再自己装依赖 (v5.4.34 更正)
-----------------------------------
旧版本这里直接跑 ``pip install --upgrade pymupdf python-pptx pillow requests mmx-cli``:
  * ``mmx-cli`` **不是 PyPI 包**(是 npm 包), 这条必然失败, 却被退出码吞掉;
  * 无条件安装, 不分平台 —— 例如在 macOS 上也把 Windows 专属的 pywin32 列进清单;
  * 完全不检测 OCR, 缺了也没人知道。
现在这些逻辑统一收在 ``deploy_scan.py`` 的**能力矩阵**里(唯一事实来源), 并由 CI 在三平台验证。
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_DIR / "scripts"


def step_print(title):
    print("\n==> %s" % title, flush=True)


def run_cmd(cmd, cwd=REPO_DIR, timeout=1800):
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return res.returncode == 0, (res.stdout or "").strip(), (res.stderr or "").strip()


def _supported_flags(script):
    """探测脚本支持哪些开关(避免在 Windows 上误调 --install-launchd)。"""
    try:
        r = subprocess.run([sys.executable, str(script), "--help"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_DIR))
        return (r.stdout or "") + (r.stderr or "")
    except Exception:                                       # noqa: BLE001
        return ""


def step_deep_scan(plan=False):
    """第 1 步 —— 分阶段跑部署扫描器。

    hermes-agent 的安装器把流程切成可单独复跑的 ``--stage``(prerequisites /
    repository / venv / …), 外层部署器因此能逐步显示进度、失败时也能只重跑一段。
    这里借同一套做法: 环境 -> 依赖/工具 -> 平台兼容性。

    返回 True 表示"必需能力齐备"。
    """
    step_print("1. 深度扫描系统环境 + 按平台补齐缺口 (deploy_scan.py%s)"
               % ("、--dry-run 预演)" if plan else ")"))
    script = SCRIPTS / "deploy_scan.py"
    if not script.exists():
        print("  ✗ 未找到 scripts/deploy_scan.py")
        return False
    extra = ["--dry-run"] if plan else []

    # 阶段一: 环境(只读, 永远成功; 失败说明连解释器都不对)
    res = subprocess.run([sys.executable, str(script), "--stage", "env"] + extra,
                         cwd=str(REPO_DIR))
    if res.returncode not in (0, 1):
        print("  ✗ 环境阶段未能完成 (退出码 %d)" % res.returncode)
        return False

    # 阶段二: 依赖/工具 —— 这一步才会真的装东西
    print("  ── 依赖与工具 ──", flush=True)
    deps = subprocess.run([sys.executable, str(script), "--stage", "deps"] + extra,
                          cwd=str(REPO_DIR))
    if deps.returncode not in (0, 1):
        print("  ✗ 依赖阶段未能完成 (退出码 %d)" % deps.returncode)
        return False

    # 阶段三: 平台兼容性(只读)
    subprocess.run([sys.executable, str(script), "--stage", "compat"] + extra,
                   cwd=str(REPO_DIR))

    if plan:
        print("  ✓ 以上为预演, **未做任何修改**。去掉 --dry-run 即可真正执行")
        return True
    if deps.returncode == 0:
        print("  ✓ 必需能力已齐备")
        return True
    print("  ⚠️ 仍有必需缺口 —— 见上面报告的 '→ 处理:' 行; 修好后重跑本脚本即可")
    return False


def step_render_doctor():
    step_print("2. 渲染通道真出图自检 (render_doctor.py)")
    script = SCRIPTS / "render_doctor.py"
    if not script.exists():
        print("  ~ 未找到 scripts/render_doctor.py, 跳过")
        return
    res = subprocess.run([sys.executable, str(script)], cwd=str(REPO_DIR))
    if res.returncode == 0:
        print("  ✓ 渲染通道就绪")
    else:
        print("  ⚠️ 渲染通道未就绪 —— 后果: PPT/Word 管线会在渲染这步失败。")
        print("     这不是缺陷而是环境限制: 按规范版式只由微软引擎产出, 不会自动换引擎。")
        print("     可选: 修好自动化权限(见上面的提示), 或显式设 RENDER_ENGINE=graph(需凭据)。")


def step_build_go():
    step_print("3. 构建 Go 核心二进制程序")
    if not shutil.which("go"):
        print("  ~ 未找到 go 工具链, 跳过 (使用预编译的 bin/medit 也正常)")
        return
    (REPO_DIR / "bin").mkdir(exist_ok=True)
    ok1, _, err1 = run_cmd(["go", "build", "-o", "bin/medit", "./cmd/medit"])
    ok2, _, err2 = run_cmd(["go", "build", "-o", "bin/medit-mcp", "./cmd/medit-mcp"])
    if ok1 and ok2:
        print("  ✓ bin/medit 与 bin/medit-mcp 编译成功")
    else:
        print("  ⚠️ 编译未成功: %s %s" % (err1 or "", err2 or ""))


def step_periodic_sync():
    step_print("4. 注册自动更新 (定时从 GitHub 拉取)")
    script = SCRIPTS / "auto_sync.py"
    if not script.exists():
        print("  ✗ 未找到 auto_sync.py")
        return
    flags = _supported_flags(script)
    if sys.platform == "darwin" and "--install-launchd" in flags:
        flag = "--install-launchd"
    elif os.name == "nt" and "--install-schtasks" in flags:
        flag = "--install-schtasks"
    elif "--install-cron" in flags:
        flag = "--install-cron"
    else:
        print("  ✗ 当前平台没有可用的自动注册方式 —— auto_sync.py 支持的开关: %s"
              % (", ".join(f for f in ("--install-launchd", "--install-cron",
                                       "--install-schtasks") if f in flags) or "无"))
        print("     Windows 可用计划任务手动注册: schtasks /create /tn via54MeditSync "
              "/tr \"python <repo>\\scripts\\auto_sync.py\" /sc daily")
        return
    ok, out, err = run_cmd([sys.executable, str(script), flag])
    print("  %s" % (out or err or ("已注册 %s" % flag)))


def main():
    argv = sys.argv[1:]
    plan = "--dry-run" in argv or "--plan" in argv
    print("======================================================")
    print(" via54Medit 设备部署 / 版本更新后的一键就绪初始化")
    print(" (兼容 Traework / Hermes / Codex / OpenClaw / DeepSeek)")
    print(" 可重复运行: 只会补上当时缺的东西")
    if plan:
        print(" 模式: --dry-run 预演 (不会改动任何东西)")
    print("======================================================")
    scan_ok = step_deep_scan(plan=plan)
    if plan:
        print("\n预演结束。真正执行: python3 scripts/bootstrap_device.py")
        return 0
    step_render_doctor()
    step_build_go()
    step_periodic_sync()

    print("\n======================================================")
    print(" 初始化完成%s" % ("" if scan_ok else "(仍有缺口, 见上)"))
    print(" 默认配置:")
    print("   • Vision Engine: mmx-cli (VISION_PROVIDER=mmx, 经 npm 安装)")
    print("   • PPT Engine   : 桌面版 Microsoft PowerPoint (默认) / Microsoft Graph (RENDER_ENGINE=graph)")
    print("   • OCR          : PaddleOCR (L2 中文识别, pip 安装)")
    print("   • Auto-Sync    : 已按平台注册系统定时任务")
    print(" 复检任意时刻: python3 scripts/deploy_scan.py --check")
    print(" 预演将要做什么: python3 scripts/bootstrap_device.py --dry-run")
    print("======================================================")
    return 0 if scan_ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    sys.exit(main())
