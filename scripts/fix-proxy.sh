#!/bin/bash
# fix-proxy.sh — 永久修复 macOS "7890 死代理" 引起的 ZCode EPIPE
#
# 根因: macOS 网络设置里 Ethernet 接口的 HTTP/HTTPS 代理指向 127.0.0.1:7890,
#       但 7890 端口没有进程 LISTEN. 所有走系统代理的流量在 Node.js 拿 EPIPE.
#
# 修复: 把代理端口改成 Clash 实际在跑的 14122 (你机器上 ls -nP 14122 = Clash).
#
# 何时运行:
#   - 启动 ZCode 之前 (手动)
#   - Clash 启动后 (手动)
#   - launchd plist (开机自动跑, 见 ~/Library/LaunchAgents/com.via54.fix-proxy.plist)
#   - ZCode 报 EPIPE 时 (手动)
#
# 用法:
#   fix-proxy.sh             检查并自动修复
#   fix-proxy.sh --check    只检查不修
#   fix-proxy.sh --status   显示当前代理配置

set -e

INTERFACE="${INTERFACE:-Ethernet}"
PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
GOOD_PORT="${GOOD_PORT:-14122}"
BAD_PORT="${BAD_PORT:-7890}"

cmd_check() {
  echo "=== 当前 macOS 代理配置 ==="
  echo "-- HTTP proxy --"
  networksetup -getwebproxy "$INTERFACE" 2>&1
  echo "-- HTTPS proxy --"
  networksetup -getsecurewebproxy "$INTERFACE" 2>&1
  echo
  echo "=== 端口 LISTEN 状态 ==="
  if lsof -nP -iTCP:"$GOOD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    local p
    p=$(lsof -nP -iTCP:"$GOOD_PORT" -sTCP:LISTEN -F p 2>/dev/null | head -1 | cut -c2-)
    echo "  $GOOD_PORT: LISTEN (PID $p) ✅"
  else
    echo "  $GOOD_PORT: NOT LISTEN ❌ (代理服务没起来)"
  fi
  if lsof -nP -iTCP:"$BAD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  $BAD_PORT: LISTEN (但通常不是真代理,可能是别的服务)"
  else
    echo "  $BAD_PORT: NOT LISTEN ⚠️  ← 死代理 (会引发 EPIPE)"
  fi
}

cmd_fix() {
  local current_http_port current_https_port
  # networksetup -getwebproxy 输出格式:
  #   Enabled: Yes
  #   Server: 127.0.0.1
  #   Port: 14122
  current_http_port=$(networksetup -getwebproxy "$INTERFACE" 2>/dev/null | awk -F': ' '/^Port:/ {gsub(/^ +/,"",$2); print $2; exit}')
  current_https_port=$(networksetup -getsecurewebproxy "$INTERFACE" 2>/dev/null | awk -F': ' '/^Port:/ {gsub(/^ +/,"",$2); print $2; exit}')

  if [ "$current_http_port" = "$GOOD_PORT" ] && [ "$current_https_port" = "$GOOD_PORT" ]; then
    echo "✓ 代理配置正常 ($PROXY_HOST:$GOOD_PORT)"
    return 0
  fi

  if ! lsof -nP -iTCP:"$GOOD_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "❌ $GOOD_PORT 端口没有 LISTEN, 不能切代理 (Clash 没起来?)"
    return 1
  fi

  echo "修复代理: HTTP=$current_http_port HTTPS=$current_https_port → $GOOD_PORT"
  networksetup -setwebproxy "$INTERFACE" "$PROXY_HOST" "$GOOD_PORT"
  networksetup -setsecurewebproxy "$INTERFACE" "$PROXY_HOST" "$GOOD_PORT"
  echo "✓ 修复完成"
  echo
  cmd_check
}

case "${1:-}" in
  --status)
    cmd_check
    ;;
  --check)
    cmd_check
    exit 0
    ;;
  --help|-h)
    echo "Usage: $0 [--check|--status|--help]"
    exit 0
    ;;
  *)
    cmd_check
    cmd_fix
    ;;
esac
