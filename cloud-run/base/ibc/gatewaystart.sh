#!/bin/bash

# =======================================================
# == FINAL DEFINITIVE VERSION (GOLDEN SCRIPT v3): gatewaystart.sh
# =======================================================

set -e
set -x

# --- 1. 定义所有路径和参数 ---
TRADING_MODE=${TRADING_MODE:-paper}
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}

IBC_PATH="/opt/ibc"
TWS_PATH=${TWS_PATH:-/root/Jts/ibgateway/1030}
LOG_PATH="/opt/ibc/logs"
JAVA_EXEC="/usr/bin/java"

# --- 2. 构建最终的、正确的 Classpath ---
# 基于我们亲眼所见的事实构建
TWS_JARS=$(find "${TWS_PATH}/jars" -name '*.jar' -print | tr '\n' ':')
# 关键：我们现在知道 v3.7.0 的核心 Jar 是 IBController.jar
IBC_JARS=$(find "${IBC_PATH}" -name 'IBController.jar' -print | tr '\n' ':')
CP="${TWS_JARS}${IBC_JARS}"

# --- 3. 构建 IBC 参数 ---
IBC_ARGS="TwsPath=${TWS_PATH} IbLoginId=${TWSUSERID} IbPassword=${TWSPASSWORD} TradingMode=${TRADING_MODE}"

# --- 4. 确保日志目录存在 ---
mkdir -p "${LOG_PATH}"

echo "--- [INFO] Launching IB Gateway via Direct Java Call (Golden Version) ---"

# --- 5. 直接执行 java 命令 ---
exec "${JAVA_EXEC}" \
    -cp "${CP}" \
    -Dlog.path="${LOG_PATH}/" \
    -Dibc.ini.path="${IBC_PATH}" \
    com.ib.controller.IBCoco \
    "${IBC_ARGS}"