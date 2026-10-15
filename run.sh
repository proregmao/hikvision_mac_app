#!/usr/bin/env bash
# 海康威视 macOS 桌面管理工具启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$1" == "--restart" ] || [ "$1" == "restart" ]; then
    echo "[*] 正在重启管理服务..."
    pkill -f "hikvision_mac_app/main.py" 2>/dev/null || true
    sleep 0.5
fi

echo "[*] 正在启动海康威视 macOS 桌面管理工具..."
exec python3 "$SCRIPT_DIR/main.py" "$@"
