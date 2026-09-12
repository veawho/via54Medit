#!/usr/bin/env python3
"""bootstrap_device.py — via54Medit 设备部署 / 版本更新后的一键就绪初始化

在**任何**新设备上部署完、或**更新到任何版本之后**, 都跑这一条:

    python3 scripts/bootstrap_device.py

它对应用户定义的 5 步部署流程, 具体做八件事:
  1. **深度扫描本机环境 + 按平台补齐缺口** —— 交给 scripts/deploy_scan.py:
     只装"与本平台相关且确实缺失"的能力, 并按正确通道装
     (Python 包走 pip、mmx-cli 走 npm、系统工具走 brew/apt/winget/choco/scoop)。
     与平台无关的能力会被明确标成"不适用", **不安装也不校验**。
     分阶段跑(``--stage env|deps|compat``), 这样进度是可见的, 而不是等一大坨输出。
  2. **渲染通道真出图自检** —— 交给 scripts/render_doctor.py: "探测到"不等于"能出图"。
  3. **构建 Go 二进制**(有 go 工具链时)。
  4. **校验视觉/OCR 通道真能出结果** —— 交给 ``deploy_scan.py --verify-ocr`` 与
     ``--verify-mmx``。**不是**"看到文件在": OCR 只 import 成功会被报成就绪, 但权重没下时
     首次调用会突然联网; mmx 只装了二进制也会被报成就绪, 但没认证时调用直接 401。
     所以这里真跑一次识别(凭据缺失只记警告 —— 凭据得由人给)。
  5. **强制校验 LLM 接入与 token 用量可读性** —— 交给 ``deploy_scan.py --verify-llm``:
     接入了哪些 LLM、它们的 token 消耗能不能真的读进库。记账是旁路, 少了不会报错,
     所以这一步不能靠"记得去看"; 校验失败时本脚本以非 0 退出。
  6. **全量测试所有功能** —— Python 测试套件 + Go ``go test ./...``, 部署/更新后必须
     确认没有回归。
  7. **清理旧代码与运行时缓存** —— 删除 ``__pycache__`` / ``*.pyc``, 确保当前部署干净稳定。
  8. **注册自动更新守护任务**(按平台选 launchd / cron / schtasks)。

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
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                         encoding="utf-8", errors="replace")
    return res.returncode == 0, (res.stdout or "").strip(), (res.stderr or "").strip()


def _supported_flags(script):
    """探测脚本支持哪些开关(避免在 Windows 上误调 --install-launchd)。"""
    try:
        r = subprocess.run([sys.executable, str(script), "--help"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_DIR),
                           encoding="utf-8", errors="replace")
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
    bin_dir = REPO_DIR / "bin"
    bin_dir.mkdir(exist_ok=True)

    # 适配 Windows 可执行文件后缀
    exe = ".exe" if sys.platform == "win32" or os.name == "nt" else ""
    medit_out = f"bin/medit{exe}"
    mcp_out = f"bin/medit-mcp{exe}"

    # 提取版本戳记 (对齐 Makefile ldflags 机制)
    _, version_str, _ = run_cmd(["git", "describe", "--tags", "--always", "--dirty"])
    if not version_str:
        version_str = "dev"
    _, commit_str, _ = run_cmd(["git", "rev-parse", "--short", "HEAD"])
    if not commit_str:
        commit_str = "unknown"
    import datetime
    build_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, go_ver, _ = run_cmd(["go", "version"])

    ldflags = (
        f"-s -w "
        f"-X github.com/veawho/via54Medit/internal/version.Version={version_str} "
        f"-X github.com/veawho/via54Medit/internal/version.Commit={commit_str} "
        f"-X github.com/veawho/via54Medit/internal/version.BuildDate={build_date} "
        f"-X \"github.com/veawho/via54Medit/internal/version.GoVersion={go_ver}\""
    )

    env = os.environ.copy()
    env["CGO_ENABLED"] = "0"
    ok1, _, err1 = run_cmd(["go", "build", "-ldflags", ldflags, "-o", medit_out, "./cmd/medit"])
    ok2, _, err2 = run_cmd(["go", "build", "-ldflags", ldflags, "-o", mcp_out, "./cmd/medit-mcp"])
    if ok1 and ok2:
        print(f"  ✓ {medit_out} 与 {mcp_out} 编译成功 ({version_str})")
    else:
        print("  ⚠️ 编译未成功: %s %s" % (err1 or "", err2 or ""))


def step_verify_vision():
    """校验**视觉/OCR 两条通道真能出结果** —— 不是"看到文件在"。

    为什么必须真跑一次: "装上了"与"能跑"是两件事, 而这个差别在报告里看不出来。
    OCR 只有 import 成功会被报成就绪, 但权重没下时首次调用会在业务路径上突然联网
    (离线/受限网络直接失败); mmx 只有二进制存在也会被报成就绪, 但没认证时调用直接 401。
    所以这里跑的是 ``deploy_scan.py --verify-ocr``(真识别一次) 与 ``--verify-mmx``
    (二进制 + 认证分开判)。

    返回 ``(ok, warnings)``: **凭据缺失只记警告**, 不算失败 —— 凭据必须由人提供,
    把它算成部署失败会让部署永远无法成功(与矩阵里 mmx_auth 的 gate=False 同一条判断)。
    """
    step_print("4. 校验视觉/OCR 通道真能出结果 (deploy_scan.py --verify-ocr / --verify-mmx)")
    script = SCRIPTS / "deploy_scan.py"
    if not script.exists():
        print("  ✗ 未找到 scripts/deploy_scan.py")
        return False, []

    warnings = []
    ocr = subprocess.run([sys.executable, str(script), "--verify-ocr"], cwd=str(REPO_DIR))
    if ocr.returncode == 0:
        print("  ✓ OCR 真识别通过 (权重已就绪, 首次业务调用不需联网)")
    else:
        print("  ✗ OCR 真识别未通过 —— 后果: 纯图片页无法识别, 且失败点在 L2 那一步。")
        print("     排查: python3 scripts/deploy_scan.py --verify-ocr")

    mmx = subprocess.run([sys.executable, str(script), "--verify-mmx"], cwd=str(REPO_DIR))
    if mmx.returncode != 0:
        print("  ✗ mmx-cli 不可用 —— 后果: VISION_PROVIDER=mmx 的视觉校验全失败。")
        print("     补法: npm install -g mmx-cli")

    # 凭据单独再判一次: --verify-mmx 的退出码**故意**不反映它(凭据必须由人提供,
    # 把它算成部署失败会让部署永远无法成功)。这里只降级成警告。
    from_deploy_scan = (
        "import sys; sys.path.insert(0, {p!r}); import deploy_scan as d;"
        " ok, detail = d._probe_mmx_auth();"
        " print('' if ok else detail);"          # 成功时 --verify-mmx 已报过
        " sys.exit(0 if ok else 1)".format(p=str(SCRIPTS)))
    auth = subprocess.run([sys.executable, "-c", from_deploy_scan], cwd=str(REPO_DIR))
    if auth.returncode != 0:
        warnings.append("mmx 未认证")
        print("  ⚠️ mmx 未认证 —— 视觉调用会 401。补法: export MINIMAX_API_KEY=... 后重跑, "
              "或交互式 `mmx auth login`")

    return (ocr.returncode == 0 and mmx.returncode == 0), warnings


def step_verify_llm():
    """**强制**校验接入了哪些 LLM, 以及它们的 token 消耗真能读进库。

    为什么要强制而不是可选: 记账是旁路 —— 一条路径不记用量, 调用本身不会报任何错,
    报表只是安静地少一块数字。实测抓到过两处(``scripts/provider_llm.py`` 返回 usage
    却从不写库; Go 侧 ``internal/foundation/llm.go`` 整个丢弃 usage), 都不会让任何
    测试变红。所以部署/更新后必须主动验一次, 且失败要能被看见。
    """
    step_print("5. 校验 LLM 接入与 Token 用量可读性 (deploy_scan.py --verify-llm)")
    script = SCRIPTS / "deploy_scan.py"
    if not script.exists():
        print("  ✗ 未找到 scripts/deploy_scan.py")
        return False
    res = subprocess.run([sys.executable, str(script), "--verify-llm"],
                         cwd=str(REPO_DIR))
    if res.returncode == 0:
        print("  ✓ 已接入的 LLM 全部可读 token 用量")
        return True
    print("  ✗ LLM 接入校验未通过 —— 后果: token 统计会缺一块, 且调用不会报错。")
    print("     排查: medit-telemetry llm -v   (看是哪个 provider 的哪条通道没在记)")
    return False


def step_full_tests():
    """全量测试 —— 部署/更新后必须确认没有回归。

    包含 Python 测试套件与 Go 全包测试。失败即阻塞结论, 避免"能启动但功能坏"
    的状态被当成已就绪。
    """
    step_print("6. 全量测试所有功能")
    python_ok = False
    go_ok = False

    if shutil.which("pytest") or run_cmd([sys.executable, "-m", "pytest", "--version"])[0]:
        res = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                             cwd=str(REPO_DIR))
        python_ok = res.returncode == 0
        if python_ok:
            print("  ✓ Python 测试通过 (pytest)")
        else:
            print("  ✗ Python 测试未通过 —— 排查: python3 -m pytest tests/ -v")
    else:
        # 对标主流方案: 无 pytest 时平滑回退到 Python 内置的 unittest discover，绝不静默漏测
        print("  ~ 未找到 pytest，优雅回退至内置 unittest discover 验证...")
        res = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                             cwd=str(REPO_DIR))
        python_ok = res.returncode == 0
        if python_ok:
            print("  ✓ Python 测试通过 (unittest discover)")
        else:
            print("  ✗ Python 测试未通过 —— 排查: python3 -m unittest discover -s tests -v")

    if shutil.which("go"):
        res = subprocess.run(["go", "test", "./..."], cwd=str(REPO_DIR))
        go_ok = res.returncode == 0
        if go_ok:
            print("  ✓ Go 测试通过")
        else:
            print("  ✗ Go 测试未通过 —— 排查: go test ./...")
    else:
        print("  ~ 未找到 go 工具链, 跳过 Go 测试")

    return python_ok, go_ok


def step_cleanup():
    """清理旧代码/运行时缓存, 确保当前部署干净、稳定。"""
    step_print("7. 清理旧代码与运行时缓存")
    cleaned = {"pycache": 0, "pyc": 0}

    for root, dirs, files in os.walk(REPO_DIR):
        # 跳过 .git 与虚拟环境, 避免误删
        if ".git" in root.split(os.sep) or ".venv" in root.split(os.sep):
            continue
        for d in list(dirs):
            if d == "__pycache__":
                try:
                    shutil.rmtree(os.path.join(root, d))
                    cleaned["pycache"] += 1
                except OSError as e:
                    print(f"  ~ 无法清理 {os.path.join(root, d)}: {e}")
        for f in files:
            if f.endswith(".pyc"):
                try:
                    os.remove(os.path.join(root, f))
                    cleaned["pyc"] += 1
                except OSError as e:
                    print(f"  ~ 无法删除 {os.path.join(root, f)}: {e}")

    print(f"  ✓ 清理完成: {cleaned['pycache']} 个 __pycache__, {cleaned['pyc']} 个 .pyc")
    return True


def step_periodic_sync():
    step_print("8. 注册自动更新 (定时从 GitHub 拉取)")
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
    # LLM 记账校验必须发生在"动过代码之后"(build_go 之后), 且**不可跳过** ——
    # 除非显式给 --no-verify-llm(给确实无法验证的环境留一条明路, 但会记进结论)。
    vision_ok, vision_warnings = step_verify_vision()
    llm_ok = True
    if "--no-verify-llm" in argv:
        print("\n5. LLM 接入校验: 已按 --no-verify-llm 跳过")
    else:
        llm_ok = step_verify_llm()
    python_ok, go_ok = step_full_tests()
    step_cleanup()
    if "--no-periodic-sync" in argv:
        print("\n8. 注册自动更新: 已按 --no-periodic-sync 跳过")
    else:
        step_periodic_sync()

    ready = scan_ok and llm_ok and vision_ok and python_ok and go_ok
    print("\n======================================================")
    print(" 初始化完成%s" % ("" if ready else "(仍有缺口, 见上)"))
    if not vision_ok:
        print(" ⚠️ 视觉/OCR 通道校验未通过: 图片页识别或视觉校验会失败。")
    if not llm_ok:
        print(" ⚠️ LLM 接入校验未通过: token 统计会缺一块, 而这些调用不会报任何错。")
    if not python_ok:
        print(" ⚠️ Python 全量测试未通过: 功能回归风险。")
    if not go_ok:
        print(" ⚠️ Go 全量测试未通过: 核心功能回归风险。")
    for w in vision_warnings:
        print(" ⚠️ %s" % w)
    print(" 默认配置:")
    print("   • Vision Engine: mmx-cli (VISION_PROVIDER=mmx, 强制; 其他 vision 方式均为可选)")
    print("   • PPT Engine   : 桌面版 Microsoft PowerPoint (唯一强制渲染方式)")
    print("   • OCR          : PaddleOCR (L2 中文识别, pip 安装 + 权重预热)")
    print("   • Feishu/lark-cli: 可选能力, 不强制部署")
    sync_state = "本次未注册(用了 --no-periodic-sync)" if "--no-periodic-sync" in argv else "已按平台注册系统定时任务"
    print("   • Auto-Sync    : %s" % sync_state)
    print(" 复检任意时刻: python3 scripts/deploy_scan.py --check")
    print(" 复检 LLM 记账: python3 scripts/deploy_scan.py --verify-llm")
    print(" 复检 OCR/mmx : python3 scripts/deploy_scan.py --verify-ocr / --verify-mmx")
    print(" 预演将要做什么: python3 scripts/bootstrap_device.py --dry-run")
    print("======================================================")
    return 0 if ready else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    sys.exit(main())
