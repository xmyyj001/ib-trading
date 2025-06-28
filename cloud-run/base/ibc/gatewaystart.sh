#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION v5: gatewaystart.sh
# =======================================================

set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
TWS_PATH="/opt/ibgateway"
LOG_PATH="/opt/ibc/logs"

# --- 2. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via official IBC scripts ---"

# --- 3. 直接在前台调用 IBC 的核心启动脚本 ---
# 关键修复：使用官方发行版中正确的脚本路径
# 我们使用 exec 来让它成为主进程
exec "${IBC_PATH}/scripts/ibcstart.sh" \
    "--mode=${TRADING_MODE}" \
    "--user=${TWSUSERID}" \
    "--pw=${TWSPASSWORD}" \
    "--tws-path=${TWS_PATH}" \
    "--ibc-path=${IBC_PATH}" \
    "--log-path=${LOG_PATH}"