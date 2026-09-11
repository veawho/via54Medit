#!/usr/bin/env python3
"""deps_auto.py — 环境自检 + 按平台补齐缺口 (薄适配层)

**v5.4.34 起依赖清单不再在这里维护** —— 已统一到 ``deploy_scan.py`` 的**能力矩阵**
(唯一事实来源)。此前有三份互不同步的清单在打架:

  * ``deps_auto.py`` / ``bootstrap_device.py`` / ``install_mmx.py`` 各自维护一份;
  * 其中两份都写 ``pip install mmx-cli`` —— 而 mmx-cli **不是 PyPI 包**(是 npm 包),
    这条命令永远失败, 还被退出码吞掉, 于是"看起来装过了";
  * 三份清单都**不检测 OCR**(paddleocr), 缺了没人知道;
  * 都不按平台过滤(Windows 专属的 pywin32 被无条件列进安装清单)。

保留 ``ensure_env()`` 是因为 ``scripts/via54_auto.py``(管线第 [0] 步)与
``medit doctor --fix`` 在调用它。

用法:
  python3 scripts/deps_auto.py             # 自检 + 按平台补齐
  python3 scripts/deps_auto.py --check      # 只自检, 不安装
  python3 scripts/deps_auto.py --skip-heavy # 跳过重依赖(OCR)
  from deps_auto import ensure_env
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_scan as ds                                        # noqa: E402

#: 与 deploy_scan 的能力矩阵保持同义(供旧调用方读取)。
MIN_PY = (3, 10)


def ensure_env(install=True, include_heavy=True):
    """自检 + 按平台补齐缺口; 返回 ``(ok, problems)``。

    ``problems`` = "必需、受门禁、且仍然缺失"的能力标签(与旧版语义一致)。
    直接打印完整报告, 便于调用方在管线日志里看到缺口。
    """
    result, _osname = ds.collect(install=install, include_heavy=include_heavy)
    ds._render(result)
    problems = ["%s" % r["label"] for r in result["capabilities"]
                if r["status"] == ds.MISSING and r["required"] and r["gate"]]
    return (not problems), problems


def main():
    install = "--no-install" not in sys.argv and "--check" not in sys.argv
    include_heavy = "--skip-heavy" not in sys.argv
    ok, problems = ensure_env(install=install, include_heavy=include_heavy)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                           # noqa: BLE001
        pass
    sys.exit(main())
