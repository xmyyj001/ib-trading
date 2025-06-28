#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION v7: gatewaystart.sh
# =======================================================

set -e
set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
TWS_PATH="/opt/ibgateway"
LOG_PATH="/opt/ibc/logs"
JAVA_EXEC="/usr/bin/java"

# --- 2. 构建真正正确的 Classpath ---
# 搜集 TWS_PATH 和 IBC_PATH 下的所有 .jar 文件
ALL_JARS=$(find "${TWS_PATH}" "${IBC_PATH}" -name '*.jar' -print | tr '\n' ':')
CP="${ALL_JARS}"

# --- 3. 构建 IBC 参数 ---
IBC_ARGS="TwsPath=${TWS_PATH} IbLoginId=${TWSUSERID} IbPassword=${TWSPASSWORD} TradingMode=${TRADING_MODE}"

# --- 4. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via Direct Java Call (v7) ---"
echo "Classpath: ${CP}"

# --- 5. 直接执行 java 命令 ---
exec "${JAVA_EXEC}" \
    -cp "${CP}" \
    -Dlog.path="${LOG_PATH}/" \
    -Dibc.ini.path="${IBC_PATH}" \
    com.ib.controller.IBCoco \
    "${IBC_ARGS}"