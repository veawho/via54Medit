"""跨平台路径解析 (TraeWork 数据目录 / 桌面 / Windows 启动项)。

历史实现把 TraeWork 的用户数据路径硬编码为 Windows 形式
(``~\\AppData\\Roaming\\TRAE SOLO CN\\...``)，导致 macOS / Linux 上：

  - 飞书凭据嗅探 (``channel_config.json``) 永远找不到，app_id / app_secret
    只能手工填写，模块设计好的"零配置"能力在非 Windows 平台失效；
  - 默认监控目录 ``~\\.trae-cn\\work``、``~\\Desktop`` 反斜杠在 POSIX 下是
    普通字符，路径不存在，守护进程空转；
  - 桌面伴随启动器写到不存在的路径，创建即失败。

本模块按平台给出正确路径，并为每个平台保留候选兜底：即使路径结构变化、
或用户把 TraeWork 数据搬到非默认位置，仍能命中。所有函数均为纯读取，
不产生副作用，可安全用于模块级常量初始化。
"""

import os
import sys
from typing import List, Optional

#: TraeWork 应用数据目录名 (Windows / macOS / Linux 一致)
APP_DIR_NAME = "TRAE SOLO CN"

#: 飞书桥接数据在应用数据根下的相对子路径
BRIDGE_SUBPATH = os.path.join(
    "User", "globalStorage", "cloudide.icube-im-bridge", "feishu-bridge"
)

#: 历史固定的 workspace 槽位号；实际以 glob 结果优先，此处仅作首选探测
DEFAULT_WORKSPACE_ID = "3401238267317833"

#: channel_config.json 文件名
CHANNEL_CONFIG_NAME = "channel_config.json"


def _home() -> str:
    return os.path.expanduser("~")


def app_data_roots() -> List[str]:
    """TraeWork 应用数据根目录候选，当前平台优先，其余平台兜底。

    Windows: ``%APPDATA%``
    macOS:   ``~/Library/Application Support``
    Linux:   ``$XDG_CONFIG_HOME`` 或 ``~/.config``
    """
    home = _home()
    win = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    mac = os.path.join(home, "Library", "Application Support")
    lin = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return {
        "win32": [win, mac, lin],
        "darwin": [mac, lin, win],
    }.get(sys.platform, [lin, mac, win])


def trae_work_config_candidates() -> List[str]:
    """``channel_config.json`` 候选路径列表 (当前平台优先，去重保序)。

    除固定 workspace 槽位外，还会扫描 ``feishu-bridge`` 下任意 workspace
    子目录，避免多账号/多工作区换机后槽位号变化导致嗅探失败。
    """
    out: List[str] = []
    for root in app_data_roots():
        base = os.path.join(root, APP_DIR_NAME, BRIDGE_SUBPATH)
        preferred = os.path.join(base, DEFAULT_WORKSPACE_ID, CHANNEL_CONFIG_NAME)
        if preferred not in out:
            out.append(preferred)
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            path = os.path.join(base, name, CHANNEL_CONFIG_NAME)
            if os.path.isfile(path) and path not in out:
                out.append(path)
    return out


def trae_work_config_path() -> str:
    """首个真实存在的 ``channel_config.json``；均不存在时返回平台首选路径。

    返回空字符串仅当候选列表为空 (理论上不会发生)。
    """
    candidates = trae_work_config_candidates()
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0] if candidates else ""


def desktop_dir() -> str:
    """用户桌面目录，兼容本地化名称 (``Desktop`` / ``桌面``)。"""
    home = _home()
    for name in ("Desktop", "桌面"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return os.path.join(home, "Desktop")


def trae_work_dir() -> str:
    """TraeWork 工作目录 (``~/.trae-cn/work``)，跨平台一致。"""
    return os.path.join(_home(), ".trae-cn", "work")


def windows_startup_dir() -> Optional[str]:
    """Windows 开机启动文件夹；非 Windows 平台返回 ``None``。"""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA") or os.path.join(_home(), "AppData", "Roaming")
    return os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def trae_work_exe() -> Optional[str]:
    """Windows 版 TraeWork 可执行文件路径；非 Windows 平台返回 ``None``。"""
    if sys.platform != "win32":
        return None
    local = os.environ.get("LOCALAPPDATA") or os.path.join(_home(), "AppData", "Local")
    return os.path.join(local, "Programs", APP_DIR_NAME, f"{APP_DIR_NAME}.exe")
