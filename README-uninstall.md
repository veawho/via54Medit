# via54Medit 完全卸载与系统清理指南 / Complete Uninstallation & System Cleanup Guide

> **🌐 语言 / Language**: 本文为双语版本 (This document is bilingual) · [🇨🇳 中文版](#中文指南) · [🇺🇸 English](#english-guide)

---

<a name="中文指南"></a>
## 🇨🇳 中文指南

本版本（**v5.4.52**）是 `via54Medit` 的系统卸载与环境清理专用版本，旨在提供一键式、跨平台（Windows / macOS / Linux）彻底移除与归档能力。

### 卸载目标与涵盖内容
1. **停止运行中的进程**：立即终止正在后台运行的 `telemetry` 守护进程、用量采集器（`usage_collector`）、周一校验（`monday_finalize`）等进程。
2. **清除定时排程**：
   - **Windows**：自动注销系统计划任务 `medit-usage-collector`、`medit-monday-finalize`、`MeditTelemetryWeekly`、`MeditTelemetryMonthly`。
   - **macOS / Linux**：清除系统 `crontab` 中所有 medit 相关的自动采集与上报条目，并卸载 macOS `LaunchAgent`。
3. **移除自启动项**：清除 Windows 开机自启文件夹（`Startup`）内的 `traework_telemetry_silent.vbs` 与伴随启动脚本。
4. **彻底删除部署目录**：完全移除用户主目录下的 `~/.via54medit`（执行程序与脚本）与 `~/.medit`（数据库、配置、日志、缓存）。
5. **清理工作伙伴与技能残留**：彻底移除豆包/飞书 `lark-chats` 解压工作区及用户技能目录中的 `via54medit*` 技能包。
6. **清理安装缓存**：移除 `Downloads` 与 `Temp` 目录中的安装包压缩包与历史发布缓存。
7. **清理本地代码仓库**：支持配合 `--clean-repo` 参数直接删除本地 Git 代码仓库。

---

### 一键卸载命令

#### Windows 系统 (PowerShell)
```powershell
# 1. 仅卸载系统部署组件并清理环境（保留本地 Git 仓库）
powershell -ExecutionPolicy Bypass -File uninstall.ps1

# 2. 全量卸载并一并清理本地代码仓库
powershell -ExecutionPolicy Bypass -File uninstall.ps1 -CleanRepo
```

#### 跨平台运行 (Python 3)
```bash
# 1. 全量卸载系统部署组件
python uninstall.py

# 2. 全量卸载并一并删除本地代码仓库
python uninstall.py --clean-repo
```

#### macOS / Linux 系统 (Shell)
```bash
# 赋予执行权限并运行
chmod +x uninstall.sh
./uninstall.sh

# 同时清理本地仓库
./uninstall.sh --clean-repo
```

---

<a name="english-guide"></a>
## 🇺🇸 English Guide

Release **v5.4.52** is a dedicated uninstaller and environment cleanup release for `via54Medit`, providing one-step, cross-platform (Windows / macOS / Linux) complete eradication and retirement.

### Scope of Uninstallation
1. **Process Termination**: Immediately terminates running background daemons (`telemetry.cli daemon`), usage collectors, and scheduled sync workers.
2. **Scheduled Task Removal**:
   - **Windows**: Unregisters Windows Task Scheduler entries `medit-usage-collector`, `medit-monday-finalize`, `MeditTelemetryWeekly`, `MeditTelemetryMonthly`.
   - **macOS / Linux**: Cleans up user `crontab` entries for via54Medit and unloads macOS `LaunchAgent`.
3. **Autostart Cleanup**: Deletes autostart scripts (`traework_telemetry_silent.vbs`) from the Windows Startup directory.
4. **Directory Removal**: Completely deletes runtime and data directories: `~/.via54medit` and `~/.medit`.
5. **Partner & Skill Cleanup**: Purges unpacked Doubao/Lark workspaces and user skills matching `via54medit*`.
6. **Cache & Archive Cleanup**: Clears downloaded installation zip files and temporary release caches.
7. **Repository Cleanup**: Cleans up local Git repository clones when `--clean-repo` or `-CleanRepo` is specified.

---

### Quick Commands

#### Windows (PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File uninstall.ps1 -CleanRepo
```

#### Cross-Platform (Python)
```bash
python uninstall.py --clean-repo
```

#### macOS / Linux (Shell)
```bash
chmod +x uninstall.sh && ./uninstall.sh --clean-repo
```
