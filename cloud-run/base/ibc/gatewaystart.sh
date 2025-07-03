#!/bin/bash

# =======================================================
# == FINAL GOLDEN SCRIPT: gatewaystart.sh
# =======================================================

set -e
set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}
TWS_VERSION=${TWS_VERSION:-1030}

IBC_PATH="/opt/ibc"
TWS_PATH=${TWS_PATH:-/root/Jts} # 使用经过验证的顶层路径
LOG_PATH="/opt/ibc/logs"

# --- 2. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via official IBC scripts ---"

# --- 3. 直接在前台调用 IBC 的核心启动脚本 ---
# 使用 exec 来让它成为主进程
exec "${IBC_PATH}/scripts/ibcstart.sh" \
    "${TWS_VERSION}" \
    --gateway \
    "--mode=${TRADING_MODE}" \
    "--user=${TWSUSERID}" \
    "--pw=${TWSPASSWORD}" \
    "--tws-path=${TWS_PATH}" \
    "--ibc-path=${IBC_PATH}" \
    "--ibc-ini=${IBC_PATH}/config.ini"