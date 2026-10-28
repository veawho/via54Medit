#!/usr/bin/env bash
# ==============================================================================
# uninstall.sh — via54Medit macOS / Linux 完全卸载与清理脚本 (Shell Uninstaller)
# ==============================================================================
set -e

HOME_DIR="${HOME:-~}"
BIN_DIR="$HOME_DIR/.via54medit"
CFG_DIR="$HOME_DIR/.medit"
PID_FILE="$CFG_DIR/daemon.pid"

echo "=================================================================="
echo " 🧹 via54Medit 一键完全卸载与清理脚本 (macOS / Linux)"
echo "=================================================================="

# 1. 终止进程
echo -e "\n[1/5] 检查并终止后台运行中的 via54Medit / Telemetry 进程..."
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
        echo "🛑 已终止记录中的守护进程 PID: $PID"
    fi
fi

# pkill 常见模式
for pat in "telemetry.cli" "usage_collector.py" "monday_finalize.py" "medit"; do
    pkill -9 -f "$pat" 2>/dev/null || true
done
echo "✅ 进程检查与清理完成"

# 2. 清理 Crontab
echo -e "\n[2/5] 清理系统 Crontab 定时排程..."
if crontab -l 2>/dev/null | grep -E "usage_collector|monday_finalize|medit|create_sched" >/dev/null 2>&1; then
    TMP_CRON=$(mktemp /tmp/medit_cron.XXXXXX)
    crontab -l | grep -v -E "usage_collector|monday_finalize|medit|create_sched" > "$TMP_CRON" || true
    crontab "$TMP_CRON"
    rm -f "$TMP_CRON"
    echo "🗑️ 已清除 Crontab 中所有 via54Medit 定时任务"
else
    echo "✅ Crontab 中无残留任务"
fi

# 3. 清理 macOS LaunchAgent
if [ "$(uname)" = "Darwin" ]; then
    echo -e "\n[3/5] 清理 macOS LaunchAgent..."
    PLIST="$HOME_DIR/Library/LaunchAgents/com.via54.medit.telemetry.plist"
    if [ -f "$PLIST" ]; then
        launchctl bootout "gui/$(id -u)/com.via54.medit.telemetry" 2>/dev/null || true
        launchctl unload -w "$PLIST" 2>/dev/null || true
        rm -f "$PLIST"
        echo "🗑️ 已移除 LaunchAgent: $PLIST"
    else
        echo "✅ 无 LaunchAgent 残留"
    fi
else
    echo -e "\n[3/5] Linux 平台跳过 LaunchAgent 清理"
fi

# 4. 删除已部署目录
echo -e "\n[4/5] 删除部署主目录 (~/.via54medit 与 ~/.medit)..."
rm -rf "$BIN_DIR" "$CFG_DIR"
echo "🗑️ 已彻底清除: $BIN_DIR 与 $CFG_DIR"

# 5. 清理本地仓库 (可选)
if [ "$1" = "--clean-repo" ]; then
    echo -e "\n[5/5] 清理本地代码仓库..."
    TARGET_REPO="${2:-$(pwd)}"
    if [ -d "$TARGET_REPO/.git" ]; then
        rm -rf "$TARGET_REPO"
        echo "🗑️ 已删除本地仓库: $TARGET_REPO"
    else
        echo "⚠️ 未能识别有效 .git 目录: $TARGET_REPO"
    fi
else
    echo -e "\n[5/5] 保留本地代码仓库 (可传入 --clean-repo 进行删除)"
fi

echo -e "\n========================= 卸载完成 ========================="
echo "✅ via54Medit 已从系统中完全卸载并清理干净！"
