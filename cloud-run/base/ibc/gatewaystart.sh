#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION v9: gatewaystart.sh
# =======================================================

set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
# TWS_PATH 会从 Dockerfile 的 ENV 中继承，现在是正确的 /root/Jts
TWS_PATH=${TWS_PATH:-/root/Jts}
LOG_PATH="/opt/ibc/logs"

# --- 2. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway from verified path: ${TWS_PATH} ---"

# --- 3. 直接在前台调用 IBC 的核心启动脚本 ---
exec "${IBC_PATH}/scripts/ibcstart.sh" \
    "--mode=${TRADING_MODE}" \
    "--user=${TWSUSERID}" \
    "--pw=${TWSPASSWORD}" \
    "--tws-path=${TWS_PATH}" \
    "--ibc-path=${IBC_PATH}" \
    "--log-path=${LOG_PATH}"