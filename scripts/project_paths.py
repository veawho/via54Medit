"""业务项目目录统一入口。

为什么需要它
------------
仓库里有 200+ 个业务脚本把 ``~/Desktop/雷管方案_文献整理`` / ``~/Desktop/TMA_文献整理``
以及其他业务目录写死在代码里。它们虽然用了 ``os.path.expanduser("~")``, 但仍然是:

1. 硬编码目录名 —— 用户把项目放在其他位置就要改源码;
2. 散落重复 —— 同一字符串在几十处重复, 一处改漏就出错;
3. 与平台假设耦合 —— 默认项目必须在 ``~/Desktop`` 下。

本模块提供统一入口, 优先读环境变量, 回退到默认 Desktop 路径。
新脚本应直接从这里导入; 旧脚本在重构时逐步迁移。
"""
import os


def _root(env_var: str, default_name: str) -> str:
    """优先环境变量, 其次 ~/Desktop/<default_name>。"""
    v = os.environ.get(env_var, "").strip()
    if v:
        return os.path.expanduser(v)
    return os.path.expanduser(os.path.join("~", "Desktop", default_name))


#: TMA 项目根目录。可通过 ``VIA54_TMA_DIR`` 覆盖。
TMA_ROOT = _root("VIA54_TMA_DIR", "TMA_文献整理")

#: 雷管方案项目根目录。可通过 ``VIA54_LEIGUAN_DIR`` 覆盖。
LEIGUAN_ROOT = _root("VIA54_LEIGUAN_DIR", "雷管方案_文献整理")

#: TMA 测试/示例项目根目录。可通过 ``VIA54_TMA_TEST_DIR`` 覆盖。
TMA_TEST_ROOT = _root("VIA54_TMA_TEST_DIR", "TMA_test")

#: HLO 设计稿目录。可通过 ``VIA54_HLO_DIR`` 覆盖。
HLO_DIR = _root("VIA54_HLO_DIR", "HLO_design")

#: HLO NLU 数据库路径。可通过 ``VIA54_HLO_DB`` 覆盖。
HLO_DB = os.environ.get("VIA54_HLO_DB") or os.path.expanduser(
    os.path.join("~", "Desktop", "hlo_nlu.sqlite")
)


def tma_path(*parts: str) -> str:
    """返回 TMA 项目下的子路径。"""
    return os.path.join(TMA_ROOT, *parts)


def leiguan_path(*parts: str) -> str:
    """返回雷管方案项目下的子路径。"""
    return os.path.join(LEIGUAN_ROOT, *parts)


def tma_test_path(*parts: str) -> str:
    """返回 TMA 测试项目下的子路径。"""
    return os.path.join(TMA_TEST_ROOT, *parts)


def hlo_path(*parts: str) -> str:
    """返回 HLO 设计稿目录下的子路径。"""
    return os.path.join(HLO_DIR, *parts)
